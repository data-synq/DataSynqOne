import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from .. import db
from ..agent.runner import stream_agent
from ..auth import CurrentPrincipal, Principal
from ..json_utils import dumps
from ..models import ChatMessage, ChatRequest

router = APIRouter(prefix="/agent", tags=["agent"])


def _make_title(message: str) -> str:
    message = message.strip().replace("\n", " ")
    return message[:60] + ("…" if len(message) > 60 else "")


async def _persist_board_events(
    session_id: str, user_id: str, message_id: int, board_events: list[dict]
) -> None:
    for ev in board_events:
        await db.add_board_event(
            session_id,
            user_id,
            message_id,
            ev["tool_call_index"],
            ev["kind"],
            ev["title"],
            ev["payload"],
        )


async def _sse(request: ChatRequest, principal: Principal):
    session_id = request.session_id
    history: list[ChatMessage] = []
    if session_id:
        stored = await db.get_session_messages(session_id, principal.user_id)
        remaining = 64000
        for item in reversed(stored[-20:]):
            content = item.get("content") or ""
            role = item.get("role")
            if role not in {"user", "assistant"} or len(content) > remaining:
                continue
            history.append(ChatMessage(role=role, content=content))
            remaining -= len(content)
        history.reverse()
    if not session_id:
        session_id = str(uuid.uuid4())
        title = _make_title(request.message)
        await db.create_session(session_id, title, principal.user_id)
        yield f"data: {dumps({'type': 'session', 'id': session_id, 'title': title})}\n\n"

    await db.add_message(session_id, "user", request.message)

    tool_calls: list[dict] = []
    # Die zugehörige Nachricht existiert erst, nachdem der Turn fertig ist —
    # bis dahin werden Board-Events nur gesammelt, nicht gespeichert.
    board_events: list[dict] = []
    try:
        async for event in stream_agent(request.message, history, principal, session_id):
            yield f"data: {dumps(event)}\n\n"

            if event["type"] == "tool_call":
                tool_calls.append({"name": event["name"], "arguments": event["arguments"]})
            elif event["type"] == "board":
                board_events.append(
                    {
                        "tool_call_index": len(tool_calls) - 1,
                        "kind": event["kind"],
                        "title": event["title"],
                        "payload": event["payload"],
                    }
                )
            elif event["type"] == "message":
                message_id = await db.add_message(
                    session_id, "assistant", event["content"], tool_calls or None
                )
                await _persist_board_events(session_id, principal.user_id, message_id, board_events)
                await db.touch_session(session_id)
            elif event["type"] == "error":
                message_id = await db.add_message(
                    session_id, "assistant", event["message"], tool_calls or None
                )
                await _persist_board_events(session_id, principal.user_id, message_id, board_events)
                await db.touch_session(session_id)
    except Exception:
        message = "Es ist ein unerwarteter Fehler aufgetreten. Bitte versuche es erneut."
        yield f"data: {dumps({'type': 'error', 'message': message})}\n\n"
        message_id = await db.add_message(session_id, "assistant", message, tool_calls or None)
        await _persist_board_events(session_id, principal.user_id, message_id, board_events)
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
