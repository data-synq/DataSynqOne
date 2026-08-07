import json
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from .. import db
from ..agent.runner import stream_agent
from ..auth import CurrentPrincipal, Principal
from ..models import ChatRequest

router = APIRouter(prefix="/agent", tags=["agent"])


def _make_title(message: str) -> str:
    message = message.strip().replace("\n", " ")
    return message[:60] + ("…" if len(message) > 60 else "")


async def _sse(request: ChatRequest, principal: Principal):
    session_id = request.session_id
    if not session_id:
        session_id = str(uuid.uuid4())
        await db.create_session(session_id, _make_title(request.message), principal.user_id)
        yield f"data: {json.dumps({'type': 'session', 'id': session_id})}\n\n"

    await db.add_message(session_id, "user", request.message)

    tool_calls: list[dict] = []
    try:
        async for event in stream_agent(request.message, request.history, principal):
            yield f"data: {json.dumps(event)}\n\n"

            if event["type"] == "tool_call":
                tool_calls.append({"name": event["name"], "arguments": event["arguments"]})
            elif event["type"] == "message":
                await db.add_message(session_id, "assistant", event["content"], tool_calls or None)
                await db.touch_session(session_id)
            elif event["type"] == "error":
                await db.add_message(session_id, "assistant", event["message"], tool_calls or None)
                await db.touch_session(session_id)
    except Exception:
        message = "Es ist ein unerwarteter Fehler aufgetreten. Bitte versuche es erneut."
        yield f"data: {json.dumps({'type': 'error', 'message': message})}\n\n"
        await db.add_message(session_id, "assistant", message, tool_calls or None)
        await db.touch_session(session_id)


@router.post("/chat")
async def chat(request: ChatRequest, principal: CurrentPrincipal) -> StreamingResponse:
    # Eine mitgeschickte session_id muss dem Anfragenden gehören. Ohne diese Prüfung
    # schreibt eine geratene UUID Nachrichten in eine fremde Konversation. 404 statt
    # 403, damit die Antwort die Existenz fremder Sitzungen nicht bestätigt.
    if request.session_id and not await db.session_belongs_to(
        request.session_id, principal.user_id
    ):
        raise HTTPException(status_code=404, detail="Session nicht gefunden")

    return StreamingResponse(_sse(request, principal), media_type="text/event-stream")
