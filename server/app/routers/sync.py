import hashlib
from datetime import datetime

from fastapi import APIRouter

from .. import db, vectorstore
from ..paperless_client import paperless_client

router = APIRouter(prefix="/sync", tags=["sync"])


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _parse_created_date(created: str | None):
    if not created:
        return None
    try:
        return datetime.fromisoformat(created.replace("Z", "+00:00")).date()
    except ValueError:
        return None


@router.post("/documents")
async def sync_documents():
    listing = await paperless_client.list_all_documents(max_results=2000)
    docs = listing.get("results", [])

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
            content_hash = _content_hash(content)

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
                created_date=_parse_created_date(doc.get("created")),
                content_hash=content_hash,
                embedding=embedding,
            )
            embedded += 1
        except Exception as e:
            errors.append({"paperless_id": paperless_id, "error": str(e)})

    synced_ids = await db.list_synced_ids()
    orphaned = list(synced_ids - current_ids)
    await db.delete_documents(orphaned)

    return {
        "scanned": scanned,
        "embedded": embedded,
        "skipped": skipped,
        "pruned": len(orphaned),
        "errors": errors,
    }


@router.get("/status")
async def sync_status():
    return {
        "synced_documents": await db.count_synced_documents(),
        "last_synced_at": await db.last_synced_at(),
    }
