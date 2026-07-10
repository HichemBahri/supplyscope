# SupplyScope

Agentic AI system for reactive generation of analytical visualizations from
operational data in EPC projects — application to Supply Chain Management.

Master's thesis (PFE) — GETS Company, Sfax / IHEC Carthage.

## Quick start

```bash
cp .env.example .env      # then edit POSTGRES_PASSWORD
docker compose up -d
docker compose ps         # postgres must be "healthy"
```

Adminer (DB browser): http://localhost:8080
(System: PostgreSQL · Server: postgres · credentials from .env · DB: supplyscope)

## Repository layout

```
supplyscope/
├── docker-compose.yml   # Runtime: postgres + adminer (backend/frontend added in later phases)
├── db/init/             # SQL executed on first DB start (schemas, roles)
├── backend/             # FastAPI + LangGraph application (Phase 2+)
├── docs/                # Architecture document & ADRs
├── Makefile             # make up / down / psql / reset
└── .env.example         # Environment template
```

## Documentation

- `docs/ARCHITECTURE.md` — system design and Architecture Decision Records.

## Status

- [x] Phase 0 — Foundation (repo, compose, DB schemas & roles)
- [ ] Phase 1 — ERP data model + synthetic data generator
- [ ] Phase 2 — Agent core (NL → SQL → chart spec)
- [ ] Phase 3 — API & persistence
- [ ] Phase 4 — Reactivity engine
- [ ] Phase 5 — Frontend
- [ ] Phase 6 — Hardening & evaluation
