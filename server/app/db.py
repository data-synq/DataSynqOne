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


async def create_session(session_id: str, title: str) -> None:
    pool = await get_pool()
    await pool.execute(
        "INSERT INTO chat_sessions (id, title) VALUES ($1, $2)",
        session_id,
        title,
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


async def list_sessions() -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT id, title, created_at, updated_at FROM chat_sessions ORDER BY updated_at DESC"
    )
    return [dict(r) for r in rows]


async def get_session_messages(session_id: str) -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT role, content, tool_calls
        FROM chat_messages
        WHERE session_id = $1
        ORDER BY id ASC
        """,
        session_id,
    )
    messages = []
    for r in rows:
        row = dict(r)
        if row.get("tool_calls") is not None:
            row["tool_calls"] = json.loads(row["tool_calls"])
        messages.append(row)
    return messages


async def delete_session(session_id: str) -> None:
    pool = await get_pool()
    await pool.execute("DELETE FROM chat_sessions WHERE id = $1", session_id)
