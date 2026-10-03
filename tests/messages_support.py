"""Original mailbox markup using observed structure and invented records."""

from html import escape

from librus_python_api.models import MessageFolder


def message_row(
    identifier: str = "101",
    *,
    folder: MessageFolder = MessageFolder.RECEIVED,
    subject: str = "Fixture subject",
    correspondent: str = "Fixture Sender",
    stamp: str = "2026-10-02 08:15:30",
    unread: bool = True,
    attachment: bool = False,
    status: str = "NIE",
) -> str:
    number = "5" if folder is MessageFolder.RECEIVED else "6"
    href = f"/wiadomosci/1/{number}/{identifier}/f0"
    style = ' style="font-weight: bold;"' if unread else ""
    icon = (
        '<img src="/fixture-paperclip.png" alt="Fixture attachment">'
        if attachment
        else ""
    )
    extra = f"<td>{escape(status)}</td>" if folder is MessageFolder.SENT else ""
    return (
        '<tr class="line0"><td class="micro center"><input type="checkbox"></td>'
        f'<td class="micro center">{icon}</td>'
        f'<td{style}><a href="{href}">{correspondent}</a></td>'
        f'<td{style}><a href="{href}">{subject}</a></td>'
        f'<td class="medium center"{style}>{escape(stamp)}</td>{extra}'
        '<td class="micro center"><a href="javascript:void(0); return false;">'
        '<img src="/fixture-trash.png"></a></td></tr>'
    )


def messages_html(
    folder: MessageFolder = MessageFolder.RECEIVED,
    *,
    page: int = 0,
    count: int = 1,
    rows: str | None = None,
    pagination: bool = True,
    footer: bool = False,
    legacy_notice: bool = False,
) -> str:
    sent = folder is MessageFolder.SENT
    role = "Adresat" if sent else "Nadawca"
    width = 7 if sent else 6
    header = (
        f"<td></td><td></td><td>{role}</td><td>Temat</td><td>Wysłano [↑]</td>"
        + ("<td>Przeczytano</td>" if sent else "")
        + "<td></td>"
    )
    if rows is None:
        rows = message_row(folder=folder)
    if not rows:
        rows = (
            f'<tr class="line0"><td class="center" colspan="{width}">'
            "Brak wiadomości</td></tr>"
        )
    pager = (
        f'<div class="pagination"><span>Strona {page + 1} z&nbsp;{count}</span></div>'
        if pagination
        else ""
    )
    return (
        "<html><body><!-- Fixture comment -->"
        + (
            '<div class="warning-content">'
            "Korzystasz ze starej wersji modułu Wiadomości, "
            "która nie jest już rozwijana i nie zawiera wszystkich dostępnych funkcji. "
            "Przejdź do ustawień i włącz opcję: Używaj nowego systemu wiadomości.</div>"
            if legacy_notice
            else ""
        )
        + f'{pager}<table class="decorated stretch">'
        + f"<thead><tr>{header}</tr></thead><tbody>{rows}</tbody>"
        + (f'<tfoot><tr><td colspan="{width}"></td></tr></tfoot>' if footer else "")
        + "</table></body></html>"
    )
