"""Verarbeitet die von der Paperless-Mailregel abgelegten 'correspondence'-
Dokumente weiter: Freigabe-Gate, Spam-/Injection-Erkennung, Fallanlage.

Ablauf pro Dokument, streng in dieser Reihenfolge:
1. Anhang-Sicherheitssperre (Makro-/Ausfuehrbar-Formate) — greift vor allem anderen.
2. Absenderadresse aus dem Inhalt ziehen, Freigabestatus pruefen. Ist der Absender
   nicht (mehr) freigegeben, geht der Inhalt NIE an ein Sprachmodell — das Gate
   blockiert vor dem Modellaufruf, nicht nur vor der Fallanlage.
3. Tracking-ID im Betreff? Dann an das bestehende Anliegen anhaengen statt ein
   neues anzulegen.
4. Sonst: lesende Fallanalyse (case_agent.analyze), danach eine Durchsetzungsebene
   in reinem Code, die jedes Feld gegen feste Regeln prueft, bevor irgendetwas
   geschrieben wird — das Modellergebnis ist ein Vorschlag, kein Befehl.
"""

import asyncio
import logging
import re
import uuid
from datetime import date, timedelta
from email.parser import Parser
from email.utils import parseaddr

import httpx

from .. import db
from ..ai_privacy import redact_text
from ..config import settings
from ..paperless_client import paperless_client
from ..tagging import get_or_create
from . import case_agent

logger = logging.getLogger(__name__)

_TICK_SECONDS_FALLBACK = 300

_BLOCKED_ATTACHMENT_EXTENSIONS = (
    ".docm", ".xlsm", ".pptm", ".exe", ".bat", ".cmd", ".com", ".ps1", ".vbs", ".js",
    ".jar", ".msi", ".scr", ".hta", ".html", ".htm", ".svg", ".zip", ".rar", ".7z",
)

_TRACKING_RE = re.compile(r"\[?(AL-\d{4}-\d{4,})\]?")
_OBJECT_CODE_RE = re.compile(r"^OBJ-\d+$", re.IGNORECASE)
_HEADER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]{0,63}:")

TAG_CORRESPONDENCE = "correspondence"
TAG_ANLIEGEN = "anliegen"
TAG_SPAM = "spam-verdacht"
TAG_PENDING = "warten-auf-freigabe"
# Bereits abschliessend behandelte Dokumente — bei einem erneuten Durchlauf
# uebersprungen, damit dieselbe Mail nicht zweimal klassifiziert/verlinkt wird.
_FINAL_TAGS = frozenset({TAG_ANLIEGEN, TAG_SPAM})

_ALLOWED_STATUSES = frozenset({"open", "urgent"})
_SIBLING_WINDOW_MINUTES = 15
# Akteur-Label fuer alles, was diese Pipeline auf dem Zeitstrahl eines Anliegens
# vermerkt — es gibt hier keinen angemeldeten Nutzer, der die Aenderung ausloest.
_ACTOR_LABEL = "Posteingang (automatisch)"


def extract_sender_email(content: str) -> str | None:
    """Read From only from the leading RFC-style header block, never from body/OCR text."""
    header_lines: list[str] = []
    for line in (content or "")[:16384].splitlines()[:100]:
        if not line.strip():
            break
        if _HEADER_RE.match(line) or (header_lines and line[:1].isspace()):
            header_lines.append(line)
            continue
        break
    if not header_lines:
        return None
    address = parseaddr(Parser().parsestr("\n".join(header_lines)).get("From", ""))[1]
    address = address.strip().lower()
    return address if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", address) else None


def contains_prompt_injection(content: str) -> bool:
    _redacted, classes = redact_text(content[: settings.mail_intake_max_chars])
    return bool(classes.get("PROMPT_INJECTION"))


def extract_tracking_id(title: str) -> str | None:
    match = _TRACKING_RE.search(title or "")
    return match.group(1) if match else None


def _is_blocked_attachment(doc: dict) -> bool:
    name = (doc.get("original_file_name") or doc.get("title") or "").lower()
    return any(name.endswith(ext) for ext in _BLOCKED_ATTACHMENT_EXTENSIONS)


def _build_correspondent_email_map(docs: list[dict]) -> dict[int, str]:
    """Anhaenge tragen selbst keinen 'From:'-Header — aber Paperless setzt ihren
    Korrespondenten (wie bei der zugehoerigen .eml) aus demselben Absendernamen.
    Ueber die .eml-Dokumente derselben Korrespondenten-ID laesst sich die Adresse
    auch fuer die Anhaenge auflösen."""
    mapping: dict[int, str] = {}
    for doc in docs:
        cid = doc.get("correspondent")
        if cid is None or cid in mapping:
            continue
        email = extract_sender_email(doc.get("content") or "")
        if email:
            mapping[cid] = email
    return mapping


async def _tag_ids_by_name() -> dict[str, int]:
    tags = (await paperless_client.list_tags()).get("results", [])
    return {t["name"]: t["id"] for t in tags}


async def _apply_tags(doc: dict, add: set[str], remove: set[str], tag_ids: dict[str, int]) -> None:
    """Additiv/entfernend auf Basis der bereits geladenen Dokument-Tags — kein
    zusaetzlicher Round-Trip zu Paperless, um den aktuellen Tag-Stand zu holen."""
    current = set(doc.get("tags") or [])
    for name in add:
        tag = await get_or_create(paperless_client.list_tags, paperless_client.create_tag, name)
        tag_ids.setdefault(name, tag["id"])
        current.add(tag["id"])
    for name in remove:
        tag_id = tag_ids.get(name)
        if tag_id is not None:
            current.discard(tag_id)
    await paperless_client.update_document(doc["id"], tags=list(current))


def _validate_due_date(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        return None
    today = date.today()
    if parsed < today - timedelta(days=1) or parsed > today + timedelta(days=730):
        return None
    return parsed.isoformat()


def _validate_object_code(raw: str | None, tag_ids: dict[str, int]) -> str | None:
    """Nur ein Code, der schon irgendwo in Paperless als Tag existiert (bar oder mit
    Beschriftung, siehe dashboard_service.parse_object_tag), gilt als bestaetigt —
    ein aus dem E-Mail-Text frei erfundener Code wird nie als neuer Tag angelegt.
    Zurueckgegeben wird immer die blanke Form ('OBJ-003'), passend zur bestehenden
    Konvention aus blankem Tag + einem beschrifteten Tag pro Objekt."""
    if not raw or not _OBJECT_CODE_RE.match(raw.strip()):
        return None
    code = raw.strip().upper()
    for name in tag_ids:
        upper_name = name.upper()
        if upper_name == code or upper_name.startswith(code + " "):
            return code
    return None


async def poll_once() -> dict:
    counts = {
        "checked": 0,
        "blocked_attachment": 0,
        "pending_sender": 0,
        "appended": 0,
        "cases_created": 0,
        "spam": 0,
        "errors": 0,
    }

    tag_ids = await _tag_ids_by_name()
    correspondence_id = tag_ids.get(TAG_CORRESPONDENCE)
    if correspondence_id is None:
        logger.info("Anliegen-Aufnahme: Tag 'correspondence' existiert noch nicht, überspringe.")
        return counts

    try:
        page = await paperless_client.list_all_documents(
            tags__id__in=str(correspondence_id),
            ordering="created",
            max_results=100000,
            max_pages=1000,
        )
    except httpx.HTTPError as exc:
        logger.warning("Anliegen-Aufnahme: Dokumentliste konnte nicht geladen werden: %s", exc)
        return counts

    docs = page.get("results", [])
    correspondent_emails = _build_correspondent_email_map(docs)

    for doc in docs:
        doc_tag_names = {name for name, tid in tag_ids.items() if tid in set(doc.get("tags") or [])}
        if doc_tag_names & _FINAL_TAGS:
            continue

        counts["checked"] += 1
        claim_owner = str(uuid.uuid4())
        claimed = await db.claim_mail_intake_document(doc["id"], claim_owner)
        if not claimed:
            continue
        try:
            completed = await _process_document(
                doc, doc_tag_names, tag_ids, correspondent_emails, counts, claim_owner
            )
        except Exception:
            logger.exception("Anliegen-Aufnahme: Verarbeitung von Dokument %s fehlgeschlagen.", doc.get("id"))
            counts["errors"] += 1
            await db.release_mail_intake_document(doc["id"], claim_owner)
        else:
            if completed:
                await db.complete_mail_intake_document(doc["id"], claim_owner)
            else:
                await db.release_mail_intake_document(doc["id"], claim_owner)

    return counts


async def _process_document(
    doc: dict,
    current_tags: set[str],
    tag_ids: dict[str, int],
    correspondent_emails: dict[int, str],
    counts: dict,
    claim_owner: str = "",
) -> bool:
    if _is_blocked_attachment(doc):
        await _apply_tags(doc, {TAG_SPAM}, {TAG_PENDING}, tag_ids)
        counts["blocked_attachment"] += 1
        return True

    content = doc.get("content") or ""
    own_email = extract_sender_email(content)
    sender_email = own_email or correspondent_emails.get(doc.get("correspondent"))

    if sender_email:
        await db.upsert_pending_sender(sender_email)

    if not sender_email or not await db.is_sender_trusted(sender_email):
        if TAG_PENDING not in current_tags:
            await _apply_tags(doc, {TAG_PENDING}, set(), tag_ids)
        counts["pending_sender"] += 1
        return False

    if contains_prompt_injection(content):
        await _apply_tags(doc, {TAG_SPAM}, {TAG_PENDING}, tag_ids)
        counts["spam"] += 1
        return True

    # Ohne unveraenderliche Message-/MIME-ID ist eine zeitbasierte Zuordnung zu
    # einem Fall nicht sicher. Solche Anhaenge bleiben bis zur manuellen Pruefung liegen.
    if not own_email:
        if TAG_PENDING not in current_tags:
            await _apply_tags(doc, {TAG_PENDING}, set(), tag_ids)
        counts["pending_sender"] += 1
        return False

    tracking_id = extract_tracking_id(doc.get("title") or "")
    if tracking_id:
        case = await db.get_case(tracking_id)
        if case is not None and (case.get("sender_email") or "").lower() == sender_email:
            decision = await case_agent.analyze(content[: settings.mail_intake_max_chars], sender_email)
            if claim_owner and not await db.renew_mail_intake_document(doc["id"], claim_owner):
                raise RuntimeError("Mail intake claim was taken over")
            if decision.get("is_spam") or decision.get("is_injection_attempt"):
                await _apply_tags(doc, {TAG_SPAM}, {TAG_PENDING}, tag_ids)
                counts["spam"] += 1
                return True
            await db.add_case_document(case["id"], doc["id"], "email" if own_email else "attachment")
            await db.add_case_event(
                case["id"],
                "received",
                detail=doc.get("title"),
                actor_label=_ACTOR_LABEL,
                link_kind="document",
                link_id=str(doc["id"]),
            )
            await _apply_tags(doc, {TAG_ANLIEGEN}, {TAG_PENDING}, tag_ids)
            counts["appended"] += 1
            return True

    decision = await case_agent.analyze(content[: settings.mail_intake_max_chars], sender_email)
    if claim_owner and not await db.renew_mail_intake_document(doc["id"], claim_owner):
        raise RuntimeError("Mail intake claim was taken over")
    return await _enforce_and_create_case(
        doc, sender_email, decision, tag_ids, counts, claim_owner
    )


async def _enforce_and_create_case(
    doc: dict,
    sender_email: str,
    decision: dict,
    tag_ids: dict[str, int],
    counts: dict,
    claim_owner: str = "",
) -> bool:
    """Nichts aus 'decision' wird ungeprueft uebernommen — jedes Feld läuft durch
    eine feste Regel, bevor es Paperless oder die Fall-Datenbank erreicht."""
    if claim_owner and not await db.renew_mail_intake_document(doc["id"], claim_owner):
        raise RuntimeError("Mail intake claim was taken over")
    if decision.get("is_spam") or decision.get("is_injection_attempt"):
        await _apply_tags(doc, {TAG_SPAM}, {TAG_PENDING}, tag_ids)
        counts["spam"] += 1
        return True

    category = decision.get("category")
    if category not in case_agent.ALLOWED_CATEGORIES:
        category = TAG_ANLIEGEN
    status = decision.get("status")
    if status not in _ALLOWED_STATUSES:
        status = "open"
    object_code = _validate_object_code(decision.get("object_code"), tag_ids)
    due_date = _validate_due_date(decision.get("due_date"))

    title = (decision.get("title") or doc.get("title") or "Anliegen")[:200]
    summary = (decision.get("summary") or "")[:2000] or None

    tracking_id = await db.next_tracking_id()
    case = await db.create_intake_case(
        paperless_id=doc["id"],
        owner_id=claim_owner,
        tracking_id=tracking_id,
        title=title,
        summary=summary,
        status=status,
        sender_email=sender_email,
        object_code=object_code,
    )
    tracking_id = case["tracking_id"]
    if claim_owner and not await db.renew_mail_intake_document(doc["id"], claim_owner):
        raise RuntimeError("Mail intake claim was taken over")
    await db.add_case_document(case["id"], doc["id"], "email")
    await db.add_case_event(
        case["id"],
        "received",
        detail=doc.get("title"),
        actor_label=_ACTOR_LABEL,
        link_kind="document",
        link_id=str(doc["id"]),
    )
    if case.get("_created", True):
        await db.add_case_event(
            case["id"],
            "filed",
            detail=f"Angelegt als {tracking_id}",
            actor_label=_ACTOR_LABEL,
            link_kind="document",
            link_id=str(doc["id"]),
        )

    tags_to_add = {TAG_ANLIEGEN, category, status}
    if object_code:
        tags_to_add.add(object_code)
    if due_date:
        tags_to_add.add(f"due:{due_date}")
    await _apply_tags(doc, tags_to_add, {TAG_PENDING}, tag_ids)
    if case.get("_created", True):
        counts["cases_created"] += 1

    return True


async def scheduler() -> None:
    if not settings.mail_intake_enabled:
        logger.info("Anliegen-Aufnahme ist abgeschaltet (MAIL_INTAKE_ENABLED).")
        return

    tick = settings.mail_intake_poll_seconds or _TICK_SECONDS_FALLBACK
    logger.info("Anliegen-Aufnahme aktiv: alle %d Sekunden.", tick)
    while True:
        try:
            result = await poll_once()
            if result.get("checked"):
                logger.info("Anliegen-Aufnahme: %s", result)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Ein Fehler in einem Durchlauf darf die Pipeline nicht dauerhaft
            # stilllegen — der naechste Tick versucht es einfach wieder.
            logger.exception("Durchlauf der Anliegen-Aufnahme fehlgeschlagen.")
        await asyncio.sleep(tick)
