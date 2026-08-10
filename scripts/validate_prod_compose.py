#!/usr/bin/env python3
"""Validate invariants on the fully rendered production Compose config."""

import json
import re
import stat
import sys
from pathlib import Path

EXPECTED_SERVICES = {
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
EXPECTED_NETWORKS = {
    "redis": {"paperless_internal"},
    "postgres": {"paperless_internal"},
    "vectordb": {"vector_internal"},
    "migrate": {"vector_internal"},
    "gotenberg": {"paperless_internal"},
    "tika": {"paperless_internal"},
    "paperless": {"admin", "app_internal", "paperless_egress", "paperless_internal"},
    "backend": {"app_internal", "caddy", "vector_internal"},
    "frontend": {"caddy"},
}
EXPECTED_SECRETS = {
    "paperless_db_password",
    "paperless_secret_key",
    "paperless_admin_password",
    "vectordb_password",
    "paperless_api_token",
    "openai_api_key",
    "database_url",
    "runtime_database_url",
    "admin_password",
    "smtp_password",
    "mail_imap_password",
    "mfa_encryption_key",
}
EXPECTED_SERVICE_SECRETS = {
    "postgres": {("paperless_db_password", "paperless_db_password")},
    "vectordb": {("vectordb_password", "vectordb_password")},
    "paperless": {
        ("paperless_db_password", "paperless_db_password"),
        ("paperless_secret_key", "paperless_secret_key"),
        ("paperless_admin_password", "paperless_admin_password"),
    },
    "backend": {
        ("paperless_api_token", "paperless_api_token"),
        ("openai_api_key", "openai_api_key"),
        ("runtime_database_url", "database_url"),
        ("admin_password", "admin_password"),
        ("smtp_password", "smtp_password"),
        ("mail_imap_password", "mail_imap_password"),
        ("mfa_encryption_key", "mfa_encryption_key"),
    },
    "migrate": {
        ("database_url", "database_url"),
        ("runtime_database_url", "runtime_database_url"),
    },
}
_DIGEST_IMAGE = re.compile(r"^.+@sha256:[0-9a-f]{64}$")


def validate(config: dict, *, check_secret_files: bool = False) -> list[str]:
    errors: list[str] = []
    services = config.get("services", {})
    if set(services) != EXPECTED_SERVICES:
        errors.append(f"unexpected service set: {sorted(services)}")

    for name, service in services.items():
        image = service.get("image", "")
        if not _DIGEST_IMAGE.fullmatch(image):
            errors.append(f"{name}: image must be pinned by sha256 digest")
        if service.get("ports"):
            errors.append(f"{name}: production services must not publish host ports")
        if service.get("read_only") is not True:
            errors.append(f"{name}: root filesystem is not read-only")
        if str(service.get("user", "")).split(":", 1)[0] in {"", "0", "root"}:
            errors.append(f"{name}: service must run as an explicit non-root user")
        if "ALL" not in service.get("cap_drop", []):
            errors.append(f"{name}: capabilities are not dropped")
        if "no-new-privileges:true" not in service.get("security_opt", []):
            errors.append(f"{name}: no-new-privileges is missing")
        if name != "migrate" and not service.get("healthcheck"):
            errors.append(f"{name}: healthcheck is missing")
        if not service.get("mem_limit") or not service.get("cpus") or not service.get("pids_limit"):
            errors.append(f"{name}: resource limits are incomplete")
        logging = service.get("logging", {})
        if logging.get("driver") != "json-file" or not logging.get("options", {}).get("max-size"):
            errors.append(f"{name}: bounded json-file logging is missing")

        networks = set(service.get("networks", {}))
        expected_networks = EXPECTED_NETWORKS.get(name)
        if expected_networks is not None and networks != expected_networks:
            errors.append(f"{name}: unexpected networks {sorted(networks)}")

    networks = config.get("networks", {})
    for name in ("app_internal", "paperless_internal", "vector_internal"):
        if networks.get(name, {}).get("internal") is not True:
            errors.append(f"{name}: network must be internal")

    if set(config.get("secrets", {})) != EXPECTED_SECRETS:
        errors.append("production secret set does not match the required contract")
    for service_name, expected in EXPECTED_SERVICE_SECRETS.items():
        declared = {
            (secret, secret)
            if isinstance(secret, str)
            else (secret.get("source"), secret.get("target", secret.get("source")))
            for secret in services.get(service_name, {}).get("secrets", [])
        }
        if declared != expected:
            errors.append(f"{service_name}: required secret mounts do not match contract")

    if services.get("backend", {}).get("environment", {}).get("ENVIRONMENT") != "production":
        errors.append("backend: ENVIRONMENT must be forced to production")
    backend_health = " ".join(
        str(part) for part in services.get("backend", {}).get("healthcheck", {}).get("test", [])
    )
    if "/ready" not in backend_health:
        errors.append("backend: healthcheck must use /ready")

    secret_readers = ("postgres", "vectordb", "paperless", "migrate", "backend")
    secret_groups = {
        str(group)
        for name in secret_readers
        for group in services.get(name, {}).get("group_add", [])
    }
    if len(secret_groups) != 1:
        errors.append("secret-reading services must share exactly one supplemental group")
    elif check_secret_files:
        expected_gid = int(next(iter(secret_groups)))
        for name, secret in config.get("secrets", {}).items():
            path = Path(secret.get("file", ""))
            try:
                metadata = path.stat()
            except OSError as exc:
                errors.append(f"secret {name}: cannot stat {path}: {exc.strerror}")
                continue
            mode = stat.S_IMODE(metadata.st_mode)
            if not path.is_file():
                errors.append(f"secret {name}: {path} is not a regular file")
            if metadata.st_uid != 0 or metadata.st_gid != expected_gid:
                errors.append(
                    f"secret {name}: owner must be root:{expected_gid}, "
                    f"got {metadata.st_uid}:{metadata.st_gid}"
                )
            if mode & 0o040 == 0 or mode & 0o027:
                errors.append(
                    f"secret {name}: mode must grant group-read only (recommended 0440), got {mode:04o}"
                )

    return errors


def main() -> int:
    try:
        config = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"invalid Compose JSON: {exc}", file=sys.stderr)
        return 2

    errors = validate(config, check_secret_files=True)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("production Compose security invariants and secret files validated")
    print(
        "WARNING: external-network membership and destination-level egress still require "
        "independent host/Caddy/VPN firewall verification.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
