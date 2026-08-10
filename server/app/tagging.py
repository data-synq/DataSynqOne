"""Get-or-create-by-name helpers for Paperless tags/correspondents/document types.

Shared between the interactive chat agent (`agent/tools.py`) and the mail intake
pipeline (`mail/intake.py`, `mail/case_agent.py`) — both resolve names to Paperless
objects the same way, so the logic lives here once instead of being duplicated
across two modules with different trust boundaries.
"""


# Eigene Farbe, damit ein Anliegen-Tag sich in Paperless optisch von der
# Taxonomie aus tag_seed.py (Status/Kategorie) abhebt. Gemeinsam genutzt von
# routers/cases.py und agent/tools.py, damit beide denselben Tag mit derselben
# Farbe anlegen statt zwei Konstanten auseinanderdriften zu lassen.
CASE_TAG_COLOR = "#6b5b95"


async def get_or_create(list_fn, create_fn, name: str) -> dict:
    existing = await list_fn()
    match = next(
        (item for item in existing.get("results", []) if item["name"].lower() == name.lower()),
        None,
    )
    if match is not None:
        return match
    return await create_fn(name)


async def find_by_name(list_fn, name: str) -> dict | None:
    existing = await list_fn()
    return next(
        (item for item in existing.get("results", []) if item["name"].lower() == name.lower()),
        None,
    )
