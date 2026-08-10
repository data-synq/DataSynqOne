"""Einladungs- und Reset-Links.

Ein Token ist ein Einmal-Schlüssel mit Ablaufdatum. Er entsteht beim Anlegen eines
Kontos und beim Zurücksetzen eines Passworts; beides mündet in dieselbe öffentliche
Seite, die nur den Zweck unterscheidet.
"""

import logging
import secrets
from urllib.parse import quote

from .. import db, mail
from ..config import settings
from .sessions import hash_token

logger = logging.getLogger(__name__)

INVITATION = "invitation"
PASSWORD_RESET = "password_reset"

_TOKEN_BYTES = 32


def link_for(token: str) -> str:
    base = settings.app_base_url.rstrip("/")
    return f"{base}/einladung/{quote(token)}"


async def issue(user_id: str, purpose: str) -> str:
    """Neues Token, alte desselben Zwecks werden entwertet.

    Wer zweimal einlädt, soll nicht zwei gültige Links in der Welt haben — der
    zuletzt verschickte ist der gültige.
    """
    token = secrets.token_urlsafe(_TOKEN_BYTES)
    await db.replace_user_token(
        token_hash=hash_token(token),
        user_id=user_id,
        purpose=purpose,
        ttl_hours=settings.invitation_ttl_hours,
    )
    return token


async def issue_and_send(
    user_id: str, display_name: str, email: str, purpose: str
) -> tuple[bool, str]:
    """Erzeugt den Link und verschickt ihn. Liefert (verschickt, Link).

    Der Link wandert auch dann zurück, wenn der Versand geklappt hat — der
    Aufrufer entscheidet, ob er ihn preisgibt. Ohne Mailserver ist er der einzige
    Weg, jemanden an Bord zu holen; mit Mailserver hat er in einer Antwort nichts
    zu suchen.
    """
    token = await issue(user_id, purpose)
    link = link_for(token)

    if purpose == INVITATION:
        subject, text, html = mail.messages.invitation(display_name, link)
    else:
        subject, text, html = mail.messages.password_reset(display_name, link)

    sent = await mail.send([email], subject, text, html)
    if not sent:
        logger.info(
            "Kein Mailversand für %s — der Link muss von Hand weitergegeben werden.",
            purpose,
        )
    return sent, link


async def resolve(token: str) -> dict | None:
    return await db.get_user_token(hash_token(token))


async def consume(token: str) -> bool:
    return await db.consume_user_token(hash_token(token))
