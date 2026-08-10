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
  rename documents and run bulk updates. Only for roles that carry the `agent:write` permission;
  a viewer is not even offered the writing tools.
- **Accounts and roles** — per-person sign-in with three roles (administrator, editor, viewer),
  invitations by email, and a user management screen. See [Users and roles](#users-and-roles).
- **Mail** — invitation and password-reset links, a daily deadline reminder, and replies drafted
  by the assistant that a human reviews before they go out. See [Mail](#mail).
- **Dashboard** — KPIs, a status board (open / in-progress / done / urgent / overdue), deadlines,
  recent correspondence and charts.
- **Charts in chat** — the agent can produce bar, line, pie and doughnut charts via `create_chart`,
  rendered in the frontend.
- **Chat history** — sessions are stored in Postgres, private to the person who created them,
  and can be reopened.
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

- **`env/backend.env`** — set `PAPERLESS_API_TOKEN`, `OPENAI_API_KEY` and the first
  administrator in `ADMIN_EMAIL`/`ADMIN_PASSWORD`. Without those two nobody can sign in;
  see [Users and roles](#users-and-roles).
- **`env/paperless.env`** — set the passwords, `PAPERLESS_SECRET_KEY` and `USERMAP_UID`/`USERMAP_GID`
  (your own `id -u` / `id -g`).
- **`env/postgres.env`** — set `POSTGRES_PASSWORD`; it must match `PAPERLESS_DBPASS`.
- **`env/vectordb.env`** — replace the database password and keep it in sync with `DATABASE_URL`.
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
make sync
```

The sync endpoints require the `sync:run` permission, so `make sync` signs in with
`ADMIN_EMAIL`/`ADMIN_PASSWORD` from `env/backend.env` first and reuses that session for both calls.
If the admin password has been changed since, pass the current one:

```bash
ADMIN_PASSWORD='…' make sync
```

The sync computes embeddings for new/changed documents (content-hash based), skips unchanged
ones and removes orphaned entries.

---

## Production containers

`compose.prod.yml` is an independent production definition. Do not merge it with `compose.yml` or
`compose.dev.yml`: Compose merges list fields such as ports, which could reintroduce development
exposure. The production file publishes no host ports and expects Caddy and the VPN-only Paperless
admin proxy to join existing external Docker networks.

All images are non-root, read-only, capability-free and resource-limited. Third-party images are
pinned by digest. `DATASYNQ_BACKEND_IMAGE` and `DATASYNQ_FRONTEND_IMAGE` must likewise be complete
immutable references such as `ghcr.io/data-synq/datasynqone-backend@sha256:...`; the production
validator rejects tags.

### Production inputs

Copy the `*.prod.env.example` files to a protected deployment location and replace the public
hostnames and account metadata. These files deliberately contain no passwords, API tokens or
database URLs. Set `BACKEND_ENV_FILE`, `PAPERLESS_ENV_FILE`, `POSTGRES_ENV_FILE` and
`VECTORDB_ENV_FILE` if they are not kept at the default paths.

Create a dedicated host group for runtime secret access and set its numeric GID in
`DATASYNQ_SECRETS_GID`. The secrets directory should be owned by `root:<secret-group>` with mode
`0750`; each secret file should be owned by `root:<secret-group>` with mode `0440`. Compose file
secrets are bind mounts and do not apply their own `uid`/`gid`/`mode`, so administrator-owned
`0600` source files are intentionally rejected by `make prod-validate`. The directory contains:

```text
paperless_db_password
paperless_secret_key
paperless_admin_password
vectordb_password
paperless_api_token
openai_api_key
database_url
runtime_database_url
admin_password
smtp_password
mail_imap_password
mfa_encryption_key
```

Optional features use empty secret files. `database_url` is the migration-owner DSN and its
password must match `vectordb_password`; `runtime_database_url` uses the separate
`datasynq_runtime` login and a different strong password. Only the one-shot migration service sees
both DSNs. The long-running backend sees the runtime DSN as `/run/secrets/database_url`. Paperless secrets are loaded by
`docker/paperless-load-secrets.sh`; PostgreSQL uses its native `POSTGRES_PASSWORD_FILE`, and the
backend reads its files directly through Pydantic Settings.
Generate `mfa_encryption_key` once with
`python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'` and
back it up separately; losing it locks administrators out of TOTP verification.

The persistent directories must already exist. Production never creates them as root. Ownership is:

| Path | Required owner UID |
|------|--------------------|
| `data/redis` | `999` |
| `data/postgres` | `999` |
| `data/vectordb` | `999` |
| `data/paperless/data`, `media`, `export`, `consume` | `PAPERLESS_UID`, default `1000` |

`make prod-paths` checks the complete existing trees without changing anything. Correct ownership
only during a planned maintenance window and after a verified backup.
Existing Paperless installations that already use another non-root owner can set `PAPERLESS_UID`
and `PAPERLESS_GID` for both `make prod-paths` and Compose instead of rewriting the complete media
tree. The chosen numeric identity still needs read/write access to all four Paperless paths.

### Network contract

Set `CADDY_NETWORK` to the external reverse-proxy network. Caddy reaches `one-frontend:80` and
`one-backend:8000`; it should expose only the frontend origin and route `/api/*` to the backend.
Set `ADMIN_NETWORK` to a separate external network reachable only through the VPN administration
path; Paperless is available there as `one-paperless:8000`.

Databases, Redis, Tika and Gotenberg are attached only to internal networks. Paperless has a
separate bridge for required IMAP egress. Strict destination-level egress filtering still belongs
in the host firewall or an egress proxy and cannot be expressed completely by Docker Compose.

### Validation and start

```bash
export DATASYNQ_BACKEND_IMAGE='ghcr.io/data-synq/datasynqone-backend@sha256:...'
export DATASYNQ_FRONTEND_IMAGE='ghcr.io/data-synq/datasynqone-frontend@sha256:...'
export DATASYNQ_SECRETS_DIR='/srv/datasynq/secrets'
export DATASYNQ_SECRETS_GID='991'
export CADDY_NETWORK='caddy'
export ADMIN_NETWORK='vpn-admin'

make prod-paths
make prod-validate
docker compose -f compose.prod.yml up -d
```

Before the first start, create both external networks and ensure their proxy containers are already
attached. A production deployment is not considered valid when `make prod-validate` fails.

The one-shot `migrate` service applies schema migration 1 under a PostgreSQL advisory lock. The migration is one
transaction and its source checksum is stored in `schema_migrations`; changed applied migrations or
a database newer than the image stop startup. It creates the restricted runtime login; the backend
has no owner credential and performs no DDL. `/live` checks only the process, while `/ready` also
requires completed startup, healthy supervisors, database/Paperless access and the exact schema checksum. The
production healthcheck uses `/ready`.

Create logical backups with `make backup` and validate artifacts with
`make restore-check BACKUP_DIR=/path/to/backup`. Follow the runbooks under `docs/runbooks/`; a
quarterly isolated restore drill is part of the operating contract.

CI runs tests, lock freshness, dependency audits, filesystem/image scans and production builds.
Published images contain SBOM and provenance and are deployed only by immutable digest. This
repository deliberately has no credential that can write to `DataSynqInfra`; production digest
updates must be reviewed in a separate infrastructure pull request.

### Dependency locks

`server/requirements.in` and `server/requirements-dev.in` are the human-maintained Python inputs.
The generated `requirements*.txt` files pin every transitive package and hash. Run `make lock`
after changing an input and commit input and lock together. Docker installs with
`--require-hashes`; the frontend uses `npm ci` and `package-lock.json`.

---

## API overview

`GET /live`, `GET /ready`, compatibility route `GET /health`, login and invitation
lookup/redemption are public. Every other endpoint requires a
signed-in session; the ones marked below need a specific permission on top of that.

| Method & path                      | Description                                          |
|------------------------------------|------------------------------------------------------|
| `GET  /live`                       | Process liveness                                     |
| `GET  /ready`                      | DB/schema/supervisor readiness                       |
| `GET  /health`                     | Compatibility alias for liveness                     |
| `POST /auth/login`                 | Sign in, sets the session cookie                     |
| `POST /auth/logout`                | Sign out                                             |
| `GET  /auth/me`                    | Current account, role and resolved permissions       |
| `POST /auth/password`              | Change your own password                             |
| `GET  /users/`                     | List accounts — `users:manage`                       |
| `POST /users/`                     | Create an account — `users:manage`                   |
| `PATCH /users/{id}`                | Name, role, active flag — `users:manage`             |
| `POST /users/{id}/invitation`      | Send a new invitation or reset link — `users:manage` |
| `DELETE /users/{id}`               | Delete an account — `users:manage`                   |
| `GET  /auth/invitation/{token}`    | Check an invitation link (public)                    |
| `POST /auth/invitation/{token}`    | Redeem it: set a password and sign in (public)       |
| `GET  /mail/settings`              | Current mail configuration, without the password — `users:manage` |
| `POST /mail/test`                  | Test mail to your own address — `users:manage`       |
| `POST /mail/deadline-digest`       | Send the deadline reminder now — `sync:run`          |
| `GET  /mail/drafts/{id}`           | One of your own drafts — `agent:write`               |
| `POST /mail/drafts/{id}/send`      | Send a draft after review — `agent:write`            |
| `GET  /audit/events`               | Append-only security audit — `audit:read`, VPN only  |
| `GET  /audit/verify`               | Verify the complete audit hash chain                 |
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
| `POST /sync/documents`             | Sync embeddings — `sync:run`                         |
| `GET  /sync/status`                | Sync status — `sync:run`                             |

Full interactive documentation at `http://localhost:8001/docs`.

---

## Users and roles

Accounts live in the app's own database (the `users` table in the vector database), independent of
the Paperless user list. Signing in returns an HttpOnly session cookie; the session itself is stored
server-side, so deactivating someone or changing their role takes effect on their very next request
instead of whenever a token happens to expire.

### The three roles

| Permission | Administrator | Editor | Viewer |
|---|:--:|:--:|:--:|
| `documents:read` — dashboard, search, document view | ✓ | ✓ | ✓ |
| `agent:chat` — talk to the assistant | ✓ | ✓ | ✓ |
| `agent:write` — let the assistant change Paperless | ✓ | ✓ | – |
| `sync:run` — trigger the embedding sync | ✓ | – | – |
| `users:manage` — manage accounts | ✓ | – | – |
| `mail:manage` — approve senders and process mail | ✓ | ✓ | – |

A viewer keeps the assistant — searching, summarizing, amount analysis and charts all work. What
they lose are the writing tools: those are removed from the tool list before it ever reaches the
model, so the assistant says plainly that it cannot make the change instead of claiming a success
that never happened. A second check in `call_tool` refuses the call even if the model invents the
name. The matrix itself lives in `server/app/auth/permissions.py`.

Chat sessions belong to the person who started them. Nobody else sees them — administrators
included — and a request carrying someone else's session id gets a 404, not a 403.

### Inviting people

An administrator creates an account with a name, an email address and a role — no password. The
person receives an invitation link, sets their own password and is signed in straight away. The
link is valid once and expires after `INVITATION_TTL_HOURS` (72 by default).

*Passwort zurücksetzen* sends the same kind of link. The old password keeps working until the new
one is set, so an accidental click does not lock out someone who is in the middle of their work.

Without a configured mail server nothing is lost: the invitation link is returned to the
administrator in the user management screen, to be passed on by hand.

### The first sign-in

Set `ADMIN_EMAIL` and `ADMIN_PASSWORD` in `env/backend.env` **before the first start**. While the
`users` table is empty, the backend creates exactly that one administrator and flags the password
as one that must be changed. Without both values no account is created and nobody can sign in —
there is deliberately no built-in default password.

Every further account is created by an administrator under *Benutzer verwalten* in the account menu
and receives an invitation link by mail.

The required password change is enforced by the backend, not only by the browser. Administrators
must then enroll a TOTP authenticator and store ten one-time recovery codes before any application
permission is granted. Later administrator sign-ins remain restricted until either a current TOTP
code or one unused recovery code has been verified. Reusing a TOTP time step or recovery code is
rejected, and ten failed MFA attempts revoke the pending session.

Sessions have both a rolling idle expiry and an immutable absolute expiry. Password and MFA
transitions rotate the token, while the account page lists active devices and can revoke one or all
other sessions. Production cookies must use the `__Host-` prefix.

### Object access

Every account has an explicit object access mode: either `all` or `restricted` with a non-empty set
of canonical `OBJ-*` codes. Missing scope rows never imply global access. Restricted users only see
documents carrying exactly one allowed object tag; objectless or ambiguously tagged documents are
hidden. The same policy covers direct files and thumbnails, dashboard aggregates, cases, agent
tools, semantic search, drafts and per-user deadline digests.

Changing a user's scope revokes their sessions and removes existing chats and drafts because those
artifacts may contain data from the previous scope. Restricted users cannot modify Paperless tags;
case links are retained in the application database without changing Paperless tags. Global user
management and sync operations require both the administrator permission and access to all objects.
The last active global administrator cannot be demoted, deleted or restricted.

Guard rails worth knowing: the last active administrator cannot be demoted, deactivated or deleted,
and nobody can deactivate or delete their own account. Password attempts are limited in fixed
15-minute windows per source and per source/account pair without globally locking the target
account. Ten failed MFA attempts after a correct administrator password revoke all pending sessions
and lock MFA verification for fifteen minutes.

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
| Mailpit (catches every mail) | http://localhost:8025 | – |

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
| `make test` | Fast backend, frontend unit and component tests |
| `make test-e2e` | Production frontend build and browser smoke test |
| `make check` | Full local gate: all tests, browser smoke test and backend compile check |
| `make lock` | Regenerate hashed Python dependency lock files |
| `make prod-paths` | Check non-root ownership of production bind mounts |
| `make prod-validate` | Validate the rendered production Compose security invariants |
| `make infra` / `make infra-down` | Only redis, postgres, vectordb, paperless |
| `make up` / `make down` / `make build` / `make logs` / `make ps` | Full stack from `compose.yml` |
| `make sync` | Index documents into the vector database |
| `make clean` | Remove `server/.venv`, `src/node_modules`, `src/dist` |

`make dev` and `make up` cannot run at the same time — both claim the same container names.

Backend configuration is via environment variables (see `server/app/config.py`).
Design guidelines: see [`src/DESIGN.md`](src/DESIGN.md).

Tests do not use the local Paperless instance, OpenAI, SMTP or the application database. The API
smoke tests replace the FastAPI lifespan dependencies with local fakes; the browser smoke test
intercepts the unauthenticated session lookup. `make test-e2e` installs the matching Playwright
Chromium revision automatically if it is not already present in the local cache.

---

## Mail

Sending is entirely configured through environment variables (see the table below). It is used in
three places:

- **Invitations and password resets** — see [Users and roles](#users-and-roles).
- **A daily deadline reminder** to every active administrator and editor, built from the same
  `due:` tags the dashboard shows. It goes out once a day from `DEADLINE_DIGEST_HOUR`, covers the
  next `DEADLINE_DIGEST_DAYS_AHEAD` days, and is skipped entirely on a day with no open deadlines.
  A note in the database prevents a restart from sending it twice.
- **Replies formulated by the assistant** remain chat text only. The model cannot persist drafts,
  mutate business data or send mail. Existing/manual drafts require a locally entered recipient and
  a separate authenticated click before sending.

**Nothing here can break a request.** An empty `SMTP_HOST` turns sending off, and a mail server
that is down is logged rather than raised: an account is created even when its invitation could
not be delivered, and the response says so with `mail_sent: false`.

To check the settings, use *Testmail an mich* in the user management screen (`POST /mail/test`) —
it sends to your own address and reports back what the mail server said.

In development, `make dev` starts **Mailpit**, which accepts every mail and delivers none. All of
it lands at **http://localhost:8025** instead of a real inbox.

### Receiving mail

Paperless-ngx fetches mail itself; this backend only seeds the account and the rule on startup
(`server/app/mail_seed.py`), the same best-effort, idempotent pattern as the tag taxonomy in
`tag_seed.py`. Set `MAIL_IMAP_HOST` and `MAIL_IMAP_USERNAME`/`MAIL_IMAP_PASSWORD` and the next
backend start creates both, unless they already exist.

The rule uses `consumption_scope = 3`, Paperless's *"process full mail as `.eml` + process
attachments as separate documents"* — **not** ".eml plus a PDF" as a document type of its own.
Every `.eml` is always rendered to PDF by Paperless (browsers cannot display `.eml` natively);
`consumption_scope` only decides whether attachments additionally become their own documents.
Producing that PDF requires the **Gotenberg** and **Tika** containers, which `compose.yml` starts
and depends on — without them, every incoming mail fails to process. `pdf_layout` only affects how
the PDF is laid out (HTML first, then text, by default), not whether one is created.

The correspondent is taken from the sender's name (falling back to their address), the title from
the subject, and every incoming document gets the tags in `MAIL_RULE_TAGS`. Processed mail is
marked read rather than deleted or moved, so a misconfigured rule never loses a message — it can
be reprocessed after fixing the rule in Paperless's own UI.

Combined with the sending side above, both halves of a conversation end up as searchable
documents in the same file.

---

## Configuration (backend)

`ENVIRONMENT=production` enables fail-closed validation. The backend then refuses to start with
missing Paperless/OpenAI credentials, insecure public URLs or cookies, wildcard/localhost CORS or
missing trusted-proxy networks,
weak database credentials, incomplete mail accounts or clear-text external mail transports. The
development defaults remain available only with `ENVIRONMENT=development`.

Sensitive settings can be mounted as files instead of container environment variables. By default
the backend reads lower-case field names from `/run/secrets`, for example
`/run/secrets/openai_api_key`, `/run/secrets/paperless_api_token`,
`/run/secrets/database_url`, `/run/secrets/admin_password`,
`/run/secrets/smtp_password` and `/run/secrets/mail_imap_password`. Set
`DATASYNQ_SECRETS_DIR` to use another directory. An explicit environment variable takes precedence
over the corresponding secret file when it is non-empty; empty environment values are ignored so
that the checked-in templates do not shadow mounted secrets. Remove a secret mount to disable it.
The production Compose wiring is defined separately from this application configuration.

| Variable             | Default                                           | Description                          |
|----------------------|---------------------------------------------------|--------------------------------------|
| `ENVIRONMENT`        | –                                                 | Required: `development` \| `production` \| `test` |
| `PAPERLESS_BASE_URL` | `http://paperless:8000`                           | Base URL of the Paperless API        |
| `PAPERLESS_API_TOKEN`| –                                                 | API token from Paperless             |
| `OPENAI_API_KEY`     | –                                                 | OpenAI API key                       |
| `OPENAI_MODEL`       | `gpt-4o-mini`                                      | Chat model                           |
| `EMBEDDING_MODEL`    | `text-embedding-3-small`                          | Embedding model (1536 dimensions)    |
| `DATABASE_URL`       | `postgresql://brain:brain@vectordb:5432/brain`    | Vector database                      |
| `CORS_ORIGINS`       | `["http://localhost:8080"]`                        | Allowed frontend origins             |
| `TRUSTED_PROXY_CIDRS` | `[]`                                               | Dedicated Caddy subnet; required in production |
| `ADMIN_CLIENT_CIDRS` | `[]`                                                | VPN client networks allowed to use administrative APIs |
| `MAX_REQUEST_BYTES`  | `1048576`                                         | Maximum declared API request body    |
| `ADMIN_EMAIL`        | –                                                 | Bootstrap administrator, first start only |
| `ADMIN_PASSWORD`     | –                                                 | Its password; change after first login |
| `SESSION_COOKIE_NAME` | `dsq_session`                                    | Session cookie name; production requires `__Host-` |
| `SESSION_COOKIE_SECURE` | `true`                                         | Set to `false` only for plain-HTTP dev |
| `SESSION_TTL_HOURS`  | `12`                                              | Rolling idle session lifetime |
| `SESSION_ABSOLUTE_TTL_HOURS` | `24`                                     | Maximum session lifetime, never extended |
| `MFA_ENCRYPTION_KEY` | –                                                 | Fernet key for encrypted TOTP secrets; required in production |
| `SMTP_HOST`          | –                                                 | Mail server; empty turns sending off  |
| `SMTP_PORT`          | `587`                                             | 587 for STARTTLS, 465 for implicit TLS |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | –                                    | Leave empty for an unauthenticated relay |
| `SMTP_SECURITY`      | `starttls`                                        | `starttls` \| `tls` \| `none`         |
| `SMTP_FROM_EMAIL`    | –                                                 | Sender address; required for sending  |
| `SMTP_FROM_NAME`     | `DataSynq One`                                    | Sender display name                   |
| `SMTP_REPLY_TO`      | –                                                 | Optional Reply-To                     |
| `SMTP_TIMEOUT_SECONDS` | `15`                                            | Per delivery attempt                  |
| `ALLOW_INSECURE_MAIL_TRANSPORT` | `false`                                 | Explicit production exception for a trusted local relay |
| `APP_BASE_URL`       | `http://localhost:5173`                           | Public frontend URL; invitation links are built from it |
| `INVITATION_TTL_HOURS` | `72`                                            | Validity of an invitation or reset link |
| `DEADLINE_DIGEST_ENABLED` | `true`                                       | The daily deadline reminder           |
| `DEADLINE_DIGEST_HOUR` | `7`                                             | Local hour it goes out from           |
| `DEADLINE_DIGEST_DAYS_AHEAD` | `14`                                      | How far ahead deadlines are included  |
| `DEADLINE_DIGEST_RECIPIENTS` | `[]`                                      | Empty means every active admin and editor |
| `MAIL_IMAP_HOST`     | –                                                 | Incoming mail; empty turns the seed off |
| `MAIL_IMAP_PORT`     | `993`                                             | 993 for SSL, 143 for STARTTLS         |
| `MAIL_IMAP_SECURITY` | `ssl`                                             | `ssl` \| `starttls` \| `none`         |
| `MAIL_IMAP_USERNAME` / `MAIL_IMAP_PASSWORD` | –                          | The mailbox Paperless fetches from    |
| `MAIL_IMAP_FOLDER`   | `INBOX`                                           |                                        |
| `MAIL_RULE_TAGS`     | `["correspondence"]`                              | Applied to every incoming document    |
| `MAIL_INTAKE_ENABLED` | `true`                                            | Process approved correspondence; must be `false` in production until signed ingress manifests exist |
| `MAIL_INGRESS_PREVALIDATED` | `false`                                    | Attests authenticated, size/type-limited upstream mail gateway; required for production receiving |
| `MAIL_INTAKE_POLL_SECONDS` | `300`                                       | Intake polling interval               |
| `MAIL_INTAKE_MAX_CHARS` | `8000`                                         | Maximum text sent to the intake model |
| `MAIL_WHITELIST_TRUST_DAYS` | `21`                                      | Lifetime of a sender approval         |

OpenAI never receives application payloads directly. `server/app/ai_gateway.py` applies local
classification, redaction and a residual secret scan to chat, OCR, mail, tool results and embedding
input. See [`SECURITY.md`](SECURITY.md) for the AI, reverse-proxy, network and mail-ingress contracts.

---

## License

No license is currently declared for this repository. Please clarify with the maintainers before
reusing the code.
