"""Die tägliche Fristen-Erinnerung.

Der Inhalt kommt vollständig aus `dashboard_service.get_overview()` — dessen
`deadlines` sind bereits nach Datum sortiert, tragen `days_until` und lassen
erledigte Vorgänge weg. Hier wird nur noch gefiltert, gruppiert und verschickt.
"""

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
import uuid

from .. import dashboard_service, db
from ..auth import ObjectAccessMode, Principal, Role, permissions_for
from ..config import settings
from . import messages
from .client import send

logger = logging.getLogger(__name__)

# Stündlich statt einmal am Tag: ein Neustart um 9 Uhr soll den 7-Uhr-Versand
# nachholen, wenn er ausgefallen ist. Gegen doppelten Versand steht der
# Tagesanspruch in mail_digest_runs, nicht das Aufwachintervall.
_TICK_SECONDS = 3600


def _principal(user: dict) -> Principal:
    role = Role(user["role"])
    return Principal(
        user_id=user["id"],
        email=user["email"],
        display_name=user["display_name"],
        role=role,
        permissions=permissions_for(role),
        object_access_mode=ObjectAccessMode(user["object_access_mode"]),
        object_scope=frozenset(user.get("object_codes", [])),
    )


def _system_principal() -> Principal:
    return Principal(
        user_id="system",
        email="",
        display_name="System",
        role=Role.ADMIN,
        permissions=permissions_for(Role.ADMIN),
        object_access_mode=ObjectAccessMode.ALL,
    )


async def collect(principal: Principal | None = None) -> tuple[list, list]:
    """(überschritten, anstehend) im eingestellten Vorlauf."""
    overview = await dashboard_service.get_overview(principal or _system_principal())
    horizon = settings.deadline_digest_days_ahead
    overdue = [d for d in overview.deadlines if d.days_until < 0]
    upcoming = [d for d in overview.deadlines if 0 <= d.days_until <= horizon]
    return overdue, upcoming


async def recipients() -> list[str]:
    accounts = await db.list_digest_recipients()
    if settings.deadline_digest_recipients:
        configured = set(settings.deadline_digest_recipients)
        return [account["email"] for account in accounts if account["email"] in configured]
    return [account["email"] for account in accounts]


async def send_digest() -> dict:
    """Baut den Aufriss und verschickt ihn. Ohne Tagesvermerk — der Aufrufer entscheidet."""
    accounts = await db.list_digest_recipients()
    if settings.deadline_digest_recipients:
        configured = set(settings.deadline_digest_recipients)
        accounts = [account for account in accounts if account["email"] in configured]
    account_batches = [
        ([account["email"]], await collect(_principal(account))) for account in accounts
    ]

    sent_any = False
    deadline_count = 0
    delivered_to = []
    for addresses, (overdue, upcoming) in account_batches:
        if not overdue and not upcoming:
            continue
        subject, text, html = messages.deadline_digest(overdue, upcoming)
        sent = await send(addresses, subject, text, html)
        sent_any = sent_any or sent
        if sent:
            delivered_to.extend(addresses)
        deadline_count += len(overdue) + len(upcoming)
    if not deadline_count:
        logger.info("Keine offenen Fristen — keine Erinnerung verschickt.")
        return {"mail_sent": False, "reason": "keine offenen Fristen", "deadlines": 0}
    return {
        "mail_sent": sent_any,
        "recipients": delivered_to,
        "deadlines": deadline_count,
    }


async def _send_account_digest(account: dict) -> bool | None:
    overdue, upcoming = await collect(_principal(account))
    if not overdue and not upcoming:
        return None
    subject, text, html = messages.deadline_digest(overdue, upcoming)
    return await send([account["email"]], subject, text, html)


async def _run_once_for_today() -> None:
    local_now = datetime.now(ZoneInfo(settings.app_timezone))
    today = local_now.date()
    if local_now.hour < settings.deadline_digest_hour:
        return

    accounts = await db.list_digest_recipients()
    if settings.deadline_digest_recipients:
        configured = set(settings.deadline_digest_recipients)
        accounts = [account for account in accounts if account["email"] in configured]
    for account in accounts:
        owner_id = str(uuid.uuid4())
        if not await db.claim_digest_recipient(today, account["id"], owner_id):
            continue
        try:
            sent = await _send_account_digest(account)
        except Exception:
            logger.exception("Fristen-Erinnerung fehlgeschlagen.")
            await db.release_digest_recipient(today, account["id"], owner_id)
            continue
        if sent:
            await db.complete_digest_recipient(today, account["id"], owner_id)
        else:
            # False (SMTP failure) and None (currently no deadlines) remain retryable.
            await db.release_digest_recipient(today, account["id"], owner_id)


async def scheduler() -> None:
    """Läuft als Hintergrundaufgabe im lifespan, bis sie abgebrochen wird."""
    if not settings.deadline_digest_enabled:
        logger.info("Fristen-Erinnerung ist abgeschaltet (DEADLINE_DIGEST_ENABLED).")
        return

    logger.info(
        "Fristen-Erinnerung aktiv: täglich ab %02d:00 Uhr, Vorlauf %d Tage.",
        settings.deadline_digest_hour,
        settings.deadline_digest_days_ahead,
    )
    while True:
        try:
            await _run_once_for_today()
        except asyncio.CancelledError:
            raise
        except Exception:
            # Der Taggeber darf nie sterben: ein Fehler in einem Durchlauf würde
            # sonst die Erinnerung bis zum nächsten Neustart stilllegen.
            logger.exception("Durchlauf der Fristen-Erinnerung fehlgeschlagen.")
        await asyncio.sleep(_TICK_SECONDS)
