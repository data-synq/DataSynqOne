"""Local, deterministic privacy boundary for outbound AI payloads."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


POLICY_VERSION = "2026-08-10.3"


class AIPurpose(StrEnum):
    AGENT = "agent"
    QUERY_EXPANSION = "query_expansion"
    AMOUNT_EXTRACTION = "amount_extraction"
    SUGGESTIONS = "suggestions"
    MAIL_INTAKE = "mail_intake"
    DOCUMENT_EMBEDDING = "document_embedding"
    QUERY_EMBEDDING = "query_embedding"


class PrivacyBoundaryError(RuntimeError):
    pass


@dataclass(frozen=True)
class SanitizedPayload:
    value: Any
    classes: dict[str, int]
    raw_hash: str
    sanitized_hash: str


_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "PROMPT_INJECTION",
        re.compile(
            r"\b(?:ignore|ignoriere|vergiss|disregard|override)\b.{0,120}\b(?:instructions?|anweisungen?|system|prompt|regeln?)\b.{0,500}|\b(?:rufe|call|execute|fuehre|führe)\b.{0,120}\b(?:tool|werkzeug|function|delete_|prepare_email)\b.{0,500}",
            re.I | re.S,
        ),
        "<UNTRUSTED_INSTRUCTION_BLOCKED>",
    ),
    (
        "PRIVATE_KEY",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.I | re.S),
        "<BLOCKED_SECRET>",
    ),
    ("EMAIL", re.compile(r"(?<![\w@])[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}(?![\w@])", re.I), "<EMAIL>"),
    ("IBAN", re.compile(r"\b[A-Z]{2}\s?\d{2}(?:[\s-]?[A-Z0-9]){11,30}\b", re.I), "<IBAN>"),
    ("BIC", re.compile(r"\b[A-Z]{4}(?:DE|AT|CH|NL|BE|FR|IT|ES|PL|CZ)[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b"), "<BIC>"),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"), "<BLOCKED_SECRET>"),
    (
        "AUTH_SECRET",
        re.compile(
            r"(?i)\b(?:bearer\s+[A-Za-z0-9._~+/=-]{12,}|sk-(?:proj-)?[A-Za-z0-9_-]{12,}|AKIA[A-Z0-9]{16}|gh[opusr]_[A-Za-z0-9]{20,}|(?:api[_-]?key|token|password|passwd|secret|authorization|cookie)\s*[:=]\s*[^\s,;]{6,})"
        ),
        "<BLOCKED_SECRET>",
    ),
    (
        "CREDENTIAL_URL",
        re.compile(r"https?://[^\s<>]+[?&](?:token|key|secret|code|password)=[^\s<>&]+", re.I),
        "<CREDENTIAL_URL>",
    ),
    ("PHONE", re.compile(r"(?<!\w)(?:\+49|0049|0)[\s()/.-]*(?:\d[\s()/.-]*){7,14}(?!\w)"), "<PHONE>"),
    (
        "ADDRESS",
        re.compile(
            r"\b(?:(?:[A-ZÄÖÜ][A-Za-zÄÖÜäöüß\-]+\s+){0,2}[A-ZÄÖÜ][A-Za-zÄÖÜäöüß\-]*(?:straße|strasse|str\.?|weg|allee|platz|gasse|ring|ufer|stieg|bahn|damm|chaussee|markt)|(?:Am|An|Auf|Unter|In)\s+(?:der\s+|den\s+|dem\s+)?[A-ZÄÖÜ][A-Za-zÄÖÜäöüß\- ]+)\s+\d+[a-z]?(?:\s*[-/]\s*\d+)?\b|\bPostfach\s+\d+\b|\b\d{5}\s+[A-ZÄÖÜ][A-Za-zÄÖÜäöüß\-]+\b",
            re.I,
        ),
        "<ADDRESS>",
    ),
    (
        "PERSON",
        re.compile(r"\b(?:Herrn?|Frau|Familie)\s+[A-ZÄÖÜ][A-Za-zÄÖÜäöüß'\-]+(?:\s+[A-ZÄÖÜ][A-Za-zÄÖÜäöüß'\-]+){0,2}\b"),
        "<PERSON>",
    ),
    (
        "PERSON",
        re.compile(r"\b[A-ZÄÖÜ][a-zäöüß][A-Za-zÄÖÜäöüß'\-]{1,30}\s+[A-ZÄÖÜ][a-zäöüß][A-Za-zÄÖÜäöüß'\-]{1,30}\b"),
        "<PERSON>",
    ),
    (
        "PERSON",
        re.compile(
            r"\b(?:[A-ZÄÖÜ][a-zäöüß][A-Za-zÄÖÜäöüß'\-]{1,30}|[A-ZÄÖÜ]{2,})\s+(?:(?:von|van|de|der|den|zu)\s+){0,3}(?:[A-ZÄÖÜ][a-zäöüß][A-Za-zÄÖÜäöüß'\-]{1,30}|[A-ZÄÖÜ]{2,}|[A-ZÄÖÜ]\.)\b"
        ),
        "<PERSON>",
    ),
)

_RESIDUAL_SECRET_PATTERNS = tuple(
    pattern for name, pattern, _replacement in _PATTERNS if name in {"PRIVATE_KEY", "JWT", "AUTH_SECRET"}
)


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    return "".join(char for char in normalized if unicodedata.category(char) != "Cf")


def redact_text(text: str) -> tuple[str, Counter[str]]:
    redacted = _normalize(text)
    classes: Counter[str] = Counter()
    for name, pattern, replacement in _PATTERNS:
        redacted, count = pattern.subn(replacement, redacted)
        if count:
            classes[name] += count
    if any(pattern.search(redacted) for pattern in _RESIDUAL_SECRET_PATTERNS):
        raise PrivacyBoundaryError("Residualscan hat ein nicht redigiertes Secret erkannt.")
    return redacted, classes


_SENSITIVE_KEYS = {
    "api_key", "apikey", "authorization", "cookie", "password", "passwd", "secret",
    "session", "session_token", "token", "access_token", "refresh_token", "private_key",
}


def _sanitize(value: Any, classes: Counter[str], key: str | None = None) -> Any:
    normalized_key = ""
    if key:
        separated = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", key.strip())
        normalized_key = re.sub(r"[^A-Za-z0-9]+", "_", separated).strip("_").lower()
    sensitive_key = normalized_key in _SENSITIVE_KEYS or any(
        normalized_key.endswith(f"_{suffix}")
        for suffix in ("api_key", "key", "password", "passwd", "secret", "token", "cookie")
    )
    if sensitive_key:
        classes["STRUCTURED_SECRET"] += 1
        return "<BLOCKED_SECRET>"
    if isinstance(value, str):
        redacted, found = redact_text(value)
        classes.update(found)
        return redacted
    if isinstance(value, list):
        return [_sanitize(item, classes) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize(item, classes) for item in value)
    if isinstance(value, dict):
        return {str(item_key): _sanitize(item, classes, str(item_key)) for item_key, item in value.items()}
    if value is None or isinstance(value, (bool, int, float)):
        return value
    raise PrivacyBoundaryError(f"Nicht unterstützter AI-Payload-Typ: {type(value).__name__}")


def sanitize_payload(value: Any) -> SanitizedPayload:
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        classes: Counter[str] = Counter()
        sanitized = _sanitize(value, classes)
        encoded = json.dumps(sanitized, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    except PrivacyBoundaryError:
        raise
    except Exception as exc:
        raise PrivacyBoundaryError("AI-Payload konnte nicht lokal klassifiziert werden.") from exc
    return SanitizedPayload(
        value=sanitized,
        classes=dict(classes),
        raw_hash=hashlib.sha256(raw).hexdigest(),
        sanitized_hash=hashlib.sha256(encoded).hexdigest(),
    )
