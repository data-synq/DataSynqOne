from fastapi import APIRouter, HTTPException

from .. import db
from ..auth import CurrentPrincipal

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("/")
async def list_sessions(principal: CurrentPrincipal):
    return await db.list_sessions(principal.user_id)


@router.get("/{session_id}")
async def get_session(session_id: str, principal: CurrentPrincipal):
    sessions = await db.list_sessions(principal.user_id)
    session = next((s for s in sessions if s["id"] == session_id), None)
    # Eine fremde Sitzung ist hier nicht von einer nicht existierenden zu
    # unterscheiden — 403 würde bestätigen, dass es sie gibt.
    if session is None:
        raise HTTPException(status_code=404, detail="Session nicht gefunden")
    messages = await db.get_session_messages(session_id, principal.user_id)
    return {**session, "messages": messages}


@router.delete("/{session_id}")
async def delete_session(session_id: str, principal: CurrentPrincipal):
    await db.delete_session(session_id, principal.user_id)
    return {"status": "ok"}
