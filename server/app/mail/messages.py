"""Die Texte der einzelnen Mails.

Kein Template-Framework: eine Handvoll Funktionen, die (Betreff, Text, HTML)
liefern. Der Ton ist derselbe wie in der Oberflaeche — knapp, ohne Ausrufezeichen,
ohne Marketing.
"""

from html import escape

from ..config import settings

# Ein schmales Blatt in der Schriftfamilie der Anwendung. Mailprogramme koennen
# kein externes CSS, deshalb steht alles inline; auf Bilder und Webfonts wird
# bewusst verzichtet, weil beide beim Empfaenger blockiert werden.
_HTML_SHELL = """\
<div style="font-family:'IBM Plex Sans',Helvetica,Arial,sans-serif;font-size:14px;
line-height:1.5;color:#24261f;max-width:34rem">
{body}
<p style="margin-top:2rem;padding-top:0.75rem;border-top:1px solid #dcdcd4;
font-size:11px;color:#8b8f84">DataSynq One</p>
</div>"""


def _html(body: str) -> str:
    return _HTML_SHELL.format(body=body)


def _button(href: str, label: str) -> str:
    return (
        f'<p><a href="{escape(href)}" style="display:inline-block;padding:0.5rem 0.9rem;'
        f'background:#161814;color:#ffffff;text-decoration:none;font-weight:500">'
        f"{escape(label)}</a></p>"
    )


def invitation(display_name: str, link: str) -> tuple[str, str, str]:
    hours = settings.invitation_ttl_hours
    subject = "Ihr Zugang zu DataSynq One"
    text = (
        f"Hallo {display_name},\n\n"
        f"für Sie wurde ein Zugang zu DataSynq One eingerichtet. Über den folgenden "
        f"Link vergeben Sie Ihr Passwort und sind anschließend angemeldet:\n\n"
        f"{link}\n\n"
        f"Der Link gilt {hours} Stunden und lässt sich nur einmal verwenden.\n\n"
        f"Wenn Sie mit diesem Zugang nichts anfangen können, ignorieren Sie diese "
        f"Nachricht — ohne den Link passiert nichts.\n"
    )
    html = _html(
        f"<p>Hallo {escape(display_name)},</p>"
        f"<p>für Sie wurde ein Zugang zu DataSynq One eingerichtet. Über den folgenden "
        f"Link vergeben Sie Ihr Passwort und sind anschließend angemeldet.</p>"
        f"{_button(link, 'Passwort vergeben')}"
        f"<p style='color:#6f7369'>Der Link gilt {hours} Stunden und lässt sich nur "
        f"einmal verwenden. Wenn Sie mit diesem Zugang nichts anfangen können, "
        f"ignorieren Sie diese Nachricht — ohne den Link passiert nichts.</p>"
    )
    return subject, text, html


def password_reset(display_name: str, link: str) -> tuple[str, str, str]:
    hours = settings.invitation_ttl_hours
    subject = "Neues Passwort für DataSynq One"
    text = (
        f"Hallo {display_name},\n\n"
        f"für Ihr Konto wurde ein neues Passwort angefordert. Über den folgenden Link "
        f"vergeben Sie es:\n\n"
        f"{link}\n\n"
        f"Der Link gilt {hours} Stunden und lässt sich nur einmal verwenden. Ihr "
        f"bisheriges Passwort bleibt gültig, bis Sie ein neues gesetzt haben.\n\n"
        f"Haben Sie das nicht veranlasst, wenden Sie sich an Ihren Administrator.\n"
    )
    html = _html(
        f"<p>Hallo {escape(display_name)},</p>"
        f"<p>für Ihr Konto wurde ein neues Passwort angefordert.</p>"
        f"{_button(link, 'Neues Passwort vergeben')}"
        f"<p style='color:#6f7369'>Der Link gilt {hours} Stunden und lässt sich nur "
        f"einmal verwenden. Ihr bisheriges Passwort bleibt gültig, bis Sie ein neues "
        f"gesetzt haben. Haben Sie das nicht veranlasst, wenden Sie sich an Ihren "
        f"Administrator.</p>"
    )
    return subject, text, html


def _deadline_line(deadline) -> str:
    parts = [deadline.title]
    if deadline.object_name:
        parts.append(deadline.object_name)
    if deadline.correspondent_name:
        parts.append(deadline.correspondent_name)
    return " · ".join(parts)


def _relative(days_until: int) -> str:
    if days_until < -1:
        return f"seit {abs(days_until)} Tagen überfällig"
    if days_until == -1:
        return "seit gestern überfällig"
    if days_until == 0:
        return "heute fällig"
    if days_until == 1:
        return "morgen fällig"
    return f"in {days_until} Tagen fällig"


def deadline_digest(overdue: list, upcoming: list) -> tuple[str, str, str]:
    """Aufriss der Fristen. `overdue` und `upcoming` sind Deadline-Objekte."""
    total = len(overdue) + len(upcoming)
    if overdue:
        subject = f"{len(overdue)} überschrittene Frist{'en' if len(overdue) != 1 else ''}"
        if upcoming:
            subject += f", {len(upcoming)} anstehend"
    else:
        subject = f"{total} anstehende Frist{'en' if total != 1 else ''}"

    def text_group(title: str, items: list) -> str:
        if not items:
            return ""
        lines = "\n".join(
            f"  {d.due_date}  {_relative(d.days_until):<24} {_deadline_line(d)}" for d in items
        )
        return f"{title}\n{lines}\n\n"

    text = (
        "Fristen aus DataSynq One\n\n"
        + text_group("Überschritten", overdue)
        + text_group("Anstehend", upcoming)
        + f"Alle Vorgänge: {settings.app_base_url}\n"
    )

    def html_group(title: str, items: list, color: str) -> str:
        if not items:
            return ""
        rows = "".join(
            f"<tr>"
            f"<td style='padding:0.3rem 0.75rem 0.3rem 0;white-space:nowrap;"
            f"font-family:monospace;font-size:12px;color:{color}'>{escape(d.due_date)}</td>"
            f"<td style='padding:0.3rem 0.75rem 0.3rem 0;white-space:nowrap;"
            f"font-size:12px;color:#6f7369'>{escape(_relative(d.days_until))}</td>"
            f"<td style='padding:0.3rem 0'>"
            f"<a href='{escape(settings.app_base_url)}/?dokument={d.document_id}' "
            f"style='color:#1f6b4f'>{escape(_deadline_line(d))}</a></td>"
            f"</tr>"
            for d in items
        )
        return (
            f"<h2 style='font-size:12px;font-weight:600;letter-spacing:0.09em;"
            f"text-transform:uppercase;margin:1.5rem 0 0.25rem;padding-bottom:0.35rem;"
            f"border-bottom:2px solid #161814'>{escape(title)}</h2>"
            f"<table style='width:100%;border-collapse:collapse'>{rows}</table>"
        )

    html = _html(
        html_group("Überschritten", overdue, "#8f3323")
        + html_group("Anstehend", upcoming, "#24261f")
    )
    return subject, text, html


def agent_message(body: str) -> tuple[str, str]:
    """Der vom Assistenten formulierte und von einem Menschen freigegebene Text.

    Bewusst ohne Briefkopf und ohne Produktzeile: das hier geht an Mieter und
    Dienstleister, nicht an Kolleginnen, und soll wie ein normaler Brief wirken.
    """
    paragraphs = "".join(
        f"<p style='margin:0 0 0.75rem'>{escape(p)}</p>"
        for p in body.split("\n\n")
        if p.strip()
    )
    html = (
        "<div style=\"font-family:'IBM Plex Sans',Helvetica,Arial,sans-serif;"
        f'font-size:14px;line-height:1.5;color:#24261f;max-width:34rem">{paragraphs}</div>'
    )
    return body, html
