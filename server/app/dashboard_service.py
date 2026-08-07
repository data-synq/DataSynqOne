import re
from datetime import UTC, date, datetime, timedelta

from .dashboard_models import ChartData, DashboardOverview, Deadline, DocSummary, TagRef
from .paperless_client import paperless_client
from .tag_seed import CATEGORY_TAGS, STATUS_TAGS

_DUE_RE = re.compile(r"^due:(\d{4}-\d{2}-\d{2})$")
# Paperless kennt keine Liegenschaft. Die Zuordnung läuft über eine Tag-
# Konvention, wie die Frist auch — im Bestand steht sie als `OBJ-001` und
# daneben als `OBJ-001 Musterhof 1`. Beide meinen dasselbe Objekt, deshalb
# trennt der Ausdruck Kennung und Klartextnamen: über die Kennung wird
# gruppiert, der Name ist nur die schönere Beschriftung.
_OBJ_RE = re.compile(r"^(obj-[\w.]+)(?:\s+(.*))?$", re.IGNORECASE)

_STATUS_PRIORITY = ["overdue", "urgent", "in-progress", "open", "done"]

# Was in "Als Nächstes" auftaucht, und in welcher Reihenfolge.
_QUEUE_STATUSES = ["overdue", "urgent", "open"]

# Beide Listen filtert die Oberfläche noch einmal nach Objekt. Sie müssen
# deshalb spürbar mehr enthalten als die paar Zeilen, die am Ende zu sehen
# sind — sonst filtert man einen bereits abgeschnittenen Kopf.
_QUEUE_LIMIT = 40
_RECENT_LIMIT = 24


def _created_date(created: str) -> date | None:
    """Der Kalendertag aus einem Paperless-`created`.

    Die Zeitstempel tragen einen Zonenversatz ("...+02:00"); nur die ersten
    zehn Zeichen zu nehmen ist hier richtig, weil Paperless das Datum bereits
    in lokaler Zeit ausliefert und ein Vorgang am Tag zählt, an dem er ankam.
    """
    if not created:
        return None
    try:
        return date.fromisoformat(created[:10])
    except ValueError:
        return None


def parse_due_tag(tag_name: str) -> date | None:
    match = _DUE_RE.match(tag_name)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def parse_object_tag(tag_name: str) -> tuple[str, str | None] | None:
    """Kennung und Klartextname eines Objekt-Tags, oder None.

    `OBJ-001`             -> ("OBJ-001", None)
    `OBJ-001 Musterhof 1` -> ("OBJ-001", "Musterhof 1")
    """
    match = _OBJ_RE.match(tag_name)
    if not match:
        return None
    label = (match.group(2) or "").strip()
    return match.group(1).upper(), label or None


def build_object_labels(tags_by_id: dict[int, TagRef]) -> dict[str, str]:
    """Kennung -> Beschriftung, über den gesamten Tag-Bestand.

    Muss global gebaut werden, nicht je Dokument: trägt eine Akte nur
    `OBJ-001` und die nächste `OBJ-001 Musterhof 1`, gehören beide zum selben
    Objekt. Würde jedes Dokument für sich beschriftet, stünden in der
    Filterzeile zwei Einträge für ein Haus.
    """
    labels: dict[str, str] = {}
    for tag in tags_by_id.values():
        parsed = parse_object_tag(tag.name)
        if parsed is None:
            continue
        code, name = parsed
        if name or code not in labels:
            labels[code] = name or code
    return labels


def _has_topic_tag(summary: DocSummary) -> bool:
    """Trägt das Dokument ein inhaltliches Schlagwort?

    Status-Tags und die Konventionen `due:`/`OBJ-` zählen nicht: sie sagen,
    wo ein Vorgang steht und wohin er gehört, nicht worum es geht.
    """
    return any(
        t.name not in STATUS_TAGS
        and parse_due_tag(t.name) is None
        and parse_object_tag(t.name) is None
        for t in summary.tags
    )


async def _load_lookups() -> tuple[dict[int, TagRef], dict[int, str], dict[int, str]]:
    tags_resp = await paperless_client.list_tags()
    correspondents_resp = await paperless_client.list_correspondents()
    document_types_resp = await paperless_client.list_document_types()
    tags_by_id = {
        t["id"]: TagRef(id=t["id"], name=t["name"], color=t.get("color") or "#87979d")
        for t in tags_resp.get("results", [])
    }
    correspondents_by_id = {c["id"]: c["name"] for c in correspondents_resp.get("results", [])}
    document_types_by_id = {d["id"]: d["name"] for d in document_types_resp.get("results", [])}
    return tags_by_id, correspondents_by_id, document_types_by_id


def resolve_document(
    doc: dict,
    tags_by_id: dict[int, TagRef],
    correspondents_by_id: dict[int, str],
    document_types_by_id: dict[int, str],
    object_labels: dict[str, str],
    *,
    with_content: bool = True,
) -> DocSummary:
    tag_refs = [tags_by_id[tid] for tid in doc.get("tags") or [] if tid in tags_by_id]
    tag_names = {t.name for t in tag_refs}

    due_date: date | None = None
    object_code: str | None = None
    for t in tag_refs:
        if due_date is None:
            due_date = parse_due_tag(t.name)
        if object_code is None:
            parsed = parse_object_tag(t.name)
            if parsed is not None:
                object_code = parsed[0]

    status = next((s for s in _STATUS_PRIORITY if s in tag_names), None)
    if status is None:
        status = "untagged"
    elif status != "done" and due_date is not None and due_date < date.today():
        status = "overdue"

    # Trägt ein Dokument mehrere Kategorien, gewinnt die erste der Taxonomie.
    # Eine Rechnung, die zugleich Rechtliches ist, gehört in die Ablage der
    # Rechnungen — dort sucht sie jemand.
    category = next((c for c in CATEGORY_TAGS if c in tag_names), None)

    return DocSummary(
        id=doc["id"],
        title=doc.get("title") or f"Dokument {doc['id']}",
        created=doc.get("created") or "",
        correspondent_name=correspondents_by_id.get(doc.get("correspondent")),
        document_type_name=document_types_by_id.get(doc.get("document_type")),
        category=category,
        object_name=object_labels.get(object_code) if object_code else None,
        tags=tag_refs,
        status=status,
        due_date=due_date.isoformat() if due_date else None,
        content=doc.get("content") if with_content else None,
    )


async def get_document_detail(document_id: int) -> DocSummary:
    tags_by_id, correspondents_by_id, document_types_by_id = await _load_lookups()
    doc = await paperless_client.get_document(document_id)
    return resolve_document(
        doc,
        tags_by_id,
        correspondents_by_id,
        document_types_by_id,
        build_object_labels(tags_by_id),
    )


async def get_overview() -> DashboardOverview:
    tags_by_id, correspondents_by_id, document_types_by_id = await _load_lookups()
    all_docs = await paperless_client.list_all_documents(
        ordering="-created", max_results=1000, max_pages=40
    )

    object_labels = build_object_labels(tags_by_id)
    # Ohne Volltext: die Übersicht schickt bis zu 64 Dokumente, und der
    # OCR-Inhalt eines einzelnen ist größer als alle Kennzahlen zusammen.
    # Wer den Text braucht, öffnet die Akte — dort liefert ihn /detail.
    summaries = [
        resolve_document(
            doc,
            tags_by_id,
            correspondents_by_id,
            document_types_by_id,
            object_labels,
            with_content=False,
        )
        for doc in all_docs.get("results", [])
    ]

    today = date.today()

    status_counts: dict[str, int] = {}
    for s in summaries:
        status_counts[s.status] = status_counts.get(s.status, 0) + 1

    # "Als Nächstes": eine Liste über alle drei offenen Zustände, sortiert nach
    # Dringlichkeit und dann nach Frist. Dokumente ohne Frist stehen hinter
    # denen mit — ohne Datum gibt es keinen Grund, sie vorzuziehen. Innerhalb
    # gleicher Frist bleibt die Reihenfolge von Paperless (ordering="-created")
    # erhalten, weil Pythons sort stabil ist.
    queue = sorted(
        (s for s in summaries if s.status in _QUEUE_STATUSES),
        key=lambda s: (_QUEUE_STATUSES.index(s.status), s.due_date or "9999-12-31"),
    )[:_QUEUE_LIMIT]

    objects = sorted({s.object_name for s in summaries if s.object_name})

    # Erledigte Vorgänge tragen ihre Frist weiter, aber sie ist keine mehr.
    # Ohne diesen Filter füllt sich "Überschritten" mit abgehakter Arbeit und
    # die Gruppe verliert genau die Bedeutung, für die sie da ist.
    deadlines: list[Deadline] = []
    for s in summaries:
        if not s.due_date or s.status == "done":
            continue
        due = date.fromisoformat(s.due_date)
        deadlines.append(
            Deadline(
                document_id=s.id,
                title=s.title,
                correspondent_name=s.correspondent_name,
                object_name=s.object_name,
                due_date=s.due_date,
                days_until=(due - today).days,
            )
        )
    deadlines.sort(key=lambda d: d.due_date)

    # Acht Kalenderwochen rückwärts, jüngste rechts.
    week_starts = [
        today - timedelta(days=today.weekday()) - timedelta(weeks=offset)
        for offset in range(7, -1, -1)
    ]
    week_counts = {ws: 0 for ws in week_starts}
    for s in summaries:
        created = _created_date(s.created)
        if created is None:
            continue
        week_start = created - timedelta(days=created.weekday())
        if week_start in week_counts:
            week_counts[week_start] += 1

    # Kategorien der letzten 60 Tage: Top 5, der Rest sammelt sich unter
    # "Sonstige" — dort landen auch die Dokumente ohne Kategorie, die genau
    # das sind. Die Beschriftung der Schlüssel macht die Oberfläche.
    sixty_days_ago = today - timedelta(days=60)
    category_counts: dict[str, int] = {}
    uncategorized = 0
    for s in summaries:
        created = _created_date(s.created)
        if created is None or created < sixty_days_ago:
            continue
        if s.category:
            category_counts[s.category] = category_counts.get(s.category, 0) + 1
        else:
            uncategorized += 1
    ranked = sorted(category_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    other = uncategorized + sum(count for _, count in ranked[5:])
    category_labels = [label for label, _ in ranked[:5]]
    category_data = [count for _, count in ranked[:5]]
    if other:
        category_labels.append("__other__")
        category_data.append(other)

    seven_days_ago = today - timedelta(days=7)
    recent_docs = [s for s in summaries if (d := _created_date(s.created)) and d >= seven_days_ago]

    overdue_days = [-d.days_until for d in deadlines if d.days_until < 0]

    kpis = {
        "open": status_counts.get("open", 0),
        "urgent": status_counts.get("urgent", 0),
        "overdue": status_counts.get("overdue", 0),
        "untagged": status_counts.get("untagged", 0),
        "recent_7d": len(recent_docs),
        "total": all_docs.get("count", len(summaries)),
        # Die Unterzeilen der Kennzahlen. Zahlen, keine Sätze: wie daraus
        # "+6 diese Woche" wird, entscheidet die Oberfläche.
        "open_new_7d": sum(1 for s in recent_docs if s.status == "open"),
        "urgent_new_today": sum(
            1 for s in summaries if s.status == "urgent" and _created_date(s.created) == today
        ),
        "overdue_oldest_days": max(overdue_days, default=0),
        "recent_7d_tagged": sum(1 for s in recent_docs if _has_topic_tag(s)),
    }

    return DashboardOverview(
        kpis=kpis,
        queue=queue,
        objects=objects,
        deadlines=deadlines,
        recent=summaries[:_RECENT_LIMIT],
        charts={
            "documents_per_week": ChartData(
                labels=[f"KW {ws.isocalendar().week:02d}" for ws in week_starts],
                data=[week_counts[ws] for ws in week_starts],
            ),
            "category_distribution": ChartData(labels=category_labels, data=category_data),
        },
        generated_at=datetime.now(UTC).isoformat(),
    )
