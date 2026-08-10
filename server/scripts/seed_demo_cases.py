"""Erzeugt eine große, bunte Menge Demo-Anliegen für die Anliegenverwaltung.

Einmalig von Hand auszufuehren, kein Teil des App-Starts (anders als tag_seed.py/
mail_seed.py). Legt Faelle direkt ueber SQL an (statt ueber db.create_case), weil
fuer realistische Zeitstrahlen/Graphen ein frei waehlbares created_at noetig ist,
das die normalen Accessor-Funktionen absichtlich nicht anbieten (dort ist "jetzt"
immer richtig, hier soll ein halbes Jahr Historie simuliert werden).

Aufruf aus server/:
    .venv/bin/python -m scripts.seed_demo_cases
"""

import asyncio
import random
from datetime import datetime, timedelta, timezone

from app import db

CASE_COUNT = 100
LINK_COUNT = 32

OBJECT_CODES = [f"OBJ-{i:03d}" for i in range(1, 18)]

CONCERNS = [
    "Wasserschaden im Bad",
    "Heizungsausfall",
    "Lärmbeschwerde Nachbarwohnung",
    "Schlüsselverlust Hauseingang",
    "Mängelanzeige Fenster",
    "Frage zur Nebenkostenabrechnung",
    "Kündigung des Mietvertrags",
    "Anfrage Mieterhöhung",
    "Aufzugsstörung",
    "Fassadenschaden nach Sturm",
    "Schädlingsbefall Keller",
    "Rohrbruch Steigleitung",
    "Anfrage Untervermietung",
    "Reklamation Gartenpflege",
    "Störung Gegensprechanlage",
    "Feuchtigkeit im Treppenhaus",
    "Reparaturauftrag Dachrinne",
    "Vertragsänderung Stellplatz",
    "Beschwerde Müllentsorgung",
    "Anfrage Sondernutzung Innenhof",
    "Modernisierungsankündigung",
    "Beschädigung Briefkastenanlage",
    "Rauchmelderprüfung fällig",
    "Anfrage Legionellenprüfung",
    "Elektrikstörung Flur",
    "Beschwerde Ruhestörung Baustelle",
    "Anfrage Kabelfernsehen kündigen",
    "Reparatur Türschließer",
    "Schimmelbildung Schlafzimmer",
    "Frage zur Kaution",
    "Mängelanzeige Balkon",
    "Anfrage Photovoltaik Balkonkraftwerk",
    "Sturmschaden Dachziegel",
    "Reklamation Handwerkerrechnung",
    "Anfrage Barrierefreiheit Eingang",
    "Streit um Gartennutzung",
    "Defekter Rauchmelder",
    "Anfrage Ladesäule Tiefgarage",
]

SENDERS = [
    "erika.beispiel@example.org",
    "max.mustermieter@example.org",
    "frieda.fiktiv@example.org",
    "konrad.kontrollfall@example.org",
    "samira.sandbox@example.org",
    "toni.testbeirat@example.org",
    "julia.beispielmieterin@example.org",
    "peter.probeperson@example.org",
    "hanna.hausbewohnerin@example.org",
    "gustav.gastmieter@example.org",
    "info@elektro-musterstrom.example",
    "auftraege@dachprofi-musterbetrieb.example",
    "service@demofix-sanitaer.example",
    "kontakt@gruenwerk-testservice.example",
    "technik@liftservice-sandbox.example",
    "pruefung@brandschutz-prueflabor.example",
    "buero@sauber-klar-demo.example",
    "schaden@versicherung-musterschutz.example",
    "verwaltung@morgenrot-gebaeudeservice.example",
    "aussenanlagen@gruensaum-demo.example",
]

NOTE_TEMPLATES = [
    "Rückruf beim Absender erfolgt, Termin für {date} vereinbart.",
    "Handwerker beauftragt, Rückmeldung steht noch aus.",
    "Nach Rücksprache mit der Hausverwaltung als nicht dringend eingestuft.",
    "Foto-Dokumentation liegt dem Anliegen bei.",
    "Zweite Mahnung an den Dienstleister verschickt.",
    "Ursache identifiziert, Reparatur für die kommende Woche geplant.",
    "Absender hat sich noch einmal telefonisch gemeldet.",
    "Kostenvoranschlag angefordert, Rückmeldung ausstehend.",
    "Zutritt für den Handwerker am {date} organisiert.",
    "Vorgang mit dem Beirat abgestimmt.",
]

REPLY_SUBJECTS = [
    "Rückmeldung zu Ihrem Anliegen",
    "Terminbestätigung",
    "Zwischenstand zu Ihrer Meldung",
    "Antwort auf Ihre Anfrage",
]


def rand_dt(days_back_min: float, days_back_max: float) -> datetime:
    now = datetime.now(timezone.utc)
    return now - timedelta(days=random.uniform(days_back_min, days_back_max))


async def fetch_user_ids(pool) -> list[str]:
    rows = await pool.fetch("SELECT id FROM users")
    return [str(r["id"]) for r in rows]


async def create_one_case(pool, index: int) -> dict:
    created_at = rand_dt(0, 180)
    status = random.choices(["open", "closed"], weights=[55, 45])[0]
    closed_at = None
    if status == "closed":
        closed_at = created_at + timedelta(days=random.uniform(0.5, 30))
        now = datetime.now(timezone.utc)
        if closed_at > now:
            closed_at = now

    concern = random.choice(CONCERNS)
    has_object = random.random() < 0.75
    object_code = random.choice(OBJECT_CODES) if has_object else None
    sender = random.choice(SENDERS)

    title = concern
    if object_code and random.random() < 0.4:
        title = f"{concern} ({object_code})"

    urgent_note = " Dringende Bearbeitung erforderlich." if random.random() < 0.15 else ""
    summary = f"{concern}, gemeldet von {sender}.{urgent_note}"

    tracking_id = await db.next_tracking_id()

    row = await pool.fetchrow(
        """
        INSERT INTO cases (tracking_id, title, summary, status, sender_email, object_code, created_at, closed_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING id::text AS id, tracking_id, created_at
        """,
        tracking_id,
        title,
        summary,
        status,
        sender,
        object_code,
        created_at,
        closed_at,
    )

    await pool.execute(
        "INSERT INTO case_events (case_id, kind, detail, created_at) VALUES ($1, 'received', $2, $3)",
        row["id"],
        title,
        created_at,
    )
    await pool.execute(
        "INSERT INTO case_events (case_id, kind, detail, created_at) VALUES ($1, 'filed', $2, $3)",
        row["id"],
        f"Angelegt als {tracking_id}",
        created_at + timedelta(minutes=random.randint(2, 90)),
    )

    return {
        "id": row["id"],
        "tracking_id": tracking_id,
        "created_at": created_at,
        "closed_at": closed_at,
        "status": status,
    }


async def add_notes_and_replies(pool, case: dict, user_ids: list[str]) -> None:
    window_end = case["closed_at"] or datetime.now(timezone.utc)

    if random.random() < 0.4:
        for _ in range(random.randint(1, 3)):
            note_time = case["created_at"] + timedelta(days=random.uniform(0, 10))
            note_time = min(note_time, window_end - timedelta(minutes=30)) if window_end > case["created_at"] else case["created_at"]
            author = random.choice(user_ids) if user_ids and random.random() < 0.8 else None
            body = random.choice(NOTE_TEMPLATES).format(date=(note_time + timedelta(days=3)).strftime("%d.%m."))
            await pool.execute(
                "INSERT INTO case_notes (case_id, author_user_id, body, created_at) VALUES ($1, $2, $3, $4)",
                case["id"],
                author,
                body,
                note_time,
            )
            await pool.execute(
                "INSERT INTO case_events (case_id, kind, detail, created_at) VALUES ($1, 'note_added', $2, $3)",
                case["id"],
                body[:120],
                note_time,
            )

    if random.random() < 0.3:
        reply_time = case["created_at"] + timedelta(days=random.uniform(0.2, 8))
        reply_time = min(reply_time, window_end - timedelta(minutes=10)) if window_end > case["created_at"] else case["created_at"]
        subject = f"[{case['tracking_id']}] {random.choice(REPLY_SUBJECTS)}"
        await pool.execute(
            "INSERT INTO case_events (case_id, kind, detail, created_at) VALUES ($1, 'reply_sent', $2, $3)",
            case["id"],
            subject,
            reply_time,
        )

    if case["status"] == "closed" and case["closed_at"]:
        await pool.execute(
            "INSERT INTO case_events (case_id, kind, created_at) VALUES ($1, 'closed', $2)",
            case["id"],
            case["closed_at"],
        )


async def create_links(pool, cases: list[dict], user_ids: list[str]) -> int:
    # dependent liegt zeitlich immer nach prerequisite: vermeidet Zyklen von
    # selbst, ohne eine eigene Zyklenerkennung zu brauchen (der Graph hat zwar
    # eine, aber "sinnvolle" Demo-Daten sollen erst gar keine erzeugen).
    ordered = sorted(cases, key=lambda c: c["created_at"])
    seen: set[tuple[str, str]] = set()
    edges = 0
    attempts = 0

    while edges < LINK_COUNT and attempts < LINK_COUNT * 15:
        attempts += 1
        idx = random.randint(1, len(ordered) - 1)
        dependent = ordered[idx]
        prerequisite = ordered[random.randint(0, idx - 1)]
        pair = (dependent["tracking_id"], prerequisite["tracking_id"])
        if pair in seen:
            continue
        seen.add(pair)

        confirmed = random.random() < 0.6
        proposed_by = "agent" if not confirmed or random.random() < 0.5 else random.choice(user_ids or ["agent"])

        link = await db.propose_case_link(dependent["tracking_id"], prerequisite["tracking_id"], proposed_by=proposed_by)
        if link is None:
            continue
        if confirmed:
            await db.confirm_case_link(dependent["tracking_id"], prerequisite["tracking_id"])

        detail = (
            f"Verknüpft mit {prerequisite['tracking_id']}"
            if confirmed
            else f"Vorschlag: hängt ab von {prerequisite['tracking_id']}"
        )
        await pool.execute(
            "INSERT INTO case_events (case_id, kind, detail, created_at) VALUES ($1, 'linked', $2, $3)",
            dependent["id"],
            detail,
            dependent["created_at"],
        )
        edges += 1

    return edges


async def main() -> None:
    await db.init_db()
    pool = await db.get_pool()
    user_ids = await fetch_user_ids(pool)

    cases = []
    for i in range(CASE_COUNT):
        case = await create_one_case(pool, i)
        await add_notes_and_replies(pool, case, user_ids)
        cases.append(case)

    edges = await create_links(pool, cases, user_ids)

    open_count = sum(1 for c in cases if c["status"] == "open")
    print(f"{len(cases)} Anliegen angelegt ({open_count} offen, {len(cases) - open_count} geschlossen).")
    print(f"{edges} Verknüpfungen angelegt.")


if __name__ == "__main__":
    asyncio.run(main())
