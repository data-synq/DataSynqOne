"""Structured audit context and redacted append-only events."""

from __future__ import annotations

import contextvars
import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone

from . import db
from .ai_privacy import sanitize_payload


logger = logging.getLogger(__name__)

_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "audit_request_id", default=None
)
_actor: contextvars.ContextVar[tuple[str, str | None, str | None]] = contextvars.ContextVar(
    "audit_actor", default=("anonymous", None, None)
)
_ACTION_RE = re.compile(r"^[a-z][a-z0-9_.-]{2,100}$")
_ALLOWED_METADATA_KEYS = frozenset(
    {
        "method",
        "route",
        "status_code",
        "auth_stage",
        "factor",
        "old_role",
        "new_role",
        "old_mode",
        "new_mode",
        "scope_count",
        "document_count",
        "view",
        "mail_sent",
        "purpose",
        "policy_version",
        "model",
        "classes",
        "scanned",
        "embedded",
        "skipped",
        "pruned",
        "errors",
        "complete",
    }
)


def begin_request() -> tuple[str, contextvars.Token, contextvars.Token]:
    request_id = str(uuid.uuid4())
    request_token = _request_id.set(request_id)
    actor_token = _actor.set(("anonymous", None, None))
    return request_id, request_token, actor_token


def end_request(request_token: contextvars.Token, actor_token: contextvars.Token) -> None:
    _request_id.reset(request_token)
    _actor.reset(actor_token)


def set_actor(user_id: str, role: str) -> None:
    _actor.set(("user", user_id, role))


def set_service_actor(name: str) -> None:
    _actor.set(("service", name, None))


def current_request_id() -> str | None:
    return _request_id.get()


def _metadata(value: dict | None) -> dict:
    metadata = value or {}
    unknown = set(metadata) - _ALLOWED_METADATA_KEYS
    if unknown:
        raise ValueError(f"Nicht erlaubte Audit-Metadaten: {sorted(unknown)}")
    sanitized = sanitize_payload(metadata).value
    if len(str(sanitized)) > 8000:
        raise ValueError("Audit-Metadaten sind zu groß")
    return sanitized


async def record(
    action: str,
    outcome: str,
    *,
    reason_code: str | None = None,
    target_type: str | None = None,
    target_id: str | int | None = None,
    metadata: dict | None = None,
    actor_type: str | None = None,
    actor_id: str | None = None,
    actor_role: str | None = None,
) -> dict:
    if not _ACTION_RE.fullmatch(action):
        raise ValueError("Ungültige Audit-Aktion")
    if outcome not in {"started", "success", "denied", "failure"}:
        raise ValueError("Ungültiges Audit-Ergebnis")
    context_actor_type, context_actor_id, context_actor_role = _actor.get()
    return await db.append_audit_event(
        occurred_at=datetime.now(timezone.utc),
        request_id=_request_id.get(),
        actor_type=actor_type or context_actor_type,
        actor_id=actor_id if actor_id is not None else context_actor_id,
        actor_role=actor_role if actor_role is not None else context_actor_role,
        action=action,
        outcome=outcome,
        reason_code=reason_code,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        metadata=_metadata(metadata),
    )


async def safe_record(*args, **kwargs) -> None:
    try:
        await asyncio.wait_for(record(*args, **kwargs), timeout=2)
    except Exception:
        logger.exception("Audit-Ereignis konnte nicht geschrieben werden.")
