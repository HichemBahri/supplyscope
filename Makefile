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

simulate:        ## Live ERP feed for the reactive demo: make simulate [interval=5]
	set -a && . ./.env && set +a && cd backend && uv run python -m scripts.simulate_activity --interval $${interval:-5}

front:           ## Run the React frontend in dev mode (http://localhost:5173)
	cd frontend && npm run dev

train:  ## Train the delivery-risk model ladder and activate the winner
	cd backend && uv run python -m app.ml.train_risk

bench-scale:  ## pandas-vs-Spark crossover benchmark (needs: uv sync --group bigdata + a JRE)
	cd backend && uv run python -m scripts.bench_scale

reset:  ## Restore the pristine seed-42 world + models + scores + alerts (test preconditions)
	$(MAKE) seed && $(MAKE) train && $(MAKE) score && $(MAKE) train-forecast && $(MAKE) alerts

alerts:  ## Evaluate the expert-system rules and refresh alerts
	cd backend && uv run python -m app.expert.engine

train-forecast:  ## Backtest the price-index ladder and store 6-month forecasts
	cd backend && uv run python -m app.ml.train_forecast

score:  ## Score open shipments with the active model (reactive refresh)
	cd backend && uv run python -m app.ml.scoring
