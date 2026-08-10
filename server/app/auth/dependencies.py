"""Die zwei Dependencies, die die Router kennen: current_principal und require."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from ..config import settings
from . import sessions
from .permissions import AuthStage, ObjectAccessMode, Permission, Principal

_GLOBAL_PERMISSIONS = frozenset(
    {Permission.SYNC_RUN, Permission.USERS_MANAGE, Permission.AUDIT_READ}
)


async def authenticated_principal(request: Request) -> Principal:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Nicht angemeldet"
        )
    principal = await sessions.resolve(token)
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Sitzung abgelaufen"
        )
    from ..audit import set_actor

    set_actor(principal.user_id, principal.role.value)
    request.state.audit_actor = (principal.user_id, principal.role.value)
    return principal


AuthenticatedPrincipal = Annotated[Principal, Depends(authenticated_principal)]


async def current_principal(principal: AuthenticatedPrincipal) -> Principal:
    requirements = {
        AuthStage.PASSWORD_CHANGE: (
            "password_change_required",
            "Das Passwort muss zuerst geändert werden.",
        ),
        AuthStage.MFA_SETUP: (
            "mfa_setup_required",
            "Die Zwei-Faktor-Authentifizierung muss zuerst eingerichtet werden.",
        ),
        AuthStage.MFA_CHALLENGE: (
            "mfa_challenge_required",
            "Die Zwei-Faktor-Anmeldung muss zuerst abgeschlossen werden.",
        ),
    }
    requirement = requirements.get(principal.auth_stage)
    if requirement:
        code, message = requirement
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail={
                "code": code,
                "message": message,
            },
        )
    return principal


CurrentPrincipal = Annotated[Principal, Depends(current_principal)]


def require(*permissions: Permission):
    """Dependency-Factory: verlangt alle genannten Rechte."""

    async def dependency(principal: CurrentPrincipal) -> Principal:
        missing = [p for p in permissions if not principal.can(p)]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Für diese Aktion fehlt dir die Berechtigung.",
            )
        if (
            principal.object_access_mode is ObjectAccessMode.RESTRICTED
            and any(permission in _GLOBAL_PERMISSIONS for permission in permissions)
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Diese globale Aktion erfordert Zugriff auf alle Objekte.",
            )
        return principal

    return dependency
