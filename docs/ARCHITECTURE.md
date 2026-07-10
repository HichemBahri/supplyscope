# SupplyScope — Architecture & Decision Records

**Project:** Agentic AI System for Reactive Generation of Analytical Visualizations
from Operational Data in EPC Projects — Application to Supply Chain Management.
**Company:** GETS (Global Engineering for Technical Services), Sfax, Tunisia.
**Author:** Hichem — Master Big Data, IHEC Carthage.

> Working name "SupplyScope" — rename freely; only the repo folder and one
> docker-compose project name need changing.

---

## 1. System overview

A business user (Procurement Engineer, Logistics Coordinator, Asset Manager, Tendering
team member) asks questions in natural language. An LLM-driven agent translates the
question into validated SQL over a mock EPC/Supply-Chain ERP database, returns the
answer as a **declarative chart specification** rendered in a web UI, and — the key
contribution — **saved charts update automatically** when the underlying data changes,
through an event-driven change-detection pipeline.

```
┌────────────┐   NL question    ┌──────────────────────────────┐
│  React SPA │ ───────────────► │  FastAPI (modular monolith)  │
│  Plotly.js │ ◄─────────────── │  ┌────────────────────────┐  │
│  chat + dashboards (SSE)      │  │ LangGraph Orchestrator │  │
└────────────┘   chart specs    │  │ plan → SQL → validate  │  │
      ▲                         │  │ → chart spec → answer  │  │
      │  auto-refresh (SSE)     │  └────────────────────────┘  │
      │                         │  Reactivity engine:          │
      │                         │  LISTEN/NOTIFY → dependency  │
      │                         │  index → re-exec → push      │
      │                         └───────────────┬──────────────┘
      │                                         │
      │                              ┌──────────▼──────────┐
      └──────────────────────────────┤ PostgreSQL          │
                data change (demo    │  schema `erp`  (mock│
                simulator inserts)   │  Supply Chain data) │
                                     │  schema `app`  (users,
                                     │  conversations, charts)
                                     └─────────────────────┘
```

---

## 2. Architecture Decision Records (ADRs)

Format: **Context → Decision → Consequences**. These ADRs are written to be
pasted (expanded) into the thesis design chapter.

### ADR-001 — Modular monolith, not microservices
- **Context:** Prior work (HRizon, Belhadj 2025) used 8 microservices; team of one,
  10 development weeks, no multi-tenant requirement.
- **Decision:** Single FastAPI application with strict internal layering
  (`routes → services → agent → persistence`). Docker Compose runs 3 containers:
  postgres, backend, frontend.
- **Consequences:** Drastically lower operational complexity; layering preserves the
  option to extract services later (documented as perspective). Trade-off: no
  independent scaling — irrelevant at our scale.

### ADR-002 — Single-orchestrator agent (LangGraph), not multi-agent frameworks
- **Context:** CrewAI/AutoGen-style parallel agent teams add cost, latency and
  debugging complexity; the task is a sequential workflow (plan → generate → validate
  → correct). Consistent with Anthropic's "simple composable patterns" guidance and
  with the prior-work conclusion (HRizon rejected multi-agent teams for the same reason).
- **Decision:** One LangGraph state machine with typed state, explicit nodes and
  conditional edges; the self-correcting SQL executor and the chart-spec generator are
  reusable sub-graphs.
- **Consequences:** Auditable, testable, cheap. The system remains legitimately
  "agentic": dynamic planning, tool use, self-correction loops, conditional routing.

### ADR-003 — Charts are declarative JSON specifications, never generated code/images
- **Context:** Reactivity requires re-rendering charts with fresh data; executing
  LLM-generated Python is a security hazard; images cannot be updated incrementally.
- **Decision:** The agent emits a chart spec = `{sql, chart_type, encodings, title, ...}`
  validated against per-chart-type Pydantic models. Frontend renders specs with
  Plotly.js via a dispatcher component. Backend re-executes `sql` to refresh data.
- **Consequences:** Reactivity becomes "re-run query + push rows"; no code execution
  from LLM output; strict schema validation catches malformed generations. Trade-off:
  chart vocabulary limited to the spec schema (acceptable; extensible).

### ADR-004 — Reactivity via PostgreSQL LISTEN/NOTIFY + chart dependency index + SSE
- **Context:** Prior work proposed log-tailing CDC but shipped interval polling
  (deferred for time; also could not add triggers to a *client's* database). We own our
  database, so lightweight triggers are acceptable.
- **Decision:** AFTER INSERT/UPDATE/DELETE triggers on `erp.*` tables emit
  `pg_notify('data_change', payload)`. On chart save, its SQL is parsed to extract
  referenced tables → stored in a dependency index (`table → [chart_ids]`). A backend
  listener receives notifications (debounced), re-executes only affected chart specs,
  and pushes fresh data to subscribed clients over Server-Sent Events.
- **Consequences:** True event-driven updates (vs polling) with second-level latency;
  minimal DB overhead. Trade-offs: NOTIFY payload limit (8 KB — we send table names,
  not data), delivery is at-most-once per connection (acceptable: a missed event is
  healed by the next one or manual refresh; documented limitation).

### ADR-005 — Provider-agnostic LLM layer
- **Context:** Model pricing/availability changes; thesis should not be married to one
  vendor; dev should run on cheap models, demo/eval on stronger ones.
- **Decision:** An LLM factory returning a LangChain chat-model interface, configured
  by env vars (`LLM_PROVIDER`, `LLM_MODEL`). Supported: Anthropic, OpenAI (Groq
  addable). Distinct "fast" and "smart" model slots.
- **Consequences:** One-line model swaps; enables cost control and a cross-model
  accuracy comparison in the evaluation chapter.

### ADR-006 — One PostgreSQL instance, two schemas: `erp` and `app`
- **Context:** Prior work used Postgres + MongoDB + Redis + ChromaDB; our data is
  relational and volumes are small.
- **Decision:** Schema `erp` holds mock ERP data (the agent's *read-only* world);
  schema `app` holds users, conversations, messages, saved charts, dashboards. The
  agent's DB role has SELECT-only rights on `erp` and no rights on `app`.
- **Consequences:** One backup, one connection pool, schema-level security boundary.
  JSONB covers our few document-shaped needs (chart specs, message payloads).

### ADR-007 — React SPA (Vite + TypeScript), not Next.js
- **Context:** No SEO/SSR requirement; single authenticated app.
- **Decision:** Vite + React + TypeScript SPA, Tailwind + shadcn/ui, Plotly.js,
  native EventSource for SSE.
- **Consequences:** Simpler build/deploy (static files), faster dev loop. SSR benefits
  forfeited — none apply here.

### ADR-008 — SSE for server→client push, not WebSockets
- **Context:** Our real-time needs are one-directional (server pushes chart updates
  and streamed agent responses); client→server traffic is ordinary REST.
- **Decision:** Server-Sent Events (native browser `EventSource`, plain HTTP).
- **Consequences:** No socket.io dependency, works through proxies, auto-reconnect
  built in. Trade-off: no client→server push channel — not needed.

### ADR-009 — Docker Compose is the official runtime
- **Context:** Reproducibility for jury/supervisor beats cloud complexity; LLM API
  requires internet anyway.
- **Decision:** `docker compose up` = the system. Optional VPS deployment only if
  ahead of schedule (week 8+). A recorded demo video is the fallback for the defense.
- **Consequences:** Zero cloud cost/risk; identical environment everywhere.

---

## 3. Explicitly excluded scope (thesis "limitations & perspectives")

| Excluded | Why | Perspective framing |
|---|---|---|
| Multi-tenancy, IAM (Keycloak) | No requirement; weeks of work | Enterprise deployment path |
| ELT stack (Airbyte/dbt/Airflow) | Data is generated, not ingested | Integration with live ERP |
| RAG insights layer | Schema introspection suffices at our scale | Grounding on business docs |
| Log-tailing CDC | Triggers acceptable on owned DB | Client-DB, non-intrusive CDC |
| Local/fine-tuned LLM | GPU cost, time | On-premise privacy deployment |
| Microservices + gateway | Team of one | Scale-out path |

## 4. Prior work

Belhadj, I. (2025). *End-to-end Agentic Data Platform (HRizon)*. PFE report, Talan
Consulting / ESPRIT. — Cited for: single-orchestrator justification, declarative chart
representation, self-correction pattern, evaluation methodology. This project differs
in domain (EPC Supply Chain vs HR), architecture scale (focused monolith vs platform),
and ships an **implemented event-driven reactivity mechanism** where prior work
deferred to interval polling.

## 5. Phase roadmap

| Phase | Weeks | Deliverable |
|---|---|---|
| 0 Foundation | 0.5 | This document, repo, compose stack (DB up) |
| 1 Data | 1.5 | ERP schema + rule-driven synthetic data generator + seed |
| 2 Agent core | 2.5 | LangGraph pipeline: NL → SQL → validated chart spec (CLI-testable) |
| 3 API | 1.5 | FastAPI: auth, conversations, chart persistence, agent endpoint |
| 4 Reactivity | 1.5 | Triggers, dependency index, SSE push, demo data simulator |
| 5 Frontend | 2 | Chat UI + reactive dashboard |
| 6 Hardening & eval | 1 | Test suite, golden benchmark, eval harness, packaging |
| 7 Thesis support | (post-internship) | Benchmarks, writing, defense prep |
