#!/usr/bin/env bash
#
# Development environment: infrastructure in Docker, backend and frontend as
# native host processes with hot reload. Driven by the Makefile.
#
#   scripts/dev.sh            infra + backend + frontend (Ctrl-C stops both)
#   scripts/dev.sh backend    infra + uvicorn --reload only, in the foreground
#   scripts/dev.sh frontend   vite only, in the foreground
#   scripts/dev.sh env        materialize env/*.env from the .example files
#   scripts/dev.sh install    (re)install backend venv and frontend node_modules
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BACKEND_PORT=8001
FRONTEND_PORT=5173
VENV="$ROOT/server/.venv"
DEPS_STAMP="$VENV/.deps-stamp"
NPM_STAMP="$ROOT/src/node_modules/.deps-stamp"
COMPOSE=(docker compose -f compose.yml -f compose.dev.yml)
ENV_FILES=(backend backend.dev paperless postgres vectordb)
# These templates ship placeholders (tokens, passwords); a freshly created one
# has to be edited before the stack is usable. The rest have working defaults.
ENV_NEEDS_EDIT=(backend paperless postgres)

if [ -t 1 ]; then
	C_RESET=$'\033[0m'; C_DIM=$'\033[2m'; C_BOLD=$'\033[1m'
	C_BACKEND=$'\033[36m'; C_FRONTEND=$'\033[35m'; C_WARN=$'\033[33m'
else
	C_RESET=''; C_DIM=''; C_BOLD=''; C_BACKEND=''; C_FRONTEND=''; C_WARN=''
fi

log()  { printf '%s==>%s %s\n' "$C_BOLD" "$C_RESET" "$*"; }
warn() { printf '%s==> %s%s\n' "$C_WARN" "$*" "$C_RESET" >&2; }
die()  { printf '%serror:%s %s\n' "$C_WARN" "$C_RESET" "$*" >&2; exit 1; }

# --- environment ------------------------------------------------------------

# Copy any missing env/*.env from its template. Returns 1 if one of the files
# that carry placeholders was created — those need editing before anything runs.
ensure_env_files() {
	local created=() needs_edit=() name
	for name in "${ENV_FILES[@]}"; do
		if [ ! -f "env/$name.env" ]; then
			[ -f "env/$name.env.example" ] || die "env/$name.env.example is missing"
			cp "env/$name.env.example" "env/$name.env"
			created+=("env/$name.env")
			if [[ " ${ENV_NEEDS_EDIT[*]} " == *" $name "* ]]; then
				needs_edit+=("env/$name.env")
			fi
		fi
	done
	[ ${#created[@]} -eq 0 ] && return 0
	log "created from templates: ${created[*]}"
	[ ${#needs_edit[@]} -eq 0 ] && return 0

	warn "fill in the placeholders in ${needs_edit[*]} (tokens, passwords), then run make dev again"
	return 1
}

# Read an env file the way Compose does: ignore comments, split on the first
# `=`, strip one layer of surrounding quotes. Plain `source` would mangle
# CORS_ORIGINS=["http://…"] by removing the inner quotes.
load_env_file() {
	local file=$1 line key value
	[ -f "$file" ] || return 0
	while IFS= read -r line || [ -n "$line" ]; do
		line=${line#"${line%%[![:space:]]*}"}
		[[ -z $line || $line == \#* || $line != *=* ]] && continue
		key=${line%%=*}
		key=${key#export }
		key=${key%"${key##*[![:space:]]}"}
		value=${line#*=}
		if [ ${#value} -ge 2 ] && [[ ( ${value:0:1} == '"' && ${value: -1} == '"' ) || ( ${value:0:1} == "'" && ${value: -1} == "'" ) ]]; then
			value=${value:1:-1}
		fi
		export "$key=$value"
	done <"$file"
}

# backend.dev.env last: it overrides the Compose service names in backend.env
# with the ports those services publish to the host.
load_backend_env() {
	load_env_file env/backend.env
	load_env_file env/backend.dev.env
}

# --- dependencies -----------------------------------------------------------

ensure_backend_deps() {
	if [ ! -x "$VENV/bin/python" ]; then
		log "creating virtualenv in server/.venv"
		python3 -m venv "$VENV"
	fi
	if [ ! -f "$DEPS_STAMP" ] || [ server/requirements.txt -nt "$DEPS_STAMP" ]; then
		log "installing backend dependencies"
		"$VENV/bin/pip" install --quiet --upgrade pip
		"$VENV/bin/pip" install --quiet -r server/requirements.txt
		touch "$DEPS_STAMP"
	fi
}

ensure_frontend_deps() {
	# Own stamp file rather than node_modules/.package-lock.json: npm leaves that
	# one untouched on a no-op install, which would re-run npm on every start.
	if [ ! -d src/node_modules ] || [ ! -f "$NPM_STAMP" ] || [ src/package-lock.json -nt "$NPM_STAMP" ]; then
		log "installing frontend dependencies"
		(cd src && npm install)
		touch "$NPM_STAMP"
	fi
}

# --- infrastructure ---------------------------------------------------------

start_infra() {
	command -v docker >/dev/null || die "docker is not installed"
	log "starting redis, postgres, vectordb, paperless"
	# vectordb first and gated on its healthcheck — the backend opens a pool at
	# startup. Paperless is only started, never waited for: its cold start takes
	# ~2 min (start_period: 240s) and tag_seed.py tolerates it being absent.
	"${COMPOSE[@]}" up -d --wait --wait-timeout 120 vectordb
	"${COMPOSE[@]}" up -d paperless
}

# --- processes --------------------------------------------------------------

run_backend_fg() {
	cd "$ROOT/server"
	exec "$VENV/bin/uvicorn" app.main:app --host 127.0.0.1 --port "$BACKEND_PORT" --reload
}

run_frontend_fg() {
	cd "$ROOT/src"
	# The vite binary rather than `npm run dev`: exec'ing it directly means a
	# SIGTERM reaches vite itself instead of stopping at the npm wrapper.
	exec node_modules/.bin/vite
}

pids=()

# Exit 0 on Ctrl-C so make does not report a failure for a deliberate stop; a
# crashing process still propagates its own status through the EXIT trap.
cleanup() {
	local code=${1:-0} pid
	trap - EXIT INT TERM
	for pid in "${pids[@]:-}"; do
		kill "$pid" 2>/dev/null || true
	done
	wait 2>/dev/null || true
	printf '\n'
	log "stopped. containers keep running — 'make dev-down' shuts them down."
	exit "$code"
}

# Start in the background with every output line prefixed, so the two logs stay
# readable side by side. Process substitution keeps $! the real process id, so
# uvicorn's reloader gets the SIGTERM directly and can stop its worker.
start_prefixed() {
	local color=$1 label=$2
	shift 2
	"$@" > >(sed -u "s/^/${color}[${label}]${C_RESET} /") 2>&1 &
	pids+=($!)
}

run_all() {
	trap 'cleanup 0' INT TERM
	trap 'cleanup $?' EXIT
	start_prefixed "$C_BACKEND" backend bash "$0" _backend_exec
	start_prefixed "$C_FRONTEND" frontend bash "$0" _frontend_exec

	printf '\n'
	log "frontend  ${C_BOLD}http://localhost:$FRONTEND_PORT${C_RESET}"
	log "backend   ${C_BOLD}http://localhost:$BACKEND_PORT/docs${C_RESET} ${C_DIM}(proxied at /api)${C_RESET}"
	log "paperless ${C_BOLD}http://localhost${C_RESET} ${C_DIM}(may need a minute on a cold start)${C_RESET}"
	printf '%s    Ctrl-C stops backend and frontend.%s\n\n' "$C_DIM" "$C_RESET"

	# Returns as soon as either process exits; the trap stops the other one.
	wait -n
}

# --- entry point ------------------------------------------------------------

case "${1:-all}" in
env)
	ensure_env_files || exit 1
	log "env files are in place"
	;;
install)
	rm -f "$DEPS_STAMP"
	ensure_backend_deps
	(cd src && npm install)
	;;
backend)
	ensure_env_files || exit 1
	ensure_backend_deps
	start_infra
	load_backend_env
	run_backend_fg
	;;
frontend)
	ensure_frontend_deps
	run_frontend_fg
	;;
all)
	ensure_env_files || exit 1
	ensure_backend_deps
	ensure_frontend_deps
	start_infra
	run_all
	;;
# Internal: the two halves of `all`, re-entered so each gets a clean process.
_backend_exec)
	load_backend_env
	run_backend_fg
	;;
_frontend_exec)
	run_frontend_fg
	;;
*)
	die "unknown mode '$1' (use: all, backend, frontend, env, install)"
	;;
esac
