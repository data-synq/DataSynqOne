import json
import re

from simpleeval import simple_eval

from .. import db, vectorstore
from ..auth import Principal
from ..auth.object_access import ObjectAccessDenied, ObjectAuthorizer, parse_object_tag
from ..paperless_client import paperless_client
from ..tagging import CASE_TAG_COLOR
from ..tagging import find_by_name as _find_by_name
from ..tagging import get_or_create as _get_or_create
from .amount_extraction import extract_amounts_llm
from .query_expansion import expand_search_terms

# Mirrors mail/intake.py's _ACTOR_LABEL: eine über den Chat ausgelöste Änderung
# soll im Zeitstrahl als "Agent" erscheinen, nicht unter dem Namen der Person,
# die gerade mit ihm chattet — sonst lässt sich "selbst geklickt" nicht mehr
# von "den Assistenten gebeten" unterscheiden.
_ACTOR_LABEL = "Agent"


def _safe_metadata(items: list[dict], *, include_color: bool = False) -> list[dict]:
    fields = {"id", "name", "slug"}
    if include_color:
        fields.add("color")
    return [{key: item.get(key) for key in fields if key in item} for item in items]

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_documents",
            "description": "Search Paperless documents by full-text query and optional correspondent id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Full-text search query"},
                    "correspondent_id": {"type": "integer", "description": "Filter by correspondent id"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_document",
            "description": "Get full metadata and OCR text content of a single document by id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "document_id": {"type": "integer"},
                },
                "required": ["document_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_correspondents",
            "description": "List all correspondents known to Paperless.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_document_types",
            "description": "List all document types known to Paperless.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": (
                "Evaluate a safe arithmetic expression, e.g. for Nebenkostenabrechnungen, "
                "Prozentrechnung oder Summenbildung. Nutze dies statt selbst zu rechnen."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "z. B. '1234.56 * 0.03' oder '(100 + 250) / 2'",
                    },
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extract_amounts",
            "description": (
                "Extract all monetary amounts (with a short label each, e.g. 'Gesamtbetrag') "
                "from a single document's OCR text using an LLM."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "document_id": {"type": "integer"},
                },
                "required": ["document_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_documents_by_amount",
            "description": (
                "Find documents whose extracted monetary amounts fall within a given range. "
                "Runs an LLM amount-extraction per candidate document, so set 'query' and/or "
                "'correspondent_id' to narrow down candidates first (max 'limit' documents checked)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "min_amount": {"type": "number"},
                    "max_amount": {"type": "number"},
                    "query": {"type": "string", "description": "Full-text search to narrow candidates"},
                    "correspondent_id": {"type": "integer"},
                    "limit": {"type": "integer", "description": "Max candidate documents to check (default 10)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "filter_documents_by_tag",
            "description": "List documents that have a given tag (matched by name, case-insensitive).",
            "parameters": {
                "type": "object",
                "properties": {
                    "tag_name": {"type": "string"},
                },
                "required": ["tag_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "filter_documents_by_date_range",
            "description": "List documents created within a date range (YYYY-MM-DD), optionally combined with a search query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_from": {"type": "string", "description": "YYYY-MM-DD"},
                    "date_to": {"type": "string", "description": "YYYY-MM-DD"},
                    "query": {"type": "string"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_recent_documents",
            "description": "List the most recently added documents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Default 10"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tags",
            "description": (
                "Listet alle in Paperless vorhandenen Tags auf. Status- und Kategorie-Tags folgen einer "
                "festen Taxonomie (siehe Systemanweisung) und existieren bereits. Nutze dieses Tool vor "
                "Klassifizierungs-/Organisationsaufgaben vor allem, um bereits vergebene, freie "
                "(nicht-taxonomische) Zusatz-Tags wiederzuverwenden statt neue, uneinheitliche zu erfinden."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_untagged_documents",
            "description": (
                "Liefert alle Dokumente, die aktuell KEINE Tags haben — zuverlaessig ueber die "
                "vollstaendige Dokumentliste ermittelt (kein serverseitiger Filter noetig). Nutze dies "
                "z. B. fuer 'tagge alle ungetaggten Dokumente'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max. Ergebnisse, Standard alle"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "semantic_search_documents",
            "description": (
                "Semantische/inhaltliche Aehnlichkeitssuche ueber alle synchronisierten Paperless-"
                "Dokumente mittels Embeddings. Nutze dies fuer vage, thematische oder bedeutungsbasierte "
                "Anfragen, bei denen die exakte Keyword-Suche ('search_documents') relevante Dokumente "
                "verpassen koennte (z. B. 'Dokumente zu Wasserschaeden', 'irgendwas zur Heizungswartung')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "description": "Max. Ergebnisse, Standard 10"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_tag",
            "description": "Erstellt einen neuen Tag (oder gibt den bestehenden zurueck, falls der Name schon existiert).",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "color": {"type": "string", "description": "Optionale Hex-Farbe, z. B. '#a6cee3'"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_correspondent",
            "description": "Erstellt einen neuen Korrespondenten (oder gibt den bestehenden zurueck, falls der Name schon existiert).",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_document_type",
            "description": "Erstellt einen neuen Dokumenttyp (oder gibt den bestehenden zurueck, falls der Name schon existiert).",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "assign_tags_to_document",
            "description": (
                "Weist einem Dokument einen oder mehrere Tags zu (additiv, bestehende Tags bleiben "
                "erhalten). Tags, die noch nicht existieren, werden automatisch angelegt."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "document_id": {"type": "integer"},
                    "tag_names": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["document_id", "tag_names"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_document_correspondent",
            "description": (
                "Setzt den Korrespondenten eines Dokuments. Der Korrespondent wird automatisch "
                "angelegt, falls er noch nicht existiert."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "document_id": {"type": "integer"},
                    "correspondent_name": {"type": "string"},
                },
                "required": ["document_id", "correspondent_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_document_document_type",
            "description": (
                "Setzt den Dokumenttyp eines Dokuments. Der Dokumenttyp wird automatisch angelegt, "
                "falls er noch nicht existiert."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "document_id": {"type": "integer"},
                    "document_type_name": {"type": "string"},
                },
                "required": ["document_id", "document_type_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rename_document",
            "description": "Aendert den Titel eines Dokuments.",
            "parameters": {
                "type": "object",
                "properties": {
                    "document_id": {"type": "integer"},
                    "title": {"type": "string"},
                },
                "required": ["document_id", "title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_tag",
            "description": "Loescht einen Tag unwiderruflich anhand seines Namens.",
            "parameters": {
                "type": "object",
                "properties": {"tag_name": {"type": "string"}},
                "required": ["tag_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_correspondent",
            "description": "Loescht einen Korrespondenten unwiderruflich anhand seines Namens.",
            "parameters": {
                "type": "object",
                "properties": {"correspondent_name": {"type": "string"}},
                "required": ["correspondent_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_document_type",
            "description": "Loescht einen Dokumenttyp unwiderruflich anhand seines Namens.",
            "parameters": {
                "type": "object",
                "properties": {"document_type_name": {"type": "string"}},
                "required": ["document_type_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bulk_update_documents",
            "description": (
                "Aendert Tags/Korrespondent/Dokumenttyp fuer viele Dokumente gleichzeitig in einem "
                "Rutsch. Ermittle die betroffenen Dokument-IDs vorher ueber ein Such-Tool "
                "(z. B. 'search_documents', 'filter_documents_by_tag') und uebergib sie hier gesammelt, "
                "statt die Einzel-Tools ('assign_tags_to_document' etc.) in einer Schleife pro Dokument "
                "aufzurufen. Namen, die noch nicht existieren, werden bei 'add_tag_names' automatisch "
                "angelegt (nicht bei 'remove_tag_names')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "document_ids": {"type": "array", "items": {"type": "integer"}},
                    "add_tag_names": {"type": "array", "items": {"type": "string"}},
                    "remove_tag_names": {"type": "array", "items": {"type": "string"}},
                    "correspondent_name": {"type": "string"},
                    "document_type_name": {"type": "string"},
                },
                "required": ["document_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_chart",
            "description": (
                "Render a chart (e.g. Kostenuebersicht, Verlauf ueber Zeit) for immediate display "
                "to the user. Gather/compute the numbers yourself first (search/amount/calculator "
                "tools), then call this with the final labels and datasets."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "chart_type": {"type": "string", "enum": ["bar", "line", "pie", "doughnut"]},
                    "title": {"type": "string"},
                    "labels": {"type": "array", "items": {"type": "string"}},
                    "datasets": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string"},
                                "data": {"type": "array", "items": {"type": "number"}},
                            },
                            "required": ["label", "data"],
                        },
                    },
                    "x_label": {"type": "string"},
                    "y_label": {"type": "string"},
                },
                "required": ["chart_type", "title", "labels", "datasets"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "prepare_email",
            "description": (
                "Prepare a DRAFT email for the user to review. This does NOT send anything — "
                "the draft is shown in the UI and a human must click send. Use it whenever the "
                "user asks you to write to a tenant, contractor or correspondent. Always tell "
                "the user afterwards that the draft is ready for their review, never that the "
                "mail was sent."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string"},
                    "body": {
                        "type": "string",
                        "description": "Full message text in German, with salutation and closing.",
                    },
                    "document_id": {
                        "type": "integer",
                        "description": "Paperless document this reply refers to, if any.",
                    },
                    "case_tracking_id": {
                        "type": "string",
                        "description": (
                            "Tracking-ID des Anliegens (z. B. 'AL-2026-0007'), falls dieser Entwurf zu "
                            "einem Anliegen gehoert. Wird automatisch in den Betreff aufgenommen, damit "
                            "die Antwort des Empfaengers dem Anliegen zugeordnet werden kann."
                        ),
                    },
                },
                "required": ["subject", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_cases",
            "description": (
                "Search existing Anliegen (cases) by keyword — matches title, summary and notes. "
                "Tracking-IDs look like 'AL-2026-0007'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "status": {"type": "string", "enum": ["open", "closed"]},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_case",
            "description": "Get full detail of one Anliegen (case) by its tracking id: status, summary, linked Paperless documents, timeline, notes and dependency links.",
            "parameters": {
                "type": "object",
                "properties": {"tracking_id": {"type": "string"}},
                "required": ["tracking_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_object_cases",
            "description": "List all Anliegen (cases) filed for a given OBJ-xxx object code.",
            "parameters": {
                "type": "object",
                "properties": {"object_code": {"type": "string"}},
                "required": ["object_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_case_note",
            "description": "Add a note to an Anliegen (case). Visible to everyone with access to the case, including a later run of the intake pipeline.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tracking_id": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["tracking_id", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "close_case",
            "description": "Mark an Anliegen (case) as closed.",
            "parameters": {
                "type": "object",
                "properties": {"tracking_id": {"type": "string"}},
                "required": ["tracking_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reopen_case",
            "description": "Reopen a previously closed Anliegen (case).",
            "parameters": {
                "type": "object",
                "properties": {"tracking_id": {"type": "string"}},
                "required": ["tracking_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "link_cases",
            "description": (
                "Mark one Anliegen (case) as depending on another. 'dependent_tracking_id' is the "
                "case that builds on / can't be considered independent of 'prerequisite_tracking_id'. "
                "Applied immediately (confirmed), since this is an explicit, live instruction from a "
                "logged-in user, not an unattended background suggestion."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dependent_tracking_id": {"type": "string"},
                    "prerequisite_tracking_id": {"type": "string"},
                },
                "required": ["dependent_tracking_id", "prerequisite_tracking_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "unlink_cases",
            "description": "Remove a dependency link between two Anliegen (cases), confirmed or still-proposed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dependent_tracking_id": {"type": "string"},
                    "prerequisite_tracking_id": {"type": "string"},
                },
                "required": ["dependent_tracking_id", "prerequisite_tracking_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "attach_case_documents",
            "description": (
                "Attach one or more existing Paperless documents to an Anliegen (case). "
                "Creates/reuses a Paperless tag named after the case's tracking id and applies "
                "it to each document — the same mechanism the document picker on the case page "
                "uses. A document can be attached to more than one case."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tracking_id": {"type": "string"},
                    "document_ids": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["tracking_id", "document_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detach_case_document",
            "description": (
                "Remove a document from an Anliegen (case): strips the case's tracking-id tag "
                "from the document in Paperless and removes the link."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tracking_id": {"type": "string"},
                    "document_id": {"type": "integer"},
                },
                "required": ["tracking_id", "document_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_board",
            "description": (
                "Show a document directly to the user in the board area next to the chat, so "
                "they can see it while you keep working. Use it when your answer centers on one "
                "specific document and showing it directly helps more than just linking it "
                "inline in the reply — not for every passing mention of a document."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "document_id": {"type": "integer", "description": "Paperless document ID to show."},
                    "title": {
                        "type": "string",
                        "description": "Short label for the board, e.g. the document title.",
                    },
                },
                "required": ["document_id"],
            },
        },
    },
]

RESPONSES_TOOL_DEFINITIONS = [{"type": "function", **t["function"]} for t in TOOL_DEFINITIONS]

# Werkzeuge, die Paperless verändern. Wer 'agent:write' nicht hat, bekommt sie gar
# nicht erst angeboten (tools_for) und käme mit einem erratenen Namen auch nicht
# durch (call_tool). Ein neues schreibendes Werkzeug gehört hier hinein — der Test
# in server/tests/test_permissions.py schlägt fehl, wenn das jemand vergisst.
WRITE_TOOLS = frozenset(
    {
        "create_tag",
        "create_correspondent",
        "create_document_type",
        "assign_tags_to_document",
        "set_document_correspondent",
        "set_document_document_type",
        "rename_document",
        "delete_tag",
        "delete_correspondent",
        "delete_document_type",
        "bulk_update_documents",
        # Verschickt nichts, legt aber einen Entwurf an, der sich mit einem Klick
        # verschicken laesst — das ist keine Lesetaetigkeit.
        "prepare_email",
        "add_case_note",
        "close_case",
        "reopen_case",
        "link_cases",
        "unlink_cases",
        "attach_case_documents",
        "detach_case_document",
    }
)

# Untrusted OCR/tool output and model reasoning must never directly mutate business
# state. The sole exception creates an internal draft without a recipient; sending
# still requires a human-entered address and a separate authenticated endpoint.
MODEL_ALLOWED_WRITE_TOOLS = frozenset()

PERMISSION_DENIED = {
    "error": (
        "Dafuer fehlt die Berechtigung: in der Rolle Betrachter stehen nur lesende und "
        "auswertende Werkzeuge zur Verfuegung. Aenderungen an Dokumenten, Tags, "
        "Korrespondenten und Dokumenttypen kann nur ein Bearbeiter oder Administrator "
        "vornehmen."
    )
}

_TOOL_SCHEMAS = {tool["function"]["name"]: tool["function"]["parameters"] for tool in TOOL_DEFINITIONS}
_WRITE_INTENT = re.compile(
    r"(?i)\b(?:aender|änder|aktualisier|weis|setze?|tagge|benenn|loesch|lösch|entfern|erstell|leg(?:e|t)|"
    r"schliess|schließ|oeffne|öffne|verknuepf|verknüpf|haeng|häng|notiz|entwurf|schreib(?:e|t)|mail)\w*\b"
)


def write_is_explicitly_authorized(name: str, user_message: str) -> bool:
    if name not in WRITE_TOOLS:
        return True
    if name == "prepare_email":
        mail_object = re.search(r"(?i)\b(?:e-?mail|mailentwurf|entwurf|anschreiben|antwortschreiben)\b", user_message)
        mail_action = re.search(r"(?i)\b(?:schreib|formulier|erstell|bereit|vorbereit)\w*\b", user_message)
        return bool(mail_object and mail_action)
    return bool(_WRITE_INTENT.search(user_message))


def _validate_schema(value, schema: dict, path: str) -> None:
    expected = schema.get("type")
    if isinstance(expected, list):
        if value is None and "null" in expected:
            return
        expected = next((item for item in expected if item != "null"), None)
    if expected == "object":
        if not isinstance(value, dict):
            raise ValueError(f"{path} muss ein Objekt sein")
        properties = schema.get("properties", {})
        unknown = set(value) - set(properties)
        if unknown:
            raise ValueError(f"{path} enthaelt unbekannte Felder")
        missing = set(schema.get("required", [])) - set(value)
        if missing:
            raise ValueError(f"{path} fehlen Pflichtfelder")
        for key, item in value.items():
            _validate_schema(item, properties[key], f"{path}.{key}")
    elif expected == "array":
        if not isinstance(value, list):
            raise ValueError(f"{path} muss eine Liste sein")
        if len(value) > min(schema.get("maxItems", 200), 200):
            raise ValueError(f"{path} enthaelt zu viele Eintraege")
        for index, item in enumerate(value):
            _validate_schema(item, schema.get("items", {}), f"{path}[{index}]")
    elif expected == "string":
        if not isinstance(value, str):
            raise ValueError(f"{path} muss Text sein")
        if len(value) > min(schema.get("maxLength", 8000), 8000):
            raise ValueError(f"{path} ist zu lang")
        if "enum" in schema and value not in schema["enum"]:
            raise ValueError(f"{path} hat einen unzulaessigen Wert")
    elif expected == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{path} muss eine Ganzzahl sein")
        maximum = 100 if path.endswith(".limit") else 2_147_483_647
        if value < 1 or value > maximum:
            raise ValueError(f"{path} liegt ausserhalb des erlaubten Bereichs")
    elif expected == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{path} muss eine Zahl sein")
    elif expected == "boolean" and not isinstance(value, bool):
        raise ValueError(f"{path} muss boolesch sein")


def validate_tool_arguments(name: str, arguments: dict) -> None:
    if name not in _TOOL_SCHEMAS:
        raise ValueError("Unbekanntes Werkzeug")
    if not isinstance(arguments, dict):
        raise ValueError("Werkzeugargumente muessen ein Objekt sein")
    if len(json.dumps(arguments, ensure_ascii=False)) > 16000:
        raise ValueError("Werkzeugargumente sind zu gross")
    _validate_schema(arguments, _TOOL_SCHEMAS[name], name)


def tools_for(can_write: bool) -> list[dict]:
    """Die Werkzeugliste, die das Modell zu sehen bekommt.

    Fuer einen Betrachter werden die schreibenden Werkzeuge entfernt, statt sie erst
    beim Aufruf abzulehnen: sonst versucht das Modell den Aufruf und berichtet dem
    Nutzer hinterher von Aenderungen, die nie stattgefunden haben.
    """
    if can_write:
        return [
            tool
            for tool in RESPONSES_TOOL_DEFINITIONS
            if tool["name"] not in WRITE_TOOLS or tool["name"] in MODEL_ALLOWED_WRITE_TOOLS
        ]
    return [t for t in RESPONSES_TOOL_DEFINITIONS if t["name"] not in WRITE_TOOLS]


_CHART_TYPES = {"bar", "line", "pie", "doughnut"}


def _optional_id(value: int | None) -> int | None:
    """Modelle senden fuer ein nicht angegebenes optionales int-Feld oft `0`
    statt es wegzulassen. `0 is not None` ist wahr, also wuerde ein direktes
    Durchreichen an Paperless nach Korrespondent 0 filtern — den gibt es nie
    (IDs beginnen bei 1), das Ergebnis ist dann still und faelschlich leer."""
    return value or None

# Dieselbe nachsichtige Pruefung wie in models.py: interne Domains wie .local
# sind hier der Normalfall, nicht der Fehler.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Dieselbe Form, mit der mail/intake.py eine Tracking-ID aus einem Betreff liest.
_TRACKING_ID_RE = re.compile(r"AL-\d{4}-\d{4,}")


def _create_chart(arguments: dict) -> dict:
    chart_type = arguments.get("chart_type")
    labels = arguments.get("labels") or []
    datasets = arguments.get("datasets") or []

    if chart_type not in _CHART_TYPES:
        return {"error": f"chart_type muss eines von {sorted(_CHART_TYPES)} sein"}
    if not labels:
        return {"error": "labels darf nicht leer sein"}
    if not datasets:
        return {"error": "datasets darf nicht leer sein"}
    for ds in datasets:
        if len(ds.get("data", [])) != len(labels):
            return {"error": f"dataset '{ds.get('label')}' hat nicht so viele Werte wie labels"}

    return {
        "chart_type": chart_type,
        "title": arguments.get("title", ""),
        "labels": labels,
        "datasets": datasets,
        "x_label": arguments.get("x_label"),
        "y_label": arguments.get("y_label"),
    }


def _open_board(arguments: dict) -> dict:
    document_id = arguments.get("document_id")
    if not isinstance(document_id, int):
        return {"error": "document_id muss eine ganze Zahl sein"}
    return {
        "document_id": document_id,
        "title": arguments.get("title") or f"DOK-{document_id}",
    }


async def _search_documents_by_amount(arguments: dict, authorizer: ObjectAuthorizer) -> dict:
    limit = min(arguments.get("limit") or 10, 10)
    candidates = await paperless_client.list_all_documents(
        query=arguments.get("query"),
        correspondent__id=_optional_id(arguments.get("correspondent_id")),
        max_results=max(limit * 10, 100),
    )
    candidates["results"] = (await authorizer.filter_documents(candidates.get("results", [])))[:limit]
    min_amount = arguments.get("min_amount")
    max_amount = arguments.get("max_amount")

    matches = []
    for doc in candidates.get("results", []):
        amounts = await extract_amounts_llm(doc.get("content") or "")
        matched = [
            a
            for a in amounts
            if (min_amount is None or a["amount"] >= min_amount)
            and (max_amount is None or a["amount"] <= max_amount)
        ]
        if matched:
            matches.append({"id": doc["id"], "title": doc["title"], "amounts": matched})

    return {"checked": len(candidates.get("results", [])), "matches": matches}


async def _search_with_expansion(
    query: str | None, authorizer: ObjectAuthorizer, **filters
) -> dict:
    result = await paperless_client.list_all_documents(query=query, **filters)
    result["results"] = await authorizer.filter_documents(result.get("results", []))
    result["count"] = len(result["results"])

    if query and len(result.get("results", [])) < 3:
        variants = [v for v in await expand_search_terms(query) if v and v.lower() != query.lower()]
        if variants:
            seen_ids = {doc["id"] for doc in result["results"]}
            expanded_with = []
            for variant in variants:
                variant_result = await paperless_client.list_all_documents(query=variant, **filters)
                variant_result["results"] = await authorizer.filter_documents(
                    variant_result.get("results", [])
                )
                new_docs = [d for d in variant_result.get("results", []) if d["id"] not in seen_ids]
                if new_docs:
                    expanded_with.append(variant)
                    seen_ids.update(d["id"] for d in new_docs)
                    result["results"].extend(new_docs)
            if expanded_with:
                result["count"] = len(result["results"])
                result["expanded_with"] = expanded_with

    return result


async def _filter_documents_by_tag(
    tag_name: str, authorizer: ObjectAuthorizer
) -> dict:
    parsed_object = parse_object_tag(tag_name)
    if parsed_object and not authorizer.allows_object_code(parsed_object[0]):
        return {"error": f"Tag '{tag_name}' nicht gefunden"}
    tags = await paperless_client.list_tags()
    tag = next(
        (t for t in tags.get("results", []) if t["name"].lower() == tag_name.lower()),
        None,
    )
    if tag is None:
        return {"error": f"Tag '{tag_name}' nicht gefunden", "available_tags": [t["name"] for t in tags.get("results", [])]}
    result = await paperless_client.list_all_documents(tags__id__in=str(tag["id"]))
    result["results"] = await authorizer.filter_documents(result.get("results", []))
    result["count"] = len(result["results"])
    return result


async def _list_untagged_documents(
    limit: int | None, authorizer: ObjectAuthorizer
) -> dict:
    all_docs = await paperless_client.list_all_documents(max_results=1000)
    visible = await authorizer.filter_documents(all_docs.get("results", []))
    untagged = [doc for doc in visible if not doc.get("tags")]
    truncated = all_docs.get("truncated", False)
    if limit is not None and len(untagged) > limit:
        untagged = untagged[:limit]
        truncated = True
    return {"count": len(untagged), "results": untagged, "truncated": truncated}


async def _semantic_search_documents(arguments: dict, authorizer: ObjectAuthorizer) -> dict:
    query = arguments["query"]
    limit = arguments.get("limit") or 10
    embedding = await vectorstore.embed_query(query)
    candidates = await db.similarity_search(
        embedding,
        limit=max(limit * 10, 100),
        unrestricted=authorizer.unrestricted,
        object_codes=tuple(authorizer.principal.object_scope),
    )
    results = []
    for candidate in candidates:
        try:
            await authorizer.require_document(candidate["paperless_id"])
        except ObjectAccessDenied:
            continue
        results.append(candidate)
        if len(results) >= limit:
            break
    return {"results": results}


async def _assign_tags_to_document(
    document_id: int, tag_names: list[str], authorizer: ObjectAuthorizer
) -> dict:
    if not authorizer.unrestricted:
        return {"error": "Tagänderungen erfordern Zugriff auf alle Objekte."}
    if any(parse_object_tag(name) for name in tag_names):
        return {"error": "Objekt-Tags dürfen nicht über generische Werkzeuge geändert werden."}
    await authorizer.require_document(document_id)
    resolved = []
    for name in tag_names:
        tag = await _get_or_create(paperless_client.list_tags, paperless_client.create_tag, name)
        await authorizer.require_document(document_id)
        await paperless_client.bulk_edit([document_id], "add_tag", {"tag": tag["id"]})
        resolved.append(tag["name"])
    return {"updated": True, "document_id": document_id, "tags_assigned": resolved}


async def _set_document_correspondent(
    document_id: int, correspondent_name: str, authorizer: ObjectAuthorizer
) -> dict:
    correspondent = await _get_or_create(
        paperless_client.list_correspondents, paperless_client.create_correspondent, correspondent_name
    )
    await authorizer.require_document(document_id)
    await paperless_client.update_document(document_id, correspondent=correspondent["id"])
    return {"updated": True, "document_id": document_id, "correspondent": correspondent["name"]}


async def _set_document_document_type(
    document_id: int, document_type_name: str, authorizer: ObjectAuthorizer
) -> dict:
    document_type = await _get_or_create(
        paperless_client.list_document_types, paperless_client.create_document_type, document_type_name
    )
    await authorizer.require_document(document_id)
    await paperless_client.update_document(document_id, document_type=document_type["id"])
    return {"updated": True, "document_id": document_id, "document_type": document_type["name"]}


async def _delete_tag(tag_name: str) -> dict:
    tag = await _find_by_name(paperless_client.list_tags, tag_name)
    if tag is None:
        return {"error": f"Tag '{tag_name}' nicht gefunden"}
    await paperless_client.delete_tag(tag["id"])
    return {"deleted": tag_name}


async def _delete_correspondent(correspondent_name: str) -> dict:
    correspondent = await _find_by_name(paperless_client.list_correspondents, correspondent_name)
    if correspondent is None:
        return {"error": f"Korrespondent '{correspondent_name}' nicht gefunden"}
    await paperless_client.delete_correspondent(correspondent["id"])
    return {"deleted": correspondent_name}


async def _delete_document_type(document_type_name: str) -> dict:
    document_type = await _find_by_name(paperless_client.list_document_types, document_type_name)
    if document_type is None:
        return {"error": f"Dokumenttyp '{document_type_name}' nicht gefunden"}
    await paperless_client.delete_document_type(document_type["id"])
    return {"deleted": document_type_name}


async def _bulk_update_documents(arguments: dict, authorizer: ObjectAuthorizer) -> dict:
    document_ids = arguments["document_ids"]
    for document_id in document_ids:
        await authorizer.require_document(document_id)
    changed_tags = [
        *(arguments.get("add_tag_names") or []),
        *(arguments.get("remove_tag_names") or []),
    ]
    if changed_tags and not authorizer.unrestricted:
        return {"error": "Tagänderungen erfordern Zugriff auf alle Objekte."}
    if any(parse_object_tag(name) for name in changed_tags):
        return {"error": "Objekt-Tags dürfen nicht über Bulk-Werkzeuge geändert werden."}
    applied = []
    errors = []

    async def reauthorize() -> None:
        for document_id in document_ids:
            await authorizer.require_document(document_id)

    async def validate_tag(tag: dict) -> dict:
        current_tags = await paperless_client.list_tags()
        current = next(
            (item for item in current_tags.get("results", []) if item["id"] == tag["id"]),
            None,
        )
        if current is None or parse_object_tag(current.get("name", "")):
            raise ObjectAccessDenied
        return current

    for tag_name in arguments.get("add_tag_names") or []:
        tag = await _get_or_create(paperless_client.list_tags, paperless_client.create_tag, tag_name)
        tag = await validate_tag(tag)
        await reauthorize()
        await paperless_client.bulk_edit(document_ids, "add_tag", {"tag": tag["id"]})
        applied.append(f"add_tag: {tag['name']}")

    for tag_name in arguments.get("remove_tag_names") or []:
        tag = await _find_by_name(paperless_client.list_tags, tag_name)
        if tag is None:
            errors.append(f"Tag '{tag_name}' nicht gefunden, nicht entfernt")
            continue
        tag = await validate_tag(tag)
        await reauthorize()
        await paperless_client.bulk_edit(document_ids, "remove_tag", {"tag": tag["id"]})
        applied.append(f"remove_tag: {tag['name']}")

    correspondent_name = arguments.get("correspondent_name")
    if correspondent_name:
        correspondent = await _get_or_create(
            paperless_client.list_correspondents, paperless_client.create_correspondent, correspondent_name
        )
        await reauthorize()
        await paperless_client.bulk_edit(document_ids, "set_correspondent", {"correspondent": correspondent["id"]})
        applied.append(f"set_correspondent: {correspondent['name']}")

    document_type_name = arguments.get("document_type_name")
    if document_type_name:
        document_type = await _get_or_create(
            paperless_client.list_document_types, paperless_client.create_document_type, document_type_name
        )
        await reauthorize()
        await paperless_client.bulk_edit(document_ids, "set_document_type", {"document_type": document_type["id"]})
        applied.append(f"set_document_type: {document_type['name']}")

    return {"document_count": len(document_ids), "applied": applied, "errors": errors}


async def _prepare_email(arguments: dict, user_id: str | None, session_id: str | None) -> dict:
    subject = (arguments.get("subject") or "").strip()
    body = (arguments.get("body") or "").strip()
    case_tracking_id = (arguments.get("case_tracking_id") or "").strip()

    if not subject or not body:
        return {"error": "Betreff und Text duerfen nicht leer sein."}
    if user_id is None:
        return {"error": "Entwuerfe koennen nur im angemeldeten Chat erstellt werden."}

    # Die Tracking-ID muss ueber den gesamten Schriftwechsel im Betreff stehen,
    # sonst kann eine Antwort des Empfaengers spaeter nicht mehr automatisch
    # demselben Anliegen zugeordnet werden — auch nicht doppelt, falls sie
    # (z. B. bei einer Antwort auf eine Antwort) schon drinsteht.
    if case_tracking_id and not _TRACKING_ID_RE.search(subject):
        subject = f"[{case_tracking_id}] {subject}"

    draft = await db.create_email_draft(
        user_id=user_id,
        session_id=session_id,
        recipient="",
        subject=subject,
        body=body,
        document_id=arguments.get("document_id"),
    )
    # Das Modell bekommt ausdruecklich gesagt, dass nichts verschickt wurde —
    # sonst berichtet es dem Nutzer von einer Mail, die noch im Entwurf steht.
    return {
        "draft_id": draft["id"],
        "subject": draft["subject"],
        "sent": False,
        "note": "Entwurf angelegt. Der Empfaenger muss lokal vom Nutzer eingegeben werden; "
        "erst danach kann der Entwurf verschickt werden.",
    }


async def _get_case_detail(
    tracking_id: str,
    user_id: str | None,
    session_id: str | None,
    authorizer: ObjectAuthorizer,
) -> dict:
    """Dieselbe Zusammensetzung wie GET /cases/{tracking_id} — bewusst nicht neu
    erfunden, damit Chat-Agent und Anliegen-Seite dasselbe Bild eines Falls sehen."""
    case = await db.get_case(tracking_id)
    if case is None:
        return {"error": f"Kein Anliegen mit Tracking-ID '{tracking_id}' gefunden."}

    documents = []
    for reference in await db.list_case_documents(case["id"]):
        try:
            await authorizer.require_document(reference["paperless_id"])
        except ObjectAccessDenied:
            continue
        documents.append(reference)
    links = []
    for link in await db.list_case_links_for(tracking_id):
        dependent = await db.get_case(link["dependent_tracking_id"])
        prerequisite = await db.get_case(link["prerequisite_tracking_id"])
        if (
            dependent
            and prerequisite
            and authorizer.allows_object_code(dependent.get("object_code"))
            and authorizer.allows_object_code(prerequisite.get("object_code"))
        ):
            links.append(link)
    return {
        **case,
        "documents": documents,
        "events": await db.list_case_events(case["id"]),
        "notes": await db.list_case_notes(case["id"]),
        "links": links,
    }


async def _add_case_note(tracking_id: str, body: str, user_id: str | None, session_id: str | None) -> dict:
    case = await db.get_case(tracking_id)
    if case is None:
        return {"error": f"Kein Anliegen mit Tracking-ID '{tracking_id}' gefunden."}
    note = await db.add_case_note(case["id"], user_id, body)
    # Verweist auf die Notiz selbst statt auf die Chat-Sitzung — beim Lesen des
    # Zeitstrahls ist "wortlaut der Notiz ansehen" der naheliegendere Klick als
    # "die ganze Unterhaltung nachlesen".
    await db.add_case_event(
        case["id"],
        "note_added",
        detail=body[:200],
        actor_user_id=None,
        actor_label=_ACTOR_LABEL,
        link_kind="note",
        link_id=note["id"],
    )
    return {"added": True, "tracking_id": tracking_id, "note_id": note["id"]}


async def _close_case(tracking_id: str, user_id: str | None, session_id: str | None) -> dict:
    case = await db.close_case(tracking_id)
    if case is None:
        return {"error": f"Anliegen '{tracking_id}' nicht gefunden oder bereits geschlossen."}
    await db.add_case_event(
        case["id"], "closed", actor_user_id=None, actor_label=_ACTOR_LABEL, link_kind="session", link_id=session_id
    )
    return {"closed": True, "tracking_id": tracking_id}


async def _reopen_case(tracking_id: str, user_id: str | None, session_id: str | None) -> dict:
    case = await db.reopen_case(tracking_id)
    if case is None:
        return {"error": f"Anliegen '{tracking_id}' nicht gefunden oder bereits offen."}
    await db.add_case_event(
        case["id"], "reopened", actor_user_id=None, actor_label=_ACTOR_LABEL, link_kind="session", link_id=session_id
    )
    return {"reopened": True, "tracking_id": tracking_id}


async def _link_cases(
    dependent_tracking_id: str, prerequisite_tracking_id: str, user_id: str | None, session_id: str | None
) -> dict:
    link = await db.propose_case_link(dependent_tracking_id, prerequisite_tracking_id, proposed_by=user_id or "agent")
    if link is None:
        return {"error": "Eines der beiden Anliegen wurde nicht gefunden, oder die Verknuepfung besteht bereits."}
    # Sofort bestaetigt: eine ausdrueckliche, live erteilte Anweisung eines
    # angemeldeten Nutzers ist etwas anderes als der unbeaufsichtigte Vorschlag
    # der Aufnahme-Pipeline (mail/intake.py), der erst bestaetigt werden muss.
    await db.confirm_case_link(dependent_tracking_id, prerequisite_tracking_id)
    case = await db.get_case(dependent_tracking_id)
    if case is not None:
        await db.add_case_event(
            case["id"],
            "linked",
            detail=f"Haengt ab von {prerequisite_tracking_id}",
            actor_user_id=None,
            actor_label=_ACTOR_LABEL,
            link_kind="case",
            link_id=prerequisite_tracking_id,
        )
    return {"linked": True, "dependent_tracking_id": dependent_tracking_id, "prerequisite_tracking_id": prerequisite_tracking_id}


async def _unlink_cases(
    dependent_tracking_id: str, prerequisite_tracking_id: str, user_id: str | None, session_id: str | None
) -> dict:
    await db.remove_case_link(dependent_tracking_id, prerequisite_tracking_id)
    case = await db.get_case(dependent_tracking_id)
    if case is not None:
        await db.add_case_event(
            case["id"],
            "unlinked",
            detail=f"Nicht mehr abhaengig von {prerequisite_tracking_id}",
            actor_user_id=None,
            actor_label=_ACTOR_LABEL,
            link_kind="case",
            link_id=prerequisite_tracking_id,
        )
    return {"unlinked": True, "dependent_tracking_id": dependent_tracking_id, "prerequisite_tracking_id": prerequisite_tracking_id}


async def _attach_case_documents(
    tracking_id: str,
    document_ids: list[int],
    user_id: str | None,
    session_id: str | None,
    authorizer: ObjectAuthorizer,
) -> dict:
    """Dieselbe Verknuepfungslogik wie POST /cases/{tracking_id}/documents — ein
    Paperless-Tag mit dem Tracking-ID als Namen, damit Chat und Anliegen-Seite
    dieselbe Zuordnung sehen und sie in Paperless selbst sichtbar bleibt."""
    case = await db.get_case(tracking_id)
    if case is None:
        return {"error": f"Kein Anliegen mit Tracking-ID '{tracking_id}' gefunden."}
    tag = None
    if authorizer.unrestricted:
        tag = await _get_or_create(
            paperless_client.list_tags,
            lambda name: paperless_client.create_tag(name, color=CASE_TAG_COLOR),
            tracking_id,
        )
    attached = []
    for document_id in document_ids:
        try:
            document = await authorizer.require_document(document_id)
        except ObjectAccessDenied:
            continue
        current_tags = document.get("tags", [])
        if tag is not None and tag["id"] not in current_tags:
            await paperless_client.bulk_edit([document_id], "add_tag", {"tag": tag["id"]})
        await db.add_case_document(case["id"], document_id, role="linked")
        await db.add_case_event(
            case["id"],
            "linked",
            actor_user_id=None,
            actor_label=_ACTOR_LABEL,
            link_kind="document",
            link_id=str(document_id),
        )
        attached.append(document_id)
    return {"attached": attached, "tracking_id": tracking_id}


async def _detach_case_document(
    tracking_id: str,
    document_id: int,
    user_id: str | None,
    session_id: str | None,
    authorizer: ObjectAuthorizer,
) -> dict:
    case = await db.get_case(tracking_id)
    if case is None:
        return {"error": f"Kein Anliegen mit Tracking-ID '{tracking_id}' gefunden."}
    tag = (
        await _find_by_name(paperless_client.list_tags, tracking_id)
        if authorizer.unrestricted
        else None
    )
    if tag is not None:
        try:
            document = await authorizer.require_document(document_id)
        except ObjectAccessDenied:
            document = None
        if document is not None:
            await paperless_client.bulk_edit([document_id], "remove_tag", {"tag": tag["id"]})
    await db.remove_case_document(case["id"], document_id)
    await db.add_case_event(
        case["id"],
        "unlinked",
        actor_user_id=None,
        actor_label=_ACTOR_LABEL,
        link_kind="document",
        link_id=str(document_id),
    )
    return {"detached": True, "tracking_id": tracking_id, "document_id": document_id}


async def _call_tool(
    name: str,
    arguments: dict,
    can_write: bool = True,
    user_id: str | None = None,
    session_id: str | None = None,
    principal: Principal | None = None,
) -> dict:
    # Zweite Verteidigungslinie hinter tools_for: das Modell kann einen Werkzeugnamen
    # auch erfinden. Als Tool-Ergebnis statt als Exception, damit der Agent dem Nutzer
    # erklaeren kann, warum nichts passiert ist, statt den Stream abzubrechen.
    if not can_write and name in WRITE_TOOLS:
        return PERMISSION_DENIED
    if name in WRITE_TOOLS and name not in MODEL_ALLOWED_WRITE_TOOLS:
        return {
            "error": "Diese Aenderung muss ausserhalb des Sprachmodells gezielt bestaetigt werden."
        }
    if name not in {tool["name"] for tool in RESPONSES_TOOL_DEFINITIONS}:
        return {"error": f"unknown tool {name}"}

    if principal is None and name != "calculator":
        return {"error": "Objektzugriff konnte nicht geprüft werden."}
    authorizer = ObjectAuthorizer(principal) if principal else None

    document_id_tools = {
        "get_document",
        "extract_amounts",
        "assign_tags_to_document",
        "set_document_correspondent",
        "set_document_document_type",
        "rename_document",
        "open_board",
        "detach_case_document",
    }
    if name in document_id_tools and "document_id" in arguments:
        try:
            await authorizer.require_document(arguments["document_id"])
        except ObjectAccessDenied:
            return {"error": "Dokument nicht gefunden."}

    case_ids = []
    if "tracking_id" in arguments:
        case_ids.append(arguments["tracking_id"])
    if arguments.get("case_tracking_id"):
        case_ids.append(arguments["case_tracking_id"])
    case_ids.extend(
        arguments[key]
        for key in ("dependent_tracking_id", "prerequisite_tracking_id")
        if key in arguments
    )
    for tracking_id in case_ids:
        case = await db.get_case(tracking_id)
        if case is None or not authorizer.allows_object_code(case.get("object_code")):
            return {"error": f"Kein Anliegen mit Tracking-ID '{tracking_id}' gefunden."}

    for document_id in arguments.get("document_ids") or []:
        try:
            document = await authorizer.require_document(document_id)
        except ObjectAccessDenied:
            return {"error": f"Dokument {document_id} nicht gefunden."}
        if name == "attach_case_documents" and case_ids:
            case = await db.get_case(case_ids[0])
            codes = await authorizer.document_object_codes(document)
            if case and case.get("object_code") and codes != {case["object_code"]}:
                return {"error": f"Dokument {document_id} gehört nicht zum Objekt des Anliegens."}

    if not authorizer.unrestricted and name in {
        "create_tag",
        "create_correspondent",
        "create_document_type",
        "delete_tag",
        "delete_correspondent",
        "delete_document_type",
    }:
        return {"error": "Globale Metadaten dürfen nur mit Zugriff auf alle Objekte geändert werden."}

    if name == "prepare_email":
        if arguments.get("document_id"):
            try:
                await authorizer.require_document(arguments["document_id"])
            except ObjectAccessDenied:
                return {"error": "Dokument nicht gefunden."}
        return await _prepare_email(arguments, user_id, session_id)
    if name == "search_documents":
        return await _search_with_expansion(
            arguments.get("query"),
            authorizer,
            correspondent__id=_optional_id(arguments.get("correspondent_id")),
        )
    if name == "get_document":
        return await authorizer.require_document(arguments["document_id"])
    if name == "list_correspondents":
        documents = await _search_with_expansion(None, authorizer)
        used = {document.get("correspondent") for document in documents["results"]}
        response = await paperless_client.list_correspondents()
        response["results"] = _safe_metadata(
            [item for item in response.get("results", []) if item["id"] in used]
        )
        response["count"] = len(response["results"])
        return response
    if name == "list_document_types":
        documents = await _search_with_expansion(None, authorizer)
        used = {document.get("document_type") for document in documents["results"]}
        response = await paperless_client.list_document_types()
        response["results"] = _safe_metadata(
            [item for item in response.get("results", []) if item["id"] in used]
        )
        response["count"] = len(response["results"])
        return response
    if name == "calculator":
        try:
            return {"result": simple_eval(arguments["expression"])}
        except Exception as e:
            return {"error": str(e)}
    if name == "extract_amounts":
        doc = await authorizer.require_document(arguments["document_id"])
        return {"amounts": await extract_amounts_llm(doc.get("content") or "")}
    if name == "search_documents_by_amount":
        return await _search_documents_by_amount(arguments, authorizer)
    if name == "filter_documents_by_tag":
        return await _filter_documents_by_tag(arguments["tag_name"], authorizer)
    if name == "filter_documents_by_date_range":
        return await _search_with_expansion(
            arguments.get("query"),
            authorizer,
            created__date__gte=arguments.get("date_from"),
            created__date__lte=arguments.get("date_to"),
        )
    if name == "list_recent_documents":
        result = await _search_with_expansion(None, authorizer, ordering="-created")
        result["results"] = result["results"][: arguments.get("limit") or 10]
        result["count"] = len(result["results"])
        return result
    if name == "list_tags":
        documents = await _search_with_expansion(None, authorizer)
        used = {tag for document in documents["results"] for tag in document.get("tags") or []}
        response = await paperless_client.list_tags()
        response["results"] = _safe_metadata(
            [item for item in response.get("results", []) if item["id"] in used],
            include_color=True,
        )
        response["count"] = len(response["results"])
        return response
    if name == "list_untagged_documents":
        return await _list_untagged_documents(arguments.get("limit"), authorizer)
    if name == "semantic_search_documents":
        return await _semantic_search_documents(arguments, authorizer)
    if name == "create_tag":
        return await _get_or_create(
            paperless_client.list_tags,
            lambda n: paperless_client.create_tag(n, color=arguments.get("color")),
            arguments["name"],
        )
    if name == "create_correspondent":
        return await _get_or_create(
            paperless_client.list_correspondents, paperless_client.create_correspondent, arguments["name"]
        )
    if name == "create_document_type":
        return await _get_or_create(
            paperless_client.list_document_types, paperless_client.create_document_type, arguments["name"]
        )
    if name == "assign_tags_to_document":
        return await _assign_tags_to_document(
            arguments["document_id"], arguments["tag_names"], authorizer
        )
    if name == "set_document_correspondent":
        return await _set_document_correspondent(
            arguments["document_id"], arguments["correspondent_name"], authorizer
        )
    if name == "set_document_document_type":
        return await _set_document_document_type(
            arguments["document_id"], arguments["document_type_name"], authorizer
        )
    if name == "rename_document":
        await authorizer.require_document(arguments["document_id"])
        return await paperless_client.update_document(arguments["document_id"], title=arguments["title"])
    if name == "delete_tag":
        return await _delete_tag(arguments["tag_name"])
    if name == "delete_correspondent":
        return await _delete_correspondent(arguments["correspondent_name"])
    if name == "delete_document_type":
        return await _delete_document_type(arguments["document_type_name"])
    if name == "bulk_update_documents":
        try:
            return await _bulk_update_documents(arguments, authorizer)
        except ObjectAccessDenied:
            return {"error": "Mindestens ein Dokument wurde nicht gefunden."}
    if name == "create_chart":
        return _create_chart(arguments)
    if name == "open_board":
        return _open_board(arguments)
    if name == "search_cases":
        return {
            "results": [
                case
                for case in await db.search_cases(
                    arguments["query"],
                    arguments.get("status"),
                    unrestricted=authorizer.unrestricted,
                    object_codes=tuple(authorizer.principal.object_scope),
                )
                if authorizer.allows_object_code(case.get("object_code"))
            ]
        }
    if name == "get_case":
        return await _get_case_detail(
            arguments["tracking_id"], user_id, session_id, authorizer
        )
    if name == "list_object_cases":
        if not authorizer.allows_object_code(arguments["object_code"]):
            return {"results": []}
        return {"results": await db.list_cases_by_object_code(arguments["object_code"])}
    if name == "add_case_note":
        return await _add_case_note(arguments["tracking_id"], arguments["body"], user_id, session_id)
    if name == "close_case":
        return await _close_case(arguments["tracking_id"], user_id, session_id)
    if name == "reopen_case":
        return await _reopen_case(arguments["tracking_id"], user_id, session_id)
    if name == "link_cases":
        return await _link_cases(
            arguments["dependent_tracking_id"], arguments["prerequisite_tracking_id"], user_id, session_id
        )
    if name == "unlink_cases":
        return await _unlink_cases(
            arguments["dependent_tracking_id"], arguments["prerequisite_tracking_id"], user_id, session_id
        )
    if name == "attach_case_documents":
        return await _attach_case_documents(
            arguments["tracking_id"],
            arguments["document_ids"],
            user_id,
            session_id,
            authorizer,
        )
    if name == "detach_case_document":
        return await _detach_case_document(
            arguments["tracking_id"],
            arguments["document_id"],
            user_id,
            session_id,
            authorizer,
        )
    return {"error": f"unknown tool {name}"}


async def call_tool(
    name: str,
    arguments: dict,
    can_write: bool = True,
    user_id: str | None = None,
    session_id: str | None = None,
    principal: Principal | None = None,
) -> dict:
    if principal is None:
        return await _call_tool(
            name, arguments, can_write, user_id, session_id, principal
        )
    async with db.authorization_lease(
        principal.user_id,
        principal.role,
        principal.object_access_mode,
        principal.object_scope,
    ) as valid:
        if not valid:
            return {"error": "Der Objektzugriff oder die Rolle wurde geändert."}
        return await _call_tool(
            name, arguments, can_write, user_id, session_id, principal
        )
