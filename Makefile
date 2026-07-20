# Convenience commands — run `make help`
.PHONY: help up down logs ps psql reset

help:            ## Show this help
	@grep -E '^[a-z]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-8s %s\n", $$1, $$2}'

up:              ## Start the stack in the background
	docker compose up -d

down:            ## Stop the stack (data is kept)
	docker compose down

logs:            ## Follow postgres logs
	docker compose logs -f postgres

ps:              ## Show container status
	docker compose ps

psql:            ## Open a psql shell as the admin user
	docker compose exec postgres psql -U $${POSTGRES_USER:-supplyscope} -d $${POSTGRES_DB:-supplyscope}

reset:           ## DANGER: wipe the database volume and restart fresh
	docker compose down -v && docker compose up -d

seed:            ## Generate & load synthetic ERP data (override: make seed SEED=7)
	set -a && . ./.env && set +a && cd backend && uv run python -m data_generator --seed $${SEED:-42}

test:            ## Run backend unit tests (fast, no DB/API needed)
	cd backend && uv run pytest tests -m "not integration" -q

test-all:        ## Run all backend tests (needs the seeded docker DB up)
	set -a && . ./.env && set +a && cd backend && uv run pytest tests -q

ask:             ## Ask the agent from repo root: make ask q="..." [tier=smart]
	set -a && . ./.env && set +a && cd backend && uv run python -m scripts.ask "$(q)" --tier $${tier:-fast}

api:             ## Run the FastAPI backend in dev mode (http://localhost:8000)
	set -a && . ./.env && set +a && cd backend && uv run uvicorn app.main:app --reload --port 8000
