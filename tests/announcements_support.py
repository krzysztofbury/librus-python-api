"""Original semantic announcement requirements and exact loopback HTTP fixture."""

from html import escape


def announcement_table(
    title: str = "Fixture notice",
    author: str = "Fixture Editor",
    day: str = "2026-10-01",
    content: str = "<p>Fixture first paragraph.</p><p>Fixture final paragraph.</p>",
) -> str:
    return (
        '<table class="margin-top printable big center decorated">'
        '<thead><tr><td colspan="2">' + escape(title) + "</td></tr></thead><tbody>"
        '<tr class="line0"><th>Dodał:</th><td>' + escape(author) + "</td></tr>"
        '<tr class="line1"><th>Data publikacji:</th><td>' + escape(day) + "</td></tr>"
        '<tr class="line0"><th>Treść:</th><td>' + content + "</td></tr>"
        '<tr><td colspan="2"></td></tr></tbody></table>'
    )


def page(*tables: str) -> str:
    return "<!doctype html><html><body>" + "".join(tables) + "</body></html>"


def empty_page() -> str:
    return page(
        '<div class="center container resizeable border-red">'
        "<div><p>Brak ogłoszeń.</p></div></div>"
    )
