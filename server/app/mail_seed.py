"""Legt beim Start ein Mail-Konto und eine Abholregel in Paperless an.

Analog zu tag_seed.py: best effort, läuft beim Start und darf die Anwendung
niemals am Hochfahren hindern. Ohne MAIL_IMAP_HOST passiert nichts — Empfang ist
eine Zusatzfunktion, kein Startvoraussetzung.

Die Feldwerte (imap_security, account_type, consumption_scope, ...) sind keine
Annahmen, sondern per `OPTIONS /api/mail_accounts/` bzw. `/api/mail_rules/` aus
einer laufenden Paperless-Instanz gelesen.
"""

import logging

import httpx

from .config import reveal_secret, settings
from .paperless_client import paperless_client

logger = logging.getLogger(__name__)

_ACCOUNT_NAME = "DataSynq One"
_RULE_NAME = "DataSynq One — Posteingang"

_IMAP_SECURITY = {"none": 1, "ssl": 2, "starttls": 3}
_ACCOUNT_TYPE_IMAP = 1

# Ganze Nachricht als .eml UND ihre Anhänge als eigene Dokumente. Das .eml wird
# von Paperless immer als PDF dargestellt (Browser können .eml nicht nativ
# rendern) — dafür müssen Gotenberg und Tika laufen, siehe compose.yml.
_CONSUMPTION_SCOPE_EML_AND_ATTACHMENTS = 3
_PDF_LAYOUT_HTML_THEN_TEXT = 2
_ASSIGN_TITLE_FROM_SUBJECT = 1
# Name des Absenders, ersatzweise die Adresse — lesbarer als eine reine E-Mail-Adresse.
_ASSIGN_CORRESPONDENT_FROM_NAME = 3
# Als gelesen markieren statt löschen/verschieben: eine fehlerhafte Regel kostet
# damit keine Mail, das Postfach bleibt die Quelle der Wahrheit.
_ACTION_MARK_READ = 3


async def _resolve_tag_ids() -> list[int]:
    tags = (await paperless_client.list_tags()).get("results", [])
    by_name = {t["name"]: t["id"] for t in tags}
    ids = []
    for name in settings.mail_rule_tags:
        tag_id = by_name.get(name)
        if tag_id is None:
            logger.warning("Mail-Regel: Tag %r existiert nicht in Paperless, wird ausgelassen.", name)
            continue
        ids.append(tag_id)
    return ids


async def seed_mail_receiving() -> None:
    """Legt Konto und Regel an, falls sie noch fehlen. Ohne MAIL_IMAP_HOST: no-op."""
    if not settings.mail_receiving_enabled:
        logger.info(
            "Mailempfang ist nicht eingerichtet (MAIL_IMAP_HOST/MAIL_IMAP_USERNAME fehlen) — "
            "es wird kein Paperless-Mail-Konto angelegt."
        )
        return

    try:
        accounts = (await paperless_client.list_mail_accounts()).get("results", [])
    except httpx.HTTPError as exc:
        logger.warning("Mailempfang nicht eingerichtet, konnte Mail-Konten nicht lesen: %s", exc)
        return

    account = next((a for a in accounts if a["name"] == _ACCOUNT_NAME), None)
    if account is None:
        try:
            account = await paperless_client.create_mail_account(
                {
                    "name": _ACCOUNT_NAME,
                    "imap_server": settings.mail_imap_host,
                    "imap_port": settings.mail_imap_port,
                    "imap_security": _IMAP_SECURITY.get(settings.mail_imap_security, 2),
                    "username": settings.mail_imap_username,
                    "password": reveal_secret(settings.mail_imap_password),
                    "account_type": _ACCOUNT_TYPE_IMAP,
                }
            )
            logger.info("Paperless-Mail-Konto %r angelegt.", _ACCOUNT_NAME)
        except httpx.HTTPError as exc:
            logger.warning("Konnte Paperless-Mail-Konto nicht anlegen: %s", exc)
            return

    try:
        rules = (await paperless_client.list_mail_rules()).get("results", [])
    except httpx.HTTPError as exc:
        logger.warning("Mail-Regel nicht angelegt, konnte bestehende Regeln nicht lesen: %s", exc)
        return

    if any(r["name"] == _RULE_NAME for r in rules):
        return

    tag_ids = await _resolve_tag_ids()
    try:
        await paperless_client.create_mail_rule(
            {
                "name": _RULE_NAME,
                "account": account["id"],
                "enabled": True,
                "folder": settings.mail_imap_folder,
                "action": _ACTION_MARK_READ,
                "assign_title_from": _ASSIGN_TITLE_FROM_SUBJECT,
                "assign_correspondent_from": _ASSIGN_CORRESPONDENT_FROM_NAME,
                "assign_tags": tag_ids,
                "consumption_scope": _CONSUMPTION_SCOPE_EML_AND_ATTACHMENTS,
                "pdf_layout": _PDF_LAYOUT_HTML_THEN_TEXT,
            }
        )
        logger.info("Paperless-Mail-Regel %r angelegt.", _RULE_NAME)
    except httpx.HTTPError as exc:
        logger.warning("Konnte Paperless-Mail-Regel nicht anlegen: %s", exc)
