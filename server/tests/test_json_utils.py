"""json_utils.dumps — die Absicherung dafür, dass ein roher Datenbank-Zeitstempel
in einem Agent-Werkzeugergebnis (SSE-Stream, function_call_output, mail/
case_agent.py's tool-Nachrichten) nicht mit einer TypeError abbricht. Genau das
ist zuvor bei jedem 'get_case'/'search_cases'-Aufruf passiert, weil asyncpg
TIMESTAMPTZ-Spalten als datetime-Objekte liefert und das nackte json-Modul die
nicht kennt (anders als FastAPIs eigener Response-Encoder für normale HTTP-
Antworten)."""

from datetime import date, datetime, timezone

import pytest

from app.json_utils import dumps


def test_datetime_becomes_iso_string():
    payload = {"created_at": datetime(2026, 8, 8, 12, 30, tzinfo=timezone.utc)}
    assert dumps(payload) == '{"created_at": "2026-08-08T12:30:00+00:00"}'


def test_date_becomes_iso_string():
    assert dumps({"due": date(2026, 8, 8)}) == '{"due": "2026-08-08"}'


def test_nested_datetime_in_list_of_dicts():
    payload = {
        "results": [
            {"tracking_id": "AL-2026-0001", "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc)},
            {"tracking_id": "AL-2026-0002", "created_at": None},
        ]
    }
    # Wirft nicht — das ist der eigentliche Regressionstest.
    dumps(payload)


def test_plain_values_unaffected():
    assert dumps({"a": 1, "b": "x", "c": None, "d": [1, 2, 3]}) == '{"a": 1, "b": "x", "c": null, "d": [1, 2, 3]}'


def test_unsupported_type_still_raises():
    class Unsupported:
        pass

    with pytest.raises(TypeError):
        dumps({"x": Unsupported()})
