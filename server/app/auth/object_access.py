"""Canonical object labels and fail-closed document authorization."""

import re
from dataclasses import dataclass, field

import httpx

from ..paperless_client import PaperlessClient, paperless_client
from .permissions import ObjectAccessMode, Principal

_OBJECT_TAG_RE = re.compile(r"^(OBJ-[A-Z0-9][A-Z0-9._-]*)(?:\s+(.*))?$", re.IGNORECASE)


class ObjectAccessDenied(LookupError):
    pass


def parse_object_tag(name: str) -> tuple[str, str | None] | None:
    match = _OBJECT_TAG_RE.fullmatch(name.strip())
    if not match:
        return None
    label = (match.group(2) or "").strip()
    return match.group(1).upper(), label or None


def normalize_object_code(value: str) -> str:
    parsed = parse_object_tag(value)
    if parsed is None or parsed[1] is not None:
        raise ValueError(f"Ungültiger Objektcode: {value}")
    return parsed[0]


@dataclass
class ObjectAuthorizer:
    principal: Principal
    client: PaperlessClient = paperless_client
    _tags_by_id: dict[int, dict] | None = field(default=None, init=False)

    @property
    def unrestricted(self) -> bool:
        return self.principal.object_access_mode is ObjectAccessMode.ALL

    async def tags_by_id(self) -> dict[int, dict]:
        if self._tags_by_id is None:
            response = await self.client.list_tags()
            self._tags_by_id = {tag["id"]: tag for tag in response.get("results", [])}
        return self._tags_by_id

    async def document_object_codes(self, document: dict) -> frozenset[str]:
        tags = await self.tags_by_id()
        codes = {
            parsed[0]
            for tag_id in document.get("tags") or []
            if (tag := tags.get(tag_id)) is not None
            if (parsed := parse_object_tag(tag.get("name", ""))) is not None
        }
        return frozenset(codes)

    async def allows_document(self, document: dict) -> bool:
        if self.unrestricted:
            return True
        codes = await self.document_object_codes(document)
        return len(codes) == 1 and codes <= self.principal.object_scope

    async def require_document(self, document_id: int) -> dict:
        try:
            document = await self.client.get_document(document_id)
        except httpx.HTTPStatusError as exc:
            raise ObjectAccessDenied from exc
        if not await self.allows_document(document):
            raise ObjectAccessDenied
        return document

    async def filter_documents(self, documents: list[dict]) -> list[dict]:
        if self.unrestricted:
            return documents
        return [document for document in documents if await self.allows_document(document)]

    def allows_object_code(self, object_code: str | None) -> bool:
        if self.unrestricted:
            return True
        if object_code is None:
            return False
        try:
            normalized = normalize_object_code(object_code)
        except ValueError:
            return False
        return normalized in self.principal.object_scope


async def available_object_options(
    client: PaperlessClient = paperless_client,
) -> list[dict[str, str]]:
    response = await client.list_tags()
    labels: dict[str, str] = {}
    for tag in response.get("results", []):
        parsed = parse_object_tag(tag.get("name", ""))
        if parsed is None:
            continue
        code, label = parsed
        if label or code not in labels:
            labels[code] = label or code
    return [
        {"code": code, "label": labels[code]}
        for code in sorted(labels)
    ]
