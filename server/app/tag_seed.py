from .paperless_client import paperless_client

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
    existing = {t["name"] for t in (await paperless_client.list_tags()).get("results", [])}
    for name, color in TAXONOMY:
        if name not in existing:
            await paperless_client.create_tag(name, color=color)
