"""FastAPI wiring smoke tests without database or external services."""

import asyncio

import httpx
from asgi_lifespan import LifespanManager

from app import main


async def test_health_runs_the_complete_lifespan_without_external_services(monkeypatch):
    calls: list[str] = []

    def record(name: str):
        async def fake(*args, **kwargs):
            calls.append(name)

        return fake

    async def wait_forever():
        await asyncio.Event().wait()

    def scheduler(name: str):
        calls.append(name)
        return wait_forever()

    monkeypatch.setattr(main, "init_db", record("init_db"))
    monkeypatch.setattr(main, "ensure_bootstrap_admin", record("bootstrap"))
    monkeypatch.setattr(main, "seed_tags", record("seed_tags"))
    monkeypatch.setattr(main, "seed_mail_receiving", record("seed_mail"))
    monkeypatch.setattr(main, "close_db", record("close_db"))
    monkeypatch.setattr(main.paperless_client, "close", record("close_paperless"))
    monkeypatch.setattr(main.digest, "scheduler", lambda: scheduler("digest_scheduler"))
    monkeypatch.setattr(main.intake, "scheduler", lambda: scheduler("intake_scheduler"))

    async with LifespanManager(main.app):
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}
            assert response.headers["cache-control"] == "no-store"
            assert response.headers["x-content-type-options"] == "nosniff"
            assert response.headers["x-frame-options"] == "DENY"
            assert calls[:4] == ["init_db", "bootstrap", "seed_tags", "seed_mail"]

    assert "digest_scheduler" in calls
    assert "intake_scheduler" in calls
    assert calls[-2:] == ["close_db", "close_paperless"]


async def test_protected_route_rejects_anonymous_requests(monkeypatch):
    async def noop(*args, **kwargs):
        return None

    async def scheduler():
        await asyncio.Event().wait()

    for name in (
        "init_db",
        "ensure_bootstrap_admin",
        "seed_tags",
        "seed_mail_receiving",
        "close_db",
    ):
        monkeypatch.setattr(main, name, noop)
    monkeypatch.setattr(main.paperless_client, "close", noop)
    monkeypatch.setattr(main.security_audit, "record", noop)
    monkeypatch.setattr(main.security_audit, "safe_record", noop)
    monkeypatch.setattr(main.digest, "scheduler", scheduler)
    monkeypatch.setattr(main.intake, "scheduler", scheduler)

    async with LifespanManager(main.app):
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/documents/")

    assert response.status_code == 401
    assert response.json() == {"detail": "Nicht angemeldet"}


def test_expected_api_routes_are_registered():
    paths = set(main.app.openapi()["paths"])
    assert {
        "/live",
        "/ready",
        "/auth/login",
        "/auth/password",
        "/auth/mfa/setup",
        "/auth/mfa/verify",
        "/auth/sessions",
        "/users/object-options",
        "/users/{user_id}/object-scope",
        "/users/",
        "/agent/chat",
        "/documents/{document_id}/file",
        "/mail/drafts/{draft_id}/send",
        "/audit/events",
    } <= paths
