import asyncio
import hashlib
import json
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import unquote, urlsplit

import asyncpg
from pgvector.asyncpg import register_vector

from .config import settings

_pool: asyncpg.Pool | None = None
_pool_lock = asyncio.Lock()
_ADMIN_MUTATION_LOCK = 0x44535141444D494E
_MIGRATION_LOCK = 0x4453514D49475241
_AUDIT_APPEND_LOCK = 0x4453514155444954
_AUTHORIZATION_LEASE_LIMIT = asyncio.Semaphore(4)
SCHEMA_VERSION = 1


def schema_checksum() -> str:
    source = Path(__file__).read_text(encoding="utf-8")
    migration = source.split("# MIGRATION_001_BEGIN", 1)[1].split(
        "# MIGRATION_001_END", 1
    )[0]
    return hashlib.sha256(migration.encode("utf-8")).hexdigest()


async def _reconcile_runtime_role(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'datasynq_runtime') THEN
                CREATE ROLE datasynq_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
            END IF;
        END;
        $$
        """
    )
    if settings.runtime_database_dsn:
        parsed_runtime = urlsplit(settings.runtime_database_dsn)
        parsed_owner = urlsplit(settings.database_dsn)
        runtime_user = unquote(parsed_runtime.username or "")
        runtime_password = unquote(parsed_runtime.password or "")
        if runtime_user != "datasynq_runtime" or not runtime_password:
            raise RuntimeError(
                "RUNTIME_DATABASE_URL muss den Benutzer datasynq_runtime mit Passwort verwenden."
            )
        if (
            parsed_runtime.hostname,
            parsed_runtime.port,
            parsed_runtime.path,
        ) != (parsed_owner.hostname, parsed_owner.port, parsed_owner.path):
            raise RuntimeError("Owner- und Runtime-Datenbank-URL müssen dieselbe Datenbank verwenden.")
        if runtime_password == unquote(parsed_owner.password or ""):
            raise RuntimeError("Owner- und Runtime-Datenbankpasswort müssen verschieden sein.")
        quoted_password = await conn.fetchval("SELECT quote_literal($1)", runtime_password)
        await conn.execute(f"ALTER ROLE datasynq_runtime LOGIN PASSWORD {quoted_password}")
    await conn.execute("GRANT datasynq_runtime TO CURRENT_USER")
    await conn.execute("GRANT USAGE ON SCHEMA public TO datasynq_runtime")
    await conn.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO datasynq_runtime"
    )
    await conn.execute(
        "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO datasynq_runtime"
    )
    await conn.execute(
        "REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON audit_events FROM datasynq_runtime"
    )
    await conn.execute(
        f"""
        CREATE OR REPLACE FUNCTION append_audit_event_record(
            p_occurred_at TIMESTAMPTZ,
            p_request_id UUID,
            p_actor_type TEXT,
            p_actor_id TEXT,
            p_actor_role TEXT,
            p_action TEXT,
            p_outcome TEXT,
            p_reason_code TEXT,
            p_target_type TEXT,
            p_target_id TEXT,
            p_metadata JSONB
        ) RETURNS SETOF audit_events
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
        DECLARE
            v_previous_hash TEXT;
            v_payload TEXT;
            v_event_hash TEXT;
        BEGIN
            IF p_action !~ '^[a-z][a-z0-9_.-]{{2,100}}$'
               OR p_outcome NOT IN ('started', 'success', 'denied', 'failure')
               OR length(p_metadata::text) > 8000 THEN
                RAISE EXCEPTION 'invalid audit event';
            END IF;
            IF EXISTS (
                SELECT 1 FROM jsonb_object_keys(p_metadata) AS key
                WHERE key NOT IN (
                    'method', 'route', 'status_code', 'auth_stage', 'factor',
                    'old_role', 'new_role', 'old_mode', 'new_mode', 'scope_count',
                    'document_count', 'view', 'mail_sent', 'purpose',
                    'policy_version', 'model', 'classes', 'scanned', 'embedded',
                    'skipped', 'pruned', 'errors', 'complete'
                )
            ) THEN
                RAISE EXCEPTION 'invalid audit metadata';
            END IF;
            PERFORM pg_advisory_xact_lock({_AUDIT_APPEND_LOCK});
            SELECT event_hash INTO v_previous_hash
            FROM audit_events ORDER BY sequence_no DESC LIMIT 1;
            v_previous_hash := COALESCE(v_previous_hash, repeat('0', 64));
            v_payload := jsonb_build_object(
                'occurred_at', p_occurred_at,
                'request_id', p_request_id,
                'actor_type', p_actor_type,
                'actor_id', p_actor_id,
                'actor_role', p_actor_role,
                'action', p_action,
                'outcome', p_outcome,
                'reason_code', p_reason_code,
                'target_type', p_target_type,
                'target_id', p_target_id,
                'metadata', p_metadata
            )::text;
            v_event_hash := encode(digest(v_previous_hash || chr(31) || v_payload, 'sha256'), 'hex');
            RETURN QUERY
            INSERT INTO audit_events (
                occurred_at, request_id, actor_type, actor_id, actor_role,
                action, outcome, reason_code, target_type, target_id, metadata,
                canonical_payload, previous_hash, event_hash
            ) VALUES (
                p_occurred_at, p_request_id, p_actor_type, p_actor_id, p_actor_role,
                p_action, p_outcome, p_reason_code, p_target_type, p_target_id, p_metadata,
                v_payload, v_previous_hash, v_event_hash
            ) RETURNING *;
        END;
        $$
        """
    )
    signature = (
        "append_audit_event_record(TIMESTAMPTZ, UUID, TEXT, TEXT, TEXT, TEXT, "
        "TEXT, TEXT, TEXT, TEXT, JSONB)"
    )
    await conn.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
    await conn.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO datasynq_runtime")


class LastActiveAdminError(RuntimeError):
    pass


class LastGlobalAdminError(RuntimeError):
    pass


async def _init_connection(conn: asyncpg.Connection) -> None:
    await register_vector(conn)
    await conn.execute("SET ROLE datasynq_runtime")


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        async with _pool_lock:
            if _pool is None:
                _pool = await asyncpg.create_pool(
                    settings.database_dsn,
                    init=_init_connection,
                    min_size=settings.db_pool_min_size,
                    max_size=settings.db_pool_max_size,
                    command_timeout=settings.db_command_timeout_seconds,
                )
    return _pool


async def init_db() -> None:
    conn = await asyncpg.connect(settings.database_dsn)
    transaction = conn.transaction()
    started = False
    committed = False
    try:
        await conn.execute("SET lock_timeout = '30s'")
        await conn.execute("SET statement_timeout = '2min'")
        await conn.execute("SELECT pg_advisory_lock($1)", _MIGRATION_LOCK)
        await conn.execute("SET statement_timeout = '10min'")
        await transaction.start()
        started = True
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version     INTEGER PRIMARY KEY,
                checksum    TEXT NOT NULL,
                applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        rows = await conn.fetch(
            "SELECT version, checksum FROM schema_migrations ORDER BY version"
        )
        if rows:
            newest = rows[-1]["version"]
            if newest > SCHEMA_VERSION:
                raise RuntimeError(
                    f"Datenbankschema {newest} ist neuer als diese Anwendung ({SCHEMA_VERSION})."
                )
            applied = {row["version"]: row["checksum"] for row in rows}
            if applied.get(SCHEMA_VERSION) != schema_checksum():
                raise RuntimeError("Checksumme der angewendeten Datenbankmigration stimmt nicht.")
            await _reconcile_runtime_role(conn)
            await transaction.commit()
            committed = True
            return

        # MIGRATION_001_BEGIN
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS document_embeddings (
                id              SERIAL PRIMARY KEY,
                paperless_id    INTEGER NOT NULL UNIQUE,
                title           TEXT NOT NULL,
                correspondent   TEXT,
                document_type   TEXT,
                tags            TEXT[],
                object_codes    TEXT[] NOT NULL DEFAULT '{}',
                created_date    DATE,
                content_hash    TEXT NOT NULL,
                embedding       VECTOR(1536) NOT NULL,
                last_synced_at  TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        await conn.execute(
            """
            ALTER TABLE document_embeddings
            ADD COLUMN IF NOT EXISTS object_codes TEXT[] NOT NULL DEFAULT '{}'
            """
        )
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS document_embeddings_embedding_idx
                ON document_embeddings USING hnsw (embedding vector_cosine_ops)
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id          TEXT PRIMARY KEY,
                title       TEXT NOT NULL,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id          SERIAL PRIMARY KEY,
                session_id  TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
                role        TEXT NOT NULL,
                content     TEXT NOT NULL,
                tool_calls  JSONB,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS chat_messages_session_idx ON chat_messages(session_id)"
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                email                TEXT NOT NULL UNIQUE,
                display_name         TEXT NOT NULL,
                password_hash        TEXT NOT NULL,
                role                 TEXT NOT NULL CHECK (role IN ('admin', 'editor', 'viewer')),
                is_active            BOOLEAN NOT NULL DEFAULT TRUE,
                must_change_password BOOLEAN NOT NULL DEFAULT FALSE,
                object_access_mode   TEXT NOT NULL DEFAULT 'all'
                    CHECK (object_access_mode IN ('all', 'restricted')),
                failed_logins        INTEGER NOT NULL DEFAULT 0,
                locked_until         TIMESTAMPTZ,
                mfa_failed_attempts  INTEGER NOT NULL DEFAULT 0,
                mfa_locked_until     TIMESTAMPTZ,
                last_login_at        TIMESTAMPTZ,
                mfa_enabled_at       TIMESTAMPTZ,
                created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        await conn.execute(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS mfa_enabled_at TIMESTAMPTZ"
        )
        await conn.execute(
            """
            ALTER TABLE users ADD COLUMN IF NOT EXISTS object_access_mode TEXT
            NOT NULL DEFAULT 'all' CHECK (object_access_mode IN ('all', 'restricted'))
            """
        )
        await conn.execute(
            """
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS mfa_failed_attempts INTEGER NOT NULL DEFAULT 0
            """
        )
        await conn.execute(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS mfa_locked_until TIMESTAMPTZ"
        )
        # Sitzungen liegen serverseitig statt in einem JWT: so ist ein deaktivierter
        # Benutzer sofort draußen, ohne Sperrliste und ohne auf einen Tokenablauf zu
        # warten. Gespeichert wird nur der SHA-256 des Cookie-Tokens — wer die Tabelle
        # liest, kann damit keine Sitzung übernehmen.
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_sessions (
                token_hash   TEXT PRIMARY KEY,
                id           UUID NOT NULL DEFAULT gen_random_uuid(),
                user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
                last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                expires_at   TIMESTAMPTZ NOT NULL,
                absolute_expires_at TIMESTAMPTZ NOT NULL,
                mfa_verified_at TIMESTAMPTZ,
                user_agent   TEXT
            )
            """
        )
        await conn.execute(
            "ALTER TABLE auth_sessions ADD COLUMN IF NOT EXISTS id UUID DEFAULT gen_random_uuid()"
        )
        await conn.execute(
            "ALTER TABLE auth_sessions ADD COLUMN IF NOT EXISTS absolute_expires_at TIMESTAMPTZ"
        )
        await conn.execute(
            "ALTER TABLE auth_sessions ADD COLUMN IF NOT EXISTS mfa_verified_at TIMESTAMPTZ"
        )
        await conn.execute(
            """
            UPDATE auth_sessions
            SET absolute_expires_at = LEAST(
                expires_at,
                created_at + make_interval(hours => $1)
            )
            WHERE absolute_expires_at IS NULL
            """,
            settings.session_absolute_ttl_hours,
        )
        await conn.execute("ALTER TABLE auth_sessions ALTER COLUMN id SET NOT NULL")
        await conn.execute(
            "ALTER TABLE auth_sessions ALTER COLUMN absolute_expires_at SET NOT NULL"
        )
        await conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS auth_sessions_id_idx ON auth_sessions(id)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS auth_sessions_user_idx ON auth_sessions(user_id)"
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_mfa (
                user_id           UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                secret_ciphertext TEXT NOT NULL,
                confirmed_at      TIMESTAMPTZ,
                last_used_step    BIGINT,
                created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mfa_recovery_codes (
                id          TEXT PRIMARY KEY,
                user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                secret_hash TEXT NOT NULL,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                used_at     TIMESTAMPTZ
            )
            """
        )
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS mfa_recovery_codes_user_idx
            ON mfa_recovery_codes(user_id)
            """
        )
        # Vorbereitung auf eine Einschränkung nach Objekten (Liegenschaften). Kein
        # Eintrag heißt 'alle Objekte', und genau so wird die Tabelle heute überall
        # ausgewertet — sie existiert, damit der Filter später nur an einer Stelle
        # scharf geschaltet werden muss.
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_object_scopes (
                user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                object_name TEXT NOT NULL,
                PRIMARY KEY (user_id, object_name)
            )
            """
        )
        await conn.execute(
            """
            ALTER TABLE chat_sessions
                ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id) ON DELETE CASCADE
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS chat_sessions_user_idx ON chat_sessions(user_id)"
        )
        # Einladungs- und Reset-Links. Wie bei auth_sessions steht der Klartext nur
        # im Link, in der Datenbank sein SHA-256. `used_at` macht ihn einmalig.
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_tokens (
                token_hash TEXT PRIMARY KEY,
                user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                purpose    TEXT NOT NULL CHECK (purpose IN ('invitation', 'password_reset')),
                expires_at TIMESTAMPTZ NOT NULL,
                used_at    TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_rate_limits (
                key_hash       TEXT PRIMARY KEY,
                attempts       INTEGER NOT NULL,
                window_ends_at TIMESTAMPTZ NOT NULL
            )
            """
        )
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS auth_rate_limits_expiry_idx
            ON auth_rate_limits(window_ends_at)
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS user_tokens_user_idx ON user_tokens(user_id)"
        )
        # Ein Anspruch pro Tag und Empfänger verhindert, dass der Erfolg eines Kontos
        # einen fehlgeschlagenen Versand an ein anderes Konto verdeckt.
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mail_digest_deliveries (
                digest_date DATE NOT NULL,
                user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                claimed_at  TIMESTAMPTZ,
                owner_id    UUID,
                sent_at     TIMESTAMPTZ,
                PRIMARY KEY (digest_date, user_id)
            )
            """
        )
        # Entwürfe des Assistenten liegen serverseitig, nicht nur im Browser: sonst
        # wäre der Sende-Endpunkt eine Versandmaschine, der man beliebigen Text und
        # beliebige Empfänger unterschiebt.
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS email_drafts (
                id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                session_id  TEXT REFERENCES chat_sessions(id) ON DELETE SET NULL,
                recipient   TEXT NOT NULL,
                subject     TEXT NOT NULL,
                body        TEXT NOT NULL,
                document_id INTEGER,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                send_claimed_at TIMESTAMPTZ,
                sent_at     TIMESTAMPTZ
            )
            """
        )
        await conn.execute(
            "ALTER TABLE email_drafts ADD COLUMN IF NOT EXISTS send_claimed_at TIMESTAMPTZ"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS email_drafts_user_idx ON email_drafts(user_id)"
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mail_intake_claims (
                paperless_id INTEGER PRIMARY KEY,
                claimed_at   TIMESTAMPTZ DEFAULT now(),
                completed_at TIMESTAMPTZ,
                case_id      UUID,
                owner_id     UUID
            )
            """
        )
        await conn.execute(
            "ALTER TABLE mail_intake_claims ALTER COLUMN claimed_at DROP NOT NULL"
        )
        await conn.execute(
            "ALTER TABLE mail_intake_claims ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ"
        )
        await conn.execute(
            "ALTER TABLE mail_intake_claims ADD COLUMN IF NOT EXISTS case_id UUID"
        )
        await conn.execute(
            "ALTER TABLE mail_intake_claims ADD COLUMN IF NOT EXISTS owner_id UUID"
        )
        # Momente, in denen der Agent selbst etwas im Board gezeigt hat (z. B. per
        # 'open_board'). Anders als bei email_drafts gehört das untrennbar zu seinem
        # Chat — verschwindet die Konversation, verschwindet auch die Erinnerung
        # daran, was darin gezeigt wurde. Deshalb CASCADE statt SET NULL.
        # tool_call_index ist die Position im tool_calls-Array der zugehörigen
        # Nachricht (nicht die id des Tool-Aufrufs selbst — die wird serverseitig gar
        # nicht gespeichert), damit die Oberfläche die Ablaufanzeige an genau dieser
        # Stelle aufteilen kann.
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS board_events (
                id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                session_id       TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
                user_id          UUID REFERENCES users(id) ON DELETE CASCADE,
                message_id       INTEGER NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
                tool_call_index  INTEGER NOT NULL,
                kind             TEXT NOT NULL,
                title            TEXT NOT NULL,
                payload          JSONB NOT NULL,
                created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS board_events_session_idx ON board_events(session_id)"
        )

        # Wer eine E-Mail schicken darf, ohne dass ein Mensch erst zustimmt: pending
        # bis zur ersten Entscheidung, approved nur befristet (expires_at) — eine
        # einmalige Freigabe ist kein Dauervertrauen. rejected bleibt rejected, bis
        # jemand das Gegenteil entscheidet (approve überschreibt es jederzeit).
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mail_sender_trust (
                email          TEXT PRIMARY KEY,
                status         TEXT NOT NULL DEFAULT 'pending',
                approved_by    UUID REFERENCES users(id) ON DELETE SET NULL,
                approved_at    TIMESTAMPTZ,
                expires_at     TIMESTAMPTZ,
                first_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                last_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )

        # Anliegen: ein eigenständig verfolgter Vorgang, getrennt von den Paperless-
        # Dokumenten, die ihn belegen (case_documents verknüpft die beiden).
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cases (
                id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tracking_id   TEXT UNIQUE NOT NULL,
                title         TEXT NOT NULL,
                summary       TEXT,
                status        TEXT NOT NULL DEFAULT 'open',
                sender_email  TEXT,
                object_code   TEXT,
                created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
                closed_at     TIMESTAMPTZ
            )
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS cases_status_idx ON cases(status)"
        )
        # Ein Zähler pro Jahr statt count(*)-basierter Nummerierung: eine gelöschte
        # Zeile würde sonst eine Nummer für eine spätere Vergabe wieder freigeben.
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS case_tracking_seq (
                year      INTEGER PRIMARY KEY,
                next_seq  INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS case_documents (
                case_id       UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                paperless_id  INTEGER NOT NULL,
                role          TEXT NOT NULL,
                added_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY (case_id, paperless_id)
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS case_events (
                id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                case_id     UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                kind        TEXT NOT NULL,
                detail      TEXT,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS case_events_case_idx ON case_events(case_id)"
        )
        # actor_user_id/actor_label: wer's war (ein Nutzer, oder — bislang nur bei
        # der Mail-Aufnahme — ein Systemakteur ohne Konto). link_kind/link_id: ein
        # kleiner generischer Verweis (Notiz/Anliegen/Dokument/Chat-Sitzung), den
        # die Oberfläche in genau einen Klickpunkt je Ereignis übersetzt, statt für
        # jede Zielart eine eigene Spalte zu brauchen.
        await conn.execute(
            """
            ALTER TABLE case_events
                ADD COLUMN IF NOT EXISTS actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                ADD COLUMN IF NOT EXISTS actor_label   TEXT,
                ADD COLUMN IF NOT EXISTS link_kind     TEXT,
                ADD COLUMN IF NOT EXISTS link_id       TEXT
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS case_notes (
                id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                case_id         UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                author_user_id  UUID REFERENCES users(id) ON DELETE SET NULL,
                body            TEXT NOT NULL,
                created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS case_notes_case_idx ON case_notes(case_id)"
        )
        # dependent_case_id baut auf prerequisite_case_id auf. proposed vs. confirmed:
        # ein vom Agenten vorgeschlagener Zusammenhang gilt erst als gesicherte
        # Abhängigkeit, wenn ein Mensch ihn im Graph bestätigt hat.
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS case_links (
                dependent_case_id     UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                prerequisite_case_id  UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                status       TEXT NOT NULL DEFAULT 'proposed',
                proposed_by  TEXT NOT NULL,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY (dependent_case_id, prerequisite_case_id)
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                sequence_no      BIGSERIAL PRIMARY KEY,
                id               UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
                occurred_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
                request_id       UUID,
                actor_type       TEXT NOT NULL,
                actor_id         TEXT,
                actor_role       TEXT,
                action           TEXT NOT NULL,
                outcome          TEXT NOT NULL CHECK (outcome IN ('started', 'success', 'denied', 'failure')),
                reason_code      TEXT,
                target_type      TEXT,
                target_id        TEXT,
                metadata         JSONB NOT NULL DEFAULT '{}',
                canonical_payload TEXT NOT NULL,
                previous_hash    TEXT NOT NULL,
                event_hash       TEXT NOT NULL UNIQUE
            )
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS audit_events_time_idx ON audit_events(occurred_at DESC)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS audit_events_action_idx ON audit_events(action, occurred_at DESC)"
        )
        await conn.execute(
            """
            CREATE OR REPLACE FUNCTION reject_audit_event_mutation()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'audit_events is append-only';
            END;
            $$
            """
        )
        await conn.execute("DROP TRIGGER IF EXISTS audit_events_append_only ON audit_events")
        await conn.execute(
            """
            CREATE TRIGGER audit_events_append_only
            BEFORE UPDATE OR DELETE ON audit_events
            FOR EACH ROW EXECUTE FUNCTION reject_audit_event_mutation()
            """
        )
        await conn.execute(
            """
            CREATE TRIGGER audit_events_no_truncate
            BEFORE TRUNCATE ON audit_events
            FOR EACH STATEMENT EXECUTE FUNCTION reject_audit_event_mutation()
            """
        )
        # MIGRATION_001_END
        await _reconcile_runtime_role(conn)
        await conn.execute(
            "INSERT INTO schema_migrations (version, checksum) VALUES ($1, $2)",
            SCHEMA_VERSION,
            schema_checksum(),
        )
        await transaction.commit()
        committed = True
    except Exception:
        if started and not committed:
            await transaction.rollback()
        raise
    finally:
        try:
            await conn.execute("SELECT pg_advisory_unlock($1)", _MIGRATION_LOCK)
        finally:
            await conn.close()


async def close_db() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def database_ready() -> bool:
    try:
        pool = await get_pool()
        row = await asyncio.wait_for(
            pool.fetchrow(
                "SELECT version, checksum FROM schema_migrations ORDER BY version DESC LIMIT 1"
            ),
            timeout=2,
        )
        return bool(
            row
            and row["version"] == SCHEMA_VERSION
            and row["checksum"] == schema_checksum()
        )
    except (asyncio.TimeoutError, asyncpg.PostgresError, OSError):
        return False


async def require_current_schema() -> None:
    if not await database_ready():
        raise RuntimeError(
            "Datenbankschema ist nicht bereit. Führe den Migrationsservice vor dem Backend aus."
        )


async def append_audit_event(
    *,
    occurred_at,
    request_id: str | None,
    actor_type: str,
    actor_id: str | None,
    actor_role: str | None,
    action: str,
    outcome: str,
    reason_code: str | None,
    target_type: str | None,
    target_id: str | None,
    metadata: dict,
) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            """
            SELECT sequence_no, id::text AS id, occurred_at, request_id::text AS request_id,
                   actor_type, actor_id, actor_role, action, outcome, reason_code,
                   target_type, target_id, metadata, previous_hash, event_hash
            FROM append_audit_event_record(
                $1, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10, $11
            )
            """,
            occurred_at,
            request_id,
            actor_type,
            actor_id,
            actor_role,
            action,
            outcome,
            reason_code,
            target_type,
            target_id,
            json.dumps(metadata),
        )
        result = dict(row)
        if isinstance(result.get("metadata"), str):
            result["metadata"] = json.loads(result["metadata"])
        return result


async def list_audit_events(limit: int = 100, before_sequence: int | None = None) -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT sequence_no, id::text AS id, occurred_at, request_id::text AS request_id,
               actor_type, actor_id, actor_role, action, outcome, reason_code,
               target_type, target_id, metadata, previous_hash, event_hash
        FROM audit_events
        WHERE ($1::bigint IS NULL OR sequence_no < $1)
        ORDER BY sequence_no DESC
        LIMIT $2
        """,
        before_sequence,
        min(max(limit, 1), 500),
    )
    result = [dict(row) for row in rows]
    for event in result:
        if isinstance(event.get("metadata"), str):
            event["metadata"] = json.loads(event["metadata"])
    return result


async def verify_audit_chain() -> dict:
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT sequence_no, occurred_at, request_id::text AS request_id, actor_type,
               actor_id, actor_role, action, outcome, reason_code, target_type,
               target_id, metadata, canonical_payload, previous_hash, event_hash,
               jsonb_build_object(
                   'occurred_at', occurred_at,
                   'request_id', request_id,
                   'actor_type', actor_type,
                   'actor_id', actor_id,
                   'actor_role', actor_role,
                   'action', action,
                   'outcome', outcome,
                   'reason_code', reason_code,
                   'target_type', target_type,
                   'target_id', target_id,
                   'metadata', metadata
               )::text AS actual_payload
        FROM audit_events ORDER BY sequence_no
        """
    )
    expected_previous = "0" * 64
    for row in rows:
        expected_hash = hashlib.sha256(
            f"{expected_previous}\x1f{row['canonical_payload']}".encode("utf-8")
        ).hexdigest()
        if (
            row["canonical_payload"] != row["actual_payload"]
            or row["previous_hash"] != expected_previous
            or row["event_hash"] != expected_hash
        ):
            return {"valid": False, "events": len(rows), "failed_at": row["sequence_no"]}
        expected_previous = expected_hash
    return {"valid": True, "events": len(rows), "head": expected_previous}


async def get_content_hash(paperless_id: int) -> str | None:
    pool = await get_pool()
    return await pool.fetchval(
        "SELECT content_hash FROM document_embeddings WHERE paperless_id = $1",
        paperless_id,
    )


async def upsert_document(
    paperless_id: int,
    title: str,
    correspondent: str | None,
    document_type: str | None,
    tags: list[str],
    object_codes: list[str],
    created_date,
    content_hash: str,
    embedding: list[float],
) -> None:
    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO document_embeddings
            (paperless_id, title, correspondent, document_type, tags, object_codes,
             created_date, content_hash, embedding, last_synced_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, now())
        ON CONFLICT (paperless_id) DO UPDATE SET
            title = EXCLUDED.title,
            correspondent = EXCLUDED.correspondent,
            document_type = EXCLUDED.document_type,
            tags = EXCLUDED.tags,
            object_codes = EXCLUDED.object_codes,
            created_date = EXCLUDED.created_date,
            content_hash = EXCLUDED.content_hash,
            embedding = EXCLUDED.embedding,
            last_synced_at = now()
        """,
        paperless_id,
        title,
        correspondent,
        document_type,
        tags,
        object_codes,
        created_date,
        content_hash,
        embedding,
    )


async def delete_documents(paperless_ids: list[int]) -> None:
    if not paperless_ids:
        return
    pool = await get_pool()
    await pool.execute(
        "DELETE FROM document_embeddings WHERE paperless_id = ANY($1::int[])",
        paperless_ids,
    )


async def list_synced_ids() -> set[int]:
    pool = await get_pool()
    rows = await pool.fetch("SELECT paperless_id FROM document_embeddings")
    return {r["paperless_id"] for r in rows}


async def count_synced_documents() -> int:
    pool = await get_pool()
    return await pool.fetchval("SELECT count(*) FROM document_embeddings")


async def last_synced_at():
    pool = await get_pool()
    return await pool.fetchval("SELECT max(last_synced_at) FROM document_embeddings")


async def similarity_search(
    query_embedding: list[float],
    limit: int = 10,
    *,
    unrestricted: bool = True,
    object_codes: tuple[str, ...] = (),
) -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT paperless_id, title, correspondent, document_type, created_date,
               1 - (embedding <=> $1) AS score
        FROM document_embeddings
        WHERE $3 OR (cardinality(object_codes) = 1 AND object_codes <@ $4::text[])
        ORDER BY embedding <=> $1
        LIMIT $2
        """,
        query_embedding,
        limit,
        unrestricted,
        list(object_codes),
    )
    results = []
    for r in rows:
        row = dict(r)
        if row.get("created_date") is not None:
            row["created_date"] = row["created_date"].isoformat()
        row["score"] = float(row["score"])
        results.append(row)
    return results


async def create_session(session_id: str, title: str, user_id: str) -> None:
    pool = await get_pool()
    await pool.execute(
        "INSERT INTO chat_sessions (id, title, user_id) VALUES ($1, $2, $3)",
        session_id,
        title,
        user_id,
    )


async def session_belongs_to(session_id: str, user_id: str) -> bool:
    """Ob diese Sitzung diesem Benutzer gehört.

    Eine fremde und eine nicht existierende Sitzung sind absichtlich derselbe
    Fall: der Aufrufer antwortet auf beides mit 404, sonst bestätigt ein 403 die
    Existenz einer fremden Konversation.
    """
    pool = await get_pool()
    return await pool.fetchval(
        "SELECT EXISTS (SELECT 1 FROM chat_sessions WHERE id = $1 AND user_id = $2)",
        session_id,
        user_id,
    )


async def touch_session(session_id: str) -> None:
    pool = await get_pool()
    await pool.execute(
        "UPDATE chat_sessions SET updated_at = now() WHERE id = $1",
        session_id,
    )


async def add_message(
    session_id: str, role: str, content: str, tool_calls: list | None = None
) -> int:
    """Liefert die id der neuen Zeile — board_events kann erst danach darauf
    verweisen, da diese Nachricht vorher noch nicht existiert."""
    pool = await get_pool()
    return await pool.fetchval(
        """
        INSERT INTO chat_messages (session_id, role, content, tool_calls)
        VALUES ($1, $2, $3, $4)
        RETURNING id
        """,
        session_id,
        role,
        content,
        json.dumps(tool_calls) if tool_calls is not None else None,
    )


async def add_board_event(
    session_id: str,
    user_id: str | None,
    message_id: int,
    tool_call_index: int,
    kind: str,
    title: str,
    payload: dict,
) -> None:
    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO board_events
            (session_id, user_id, message_id, tool_call_index, kind, title, payload)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        session_id,
        user_id,
        message_id,
        tool_call_index,
        kind,
        title,
        json.dumps(payload),
    )


async def list_sessions(user_id: str) -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT id, title, created_at, updated_at
        FROM chat_sessions
        WHERE user_id = $1
        ORDER BY updated_at DESC
        """,
        user_id,
    )
    return [dict(r) for r in rows]


async def get_session_messages(session_id: str, user_id: str) -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT m.id, m.role, m.content, m.tool_calls
        FROM chat_messages m
        JOIN chat_sessions s ON s.id = m.session_id
        WHERE m.session_id = $1 AND s.user_id = $2
        ORDER BY m.id ASC
        """,
        session_id,
        user_id,
    )
    board_rows = await pool.fetch(
        """
        SELECT id::text AS id, message_id, tool_call_index, kind, title, payload
        FROM board_events
        WHERE session_id = $1 AND user_id = $2
        ORDER BY id ASC
        """,
        session_id,
        user_id,
    )
    board_by_message: dict[int, list[dict]] = {}
    for r in board_rows:
        row = dict(r)
        message_id = row.pop("message_id")
        row["payload"] = json.loads(row["payload"])
        board_by_message.setdefault(message_id, []).append(row)

    messages = []
    for r in rows:
        row = dict(r)
        message_id = row.pop("id")
        if row.get("tool_calls") is not None:
            row["tool_calls"] = json.loads(row["tool_calls"])
        board_events = board_by_message.get(message_id)
        if board_events:
            row["board_events"] = board_events
        messages.append(row)
    return messages


async def delete_session(session_id: str, user_id: str) -> None:
    pool = await get_pool()
    await pool.execute(
        "DELETE FROM chat_sessions WHERE id = $1 AND user_id = $2",
        session_id,
        user_id,
    )


# ---------------------------------------------------------------------------
# Benutzer
# ---------------------------------------------------------------------------

_USER_COLUMNS = """
    id::text AS id, email, display_name, role, is_active, must_change_password,
    object_access_mode,
    mfa_enabled_at,
    failed_logins, locked_until, mfa_failed_attempts, mfa_locked_until,
    last_login_at, created_at, updated_at
"""

# Dieselben Spalten für Abfragen mit Join, in denen `id` und `role` mehrdeutig wären.
_USER_COLUMNS_PREFIXED = """
    u.id::text AS id, u.email, u.display_name, u.role, u.is_active, u.must_change_password,
    u.object_access_mode,
    u.mfa_enabled_at,
    u.failed_logins, u.locked_until, u.mfa_failed_attempts, u.mfa_locked_until,
    u.last_login_at, u.created_at, u.updated_at
"""


async def count_users() -> int:
    pool = await get_pool()
    return await pool.fetchval("SELECT count(*) FROM users")


async def count_active_admins(excluding_user_id: str | None = None) -> int:
    pool = await get_pool()
    if excluding_user_id is None:
        return await pool.fetchval(
            "SELECT count(*) FROM users WHERE role = 'admin' AND is_active"
        )
    return await pool.fetchval(
        "SELECT count(*) FROM users WHERE role = 'admin' AND is_active AND id <> $1",
        excluding_user_id,
    )


async def create_user(
    email: str,
    display_name: str,
    password_hash: str,
    role: str,
    must_change_password: bool = True,
    object_access_mode: str = "all",
    object_codes: tuple[str, ...] = (),
) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            f"""
            INSERT INTO users (
                email, display_name, password_hash, role, must_change_password,
                object_access_mode
            )
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING {_USER_COLUMNS}
            """,
            email.strip().lower(),
            display_name.strip(),
            password_hash,
            role,
            must_change_password,
            object_access_mode,
        )
        if object_codes:
            await conn.executemany(
                "INSERT INTO user_object_scopes (user_id, object_name) VALUES ($1, $2)",
                [(row["id"], code) for code in object_codes],
            )
    user = dict(row)
    user["object_codes"] = list(object_codes)
    return user


async def get_user_by_email(email: str) -> dict | None:
    """Inklusive Hash und Sperrzustand — nur für den Login gedacht."""
    pool = await get_pool()
    row = await pool.fetchrow(
        f"SELECT {_USER_COLUMNS}, password_hash FROM users WHERE email = $1",
        email.strip().lower(),
    )
    if row is None:
        return None
    user = dict(row)
    user["object_codes"] = list(await get_object_scope(user["id"]))
    return user


async def get_user_by_id(user_id: str) -> dict | None:
    pool = await get_pool()
    row = await pool.fetchrow(f"SELECT {_USER_COLUMNS} FROM users WHERE id = $1", user_id)
    if row is None:
        return None
    user = dict(row)
    user["object_codes"] = list(await get_object_scope(user_id))
    return user


async def get_password_hash(user_id: str) -> str | None:
    pool = await get_pool()
    return await pool.fetchval("SELECT password_hash FROM users WHERE id = $1", user_id)


async def list_users() -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(f"SELECT {_USER_COLUMNS} FROM users ORDER BY display_name ASC")
    users = [dict(r) for r in rows]
    for user in users:
        user["object_codes"] = list(await get_object_scope(user["id"]))
    return users


async def update_user(
    user_id: str,
    display_name: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock($1)", _ADMIN_MUTATION_LOCK)
        current = await conn.fetchrow(
            "SELECT role, is_active, object_access_mode FROM users WHERE id = $1 FOR UPDATE",
            user_id,
        )
        if current is None:
            return None
        loses_admin = current["role"] == "admin" and current["is_active"] and (
            (role is not None and role != "admin") or is_active is False
        )
        if loses_admin:
            active_admins = await conn.fetchval(
                "SELECT count(*) FROM users WHERE role = 'admin' AND is_active"
            )
            if active_admins <= 1:
                raise LastActiveAdminError
            if current["object_access_mode"] == "all":
                global_admins = await conn.fetchval(
                    """
                    SELECT count(*) FROM users
                    WHERE role = 'admin' AND is_active AND object_access_mode = 'all'
                    """
                )
                if global_admins <= 1:
                    raise LastGlobalAdminError
        row = await conn.fetchrow(
            f"""
            UPDATE users SET
                display_name = COALESCE($2, display_name),
                role         = COALESCE($3, role),
                is_active    = COALESCE($4, is_active),
                updated_at   = now()
            WHERE id = $1
            RETURNING {_USER_COLUMNS}
            """,
            user_id,
            display_name,
            role,
            is_active,
        )
    if row is None:
        return None
    user = dict(row)
    user["object_codes"] = list(await get_object_scope(user_id))
    return user


async def set_password(user_id: str, password_hash: str, must_change: bool) -> None:
    pool = await get_pool()
    await pool.execute(
        """
        UPDATE users SET
            password_hash        = $2,
            must_change_password = $3,
            failed_logins        = 0,
            locked_until         = NULL,
            updated_at           = now()
        WHERE id = $1
        """,
        user_id,
        password_hash,
        must_change,
    )


async def update_password_hash_if_current(
    user_id: str, current_hash: str, replacement_hash: str
) -> bool:
    """Rehash ohne die Nebenwirkungen eines echten Passwortwechsels."""
    pool = await get_pool()
    result = await pool.execute(
        """
        UPDATE users SET password_hash = $3, updated_at = now()
        WHERE id = $1 AND password_hash = $2
        """,
        user_id,
        current_hash,
        replacement_hash,
    )
    return result.rsplit(" ", 1)[-1] == "1"


async def delete_user(user_id: str) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock($1)", _ADMIN_MUTATION_LOCK)
        current = await conn.fetchrow(
            "SELECT role, is_active, object_access_mode FROM users WHERE id = $1 FOR UPDATE",
            user_id,
        )
        if current is None:
            return False
        if current["role"] == "admin" and current["is_active"]:
            active_admins = await conn.fetchval(
                "SELECT count(*) FROM users WHERE role = 'admin' AND is_active"
            )
            if active_admins <= 1:
                raise LastActiveAdminError
            if current["object_access_mode"] == "all":
                global_admins = await conn.fetchval(
                    """
                    SELECT count(*) FROM users
                    WHERE role = 'admin' AND is_active AND object_access_mode = 'all'
                    """
                )
                if global_admins <= 1:
                    raise LastGlobalAdminError
        await conn.execute("DELETE FROM users WHERE id = $1", user_id)
        return True


async def record_login_success(user_id: str) -> None:
    pool = await get_pool()
    await pool.execute(
        """
        UPDATE users SET
            failed_logins = 0,
            locked_until = NULL,
            mfa_failed_attempts = 0,
            mfa_locked_until = NULL,
            last_login_at = now()
        WHERE id = $1
        """,
        user_id,
    )


async def clear_login_failures(user_id: str) -> None:
    pool = await get_pool()
    await pool.execute(
        """
        UPDATE users SET
            failed_logins = 0,
            locked_until = NULL,
            mfa_failed_attempts = 0,
            mfa_locked_until = NULL
        WHERE id = $1
        """,
        user_id,
    )


async def record_login_failure(user_id: str, max_attempts: int, lock_minutes: int) -> None:
    """Zählt für die Administration; das eigentliche Limit ist quellbezogen."""
    pool = await get_pool()
    await pool.execute(
        "UPDATE users SET failed_logins = failed_logins + 1 WHERE id = $1",
        user_id,
    )


async def consume_auth_rate_limit(key_hash: str, limit: int, window_minutes: int) -> bool:
    pool = await get_pool()
    attempts = await pool.fetchval(
        """
        INSERT INTO auth_rate_limits (key_hash, attempts, window_ends_at)
        VALUES ($1, 1, now() + make_interval(mins => $3))
        ON CONFLICT (key_hash) DO UPDATE SET
            attempts = CASE
                WHEN auth_rate_limits.window_ends_at <= now() THEN 1
                ELSE auth_rate_limits.attempts + 1
            END,
            window_ends_at = CASE
                WHEN auth_rate_limits.window_ends_at <= now()
                THEN now() + make_interval(mins => $3)
                ELSE auth_rate_limits.window_ends_at
            END
        RETURNING attempts <= $2
        """,
        key_hash,
        limit,
        window_minutes,
    )
    return bool(attempts)


async def purge_expired_auth_rate_limits() -> None:
    pool = await get_pool()
    await pool.execute(
        "DELETE FROM auth_rate_limits WHERE window_ends_at < now() - interval '1 hour'"
    )


async def clear_auth_rate_limit(key_hash: str) -> None:
    pool = await get_pool()
    await pool.execute("DELETE FROM auth_rate_limits WHERE key_hash = $1", key_hash)


async def assign_orphaned_sessions(user_id: str) -> int:
    """Ordnet Chats aus der Zeit vor der Benutzerverwaltung einem Konto zu.

    Ohne das wären die bestehenden Konversationen für niemanden mehr sichtbar,
    da jede Abfrage jetzt über user_id filtert.
    """
    pool = await get_pool()
    result = await pool.execute(
        "UPDATE chat_sessions SET user_id = $1 WHERE user_id IS NULL",
        user_id,
    )
    return int(result.rsplit(" ", 1)[-1])


# ---------------------------------------------------------------------------
# Anmeldesitzungen
# ---------------------------------------------------------------------------


async def create_auth_session(
    token_hash: str,
    user_id: str,
    ttl_hours: int,
    absolute_ttl_hours: int,
    user_agent: str | None,
    mfa_verified: bool,
    expected_password_hash: str | None = None,
) -> bool:
    pool = await get_pool()
    if expected_password_hash is None:
        row = await pool.fetchrow(
            """
            INSERT INTO auth_sessions (
                token_hash, user_id, expires_at, absolute_expires_at, user_agent,
                mfa_verified_at
            )
            VALUES (
                $1,
                $2,
                now() + make_interval(hours => $3),
                now() + make_interval(hours => $4),
                $5,
                CASE WHEN $6 THEN now() ELSE NULL END
            )
            RETURNING id
            """,
            token_hash,
            user_id,
            ttl_hours,
            absolute_ttl_hours,
            user_agent,
            mfa_verified,
        )
        return row is not None

    row = await pool.fetchrow(
        """
        INSERT INTO auth_sessions (
            token_hash, user_id, expires_at, absolute_expires_at, user_agent,
            mfa_verified_at
        )
        SELECT
            $1,
            u.id,
            now() + make_interval(hours => $3),
            now() + make_interval(hours => $4),
            $5,
            CASE WHEN $6 THEN now() ELSE NULL END
        FROM users u
        WHERE u.id = $2
          AND u.password_hash = $7
          AND u.is_active
        RETURNING id
        """,
        token_hash,
        user_id,
        ttl_hours,
        absolute_ttl_hours,
        user_agent,
        mfa_verified,
        expected_password_hash,
    )
    return row is not None


async def touch_auth_session(token_hash: str, ttl_hours: int) -> dict | None:
    """Löst das Token auf und verlängert die Gültigkeit in einem Zug.

    Liefert nur etwas, wenn die Sitzung nicht abgelaufen und der Benutzer aktiv
    ist — ein Deaktivieren wirkt damit ab dem nächsten Request.
    """
    pool = await get_pool()
    row = await pool.fetchrow(
        f"""
        UPDATE auth_sessions s SET
            last_seen_at = now(),
            expires_at   = LEAST(
                now() + make_interval(hours => $2),
                s.absolute_expires_at
            )
        FROM users u
        WHERE s.token_hash = $1
          AND s.user_id = u.id
          AND s.expires_at > now()
          AND s.absolute_expires_at > now()
          AND u.is_active
        RETURNING
            {_USER_COLUMNS_PREFIXED},
            s.id::text AS session_id,
            s.mfa_verified_at
        """,
        token_hash,
        ttl_hours,
    )
    return dict(row) if row else None


async def delete_auth_session(token_hash: str) -> None:
    pool = await get_pool()
    await pool.execute("DELETE FROM auth_sessions WHERE token_hash = $1", token_hash)


async def delete_auth_sessions_for_user(user_id: str, keep_token_hash: str | None = None) -> None:
    pool = await get_pool()
    if keep_token_hash is None:
        await pool.execute("DELETE FROM auth_sessions WHERE user_id = $1", user_id)
    else:
        await pool.execute(
            "DELETE FROM auth_sessions WHERE user_id = $1 AND token_hash <> $2",
            user_id,
            keep_token_hash,
        )


async def purge_expired_auth_sessions() -> None:
    pool = await get_pool()
    await pool.execute(
        "DELETE FROM auth_sessions WHERE expires_at < now() OR absolute_expires_at < now()"
    )


async def list_auth_sessions(user_id: str, current_token_hash: str) -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT
            id::text AS id,
            created_at,
            last_seen_at,
            expires_at,
            absolute_expires_at,
            user_agent,
            token_hash = $2 AS current
        FROM auth_sessions
        WHERE user_id = $1
          AND expires_at > now()
          AND absolute_expires_at > now()
        ORDER BY current DESC, last_seen_at DESC
        """,
        user_id,
        current_token_hash,
    )
    return [dict(row) for row in rows]


async def delete_auth_session_for_user(session_id: str, user_id: str) -> str | None:
    pool = await get_pool()
    return await pool.fetchval(
        """
        DELETE FROM auth_sessions
        WHERE id::text = $1 AND user_id = $2
        RETURNING token_hash
        """,
        session_id,
        user_id,
    )


async def record_mfa_failure(
    user_id: str, session_id: str, max_attempts: int, lock_minutes: int
) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("SELECT id FROM users WHERE id = $1 FOR UPDATE", user_id)
        pending = await conn.fetchval(
            """
            SELECT 1 FROM auth_sessions
            WHERE id::text = $1 AND user_id = $2 AND mfa_verified_at IS NULL
            FOR UPDATE
            """,
            session_id,
            user_id,
        )
        if pending is None:
            return 0
        attempts = await conn.fetchval(
            """
            UPDATE users SET
                mfa_failed_attempts = mfa_failed_attempts + 1,
                mfa_locked_until = CASE
                    WHEN mfa_failed_attempts + 1 >= $2
                    THEN now() + make_interval(mins => $3)
                    ELSE mfa_locked_until
                END
            WHERE id = $1
            RETURNING mfa_failed_attempts
            """,
            user_id,
            max_attempts,
            lock_minutes,
        )
        attempts = int(attempts or max_attempts)
        if attempts >= max_attempts:
            await conn.execute("DELETE FROM auth_sessions WHERE user_id = $1", user_id)
        return attempts


async def _insert_verified_session(
    conn: asyncpg.Connection,
    token_hash: str,
    user_id: str,
    ttl_hours: int,
    absolute_ttl_hours: int,
    user_agent: str | None,
) -> None:
    await conn.execute(
        """
        INSERT INTO auth_sessions (
            token_hash, user_id, expires_at, absolute_expires_at, user_agent,
            mfa_verified_at
        )
        VALUES (
            $1,
            $2,
            now() + make_interval(hours => $3),
            now() + make_interval(hours => $4),
            $5,
            now()
        )
        """,
        token_hash,
        user_id,
        ttl_hours,
        absolute_ttl_hours,
        user_agent,
    )


async def confirm_mfa_and_create_session(
    user_id: str,
    step: int,
    recovery_codes: list[tuple[str, str]],
    token_hash: str,
    ttl_hours: int,
    absolute_ttl_hours: int,
    user_agent: str | None,
) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        user = await conn.fetchrow(
            """
            SELECT (mfa_locked_until IS NULL OR mfa_locked_until <= now()) AS allowed
            FROM users WHERE id = $1 FOR UPDATE
            """,
            user_id,
        )
        if user is None or not user["allowed"]:
            return False
        confirmed = await conn.fetchval(
            """
            UPDATE user_mfa SET
                confirmed_at = now(),
                last_used_step = $2,
                updated_at = now()
            WHERE user_id = $1 AND confirmed_at IS NULL
            RETURNING user_id
            """,
            user_id,
            step,
        )
        if confirmed is None:
            return False
        await conn.execute("DELETE FROM mfa_recovery_codes WHERE user_id = $1", user_id)
        await conn.executemany(
            """
            INSERT INTO mfa_recovery_codes (id, user_id, secret_hash)
            VALUES ($1, $2, $3)
            """,
            [(code_id, user_id, secret_hash) for code_id, secret_hash in recovery_codes],
        )
        await conn.execute("DELETE FROM auth_sessions WHERE user_id = $1", user_id)
        await _insert_verified_session(
            conn, token_hash, user_id, ttl_hours, absolute_ttl_hours, user_agent
        )
        await conn.execute(
            """
            UPDATE users SET
                mfa_enabled_at = now(),
                failed_logins = 0,
                locked_until = NULL,
                mfa_failed_attempts = 0,
                mfa_locked_until = NULL,
                last_login_at = now(),
                updated_at = now()
            WHERE id = $1
            """,
            user_id,
        )
        return True


async def complete_mfa_login(
    user_id: str,
    token_hash: str,
    ttl_hours: int,
    absolute_ttl_hours: int,
    user_agent: str | None,
    *,
    totp_step: int | None = None,
    recovery_code_id: str | None = None,
) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        user = await conn.fetchrow(
            """
            SELECT (mfa_locked_until IS NULL OR mfa_locked_until <= now()) AS allowed
            FROM users WHERE id = $1 FOR UPDATE
            """,
            user_id,
        )
        if user is None or not user["allowed"]:
            return False
        if totp_step is not None:
            factor = await conn.fetchval(
                """
                UPDATE user_mfa SET last_used_step = $2, updated_at = now()
                WHERE user_id = $1
                  AND confirmed_at IS NOT NULL
                  AND (last_used_step IS NULL OR last_used_step < $2)
                RETURNING user_id
                """,
                user_id,
                totp_step,
            )
        elif recovery_code_id is not None:
            factor = await conn.fetchval(
                """
                UPDATE mfa_recovery_codes SET used_at = now()
                WHERE id = $1 AND user_id = $2 AND used_at IS NULL
                RETURNING id
                """,
                recovery_code_id,
                user_id,
            )
        else:
            return False
        if factor is None:
            return False
        await conn.execute("DELETE FROM auth_sessions WHERE user_id = $1", user_id)
        await _insert_verified_session(
            conn, token_hash, user_id, ttl_hours, absolute_ttl_hours, user_agent
        )
        await conn.execute(
            """
            UPDATE users SET
                failed_logins = 0,
                locked_until = NULL,
                mfa_failed_attempts = 0,
                mfa_locked_until = NULL,
                last_login_at = now()
            WHERE id = $1
            """,
            user_id,
        )
        return True


# ---------------------------------------------------------------------------
# Administrator-MFA
# ---------------------------------------------------------------------------


async def get_mfa(user_id: str) -> dict | None:
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        SELECT secret_ciphertext, confirmed_at, last_used_step
        FROM user_mfa WHERE user_id = $1
        """,
        user_id,
    )
    return dict(row) if row else None


async def save_pending_mfa(user_id: str, secret_ciphertext: str) -> bool:
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO user_mfa (user_id, secret_ciphertext)
        VALUES ($1, $2)
        ON CONFLICT (user_id) DO UPDATE SET
            secret_ciphertext = EXCLUDED.secret_ciphertext,
            last_used_step = NULL,
            updated_at = now()
        WHERE user_mfa.confirmed_at IS NULL
        RETURNING user_id
        """,
        user_id,
        secret_ciphertext,
    )
    return row is not None


async def confirm_mfa(
    user_id: str, step: int, recovery_codes: list[tuple[str, str]]
) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        confirmed = await conn.fetchval(
            """
            UPDATE user_mfa m SET
                confirmed_at = now(),
                last_used_step = $2,
                updated_at = now()
            FROM users u
            WHERE m.user_id = $1
              AND u.id = m.user_id
              AND (u.mfa_locked_until IS NULL OR u.mfa_locked_until <= now())
              AND m.confirmed_at IS NULL
            RETURNING m.user_id
            """,
            user_id,
            step,
        )
        if confirmed is None:
            return False
        await conn.execute("DELETE FROM mfa_recovery_codes WHERE user_id = $1", user_id)
        await conn.executemany(
            """
            INSERT INTO mfa_recovery_codes (id, user_id, secret_hash)
            VALUES ($1, $2, $3)
            """,
            [(code_id, user_id, secret_hash) for code_id, secret_hash in recovery_codes],
        )
        await conn.execute(
            "UPDATE users SET mfa_enabled_at = now(), updated_at = now() WHERE id = $1",
            user_id,
        )
        return True


async def use_totp_step(user_id: str, step: int) -> bool:
    pool = await get_pool()
    result = await pool.execute(
        """
        UPDATE user_mfa m SET last_used_step = $2, updated_at = now()
        FROM users u
        WHERE m.user_id = $1
          AND u.id = m.user_id
          AND (u.mfa_locked_until IS NULL OR u.mfa_locked_until <= now())
          AND m.confirmed_at IS NOT NULL
          AND (m.last_used_step IS NULL OR m.last_used_step < $2)
        """,
        user_id,
        step,
    )
    return result.rsplit(" ", 1)[-1] == "1"


async def get_recovery_code_hash(user_id: str, code_id: str) -> str | None:
    pool = await get_pool()
    return await pool.fetchval(
        """
        SELECT secret_hash FROM mfa_recovery_codes
        WHERE id = $1 AND user_id = $2 AND used_at IS NULL
        """,
        code_id,
        user_id,
    )


async def consume_recovery_code(user_id: str, code_id: str) -> bool:
    pool = await get_pool()
    result = await pool.execute(
        """
        UPDATE mfa_recovery_codes c SET used_at = now()
        FROM users u
        WHERE c.id = $1
          AND c.user_id = $2
          AND c.used_at IS NULL
          AND u.id = c.user_id
          AND (u.mfa_locked_until IS NULL OR u.mfa_locked_until <= now())
        """,
        code_id,
        user_id,
    )
    return result.rsplit(" ", 1)[-1] == "1"


async def count_recovery_codes(user_id: str) -> int:
    pool = await get_pool()
    return await pool.fetchval(
        "SELECT count(*) FROM mfa_recovery_codes WHERE user_id = $1 AND used_at IS NULL",
        user_id,
    )


# ---------------------------------------------------------------------------
# Einladungs- und Reset-Token
# ---------------------------------------------------------------------------


async def create_user_token(
    token_hash: str, user_id: str, purpose: str, ttl_hours: int
) -> None:
    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO user_tokens (token_hash, user_id, purpose, expires_at)
        VALUES ($1, $2, $3, now() + make_interval(hours => $4))
        """,
        token_hash,
        user_id,
        purpose,
        ttl_hours,
    )


async def replace_user_token(
    token_hash: str, user_id: str, purpose: str, ttl_hours: int
) -> None:
    """Serialisiert Neuausgaben pro Benutzer, damit nur der letzte Link gilt."""
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("SELECT id FROM users WHERE id = $1 FOR UPDATE", user_id)
        await conn.execute(
            """
            UPDATE user_tokens SET used_at = now()
            WHERE user_id = $1 AND purpose = $2 AND used_at IS NULL
            """,
            user_id,
            purpose,
        )
        await conn.execute(
            """
            INSERT INTO user_tokens (token_hash, user_id, purpose, expires_at)
            VALUES ($1, $2, $3, now() + make_interval(hours => $4))
            """,
            token_hash,
            user_id,
            purpose,
            ttl_hours,
        )


async def get_user_token(token_hash: str) -> dict | None:
    """Nur gültige Token: nicht abgelaufen, nicht benutzt, Konto existiert.

    Ein abgelaufenes, ein benutztes und ein unbekanntes Token sind für den
    Aufrufer derselbe Fall — er antwortet auf alle drei gleich.
    """
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        SELECT t.purpose, t.user_id::text AS user_id, u.display_name, u.email
        FROM user_tokens t
        JOIN users u ON u.id = t.user_id
        WHERE t.token_hash = $1 AND t.used_at IS NULL AND t.expires_at > now()
        """,
        token_hash,
    )
    return dict(row) if row else None


async def consume_user_token(token_hash: str) -> bool:
    """Entwertet das Token. False, wenn es zwischenzeitlich schon benutzt wurde.

    Die Bedingung steht im UPDATE selbst, damit zwei gleichzeitige Anfragen mit
    demselben Link nicht beide durchkommen.
    """
    pool = await get_pool()
    result = await pool.execute(
        """
        UPDATE user_tokens SET used_at = now()
        WHERE token_hash = $1 AND used_at IS NULL AND expires_at > now()
        """,
        token_hash,
    )
    return result.rsplit(" ", 1)[-1] == "1"


async def invalidate_user_tokens(user_id: str, purpose: str | None = None) -> None:
    pool = await get_pool()
    if purpose is None:
        await pool.execute(
            "UPDATE user_tokens SET used_at = now() WHERE user_id = $1 AND used_at IS NULL",
            user_id,
        )
    else:
        await pool.execute(
            """
            UPDATE user_tokens SET used_at = now()
            WHERE user_id = $1 AND purpose = $2 AND used_at IS NULL
            """,
            user_id,
            purpose,
        )


async def purge_expired_user_tokens() -> None:
    pool = await get_pool()
    await pool.execute("DELETE FROM user_tokens WHERE expires_at < now() - interval '30 days'")


# ---------------------------------------------------------------------------
# Fristen-Erinnerung
# ---------------------------------------------------------------------------


async def claim_digest_recipient(digest_date, user_id: str, owner_id: str) -> bool:
    pool = await get_pool()
    row = await pool.fetchval(
        """
        INSERT INTO mail_digest_deliveries (digest_date, user_id, claimed_at, owner_id)
        VALUES ($1, $2::uuid, now(), $3::uuid)
        ON CONFLICT (digest_date, user_id) DO UPDATE
        SET claimed_at = EXCLUDED.claimed_at, owner_id = EXCLUDED.owner_id
        WHERE mail_digest_deliveries.sent_at IS NULL
          AND mail_digest_deliveries.claimed_at IS NULL
        RETURNING owner_id
        """,
        digest_date,
        user_id,
        owner_id,
    )
    return str(row) == owner_id


async def release_digest_recipient(digest_date, user_id: str, owner_id: str) -> None:
    pool = await get_pool()
    await pool.execute(
        """
        UPDATE mail_digest_deliveries SET claimed_at = NULL, owner_id = NULL
        WHERE digest_date = $1 AND user_id = $2::uuid AND owner_id = $3::uuid
          AND sent_at IS NULL
        """,
        digest_date,
        user_id,
        owner_id,
    )


async def complete_digest_recipient(digest_date, user_id: str, owner_id: str) -> None:
    pool = await get_pool()
    await pool.execute(
        """
        UPDATE mail_digest_deliveries
        SET claimed_at = NULL, owner_id = NULL, sent_at = now()
        WHERE digest_date = $1 AND user_id = $2::uuid AND owner_id = $3::uuid
          AND sent_at IS NULL
        """,
        digest_date,
        user_id,
        owner_id,
    )


async def list_digest_recipients() -> list[dict]:
    """Aktive Admins und Bearbeiter. Betrachter können mit einer Frist nichts anfangen."""
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT id::text AS id, email, display_name, role, object_access_mode FROM users
        WHERE is_active AND role IN ('admin', 'editor')
        ORDER BY email
        """
    )
    users = [dict(r) for r in rows]
    for user in users:
        user["object_codes"] = list(await get_object_scope(user["id"]))
    return users


# ---------------------------------------------------------------------------
# E-Mail-Entwürfe des Assistenten
# ---------------------------------------------------------------------------


async def create_email_draft(
    user_id: str,
    session_id: str | None,
    recipient: str,
    subject: str,
    body: str,
    document_id: int | None,
) -> dict:
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO email_drafts (user_id, session_id, recipient, subject, body, document_id)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id::text AS id, recipient, subject, body, document_id, created_at, sent_at
        """,
        user_id,
        session_id,
        recipient,
        subject,
        body,
        document_id,
    )
    return dict(row)


async def get_email_draft(draft_id: str, user_id: str) -> dict | None:
    """Nur der eigene Entwurf. Ein fremder ist für den Aufrufer nicht vorhanden."""
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        SELECT id::text AS id, recipient, subject, body, document_id, created_at, sent_at
        FROM email_drafts WHERE id = $1 AND user_id = $2
        """,
        draft_id,
        user_id,
    )
    return dict(row) if row else None


async def mark_email_draft_sent(
    draft_id: str, user_id: str, recipient: str, subject: str, body: str
) -> dict | None:
    """Hält den tatsächlich verschickten Wortlaut fest — er darf vom Entwurf abweichen.

    `sent_at IS NULL` in der Bedingung verhindert einen zweiten Versand, auch bei
    zwei gleichzeitigen Klicks.
    """
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        UPDATE email_drafts SET sent_at = now(), recipient = $3, subject = $4, body = $5
        WHERE id = $1 AND user_id = $2 AND sent_at IS NULL AND send_claimed_at IS NOT NULL
        RETURNING id::text AS id, recipient, subject, body, document_id, created_at, sent_at
        """,
        draft_id,
        user_id,
        recipient,
        subject,
        body,
    )
    return dict(row) if row else None


async def claim_email_draft_for_send(draft_id: str, user_id: str) -> bool:
    pool = await get_pool()
    result = await pool.execute(
        """
        UPDATE email_drafts SET send_claimed_at = now()
        WHERE id = $1
          AND user_id = $2
          AND sent_at IS NULL
          AND (send_claimed_at IS NULL OR send_claimed_at < now() - interval '10 minutes')
        """,
        draft_id,
        user_id,
    )
    return result.rsplit(" ", 1)[-1] == "1"


async def release_email_draft_claim(draft_id: str, user_id: str) -> None:
    pool = await get_pool()
    await pool.execute(
        """
        UPDATE email_drafts SET send_claimed_at = NULL
        WHERE id = $1 AND user_id = $2 AND sent_at IS NULL
        """,
        draft_id,
        user_id,
    )


async def claim_mail_intake_document(paperless_id: int, owner_id: str) -> bool:
    pool = await get_pool()
    row = await pool.fetchval(
        """
        INSERT INTO mail_intake_claims (paperless_id, owner_id)
        VALUES ($1, $2::uuid)
        ON CONFLICT (paperless_id) DO UPDATE
        SET claimed_at = now(), owner_id = EXCLUDED.owner_id
        WHERE mail_intake_claims.completed_at IS NULL
          AND (
            mail_intake_claims.claimed_at IS NULL
            OR mail_intake_claims.claimed_at < now() - interval '15 minutes'
          )
        RETURNING owner_id
        """,
        paperless_id,
        owner_id,
    )
    return str(row) == owner_id


async def release_mail_intake_document(paperless_id: int, owner_id: str) -> None:
    pool = await get_pool()
    await pool.execute(
        """
        UPDATE mail_intake_claims SET claimed_at = NULL, owner_id = NULL
        WHERE paperless_id = $1 AND owner_id = $2::uuid AND completed_at IS NULL
        """,
        paperless_id,
        owner_id,
    )


async def renew_mail_intake_document(paperless_id: int, owner_id: str) -> bool:
    pool = await get_pool()
    result = await pool.execute(
        """
        UPDATE mail_intake_claims SET claimed_at = now()
        WHERE paperless_id = $1 AND owner_id = $2::uuid AND completed_at IS NULL
        """,
        paperless_id,
        owner_id,
    )
    return result.rsplit(" ", 1)[-1] == "1"


async def complete_mail_intake_document(paperless_id: int, owner_id: str) -> None:
    pool = await get_pool()
    await pool.execute(
        """
        UPDATE mail_intake_claims SET claimed_at = NULL, owner_id = NULL, completed_at = now()
        WHERE paperless_id = $1 AND owner_id = $2::uuid
        """,
        paperless_id,
        owner_id,
    )


async def create_intake_case(
    paperless_id: int,
    owner_id: str,
    tracking_id: str,
    title: str,
    summary: str | None,
    status: str,
    sender_email: str | None,
    object_code: str | None,
) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        claim = await conn.fetchrow(
            "SELECT case_id, owner_id FROM mail_intake_claims WHERE paperless_id = $1 FOR UPDATE",
            paperless_id,
        )
        if claim is None:
            raise RuntimeError("Mail intake document has no authorization claim")
        if str(claim["owner_id"]) != owner_id:
            raise RuntimeError("Mail intake authorization claim changed owner")
        if claim["case_id"] is not None:
            row = await conn.fetchrow(
                """
                SELECT id::text AS id, tracking_id, title, summary, status, sender_email,
                       object_code, created_at, closed_at
                FROM cases WHERE id = $1
                """,
                claim["case_id"],
            )
            result = dict(row)
            result["_created"] = False
            return result
        row = await conn.fetchrow(
            """
            INSERT INTO cases (tracking_id, title, summary, status, sender_email, object_code)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id, tracking_id, title, summary, status, sender_email, object_code,
                      created_at, closed_at
            """,
            tracking_id,
            title,
            summary,
            status,
            sender_email,
            object_code,
        )
        await conn.execute(
            "UPDATE mail_intake_claims SET case_id = $2 WHERE paperless_id = $1",
            paperless_id,
            row["id"],
        )
        result = dict(row)
        result["id"] = str(result["id"])
        result["_created"] = True
        return result


async def get_object_scope(user_id: str) -> frozenset[str]:
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT object_name FROM user_object_scopes WHERE user_id = $1", user_id
    )
    return frozenset(r["object_name"] for r in rows)


@asynccontextmanager
async def authorization_lease(
    user_id: str,
    expected_role: str,
    expected_mode: str,
    expected_codes: frozenset[str],
):
    """Stabiler Auth-Kontext für einen Toolaufruf.

    Rollen- und Scope-Updates sperren dieselbe Benutzerzeile exklusiv und können
    daher erst committen, nachdem der laufende Toolaufruf beendet ist.
    """
    async with _AUTHORIZATION_LEASE_LIMIT:
        pool = await get_pool()
        async with pool.acquire() as conn, conn.transaction():
            user = await conn.fetchrow(
                """
                SELECT role, is_active, object_access_mode
                FROM users WHERE id = $1 FOR SHARE
                """,
                user_id,
            )
            rows = await conn.fetch(
                "SELECT object_name FROM user_object_scopes WHERE user_id = $1",
                user_id,
            )
            current_codes = frozenset(row["object_name"] for row in rows)
            valid = bool(
                user
                and user["is_active"]
                and user["role"] == str(expected_role)
                and user["object_access_mode"] == str(expected_mode)
                and current_codes == expected_codes
            )
            yield valid


async def set_object_scope(user_id: str, mode: str, object_codes: tuple[str, ...]) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock($1)", _ADMIN_MUTATION_LOCK)
        current = await conn.fetchrow(
            "SELECT role, is_active, object_access_mode FROM users WHERE id = $1 FOR UPDATE",
            user_id,
        )
        if current is None:
            return False
        if (
            current["role"] == "admin"
            and current["is_active"]
            and current["object_access_mode"] == "all"
            and mode != "all"
        ):
            global_admins = await conn.fetchval(
                """
                SELECT count(*) FROM users
                WHERE role = 'admin' AND is_active AND object_access_mode = 'all'
                """
            )
            if global_admins <= 1:
                raise LastGlobalAdminError
        updated = await conn.fetchval(
            """
            UPDATE users SET object_access_mode = $2, updated_at = now()
            WHERE id = $1 RETURNING id
            """,
            user_id,
            mode,
        )
        if updated is None:
            return False
        await conn.execute("DELETE FROM user_object_scopes WHERE user_id = $1", user_id)
        if object_codes:
            await conn.executemany(
                "INSERT INTO user_object_scopes (user_id, object_name) VALUES ($1, $2)",
                [(user_id, code) for code in object_codes],
            )
        # Alte Antworten und Entwürfe können Inhalte aus dem vorherigen Scope
        # enthalten. Ohne feinere Provenienz ist Löschen die einzige fail-closed
        # Variante; laufende Anmeldesitzungen werden ebenfalls entzogen.
        await conn.execute("DELETE FROM chat_sessions WHERE user_id = $1", user_id)
        await conn.execute("DELETE FROM email_drafts WHERE user_id = $1", user_id)
        await conn.execute("DELETE FROM auth_sessions WHERE user_id = $1", user_id)
        return True


# --- Absender-Freigabe -----------------------------------------------------


async def upsert_pending_sender(email: str) -> None:
    """Neuer Absender: pending anlegen. Bekannter Absender: nur last_seen_at
    aktualisieren — status bleibt unangetastet, eine erneute Mail von einem
    bereits freigegebenen oder abgelehnten Absender ändert daran nichts."""
    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO mail_sender_trust (email, status, first_seen_at, last_seen_at)
        VALUES ($1, 'pending', now(), now())
        ON CONFLICT (email) DO UPDATE SET last_seen_at = now()
        """,
        email,
    )


async def approve_sender(email: str, user_id: str, trust_days: int) -> dict:
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO mail_sender_trust (email, status, approved_by, approved_at, expires_at)
        VALUES ($1, 'approved', $2, now(), now() + make_interval(days => $3))
        ON CONFLICT (email) DO UPDATE SET
            status = 'approved', approved_by = $2, approved_at = now(),
            expires_at = now() + make_interval(days => $3)
        RETURNING email, status, approved_by::text AS approved_by, approved_at, expires_at,
                  first_seen_at, last_seen_at
        """,
        email,
        user_id,
        trust_days,
    )
    return dict(row)


async def reject_sender(email: str, user_id: str) -> dict:
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO mail_sender_trust (email, status, approved_by, approved_at, expires_at)
        VALUES ($1, 'rejected', $2, now(), NULL)
        ON CONFLICT (email) DO UPDATE SET
            status = 'rejected', approved_by = $2, approved_at = now(), expires_at = NULL
        RETURNING email, status, approved_by::text AS approved_by, approved_at, expires_at,
                  first_seen_at, last_seen_at
        """,
        email,
        user_id,
    )
    return dict(row)


async def list_senders(status: str | None = None) -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT email, status, approved_by::text AS approved_by, approved_at, expires_at,
               first_seen_at, last_seen_at
        FROM mail_sender_trust
        WHERE ($1::text IS NULL OR status = $1)
        ORDER BY last_seen_at DESC
        """,
        status,
    )
    return [dict(r) for r in rows]


async def is_sender_trusted(email: str) -> bool:
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        SELECT 1 FROM mail_sender_trust
        WHERE email = $1 AND status = 'approved' AND (expires_at IS NULL OR expires_at > now())
        """,
        email,
    )
    return row is not None


# --- Anliegen (Cases) --------------------------------------------------------


async def next_tracking_id() -> str:
    """Atomarer Jahres-Zähler statt count(*): eine gelöschte Zeile würde sonst eine
    Nummer für eine spätere Vergabe wieder freigeben, was zwei Anliegen dieselbe
    Tracking-ID geben könnte. INSERT ... ON CONFLICT sperrt die Zeile für die Dauer
    der Transaktion, zwei gleichzeitige Aufrufe bekommen also nie dieselbe Zahl."""
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO case_tracking_seq (year, next_seq)
        VALUES (EXTRACT(YEAR FROM now())::int, 2)
        ON CONFLICT (year) DO UPDATE SET next_seq = case_tracking_seq.next_seq + 1
        RETURNING year, next_seq - 1 AS seq
        """
    )
    return f"AL-{row['year']}-{row['seq']:04d}"


async def create_case(
    tracking_id: str,
    title: str,
    summary: str | None,
    status: str,
    sender_email: str | None,
    object_code: str | None,
) -> dict:
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO cases (tracking_id, title, summary, status, sender_email, object_code)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id::text AS id, tracking_id, title, summary, status, sender_email, object_code,
                  created_at, closed_at
        """,
        tracking_id,
        title,
        summary,
        status,
        sender_email,
        object_code,
    )
    return dict(row)


async def get_case(tracking_id: str) -> dict | None:
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        SELECT id::text AS id, tracking_id, title, summary, status, sender_email, object_code,
               created_at, closed_at
        FROM cases WHERE tracking_id = $1
        """,
        tracking_id,
    )
    return dict(row) if row else None


async def list_cases(status: str | None = None) -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT id::text AS id, tracking_id, title, summary, status, sender_email, object_code,
               created_at, closed_at
        FROM cases
        WHERE ($1::text IS NULL OR status = $1)
        ORDER BY created_at DESC
        """,
        status,
    )
    return [dict(r) for r in rows]


async def search_cases(
    query: str,
    status: str | None = None,
    *,
    unrestricted: bool = True,
    object_codes: tuple[str, ...] = (),
) -> list[dict]:
    """Für den lesenden Werkzeugsatz der Fallanalyse (mail/case_agent.py) — findet
    auch Treffer, die nur in einer Notiz stehen, nicht nur in Titel/Zusammenfassung."""
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT DISTINCT c.id::text AS id, c.tracking_id, c.title, c.summary, c.status,
                        c.object_code, c.created_at
        FROM cases c
        LEFT JOIN case_notes n ON n.case_id = c.id
        WHERE (c.title ILIKE '%' || $1 || '%' OR c.summary ILIKE '%' || $1 || '%' OR n.body ILIKE '%' || $1 || '%')
          AND ($2::text IS NULL OR c.status = $2)
          AND ($3 OR c.object_code = ANY($4::text[]))
        ORDER BY c.created_at DESC
        LIMIT 20
        """,
        query,
        status,
        unrestricted,
        list(object_codes),
    )
    return [dict(r) for r in rows]


async def list_cases_by_object_code(object_code: str) -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT id::text AS id, tracking_id, title, summary, status, created_at
        FROM cases WHERE object_code = $1
        ORDER BY created_at DESC
        """,
        object_code,
    )
    return [dict(r) for r in rows]


async def find_recent_case_by_sender(sender_email: str, within_minutes: int = 15) -> dict | None:
    """Bestes-Ergebnis-Gruppierung: Paperless legt eine Mail und ihre Anhaenge als
    getrennte Dokumente an, ohne eine gemeinsame Kennung dafuer zu liefern. Ueber
    denselben Absender innerhalb eines engen Zeitfensters lassen sie sich in der
    Praxis trotzdem demselben Anliegen zuordnen."""
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        SELECT id::text AS id, tracking_id FROM cases
        WHERE sender_email = $1 AND created_at > now() - make_interval(mins => $2)
        ORDER BY created_at DESC LIMIT 1
        """,
        sender_email,
        within_minutes,
    )
    return dict(row) if row else None


async def close_case(tracking_id: str) -> dict | None:
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        UPDATE cases SET status = 'closed', closed_at = now()
        WHERE tracking_id = $1 AND status != 'closed'
        RETURNING id::text AS id, tracking_id, title, summary, status, sender_email, object_code,
                  created_at, closed_at
        """,
        tracking_id,
    )
    return dict(row) if row else None


async def reopen_case(tracking_id: str) -> dict | None:
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        UPDATE cases SET status = 'open', closed_at = NULL
        WHERE tracking_id = $1 AND status != 'open'
        RETURNING id::text AS id, tracking_id, title, summary, status, sender_email, object_code,
                  created_at, closed_at
        """,
        tracking_id,
    )
    return dict(row) if row else None


async def add_case_document(case_id: str, paperless_id: int, role: str) -> None:
    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO case_documents (case_id, paperless_id, role)
        VALUES ($1, $2, $3)
        ON CONFLICT (case_id, paperless_id) DO NOTHING
        """,
        case_id,
        paperless_id,
        role,
    )


async def list_case_documents(case_id: str) -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT paperless_id, role, added_at FROM case_documents WHERE case_id = $1 ORDER BY added_at",
        case_id,
    )
    return [dict(r) for r in rows]


async def remove_case_document(case_id: str, paperless_id: int) -> None:
    pool = await get_pool()
    await pool.execute(
        "DELETE FROM case_documents WHERE case_id = $1 AND paperless_id = $2",
        case_id,
        paperless_id,
    )


async def add_case_event(
    case_id: str,
    kind: str,
    detail: str | None = None,
    actor_user_id: str | None = None,
    actor_label: str | None = None,
    link_kind: str | None = None,
    link_id: str | None = None,
) -> dict:
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO case_events (case_id, kind, detail, actor_user_id, actor_label, link_kind, link_id)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING id::text AS id, kind, detail, actor_user_id::text AS actor_user_id, actor_label,
                  link_kind, link_id, created_at
        """,
        case_id,
        kind,
        detail,
        actor_user_id,
        actor_label,
        link_kind,
        link_id,
    )
    return dict(row)


async def list_case_events(case_id: str) -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT e.id::text AS id, e.kind, e.detail, e.actor_user_id::text AS actor_user_id,
               u.display_name AS actor_name, e.actor_label, e.link_kind, e.link_id, e.created_at
        FROM case_events e
        LEFT JOIN users u ON u.id = e.actor_user_id
        WHERE e.case_id = $1
        ORDER BY e.created_at
        """,
        case_id,
    )
    return [dict(r) for r in rows]


async def has_chat_link_event(case_id: str, session_id: str) -> bool:
    """Verhindert, dass ein und dieselbe Unterhaltung bei jedem erneuten 'get_case'
    einen weiteren 'Im Chat besprochen'-Eintrag erzeugt."""
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        SELECT 1 FROM case_events
        WHERE case_id = $1 AND kind = 'chat_linked' AND link_kind = 'session' AND link_id = $2
        LIMIT 1
        """,
        case_id,
        session_id,
    )
    return row is not None


async def add_case_note(case_id: str, author_user_id: str | None, body: str) -> dict:
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO case_notes (case_id, author_user_id, body)
        VALUES ($1, $2, $3)
        RETURNING id::text AS id, author_user_id::text AS author_user_id, body, created_at
        """,
        case_id,
        author_user_id,
        body,
    )
    return dict(row)


async def list_case_notes(case_id: str) -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT n.id::text AS id, n.author_user_id::text AS author_user_id,
               u.display_name AS author_name, n.body, n.created_at
        FROM case_notes n
        LEFT JOIN users u ON u.id = n.author_user_id
        WHERE n.case_id = $1
        ORDER BY n.created_at
        """,
        case_id,
    )
    return [dict(r) for r in rows]


async def propose_case_link(dependent_tracking_id: str, prerequisite_tracking_id: str, proposed_by: str) -> dict | None:
    """proposed_by ist 'agent' oder eine user_id. Beide Tracking-IDs müssen bereits
    existierende Anliegen sein — sonst None statt eines Fremdschlüsselfehlers,
    damit ein vom Modell erfundenes Tracking-ID nur verworfen statt geworfen wird."""
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO case_links (dependent_case_id, prerequisite_case_id, status, proposed_by)
        SELECT d.id, p.id, 'proposed', $3
        FROM cases d, cases p
        WHERE d.tracking_id = $1 AND p.tracking_id = $2
        ON CONFLICT (dependent_case_id, prerequisite_case_id) DO NOTHING
        RETURNING dependent_case_id::text AS dependent_case_id,
                  prerequisite_case_id::text AS prerequisite_case_id, status, proposed_by, created_at
        """,
        dependent_tracking_id,
        prerequisite_tracking_id,
        proposed_by,
    )
    return dict(row) if row else None


async def confirm_case_link(dependent_tracking_id: str, prerequisite_tracking_id: str) -> dict | None:
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        UPDATE case_links SET status = 'confirmed'
        WHERE dependent_case_id = (SELECT id FROM cases WHERE tracking_id = $1)
          AND prerequisite_case_id = (SELECT id FROM cases WHERE tracking_id = $2)
        RETURNING dependent_case_id::text AS dependent_case_id,
                  prerequisite_case_id::text AS prerequisite_case_id, status, proposed_by, created_at
        """,
        dependent_tracking_id,
        prerequisite_tracking_id,
    )
    return dict(row) if row else None


async def remove_case_link(dependent_tracking_id: str, prerequisite_tracking_id: str) -> None:
    pool = await get_pool()
    await pool.execute(
        """
        DELETE FROM case_links
        WHERE dependent_case_id = (SELECT id FROM cases WHERE tracking_id = $1)
          AND prerequisite_case_id = (SELECT id FROM cases WHERE tracking_id = $2)
        """,
        dependent_tracking_id,
        prerequisite_tracking_id,
    )


async def list_case_links_for(tracking_id: str) -> list[dict]:
    """Alle Verknüpfungen, in denen dieses Anliegen auf einer der beiden Seiten
    steht — mit der Tracking-ID/dem Titel der jeweils anderen Seite, damit die
    Oberfläche nicht noch einmal nachschlagen muss."""
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT d.tracking_id AS dependent_tracking_id, d.title AS dependent_title,
               p.tracking_id AS prerequisite_tracking_id, p.title AS prerequisite_title,
               l.status, l.proposed_by, l.created_at
        FROM case_links l
        JOIN cases d ON d.id = l.dependent_case_id
        JOIN cases p ON p.id = l.prerequisite_case_id
        WHERE d.tracking_id = $1 OR p.tracking_id = $1
        ORDER BY l.created_at
        """,
        tracking_id,
    )
    return [dict(r) for r in rows]


async def list_all_case_links() -> list[dict]:
    """Die komplette Kantenliste für den Abhängigkeitsgraphen."""
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT d.tracking_id AS dependent_tracking_id, p.tracking_id AS prerequisite_tracking_id,
               l.status, l.proposed_by, l.created_at
        FROM case_links l
        JOIN cases d ON d.id = l.dependent_case_id
        JOIN cases p ON p.id = l.prerequisite_case_id
        ORDER BY l.created_at
        """
    )
    return [dict(r) for r in rows]
