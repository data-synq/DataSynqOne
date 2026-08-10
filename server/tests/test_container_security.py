"""Static regression tests for reproducible and hardened container definitions."""

import importlib.util
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_application_dockerfiles_are_reproducible_and_non_root():
    backend = read("server/Dockerfile")
    frontend = read("src/Dockerfile")

    assert "FROM python:3.12-slim@sha256:" in backend
    assert "--require-hashes" in backend
    assert "USER 65532:65532" in backend
    assert "--no-proxy-headers" in backend

    assert "FROM node:22-alpine@sha256:" in frontend
    assert "FROM nginx:alpine@sha256:" in frontend
    assert "RUN npm ci" in frontend
    assert "USER 101:101" in frontend


def test_build_contexts_exclude_local_dependencies_and_secrets():
    backend_ignore = read("server/.dockerignore")
    frontend_ignore = read("src/.dockerignore")
    assert backend_ignore.startswith("**\n")
    assert "!requirements.txt" in backend_ignore
    assert frontend_ignore.startswith("**\n")
    assert "!package-lock.json" in frontend_ignore
    assert "!nginx.conf" in frontend_ignore
    assert "!public/**" in frontend_ignore


def test_python_locks_pin_versions_and_require_hashes():
    runtime = read("server/requirements.txt")
    development = read("server/requirements-dev.txt")
    assert "fastapi==" in runtime
    assert "--hash=sha256:" in runtime
    assert "pytest==" in development
    assert "uv==" in development
    assert "--hash=sha256:" in development


def test_production_env_template_contains_no_secret_values():
    backend_env = read("env/backend.prod.env.example")
    forbidden = (
        "OPENAI_API_KEY=",
        "PAPERLESS_API_TOKEN=",
        "DATABASE_URL=",
        "ADMIN_PASSWORD=",
        "SMTP_PASSWORD=",
        "MAIL_IMAP_PASSWORD=",
    )
    assert not any(name in backend_env for name in forbidden)


def test_production_compose_declares_hardening_for_every_service():
    config = yaml.safe_load(read("compose.prod.yml"))
    services = config["services"]
    assert set(services) == {
        "redis",
        "postgres",
        "vectordb",
        "migrate",
        "gotenberg",
        "tika",
        "paperless",
        "backend",
        "frontend",
    }
    for service in services.values():
        assert "ports" not in service
        assert service["read_only"] is True
        assert service["user"].split(":", 1)[0] not in {"0", "root"}
        assert "ALL" in service["cap_drop"]
        assert "no-new-privileges:true" in service["security_opt"]
        if service is not services["migrate"]:
            assert service["healthcheck"]
        assert service["mem_limit"]
        assert service["cpus"]
        assert service["pids_limit"]

    for name in ("postgres", "vectordb", "paperless", "migrate", "backend"):
        assert services[name]["group_add"] == [
            "${DATASYNQ_SECRETS_GID:?Set DATASYNQ_SECRETS_GID to the host secrets group}"
        ]
    assert services["backend"]["environment"]["ENVIRONMENT"] == "production"
    assert "/ready" in " ".join(services["backend"]["healthcheck"]["test"])


def test_rendered_compose_validator_rejects_mutable_images():
    spec = importlib.util.spec_from_file_location(
        "validate_prod_compose", ROOT / "scripts/validate_prod_compose.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    config = yaml.safe_load(read("compose.prod.yml"))
    config["services"]["backend"]["image"] = "ghcr.io/data-synq/backend:latest"
    errors = module.validate(config, check_secret_files=False)
    assert "backend: image must be pinned by sha256 digest" in errors


def test_rendered_compose_validator_rejects_missing_required_secret():
    spec = importlib.util.spec_from_file_location(
        "validate_prod_compose", ROOT / "scripts/validate_prod_compose.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    config = yaml.safe_load(read("compose.prod.yml"))
    config["secrets"].pop("mfa_encryption_key")
    errors = module.validate(config, check_secret_files=False)
    assert "production secret set does not match the required contract" in errors


def test_rendered_compose_validator_rejects_wrong_secret_target():
    spec = importlib.util.spec_from_file_location(
        "validate_prod_compose", ROOT / "scripts/validate_prod_compose.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    config = yaml.safe_load(read("compose.prod.yml"))
    runtime_mount = next(
        item
        for item in config["services"]["backend"]["secrets"]
        if item["source"] == "runtime_database_url"
    )
    runtime_mount["target"] = "runtime_database_url"
    errors = module.validate(config, check_secret_files=False)
    assert "backend: required secret mounts do not match contract" in errors


def test_rendered_compose_validator_rejects_unprotected_secret_files(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "validate_prod_compose", ROOT / "scripts/validate_prod_compose.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    config = yaml.safe_load(read("compose.prod.yml"))
    digest = "example.invalid/image@sha256:" + "a" * 64
    for service in config["services"].values():
        service["image"] = digest
    for name in ("postgres", "vectordb", "paperless", "migrate", "backend"):
        config["services"][name]["group_add"] = [str(os.getgid())]

    secret = tmp_path / "secret"
    secret.write_text("test-only", encoding="utf-8")
    secret.chmod(0o600)
    config["secrets"] = {"test": {"file": str(secret)}}

    errors = module.validate(config, check_secret_files=True)
    assert any(error.startswith("secret test:") for error in errors)
