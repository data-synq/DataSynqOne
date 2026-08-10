from .ai_gateway import embedding
from .ai_privacy import AIPurpose
from .config import settings

MAX_CHARS = 24000



async def embed_text(text: str) -> list[float]:
    return await embedding(
        AIPurpose.DOCUMENT_EMBEDDING, model=settings.embedding_model, input=text[:MAX_CHARS]
    )


async def embed_query(query: str) -> list[float]:
    return await embedding(
        AIPurpose.QUERY_EMBEDDING, model=settings.embedding_model, input=query[:MAX_CHARS]
    )
