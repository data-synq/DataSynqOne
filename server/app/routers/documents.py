from fastapi import APIRouter, Response

from .. import dashboard_service
from ..dashboard_models import DocSummary
from ..paperless_client import paperless_client

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/")
async def list_documents(query: str | None = None, correspondent__id: int | None = None):
    return await paperless_client.list_documents(query=query, correspondent__id=correspondent__id)


@router.get("/{document_id}")
async def get_document(document_id: int):
    return await paperless_client.get_document(document_id)


@router.get("/{document_id}/detail")
async def get_document_detail(document_id: int) -> DocSummary:
    return await dashboard_service.get_document_detail(document_id)


@router.get("/{document_id}/file")
async def get_document_file(document_id: int):
    content, content_type = await paperless_client.get_document_preview(document_id)
    return Response(content=content, media_type=content_type)


@router.get("/meta/correspondents")
async def correspondents():
    return await paperless_client.list_correspondents()


@router.get("/meta/document-types")
async def document_types():
    return await paperless_client.list_document_types()


@router.get("/meta/tags")
async def tags():
    return await paperless_client.list_tags()
