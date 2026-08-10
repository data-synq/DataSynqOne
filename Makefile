COMPOSE     := docker compose
COMPOSE_DEV := docker compose -f compose.yml -f compose.dev.yml
INFRA       := redis postgres vectordb paperless mailpit gotenberg tika

.DEFAULT_GOAL := help
.PHONY: help dev dev-backend dev-frontend dev-down infra infra-down \
        install env up down build logs ps sync clean test test-backend \
        test-frontend test-e2e check lock prod-validate prod-paths backup restore-check

help: ## Show this help
	@printf '\033[1mDataSynq One\033[0m\n\n'
	@printf '\033[1mDevelopment\033[0m  (infra in Docker, apps native with hot reload)\n'
	@awk 'BEGIN {FS = ":.*## "} /^(dev|install|env)[a-z-]*:.*## / {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@printf '\n\033[1mTesting\033[0m\n'
	@awk 'BEGIN {FS = ":.*## "} /^(test|check|lock)[a-z0-9-]*:.*## / {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@printf '\n\033[1mProduction-like stack\033[0m  (everything in Docker)\n'
	@awk 'BEGIN {FS = ":.*## "} /^(up|down|build|logs|ps|infra|sync|clean|prod)[a-z-]*:.*## / {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
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

# --- tests ------------------------------------------------------------------

test: test-backend test-frontend ## Run the fast backend and frontend test suites

test-backend: ## Run backend unit and API smoke tests
	@cd server && ./.venv/bin/python -m pytest

test-frontend: ## Run frontend unit and component tests
	@npm --prefix src run test:unit

test-e2e: ## Build the frontend and run the browser smoke test
	@npm --prefix src run test:e2e

check: test test-e2e ## Run all tests and production frontend build
	@cd server && ./.venv/bin/python -m compileall -q app

lock: ## Regenerate hashed Python dependency locks from requirements*.in
	@cd server && ./.venv/bin/uv pip compile --generate-hashes --output-file requirements.txt requirements.in
	@cd server && ./.venv/bin/uv pip compile --generate-hashes --output-file requirements-dev.txt requirements-dev.in

prod-validate: ## Validate rendered production Compose security invariants
	@docker compose -f compose.prod.yml config --format json | python3 scripts/validate_prod_compose.py

prod-paths: ## Check production bind-mount ownership without changing files
	@python3 scripts/check_prod_paths.py

backup: ## Create logical database and Paperless-media backups
	@bash scripts/backup.sh

restore-check: ## Validate BACKUP_DIR artifacts before a restore drill
	@bash scripts/restore-check.sh "$(BACKUP_DIR)"

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
	@scripts/dev.sh sync

clean: ## Remove server/.venv, src/node_modules and src/dist
	rm -rf server/.venv src/node_modules src/dist
