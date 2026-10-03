"""Original invented content fixtures; source-informed, not live wire evidence."""

from librus_python_api import MessageFolder


def content_html(
    folder: MessageFolder = MessageFolder.RECEIVED,
    *,
    content: str = "First line<br>Second <strong>line</strong>",
    attachments: str = "",
    read_receipt: bool = False,
) -> str:
    label = "Nadawca" if folder is MessageFolder.RECEIVED else "Adresat"
    receipt = (
        '<table class="stretch"><tr><td class="medium">Przeczytano</td>'
        '<td class="left">2026-10-02 09:00:00</td></tr></table>'
        if read_receipt
        else ""
    )
    return f"""<html><body><table class="stretch"><tbody>
    <tr><td>{label}:</td><td class="left">Fixture Person</td></tr>
    <tr><td>Temat:</td><td class="left">Fixture subject</td></tr>
    <tr><td>Wysłano:</td><td class="left">2026-10-02 08:15:30</td></tr>
    </tbody></table><div class="container-message-content">{content}</div>
    {attachments}{receipt}</body></html>"""


def attachment_html(
    identifier: str = "301", name: str = "Fixture file.txt", message: str = "101"
) -> str:
    return f"""<table><tr><td>{name}</td><td><img alt="download"
    onclick="window.location.href='/wiadomosci/pobierz_zalacznik/{message}/{identifier}';">
    </td></tr></table>"""


def sent_content_html(
    receipts: tuple[tuple[str, str], ...] = (
        ("Fixture Office", "2026-10-03 09:00:00"),
    ),
) -> str:
    """Original sent shape: no correspondent field, separate recipient receipts."""
    rows = "".join(
        f"<tr><td>{name}</td><td>{status}</td></tr>" for name, status in receipts
    )
    return f"""<html><body><table class="stretch"><tbody>
    <tr><td>Temat</td><td>Fixture sent subject</td></tr>
    <tr><td>Wysłano</td><td>2026-10-03 08:00:00</td></tr></tbody></table>
    <div class="container-message-content">Fixture sent body<br>Second line</div>
    <table class="stretch"><tbody><tr><td colspan="3">Przeczytano</td></tr>
    {rows}</tbody></table></body></html>"""
