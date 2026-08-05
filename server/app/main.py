from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import close_db, init_db
from .paperless_client import paperless_client
from .routers import agent, dashboard, documents, sessions, sync
from .tag_seed import seed_tags


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await seed_tags()
    yield
    await close_db()
    await paperless_client.close()


app = FastAPI(title="Paperless Agent Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router)
app.include_router(agent.router)
app.include_router(sessions.router)
app.include_router(sync.router)
app.include_router(dashboard.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
