import hashlib
import json
from datetime import datetime

from fastapi import APIRouter

from .. import db, vectorstore
from .. import audit as security_audit
from ..ai_privacy import POLICY_VERSION
from ..auth.object_access import parse_object_tag
from ..paperless_client import paperless_client

router = APIRouter(prefix="/sync", tags=["sync"])


def _content_hash(content: str, document: dict) -> str:
    authorization_metadata = {
        "ai_privacy_policy": POLICY_VERSION,
        "embedding_model": vectorstore.settings.embedding_model,
        "content": content,
        "title": document.get("title"),
        "correspondent": document.get("correspondent"),
        "document_type": document.get("document_type"),
        "tags": sorted(document.get("tags") or []),
    }
    return hashlib.sha256(
        json.dumps(authorization_metadata, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _parse_created_date(created: str | None):
    if not created:
        return None
    try:
        return datetime.fromisoformat(created.replace("Z", "+00:00")).date()
    except ValueError:
        return None


@router.post("/documents")
async def sync_documents():
    await security_audit.safe_record("sync.documents", "started")
    listing = await paperless_client.list_all_documents(max_results=100000, max_pages=1000)
    docs = listing.get("results", [])
    tags = await paperless_client.list_tags()
    tags_by_id = {tag["id"]: tag["name"] for tag in tags.get("results", [])}

    scanned = 0
    embedded = 0
    skipped = 0
    errors = []
    current_ids = set()

    for doc in docs:
        scanned += 1
        paperless_id = doc["id"]
        current_ids.add(paperless_id)
        try:
            content = doc.get("content")
            if content is None:
                full = await paperless_client.get_document(paperless_id)
                content = full.get("content") or ""
            content_hash = _content_hash(content, doc)
            object_codes = sorted(
                {
                    parsed[0]
                    for tag_id in doc.get("tags") or []
                    if (tag_name := tags_by_id.get(tag_id)) is not None
                    if (parsed := parse_object_tag(tag_name)) is not None
                }
            )

            existing_hash = await db.get_content_hash(paperless_id)
            if existing_hash == content_hash:
                skipped += 1
                continue

            embedding = await vectorstore.embed_text(content)
            await db.upsert_document(
                paperless_id=paperless_id,
                title=doc.get("title") or f"Dokument {paperless_id}",
                correspondent=str(doc["correspondent"]) if doc.get("correspondent") is not None else None,
                document_type=str(doc["document_type"]) if doc.get("document_type") is not None else None,
                tags=[str(t) for t in (doc.get("tags") or [])],
                object_codes=object_codes,
                created_date=_parse_created_date(doc.get("created")),
                content_hash=content_hash,
                embedding=embedding,
            )
            embedded += 1
        except Exception as e:
            errors.append({"paperless_id": paperless_id, "error": str(e)})

    orphaned: list[int] = []
    complete_listing = (
        not listing.get("truncated")
        and listing.get("count", len(docs)) == len(docs)
        and len(current_ids) == len(docs)
    )
    if complete_listing:
        synced_ids = await db.list_synced_ids()
        orphaned = list(synced_ids - current_ids)
        await db.delete_documents(orphaned)

    result = {
        "scanned": scanned,
        "embedded": embedded,
        "skipped": skipped,
        "pruned": len(orphaned),
        "truncated": bool(listing.get("truncated")),
        "complete": complete_listing,
        "errors": errors,
    }
    await security_audit.safe_record(
        "sync.documents",
        "success" if not errors else "failure",
        reason_code=None if not errors else "document_errors",
        metadata={
            "scanned": scanned,
            "embedded": embedded,
            "skipped": skipped,
            "pruned": len(orphaned),
            "errors": len(errors),
            "complete": complete_listing,
        },
    )
    return result


@router.get("/status")
async def sync_status():
    return {
        "synced_documents": await db.count_synced_documents(),
        "last_synced_at": await db.last_synced_at(),
    }
