from contextlib import asynccontextmanager

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.agent import tools
from app import dashboard_service
from app.auth import AuthStage, ObjectAccessMode, Permission, Principal, Role
from app.auth import dependencies
from app.auth.object_access import ObjectAccessDenied, ObjectAuthorizer, parse_object_tag
from app.models import ObjectAccessRequest


class PaperlessStub:
    def __init__(self):
        self.tags = {
            1: {"id": 1, "name": "OBJ-001 Musterhof"},
            2: {"id": 2, "name": "OBJ-002 Nebenhaus"},
            3: {"id": 3, "name": "invoice"},
        }
        self.documents = {
            10: {"id": 10, "title": "Eigen", "tags": [1, 3], "content": "own"},
            20: {"id": 20, "title": "Fremd", "tags": [2], "content": "foreign"},
            30: {"id": 30, "title": "Ohne Objekt", "tags": [3]},
            40: {"id": 40, "title": "Mehrdeutig", "tags": [1, 2]},
        }

    async def list_tags(self):
        return {"count": len(self.tags), "results": list(self.tags.values())}

    async def get_document(self, document_id: int):
        return self.documents[document_id]


def principal(mode: ObjectAccessMode, codes: frozenset[str] = frozenset()) -> Principal:
    return Principal(
        user_id="00000000-0000-0000-0000-000000000001",
        email="viewer@example.org",
        display_name="Viewer",
        role=Role.VIEWER,
        auth_stage=AuthStage.READY,
        permissions=frozenset({Permission.DOCUMENTS_READ, Permission.AGENT_CHAT}),
        object_access_mode=mode,
        object_scope=codes,
    )


@pytest.fixture
def authorization_lease(monkeypatch):
    @asynccontextmanager
    async def lease(*_args, **_kwargs):
        yield True

    monkeypatch.setattr(tools.db, "authorization_lease", lease)


def test_object_tags_are_canonicalized():
    assert parse_object_tag("obj-001 Musterhof") == ("OBJ-001", "Musterhof")
    assert parse_object_tag("invoice") is None


def test_scope_request_is_explicit_and_rejects_ambiguous_empty_access():
    with pytest.raises(ValidationError):
        ObjectAccessRequest(mode="restricted", object_codes=[])
    with pytest.raises(ValidationError):
        ObjectAccessRequest(mode="all", object_codes=["OBJ-001"])

    access = ObjectAccessRequest(
        mode="restricted", object_codes=["obj-001", "OBJ-001"]
    )
    assert access.object_codes == ["OBJ-001"]


async def test_restricted_document_access_is_fail_closed():
    client = PaperlessStub()
    authorizer = ObjectAuthorizer(
        principal(ObjectAccessMode.RESTRICTED, frozenset({"OBJ-001"})), client
    )

    assert (await authorizer.require_document(10))["title"] == "Eigen"
    for document_id in (20, 30, 40):
        with pytest.raises(ObjectAccessDenied):
            await authorizer.require_document(document_id)


async def test_restricted_empty_scope_never_means_global_access():
    client = PaperlessStub()
    authorizer = ObjectAuthorizer(principal(ObjectAccessMode.RESTRICTED), client)

    assert await authorizer.filter_documents(list(client.documents.values())) == []


async def test_unrestricted_access_keeps_objectless_documents_visible():
    client = PaperlessStub()
    authorizer = ObjectAuthorizer(principal(ObjectAccessMode.ALL), client)

    assert len(await authorizer.filter_documents(list(client.documents.values()))) == 4


async def test_agent_direct_document_access_uses_the_same_authorizer(
    monkeypatch, authorization_lease
):
    client = PaperlessStub()
    monkeypatch.setattr(tools.paperless_client, "list_tags", client.list_tags)
    monkeypatch.setattr(tools.paperless_client, "get_document", client.get_document)
    restricted = principal(ObjectAccessMode.RESTRICTED, frozenset({"OBJ-001"}))

    visible = await tools.call_tool(
        "get_document", {"document_id": 10}, can_write=False, principal=restricted
    )
    hidden = await tools.call_tool(
        "get_document", {"document_id": 20}, can_write=False, principal=restricted
    )

    assert visible["title"] == "Eigen"
    assert hidden == {"error": "Dokument nicht gefunden."}


async def test_restricted_admin_cannot_execute_global_permissions():
    restricted_admin = Principal(
        user_id="00000000-0000-0000-0000-000000000001",
        email="admin@example.org",
        display_name="Admin",
        role=Role.ADMIN,
        permissions=frozenset(Permission),
        object_access_mode=ObjectAccessMode.RESTRICTED,
        object_scope=frozenset({"OBJ-001"}),
    )

    with pytest.raises(HTTPException) as exc:
        await dependencies.require(Permission.USERS_MANAGE)(restricted_admin)

    assert exc.value.status_code == 403
    assert "globale Aktion" in exc.value.detail


async def test_dashboard_aggregates_only_visible_documents(monkeypatch):
    client = PaperlessStub()

    async def list_all_documents(**_kwargs):
        return {"count": 4, "results": list(client.documents.values())}

    async def list_correspondents():
        return {"results": []}

    async def list_document_types():
        return {"results": []}

    monkeypatch.setattr(dashboard_service.paperless_client, "list_tags", client.list_tags)
    monkeypatch.setattr(
        dashboard_service.paperless_client, "list_all_documents", list_all_documents
    )
    monkeypatch.setattr(
        dashboard_service.paperless_client, "list_correspondents", list_correspondents
    )
    monkeypatch.setattr(
        dashboard_service.paperless_client, "list_document_types", list_document_types
    )
    restricted = principal(ObjectAccessMode.RESTRICTED, frozenset({"OBJ-001"}))

    overview = await dashboard_service.get_overview(restricted)

    assert overview.kpis["total"] == 1
    assert [document.id for document in overview.recent] == [10]


async def test_agent_bulk_update_requires_deterministic_confirmation(
    monkeypatch, authorization_lease
):
    client = PaperlessStub()
    bulk_calls = []

    async def bulk_edit(*args, **kwargs):
        bulk_calls.append((args, kwargs))
        return {}

    monkeypatch.setattr(tools.paperless_client, "list_tags", client.list_tags)
    monkeypatch.setattr(tools.paperless_client, "get_document", client.get_document)
    monkeypatch.setattr(tools.paperless_client, "bulk_edit", bulk_edit)
    restricted = principal(ObjectAccessMode.RESTRICTED, frozenset({"OBJ-001"}))

    result = await tools.call_tool(
        "bulk_update_documents",
        {"document_ids": [10, 20], "add_tag_names": ["invoice"]},
        can_write=True,
        principal=restricted,
    )

    assert "ausserhalb des Sprachmodells" in result["error"]
    assert bulk_calls == []


async def test_restricted_agent_cannot_mutate_paperless_tags(
    monkeypatch, authorization_lease
):
    client = PaperlessStub()
    bulk_calls = []

    async def bulk_edit(*args, **kwargs):
        bulk_calls.append((args, kwargs))
        return {}

    monkeypatch.setattr(tools.paperless_client, "list_tags", client.list_tags)
    monkeypatch.setattr(tools.paperless_client, "get_document", client.get_document)
    monkeypatch.setattr(tools.paperless_client, "bulk_edit", bulk_edit)
    restricted = principal(ObjectAccessMode.RESTRICTED, frozenset({"OBJ-001"}))

    result = await tools.call_tool(
        "assign_tags_to_document",
        {"document_id": 10, "tag_names": ["invoice"]},
        can_write=True,
        principal=restricted,
    )

    assert "ausserhalb des Sprachmodells" in result["error"]
    assert bulk_calls == []
