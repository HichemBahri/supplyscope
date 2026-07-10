-- =============================================================================
-- SupplyScope — database bootstrap
-- Runs automatically the FIRST time the postgres container starts
-- (docker-entrypoint-initdb.d). To re-run: `docker compose down -v` then up.
-- =============================================================================

-- Two-schema layout (see ADR-006):
--   erp : mock ERP / Supply Chain data — the agent's READ-ONLY world
--   app : application data (users, conversations, saved charts, dashboards)
CREATE SCHEMA IF NOT EXISTS erp;
CREATE SCHEMA IF NOT EXISTS app;

-- -----------------------------------------------------------------------------
-- Security boundary: the role used by the agent's SQL-execution tool.
-- SELECT-only on erp.*, no access to app.* — LLM-generated SQL runs as this role.
-- The password here is for local development only; it is overridden per
-- environment via the AGENT_DB_PASSWORD setting in later phases.
-- -----------------------------------------------------------------------------
DO $$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'agent_reader') THEN
      CREATE ROLE agent_reader LOGIN PASSWORD 'agent_reader_dev_only';
   END IF;
END
$$;

GRANT USAGE ON SCHEMA erp TO agent_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA erp TO agent_reader;
-- Tables created later in erp are automatically readable by the agent:
ALTER DEFAULT PRIVILEGES IN SCHEMA erp GRANT SELECT ON TABLES TO agent_reader;

-- Explicitly no grants on schema app for agent_reader.
REVOKE ALL ON SCHEMA app FROM agent_reader;
