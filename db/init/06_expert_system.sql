-- Expert system (Phase 8): schema es, alerts, grants, reactivity trigger

CREATE SCHEMA IF NOT EXISTS es;
GRANT USAGE ON SCHEMA es TO agent_reader;

CREATE TABLE IF NOT EXISTS es.alerts (
    alert_id    integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    rule_code   text NOT NULL,
    entity_ref  text NOT NULL,
    severity    text NOT NULL CHECK (severity IN ('info','warning','critical')),
    title       text NOT NULL,
    detail      text NOT NULL,
    context     jsonb NOT NULL DEFAULT '{}'::jsonb,
    status      text NOT NULL DEFAULT 'active'
                CHECK (status IN ('active','acknowledged','resolved')),
    first_seen  timestamptz NOT NULL DEFAULT now(),
    last_seen   timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz,
    acknowledged_by integer,
    acknowledged_at timestamptz,
    UNIQUE (rule_code, entity_ref)
);
COMMENT ON TABLE es.alerts IS
 'Expert-system alerts: business rules evaluated over erp data. status: active (condition holds, unseen), acknowledged (condition holds, seen by a human), resolved (condition no longer holds). severity: info/warning/critical.';
GRANT SELECT ON es.alerts TO agent_reader;

DO $$ BEGIN
  CREATE TRIGGER trg_notify_change
  AFTER INSERT OR UPDATE OR DELETE ON es.alerts
  FOR EACH STATEMENT EXECUTE FUNCTION erp.notify_data_change();
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
