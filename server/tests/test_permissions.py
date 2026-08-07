"""Die Rechte-Matrix und der Werkzeugfilter — reine Funktionen, keine Datenbank.

Der Test, auf den es ankommt, ist test_viewer_never_sees_a_write_tool: er schlaegt
fehl, sobald jemand ein schreibendes Werkzeug ergaenzt, ohne es in WRITE_TOOLS
einzutragen. Genau dieses Vergessen waere sonst still, und ein Betrachter koennte
darueber Dokumente aendern.
"""

import pytest

from app.agent.tools import (
    PERMISSION_DENIED,
    RESPONSES_TOOL_DEFINITIONS,
    WRITE_TOOLS,
    call_tool,
    tools_for,
)
from app.auth.permissions import Permission, Principal, Role, permissions_for

# Namen, an denen ein schreibendes Werkzeug zu erkennen ist. Bewusst unabhaengig
# von WRITE_TOOLS formuliert — sonst wuerde der Test dieselbe Liste pruefen, die
# er absichern soll.
_WRITE_PREFIXES = ("create_", "delete_", "assign_", "set_document_", "rename_", "bulk_")
_READ_ONLY_EXCEPTIONS = {"create_chart"}  # zeichnet nur, aendert nichts in Paperless


def _tool_names(tools):
    return {t["name"] for t in tools}


class TestRoleMatrix:
    def test_viewer_may_read_and_chat_but_not_write(self):
        perms = permissions_for(Role.VIEWER)
        assert Permission.DOCUMENTS_READ in perms
        assert Permission.AGENT_CHAT in perms
        assert Permission.AGENT_WRITE not in perms
        assert Permission.SYNC_RUN not in perms
        assert Permission.USERS_MANAGE not in perms

    def test_editor_may_write_but_not_manage_users_or_sync(self):
        perms = permissions_for(Role.EDITOR)
        assert Permission.AGENT_WRITE in perms
        assert Permission.SYNC_RUN not in perms
        assert Permission.USERS_MANAGE not in perms

    def test_admin_has_every_permission(self):
        assert permissions_for(Role.ADMIN) == frozenset(Permission)

    def test_unknown_role_gets_nothing(self):
        # Ein Tippfehler in der Rolle darf niemals versehentlich Rechte vergeben.
        assert permissions_for("chef") == frozenset()

    def test_principal_can_reflects_its_permissions(self):
        viewer = Principal(
            user_id="1",
            email="b@example.org",
            display_name="Bea",
            role=Role.VIEWER,
            permissions=permissions_for(Role.VIEWER),
        )
        assert viewer.can(Permission.AGENT_CHAT)
        assert not viewer.can(Permission.AGENT_WRITE)


class TestToolFiltering:
    def test_write_tools_all_exist(self):
        known = _tool_names(RESPONSES_TOOL_DEFINITIONS)
        assert WRITE_TOOLS <= known, f"unbekannt: {WRITE_TOOLS - known}"

    def test_viewer_never_sees_a_write_tool(self):
        offered = _tool_names(tools_for(can_write=False))
        suspicious = {
            name
            for name in offered
            if name.startswith(_WRITE_PREFIXES) and name not in _READ_ONLY_EXCEPTIONS
        }
        assert not suspicious, (
            f"Diese Werkzeuge sehen schreibend aus, werden einem Betrachter aber "
            f"angeboten: {sorted(suspicious)}. Fehlen sie in WRITE_TOOLS?"
        )

    def test_editor_sees_the_full_list(self):
        assert _tool_names(tools_for(can_write=True)) == _tool_names(RESPONSES_TOOL_DEFINITIONS)

    def test_viewer_keeps_the_reading_tools(self):
        offered = _tool_names(tools_for(can_write=False))
        for name in ("search_documents", "semantic_search_documents", "calculator", "create_chart"):
            assert name in offered

    def test_filtering_removes_exactly_the_write_tools(self):
        assert _tool_names(RESPONSES_TOOL_DEFINITIONS) - _tool_names(
            tools_for(can_write=False)
        ) == set(WRITE_TOOLS)


class TestCallToolGuard:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("name", sorted(WRITE_TOOLS))
    async def test_write_tool_is_refused_without_permission(self, name):
        # Zweite Verteidigungslinie: das Modell kann einen Werkzeugnamen erfinden,
        # auch wenn er ihm nie angeboten wurde. Kein Netzwerkzugriff noetig — die
        # Pruefung steht vor jeder Weiterleitung an Paperless.
        assert await call_tool(name, {}, can_write=False) == PERMISSION_DENIED

    @pytest.mark.asyncio
    async def test_unknown_tool_still_reports_unknown(self):
        result = await call_tool("gibt_es_nicht", {}, can_write=False)
        assert "unknown tool" in result["error"]
