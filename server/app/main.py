from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth import Permission, require
from .auth.bootstrap import ensure_bootstrap_admin
from .config import settings
from .db import close_db, init_db
from .paperless_client import paperless_client
from .routers import agent, auth, dashboard, documents, sessions, sync, users
from .tag_seed import seed_tags


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await ensure_bootstrap_admin()
    await seed_tags()
    yield
    await close_db()
    await paperless_client.close()


app = FastAPI(title="Paperless Agent Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    # Ohne das schickt der Browser das Session-Cookie bei einem Cross-Origin-Aufruf
    # nicht mit. Produktion und `make dev` laufen zwar same-origin über /api, der
    # direkte Zugriff auf :8001 aber nicht.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(
    documents.router, dependencies=[Depends(require(Permission.DOCUMENTS_READ))]
)
app.include_router(agent.router, dependencies=[Depends(require(Permission.AGENT_CHAT))])
app.include_router(sessions.router, dependencies=[Depends(require(Permission.AGENT_CHAT))])
app.include_router(sync.router, dependencies=[Depends(require(Permission.SYNC_RUN))])
app.include_router(
    dashboard.router, dependencies=[Depends(require(Permission.DOCUMENTS_READ))]
)


# Bewusst ohne Anmeldung: daran hängen der Healthcheck in compose.yml und die
# Erreichbarkeitsprüfung hinter Caddy.
@app.get("/health")
async def health():
    return {"status": "ok"}
