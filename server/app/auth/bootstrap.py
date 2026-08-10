"""Der erste Admin.

Ohne ihn käme niemand in die frisch aufgesetzte Anwendung hinein, weil jedes
Konto von einem Admin angelegt werden muss. Erzeugt wird er nur, solange die
Benutzertabelle noch leer ist — und nur, wenn beide ENV-Werte gesetzt sind. Ein
im Code hinterlegtes Standardpasswort gibt es bewusst nicht.
"""

import logging

from .. import db
from ..config import is_valid_email, reveal_secret, settings
from .passwords import hash_password, validate_password
from .permissions import Role

logger = logging.getLogger(__name__)


async def ensure_bootstrap_admin() -> None:
    if await db.count_users() > 0:
        return

    admin_password = reveal_secret(settings.admin_password)
    if not settings.admin_email or not admin_password:
        if settings.environment == "production":
            raise RuntimeError(
                "Keine Benutzerkonten vorhanden: ADMIN_EMAIL und ADMIN_PASSWORD sind für den "
                "einmaligen Produktions-Bootstrap erforderlich."
            )
        logger.warning(
            "Es existiert kein Benutzerkonto und ADMIN_EMAIL/ADMIN_PASSWORD sind nicht "
            "gesetzt. Ohne diese Werte kann sich niemand anmelden — beide in "
            "env/backend.env eintragen und das Backend neu starten."
        )
        return

    if not is_valid_email(settings.admin_email):
        raise RuntimeError("ADMIN_EMAIL ist für den Bootstrap keine gültige E-Mail-Adresse.")
    try:
        validate_password(admin_password)
    except ValueError as exc:
        raise RuntimeError("ADMIN_PASSWORD erfüllt die Passwortanforderungen nicht.") from exc

    user = await db.create_user(
        email=settings.admin_email,
        display_name="Administrator",
        password_hash=hash_password(admin_password),
        role=Role.ADMIN,
        must_change_password=True,
    )
    logger.warning(
        "Administrator aus ADMIN_EMAIL/ADMIN_PASSWORD angelegt. Das Passwort ist "
        "beim ersten Login zu ändern.",
    )

    # Chats aus der Zeit vor der Benutzerverwaltung haben keinen Besitzer und wären
    # sonst für niemanden mehr sichtbar.
    adopted = await db.assign_orphaned_sessions(user["id"])
    if adopted:
        logger.info("%d herrenlose Chat-Sitzungen dem Administrator zugeordnet.", adopted)
