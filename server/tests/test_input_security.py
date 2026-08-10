import pytest
from pydantic import ValidationError
from starlette.requests import Request

from app.agent.tools import validate_tool_arguments, write_is_explicitly_authorized
from app.http_security import BodyLimitMiddleware
from app import main
from app.models import ChatRequest
from app.paperless_client import PaperlessClient
from app.network import resolve_client_ip
from app.routers import auth


def _request(peer: str, forwarded: str | None = None) -> Request:
    headers = [] if forwarded is None else [(b"x-forwarded-for", forwarded.encode())]
    return Request({"type": "http", "method": "POST", "path": "/auth/login", "headers": headers, "client": (peer, 1234)})


def test_forwarded_source_requires_a_trusted_proxy(monkeypatch):
    monkeypatch.setattr(auth.settings, "environment", "production")
    monkeypatch.setattr(auth.settings, "trusted_proxy_cidrs", ["172.30.0.0/24"])
    assert auth._login_source(_request("10.0.0.4", "198.51.100.9")) == "10.0.0.4"
    assert auth._login_source(_request("172.30.0.5", "198.51.100.9")) == "198.51.100.9"
    assert auth._login_source(_request("172.30.0.5", "not-an-ip")) == "172.30.0.5"
    assert resolve_client_ip("172.30.0.5", "198.51.100.9", ["172.30.0.0/24"]) == "198.51.100.9"


def test_client_history_is_rejected_and_messages_are_bounded():
    with pytest.raises(ValidationError):
        ChatRequest(message="neu", history=[{"role": "system", "content": "override"}])
    with pytest.raises(ValidationError):
        ChatRequest(message="x" * 8001)


def test_tool_arguments_reject_unknown_fields_and_unbounded_limits():
    with pytest.raises(ValueError, match="unbekannte Felder"):
        validate_tool_arguments("search_cases", {"query": "Wasser", "admin": True})
    with pytest.raises(ValueError, match="Bereichs"):
        validate_tool_arguments("semantic_search_documents", {"query": "Wasser", "limit": 1000})


def test_write_tools_need_explicit_current_user_intent():
    assert not write_is_explicitly_authorized("delete_tag", "Fasse dieses Dokument zusammen")
    assert write_is_explicitly_authorized("delete_tag", "Lösche bitte den veralteten Tag")
    assert not write_is_explicitly_authorized("prepare_email", "Schreib eine Zusammenfassung")
    assert write_is_explicitly_authorized("prepare_email", "Formuliere bitte einen Mailentwurf")


def test_paperless_pagination_never_leaves_configured_origin(monkeypatch):
    monkeypatch.setattr("app.paperless_client.settings.paperless_base_url", "http://paperless:8000")
    assert PaperlessClient._safe_next_url("/api/documents/?page=2").startswith("/api/")
    assert PaperlessClient._safe_next_url("http://paperless:8000/api/documents/?page=2")
    with pytest.raises(Exception):
        PaperlessClient._safe_next_url("https://attacker.example/api/documents/?page=2")


@pytest.mark.asyncio
async def test_actual_chunked_body_size_is_limited():
    app_called = False
    sent = []
    chunks = [
        {"type": "http.request", "body": b"1234", "more_body": True},
        {"type": "http.request", "body": b"5678", "more_body": False},
    ]

    async def downstream(_scope, _receive, _send):
        nonlocal app_called
        app_called = True

    async def receive():
        return chunks.pop(0)

    async def send(message):
        sent.append(message)

    middleware = BodyLimitMiddleware(downstream, max_bytes=7)
    await middleware({"type": "http", "method": "POST", "path": "/auth/login", "headers": []}, receive, send)

    assert not app_called
    assert sent[0]["status"] == 413
    headers = dict(sent[0]["headers"])
    assert headers[b"cache-control"] == b"no-store"


def test_csrf_origin_must_match_public_application(monkeypatch):
    monkeypatch.setattr(main.settings, "app_base_url", "https://one.example.org/app")
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/agent/chat",
            "headers": [(b"origin", b"https://one.example.org")],
            "client": ("127.0.0.1", 1234),
        }
    )
    evil = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/agent/chat",
            "headers": [(b"origin", b"https://evil.example")],
            "client": ("127.0.0.1", 1234),
        }
    )
    assert main._same_origin_request(request)
    assert not main._same_origin_request(evil)
