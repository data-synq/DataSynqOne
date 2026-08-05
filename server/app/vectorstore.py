from openai import AsyncOpenAI

from .config import settings

MAX_CHARS = 24000

_client = AsyncOpenAI(api_key=settings.openai_api_key)


async def embed_text(text: str) -> list[float]:
    resp = await _client.embeddings.create(model=settings.embedding_model, input=text[:MAX_CHARS])
    return resp.data[0].embedding


async def embed_query(query: str) -> list[float]:
    return await embed_text(query)
