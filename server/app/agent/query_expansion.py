import json

from ..openai_client import get_client

from ..config import settings


_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "search_query_variants",
        "schema": {
            "type": "object",
            "properties": {
                "variants": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 5,
                },
            },
            "required": ["variants"],
            "additionalProperties": False,
        },
        "strict": True,
    },
}

_PROMPT = (
    "Du hilfst bei der Volltextsuche in Dokumenten einer Hausverwaltung (Paperless-ngx). "
    "Ein Suchbegriff hat wenige oder keine Treffer geliefert. Generiere bis zu 5 alternative "
    "Suchbegriffe, die dieselbe thematische Absicht abdecken, z. B.: deutsche Kompositum-/"
    "Rechtschreibvarianten (Fugen-s, z. B. 'Schadenmeldung' -> 'Schadensmeldung'), Singular/Plural, "
    "gaengige Synonyme sowie eng verwandte Fachbegriffe aus dem Hausverwaltungs-Kontext. Bleibe beim "
    "Thema des Suchbegriffs, erfinde keine unabhaengigen neuen Themen."
)


async def expand_search_terms(query: str) -> list[str]:
    completion = await get_client().chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": _PROMPT},
            {"role": "user", "content": query},
        ],
        response_format=_SCHEMA,
    )
    content = completion.choices[0].message.content or "{}"
    data = json.loads(content)
    return data.get("variants", [])[:5]
