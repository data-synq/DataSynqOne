from fastapi import APIRouter, HTTPException, Response, status

from .. import dashboard_service
from .. import audit as security_audit
from ..auth import CurrentPrincipal
from ..auth.object_access import ObjectAccessDenied, ObjectAuthorizer
from ..dashboard_models import DocSummary
from ..paperless_client import paperless_client

router = APIRouter(prefix="/documents", tags=["documents"])


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dokument nicht gefunden")


def _safe_metadata(items: list[dict], *, include_color: bool = False) -> list[dict]:
    fields = {"id", "name", "slug"}
    if include_color:
        fields.add("color")
    return [{key: item.get(key) for key in fields if key in item} for item in items]


async def _visible_documents(principal: CurrentPrincipal, **filters) -> list[dict]:
    response = await paperless_client.list_all_documents(
        **filters, max_results=2000, max_pages=40
    )
    return await ObjectAuthorizer(principal).filter_documents(response.get("results", []))


@router.get("/")
async def list_documents(
    principal: CurrentPrincipal,
    query: str | None = None,
    correspondent__id: int | None = None,
):
    if ObjectAuthorizer(principal).unrestricted:
        return await paperless_client.list_documents(
            query=query, correspondent__id=correspondent__id
        )
    documents = await _visible_documents(
        principal, query=query, correspondent__id=correspondent__id
    )
    return {"count": len(documents), "next": None, "previous": None, "results": documents[:25]}


@router.get("/meta/correspondents")
async def correspondents(principal: CurrentPrincipal):
    response = await paperless_client.list_correspondents()
    if ObjectAuthorizer(principal).unrestricted:
        return response
    documents = await _visible_documents(principal)
    used = {document.get("correspondent") for document in documents}
    results = _safe_metadata(
        [item for item in response.get("results", []) if item["id"] in used]
    )
    return {"count": len(results), "results": results}


@router.get("/meta/document-types")
async def document_types(principal: CurrentPrincipal):
    response = await paperless_client.list_document_types()
    if ObjectAuthorizer(principal).unrestricted:
        return response
    documents = await _visible_documents(principal)
    used = {document.get("document_type") for document in documents}
    results = _safe_metadata(
        [item for item in response.get("results", []) if item["id"] in used]
    )
    return {"count": len(results), "results": results}


@router.get("/meta/tags")
async def tags(principal: CurrentPrincipal):
    response = await paperless_client.list_tags()
    if ObjectAuthorizer(principal).unrestricted:
        return response
    documents = await _visible_documents(principal)
    used = {tag_id for document in documents for tag_id in document.get("tags") or []}
    results = _safe_metadata(
        [item for item in response.get("results", []) if item["id"] in used],
        include_color=True,
    )
    return {"count": len(results), "results": results}


@router.get("/{document_id}")
async def get_document(document_id: int, principal: CurrentPrincipal):
    try:
        document = await ObjectAuthorizer(principal).require_document(document_id)
        await security_audit.safe_record(
            "document.viewed",
            "success",
            target_type="document",
            target_id=document_id,
            metadata={"view": "content"},
        )
        return document
    except ObjectAccessDenied as exc:
        raise _not_found() from exc


@router.get("/{document_id}/detail")
async def get_document_detail(document_id: int, principal: CurrentPrincipal) -> DocSummary:
    try:
        document = await ObjectAuthorizer(principal).require_document(document_id)
    except ObjectAccessDenied as exc:
        raise _not_found() from exc
    return await dashboard_service.get_document_detail(document_id, principal, document)


@router.get("/{document_id}/file")
async def get_document_file(document_id: int, principal: CurrentPrincipal):
    try:
        await ObjectAuthorizer(principal).require_document(document_id)
    except ObjectAccessDenied as exc:
        raise _not_found() from exc
    content, content_type = await paperless_client.get_document_preview(document_id)
    if content_type != "application/pdf" or not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=415, detail="Nur validierte PDF-Vorschauen können angezeigt werden")
    await security_audit.safe_record(
        "document.viewed",
        "success",
        target_type="document",
        target_id=document_id,
        metadata={"view": "pdf"},
    )
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="document-{document_id}.pdf"',
            # frame-ancestors 'self' (not 'none'): the SPA embeds this same
            # response in its own <iframe> for the PDF preview tab. Without
            # it, the global SecurityHeadersMiddleware's X-Frame-Options:
            # DENY default (http_security.py) applies here too, since this
            # response didn't set its own — blocking even that same-origin
            # embed. X-Frame-Options: SAMEORIGIN is the fallback for browsers
            # that don't honor frame-ancestors.
            #
            # No bare `sandbox` token here (unlike an earlier version):
            # combined with the frontend's own iframe sandbox attribute it
            # blocked the browser's native PDF viewer from running its own
            # script (rendering, the download button) — same-origin
            # embedding already prevents the content this was meant to
            # guard against, and default-src 'none' still blocks the PDF
            # from fetching any external resource.
            "Content-Security-Policy": "default-src 'none'; frame-ancestors 'self'",
            "X-Frame-Options": "SAMEORIGIN",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{document_id}/thumbnail")
async def get_document_thumbnail(document_id: int, principal: CurrentPrincipal):
    try:
        await ObjectAuthorizer(principal).require_document(document_id)
    except ObjectAccessDenied as exc:
        raise _not_found() from exc
    content, content_type = await paperless_client.get_document_thumbnail(document_id)
    if content_type not in {"image/webp", "image/png", "image/jpeg"}:
        raise HTTPException(status_code=415, detail="Nicht unterstütztes Vorschaubild")
    signatures = {
        "image/png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": content.startswith(b"\xff\xd8\xff"),
        "image/webp": content.startswith(b"RIFF") and content[8:12] == b"WEBP",
    }
    if not signatures[content_type]:
        raise HTTPException(status_code=415, detail="Ungültiges Vorschaubild")
    return Response(content=content, media_type=content_type)
