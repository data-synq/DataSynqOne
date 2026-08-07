# DataSynq One

DataSynq One is a self-hostable AI assistant with a dashboard for **property management**.
It builds on [Paperless-ngx](https://docs.paperless-ngx.com/) as the document store and adds a
conversational agent, semantic search and an overview dashboard — so invoices, contracts,
maintenance requests and correspondence become quick to find, analyze and act on.

> All AI features run through the OpenAI API. Your documents and metadata stay in your own
> Paperless / Postgres instance.
>
> The assistant currently answers in **German** (the system prompt is tuned for a German
> property-management workflow).

---

## Features

- **AI chat for property management** — an agent (OpenAI, function calling) that finds documents,
  summarizes cases and drafts replies. It can call multiple tools in sequence or in parallel and
  streams its answers over Server-Sent Events (SSE).
- **Full-text & semantic search** — classic Paperless search plus semantic search over vector
  embeddings (pgvector). When there are few hits, queries are automatically expanded with
  synonyms and spelling/compound variants.
- **Amount analysis** — extract monetary amounts from a single document (`extract_amounts`) or
  search across documents by amount (`search_documents_by_amount`); calculations run through a
  dedicated calculator tool instead of the model doing arithmetic itself.
- **Document management via chat** — create/assign/delete tags, correspondents and document types,
  rename documents and run bulk updates.
- **Dashboard** — KPIs, a status board (open / in-progress / done / urgent / overdue), deadlines,
  recent correspondence and charts.
- **Charts in chat** — the agent can produce bar, line, pie and doughnut charts via `create_chart`,
  rendered in the frontend.
- **Chat history** — sessions are stored in Postgres and can be reopened.
- **Automatic tag taxonomy** — on startup a set of default tags (status and category tags with
  colors) is seeded into Paperless.

---

## Architecture

```
┌────────────┐      ┌────────────┐      ┌──────────────┐
│  frontend  │ ───▶ │  backend   │ ───▶ │  paperless   │
│ Vue 3 / TS │      │  FastAPI   │      │    -ngx      │
│  (nginx)   │      │  + Agent   │      └──────┬───────┘
└────────────┘      └─────┬──────┘             │
     :8080               :8001          ┌──────┴───────┐
                          │             │  redis  │ postgres │
                    ┌─────┴──────┐      └──────────────┘
                    │  vectordb  │
                    │  pgvector  │
                    └────────────┘
                    │ OpenAI API │  (chat + embeddings)
```

| Service     | Technology                          | Responsibility                                       | Port |
|-------------|-------------------------------------|------------------------------------------------------|------|
| `frontend`  | Vue 3 + TypeScript + Vite (nginx)   | Dashboard & chat UI                                  | 8080 |
| `backend`   | FastAPI, OpenAI SDK                  | Agent, tools, sync, dashboard API                    | 8001 |
| `paperless` | Paperless-ngx                       | Document management (source of truth)                | 80   |
| `postgres`  | PostgreSQL 16                       | Paperless database                                   | –    |
| `vectordb`  | pgvector (PostgreSQL 16)            | Embeddings, semantic search, chat history            | –    |
| `redis`     | Redis                               | Task queue for Paperless                             | –    |

### Backend structure (`server/app`)

- `main.py` — FastAPI app, router registration, lifespan (DB init, tag seed).
- `agent/` — agent runner (`runner.py`), tool definitions (`tools.py`), query expansion,
  amount extraction, prompt suggestions.
- `routers/` — `documents`, `agent` (SSE chat), `sessions`, `sync`, `dashboard`.
- `vectorstore.py` / `db.py` — embeddings and pgvector access.
- `paperless_client.py` — HTTP client for the Paperless API.
- `tag_seed.py` — default tag taxonomy.

---

## Requirements

- [Docker](https://docs.docker.com/get-docker/) & Docker Compose (or Podman)
- An **OpenAI API key**
- Node.js 22+ and Python 3.12+ only for local development without containers

---

## Quick start (Docker Compose)

### 1. Clone the repository

```bash
git clone https://github.com/data-synq/DataSynqOne.git
cd DataSynqOne
```

### 2. Create the environment files

The env files in `env/` hold secrets and are not checked in. Create them from the templates:

```bash
make env
```

That copies every `env/*.env.example` to `env/*.env`. Then edit them:

- **`env/backend.env`** — set `PAPERLESS_API_TOKEN` and `OPENAI_API_KEY`.
- **`env/paperless.env`** — set the passwords, `PAPERLESS_SECRET_KEY` and `USERMAP_UID`/`USERMAP_GID`
  (your own `id -u` / `id -g`).
- **`env/postgres.env`** — set `POSTGRES_PASSWORD`; it must match `PAPERLESS_DBPASS`.
- **`env/vectordb.env`** — defaults are fine.
- **`env/backend.dev.env`** — host overrides for `make dev`; defaults are fine.

> Create the `PAPERLESS_API_TOKEN` in Paperless under *Settings → API Token*. It only exists
> after the first start, so leave it empty for now and fill it in afterwards.

### 3. Frontend configuration (optional)

The frontend reads `VITE_BACKEND_URL` at build time (default: `http://localhost:8001`).
For different deployments, set it in `src/.env` (see `src/.env.example`). In dev mode this is
already handled by `src/.env.development` — see [Development](#development).

### 4. Start

```bash
make up            # or: docker compose up -d --build
```

Then available at:

- **Frontend / dashboard:** http://localhost:8080
- **Backend API (FastAPI docs):** http://localhost:8001/docs
- **Paperless-ngx:** http://localhost

### 5. Index documents

For semantic search to work, the Paperless documents must be synced into the vector database
once:

```bash
make sync          # or: curl -X POST http://localhost:8001/sync/documents
```

Check the status:

```bash
curl http://localhost:8001/sync/status
```

The sync computes embeddings for new/changed documents (content-hash based), skips unchanged
ones and removes orphaned entries.

---

## API overview

| Method & path                      | Description                                          |
|------------------------------------|------------------------------------------------------|
| `GET  /health`                     | Health check                                         |
| `POST /agent/chat`                 | Chat with the agent (Server-Sent Events)             |
| `GET  /sessions`                   | List chat sessions                                   |
| `GET  /sessions/{id}`              | History of a session                                 |
| `DELETE /sessions/{id}`            | Delete a session                                     |
| `GET  /documents`                  | List documents from Paperless                        |
| `GET  /documents/{id}`             | Single document                                      |
| `GET  /documents/{id}/detail`      | Prepared detail view                                 |
| `GET  /documents/{id}/file`        | Original file                                         |
| `GET  /documents/meta/*`           | Correspondents / document types / tags               |
| `GET  /dashboard/overview`         | KPIs, status board, deadlines, charts                |
| `POST /sync/documents`             | Sync embeddings                                      |
| `GET  /sync/status`                | Sync status                                          |

Full interactive documentation at `http://localhost:8001/docs`.

---

## Agent tools

The agent has access to tools including:

- **Search:** `search_documents`, `semantic_search_documents`, `search_documents_by_amount`,
  `filter_documents_by_tag`, `filter_documents_by_date_range`, `list_recent_documents`,
  `list_untagged_documents`, `get_document`
- **Metadata:** `list_tags`, `list_correspondents`, `list_document_types`,
  `create_tag` / `delete_tag`, `create_correspondent` / `delete_correspondent`,
  `create_document_type` / `delete_document_type`
- **Editing:** `assign_tags_to_document`, `set_document_correspondent`,
  `set_document_document_type`, `rename_document`, `bulk_update_documents`
- **Analysis:** `extract_amounts`, `calculator`, `create_chart`

---

## Development

```bash
make dev
```

That is the whole setup. It creates any missing `env/*.env` from the templates, installs
`server/.venv` and `src/node_modules` if they are stale, starts redis / postgres / vectordb /
paperless as containers, and then runs **backend and frontend natively with hot reload**:

| | URL | Reload |
|---|---|---|
| Frontend (Vite) | http://localhost:5173 | HMR on every change under `src/src` |
| Backend (uvicorn) | http://localhost:8001/docs | restarts on every change under `server/app` |
| Paperless-ngx | http://localhost | – |
| vectordb (pgvector) | `localhost:5433` | – |

`Ctrl-C` stops backend and frontend; the containers keep running until `make dev-down`.

In dev the frontend talks to the backend through a Vite proxy on `/api` that strips the prefix —
the same shape the reverse proxy provides in production, so dev is same-origin and needs no CORS.
`src/.env.development` sets `VITE_BACKEND_URL=/api` for that; it is only loaded in dev mode, never
by `npm run build`.

`env/backend.dev.env` holds the host overrides applied on top of `env/backend.env` (the Compose
service names `vectordb` and `paperless` do not resolve from the host). Secrets belong in
`env/backend.env` only.

### Make targets

| Target | Description |
|--------|-------------|
| `make dev` | Everything in dev mode |
| `make dev-backend` / `make dev-frontend` | A single process, for separate terminals |
| `make dev-down` | Stop the dev containers |
| `make install` | Reinstall `server/.venv` and `src/node_modules` |
| `make env` | Create missing `env/*.env` from `env/*.env.example` |
| `make infra` / `make infra-down` | Only redis, postgres, vectordb, paperless |
| `make up` / `make down` / `make build` / `make logs` / `make ps` | Full stack from `compose.yml` |
| `make sync` | Index documents into the vector database |
| `make clean` | Remove `server/.venv`, `src/node_modules`, `src/dist` |

`make dev` and `make up` cannot run at the same time — both claim the same container names.

Backend configuration is via environment variables (see `server/app/config.py`).
Design guidelines: see [`src/DESIGN.md`](src/DESIGN.md).

---

## Configuration (backend)

| Variable             | Default                                           | Description                          |
|----------------------|---------------------------------------------------|--------------------------------------|
| `PAPERLESS_BASE_URL` | `http://paperless:8000`                           | Base URL of the Paperless API        |
| `PAPERLESS_API_TOKEN`| –                                                 | API token from Paperless             |
| `OPENAI_API_KEY`     | –                                                 | OpenAI API key                       |
| `OPENAI_MODEL`       | `gpt-4o-mini`                                      | Chat model                           |
| `EMBEDDING_MODEL`    | `text-embedding-3-small`                          | Embedding model (1536 dimensions)    |
| `DATABASE_URL`       | `postgresql://brain:brain@vectordb:5432/brain`    | Vector database                      |
| `CORS_ORIGINS`       | `["http://localhost:8080"]`                        | Allowed frontend origins             |

---

## License

No license is currently declared for this repository. Please clarify with the maintainers before
reusing the code.
