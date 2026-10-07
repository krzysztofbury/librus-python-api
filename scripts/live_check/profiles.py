"""The release and weekly profiles. Every check declares the routes it reads."""

import hmac

from librus_python_api import MessageFolder
from scripts.live_check.checks import (
    Check,
    CheckFailed,
    Context,
    Observed,
    accepts,
    check,
    coverage_of,
    has,
    identity_key,
)
from scripts.live_check.report import Coverage
from scripts.live_check.runner import Profile

POPULATED = Observed(Coverage.POPULATED)
MODERN = "modern_identity"


@check("identity", reads={"identity"})
async def identity(ctx: Context) -> Observed:
    result = await ctx.client.identity(budget=ctx.budget)
    expected = ctx.expected_identity
    if expected is not None and not hmac.compare_digest(
        identity_key(result).encode(), expected.encode()
    ):
        raise CheckFailed("identity_mismatch")
    return POPULATED


@check("notification_counts", reads={"student_information"})
async def notification_counts(ctx: Context) -> Observed:
    result = await ctx.client.notification_counts(budget=ctx.budget)
    categories = [item.category.value for item in result.items]
    if not categories:
        raise CheckFailed("no_counter_categories")
    return Observed(
        Coverage.POPULATED,
        (("categories", len(categories)), ("messages", "messages" in categories)),
    )


@check("modern_identity", reads={MODERN})
async def modern_identity(ctx: Context) -> Observed:
    await ctx.client.modern_identity(budget=ctx.budget)
    return POPULATED


@check(
    "modern_unread_counts",
    reads={MODERN, "modern_unread_counts"},
    requires=has("modern_unread_counts"),
    after=MODERN,
)
async def modern_unread_counts(ctx: Context) -> Observed:
    result = await ctx.client.modern_unread_counts(budget=ctx.budget)
    return Observed(
        Coverage.POPULATED,
        (("inbox", result.current.inbox), ("archive_inbox", result.archive.inbox)),
    )


def modern_page(folder: MessageFolder) -> Check:
    @check(
        f"modern_page {folder.value}",
        reads={MODERN, f"modern_messages_{folder.value}"},
        after=MODERN,
    )
    async def probe(ctx: Context) -> Observed:
        page = await ctx.client.modern_messages_page(folder, budget=ctx.budget)
        ctx.state[f"modern_total {folder.value}"] = page.total_count
        if page.items:
            ctx.state[f"modern_first {folder.value}"] = page.items[0].reference
        return coverage_of(
            page.total_count, total=page.total_count, items=len(page.items)
        )

    return probe


def modern_archive_page(folder: MessageFolder) -> Check:
    @check(
        f"modern_archive_page {folder.value}",
        reads={MODERN, f"modern_archive_messages_{folder.value}"},
        requires=accepts("modern_messages_page", "archived"),
        after=MODERN,
    )
    async def probe(ctx: Context) -> Observed:
        page = await ctx.client.modern_messages_page(
            folder, budget=ctx.budget, archived=True
        )
        if not all(item.reference.archived for item in page.items):
            raise CheckFailed("unflagged_archive_item")
        return coverage_of(
            page.total_count, total=page.total_count, items=len(page.items)
        )

    return probe


def modern_correspondents(folder: MessageFolder) -> Check:
    route = "modern_senders" if folder is MessageFolder.RECEIVED else "modern_receivers"

    @check(
        f"modern_correspondents {folder.value}",
        reads={MODERN, route},
        requires=has("modern_correspondents"),
        after=MODERN,
    )
    async def probe(ctx: Context) -> Observed:
        people = await ctx.client.modern_correspondents(folder, budget=ctx.budget)
        if people.items:
            ctx.state[f"correspondent {folder.value}"] = people.items[0].reference
        return coverage_of(len(people.items), count=len(people.items))

    return probe


def filtered_page(folder: MessageFolder) -> Check:
    @check(
        f"filtered_page {folder.value}",
        reads={MODERN, f"modern_messages_{folder.value}"},
        requires=has("modern_correspondents"),
        after=f"modern_correspondents {folder.value}",
    )
    async def probe(ctx: Context) -> Observed:
        reference = ctx.state.get(f"correspondent {folder.value}")
        whole = ctx.state.get(f"modern_total {folder.value}")
        if reference is None or whole is None:
            return Observed(Coverage.EMPTY)
        page = await ctx.client.modern_messages_page(
            folder, budget=ctx.budget, correspondent=reference
        )
        if not 1 <= page.total_count <= whole:
            raise CheckFailed("filter_not_narrowed")
        if page.correspondent != reference:
            raise CheckFailed("filter_not_recorded")
        return coverage_of(page.total_count, total=page.total_count)

    return probe


@check(
    "unread_only_page",
    reads={MODERN, "modern_messages_received"},
    requires=has("modern_correspondents"),
    after=MODERN,
)
async def unread_only_page(ctx: Context) -> Observed:
    page = await ctx.client.modern_messages_page(
        MessageFolder.RECEIVED, budget=ctx.budget, unread_only=True
    )
    if not all(item.unread for item in page.items):
        raise CheckFailed("read_item_in_unread_list")
    return coverage_of(page.total_count, total=page.total_count)


@check(
    "modern_teacher_subjects",
    reads={MODERN, "modern_teacher_subjects"},
    requires=has("modern_teacher_subjects"),
    after=MODERN,
)
async def modern_teacher_subjects(ctx: Context) -> Observed:
    result = await ctx.client.modern_teacher_subjects(budget=ctx.budget)
    return coverage_of(len(result.items), count=len(result.items))


@check("session_alive", reads={"identity"})
async def session_alive(ctx: Context) -> Observed:
    # A fresh identity read proves the session survived every step, including
    # the counter read that once logged parent accounts out.
    await ctx.client.identity(budget=ctx.budget)
    return POPULATED


FOLDERS = (MessageFolder.RECEIVED, MessageFolder.SENT)
RELEASE_READS: tuple[Check, ...] = (
    identity,
    notification_counts,
    modern_identity,
    modern_unread_counts,
    *(c for f in FOLDERS for c in (modern_page(f), modern_archive_page(f))),
    *(c for f in FOLDERS for c in (modern_correspondents(f), filtered_page(f))),
    unread_only_page,
    modern_teacher_subjects,
)
RELEASE = Profile("release", (*RELEASE_READS, session_alive), 48, 180)
PROFILES: dict[str, Profile] = {"release": RELEASE}
