# EventFlow developer commands. Run `make help` for the list.
.DEFAULT_GOAL := help
COMPOSE := docker compose

REQUIRED_DOCS := docs/contracts.md docs/failure-model.md \
	docs/adr/ADR-001-transport-http.md \
	docs/adr/ADR-002-event-identity.md \
	docs/adr/ADR-003-delivery-guarantee.md

.PHONY: help env up down clean logs psql check test

help: ## List available commands
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-8s %s\n", $$1, $$2}'

env: ## Create .env from .env.example (if missing)
	@test -f .env || (cp .env.example .env && echo "created .env")

up: env ## Start services (Postgres for now) and wait until healthy
	$(COMPOSE) up -d --wait

down: ## Stop services, keep data
	$(COMPOSE) down

clean: ## Stop services and DELETE local data volumes
	$(COMPOSE) down -v

logs: ## Follow service logs
	$(COMPOSE) logs -f

psql: ## Open a psql shell inside the Postgres container
	$(COMPOSE) exec postgres sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

check: ## Repo sanity checks (run by CI)
	@for f in $(REQUIRED_DOCS); do test -s $$f || { echo "missing or empty: $$f"; exit 1; }; done
	@echo "docs: ok"
	@if command -v docker >/dev/null 2>&1; then $(COMPOSE) config -q && echo "compose: ok"; \
	 else echo "compose: skipped (docker not installed)"; fi

test: ## Run all test suites that exist so far
	@echo "no test suites yet (ingest tests arrive on Day 2)"
