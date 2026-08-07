from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Response, status

from .. import db
from ..auth import CurrentPrincipal, ROLE_LABELS, Role, permissions_for
from ..auth import sessions as auth_sessions
from ..auth.passwords import hash_password, validate_password, verify_password
from ..config import settings
from ..models import LoginRequest, MeOut, PasswordChangeRequest

__all__ = ["router", "me_payload"]

router = APIRouter(prefix="/auth", tags=["auth"])

# Der Caddyfile-Kommentar hält fest, dass vor dem bisherigen Basic-Auth-Gate kein
# Rate Limiting steht. Ein eigenes Login braucht deshalb eine eigene Bremse.
MAX_LOGIN_ATTEMPTS = 10
LOCK_MINUTES = 15

# Dieselbe Meldung für falsches Passwort, unbekannte E-Mail und deaktiviertes
# Konto: sonst lässt sich daran ablesen, welche Konten es gibt.
_LOGIN_FAILED = "E-Mail-Adresse oder Passwort ist falsch."


def me_payload(user: dict) -> MeOut:
    role = Role(user["role"])
    return MeOut(
        id=user["id"],
        email=user["email"],
        display_name=user["display_name"],
        role=role,
        role_label=ROLE_LABELS[role],
        is_active=user["is_active"],
        must_change_password=user["must_change_password"],
        last_login_at=user.get("last_login_at"),
        created_at=user["created_at"],
        permissions=sorted(permissions_for(role)),
    )


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post("/login", response_model=MeOut)
async def login(payload: LoginRequest, request: Request, response: Response) -> MeOut:
    await db.purge_expired_auth_sessions()

    user = await db.get_user_by_email(payload.email)

    locked_until = user.get("locked_until") if user else None
    if locked_until and locked_until > datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_LOGIN_FAILED)

    # Auch ohne Treffer wird verifiziert — verify_password rechnet dann gegen einen
    # Dummy-Hash, damit die Antwortzeit nichts über die Existenz des Kontos verrät.
    password_ok = verify_password(user.get("password_hash") if user else None, payload.password)

    if user is None or not password_ok or not user["is_active"]:
        if user is not None and not password_ok:
            await db.record_login_failure(user["id"], MAX_LOGIN_ATTEMPTS, LOCK_MINUTES)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_LOGIN_FAILED)

    await db.record_login_success(user["id"])
    token = await auth_sessions.issue(user["id"], request.headers.get("user-agent"))
    set_session_cookie(response, token)

    fresh = await db.get_user_by_id(user["id"])
    return me_payload(fresh or user)


@router.post("/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        await auth_sessions.revoke(token)
    response.delete_cookie(
        key=settings.session_cookie_name,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    return {"status": "ok"}


@router.get("/me", response_model=MeOut)
async def me(principal: CurrentPrincipal) -> MeOut:
    user = await db.get_user_by_id(principal.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nicht angemeldet")
    return me_payload(user)


@router.post("/password", response_model=MeOut)
async def change_password(
    payload: PasswordChangeRequest, principal: CurrentPrincipal, request: Request
) -> MeOut:
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

    # Alle anderen Geräte fliegen raus; die eigene Sitzung bleibt bestehen, sonst
    # steht man direkt nach dem Wechsel wieder vor dem Login.
    await auth_sessions.revoke_all(
        principal.user_id, keep_token=request.cookies.get(settings.session_cookie_name)
    )

    user = await db.get_user_by_id(principal.user_id)
    return me_payload(user)
