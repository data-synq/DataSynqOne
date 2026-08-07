import json

import asyncpg
from pgvector.asyncpg import register_vector

from .config import settings

_pool: asyncpg.Pool | None = None


async def _init_connection(conn: asyncpg.Connection) -> None:
    await register_vector(conn)


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(settings.database_url, init=_init_connection)
    return _pool


async def init_db() -> None:
    conn = await asyncpg.connect(settings.database_url)
    try:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    finally:
        await conn.close()

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS document_embeddings (
                id              SERIAL PRIMARY KEY,
                paperless_id    INTEGER NOT NULL UNIQUE,
                title           TEXT NOT NULL,
                correspondent   TEXT,
                document_type   TEXT,
                tags            TEXT[],
                created_date    DATE,
                content_hash    TEXT NOT NULL,
                embedding       VECTOR(1536) NOT NULL,
                last_synced_at  TIMESTAMPTZ NOT NULL DEFAULT now()
            )
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
                failed_logins        INTEGER NOT NULL DEFAULT 0,
                locked_until         TIMESTAMPTZ,
                last_login_at        TIMESTAMPTZ,
                created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        # Sitzungen liegen serverseitig statt in einem JWT: so ist ein deaktivierter
        # Benutzer sofort draußen, ohne Sperrliste und ohne auf einen Tokenablauf zu
        # warten. Gespeichert wird nur der SHA-256 des Cookie-Tokens — wer die Tabelle
        # liest, kann damit keine Sitzung übernehmen.
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_sessions (
                token_hash   TEXT PRIMARY KEY,
                user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
                last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                expires_at   TIMESTAMPTZ NOT NULL,
                user_agent   TEXT
            )
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS auth_sessions_user_idx ON auth_sessions(user_id)"
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


async def close_db() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


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
    created_date,
    content_hash: str,
    embedding: list[float],
) -> None:
    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO document_embeddings
            (paperless_id, title, correspondent, document_type, tags, created_date, content_hash, embedding, last_synced_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, now())
        ON CONFLICT (paperless_id) DO UPDATE SET
            title = EXCLUDED.title,
            correspondent = EXCLUDED.correspondent,
            document_type = EXCLUDED.document_type,
            tags = EXCLUDED.tags,
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


async def similarity_search(query_embedding: list[float], limit: int = 10) -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT paperless_id, title, correspondent, document_type, created_date,
               1 - (embedding <=> $1) AS score
        FROM document_embeddings
        ORDER BY embedding <=> $1
        LIMIT $2
        """,
        query_embedding,
        limit,
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
) -> None:
    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO chat_messages (session_id, role, content, tool_calls)
        VALUES ($1, $2, $3, $4)
        """,
        session_id,
        role,
        content,
        json.dumps(tool_calls) if tool_calls is not None else None,
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
        SELECT m.role, m.content, m.tool_calls
        FROM chat_messages m
        JOIN chat_sessions s ON s.id = m.session_id
        WHERE m.session_id = $1 AND s.user_id = $2
        ORDER BY m.id ASC
        """,
        session_id,
        user_id,
    )
    messages = []
    for r in rows:
        row = dict(r)
        if row.get("tool_calls") is not None:
            row["tool_calls"] = json.loads(row["tool_calls"])
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
    failed_logins, locked_until, last_login_at, created_at, updated_at
"""

# Dieselben Spalten für Abfragen mit Join, in denen `id` und `role` mehrdeutig wären.
_USER_COLUMNS_PREFIXED = """
    u.id::text AS id, u.email, u.display_name, u.role, u.is_active, u.must_change_password,
    u.failed_logins, u.locked_until, u.last_login_at, u.created_at, u.updated_at
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
) -> dict:
    pool = await get_pool()
    row = await pool.fetchrow(
        f"""
        INSERT INTO users (email, display_name, password_hash, role, must_change_password)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING {_USER_COLUMNS}
        """,
        email.strip().lower(),
        display_name.strip(),
        password_hash,
        role,
        must_change_password,
    )
    return dict(row)


async def get_user_by_email(email: str) -> dict | None:
    """Inklusive Hash und Sperrzustand — nur für den Login gedacht."""
    pool = await get_pool()
    row = await pool.fetchrow(
        f"SELECT {_USER_COLUMNS}, password_hash FROM users WHERE email = $1",
        email.strip().lower(),
    )
    return dict(row) if row else None


async def get_user_by_id(user_id: str) -> dict | None:
    pool = await get_pool()
    row = await pool.fetchrow(f"SELECT {_USER_COLUMNS} FROM users WHERE id = $1", user_id)
    return dict(row) if row else None


async def get_password_hash(user_id: str) -> str | None:
    pool = await get_pool()
    return await pool.fetchval("SELECT password_hash FROM users WHERE id = $1", user_id)


async def list_users() -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(f"SELECT {_USER_COLUMNS} FROM users ORDER BY display_name ASC")
    return [dict(r) for r in rows]


async def update_user(
    user_id: str,
    display_name: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
) -> dict | None:
    pool = await get_pool()
    row = await pool.fetchrow(
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
    return dict(row) if row else None


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


async def delete_user(user_id: str) -> None:
    pool = await get_pool()
    await pool.execute("DELETE FROM users WHERE id = $1", user_id)


async def record_login_success(user_id: str) -> None:
    pool = await get_pool()
    await pool.execute(
        """
        UPDATE users SET failed_logins = 0, locked_until = NULL, last_login_at = now()
        WHERE id = $1
        """,
        user_id,
    )


async def record_login_failure(user_id: str, max_attempts: int, lock_minutes: int) -> None:
    """Zählt den Fehlversuch und sperrt das Konto, sobald das Limit erreicht ist."""
    pool = await get_pool()
    await pool.execute(
        """
        UPDATE users SET
            failed_logins = failed_logins + 1,
            locked_until  = CASE
                WHEN failed_logins + 1 >= $2 THEN now() + make_interval(mins => $3)
                ELSE locked_until
            END
        WHERE id = $1
        """,
        user_id,
        max_attempts,
        lock_minutes,
    )


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
    token_hash: str, user_id: str, ttl_hours: int, user_agent: str | None
) -> None:
    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO auth_sessions (token_hash, user_id, expires_at, user_agent)
        VALUES ($1, $2, now() + make_interval(hours => $3), $4)
        """,
        token_hash,
        user_id,
        ttl_hours,
        user_agent,
    )


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
            expires_at   = now() + make_interval(hours => $2)
        FROM users u
        WHERE s.token_hash = $1
          AND s.user_id = u.id
          AND s.expires_at > now()
          AND u.is_active
        RETURNING {_USER_COLUMNS_PREFIXED}
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
    await pool.execute("DELETE FROM auth_sessions WHERE expires_at < now()")


async def get_object_scope(user_id: str) -> frozenset[str] | None:
    """Objekte, auf die dieser Benutzer eingeschränkt ist. None heißt: alle.

    Die Tabelle wird heute von niemandem befüllt; die Funktion existiert, damit
    der spätere Objekt-Filter nur eine Stelle braucht und nicht überall in
    dashboard_service und den Agent-Werkzeugen nachgezogen werden muss.
    """
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT object_name FROM user_object_scopes WHERE user_id = $1", user_id
    )
    if not rows:
        return None
    return frozenset(r["object_name"] for r in rows)
