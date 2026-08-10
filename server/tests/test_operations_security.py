import re
from pathlib import Path

import pytest
from starlette.requests import Request

from app import audit, db
from app import main


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_schema_migration_is_versioned_locked_and_append_only():
    source = read("server/app/db.py")
    assert db.SCHEMA_VERSION == 1
    assert len(db.schema_checksum()) == 64
    assert "pg_advisory_lock" in source
    assert "schema_migrations" in source
    assert "MIGRATION_001_BEGIN" in source
    assert "audit_events_append_only" in source
    assert "audit_events_no_truncate" in source
    assert "BEFORE UPDATE OR DELETE ON audit_events" in source
    assert "SET ROLE datasynq_runtime" in source
    assert "REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON audit_events" in source
    assert "p_previous_hash" not in source
    assert "p_event_hash" not in source
    assert "digest(v_previous_hash" in source


def test_production_healthcheck_uses_readiness_and_shutdown_is_bounded():
    compose = read("compose.prod.yml")
    dockerfile = read("server/Dockerfile")
    assert "127.0.0.1:8000/ready" in compose
    assert "--timeout-graceful-shutdown" in dockerfile
    assert '"25"' in dockerfile


def test_backup_scripts_cover_both_databases_media_and_checksums():
    backup = read("scripts/backup.sh")
    restore = read("scripts/restore-check.sh")
    assert backup.count("pg_dump --format=custom") == 2
    assert "PAPERLESS_QUIESCED" in backup
    assert "flock --nonblock" in backup
    assert 'mkdir "${destination}"' in backup
    assert "DATABASE_URL" not in backup
    assert "PGPASSFILE" in backup
    assert "paperless-media.tar" in backup
    assert "sha256sum" in backup
    assert "sha256sum --check" in restore
    assert restore.count("pg_restore --list") == 2


def test_workflows_pin_actions_and_expose_no_cross_repository_secret():
    workflows = list((ROOT / ".github/workflows").glob("*.yml"))
    assert workflows
    for path in workflows:
        source = path.read_text(encoding="utf-8")
        for target in re.findall(r"uses:\s*[^@\s]+@([^\s]+)", source):
            assert re.fullmatch(r"[0-9a-f]{40}", target), (path, target)
        assert "INFRA_BUMP_TOKEN" not in source
        assert "permissions: write-all" not in source
    release = read(".github/workflows/build-and-push.yml")
    assert "permissions: {}" in release
    assert "provenance: mode=max" in release
    assert "sbom: true" in release
    assert "persist-credentials: false" in release
    assert "git push origin HEAD:main" not in release
    assert release.index("datasynqone-backend:security-scan") < release.index("push: true")


def test_normal_mail_logs_do_not_include_subject_or_recipient_values():
    source = read("server/app/mail/client.py")
    logging_calls = "\n".join(
        line for line in source.splitlines() if "logger." in line or line.strip().startswith('"Mail')
    )
    assert "subject" not in logging_calls
    assert "join(recipients)" not in source


@pytest.mark.asyncio
async def test_audit_metadata_is_allowlisted_and_redacted(monkeypatch):
    captured = {}

    async def append(**kwargs):
        captured.update(kwargs)
        return kwargs

    monkeypatch.setattr(db, "append_audit_event", append)
    await audit.record(
        "auth.login",
        "denied",
        metadata={"method": "POST", "route": "/auth/login", "status_code": 401},
    )
    assert captured["metadata"] == {
        "method": "POST",
        "route": "/auth/login",
        "status_code": 401,
    }
    with pytest.raises(ValueError, match="Nicht erlaubte"):
        await audit.record("auth.login", "failure", metadata={"password": "secret"})


def test_unresolved_invitation_route_never_audits_token():
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/auth/invitation/super-secret-token",
            "raw_path": b"/auth/invitation/super-secret-token",
            "query_string": b"",
            "headers": [],
            "scheme": "https",
            "server": ("example.test", 443),
            "client": ("127.0.0.1", 1234),
        }
    )
    assert main._audit_route(request) == "/auth/invitation/{token}"


@pytest.mark.asyncio
async def test_readiness_requires_database_and_paperless(monkeypatch):
    async def available():
        return True

    async def unavailable():
        return False

    monkeypatch.setattr(main, "_runtime_ready", True)
    monkeypatch.setattr(main, "_supervisor_tasks", [])
    monkeypatch.setattr(main.db, "database_ready", available)
    monkeypatch.setattr(main.paperless_client, "ready", available)
    assert (await main.ready())["status"] == "ready"

    monkeypatch.setattr(main.paperless_client, "ready", unavailable)
    assert (await main.ready()).status_code == 503
