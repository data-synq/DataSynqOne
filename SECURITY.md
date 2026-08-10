# Security boundaries

## AI data boundary

All OpenAI traffic must pass through `server/app/ai_gateway.py`. The gateway applies the local
policy in `server/app/ai_privacy.py` recursively to messages, tool results, schemas and embedding
input. It normalizes Unicode, removes direct contact, address and bank identifiers, blocks common
credentials and neutralizes recognizable prompt-injection instructions. A residual secret scan is
fail-closed. Audit log entries contain only purpose, policy version, hashes and class counters.

Direct OpenAI SDK use outside the gateway is forbidden and covered by a static regression test.
Changing `POLICY_VERSION` causes document embeddings to be regenerated on the next sync.

Chat history is loaded from the application database. Browsers cannot supply model roles or old
messages. Tool input is schema-checked and bounded before dispatch. Model-driven writes are disabled;
all business mutations, draft persistence and outbound communication require a separate deterministic
user action.

## Public and administrative routes

The public application origin exposes the frontend, `/api/health`, authentication and the
authenticated application API. FastAPI documentation is disabled in production. Administrative
routes under `/api/users`, `/api/sync`, `/api/mail/settings`, `/api/mail/test`,
`/api/mail/deadline-digest`, `/api/mail/pending-senders`, `/api/mail/intake` and sender approvals must additionally be restricted to the VPN at the
reverse proxy. Paperless itself is VPN-only.

`TRUSTED_PROXY_CIDRS` must name only the dedicated Docker subnet from which Caddy reaches the
backend. The backend ignores `X-Forwarded-For` from every other peer. Do not start Uvicorn with
`--forwarded-allow-ips=*`. `ADMIN_CLIENT_CIDRS` is enforced by the backend for user management,
sync and administrative mail routes in addition to the reverse-proxy VPN guard.

## Infrastructure contract

The production host and the separate infrastructure repository must preserve these invariants:

- Caddy is the only container that can reach frontend and backend HTTP ports.
- Backend can reach Paperless, pgvector, OpenAI and the configured mail relay, but no unrelated service.
- Paperless can reach its PostgreSQL, Redis, Tika, Gotenberg and configured mailbox only.
- Database, Redis, Tika and Gotenberg networks are internal and are not shared with unrelated containers.
- Paperless and application administration are reachable only from the VPN.
- Caddy applies HSTS, TLS policy, request timeouts, body limits and volumetric rate limits before authentication.
- The backend image is not started with wildcard proxy trust.
- Egress destination controls are enforced by the host firewall or an egress proxy; Compose networks alone are insufficient.

`scripts/validate_prod_compose.py` validates the repository-owned portion. It cannot prove host
firewall rules, external network membership, DNS destination controls or the Caddy configuration.

## Audit and migrations

Security events are appended to `audit_events` with an internal request ID, actor snapshot,
allowlisted/redacted metadata and a SHA-256 chain to the previous event. PostgreSQL triggers reject
updates and deletes. Audit reads require `audit:read`, global object access and the VPN admin network;
the read itself is audited by the HTTP audit middleware. Raw prompts, OCR, passwords, tokens, mail
addresses, subjects and message bodies are forbidden audit metadata.

Schema migration 1 runs in a one-shot Compose service under a session advisory lock and one
transaction. Its source checksum is stored in `schema_migrations`. Editing an applied migration or
starting an older image against a newer database fails closed. The migration service alone receives
the owner and runtime DSNs. The backend authenticates as `datasynq_runtime`, cannot execute DDL or
mutate the audit table directly, and appends only through a narrowly granted security-definer
function.

Audit retention is an owner-level operational process: archive and verify the chain off-host before
deleting old partitions in a future migration. The application role intentionally has no audit
delete path.

## Mail and external input

The mail intake accepts `From` only from the leading RFC-style header block. A body or quoted
`From:` line is never identity. A visible tracking ID attaches mail automatically only when the
approved sender exactly matches the sender already bound to the case. Attachments without their own
verifiable sender remain pending; time-window and correspondent-name guesses are forbidden.

Executable, macro-enabled, active-HTML and archive extensions are quarantined. This repository
cannot inspect mail before Paperless downloads and parses it. Deployments requiring hostile public
mail intake need a mail gateway that verifies SPF/DKIM/DMARC and enforces MIME, magic-byte, archive,
attachment-count and decompression limits before Paperless.

Production startup always rejects automatic mail intake until a signed ingress manifest is
implemented. Mail receiving additionally requires `MAIL_INGRESS_PREVALIDATED=true`; set it only when
the mailbox can receive messages exclusively through that upstream security gate.

Only a size-limited response with `application/pdf` and a `%PDF-` signature is served inline. The
viewer iframe is sandboxed. Other original formats must be handled as downloads by an administrative
workflow.
