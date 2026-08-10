"""Der SMTP-Versand.

aiosmtplib statt smtplib aus der Standardbibliothek: der Backend ist durchgehend
asynchron (asyncpg, httpx.AsyncClient), und ein blockierender Socket haelt waehrend
der ganzen SMTP-Konversation den Event Loop an — samt aller laufenden SSE-Streams
des Assistenten.

Grundregel dieses Moduls: **es wirft nicht**. Ein nicht erreichbarer Mailserver
darf keinen Request scheitern lassen, der fachlich bereits durch ist. Jede Funktion
meldet ueber ihren Rueckgabewert, ob zugestellt wurde; der Aufrufer reicht das als
`mail_sent` bis in die HTTP-Antwort weiter, damit niemand im Glauben bleibt, die
Mail sei unterwegs.
"""

import logging
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import parseaddr

import aiosmtplib

from ..config import reveal_secret, settings

logger = logging.getLogger(__name__)

STARTTLS = "starttls"
IMPLICIT_TLS = "tls"
NO_TLS = "none"


def _from_header() -> Address:
    name, addr = parseaddr(settings.smtp_from_email)
    display = settings.smtp_from_name or name
    local, _, domain = addr.partition("@")
    return Address(display_name=display, username=local, domain=domain)


def build_message(
    to: list[str],
    subject: str,
    text: str,
    html: str | None = None,
    reply_to: str | None = None,
) -> EmailMessage:
    """Text und optional HTML als multipart/alternative.

    Immer mit Textteil: eine reine HTML-Mail wird von Spamfiltern schlechter
    bewertet, und die Fristenliste liest sich als Text ohnehin gut.
    """
    message = EmailMessage()
    message["From"] = _from_header()
    message["To"] = ", ".join(to)
    message["Subject"] = subject
    reply = reply_to or settings.smtp_reply_to
    if reply:
        message["Reply-To"] = reply

    message.set_content(text)
    if html:
        message.add_alternative(html, subtype="html")
    return message


async def send(
    to: list[str],
    subject: str,
    text: str,
    html: str | None = None,
    reply_to: str | None = None,
) -> bool:
    """True, wenn der Mailserver die Nachricht angenommen hat."""
    recipients = [address for address in to if address]
    if not recipients:
        return False

    if not settings.mail_enabled:
        logger.info(
            "Mailversand ist nicht eingerichtet (SMTP_HOST/SMTP_FROM_EMAIL fehlen) — "
            "Nachricht an %d Empfänger wurde nicht verschickt.",
            len(recipients),
        )
        return False

    try:
        message = build_message(recipients, subject, text, html, reply_to)
        await aiosmtplib.send(
            message,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username or None,
            password=reveal_secret(settings.smtp_password) or None,
            # start_tls und use_tls schliessen sich aus: das eine handelt die
            # Verschluesselung auf einer offenen Verbindung aus (587), das andere
            # verschluesselt von der ersten Anfrage an (465).
            start_tls=settings.smtp_security == STARTTLS,
            use_tls=settings.smtp_security == IMPLICIT_TLS,
            timeout=settings.smtp_timeout_seconds,
        )
    except Exception as e:
        logger.warning(
            "Mailversand an %d Empfänger fehlgeschlagen (%s).",
            len(recipients),
            type(e).__name__,
        )
        return False

    logger.info("Mail an %d Empfänger verschickt.", len(recipients))
    return True
