"""Anmeldesitzungen: Token erzeugen, auflösen, zurückziehen."""

import hashlib
import secrets

from .. import db
from ..config import settings
from .permissions import Principal, Role, permissions_for

_TOKEN_BYTES = 32


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def issue(user_id: str, user_agent: str | None) -> str:
    """Legt eine Sitzung an und liefert das Klartext-Token für das Cookie."""
    token = secrets.token_urlsafe(_TOKEN_BYTES)
    await db.create_auth_session(
        token_hash=hash_token(token),
        user_id=user_id,
        ttl_hours=settings.session_ttl_hours,
        user_agent=user_agent,
    )
    return token


async def resolve(token: str) -> Principal | None:
    """Token zu Principal. None, wenn abgelaufen, unbekannt oder Konto inaktiv.

    Die Gültigkeit ist rollierend: jeder Request schiebt `expires_at` um die volle
    TTL nach vorn, damit niemand mitten in der Arbeit herausfliegt.
    """
    user = await db.touch_auth_session(hash_token(token), settings.session_ttl_hours)
    if user is None:
        return None
    return await principal_from_user(user)


async def principal_from_user(user: dict) -> Principal:
    role = Role(user["role"])
    return Principal(
        user_id=user["id"],
        email=user["email"],
        display_name=user["display_name"],
        role=role,
        permissions=permissions_for(role),
        object_scope=await db.get_object_scope(user["id"]),
    )


async def revoke(token: str) -> None:
    await db.delete_auth_session(hash_token(token))


async def revoke_all(user_id: str, keep_token: str | None = None) -> None:
    await db.delete_auth_sessions_for_user(
        user_id, keep_token_hash=hash_token(keep_token) if keep_token else None
    )
