import secrets

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from .. import db
from .. import audit as security_audit
from ..auth import CurrentPrincipal, Permission, ROLE_LABELS, Role, require
from ..auth import invitations
from ..auth.object_access import available_object_options
from ..auth import sessions as auth_sessions
from ..auth.passwords import hash_password
from ..models import (
    InvitationResult,
    ObjectAccessRequest,
    ObjectOption,
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
        mfa_enabled=bool(user.get("mfa_enabled_at")),
        object_access_mode=user.get("object_access_mode", "restricted"),
        object_codes=sorted(user.get("object_codes", [])),
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


@router.get("/", response_model=list[UserOut])
async def list_users() -> list[UserOut]:
    return [_out(u) for u in await db.list_users()]


@router.post("/", response_model=InvitationResult, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreateRequest) -> InvitationResult:
    role = _parse_role(payload.role)
    await _validate_object_access(payload.object_access)

    if await db.get_user_by_email(payload.email) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Diese E-Mail-Adresse wird bereits verwendet.",
        )

    # Ein Zufallspasswort, das niemand kennt und niemand je erfährt: das Konto ist
    # bis zum Einlösen der Einladung nicht anmeldbar, aber password_hash ist NOT NULL
    # und der Login soll auch hier gegen einen echten Hash rechnen.
    user = await db.create_user(
        email=payload.email,
        display_name=payload.display_name,
        password_hash=hash_password(secrets.token_urlsafe(32)),
        role=role,
        must_change_password=True,
        object_access_mode=payload.object_access.mode,
        object_codes=tuple(payload.object_access.object_codes),
    )

    sent, link = await invitations.issue_and_send(
        user["id"], user["display_name"], user["email"], invitations.INVITATION
    )
    await security_audit.safe_record(
        "user.created",
        "success",
        target_type="user",
        target_id=user["id"],
        metadata={"new_role": role.value, "new_mode": payload.object_access.mode},
    )
    return InvitationResult(user=_out(user), mail_sent=sent, invitation_link=None if sent else link)


async def _validate_object_access(access: ObjectAccessRequest) -> None:
    if access.mode == "all":
        return
    try:
        available = {option["code"] for option in await available_object_options()}
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Die verfügbaren Objekte konnten nicht geprüft werden.",
        ) from exc
    unknown = sorted(set(access.object_codes) - available)
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unbekannte Objektcodes: {', '.join(unknown)}",
        )


@router.get("/object-options", response_model=list[ObjectOption])
async def object_options() -> list[ObjectOption]:
    try:
        return await available_object_options()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Die verfügbaren Objekte konnten nicht geladen werden.",
        ) from exc


@router.put("/{user_id}/object-scope", response_model=UserOut)
async def update_object_scope(
    user_id: str, payload: ObjectAccessRequest, principal: CurrentPrincipal
) -> UserOut:
    if user_id == principal.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Du kannst deinen eigenen Objektzugriff nicht ändern.",
        )
    await _validate_object_access(payload)
    try:
        updated = await db.set_object_scope(
            user_id, payload.mode, tuple(payload.object_codes)
        )
    except db.LastGlobalAdminError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Der letzte globale Administrator muss Zugriff auf alle Objekte behalten.",
        ) from exc
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benutzer nicht gefunden")
    user = await db.get_user_by_id(user_id)
    await security_audit.safe_record(
        "user.scope_changed",
        "success",
        target_type="user",
        target_id=user_id,
        metadata={"new_mode": payload.mode, "scope_count": len(payload.object_codes)},
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
    try:
        user = await db.update_user(
            user_id,
            display_name=payload.display_name,
            role=role,
            is_active=payload.is_active,
        )
    except (db.LastActiveAdminError, db.LastGlobalAdminError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Das ist der letzte aktive Administrator. Lege zuerst einen weiteren an.",
        ) from exc
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benutzer nicht gefunden")

    # Eine geänderte Rolle oder ein deaktiviertes Konto muss sofort wirken und nicht
    # erst, wenn die laufende Sitzung von selbst abläuft.
    if role is not None or payload.is_active is not None:
        await auth_sessions.revoke_all(user_id)

    await security_audit.safe_record(
        "user.updated",
        "success",
        target_type="user",
        target_id=user_id,
        metadata={"new_role": role.value if role is not None else user["role"]},
    )

    return _out(user)


@router.post("/{user_id}/invitation", response_model=InvitationResult)
async def resend_invitation(user_id: str) -> InvitationResult:
    """Neuer Link — für eine abgelaufene Einladung wie für ein vergessenes Passwort.

    Das bisherige Passwort bleibt bis zum Einlösen gültig: sonst sperrt ein
    versehentlicher Klick jemanden aus, der gerade arbeitet.
    """
    user = await db.get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benutzer nicht gefunden")

    purpose = (
        invitations.INVITATION if user["last_login_at"] is None else invitations.PASSWORD_RESET
    )
    sent, link = await invitations.issue_and_send(
        user["id"], user["display_name"], user["email"], purpose
    )
    return InvitationResult(user=_out(user), mail_sent=sent, invitation_link=None if sent else link)


@router.delete("/{user_id}")
async def delete_user(user_id: str, principal: CurrentPrincipal):
    if user_id == principal.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Du kannst dein eigenes Konto nicht löschen.",
        )
    # Die Chat-Sitzungen des Benutzers hängen per ON DELETE CASCADE daran und gehen
    # mit — sie gehören ihm allein und wären für niemanden sonst sichtbar.
    try:
        deleted = await db.delete_user(user_id)
    except (db.LastActiveAdminError, db.LastGlobalAdminError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Das ist der letzte aktive Administrator. Lege zuerst einen weiteren an.",
        ) from exc
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benutzer nicht gefunden")
    await security_audit.safe_record(
        "user.deleted", "success", target_type="user", target_id=user_id
    )
    return {"status": "ok"}
