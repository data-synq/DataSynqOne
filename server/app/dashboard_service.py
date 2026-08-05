import re
from datetime import date, datetime, timedelta

from .dashboard_models import ChartData, DashboardOverview, Deadline, DocSummary, TagRef
from .paperless_client import paperless_client
from .tag_seed import STATUS_TAGS

_DUE_RE = re.compile(r"^due:(\d{4}-\d{2}-\d{2})$")

_STATUS_PRIORITY = ["overdue", "urgent", "in-progress", "open", "done"]


def parse_due_tag(tag_name: str) -> date | None:
    match = _DUE_RE.match(tag_name)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


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
) -> DocSummary:
    tag_refs = [tags_by_id[tid] for tid in doc.get("tags") or [] if tid in tags_by_id]
    tag_names = {t.name for t in tag_refs}

    due_date: date | None = None
    for t in tag_refs:
        parsed = parse_due_tag(t.name)
        if parsed is not None:
            due_date = parsed
            break

    status = next((s for s in _STATUS_PRIORITY if s in tag_names), None)
    if status is None:
        status = "untagged"
    elif status != "done" and due_date is not None and due_date < date.today():
        status = "overdue"

    return DocSummary(
        id=doc["id"],
        title=doc.get("title") or f"Dokument {doc['id']}",
        created=doc.get("created") or "",
        correspondent_name=correspondents_by_id.get(doc.get("correspondent")),
        document_type_name=document_types_by_id.get(doc.get("document_type")),
        tags=tag_refs,
        status=status,
        due_date=due_date.isoformat() if due_date else None,
        content=doc.get("content"),
    )


async def get_document_detail(document_id: int) -> DocSummary:
    tags_by_id, correspondents_by_id, document_types_by_id = await _load_lookups()
    doc = await paperless_client.get_document(document_id)
    return resolve_document(doc, tags_by_id, correspondents_by_id, document_types_by_id)


async def get_overview() -> DashboardOverview:
    tags_by_id, correspondents_by_id, document_types_by_id = await _load_lookups()
    all_docs = await paperless_client.list_all_documents(
        ordering="-created", max_results=1000, max_pages=40
    )

    summaries = [
        resolve_document(doc, tags_by_id, correspondents_by_id, document_types_by_id)
        for doc in all_docs.get("results", [])
    ]

    by_status: dict[str, list[DocSummary]] = {"open": [], "urgent": [], "overdue": []}
    for s in summaries:
        if s.status in by_status:
            by_status[s.status].append(s)

    STATUS_DISPLAY_LIMIT = 6
    kpi_counts = {status: len(docs) for status, docs in by_status.items()}
    by_status = {status: docs[:STATUS_DISPLAY_LIMIT] for status, docs in by_status.items()}

    deadlines: list[Deadline] = []
    today = date.today()
    for s in summaries:
        if not s.due_date:
            continue
        due = date.fromisoformat(s.due_date)
        deadlines.append(
            Deadline(
                document_id=s.id,
                title=s.title,
                correspondent_name=s.correspondent_name,
                due_date=s.due_date,
                days_until=(due - today).days,
            )
        )
    deadlines.sort(key=lambda d: d.due_date)

    months: list[str] = []
    cursor = today.replace(day=1)
    for _ in range(12):
        months.append(cursor.strftime("%Y-%m"))
        prev_month_end = cursor - timedelta(days=1)
        cursor = prev_month_end.replace(day=1)
    months.reverse()
    month_counts = {m: 0 for m in months}
    for s in summaries:
        if not s.created:
            continue
        try:
            month_key = s.created[:7]
        except Exception:
            continue
        if month_key in month_counts:
            month_counts[month_key] += 1

    status_labels = ["open", "in-progress", "done", "urgent", "overdue", "untagged"]
    status_counts = {label: 0 for label in status_labels}
    for s in summaries:
        if s.status in status_counts:
            status_counts[s.status] += 1

    seven_days_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
    recent_7d = sum(1 for s in summaries if s.created and s.created >= seven_days_ago)

    kpis = {
        "open": kpi_counts["open"],
        "overdue": kpi_counts["overdue"],
        "urgent": kpi_counts["urgent"],
        "untagged": status_counts["untagged"],
        "recent_7d": recent_7d,
    }

    return DashboardOverview(
        kpis=kpis,
        by_status=by_status,
        deadlines=deadlines,
        recent=summaries[:8],
        charts={
            "documents_over_time": ChartData(labels=months, data=[month_counts[m] for m in months]),
            "status_distribution": ChartData(
                labels=status_labels, data=[status_counts[label] for label in status_labels]
            ),
        },
        generated_at=datetime.utcnow().isoformat(),
    )
