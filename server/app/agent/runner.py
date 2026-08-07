import asyncio
import json
from typing import AsyncIterator

from ..openai_client import get_client

from ..auth.permissions import Permission, Principal
from ..config import settings
from ..models import ChatMessage
from .suggestions import generate_suggestions
from .tools import call_tool, tools_for

# Der Prompt zerfaellt in einen gemeinsamen Sockel und einen Block ueber das
# schreibende Verwalten. Ein Betrachter darf den Schreib-Block nicht sehen: sonst
# kuendigt der Assistent Aenderungen an, die seine Rolle gar nicht zulaesst, und die
# schreibenden Werkzeuge stehen ihm ohnehin nicht zur Verfuegung (siehe tools_for).
_BASE_PROMPT = (
    "Du bist ein Assistent fuer eine Hausverwaltung, der auf der Paperless-ngx "
    "Dokumentenverwaltung arbeitet. Nutze die verfuegbaren Tools, um Dokumente zu finden, "
    "Faelle zusammenzufassen und auf Wunsch Antwort-Entwuerfe zu formulieren. Antworte auf Deutsch. "
    "Fuer Berechnungen (Summen, Prozentrechnung, Nebenkostenverteilung etc.) nutze immer das "
    "'calculator'-Tool statt selbst zu rechnen. Fuer Fragen zu Geldbetraegen in Dokumenten nutze "
    "'extract_amounts' (einzelnes Dokument) oder 'search_documents_by_amount' (Suche ueber mehrere "
    "Dokumente). Du darfst mehrere Tools nacheinander und auch mehrere gleichzeitig aufrufen, wenn das "
    "zur Beantwortung noetig ist. "
    "Wenn du ein konkretes Dokument erwaehnst, verlinke es immer im Format "
    "[Titel](doc:ID), wobei ID die Paperless-Dokument-ID aus den Tool-Ergebnissen ist "
    "(z. B. [Rechnung Stadtwerke](doc:42)), damit die Oberflaeche daraus einen Button machen kann. "
    "Wenn ein Such-/Filter-Tool mehrere Dokumente liefert, liste in deiner Antwort IMMER ALLE "
    "zurueckgegebenen Dokumente auf, nicht nur eine Auswahl. Wenn das Tool-Ergebnis "
    "'truncated: true' enthaelt, weise darauf hin, dass es noch weitere, nicht angezeigte Treffer gibt. "
    "'search_documents' und 'filter_documents_by_date_range' erweitern die Suche bei wenigen Treffern "
    "automatisch um thematisch verwandte Begriffe (Rechtschreib-/Kompositum-Varianten, Synonyme) — das "
    "Tool-Ergebnis enthaelt dann 'expanded_with' mit den zusaetzlich genutzten Begriffen. Erwaehne kurz, "
    "wenn die Suche so erweitert wurde. "
    "Nutze 'semantic_search_documents' zusaetzlich zu 'search_documents' fuer vage, thematische Anfragen "
    "ohne exakte Suchbegriffe (z. B. 'irgendwas zu Wasserschaeden') — fuer exakte Begriffe, Nummern oder "
    "bekannte Titel bleibt 'search_documents' die erste Wahl. "
    "'search_documents' ohne 'query' und 'list_untagged_documents' liefern zuverlaessig die "
    "vollstaendige bzw. korrekt gefilterte Dokumentliste — verlasse dich darauf, statt an der "
    "Vollstaendigkeit zu zweifeln oder die Aufgabe deswegen abzulehnen. "
    "Wenn Zahlen sich sinnvoll visualisieren lassen (z. B. Kostenuebersicht, Verlauf ueber Zeit, "
    "Vergleich mehrerer Positionen), ermittle die Werte zuerst ueber die passenden Tools und rufe dann "
    "'create_chart' mit den fertigen Labels/Datasets auf. Der Chart wird dem Nutzer automatisch sofort "
    "rechts angezeigt, du musst ihn nicht zusaetzlich verlinken oder beschreiben, was er zeigt."
)

_WRITE_PROMPT = (
    " "
    "Du darfst Paperless auch schreibend verwalten: Tags, Korrespondenten und Dokumenttypen anlegen "
    "('create_tag', 'create_correspondent', 'create_document_type' — legen bei bereits existierendem "
    "Namen nichts doppelt an, sondern nutzen den vorhandenen Eintrag), Dokumenten zuweisen "
    "('assign_tags_to_document', 'set_document_correspondent', 'set_document_document_type') und "
    "Dokumente umbenennen ('rename_document'). 'delete_tag', 'delete_correspondent' und "
    "'delete_document_type' loeschen unwiderruflich — nutze sie nur, wenn der Nutzer das ausdruecklich "
    "verlangt, und fasse in deiner Antwort klar zusammen, was geloescht wurde. "
    "Wenn mehrere Dokumente gleichzeitig geaendert werden sollen (z. B. 'tagge alle Rechnungen von X'), "
    "ermittle zuerst die betroffenen Dokument-IDs ueber ein Such-Tool und rufe dann 'bulk_update_documents' "
    "einmal mit der gesammelten ID-Liste auf, statt die Einzel-Tools in einer Schleife pro Dokument "
    "aufzurufen. "
    "Bei offenen Organisations-/Klassifizierungsaufgaben ohne vorgegebene Taxonomie (z. B. 'tagge alle "
    "ungetaggten Dokumente richtig' oder 'sortiere die Dokumente') sollst du NICHT ablehnen oder nach "
    "einer Tag-Struktur fragen, sondern selbst eine sinnvolle Einteilung vornehmen: rufe zuerst "
    "'list_tags' auf, um bestehende Tags zu sehen und wiederzuverwenden, leite dann pro Dokument aus "
    "dessen Inhalt eine passende Tag-Zuordnung ab und weise sie zu ('assign_tags_to_document' einzeln "
    "bei unterschiedlicher Einordnung je Dokument, 'bulk_update_documents' wenn mehrere Dokumente in "
    "dieselbe Kategorie fallen). Fasse am Ende kurz zusammen, welches Dokument welche(n) Tag(s) bekommen "
    "hat und warum. "
    "Fuer Status und Kategorie von Dokumenten verwende ausschliesslich folgende feste Tag-Namen "
    "(englisch, nicht uebersetzen, nicht abwandeln, keine neuen Status-/Kategorie-Tags erfinden): "
    "Status (genau EINEN pro Dokument): 'open', 'in-progress', 'done', 'urgent', 'overdue'. "
    "Kategorie (mindestens einen pro Dokument, mehrere moeglich): 'invoice', 'contract', "
    "'maintenance-request', 'legal', 'correspondence', 'tenant-notice', 'insurance', 'utility-bill'. "
    "Wenn du in einem Dokument eine konkrete Frist/ein Faelligkeitsdatum erkennst (Zahlungsziel, "
    "Widerspruchsfrist, Ablaufdatum etc.), weise zusaetzlich einen Tag im Format 'due:JJJJ-MM-TT' zu "
    "(z. B. 'due:2026-08-20'), basierend auf dem erkannten Datum. Aendert sich der Status eines "
    "Dokuments (z. B. von 'open' zu 'done'), entferne den alten Status-Tag ueber "
    "'bulk_update_documents' mit 'remove_tag_names' und setze den neuen mit 'add_tag_names', statt "
    "beide gleichzeitig stehen zu lassen."
)

_READ_ONLY_PROMPT = (
    " "
    "Der Nutzer hat Nur-Lese-Zugang (Rolle 'Betrachter'). Dir stehen ausschliesslich suchende und "
    "auswertende Werkzeuge zur Verfuegung; Dokumente, Tags, Korrespondenten und Dokumenttypen kannst "
    "du weder anlegen noch aendern oder loeschen. Sage bei einem entsprechenden Wunsch klar und ohne "
    "Umschweife, dass das in dieser Rolle nicht moeglich ist und ein Bearbeiter oder Administrator "
    "die Aenderung vornehmen muss. Versprich keine Aenderung und behaupte nie, eine durchgefuehrt zu "
    "haben. Analysieren, zusammenfassen, Antwortentwuerfe formulieren und Auswertungen als Chart "
    "darstellen darfst du weiterhin uneingeschraenkt. "
    "Zum Verstaendnis der vorhandenen Tags: der Status eines Dokuments steckt in genau einem der Tags "
    "'open', 'in-progress', 'done', 'urgent', 'overdue', die Kategorie in einem oder mehreren von "
    "'invoice', 'contract', 'maintenance-request', 'legal', 'correspondence', 'tenant-notice', "
    "'insurance', 'utility-bill'. Ein Tag der Form 'due:JJJJ-MM-TT' ist eine Frist."
)


def build_system_prompt(can_write: bool) -> str:
    return _BASE_PROMPT + (_WRITE_PROMPT if can_write else _READ_ONLY_PROMPT)


MAX_TOOL_ROUNDS = 30
HEARTBEAT_SECONDS = 15


_TRIM_TEXT_FIELDS = {"content", "highlights"}
_CLIENT_TEXT_LIMIT = 2000


def _trim_for_client(value):
    """Shrinks large text fields (e.g. full OCR content) before sending a tool
    result to the frontend over SSE — the full text still goes to the model via
    function_call_output, the UI just doesn't need it verbatim."""
    if isinstance(value, dict):
        trimmed = {}
        for key, val in value.items():
            if key in _TRIM_TEXT_FIELDS and isinstance(val, str) and len(val) > _CLIENT_TEXT_LIMIT:
                trimmed[key] = val[:_CLIENT_TEXT_LIMIT] + "…"
            else:
                trimmed[key] = _trim_for_client(val)
        return trimmed
    if isinstance(value, list):
        return [_trim_for_client(v) for v in value]
    return value


async def _await_with_heartbeat(coro) -> AsyncIterator[dict]:
    """Runs any awaitable as a background task and yields SSE pings every
    HEARTBEAT_SECONDS while it's pending, so a slow operation (an OpenAI call, or a
    tool call that hits Paperless/embeddings/an LLM) never leaves the SSE stream
    silent long enough for a NAT/proxy/browser to consider the connection dead."""
    task = asyncio.ensure_future(coro)
    while True:
        done, _ = await asyncio.wait({task}, timeout=HEARTBEAT_SECONDS)
        if task in done:
            yield {"type": "result", "value": task.result()}
            return
        yield {"type": "ping"}


async def stream_agent(
    message: str, history: list[ChatMessage], principal: Principal
) -> AsyncIterator[dict]:
    can_write = principal.can(Permission.AGENT_WRITE)
    system_prompt = build_system_prompt(can_write)
    tool_definitions = tools_for(can_write)

    # Only the first round sends full history; subsequent rounds chain via
    # previous_response_id and send just the newly produced function_call_outputs,
    # so the request body no longer grows with every tool call in a long session.
    input_items: list[dict] = [{"role": m.role, "content": m.content} for m in history]
    input_items.append({"role": "user", "content": message})
    previous_response_id: str | None = None

    for _ in range(MAX_TOOL_ROUNDS):
        response = None
        try:
            async for event in _await_with_heartbeat(
                get_client().responses.create(
                    model=settings.openai_model,
                    instructions=system_prompt,
                    input=input_items,
                    tools=tool_definitions,
                    previous_response_id=previous_response_id,
                )
            ):
                if event["type"] == "ping":
                    yield event
                else:
                    response = event["value"]
        except Exception as e:
            error_text = str(e)
            if "context_length" in error_text or "maximum context length" in error_text.lower():
                friendly = (
                    "Die Konversation ist fuer diese Anfrage zu lang geworden. "
                    "Bitte stelle die Anfrage in kleineren Schritten (z. B. weniger Dokumente auf einmal)."
                )
            else:
                friendly = "Bei der Anfrage an das Sprachmodell ist ein Fehler aufgetreten. Bitte versuche es erneut."
            yield {"type": "error", "message": friendly}
            return

        previous_response_id = response.id
        function_calls = [item for item in response.output if item.type == "function_call"]

        if not function_calls:
            final_content = response.output_text or ""
            yield {"type": "message", "content": final_content}
            suggestions = await generate_suggestions(history, message, final_content)
            yield {"type": "suggestions", "items": suggestions}
            return

        input_items = []
        for item in function_calls:
            args = json.loads(item.arguments or "{}")
            yield {
                "type": "tool_call",
                "id": item.call_id,
                "name": item.name,
                "arguments": args,
            }
            result = None
            try:
                async for event in _await_with_heartbeat(call_tool(item.name, args, can_write)):
                    if event["type"] == "ping":
                        yield event
                    else:
                        result = event["value"]
            except Exception as e:
                result = {"error": str(e)}
            yield {
                "type": "tool_result",
                "id": item.call_id,
                "name": item.name,
                "result": _trim_for_client(result),
            }
            if item.name == "create_chart" and "error" not in result:
                yield {"type": "chart", "id": item.call_id, "spec": result}
            input_items.append(
                {
                    "type": "function_call_output",
                    "call_id": item.call_id,
                    "output": json.dumps(result)[:8000],
                }
            )

    yield {
        "type": "error",
        "message": "Ich konnte innerhalb der erlaubten Schritte keine endgueltige Antwort finden.",
    }
