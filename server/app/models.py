import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from .auth.object_access import normalize_object_code

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
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=8000)
    session_id: str | None = None


class LoginRequest(BaseModel):
    email: Email
    password: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


class ObjectAccessRequest(BaseModel):
    mode: Literal["all", "restricted"]
    object_codes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_scope(self):
        try:
            normalized = sorted({normalize_object_code(code) for code in self.object_codes})
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        if self.mode == "all" and normalized:
            raise ValueError("Bei globalem Zugriff dürfen keine Objektcodes gesetzt sein.")
        if self.mode == "restricted" and not normalized:
            raise ValueError("Eingeschränkter Zugriff benötigt mindestens einen Objektcode.")
        self.object_codes = normalized
        return self


class MfaCodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=100)


class MfaSetupOut(BaseModel):
    secret: str
    provisioning_uri: str


class AuthSessionOut(BaseModel):
    id: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    absolute_expires_at: datetime
    user_agent: str | None
    current: bool


class UserCreateRequest(BaseModel):
    email: Email
    display_name: str = Field(min_length=1, max_length=120)
    role: str
    object_access: ObjectAccessRequest


class UserUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    role: str | None = None
    is_active: bool | None = None


class ObjectOption(BaseModel):
    code: str
    label: str


class InvitationRedeemRequest(BaseModel):
    password: str


class InvitationInfo(BaseModel):
    """Was die öffentliche Einladungsseite erfährt — Name und Zweck, sonst nichts."""

    display_name: str
    purpose: str


class EmailDraft(BaseModel):
    id: str
    recipient: str
    subject: str
    body: str
    document_id: int | None = None
    created_at: datetime
    sent_at: datetime | None = None


class EmailDraftSendRequest(BaseModel):
    """Betreff und Text dürfen korrigiert werden, der Empfänger nicht.

    Die Adresse stammt aus dem gespeicherten Entwurf — sonst wäre der Endpunkt ein
    Weg, über den Mailserver der Installation an beliebige Adressen zu schreiben.
    """

    recipient: Email
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=100000)


class CaseNoteRequest(BaseModel):
    body: str = Field(min_length=1, max_length=16000)


class CaseLinkRequest(BaseModel):
    """dependent_tracking_id baut auf prerequisite_tracking_id auf."""

    dependent_tracking_id: str
    prerequisite_tracking_id: str


class CaseDocumentAttachRequest(BaseModel):
    paperless_ids: list[int] = Field(min_length=1, max_length=200)


class UserOut(BaseModel):
    """Ein Benutzer, wie ihn die Oberfläche sieht — ohne Hash und Fehlversuche."""

    id: str
    email: str
    display_name: str
    role: str
    role_label: str
    is_active: bool
    must_change_password: bool
    mfa_enabled: bool
    object_access_mode: str
    object_codes: list[str]
    last_login_at: datetime | None = None
    created_at: datetime


class MeOut(UserOut):
    """Das eigene Profil, zusätzlich mit der aufgelösten Rechteliste für die UI."""

    permissions: list[str]
    auth_stage: str


class MfaConfirmOut(BaseModel):
    user: MeOut
    recovery_codes: list[str]


class InvitationResult(BaseModel):
    """Antwort auf 'Konto angelegt' und 'Einladung erneut senden'.

    `invitation_link` steht nur drin, wenn die Mail *nicht* rausging — dann ist er
    der einzige Weg, die Person an Bord zu holen. Ging sie raus, hat der Link in
    einer HTTP-Antwort nichts zu suchen.
    """

    user: UserOut
    mail_sent: bool
    invitation_link: str | None = None
