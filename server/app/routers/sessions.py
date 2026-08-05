from fastapi import APIRouter, HTTPException

from .. import db

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("/")
async def list_sessions():
    return await db.list_sessions()


@router.get("/{session_id}")
async def get_session(session_id: str):
    sessions = await db.list_sessions()
    session = next((s for s in sessions if s["id"] == session_id), None)
    if session is None:
        raise HTTPException(status_code=404, detail="Session nicht gefunden")
    messages = await db.get_session_messages(session_id)
    return {**session, "messages": messages}


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    await db.delete_session(session_id)
    return {"status": "ok"}
