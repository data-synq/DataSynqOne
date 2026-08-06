from .openai_client import get_client

from .config import settings

MAX_CHARS = 24000



async def embed_text(text: str) -> list[float]:
    resp = await get_client().embeddings.create(model=settings.embedding_model, input=text[:MAX_CHARS])
    return resp.data[0].embedding


async def embed_query(query: str) -> list[float]:
    return await embed_text(query)
