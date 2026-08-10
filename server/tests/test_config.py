"""Deployment configuration must fail closed without exposing secret values."""

import pytest
from pydantic import SecretStr, ValidationError

from app import db, openai_client
from app.auth import bootstrap
from app.config import Settings, load_settings, reveal_secret, settings


def production_settings(**overrides) -> Settings:
    values = {
        "environment": "production",
        "paperless_api_token": "paperless-token",
        "openai_api_key": "openai-token",
        "database_url": "postgresql://datasynq_runtime:a-long-random-database-password@vectordb:5432/datasynq",
        "app_base_url": "https://one.example.org",
        "cors_origins": ["https://one.example.org"],
        "session_cookie_secure": True,
        "session_cookie_name": "__Host-dsq_session",
        "mfa_encryption_key": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
        "trusted_proxy_cidrs": ["172.30.0.0/24"],
        "admin_client_cidrs": ["10.20.0.0/24"],
        "mail_intake_enabled": False,
    }
    values.update(overrides)
    return Settings(_secrets_dir=None, **values)


def test_valid_production_configuration_is_accepted():
    configured = production_settings()
    assert configured.environment == "production"
    assert configured.database_dsn.startswith("postgresql://datasynq_runtime:")


def test_production_allows_same_origin_without_cors():
    assert production_settings(cors_origins=[]).cors_origins == []


def test_production_requires_narrow_trusted_proxy_networks():
    with pytest.raises(ValidationError, match="TRUSTED_PROXY_CIDRS"):
        production_settings(trusted_proxy_cidrs=[])
    with pytest.raises(ValidationError, match="gesamte Internet"):
        production_settings(trusted_proxy_cidrs=["0.0.0.0/0"])


def test_production_mail_intake_requires_prevalidated_ingress():
    with pytest.raises(ValidationError, match="signierten Ingress-Manifest"):
        production_settings(mail_intake_enabled=True)
    with pytest.raises(ValidationError, match="signierten Ingress-Manifest"):
        production_settings(mail_intake_enabled=True, mail_ingress_prevalidated=True)


def test_absolute_session_lifetime_cannot_be_shorter_than_idle_lifetime():
    with pytest.raises(ValidationError, match="SESSION_ABSOLUTE_TTL_HOURS"):
        Settings(
            environment="test",
            session_ttl_hours=12,
            session_absolute_ttl_hours=6,
            _secrets_dir=None,
        )


def test_environment_is_required_and_restricted(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    with pytest.raises(ValidationError, match="environment"):
        Settings(_secrets_dir=None)

    with pytest.raises(ValidationError, match="environment"):
        Settings(environment="prod", _secrets_dir=None)


@pytest.mark.parametrize("missing", ["paperless_api_token", "openai_api_key"])
def test_production_requires_external_service_tokens(missing):
    with pytest.raises(ValidationError, match=missing.upper()):
        production_settings(**{missing: ""})


def test_production_requires_valid_mfa_encryption_key():
    with pytest.raises(ValidationError, match="MFA_ENCRYPTION_KEY"):
        production_settings(mfa_encryption_key="not-a-fernet-key")


@pytest.mark.parametrize("field", ["paperless_api_token", "openai_api_key"])
def test_production_rejects_placeholder_tokens(field):
    with pytest.raises(ValidationError, match="Platzhalter"):
        production_settings(**{field: "change-me"})


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"app_base_url": "http://one.example.org"}, "öffentliche HTTPS-URL"),
        ({"app_base_url": "https://localhost"}, "öffentliche HTTPS-URL"),
        ({"app_base_url": "https://10.0.0.1"}, "öffentliche HTTPS-URL"),
        ({"cors_origins": ["*"]}, "Wildcard-Origin"),
        ({"cors_origins": ["https://one.example.org/path"]}, "ohne Pfad"),
        ({"session_cookie_secure": False}, "SESSION_COOKIE_SECURE"),
        ({"session_cookie_name": "dsq_session"}, "__Host-"),
        ({"database_url": "postgresql://brain:brain@vectordb:5432/brain"}, "Datenbankpasswort"),
    ],
)
def test_production_rejects_unsafe_web_and_database_settings(override, message):
    with pytest.raises(ValidationError, match=message):
        production_settings(**override)


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"session_cookie_name": "bad name"}, "SESSION_COOKIE_NAME"),
        ({"smtp_from_email": "not-an-email"}, "SMTP_FROM_EMAIL"),
        ({"smtp_reply_to": "victim@example.org\nBcc: attacker@example.org"}, "SMTP_REPLY_TO"),
        ({"smtp_from_name": "DataSynq\r\nBcc: attacker@example.org"}, "SMTP_FROM_NAME"),
    ],
)
def test_header_and_cookie_values_are_validated(override, message):
    with pytest.raises(ValidationError, match=message):
        Settings(environment="test", _secrets_dir=None, **override)


def test_disabled_smtp_ignores_leftover_credentials():
    configured = Settings(environment="test", smtp_password="leftover", _secrets_dir=None)
    assert not configured.mail_enabled


def test_production_rejects_unencrypted_external_mail_transport():
    with pytest.raises(ValidationError, match="SMTP_SECURITY=none"):
        production_settings(
            smtp_host="smtp.example.org",
            smtp_from_email="one@example.org",
            smtp_security="none",
        )


def test_secret_values_are_masked_in_validation_errors():
    secrets = {
        "paperless_api_token": "paperless-value-must-never-appear",
        "openai_api_key": "openai-value-must-never-appear",
        "database_url": "postgresql://datasynq_runtime:database-value-must-never-appear@vectordb:5432/datasynq",
        "admin_password": "admin-value-must-never-appear",
    }
    with pytest.raises(ValidationError) as exc_info:
        production_settings(
            admin_email="admin@example.org",
            session_cookie_secure=False,
            **secrets,
        )

    error = str(exc_info.value)
    assert all(
        marker not in error
        for marker in (
            "paperless-value-must-never-appear",
            "openai-value-must-never-appear",
            "database-value-must-never-appear",
            "admin-value-must-never-appear",
        )
    )

    isolated_secret = "short-error-secret-must-not-leak"
    with pytest.raises(ValidationError) as isolated_error:
        Settings(
            environment="test",
            smtp_host="smtp.example.org",
            smtp_from_email="one@example.org",
            smtp_password=isolated_secret,
            _secrets_dir=None,
        )
    assert isolated_secret not in str(isolated_error.value)


def test_secret_files_are_loaded_and_environment_wins(tmp_path, monkeypatch):
    (tmp_path / "openai_api_key").write_text("file-secret\n", encoding="utf-8")
    configured = Settings(environment="test", _secrets_dir=tmp_path)
    assert reveal_secret(configured.openai_api_key) == "file-secret"

    monkeypatch.setenv("OPENAI_API_KEY", "environment-secret")
    configured = Settings(environment="test", _secrets_dir=tmp_path)
    assert reveal_secret(configured.openai_api_key) == "environment-secret"


def test_configured_secret_directory_is_used_by_application_loader(tmp_path, monkeypatch):
    (tmp_path / "paperless_api_token").write_text("mounted-secret\n", encoding="utf-8")
    monkeypatch.setenv("DATASYNQ_SECRETS_DIR", str(tmp_path))
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.delenv("PAPERLESS_API_TOKEN", raising=False)

    configured = load_settings()

    assert reveal_secret(configured.paperless_api_token) == "mounted-secret"


def test_secret_repr_does_not_disclose_value():
    configured = Settings(environment="test", openai_api_key="hidden", _secrets_dir=None)
    assert "hidden" not in repr(configured)
    assert isinstance(configured.openai_api_key, SecretStr)


def test_openai_client_does_not_bypass_settings_with_ambient_environment(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", SecretStr(""))
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-key")
    openai_client._get_transport.cache_clear()

    with pytest.raises(RuntimeError, match="nicht konfiguriert"):
        openai_client._get_transport()

    openai_client._get_transport.cache_clear()


async def test_empty_production_database_requires_bootstrap_credentials(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "admin_email", "")
    monkeypatch.setattr(settings, "admin_password", SecretStr(""))
    monkeypatch.setattr(db, "count_users", lambda: _async_value(0))

    with pytest.raises(RuntimeError, match="Produktions-Bootstrap"):
        await bootstrap.ensure_bootstrap_admin()


@pytest.mark.parametrize(
    ("email", "password", "message"),
    [
        ("admin@example.org", "", "Produktions-Bootstrap"),
        ("not-an-email", "a-secure-password", "ADMIN_EMAIL"),
        ("admin@example.org", "short", "Passwortanforderungen"),
    ],
)
async def test_new_production_bootstrap_validates_credentials(monkeypatch, email, password, message):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "admin_email", email)
    monkeypatch.setattr(settings, "admin_password", SecretStr(password))
    monkeypatch.setattr(db, "count_users", lambda: _async_value(0))

    with pytest.raises(RuntimeError, match=message):
        await bootstrap.ensure_bootstrap_admin()


async def test_existing_production_user_does_not_require_bootstrap_secret(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "admin_email", "stale-invalid-value")
    monkeypatch.setattr(settings, "admin_password", SecretStr("short"))
    monkeypatch.setattr(db, "count_users", lambda: _async_value(1))

    await bootstrap.ensure_bootstrap_admin()


async def _async_value(value):
    return value
