"""Lazy shared AsyncOpenAI client.

Five modules used to build their own client at import time
(`AsyncOpenAI(api_key=settings.openai_api_key)`). With the default empty
key the constructor raises, which meant the whole app crashed on import —
uvicorn could not even boot without a key, long before any request needed
one. Constructing lazily keeps startup independent of credentials; a
missing key now surfaces on the first agent/embedding call instead.
"""

from functools import lru_cache

from openai import AsyncOpenAI

from .config import settings


@lru_cache(maxsize=1)
def get_client() -> AsyncOpenAI:
    # `or None` lets the SDK fall back to the OPENAI_API_KEY env var
    # instead of treating the empty default as an explicit (bad) key.
    return AsyncOpenAI(api_key=settings.openai_api_key or None)
