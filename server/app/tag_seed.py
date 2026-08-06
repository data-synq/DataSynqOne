import logging

import httpx

from .paperless_client import paperless_client

logger = logging.getLogger(__name__)

TAXONOMY: list[tuple[str, str]] = [
    ("open", "#83afc2"),
    ("in-progress", "#d7c394"),
    ("done", "#527661"),
    ("urgent", "#a8443b"),
    ("overdue", "#8c3a32"),
    ("invoice", "#587d8d"),
    ("contract", "#456774"),
    ("maintenance-request", "#b59d68"),
    ("legal", "#304f5b"),
    ("correspondence", "#a8c5d2"),
    ("tenant-notice", "#d7c394"),
    ("insurance", "#718087"),
    ("utility-bill", "#83afc2"),
]

STATUS_TAGS = {"open", "in-progress", "done", "urgent", "overdue"}


async def seed_tags() -> None:
    """Ensure the tag taxonomy exists in Paperless.

    Best effort: this runs at startup and must never prevent the app from booting,
    so Paperless being unreachable or rejecting our token is logged, not raised.
    """
    try:
        existing = {t["name"] for t in (await paperless_client.list_tags()).get("results", [])}
    except httpx.HTTPError as exc:
        logger.warning("Tag taxonomy not seeded, could not list Paperless tags: %s", exc)
        return

    for name, color in TAXONOMY:
        if name in existing:
            continue
        try:
            await paperless_client.create_tag(name, color=color)
        except httpx.HTTPError as exc:
            logger.warning("Could not create Paperless tag %r: %s", name, exc)
