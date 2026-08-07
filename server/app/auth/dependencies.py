"""Die zwei Dependencies, die die Router kennen: current_principal und require."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from ..config import settings
from . import sessions
from .permissions import Permission, Principal


async def current_principal(request: Request) -> Principal:
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
        return principal

    return dependency
