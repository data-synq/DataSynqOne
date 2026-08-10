"""TOTP and recovery-code primitives; persistence and rate limits live in db.py."""

import hashlib
import hmac
import secrets
import time

import pyotp
from cryptography.fernet import Fernet, InvalidToken

from ..config import reveal_secret, settings

RECOVERY_CODE_COUNT = 10
TOTP_PERIOD_SECONDS = 30


class MfaKeyError(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = reveal_secret(settings.mfa_encryption_key)
    if not key:
        raise MfaKeyError("MFA encryption key is not configured")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise MfaKeyError("MFA encryption key is invalid") from exc


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="DataSynq One")


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode("ascii")).decode("ascii")


def decrypt_secret(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("ascii")
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise MfaKeyError("MFA secret cannot be decrypted") from exc


def matching_totp_step(secret: str, code: str, at_time: float | None = None) -> int | None:
    normalized = code.strip().replace(" ", "")
    if len(normalized) != 6 or not normalized.isdigit():
        return None
    current_step = int((time.time() if at_time is None else at_time) // TOTP_PERIOD_SECONDS)
    totp = pyotp.TOTP(secret, interval=TOTP_PERIOD_SECONDS)
    for step in (current_step, current_step - 1, current_step + 1):
        if hmac.compare_digest(totp.at(step * TOTP_PERIOD_SECONDS), normalized):
            return step
    return None


def generate_recovery_codes() -> list[tuple[str, str, str]]:
    result = []
    for _ in range(RECOVERY_CODE_COUNT):
        code_id = secrets.token_hex(4)
        secret = secrets.token_urlsafe(12)
        code = f"{code_id}.{secret}"
        result.append((code_id, code, hashlib.sha256(secret.encode("ascii")).hexdigest()))
    return result


def split_recovery_code(code: str) -> tuple[str, str] | None:
    try:
        code_id, secret = code.strip().split(".", 1)
    except ValueError:
        return None
    if len(code_id) != 8 or not secret:
        return None
    return code_id.lower(), hashlib.sha256(secret.encode("utf-8")).hexdigest()
