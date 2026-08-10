import asyncio
import logging
import os
import signal
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .auth import Permission, require
from . import audit as security_audit
from .auth.bootstrap import ensure_bootstrap_admin
from .config import settings
from . import db
from .db import close_db, init_db
from .mail import digest, intake
from .mail_seed import seed_mail_receiving
from .http_security import BodyLimitMiddleware, SecurityHeadersMiddleware, secure_response
from .network import is_admin_network, request_client_ip
from .paperless_client import paperless_client
from .routers import agent, audit, auth, cases, dashboard, documents, mail, sessions, sync, users
from .tag_seed import seed_tags


# Ohne das bleibt der Standard der Standardbibliothek stehen und alles unterhalb
# von WARNING verschwindet — also genau die Zeilen, die sagen, welche Mail an wen
# rausging oder eben nicht. uvicorn hängt seine Handler an eigene Logger mit
# propagate=False, deshalb doppelt sich hier nichts.
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-8s %(name)s: %(message)s",
)


_runtime_ready = False
_supervisor_tasks: list[asyncio.Task] = []


def _supervisor_done(task: asyncio.Task) -> None:
    if _runtime_ready and not task.cancelled():
        logging.getLogger(__name__).critical(
            "Kritischer Scheduler %s wurde unerwartet beendet.", task.get_name()
        )
        os.kill(os.getpid(), signal.SIGTERM)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _runtime_ready, _supervisor_tasks
    try:
        if production:
            await db.require_current_schema()
        else:
            await init_db()
        await ensure_bootstrap_admin()
        await seed_tags()
        await seed_mail_receiving()

        _supervisor_tasks = []
        if settings.deadline_digest_enabled:
            _supervisor_tasks.append(
                asyncio.create_task(digest.scheduler(), name="deadline-digest")
            )
        if settings.mail_intake_enabled:
            _supervisor_tasks.append(
                asyncio.create_task(intake.scheduler(), name="mail-intake")
            )
        for task in _supervisor_tasks:
            task.add_done_callback(_supervisor_done)
        _runtime_ready = True
        yield
    finally:
        _runtime_ready = False
        for task in _supervisor_tasks:
            task.cancel()
        if _supervisor_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*_supervisor_tasks, return_exceptions=True), timeout=8
                )
            except asyncio.TimeoutError:
                logging.getLogger(__name__).error("Scheduler-Shutdown hat das Zeitlimit überschritten.")
        _supervisor_tasks = []
        try:
            await asyncio.wait_for(
                asyncio.gather(close_db(), paperless_client.close(), return_exceptions=True),
                timeout=8,
            )
        except asyncio.TimeoutError:
            logging.getLogger(__name__).error("Ressourcen-Shutdown hat das Zeitlimit überschritten.")


production = settings.environment == "production"
_ADMIN_PATH_PREFIXES = ("/users", "/sync", "/audit")
_ADMIN_MAIL_PATHS = (
    "/mail/settings",
    "/mail/test",
    "/mail/deadline-digest",
    "/mail/pending-senders",
    "/mail/intake",
)
app = FastAPI(
    title="Paperless Agent Backend",
    lifespan=lifespan,
    docs_url=None if production else "/docs",
    redoc_url=None if production else "/redoc",
    openapi_url=None if production else "/openapi.json",
)
app.add_middleware(BodyLimitMiddleware, max_bytes=settings.max_request_bytes)


def _same_origin_request(request: Request) -> bool:
    site = request.headers.get("sec-fetch-site")
    if site == "same-origin":
        return True
    origin = request.headers.get("origin")
    if not origin:
        return False
    expected = urlsplit(settings.app_base_url)
    actual = urlsplit(origin)
    return (actual.scheme, actual.netloc) == (expected.scheme, expected.netloc)


def _audit_route(request: Request) -> str:
    route = getattr(request.scope.get("route"), "path", None)
    if route:
        return route
    path = request.url.path
    if path.startswith("/auth/invitation/"):
        return "/auth/invitation/{token}"
    first_segment = path.strip("/").split("/", 1)[0]
    return f"/{first_segment}/<unmatched>" if first_segment else "/"


@app.middleware("http")
async def request_limits_and_security_headers(request: Request, call_next):
    request_id, request_token, actor_token = security_audit.begin_request()
    if production and (
        request.url.path.startswith(_ADMIN_PATH_PREFIXES)
        or request.url.path.startswith(_ADMIN_MAIL_PATHS)
    ) and not is_admin_network(request_client_ip(request)):
        await security_audit.safe_record(
            "access.network_denied",
            "denied",
            reason_code="admin_network_required",
            metadata={"method": request.method, "route": _audit_route(request)},
        )
        response = secure_response(
            JSONResponse(status_code=403, content={"detail": "Administration ist nur über das VPN erreichbar."})
        )
        response.headers["X-Request-ID"] = request_id
        security_audit.end_request(request_token, actor_token)
        return response

    if production and request.method in {"POST", "PUT", "PATCH", "DELETE"} and not _same_origin_request(request):
        await security_audit.safe_record(
            "access.origin_denied",
            "denied",
            reason_code="same_origin_required",
            metadata={"method": request.method, "route": _audit_route(request)},
        )
        response = secure_response(
            JSONResponse(status_code=403, content={"detail": "Ungültiger Anfrageursprung."})
        )
        response.headers["X-Request-ID"] = request_id
        security_audit.end_request(request_token, actor_token)
        return response

    try:
        if request.url.path not in {"/live", "/ready", "/health"}:
            await security_audit.record(
                "http.request",
                "started",
                metadata={"method": request.method, "route": _audit_route(request)},
            )
        response = await call_next(request)
        route = _audit_route(request)
        if route not in {"/live", "/ready", "/health"}:
            actor = getattr(request.state, "audit_actor", (None, None))
            await security_audit.safe_record(
                "http.request",
                "success" if response.status_code < 400 else "denied",
                reason_code=None if response.status_code < 400 else f"http_{response.status_code}",
                metadata={
                    "method": request.method,
                    "route": route,
                    "status_code": response.status_code,
                },
                actor_type="user" if actor[0] else "anonymous",
                actor_id=actor[0],
                actor_role=actor[1],
            )
        response.headers["X-Request-ID"] = request_id
        return secure_response(response)
    except Exception:
        await security_audit.safe_record(
            "http.request",
            "failure",
            reason_code="unhandled_exception",
            metadata={"method": request.method, "route": _audit_route(request)},
        )
        raise
    finally:
        security_audit.end_request(request_token, actor_token)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    # Ohne das schickt der Browser das Session-Cookie bei einem Cross-Origin-Aufruf
    # nicht mit. Produktion und `make dev` laufen zwar same-origin über /api, der
    # direkte Zugriff auf :8001 aber nicht.
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(auth.router)
app.include_router(audit.router)
app.include_router(users.router)
# Rechte stehen hier an den einzelnen Routen: /mail/test und /mail/settings sind
# Verwaltung, /mail/drafts gehört jedem Bearbeiter, /mail/deadline-digest ist Betrieb.
app.include_router(mail.router)
app.include_router(
    documents.router, dependencies=[Depends(require(Permission.DOCUMENTS_READ))]
)
app.include_router(agent.router, dependencies=[Depends(require(Permission.AGENT_CHAT))])
app.include_router(sessions.router, dependencies=[Depends(require(Permission.AGENT_CHAT))])
app.include_router(sync.router, dependencies=[Depends(require(Permission.SYNC_RUN))])
app.include_router(
    dashboard.router, dependencies=[Depends(require(Permission.DOCUMENTS_READ))]
)
# Rechte stehen hier an den einzelnen Routen: Lesen ist documents:read, Notizen/
# Schliessen/Verknuepfen ist agent:write (siehe routers/cases.py).
app.include_router(cases.router)


# Bewusst ohne Anmeldung: Liveness prüft nur Prozess/Event-Loop.
@app.get("/live")
async def live():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    supervisors_ok = all(not task.done() for task in _supervisor_tasks)
    if not _runtime_ready or not supervisors_ok:
        return JSONResponse(status_code=503, content={"status": "not_ready"})
    dependencies_ok = await asyncio.gather(db.database_ready(), paperless_client.ready())
    if not all(dependencies_ok):
        return JSONResponse(status_code=503, content={"status": "not_ready"})
    return {"status": "ready", "schema_version": db.SCHEMA_VERSION}


@app.get("/health", include_in_schema=False)
async def health_compatibility():
    return await live()
