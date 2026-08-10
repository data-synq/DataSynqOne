"""JSON-Serialisierung für Werkzeug-Ergebnisse, die roh aus der Datenbank kommen.

asyncpg liefert TIMESTAMPTZ/DATE-Spalten als echte datetime/date-Objekte
zurueck, nicht als Text — json.dumps() kennt die nicht und wirft eine
TypeError. Fuer normale HTTP-Antworten faengt FastAPIs eigener Encoder das ab,
aber der Agent-Werkzeug-Pfad (SSE-Stream in routers/agent.py, das
function_call_output in agent/runner.py, das 'tool'-Nachrichten-Content in
mail/case_agent.py) serialisiert mit dem nackten json-Modul. Ein einziger,
datetime-fähiger default() hier deckt alle drei Stellen ab, statt jede
Datenbankfunktion einzeln um ::text-Casts zu ergaenzen und beim naechsten
neuen Feld denselben Fehler zu riskieren.
"""

import json
from datetime import date, datetime
from typing import Any


def _default(obj: Any) -> str:
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def dumps(value: Any, **kwargs) -> str:
    return json.dumps(value, default=_default, **kwargs)
