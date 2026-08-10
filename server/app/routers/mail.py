from fastapi import APIRouter, Depends, HTTPException, status

from .. import db, mail
from .. import audit as security_audit
from ..auth import CurrentPrincipal, Permission, require
from ..auth.object_access import ObjectAccessDenied, ObjectAuthorizer
from ..config import settings
from ..mail import digest, intake
from ..models import EmailDraft, EmailDraftSendRequest

router = APIRouter(prefix="/mail", tags=["mail"])


@router.get("/settings", dependencies=[Depends(require(Permission.USERS_MANAGE))])
async def mail_settings():
    """Was eingestellt ist — ohne das Passwort.

    Ein Tippfehler im Hostnamen faellt sonst erst auf, wenn eine Einladung nicht
    ankommt, und dann sucht man ihn im Log statt in der Oberflaeche.
    """
    return {
        "enabled": settings.mail_enabled,
        "host": settings.smtp_host,
        "port": settings.smtp_port,
        "security": settings.smtp_security,
        "username": settings.smtp_username,
        "from_email": settings.smtp_from_email,
        "from_name": settings.smtp_from_name,
        "reply_to": settings.smtp_reply_to,
        "app_base_url": settings.app_base_url,
    }


@router.post("/test", dependencies=[Depends(require(Permission.USERS_MANAGE))])
async def send_test_mail(principal: CurrentPrincipal):
    """Testmail an die eigene Adresse — nie an eine fremde.

    Sonst waere der Endpunkt ein Weg, ueber einen fremden Mailserver beliebige
    Adressen anzuschreiben.
    """
    subject = "Testmail aus DataSynq One"
    text = (
        f"Hallo {principal.display_name},\n\n"
        f"diese Nachricht bestätigt, dass der Mailversand eingerichtet ist.\n\n"
        f"Server: {settings.smtp_host}:{settings.smtp_port} ({settings.smtp_security})\n"
        f"Absender: {settings.smtp_from_name} <{settings.smtp_from_email}>\n"
    )
    sent = await mail.send([principal.email], subject, text)
    await security_audit.safe_record(
        "mail.test",
        "success" if sent else "failure",
        reason_code=None if sent else "smtp_not_accepted",
        metadata={"mail_sent": sent},
    )
    return {
        "mail_sent": sent,
        "recipient": principal.email,
        "detail": (
            "Testmail verschickt."
            if sent
            else "Es wurde nichts verschickt. Prüfe SMTP_HOST und SMTP_FROM_EMAIL "
            "sowie das Backend-Log."
        ),
    }


@router.get(
    "/drafts/{draft_id}",
    response_model=EmailDraft,
    dependencies=[Depends(require(Permission.AGENT_WRITE))],
)
async def get_draft(draft_id: str, principal: CurrentPrincipal) -> EmailDraft:
    draft = await db.get_email_draft(draft_id, principal.user_id)
    if draft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entwurf nicht gefunden")
    if draft.get("document_id") is not None:
        try:
            await ObjectAuthorizer(principal).require_document(draft["document_id"])
        except ObjectAccessDenied as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Entwurf nicht gefunden"
            ) from exc
    return EmailDraft(**draft)


@router.post(
    "/drafts/{draft_id}/send",
    response_model=EmailDraft,
    dependencies=[Depends(require(Permission.AGENT_WRITE))],
)
async def send_draft(
    draft_id: str, payload: EmailDraftSendRequest, principal: CurrentPrincipal
) -> EmailDraft:
    """Verschickt den freigegebenen Entwurf.

    Der Empfaenger wird bewusst erst hier vom Menschen eingegeben. Das Modell
    kann dadurch keine Adresse aus einem unvertrauenswuerdigen Dokument uebernehmen.
    """
    draft = await db.get_email_draft(draft_id, principal.user_id)
    if draft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entwurf nicht gefunden")
    if draft.get("document_id") is not None:
        try:
            await ObjectAuthorizer(principal).require_document(draft["document_id"])
        except ObjectAccessDenied as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Entwurf nicht gefunden"
            ) from exc
    if draft["sent_at"] is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Dieser Entwurf wurde bereits verschickt.",
        )

    if not await db.claim_email_draft_for_send(draft_id, principal.user_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Dieser Entwurf wird bereits verschickt.",
        )

    await security_audit.safe_record(
        "mail.draft_send", "started", target_type="mail_draft", target_id=draft_id
    )
    text, html = mail.messages.agent_message(payload.body)
    try:
        sent = await mail.send([payload.recipient], payload.subject, text, html)
    except Exception:
        await db.release_email_draft_claim(draft_id, principal.user_id)
        raise
    if not sent:
        await db.release_email_draft_claim(draft_id, principal.user_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Die Mail konnte nicht verschickt werden. Der Entwurf bleibt erhalten.",
        )

    # Erst nach erfolgreichem Versand vermerken — sonst gilt ein Entwurf als
    # verschickt, obwohl der Mailserver ihn nie angenommen hat.
    updated = await db.mark_email_draft_sent(
        draft_id, principal.user_id, payload.recipient, payload.subject, payload.body
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Dieser Entwurf wurde bereits verschickt.",
        )
    await security_audit.safe_record(
        "mail.draft_send",
        "success",
        target_type="mail_draft",
        target_id=draft_id,
        metadata={"mail_sent": True},
    )

    # Best effort: steht eine Tracking-ID im Betreff, landet der Versand auch auf
    # dem Zeitstrahl des Anliegens. Ein fehlender/ungueltiger Treffer verhindert
    # den Versand selbst nicht mehr — der ist zu diesem Zeitpunkt schon passiert.
    tracking_id = intake.extract_tracking_id(payload.subject)
    if tracking_id:
        case = await db.get_case(tracking_id)
        if case is not None and ObjectAuthorizer(principal).allows_object_code(
            case.get("object_code")
        ):
            await db.add_case_event(
                case["id"], "reply_sent", detail=payload.subject, actor_user_id=principal.user_id
            )

    return EmailDraft(**updated)


@router.post("/deadline-digest", dependencies=[Depends(require(Permission.SYNC_RUN))])
async def send_deadline_digest():
    """Verschickt den Fristenaufriss sofort, unabhängig vom Tagesvermerk.

    Ohne diesen Endpunkt liesse sich der Versand nur pruefen, indem man bis zum
    naechsten Morgen wartet.
    """
    return await digest.send_digest()


@router.get("/pending-senders", dependencies=[Depends(require(Permission.MAIL_MANAGE))])
async def list_pending_senders(status_filter: str | None = None):
    """Alle Absender mit ihrem Freigabestatus, neueste Aktivität zuerst.

    `status_filter` ohne Wert liefert alle (pending/approved/rejected) — die
    Oberfläche filtert clientseitig weiter, damit ein Tabwechsel nicht jedes Mal
    neu laedt.
    """
    return await db.list_senders(status_filter)


@router.post("/pending-senders/{email}/approve", dependencies=[Depends(require(Permission.MAIL_MANAGE))])
async def approve_pending_sender(email: str, principal: CurrentPrincipal):
    """Befristete Freigabe — kein Dauervertrauen, siehe MAIL_WHITELIST_TRUST_DAYS."""
    result = await db.approve_sender(email, principal.user_id, settings.mail_whitelist_trust_days)
    await security_audit.safe_record("mail.sender_approved", "success")
    return result


@router.post("/pending-senders/{email}/reject", dependencies=[Depends(require(Permission.MAIL_MANAGE))])
async def reject_pending_sender(email: str, principal: CurrentPrincipal):
    result = await db.reject_sender(email, principal.user_id)
    await security_audit.safe_record("mail.sender_rejected", "success")
    return result


@router.post("/intake/run", dependencies=[Depends(require(Permission.MAIL_MANAGE))])
async def run_mail_intake():
    """Stößt einen Durchlauf der Anliegen-Aufnahme sofort an, unabhängig vom
    Abfrageintervall — zum Testen und für die Demo, ohne auf den nächsten Tick
    zu warten."""
    if settings.environment == "production":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Automatische Mailaufnahme ist bis zum signierten Ingress-Manifest deaktiviert.",
        )
    return await intake.poll_once()
