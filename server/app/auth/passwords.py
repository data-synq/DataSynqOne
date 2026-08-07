"""Passwort-Hashing über Argon2id.

Argon2 direkt statt über passlib: passlib ist seit Jahren unbewegt und stolpert
über neuere bcrypt-Versionen. argon2-cffi bringt sinnvolle Parameter selbst mit.
"""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError, VerificationError

MIN_PASSWORD_LENGTH = 12

_hasher = PasswordHasher()

# Gegen diesen Hash wird verifiziert, wenn es die E-Mail gar nicht gibt. Ohne das
# antwortet der Login bei unbekannten Konten messbar schneller als bei falschem
# Passwort, und genau daraus liest man ab, welche Konten existieren.
_DUMMY_HASH = _hasher.hash("dummy-password-for-constant-time-login")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    if password_hash is None:
        try:
            _hasher.verify(_DUMMY_HASH, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            pass
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def validate_password(password: str) -> None:
    """Wirft ValueError mit einer Meldung, die direkt in die Oberfläche darf."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Das Passwort muss mindestens {MIN_PASSWORD_LENGTH} Zeichen lang sein.")
