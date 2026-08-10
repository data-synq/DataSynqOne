"""Anmeldesitzungen: Token erzeugen, auflösen, zurückziehen."""

import hashlib
import secrets

from .. import db
from ..config import settings
from .permissions import AuthStage, ObjectAccessMode, Principal, Role, permissions_for

_TOKEN_BYTES = 32


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


async def issue(
    user_id: str,
    user_agent: str | None,
    *,
    mfa_verified: bool = False,
    expected_password_hash: str | None = None,
) -> str | None:
    """Legt eine Sitzung an und liefert das Klartext-Token für das Cookie."""
    token = generate_token()
    created = await db.create_auth_session(
        token_hash=hash_token(token),
        user_id=user_id,
        ttl_hours=settings.session_ttl_hours,
        absolute_ttl_hours=settings.session_absolute_ttl_hours,
        user_agent=user_agent,
        mfa_verified=mfa_verified,
        expected_password_hash=expected_password_hash,
    )
    return token if created else None


async def resolve(token: str) -> Principal | None:
    """Token zu Principal. None, wenn abgelaufen, unbekannt oder Konto inaktiv.

    Die Idle-Gültigkeit ist rollierend, endet aber spätestens an der beim Login
    gesetzten absoluten Ablaufzeit.
    """
    user = await db.touch_auth_session(hash_token(token), settings.session_ttl_hours)
    if user is None:
        return None
    return await principal_from_user(user)


async def principal_from_user(user: dict) -> Principal:
    role = Role(user["role"])
    mfa_enabled = bool(user.get("mfa_enabled_at"))
    if user["must_change_password"]:
        auth_stage = AuthStage.PASSWORD_CHANGE
    elif role is Role.ADMIN and not mfa_enabled:
        auth_stage = AuthStage.MFA_SETUP
    elif role is Role.ADMIN and not user.get("mfa_verified_at"):
        auth_stage = AuthStage.MFA_CHALLENGE
    else:
        auth_stage = AuthStage.READY
    try:
        object_access_mode = ObjectAccessMode(user["object_access_mode"])
    except (KeyError, ValueError):
        object_access_mode = ObjectAccessMode.RESTRICTED
    return Principal(
        user_id=user["id"],
        email=user["email"],
        display_name=user["display_name"],
        role=role,
        session_id=user.get("session_id", ""),
        mfa_enabled=mfa_enabled,
        auth_stage=auth_stage,
        permissions=permissions_for(role) if auth_stage is AuthStage.READY else frozenset(),
        object_access_mode=object_access_mode,
        object_scope=await db.get_object_scope(user["id"]) or frozenset(),
    )


async def revoke(token: str) -> None:
    await db.delete_auth_session(hash_token(token))


async def revoke_all(user_id: str, keep_token: str | None = None) -> None:
    await db.delete_auth_sessions_for_user(
        user_id, keep_token_hash=hash_token(keep_token) if keep_token else None
    )
