import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from .. import db, tagging
from .. import audit as security_audit
from ..auth import CurrentPrincipal, Permission, require
from ..auth.object_access import ObjectAccessDenied, ObjectAuthorizer
from ..models import CaseDocumentAttachRequest, CaseLinkRequest, CaseNoteRequest
from ..paperless_client import paperless_client
from ..tagging import CASE_TAG_COLOR

router = APIRouter(prefix="/cases", tags=["cases"])


async def _get_case_or_404(tracking_id: str, principal: CurrentPrincipal) -> dict:
    case = await db.get_case(tracking_id)
    if case is None or not ObjectAuthorizer(principal).allows_object_code(case.get("object_code")):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anliegen nicht gefunden")
    return case


async def _visible_case_links(tracking_id: str, principal: CurrentPrincipal) -> list[dict]:
    authorizer = ObjectAuthorizer(principal)
    visible = []
    for link in await db.list_case_links_for(tracking_id):
        dependent = await db.get_case(link["dependent_tracking_id"])
        prerequisite = await db.get_case(link["prerequisite_tracking_id"])
        if (
            dependent
            and prerequisite
            and authorizer.allows_object_code(dependent.get("object_code"))
            and authorizer.allows_object_code(prerequisite.get("object_code"))
        ):
            visible.append(link)
    return visible


@router.get("", dependencies=[Depends(require(Permission.DOCUMENTS_READ))])
async def list_cases(principal: CurrentPrincipal, status_filter: str | None = None):
    return [
        case
        for case in await db.list_cases(status_filter)
        if ObjectAuthorizer(principal).allows_object_code(case.get("object_code"))
    ]


@router.get("/{tracking_id}", dependencies=[Depends(require(Permission.DOCUMENTS_READ))])
async def get_case(tracking_id: str, principal: CurrentPrincipal):
    case = await _get_case_or_404(tracking_id, principal)
    documents = []
    authorizer = ObjectAuthorizer(principal)
    for reference in await db.list_case_documents(case["id"]):
        try:
            await authorizer.require_document(reference["paperless_id"])
        except ObjectAccessDenied:
            continue
        documents.append(reference)
    return {
        **case,
        "documents": documents,
        "events": await db.list_case_events(case["id"]),
        "notes": await db.list_case_notes(case["id"]),
        "links": await _visible_case_links(tracking_id, principal),
    }


@router.post("/{tracking_id}/notes", dependencies=[Depends(require(Permission.AGENT_WRITE))])
async def add_case_note(tracking_id: str, payload: CaseNoteRequest, principal: CurrentPrincipal):
    case = await _get_case_or_404(tracking_id, principal)
    note = await db.add_case_note(case["id"], principal.user_id, payload.body)
    await db.add_case_event(
        case["id"],
        "note_added",
        detail=payload.body[:200],
        actor_user_id=principal.user_id,
        link_kind="note",
        link_id=note["id"],
    )
    await security_audit.safe_record(
        "case.note_added", "success", target_type="case", target_id=tracking_id
    )
    return note


@router.post("/{tracking_id}/close", dependencies=[Depends(require(Permission.AGENT_WRITE))])
async def close_case(tracking_id: str, principal: CurrentPrincipal):
    await _get_case_or_404(tracking_id, principal)
    case = await db.close_case(tracking_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anliegen nicht gefunden oder bereits geschlossen")
    await db.add_case_event(case["id"], "closed", actor_user_id=principal.user_id)
    await security_audit.safe_record(
        "case.closed", "success", target_type="case", target_id=tracking_id
    )
    return case


@router.post("/{tracking_id}/reopen", dependencies=[Depends(require(Permission.AGENT_WRITE))])
async def reopen_case(tracking_id: str, principal: CurrentPrincipal):
    await _get_case_or_404(tracking_id, principal)
    case = await db.reopen_case(tracking_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anliegen nicht gefunden oder bereits offen")
    await db.add_case_event(case["id"], "reopened", actor_user_id=principal.user_id)
    await security_audit.safe_record(
        "case.reopened", "success", target_type="case", target_id=tracking_id
    )
    return case


@router.get("/links/all", dependencies=[Depends(require(Permission.DOCUMENTS_READ))])
async def list_all_links(principal: CurrentPrincipal):
    """Die komplette Kantenliste für den Abhängigkeitsgraphen."""
    visible = {
        case["tracking_id"]
        for case in await db.list_cases()
        if ObjectAuthorizer(principal).allows_object_code(case.get("object_code"))
    }
    return [
        link
        for link in await db.list_all_case_links()
        if link["dependent_tracking_id"] in visible
        and link["prerequisite_tracking_id"] in visible
    ]


@router.post("/links", dependencies=[Depends(require(Permission.AGENT_WRITE))])
async def create_case_link(payload: CaseLinkRequest, principal: CurrentPrincipal):
    """Von Hand gesetzt gilt sofort als bestätigt — anders als ein vom Agenten
    vorgeschlagener Zusammenhang, der erst bestätigt werden muss."""
    await _get_case_or_404(payload.dependent_tracking_id, principal)
    await _get_case_or_404(payload.prerequisite_tracking_id, principal)
    link = await db.propose_case_link(
        payload.dependent_tracking_id, payload.prerequisite_tracking_id, proposed_by=principal.user_id
    )
    if link is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Eines der beiden Anliegen wurde nicht gefunden, oder die Verknüpfung besteht bereits.",
        )
    confirmed = await db.confirm_case_link(payload.dependent_tracking_id, payload.prerequisite_tracking_id)
    case = await db.get_case(payload.dependent_tracking_id)
    if case is not None:
        await db.add_case_event(
            case["id"],
            "linked",
            detail="Manuell verknüpft",
            actor_user_id=principal.user_id,
            link_kind="case",
            link_id=payload.prerequisite_tracking_id,
        )
    await security_audit.safe_record(
        "case.linked",
        "success",
        target_type="case",
        target_id=payload.dependent_tracking_id,
    )
    return confirmed


@router.post(
    "/links/{dependent_tracking_id}/{prerequisite_tracking_id}/confirm",
    dependencies=[Depends(require(Permission.AGENT_WRITE))],
)
async def confirm_case_link(dependent_tracking_id: str, prerequisite_tracking_id: str, principal: CurrentPrincipal):
    await _get_case_or_404(dependent_tracking_id, principal)
    await _get_case_or_404(prerequisite_tracking_id, principal)
    link = await db.confirm_case_link(dependent_tracking_id, prerequisite_tracking_id)
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Verknüpfung nicht gefunden")
    case = await db.get_case(dependent_tracking_id)
    if case is not None:
        await db.add_case_event(
            case["id"],
            "linked",
            detail="Vorschlag bestätigt",
            actor_user_id=principal.user_id,
            link_kind="case",
            link_id=prerequisite_tracking_id,
        )
    await security_audit.safe_record(
        "case.link_confirmed",
        "success",
        target_type="case",
        target_id=dependent_tracking_id,
    )
    return link


@router.delete(
    "/links/{dependent_tracking_id}/{prerequisite_tracking_id}",
    dependencies=[Depends(require(Permission.AGENT_WRITE))],
)
async def remove_case_link(dependent_tracking_id: str, prerequisite_tracking_id: str, principal: CurrentPrincipal):
    await _get_case_or_404(dependent_tracking_id, principal)
    await _get_case_or_404(prerequisite_tracking_id, principal)
    await db.remove_case_link(dependent_tracking_id, prerequisite_tracking_id)
    case = await db.get_case(dependent_tracking_id)
    if case is not None:
        await db.add_case_event(
            case["id"],
            "unlinked",
            actor_user_id=principal.user_id,
            link_kind="case",
            link_id=prerequisite_tracking_id,
        )
    await security_audit.safe_record(
        "case.unlinked",
        "success",
        target_type="case",
        target_id=dependent_tracking_id,
    )
    return {"status": "removed"}


@router.post("/{tracking_id}/documents", dependencies=[Depends(require(Permission.AGENT_WRITE))])
async def attach_case_documents(tracking_id: str, payload: CaseDocumentAttachRequest, principal: CurrentPrincipal):
    """Verknüpfung erfolgt über einen Paperless-Tag mit dem Tracking-ID als Namen —
    dadurch bleibt sie auch innerhalb von Paperless selbst sichtbar/filterbar, statt
    nur eine stille Zeile in unserer eigenen Tabelle zu sein."""
    case = await _get_case_or_404(tracking_id, principal)
    authorizer = ObjectAuthorizer(principal)
    documents: list[tuple[int, dict]] = []
    for paperless_id in payload.paperless_ids:
        try:
            document = await authorizer.require_document(paperless_id)
        except ObjectAccessDenied as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dokument {paperless_id} nicht gefunden",
            ) from exc
        document_codes = await authorizer.document_object_codes(document)
        if case.get("object_code") and document_codes != {case["object_code"]}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Dokument {paperless_id} gehört nicht zum Objekt des Anliegens.",
            )
        documents.append((paperless_id, document))
    tag = None
    if authorizer.unrestricted:
        tag = await tagging.get_or_create(
            paperless_client.list_tags,
            lambda name: paperless_client.create_tag(name, color=CASE_TAG_COLOR),
            tracking_id,
        )
    for paperless_id, document in documents:
        current_tags = document.get("tags", [])
        if tag is not None and tag["id"] not in current_tags:
            await authorizer.require_document(paperless_id)
            await paperless_client.bulk_edit([paperless_id], "add_tag", {"tag": tag["id"]})
        await db.add_case_document(case["id"], paperless_id, role="linked")
        await db.add_case_event(
            case["id"],
            "linked",
            actor_user_id=principal.user_id,
            link_kind="document",
            link_id=str(paperless_id),
        )
    await security_audit.safe_record(
        "case.documents_attached",
        "success",
        target_type="case",
        target_id=tracking_id,
        metadata={"document_count": len(documents)},
    )
    return await db.list_case_documents(case["id"])


@router.delete("/{tracking_id}/documents/{paperless_id}", dependencies=[Depends(require(Permission.AGENT_WRITE))])
async def detach_case_document(tracking_id: str, paperless_id: int, principal: CurrentPrincipal):
    case = await _get_case_or_404(tracking_id, principal)
    try:
        await ObjectAuthorizer(principal).require_document(paperless_id)
    except ObjectAccessDenied as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dokument nicht gefunden"
        ) from exc
    authorizer = ObjectAuthorizer(principal)
    tag = (
        await tagging.find_by_name(paperless_client.list_tags, tracking_id)
        if authorizer.unrestricted
        else None
    )
    if tag is not None:
        try:
            document = await paperless_client.get_document(paperless_id)
        except httpx.HTTPStatusError:
            document = None
        if document is not None:
            await ObjectAuthorizer(principal).require_document(paperless_id)
            await paperless_client.bulk_edit([paperless_id], "remove_tag", {"tag": tag["id"]})
    await db.remove_case_document(case["id"], paperless_id)
    await db.add_case_event(
        case["id"],
        "unlinked",
        actor_user_id=principal.user_id,
        link_kind="document",
        link_id=str(paperless_id),
    )
    await security_audit.safe_record(
        "case.document_detached",
        "success",
        target_type="case",
        target_id=tracking_id,
        metadata={"document_count": 1},
    )
    return {"status": "removed"}
