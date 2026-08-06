import json

from ..openai_client import get_client

from ..config import settings
from ..models import ChatMessage


_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "suggested_prompts",
        "schema": {
            "type": "object",
            "properties": {
                "suggestions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 4,
                    "maxItems": 4,
                },
            },
            "required": ["suggestions"],
            "additionalProperties": False,
        },
        "strict": True,
    },
}

_PROMPT = (
    "Du hilfst einer Hausverwaltung, die mit einem Dokumenten-Assistenten (Paperless-ngx) chattet. "
    "Basierend auf dem bisherigen Gespraech, schlage genau 4 kurze, konkrete Folge-Prompts vor, die "
    "der Nutzer als naechstes anklicken koennte (in Ich-Form/Imperativ, auf Deutsch, je max. ca. 12 Woerter). "
    "Typische sinnvolle Richtungen: eine Antwort/einen Entwurf auf ein Schreiben formulieren, einen "
    "passenden Handwerker anhand frueherer Auftraege heraussuchen, die Korrespondenz zu einem Fall "
    "zusammenfassen, den letzten Kontakt mit einem Korrespondenten herausfinden, Kosten frueherer "
    "aehnlicher Reparaturen ermitteln oder ein Anliegen kostenmaessig einschaetzen. Waehle die 4 Vorschlaege "
    "so, dass sie zum tatsaechlichen Inhalt des Gespraechs passen (z. B. konkrete Namen/Themen aufgreifen), "
    "nicht generisch bleiben."
)


async def generate_suggestions(
    history: list[ChatMessage], last_user_message: str, last_assistant_message: str
) -> list[str]:
    transcript = "\n".join(f"{m.role}: {m.content}" for m in history)
    transcript += f"\nuser: {last_user_message}\nassistant: {last_assistant_message}"

    completion = await get_client().chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": _PROMPT},
            {"role": "user", "content": transcript[-8000:]},
        ],
        response_format=_SCHEMA,
    )
    content = completion.choices[0].message.content or "{}"
    data = json.loads(content)
    return data.get("suggestions", [])[:4]
