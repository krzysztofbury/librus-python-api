"""The release and weekly profiles. Every check declares the routes it reads."""

import hmac
from datetime import date, timedelta

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
from scripts.live_check.credentials import MAX_SLOTS
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
RELEASE = Profile(
    "release",
    (*RELEASE_READS, session_alive),
    max_requests=48,
    timeout_seconds=180,
    max_accounts=4,
    deadline_seconds=720,
)


def month_bounds(day: date) -> tuple[date, date]:
    first = day.replace(day=1)
    following = (first + timedelta(days=32)).replace(day=1)
    return first, following - timedelta(days=1)


@check("student_information", reads={"student_information"})
async def student_information(ctx: Context) -> Observed:
    await ctx.client.student_information(budget=ctx.budget)
    return POPULATED


@check("grades", reads={"grades"})
async def grades(ctx: Context) -> Observed:
    records = (await ctx.client.grades(budget=ctx.budget)).records
    numeric, descriptive = len(records.numeric), len(records.descriptive)
    return coverage_of(numeric + descriptive, numeric=numeric, descriptive=descriptive)


@check("grades_window", reads={"grades"})
async def grades_window(ctx: Context) -> Observed:
    window = await ctx.client.grades_window(budget=ctx.budget)
    return coverage_of(len(window.numeric) + len(window.descriptive))


@check("final_grades", reads={"final_grades"})
async def final_grades(ctx: Context) -> Observed:
    result = await ctx.client.final_grades(budget=ctx.budget)
    return coverage_of(len(result.items), subjects=len(result.items))


@check(
    "school_year_archive",
    reads={"school_year_archive"},
    requires=has("school_year_archive"),
)
async def school_year_archive(ctx: Context) -> Observed:
    result = await ctx.client.school_year_archive(budget=ctx.budget)
    return coverage_of(len(result.years), years=len(result.years))


@check("attendance", reads={"attendance"})
async def attendance(ctx: Context) -> Observed:
    result = await ctx.client.attendance(budget=ctx.budget)
    ctx.state["attendance_detail"] = next(
        (item.detail_id for item in result.items if item.detail_id), None
    )
    ctx.state["attendance_day"] = result.items[0].day if result.items else None
    return coverage_of(len(result.items), records=len(result.items))


@check("attendance_window", reads={"attendance"})
async def attendance_window(ctx: Context) -> Observed:
    result = await ctx.client.attendance_window(budget=ctx.budget)
    return coverage_of(len(result.items))


@check(
    "attendance_detail",
    reads={"attendance", "attendance_detail"},
    references={"attendance_detail"},
    after="attendance",
)
async def attendance_detail(ctx: Context) -> Observed:
    detail_id = ctx.state.get("attendance_detail")
    if detail_id is None:
        return Observed(Coverage.EMPTY)
    result = await ctx.client.attendance_detail(detail_id, budget=ctx.budget)
    return coverage_of(len(result.fields), fields=len(result.fields))


@check("attendance_frequency", reads={"gateway_attendance"})
async def attendance_frequency(ctx: Context) -> Observed:
    await ctx.client.attendance_frequency(budget=ctx.budget)
    return POPULATED


@check(
    "subject_frequency",
    reads={
        "gateway_attendance",
        "attendance_lessons",
        "attendance_subjects",
        "attendance_lesson",
        "attendance_subject",
    },
    references={"attendance_lesson", "attendance_subject"},
    after="attendance",
)
async def subject_frequency(ctx: Context) -> Observed:
    day = ctx.state.get("attendance_day")
    if day is None:
        return Observed(Coverage.EMPTY)
    result = await ctx.client.subject_frequency(day, day, budget=ctx.budget)
    return coverage_of(len(result.items), subjects=len(result.items))


@check("timetable", reads={"timetable"})
async def timetable(ctx: Context) -> Observed:
    monday = ctx.today - timedelta(days=ctx.today.weekday())
    result = await ctx.client.timetable(monday, budget=ctx.budget)
    periods = sum(len(day.periods) for day in result.days)
    return coverage_of(periods, periods=periods)


@check("agenda", reads={"agenda"})
async def agenda(ctx: Context) -> Observed:
    result = await ctx.client.agenda(ctx.today.year, ctx.today.month, budget=ctx.budget)
    events = [event for day in result.days for event in day.events]
    ctx.state["agenda_reference"] = next(
        (event.reference for event in events if event.reference), None
    )
    return coverage_of(len(events), events=len(events))


@check(
    "agenda_detail",
    reads={"agenda_detail"},
    references={"agenda_detail"},
    after="agenda",
)
async def agenda_detail(ctx: Context) -> Observed:
    reference = ctx.state.get("agenda_reference")
    if reference is None:
        return Observed(Coverage.EMPTY)
    result = await ctx.client.agenda_detail(reference, budget=ctx.budget)
    return coverage_of(len(result.fields), fields=len(result.fields))


@check("homework", reads={"homework"})
async def homework(ctx: Context) -> Observed:
    first, last = month_bounds(ctx.today)
    result = await ctx.client.homework(first, last, budget=ctx.budget)
    ctx.state["homework_reference"] = next(
        (item.reference for item in result.items if item.reference), None
    )
    return coverage_of(len(result.items), items=len(result.items))


@check(
    "homework_detail",
    reads={"homework_detail"},
    references={"homework_detail"},
    after="homework",
)
async def homework_detail(ctx: Context) -> Observed:
    reference = ctx.state.get("homework_reference")
    if reference is None:
        return Observed(Coverage.EMPTY)
    result = await ctx.client.homework_detail(reference, budget=ctx.budget)
    return coverage_of(len(result.fields), fields=len(result.fields))


@check("announcements", reads={"announcements"})
async def announcements(ctx: Context) -> Observed:
    result = await ctx.client.announcements(budget=ctx.budget)
    return coverage_of(len(result.items), items=len(result.items))


@check("completed_lessons", reads={"completed_lessons"})
async def completed_lessons(ctx: Context) -> Observed:
    first, _ = month_bounds(ctx.today)
    result = await ctx.client.completed_lessons_page(
        first, ctx.today, budget=ctx.budget
    )
    return coverage_of(len(result.items), items=len(result.items))


def legacy_messages(folder: MessageFolder) -> Check:
    @check(f"legacy_messages {folder.value}", reads={f"messages_{folder.value}"})
    async def probe(ctx: Context) -> Observed:
        page = await ctx.client.messages_page(folder, budget=ctx.budget)
        if page.items:
            ctx.state[f"legacy_first {folder.value}"] = page.items[0].reference
        return coverage_of(len(page.items), items=len(page.items))

    return probe


@check(
    "legacy_sent_content",
    reads={"message_content_sent"},
    references={"message_content_sent"},
    after="legacy_messages sent",
)
async def legacy_sent_content(ctx: Context) -> Observed:
    reference = ctx.state.get("legacy_first sent")
    if reference is None:
        return Observed(Coverage.EMPTY)
    if reference.folder is not MessageFolder.SENT:
        raise CheckFailed("not_a_sent_message")
    await ctx.client.message_content(reference, budget=ctx.budget)
    return POPULATED


@check("recipient_groups", reads={"recipient_groups"})
async def recipient_groups(ctx: Context) -> Observed:
    result = await ctx.client.recipient_groups(budget=ctx.budget)
    ctx.state["recipient_group"] = next(
        (g.reference for g in result.groups if g.available and g.lookup_supported),
        None,
    )
    return coverage_of(len(result.groups), groups=len(result.groups))


@check("recipients", reads={"recipients"}, after="recipient_groups")
async def recipients(ctx: Context) -> Observed:
    group = ctx.state.get("recipient_group")
    if group is None:
        return Observed(Coverage.EMPTY)
    result = await ctx.client.recipients(group, budget=ctx.budget)
    return coverage_of(len(result.items), count=len(result.items))


@check(
    "modern_recipient_types",
    reads={MODERN, "modern_recipient_types"},
    after=MODERN,
)
async def modern_recipient_types(ctx: Context) -> Observed:
    result = await ctx.client.modern_recipient_types(budget=ctx.budget)
    ctx.state["modern_type"] = next(
        (t.reference for t in result.items if t.lookup_supported), None
    )
    return coverage_of(len(result.items), types=len(result.items))


@check(
    "modern_recipients",
    reads={
        MODERN,
        "modern_recipients",
        "modern_school_recipients",
        "modern_class_parents",
    },
    after="modern_recipient_types",
)
async def modern_recipients(ctx: Context) -> Observed:
    recipient_type = ctx.state.get("modern_type")
    if recipient_type is None:
        return Observed(Coverage.EMPTY)
    result = await ctx.client.modern_recipients(recipient_type, budget=ctx.budget)
    return coverage_of(len(result.items), count=len(result.items))


@check(
    "modern_sent_content",
    reads={MODERN, "modern_content_sent"},
    references={"modern_content_sent"},
    after="modern_page sent",
)
async def modern_sent_content(ctx: Context) -> Observed:
    reference = ctx.state.get("modern_first sent")
    if reference is None:
        return Observed(Coverage.EMPTY)
    if reference.folder is not MessageFolder.SENT or reference.archived:
        raise CheckFailed("not_a_current_sent_message")
    await ctx.client.modern_message_content(reference, budget=ctx.budget)
    return POPULATED


WEEKLY_READS: tuple[Check, ...] = (
    student_information,
    grades,
    grades_window,
    final_grades,
    school_year_archive,
    attendance,
    attendance_window,
    attendance_detail,
    attendance_frequency,
    subject_frequency,
    timetable,
    agenda,
    agenda_detail,
    homework,
    homework_detail,
    announcements,
    completed_lessons,
    legacy_messages(MessageFolder.RECEIVED),
    legacy_messages(MessageFolder.SENT),
    legacy_sent_content,
    recipient_groups,
    recipients,
    modern_recipient_types,
    modern_recipients,
    modern_sent_content,
)
# Measured fixture requests per login: 48. The budget leaves live headroom for
# more attendance rows to resolve, as the design targets about 70.
WEEKLY = Profile(
    "weekly",
    (*RELEASE_READS, *WEEKLY_READS, session_alive),
    max_requests=70,
    timeout_seconds=240,
    max_accounts=MAX_SLOTS,
    deadline_seconds=600,
)
PROFILES: dict[str, Profile] = {"release": RELEASE, "weekly": WEEKLY}
