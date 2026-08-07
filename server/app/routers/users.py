from fastapi import APIRouter, Depends, HTTPException, status

from .. import db
from ..auth import CurrentPrincipal, Permission, ROLE_LABELS, Role, require
from ..auth import sessions as auth_sessions
from ..auth.passwords import hash_password, validate_password
from ..models import (
    PasswordResetRequest,
    UserCreateRequest,
    UserOut,
    UserUpdateRequest,
)

router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(require(Permission.USERS_MANAGE))],
)


def _out(user: dict) -> UserOut:
    role = Role(user["role"])
    return UserOut(
        id=user["id"],
        email=user["email"],
        display_name=user["display_name"],
        role=role,
        role_label=ROLE_LABELS[role],
        is_active=user["is_active"],
        must_change_password=user["must_change_password"],
        last_login_at=user.get("last_login_at"),
        created_at=user["created_at"],
    )


def _parse_role(role: str) -> Role:
    try:
        return Role(role)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unbekannte Rolle '{role}'. Erlaubt: {', '.join(r.value for r in Role)}.",
        ) from None


async def _guard_last_admin(user_id: str, *, new_role: str | None, new_active: bool | None) -> None:
    """Verhindert, dass sich die Anwendung selbst aussperrt.

    Ohne diese Prüfung genügt ein Klick auf 'Betrachter' beim einzigen Admin, und
    niemand kann mehr Benutzer verwalten — auch nicht sich selbst zurückstufen.
    """
    losing_admin = new_role is not None and new_role != Role.ADMIN
    losing_active = new_active is False
    if not (losing_admin or losing_active):
        return

    current = await db.get_user_by_id(user_id)
    if current is None or current["role"] != Role.ADMIN or not current["is_active"]:
        return

    if await db.count_active_admins(excluding_user_id=user_id) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Das ist der letzte aktive Administrator. Lege zuerst einen weiteren an.",
        )


@router.get("/", response_model=list[UserOut])
async def list_users() -> list[UserOut]:
    return [_out(u) for u in await db.list_users()]


@router.post("/", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreateRequest) -> UserOut:
    role = _parse_role(payload.role)
    try:
        validate_password(payload.password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    if await db.get_user_by_email(payload.email) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Diese E-Mail-Adresse wird bereits verwendet.",
        )

    user = await db.create_user(
        email=payload.email,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
        role=role,
        must_change_password=True,
    )
    return _out(user)


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: str, payload: UserUpdateRequest, principal: CurrentPrincipal
) -> UserOut:
    role = _parse_role(payload.role) if payload.role is not None else None

    if user_id == principal.user_id and payload.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Du kannst dein eigenes Konto nicht deaktivieren.",
        )
    await _guard_last_admin(user_id, new_role=role, new_active=payload.is_active)

    user = await db.update_user(
        user_id,
        display_name=payload.display_name,
        role=role,
        is_active=payload.is_active,
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benutzer nicht gefunden")

    # Eine geänderte Rolle oder ein deaktiviertes Konto muss sofort wirken und nicht
    # erst, wenn die laufende Sitzung von selbst abläuft.
    if role is not None or payload.is_active is not None:
        await auth_sessions.revoke_all(user_id)

    return _out(user)


@router.post("/{user_id}/password", response_model=UserOut)
async def reset_password(user_id: str, payload: PasswordResetRequest) -> UserOut:
    try:
        validate_password(payload.password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    if await db.get_user_by_id(user_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benutzer nicht gefunden")

    await db.set_password(user_id, hash_password(payload.password), must_change=True)
    await auth_sessions.revoke_all(user_id)
    return _out(await db.get_user_by_id(user_id))


@router.delete("/{user_id}")
async def delete_user(user_id: str, principal: CurrentPrincipal):
    if user_id == principal.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Du kannst dein eigenes Konto nicht löschen.",
        )
    await _guard_last_admin(user_id, new_role=None, new_active=False)

    if await db.get_user_by_id(user_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benutzer nicht gefunden")

    # Die Chat-Sitzungen des Benutzers hängen per ON DELETE CASCADE daran und gehen
    # mit — sie gehören ihm allein und wären für niemanden sonst sichtbar.
    await db.delete_user(user_id)
    return {"status": "ok"}
