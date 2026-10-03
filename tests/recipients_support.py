"""Independently authored recipient structure with invented names and IDs."""

from html import escape


def groups_html(
    types: tuple[str, ...] = ("nauczyciel", "wychowawca", "grupa"),
    *,
    header: bool = True,
) -> str:
    heading = (
        "<thead><tr><td></td><td>Fixture group selection</td></tr></thead>"
        if header
        else ""
    )
    rows = "".join(
        '<tr><td><input type="radio" class="recipiantTypeRadio" '
        f'id="radio_{t}" value="{t}"></td>'
        f'<td colspan="2"><label for="radio_{t}">Fixture {t} group</label></td></tr>'
        for t in types
    )
    return (
        f'<html><table class="message-recipients">{heading}'
        f"<tbody>{rows}</tbody></table></html>"
    )


def recipient_html(
    records: tuple[tuple[str, str], ...] = (
        ("101", "Fixture Person"),
        ("102", "Other Fixture Person"),
    ),
) -> str:
    return (
        '<html><div class="fixture-recipients"><input type="checkbox">'
        + "".join(
            f'<input type="checkbox" id="adresat_{identifier}" value="{identifier}">'
            f'<label for="adresat_{identifier}">{escape(label)}</label>'
            for identifier, label in records
        )
        + "</div></html>"
    )


def choice_html(options: tuple[tuple[str, str, bool], ...] = ()) -> str:
    """Observed empty selector plus independently invented populated options."""
    choices = "".join(
        f'<option value="{identifier}"{" disabled" if disabled else ""}>'
        f"{escape(label)}</option>"
        for identifier, label, disabled in options
    )
    return f"""<html><body><table><tr><td>
    <select name="idGrupy" id="idGrupy"><option value="0"></option>{choices}</select>
    <input type="button" value="Fixture choose"></td></tr></table>
    <div><p class="msgEmptyTable">Wybierz grupę</p></div></body></html>"""
