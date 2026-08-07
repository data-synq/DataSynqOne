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


class Permission(StrEnum):
    DOCUMENTS_READ = "documents:read"
    AGENT_CHAT = "agent:chat"
    AGENT_WRITE = "agent:write"
    SYNC_RUN = "sync:run"
    USERS_MANAGE = "users:manage"


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

    `object_scope` ist die Vorbereitung auf eine Einschränkung nach Objekten
    (Liegenschaften): None bedeutet 'alle Objekte'. Solange in Paperless keine
    `obj:`-Tags gepflegt sind, bleibt es überall None — der Filter hat damit aber
    schon jetzt genau eine Stelle, an der er später greifen kann.
    """

    user_id: str
    email: str
    display_name: str
    role: Role
    permissions: frozenset[Permission] = field(default_factory=frozenset)
    object_scope: frozenset[str] | None = None

    def can(self, permission: Permission) -> bool:
        return permission in self.permissions
