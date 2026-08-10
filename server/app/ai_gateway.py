"""The only module allowed to send application data to OpenAI."""

from __future__ import annotations

import logging
from typing import Any

from . import openai_client
from . import audit as security_audit
from .ai_privacy import AIPurpose, POLICY_VERSION, sanitize_payload


logger = logging.getLogger(__name__)


def _approved(purpose: AIPurpose, payload: dict[str, Any]):
    if not isinstance(purpose, AIPurpose):
        raise ValueError("Jeder AI-Aufruf benötigt einen bekannten Verwendungszweck.")
    result = sanitize_payload(payload)
    logger.info(
        "AI privacy gate allowed purpose=%s policy=%s raw_hash=%s sanitized_hash=%s classes=%s",
        purpose.value,
        POLICY_VERSION,
        result.raw_hash,
        result.sanitized_hash,
        result.classes,
    )
    return result


async def _audit_privacy(purpose: AIPurpose, result, model: str, outcome: str) -> None:
    await security_audit.safe_record(
        "ai.privacy",
        outcome,
        reason_code=None if outcome == "success" else "privacy_or_transport_failure",
        metadata={
            "purpose": purpose.value,
            "policy_version": POLICY_VERSION,
            "model": model,
            "classes": result.classes if result is not None else {},
        },
        actor_type="service",
        actor_id="ai-gateway",
    )


async def responses_create(purpose: AIPurpose, **payload: Any):
    result = None
    try:
        result = _approved(purpose, payload)
        response = await openai_client._get_transport().responses.create(**result.value)
    except Exception:
        await _audit_privacy(purpose, result, str(payload.get("model", "")), "failure")
        raise
    await _audit_privacy(purpose, result, str(payload.get("model", "")), "success")
    return response


async def chat_completion(purpose: AIPurpose, **payload: Any):
    result = None
    try:
        result = _approved(purpose, payload)
        response = await openai_client._get_transport().chat.completions.create(**result.value)
    except Exception:
        await _audit_privacy(purpose, result, str(payload.get("model", "")), "failure")
        raise
    await _audit_privacy(purpose, result, str(payload.get("model", "")), "success")
    return response


async def embedding(purpose: AIPurpose, **payload: Any) -> list[float]:
    result = None
    try:
        result = _approved(purpose, payload)
        response = await openai_client._get_transport().embeddings.create(**result.value)
    except Exception:
        await _audit_privacy(purpose, result, str(payload.get("model", "")), "failure")
        raise
    await _audit_privacy(purpose, result, str(payload.get("model", "")), "success")
    return response.data[0].embedding
