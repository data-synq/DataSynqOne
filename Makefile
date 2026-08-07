COMPOSE     := docker compose
COMPOSE_DEV := docker compose -f compose.yml -f compose.dev.yml
INFRA       := redis postgres vectordb paperless

.DEFAULT_GOAL := help
.PHONY: help dev dev-backend dev-frontend dev-down infra infra-down \
        install env up down build logs ps sync clean

help: ## Show this help
	@printf '\033[1mDataSynq One\033[0m\n\n'
	@printf '\033[1mDevelopment\033[0m  (infra in Docker, apps native with hot reload)\n'
	@awk 'BEGIN {FS = ":.*## "} /^(dev|install|env)[a-z-]*:.*## / {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@printf '\n\033[1mProduction-like stack\033[0m  (everything in Docker)\n'
	@awk 'BEGIN {FS = ":.*## "} /^(up|down|build|logs|ps|infra|sync|clean)[a-z-]*:.*## / {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@printf '\n\033[2m  dev and up cannot run at the same time — both claim the same container names.\033[0m\n'
	@printf '\033[2m  Dev ports: frontend 5173, backend 8001, paperless 80, vectordb 5433.\033[0m\n'

# --- development ------------------------------------------------------------

dev: ## Start everything in dev mode (Ctrl-C stops backend + frontend)
	@scripts/dev.sh

dev-backend: ## Only uvicorn --reload on :8001, in the foreground
	@scripts/dev.sh backend

dev-frontend: ## Only the vite dev server on :5173, in the foreground
	@scripts/dev.sh frontend

dev-down: ## Stop the dev infrastructure containers
	$(COMPOSE_DEV) down

install: ## Reinstall server/.venv and src/node_modules
	@scripts/dev.sh install

env: ## Create any missing env/*.env from the .example templates
	@scripts/dev.sh env

# --- containers -------------------------------------------------------------

infra: ## Start only redis, postgres, vectordb, paperless
	$(COMPOSE_DEV) up -d $(INFRA)

infra-down: ## Stop those infrastructure containers
	$(COMPOSE_DEV) stop $(INFRA)

up: ## Start the full stack from compose.yml (frontend on :8080)
	$(COMPOSE) up -d

build: ## Rebuild the backend and frontend images
	$(COMPOSE) build

down: ## Stop the full stack
	$(COMPOSE) down

logs: ## Follow the logs of the full stack
	$(COMPOSE) logs -f

ps: ## Show container status
	$(COMPOSE) ps

# --- utilities --------------------------------------------------------------

sync: ## Index Paperless documents into the vector database
	curl -fsS -X POST http://localhost:8001/sync/documents && echo
	curl -fsS http://localhost:8001/sync/status && echo

clean: ## Remove server/.venv, src/node_modules and src/dist
	rm -rf server/.venv src/node_modules src/dist
