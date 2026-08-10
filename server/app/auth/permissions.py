"""Rollen, Rechte und der Principal — die einzige Wahrheit über 'wer darf was'.

Alles andere (Router-Dependencies, Werkzeugfilter des Agenten, die Oberfläche)
leitet sich aus ROLE_PERMISSIONS ab. Wer ein Recht ändern will, ändert es hier.
"""

from dataclasses import dataclass, field
from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


class AuthStage(StrEnum):
    PASSWORD_CHANGE = "password_change"
    MFA_SETUP = "mfa_setup"
    MFA_CHALLENGE = "mfa_challenge"
    READY = "ready"


class ObjectAccessMode(StrEnum):
    ALL = "all"
    RESTRICTED = "restricted"


class Permission(StrEnum):
    DOCUMENTS_READ = "documents:read"
    AGENT_CHAT = "agent:chat"
    AGENT_WRITE = "agent:write"
    SYNC_RUN = "sync:run"
    USERS_MANAGE = "users:manage"
    MAIL_MANAGE = "mail:manage"
    AUDIT_READ = "audit:read"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.VIEWER: frozenset(
        {
            Permission.DOCUMENTS_READ,
            Permission.AGENT_CHAT,
        }
    ),
    Role.EDITOR: frozenset(
        {
            Permission.DOCUMENTS_READ,
            Permission.AGENT_CHAT,
            Permission.AGENT_WRITE,
            Permission.MAIL_MANAGE,
        }
    ),
    Role.ADMIN: frozenset(Permission),
}

ROLE_LABELS: dict[Role, str] = {
    Role.ADMIN: "Administrator",
    Role.EDITOR: "Bearbeiter",
    Role.VIEWER: "Betrachter",
}


def permissions_for(role: str) -> frozenset[Permission]:
    """Rechte einer Rolle. Unbekannte Rolle heißt keine Rechte, nicht alle."""
    try:
        return ROLE_PERMISSIONS[Role(role)]
    except ValueError:
        return frozenset()


@dataclass(frozen=True)
class Principal:
    """Der angemeldete Benutzer, wie ihn die Anwendung sieht.

    `object_access_mode` entscheidet ausdrücklich zwischen globalem und
    eingeschränktem Zugriff. Ein leeres `object_scope` im eingeschränkten Modus
    bedeutet keinen Zugriff und kann niemals zu globalem Zugriff degradieren.
    """

    user_id: str
    email: str
    display_name: str
    role: Role
    session_id: str = ""
    mfa_enabled: bool = False
    auth_stage: AuthStage = AuthStage.READY
    permissions: frozenset[Permission] = field(default_factory=frozenset)
    object_access_mode: ObjectAccessMode = ObjectAccessMode.ALL
    object_scope: frozenset[str] = field(default_factory=frozenset)

    def can(self, permission: Permission) -> bool:
        return permission in self.permissions
