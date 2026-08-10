from datetime import datetime, timezone

import pytest
import pyotp
from argon2 import PasswordHasher
from cryptography.fernet import Fernet
from fastapi import HTTPException
from starlette.requests import Request
from pydantic import SecretStr

from app import db
from app.auth import AuthStage, Permission, Principal, Role
from app.auth import dependencies, mfa, sessions
from app.auth.passwords import verify_password_and_rehash
from app.routers import auth as auth_router
from app.routers.auth import me_payload


def principal(stage: AuthStage) -> Principal:
    return Principal(
        user_id="00000000-0000-0000-0000-000000000001",
        email="admin@example.org",
        display_name="Admin",
        role=Role.ADMIN,
        auth_stage=stage,
        permissions=frozenset(Permission),
    )


async def test_password_change_stage_cannot_become_current_principal():
    with pytest.raises(HTTPException) as exc:
        await dependencies.current_principal(principal(AuthStage.PASSWORD_CHANGE))

    assert exc.value.status_code == 428
    assert exc.value.detail["code"] == "password_change_required"


async def test_ready_stage_becomes_current_principal():
    expected = principal(AuthStage.READY)
    assert await dependencies.current_principal(expected) is expected


@pytest.mark.parametrize(
    ("stage", "code"),
    [
        (AuthStage.MFA_SETUP, "mfa_setup_required"),
        (AuthStage.MFA_CHALLENGE, "mfa_challenge_required"),
    ],
)
async def test_mfa_stages_cannot_access_application_routes(stage, code):
    with pytest.raises(HTTPException) as exc:
        await dependencies.current_principal(principal(stage))

    assert exc.value.status_code == 428
    assert exc.value.detail["code"] == code


async def test_password_change_principal_has_no_permissions(monkeypatch):
    async def no_scope(_user_id: str):
        return None

    monkeypatch.setattr(sessions.db, "get_object_scope", no_scope)
    result = await sessions.principal_from_user(
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "email": "admin@example.org",
            "display_name": "Admin",
            "role": "admin",
            "must_change_password": True,
        }
    )

    assert result.auth_stage is AuthStage.PASSWORD_CHANGE
    assert result.permissions == frozenset()


@pytest.mark.parametrize(
    ("user", "expected"),
    [
        (
            {"role": "admin", "must_change_password": False, "mfa_enabled_at": None},
            AuthStage.MFA_SETUP,
        ),
        (
            {
                "role": "admin",
                "must_change_password": False,
                "mfa_enabled_at": datetime.now(timezone.utc),
            },
            AuthStage.MFA_CHALLENGE,
        ),
        (
            {"role": "viewer", "must_change_password": False, "mfa_enabled_at": None},
            AuthStage.READY,
        ),
    ],
)
async def test_principal_auth_stage_is_derived_server_side(monkeypatch, user, expected):
    async def no_scope(_user_id: str):
        return None

    monkeypatch.setattr(sessions.db, "get_object_scope", no_scope)
    user.update(
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "email": "admin@example.org",
            "display_name": "Admin",
        }
    )

    result = await sessions.principal_from_user(user)

    assert result.auth_stage is expected
    assert bool(result.permissions) is (expected is AuthStage.READY)


def test_me_payload_exposes_restricted_auth_stage_without_permissions():
    result = me_payload(
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "email": "admin@example.org",
            "display_name": "Admin",
            "role": "admin",
            "is_active": True,
            "must_change_password": True,
            "last_login_at": None,
            "created_at": datetime.now(timezone.utc),
        }
    )

    assert result.auth_stage == AuthStage.PASSWORD_CHANGE
    assert result.permissions == []


def test_successful_password_verification_upgrades_old_argon2_parameters():
    old_hash = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1).hash(
        "a sufficiently long password"
    )

    valid, replacement = verify_password_and_rehash(
        old_hash, "a sufficiently long password"
    )

    assert valid
    assert replacement is not None


def test_failed_password_verification_never_returns_replacement_hash():
    old_hash = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1).hash(
        "a sufficiently long password"
    )

    valid, replacement = verify_password_and_rehash(old_hash, "wrong password")

    assert not valid
    assert replacement is None


def test_totp_secret_is_encrypted_and_valid_with_clock_tolerance(monkeypatch):
    key = Fernet.generate_key()
    monkeypatch.setattr(mfa.settings, "mfa_encryption_key", SecretStr(key.decode("ascii")))
    secret = mfa.generate_totp_secret()
    ciphertext = mfa.encrypt_secret(secret)
    at_time = 1_700_000_000
    code = pyotp.TOTP(secret).at(at_time - mfa.TOTP_PERIOD_SECONDS)

    assert secret not in ciphertext
    assert mfa.decrypt_secret(ciphertext) == secret
    assert mfa.matching_totp_step(secret, code, at_time) == (
        at_time // mfa.TOTP_PERIOD_SECONDS - 1
    )


def test_recovery_codes_are_unique_and_only_the_secret_hash_is_persisted():
    generated = mfa.generate_recovery_codes()

    assert len(generated) == mfa.RECOVERY_CODE_COUNT
    assert len({code for _code_id, code, _secret_hash in generated}) == len(generated)
    for code_id, code, secret_hash in generated:
        assert mfa.split_recovery_code(code) == (code_id, secret_hash)
        assert code not in secret_hash


async def test_session_touch_is_bounded_by_absolute_expiry(monkeypatch):
    queries: list[str] = []

    class Pool:
        async def fetchrow(self, query, *_args):
            queries.append(query)
            return None

    async def pool():
        return Pool()

    monkeypatch.setattr(db, "get_pool", pool)
    await db.touch_auth_session("hash", 12)

    assert "LEAST" in queries[0]
    assert "s.absolute_expires_at > now()" in queries[0]


async def test_mfa_setup_returns_an_encrypted_pending_secret(monkeypatch):
    key = Fernet.generate_key()
    stored: list[str] = []

    async def no_entry(_user_id: str):
        return None

    async def save(_user_id: str, ciphertext: str):
        stored.append(ciphertext)
        return True

    monkeypatch.setattr(mfa.settings, "mfa_encryption_key", SecretStr(key.decode("ascii")))
    monkeypatch.setattr(auth_router.db, "get_mfa", no_entry)
    monkeypatch.setattr(auth_router.db, "save_pending_mfa", save)
    setup_principal = principal(AuthStage.MFA_SETUP)

    result = await auth_router.setup_mfa(setup_principal)

    assert result.secret not in stored[0]
    assert mfa.decrypt_secret(stored[0]) == result.secret
    assert result.provisioning_uri.startswith("otpauth://totp/")


async def test_password_change_revokes_and_rotates_the_current_session(monkeypatch):
    old_password = "old-password-long-enough"
    calls: list[tuple] = []
    user = {
        "id": "00000000-0000-0000-0000-000000000001",
        "email": "viewer@example.org",
        "display_name": "Viewer",
        "role": "viewer",
        "is_active": True,
        "must_change_password": False,
        "mfa_enabled_at": None,
        "last_login_at": None,
        "created_at": datetime.now(timezone.utc),
    }

    async def password_hash(_user_id: str):
        return auth_router.hash_password(old_password)

    async def set_password(*args, **kwargs):
        calls.append(("set", args, kwargs))

    async def revoke_all(*args, **kwargs):
        calls.append(("revoke", args, kwargs))

    async def issue(*args, **kwargs):
        calls.append(("issue", args, kwargs))
        return "rotated-token"

    async def get_user(_user_id: str):
        return user

    monkeypatch.setattr(auth_router.db, "get_password_hash", password_hash)
    monkeypatch.setattr(auth_router.db, "set_password", set_password)
    monkeypatch.setattr(auth_router.db, "get_user_by_id", get_user)
    monkeypatch.setattr(auth_router.auth_sessions, "revoke_all", revoke_all)
    monkeypatch.setattr(auth_router.auth_sessions, "issue", issue)
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/auth/password",
            "headers": [(b"cookie", b"dsq_session=old-token"), (b"user-agent", b"test")],
        }
    )
    response = auth_router.Response()

    result = await auth_router.change_password(
        auth_router.PasswordChangeRequest(
            current_password=old_password,
            new_password="new-password-long-enough",
        ),
        principal(AuthStage.PASSWORD_CHANGE),
        request,
        response,
    )

    revoke = next(call for call in calls if call[0] == "revoke")
    assert revoke[2] == {}
    assert "rotated-token" in response.headers["set-cookie"]
    assert result.auth_stage == AuthStage.READY


async def test_forced_password_change_rejects_the_same_password():
    with pytest.raises(HTTPException) as exc:
        await auth_router.change_password(
            auth_router.PasswordChangeRequest(
                current_password="same-password-long-enough",
                new_password="same-password-long-enough",
            ),
            principal(AuthStage.PASSWORD_CHANGE),
            Request(
                {
                    "type": "http",
                    "method": "POST",
                    "path": "/auth/password",
                    "headers": [],
                }
            ),
            auth_router.Response(),
        )

    assert exc.value.status_code == 400
    assert "unterscheiden" in exc.value.detail
