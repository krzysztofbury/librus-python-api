# librus-python-api

An independent, typed, async Python client for Librus Synergia, built to replace
`librus-apix` as the backend of [librus-mcp](https://github.com/krzysztofbury/librus-mcp).

One `LibrusService` manages several independent Librus logins under a shared,
bounded traffic policy and returns immutable, typed results. A parent login and
a student login stay separate security contexts even when they belong to the
same student.

Status: `0.4.5`, local-first. Nothing is published to PyPI yet; publication
starts at `1.0.0rc1`. See [TODO.md](TODO.md) for the roadmap.

## What it reads

| Family | Calls | Latest live evidence |
| --- | --- | --- |
| Identity, profile | `identity`, `student_information` | Verified on two student contexts |
| Grades | `final_grades`, `grades`, `grades_window` | Verified on two student contexts |
| Attendance | `attendance`, `attendance_window`, `attendance_detail`, `gateway_attendance`, `attendance_frequency`, `subject_frequency` | Verified on two student contexts |
| Timetable | `timetable` (explicit week) | Verified on two contexts, including substitution notices |
| Announcements | `announcements` | Verified on two student contexts |
| Agenda | `agenda`, `agenda_detail` | Verified on two contexts, two months each |
| Homework | `homework`, `homework_detail` | Verified: populated and empty |
| Completed lessons | `completed_lessons_page`, `completed_lessons` | Disabled by the school on every available account; returns `ViewDisabledError` |
| Message lists | `messages_page`, `messages` | 0.4.5: one populated two-page received mailbox and page-zero sent rows; independent byte/browser comparison |
| Recipient discovery | `recipient_groups`, `recipient_group_choices`, `recipients` | 0.4.5: four login contexts, five named types and an anonymous target; empty group options observed, populated selection remains offline-qualified |
| Message content | `message_content` | 0.4.5: populated sent subject/date metadata and individual receipts; 0.4.3 received attachment evidence retained |
| Attachment bytes | `stream_attachment` | 0.4.3: installed wheel streams one 930,056-byte file to clean EOF without retaining it; strict credential-free destination |
| Notification counts | `notification_counts` | 0.4.4: installed smoke on five shown categories; same-byte apix and independent Chromium agree |
| Read-once events | `consume_schedule_events`, `decode_schedule_events` | 0.4.4: offline checkpoint/cancellation/replay proof only; no live consume |

"Verified" refers to the release-specific observations in the verification log,
not a claim that every family was called live again in 0.4.5. School reads,
timetable, profile, messages and recipients were compared with Chromium's independent
rendering of the same bytes. It is not a claim about every school's layout. Details and
remaining gaps are in [VERIFICATION.md](VERIFICATION.md).

Notification primitives do not own seen state or persistence. Sending is plan-only. Message-list live
gaps and the apix coverage comparison are in [contracts/messages.md](contracts/messages.md).
Recipient gaps and apix coverage are in [contracts/recipients.md](contracts/recipients.md).
Content requires explicit potential mark-read consent; see
[contracts/message-content.md](contracts/message-content.md) for its qualification gaps.
Stream lifecycle, byte budgets and destination restrictions are specified in
[contracts/attachments.md](contracts/attachments.md).
Read-once checkpoint ownership and its remaining loss windows are specified in
[contracts/notifications.md](contracts/notifications.md); routine live checks never consume events.
Behaviour notes stay unsupported until a populated page has been observed
([decision](contracts/behaviour-notes.md)).

## Example

```python
import asyncio
from datetime import date

from librus_python_api import AccountCredentials, LibrusService


async def main() -> None:
    accounts = {
        "parent": AccountCredentials(login="...", password="..."),
        "student": AccountCredentials(login="...", password="..."),
    }
    async with LibrusService(accounts) as service:
        parent = service.account("parent")
        homework = await parent.homework(date(2026, 9, 1), date(2026, 9, 30))
        for item in homework.items:
            print(item.subject, item.topic, item.due_on, item.marked_done_at)


asyncio.run(main())
```

See [API.md](API.md) for every call, its result types and its limits.

## Guarantees

- **Bounded traffic.** Every request, including each login hop, passes one
  service-wide scheduler: 5 requests/second with a burst of 10, two active
  requests, one per account, bounded queues. Budgets cap requests, bytes and
  time per operation.
- **No silent partial data.** Unrecognized layouts raise typed errors instead
  of returning empty or partial results. A view disabled by the school is
  `ViewDisabledError`, not an empty list.
- **No unsafe replays.** View-selection and content opens are never replayed.
  Hidden persistent-connection retries are disabled. Safe reads
  recover a proven session expiry with at most one new login. Credentials are
  never resubmitted by a retry policy.
- **Isolation.** Each login has its own cookies, session, cache and cooldowns.
- **Redaction.** Errors carry a closed kind only: no response bodies, URLs,
  aliases or secrets. Result reprs omit personal fields.

## Installation (local)

```sh
uv build --no-sources
uv pip install dist/*.whl
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, checks, the test layout and
the live verification workflow. Repository content is English and contains no
private or school data.

## License

MIT. See [LICENSE](LICENSE).
