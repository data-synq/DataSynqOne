import re
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field

# Bewusst nicht pydantics EmailStr: das lehnt reservierte Domains wie .local, .lan
# oder .intern ab — also genau die, die eine selbst gehostete Installation intern
# verwendet. Beim Login waere das fatal, weil es ein bestehendes Konto aussperrt.
# Konten legt ohnehin nur ein Administrator von Hand an; hier geht es um Tippfehler,
# nicht um die Abwehr von Massenregistrierungen.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_email(value: str) -> str:
    value = value.strip().lower()
    if not _EMAIL_RE.match(value):
        raise ValueError("Das ist keine gültige E-Mail-Adresse.")
    return value


Email = Annotated[str, AfterValidator(_normalize_email)]


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []
    session_id: str | None = None


class LoginRequest(BaseModel):
    email: Email
    password: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


class UserCreateRequest(BaseModel):
    email: Email
    display_name: str = Field(min_length=1, max_length=120)
    role: str
    password: str


class UserUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    role: str | None = None
    is_active: bool | None = None


class PasswordResetRequest(BaseModel):
    password: str


class UserOut(BaseModel):
    """Ein Benutzer, wie ihn die Oberfläche sieht — ohne Hash und Fehlversuche."""

    id: str
    email: str
    display_name: str
    role: str
    role_label: str
    is_active: bool
    must_change_password: bool
    last_login_at: datetime | None = None
    created_at: datetime


class MeOut(UserOut):
    """Das eigene Profil, zusätzlich mit der aufgelösten Rechteliste für die UI."""

    permissions: list[str]
