import json

from ..openai_client import get_client

from ..config import settings


_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "extracted_amounts",
        "schema": {
            "type": "object",
            "properties": {
                "amounts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string", "description": "Kurze Bezeichnung, z. B. 'Gesamtbetrag', 'Mahngebuehr'"},
                            "amount": {"type": "number"},
                            "currency": {"type": "string", "description": "z. B. EUR"},
                        },
                        "required": ["label", "amount", "currency"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["amounts"],
            "additionalProperties": False,
        },
        "strict": True,
    },
}

_PROMPT = (
    "Analysiere den folgenden Dokumenttext (OCR, kann Fehler enthalten) und extrahiere "
    "alle darin vorkommenden Geldbetraege. Gib zu jedem Betrag eine kurze, aussagekraeftige "
    "Bezeichnung (z. B. 'Gesamtbetrag', 'Nebenkosten Nachzahlung', 'Mahngebuehr') sowie den "
    "Betrag als Zahl (Punkt als Dezimaltrennzeichen) und die Waehrung an. Wenn keine Betraege "
    "vorkommen, gib eine leere Liste zurueck.\n\nDokumenttext:\n"
)


async def extract_amounts_llm(text: str) -> list[dict]:
    completion = await get_client().chat.completions.create(
        model=settings.openai_model,
        messages=[{"role": "user", "content": _PROMPT + text[:12000]}],
        response_format=_SCHEMA,
    )
    content = completion.choices[0].message.content or "{}"
    data = json.loads(content)
    return data.get("amounts", [])
