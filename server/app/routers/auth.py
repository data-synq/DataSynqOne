from datetime import datetime, timezone
import hashlib
import hmac
import ipaddress

from fastapi import APIRouter, HTTPException, Request, Response, status

from .. import db
from .. import audit as security_audit
from ..auth import (
    AuthStage,
    AuthenticatedPrincipal,
    CurrentPrincipal,
    ROLE_LABELS,
    Role,
    invitations,
    mfa,
    permissions_for,
)
from ..auth import sessions as auth_sessions
from ..auth.passwords import (
    hash_password,
    validate_password,
    verify_password,
    verify_password_and_rehash,
)
from ..config import settings
from ..models import (
    AuthSessionOut,
    InvitationInfo,
    InvitationRedeemRequest,
    LoginRequest,
    MeOut,
    MfaCodeRequest,
    MfaConfirmOut,
    MfaSetupOut,
    PasswordChangeRequest,
)
from ..network import request_client_ip

__all__ = ["router", "me_payload"]

router = APIRouter(prefix="/auth", tags=["auth"])

# Der Caddyfile-Kommentar hält fest, dass vor dem bisherigen Basic-Auth-Gate kein
# Rate Limiting steht. Ein eigenes Login braucht deshalb eine eigene Bremse.
MAX_LOGIN_ATTEMPTS = 10
LOCK_MINUTES = 15
MAX_SOURCE_ATTEMPTS = 100
MAX_ACCOUNT_ATTEMPTS = 100

# Dieselbe Meldung für falsches Passwort, unbekannte E-Mail und deaktiviertes
# Konto: sonst lässt sich daran ablesen, welche Konten es gibt.
_LOGIN_FAILED = "E-Mail-Adresse oder Passwort ist falsch."


def _login_source(request: Request) -> str:
    return request_client_ip(request)


def _rate_key(kind: str, *parts: str) -> str:
    value = "\0".join((kind, *parts)).encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _rate_source(source: str) -> str:
    try:
        address = ipaddress.ip_address(source)
    except ValueError:
        return source
    if address.version == 6:
        return str(ipaddress.ip_network(f"{address}/64", strict=False))
    return str(address)


def auth_stage_for(user: dict, *, mfa_verified: bool = False) -> AuthStage:
    role = Role(user["role"])
    if user["must_change_password"]:
        return AuthStage.PASSWORD_CHANGE
    if role is Role.ADMIN and not user.get("mfa_enabled_at"):
        return AuthStage.MFA_SETUP
    if role is Role.ADMIN and not mfa_verified:
        return AuthStage.MFA_CHALLENGE
    return AuthStage.READY


def me_payload(user: dict, auth_stage: AuthStage | None = None) -> MeOut:
    role = Role(user["role"])
    auth_stage = auth_stage or auth_stage_for(user)
    return MeOut(
        id=user["id"],
        email=user["email"],
        display_name=user["display_name"],
        role=role,
        role_label=ROLE_LABELS[role],
        is_active=user["is_active"],
        must_change_password=user["must_change_password"],
        mfa_enabled=bool(user.get("mfa_enabled_at")),
        object_access_mode=user.get("object_access_mode", "restricted"),
        object_codes=sorted(user.get("object_codes", [])),
        last_login_at=user.get("last_login_at"),
        created_at=user["created_at"],
        permissions=sorted(permissions_for(role)) if auth_stage is AuthStage.READY else [],
        auth_stage=auth_stage,
    )


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_absolute_ttl_hours * 3600,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post("/login", response_model=MeOut)
async def login(payload: LoginRequest, request: Request, response: Response) -> MeOut:
    await db.purge_expired_auth_sessions()
    await db.purge_expired_auth_rate_limits()

    source = _rate_source(_login_source(request))
    source_allowed = await db.consume_auth_rate_limit(
        _rate_key("source", source), MAX_SOURCE_ATTEMPTS, LOCK_MINUTES
    )
    if not source_allowed:
        await security_audit.safe_record(
            "auth.login", "denied", reason_code="source_rate_limited"
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Zu viele Anmeldeversuche. Bitte später erneut versuchen.",
            headers={"Retry-After": str(LOCK_MINUTES * 60)},
        )
    target_allowed = await db.consume_auth_rate_limit(
        _rate_key("target", source, payload.email), MAX_LOGIN_ATTEMPTS, LOCK_MINUTES
    )
    account_key = _rate_key("account", payload.email)
    account_allowed = await db.consume_auth_rate_limit(
        account_key, MAX_ACCOUNT_ATTEMPTS, LOCK_MINUTES
    )

    user = await db.get_user_by_email(payload.email)

    # Auch ohne Treffer wird verifiziert — verify_password rechnet dann gegen einen
    # Dummy-Hash, damit die Antwortzeit nichts über die Existenz des Kontos verrät.
    stored_hash = user.get("password_hash") if user else None
    password_ok, replacement_hash = verify_password_and_rehash(stored_hash, payload.password)
    credentials_valid = bool(user and password_ok and user["is_active"])
    if (not target_allowed or not account_allowed) and not credentials_valid:
        await security_audit.safe_record(
            "auth.login",
            "denied",
            reason_code="account_rate_limited",
            target_type="user",
            target_id=user["id"] if user else None,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Zu viele Anmeldeversuche. Bitte später erneut versuchen.",
            headers={"Retry-After": str(LOCK_MINUTES * 60)},
        )

    now = datetime.now(timezone.utc)
    mfa_locked = bool(user and user.get("mfa_locked_until") and user["mfa_locked_until"] > now)
    if user is None or not password_ok or not user["is_active"] or mfa_locked:
        if user is not None and not password_ok:
            await db.record_login_failure(user["id"], MAX_LOGIN_ATTEMPTS, LOCK_MINUTES)
        await security_audit.safe_record(
            "auth.login",
            "denied",
            reason_code="invalid_credentials",
            target_type="user",
            target_id=user["id"] if user else None,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_LOGIN_FAILED)

    issue_hash = stored_hash
    if replacement_hash is not None:
        if await db.update_password_hash_if_current(user["id"], stored_hash, replacement_hash):
            issue_hash = replacement_hash

    token = await auth_sessions.issue(
        user["id"],
        request.headers.get("user-agent"),
        expected_password_hash=issue_hash,
    )
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_LOGIN_FAILED)
    if Role(user["role"]) is Role.ADMIN:
        await db.clear_login_failures(user["id"])
    else:
        await db.record_login_success(user["id"])
    await db.clear_auth_rate_limit(account_key)
    await security_audit.safe_record(
        "auth.login",
        "success",
        target_type="user",
        target_id=user["id"],
        metadata={"auth_stage": auth_stage_for(user).value},
        actor_type="user",
        actor_id=user["id"],
        actor_role=user["role"],
    )
    set_session_cookie(response, token)

    fresh = await db.get_user_by_id(user["id"])
    return me_payload(fresh or user)


@router.post("/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        principal = await auth_sessions.resolve(token)
        await auth_sessions.revoke(token)
        if principal is not None:
            await security_audit.safe_record(
                "auth.logout",
                "success",
                target_type="user",
                target_id=principal.user_id,
                actor_type="user",
                actor_id=principal.user_id,
                actor_role=principal.role.value,
            )
    response.delete_cookie(
        key=settings.session_cookie_name,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    return {"status": "ok"}


_INVALID_TOKEN = "Dieser Link ist ungültig oder abgelaufen. Bitte fordere einen neuen an."


@router.get("/invitation/{token}", response_model=InvitationInfo)
async def invitation_info(token: str) -> InvitationInfo:
    """Öffentlich. Liefert nur Anzeigename und Zweck — genug für die Beschriftung.

    Unbekannt, abgelaufen und bereits eingelöst ergeben dieselbe Antwort; jede
    Unterscheidung wäre eine Auskunft an jemanden, der nur einen Link geraten hat.
    """
    entry = await invitations.resolve(token)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_INVALID_TOKEN)
    return InvitationInfo(display_name=entry["display_name"], purpose=entry["purpose"])


@router.post("/invitation/{token}", response_model=MeOut)
async def redeem_invitation(
    token: str, payload: InvitationRedeemRequest, request: Request, response: Response
) -> MeOut:
    """Passwort setzen, Token entwerten und direkt anmelden."""
    entry = await invitations.resolve(token)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_INVALID_TOKEN)

    try:
        validate_password(payload.password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    # Entwerten vor dem Setzen: zwei gleichzeitige Anfragen mit demselben Link
    # dürfen nicht beide ein Passwort schreiben.
    if not await invitations.consume(token):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_INVALID_TOKEN)

    user_id = entry["user_id"]
    await db.set_password(user_id, hash_password(payload.password), must_change=False)
    # Wer bisher angemeldet war, fliegt raus — ein Reset ist auch der Weg nach
    # einem verlorenen oder mitgelesenen Passwort.
    await auth_sessions.revoke_all(user_id)

    user = await db.get_user_by_id(user_id)
    if Role(user["role"]) is Role.ADMIN:
        await db.clear_login_failures(user_id)
    else:
        await db.record_login_success(user_id)
    session_token = await auth_sessions.issue(user_id, request.headers.get("user-agent"))
    set_session_cookie(response, session_token)

    await security_audit.safe_record(
        "auth.invitation_redeemed",
        "success",
        target_type="user",
        target_id=user_id,
        metadata={"purpose": entry["purpose"]},
        actor_type="user",
        actor_id=user_id,
        actor_role=user["role"],
    )

    return me_payload(user)


@router.get("/me", response_model=MeOut)
async def me(principal: AuthenticatedPrincipal) -> MeOut:
    user = await db.get_user_by_id(principal.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nicht angemeldet")
    return me_payload(user, principal.auth_stage)


@router.post("/password", response_model=MeOut)
async def change_password(
    payload: PasswordChangeRequest,
    principal: AuthenticatedPrincipal,
    request: Request,
    response: Response,
) -> MeOut:
    if payload.current_password == payload.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Das neue Passwort muss sich vom aktuellen Passwort unterscheiden.",
        )
    current_hash = await db.get_password_hash(principal.user_id)
    if not verify_password(current_hash, payload.current_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Das aktuelle Passwort ist falsch."
        )
    try:
        validate_password(payload.new_password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    await db.set_password(principal.user_id, hash_password(payload.new_password), must_change=False)

    await auth_sessions.revoke_all(principal.user_id)
    session_token = await auth_sessions.issue(
        principal.user_id, request.headers.get("user-agent")
    )
    set_session_cookie(response, session_token)

    user = await db.get_user_by_id(principal.user_id)
    await security_audit.safe_record(
        "auth.password_changed",
        "success",
        target_type="user",
        target_id=principal.user_id,
    )
    return me_payload(user)


def _require_mfa_stage(principal: AuthenticatedPrincipal, stage: AuthStage) -> None:
    if principal.role is not Role.ADMIN or principal.auth_stage is not stage:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Dieser MFA-Schritt ist für die aktuelle Sitzung nicht verfügbar.",
        )


async def _reject_mfa_code(principal: AuthenticatedPrincipal, response: Response) -> None:
    attempts = await db.record_mfa_failure(
        principal.user_id,
        principal.session_id,
        MAX_LOGIN_ATTEMPTS,
        LOCK_MINUTES,
    )
    if attempts >= MAX_LOGIN_ATTEMPTS:
        response.delete_cookie(
            key=settings.session_cookie_name,
            httponly=True,
            secure=settings.session_cookie_secure,
            samesite="lax",
            path="/",
        )
    await security_audit.safe_record(
        "auth.mfa",
        "denied",
        reason_code="invalid_code",
        target_type="user",
        target_id=principal.user_id,
    )
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Der MFA-Code ist ungültig.")


@router.post("/mfa/setup", response_model=MfaSetupOut)
async def setup_mfa(principal: AuthenticatedPrincipal) -> MfaSetupOut:
    _require_mfa_stage(principal, AuthStage.MFA_SETUP)
    entry = await db.get_mfa(principal.user_id)
    if entry and entry["confirmed_at"]:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="MFA ist bereits aktiviert.")

    try:
        secret = mfa.decrypt_secret(entry["secret_ciphertext"]) if entry else mfa.generate_totp_secret()
        if entry is None and not await db.save_pending_mfa(
            principal.user_id, mfa.encrypt_secret(secret)
        ):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="MFA ist bereits aktiviert.")
    except mfa.MfaKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MFA ist derzeit nicht verfügbar.",
        ) from exc
    return MfaSetupOut(
        secret=secret,
        provisioning_uri=mfa.provisioning_uri(secret, principal.email),
    )


@router.post("/mfa/confirm", response_model=MfaConfirmOut)
async def confirm_mfa(
    payload: MfaCodeRequest,
    principal: AuthenticatedPrincipal,
    request: Request,
    response: Response,
) -> MfaConfirmOut:
    _require_mfa_stage(principal, AuthStage.MFA_SETUP)
    entry = await db.get_mfa(principal.user_id)
    if entry is None or entry["confirmed_at"]:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="MFA-Einrichtung fehlt.")
    try:
        secret = mfa.decrypt_secret(entry["secret_ciphertext"])
    except mfa.MfaKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MFA ist derzeit nicht verfügbar.",
        ) from exc
    step = mfa.matching_totp_step(secret, payload.code)
    if step is None:
        await _reject_mfa_code(principal, response)

    generated = mfa.generate_recovery_codes()
    token = auth_sessions.generate_token()
    if not await db.confirm_mfa_and_create_session(
        principal.user_id,
        step,
        [(code_id, secret_hash) for code_id, _code, secret_hash in generated],
        auth_sessions.hash_token(token),
        settings.session_ttl_hours,
        settings.session_absolute_ttl_hours,
        request.headers.get("user-agent"),
    ):
        await _reject_mfa_code(principal, response)

    set_session_cookie(response, token)
    user = await db.get_user_by_id(principal.user_id)
    await security_audit.safe_record(
        "auth.mfa_enabled",
        "success",
        target_type="user",
        target_id=principal.user_id,
        metadata={"factor": "totp"},
    )
    return MfaConfirmOut(
        user=me_payload(user, AuthStage.READY),
        recovery_codes=[code for _code_id, code, _secret_hash in generated],
    )


@router.post("/mfa/verify", response_model=MeOut)
async def verify_mfa(
    payload: MfaCodeRequest,
    principal: AuthenticatedPrincipal,
    request: Request,
    response: Response,
) -> MeOut:
    _require_mfa_stage(principal, AuthStage.MFA_CHALLENGE)
    entry = await db.get_mfa(principal.user_id)
    totp_step = None
    recovery_code_id = None
    if entry and entry["confirmed_at"]:
        try:
            secret = mfa.decrypt_secret(entry["secret_ciphertext"])
        except mfa.MfaKeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="MFA ist derzeit nicht verfügbar.",
            ) from exc
        totp_step = mfa.matching_totp_step(secret, payload.code)

    if totp_step is None:
        recovery = mfa.split_recovery_code(payload.code)
        if recovery:
            code_id, candidate_hash = recovery
            stored_hash = await db.get_recovery_code_hash(principal.user_id, code_id)
            if stored_hash and hmac.compare_digest(stored_hash, candidate_hash):
                recovery_code_id = code_id

    if totp_step is None and recovery_code_id is None:
        await _reject_mfa_code(principal, response)

    token = auth_sessions.generate_token()
    completed = await db.complete_mfa_login(
        principal.user_id,
        auth_sessions.hash_token(token),
        settings.session_ttl_hours,
        settings.session_absolute_ttl_hours,
        request.headers.get("user-agent"),
        totp_step=totp_step,
        recovery_code_id=recovery_code_id,
    )
    if not completed:
        await _reject_mfa_code(principal, response)
    set_session_cookie(response, token)
    await security_audit.safe_record(
        "auth.mfa_verified",
        "success",
        target_type="user",
        target_id=principal.user_id,
        metadata={"factor": "recovery" if recovery_code_id else "totp"},
    )
    return me_payload(await db.get_user_by_id(principal.user_id), AuthStage.READY)


@router.get("/sessions", response_model=list[AuthSessionOut])
async def list_auth_sessions(
    principal: CurrentPrincipal, request: Request
) -> list[AuthSessionOut]:
    token = request.cookies[settings.session_cookie_name]
    return await db.list_auth_sessions(principal.user_id, auth_sessions.hash_token(token))


@router.delete("/sessions/{session_id}")
async def delete_auth_session(
    session_id: str,
    principal: CurrentPrincipal,
    request: Request,
    response: Response,
):
    try:
        removed_hash = await db.delete_auth_session_for_user(session_id, principal.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sitzung nicht gefunden") from exc
    if removed_hash is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sitzung nicht gefunden")

    current = request.cookies.get(settings.session_cookie_name)
    if current and removed_hash == auth_sessions.hash_token(current):
        response.delete_cookie(
            key=settings.session_cookie_name,
            httponly=True,
            secure=settings.session_cookie_secure,
            samesite="lax",
            path="/",
        )
    return {"status": "ok"}


@router.delete("/sessions")
async def delete_other_auth_sessions(
    principal: CurrentPrincipal, request: Request
):
    token = request.cookies[settings.session_cookie_name]
    await auth_sessions.revoke_all(principal.user_id, keep_token=token)
    return {"status": "ok"}
