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

from .config import reveal_secret, settings


@lru_cache(maxsize=1)
def _get_transport() -> AsyncOpenAI:
    # Pydantic is the authoritative source; the SDK must not silently bypass
    # validation by reading OPENAI_API_KEY from the ambient environment itself.
    api_key = reveal_secret(settings.openai_api_key)
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY ist nicht konfiguriert.")
    return AsyncOpenAI(api_key=api_key)
