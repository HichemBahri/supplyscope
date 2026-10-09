# SupplyScope

Agentic AI platform for the reactive analytical visualisation of EPC supply-chain data.

Master's thesis (PFE), Big Data Master, IHEC Carthage. Built during a five-month internship in the IT department of GETS (Global Engineering for Technical Services, Sfax), in collaboration with its supply-chain and tendering teams. Version 1.0 frozen on 4 September 2026, completed to 1.0.11 during the writing of the report.

## What it does

Around one PostgreSQL database modelled on the procure-to-pay process of an EPC contractor, SupplyScope combines five reasoning layers:

| Module | Capability |
|---|---|
| Conversational analytics | A LangGraph agent turns a plain-language question into SQL, runs it under a read-only database role, repairs its own errors from the database feedback and returns a validated chart. Fast and smart model tiers. |
| Charts and dashboards | Charts saved from answers, composed into dashboards that refresh within a second of a change in the ERP (LISTEN/NOTIFY, Server-Sent Events). Shared dashboards with comments. |
| Predictions | Delivery-risk classifier (order-time features, time split, model ladder with a registry) and a six-month price-index forecast with an expanding-window backtest. |
| Alerts | Seven declarative business rules evaluated on every data change, alert lifecycle (new, acknowledged, resolved, purged), in-app notifications and critical-alert e-mail. |
| Supplier recommendation | Simple Additive Weighting over seven criteria, including the predicted risk, with presets and custom weights; every score decomposes into auditable contributions; decisions recorded. |
| Award optimisation | Mixed-integer program (PuLP + CBC) that allocates a tender round under a risk ceiling and the 40 % concentration rule, compared with the actual awards and the cheapest-bid plan. |
| Dashboard synthesis | A complete dashboard generated from one topic, each view produced by the agent and filtered by deterministic quality gates that drop or repair defective charts and explain why. |

Access is by JWT with three roles (analyst, manager, administrator), e-mail verification, lockout after failed attempts and an audit trail of sensitive actions.

## Quick start

Requirements: Docker Desktop, Node 20, Python 3.12 with [uv](https://docs.astral.sh/uv/), an Anthropic (or OpenAI) API key.

```bash
cp .env.example .env            # set POSTGRES_PASSWORD, JWT_SECRET and your API key
make up                          # postgres, backend, mailhog, adminer
make seed                        # synthetic ERP world, seed 42 (21 tables, ~9,000 rows)
make train && make score         # delivery-risk model and scores
make train-forecast && make alerts
make front                       # React app on http://localhost:5173
```

Other entry points: API docs at http://localhost:8000/docs, mail inbox at http://localhost:8025, database browser at http://localhost:8080.

`make reset` restores the pristine seed-42 world with its models, scores and alerts, and is the precondition of the demonstrations and of the full test suite. `make help` lists every command.

## Repository layout

```
supplyscope/
├── docker-compose.yml      # postgres 16, backend, mailhog, adminer
├── Makefile                # operator commands (make help)
├── db/init/                # SQL run on first start: schemas, roles, ERP model, app tables, triggers, ml, es
├── backend/
│   ├── app/
│   │   ├── api/            # FastAPI routes, security (JWT, roles)
│   │   ├── agent/          # LangGraph graph, prompts, chart grammar, dashboard synthesis and gates
│   │   ├── db/             # application repository, safe executor, schema introspection
│   │   ├── reactivity/     # LISTEN/NOTIFY listener, chart dependency index, SSE
│   │   ├── ml/             # features, training ladder, registry, scoring, price forecast
│   │   ├── expert/         # rule catalogue and evaluation engine
│   │   ├── reco/           # SAW recommender
│   │   ├── optimize/       # MILP award optimiser
│   │   ├── eval/           # benchmark question bank and grader
│   │   ├── bigdata/        # twin pandas / Spark feature job (scale study)
│   │   └── services/       # audit trail, mailer
│   ├── data_generator/     # seeded synthetic world with planted situations; scale-mode generator
│   ├── scripts/            # bench_agent, eval_optimizer, eval_recommender, bench_scale, demo_alerts, simulate_activity
│   └── tests/              # 133 automated tests (pytest)
├── frontend/               # React + Vite single-page application
└── docs/                   # ARCHITECTURE.md, DATA_MODEL.md, report sources and diagram sources
```

## Evaluation

Every result of the report is reproducible from this repository.

```bash
make bench-agent                       # 43-question benchmark, ground truth computed by the database (LLM calls, cached)
make bench-agent ARGS="--llm-tier smart"
make bench-agent ARGS="--aggregate"    # stability over repeated runs
make eval-all                          # optimiser sensitivity sweep and recommender ablation (no LLM)
make bench-scale                       # pandas vs Spark ladder, 10 k to 30 M rows (needs uv sync --group bigdata and a JRE)
make test-all                          # full test suite against the seeded stack
```

Results at version 1.0: agent accuracy 95.3 % (fast tier) and 93.0 % (smart tier), identical over three runs; the predicted risk changes the recommended supplier in 12.5 % of cases; pandas faster than Spark at every size up to 30 million rows on one machine. Reports are written to `backend/bench_results/`.

## Versions

| Version | Content |
|---|---|
| 1.0 | Freeze at the end of Sprint 5 (4 September 2026) |
| 1.0.1 | Schema document extended to the `ml` and `es` schemas (defect found by the benchmark) |
| 1.0.2 to 1.0.8 | Interface completions: audit page, model tier selector, plain-prose answers, visible self-correction attempts, swapped-axis repair, deletion of pinned charts and of any dashboard by administrators, test-fixture cleanup |
| 1.0.9 to 1.0.10 | Scale benchmark: Spark heap sized to the machine, machine recorded on the chart, tolerance to an engine failure |
| 1.0.11 | Reason of each view dropped by the quality gates shown on the dashboards page |

## Documentation

- `docs/ARCHITECTURE.md`: system design and architecture decision records.
- `docs/DATA_MODEL.md`: the ERP data model and the planted situations of the synthetic world.
- `docs/report/`: sources of the thesis report and of its diagrams (PlantUML).

## Licence and data

The code is provided for academic evaluation. The data is synthetic, generated from a seed, and contains no information from GETS.
