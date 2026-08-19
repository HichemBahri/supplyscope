"""Expert-system engine: evaluates the rule catalog and maintains alerts.

Alert lifecycle:
  fire     — a rule's SQL returns an entity: the alert is inserted (active)
             or, if it already exists, its last_seen/context are refreshed.
  persist  — an acknowledged alert that keeps firing STAYS acknowledged
             (a human has seen it; we do not re-alarm every evaluation).
  resolve  — an alert whose condition no longer holds is marked resolved.
  re-fire  — if a resolved condition returns, the alert reactivates.

Alerts live in schema `es`, readable by agent_reader and carrying the same
NOTIFY triggers as erp/ml tables — so the NL agent can answer "what alerts
are active?" and pinned alert charts refresh live. Evaluation is triggered
at startup, on demand (admin), and reactively after any erp data change
(hooked into the reactivity engine's debounced processing).
"""
from __future__ import annotations

import logging

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

from app.config import get_settings
from app.db.app_repo import _dumps
from app.expert.rules import CONCENTRATION_THRESHOLD, RULES

logger = logging.getLogger("supplyscope.expert")

_DDL = """
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
"""


def ensure_ddl() -> None:
    with psycopg.connect(get_settings().app_dsn, autocommit=True) as c:
        c.execute(_DDL)


def _render(template: str, row: dict) -> str:
    try:
        return template.format(**row)
    except (KeyError, ValueError):        # a context column changed shape —
        return template                   # never let formatting kill an alert


def evaluate_all() -> dict:
    """Run every rule, upsert firing alerts, resolve cleared ones."""
    ensure_ddl()
    s = get_settings()
    fired: list[tuple] = []               # rows to upsert
    firing_keys: list[tuple[str, str]] = []
    with psycopg.connect(s.app_dsn, row_factory=dict_row) as conn:
        for rule in RULES:
            rows = conn.execute(rule.sql).fetchall()
            if rule.code == "SUPPLIER_CONCENTRATION":
                rows = [r for r in rows
                        if float(r["share"]) > CONCENTRATION_THRESHOLD]
            for r in rows:
                r = {k: (float(v) if hasattr(v, "quantize") else v)
                     for k, v in r.items()}
                key = (rule.code, str(r["entity_ref"]))
                firing_keys.append(key)
                fired.append((
                    rule.code, str(r["entity_ref"]), rule.severity,
                    _render(rule.title_template, r),
                    _render(rule.detail_template, r),
                    Json(r, dumps=_dumps),
                ))

    with psycopg.connect(s.app_dsn, autocommit=True) as conn:
        new = reactivated = 0
        with conn.cursor() as cur:
            for row in fired:
                cur.execute(
                    """
                    INSERT INTO es.alerts (rule_code, entity_ref, severity,
                                           title, detail, context)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (rule_code, entity_ref) DO UPDATE SET
                        last_seen = now(),
                        severity = EXCLUDED.severity,
                        title = EXCLUDED.title,
                        detail = EXCLUDED.detail,
                        context = EXCLUDED.context,
                        resolved_at = NULL,
                        status = CASE WHEN es.alerts.status = 'resolved'
                                      THEN 'active' ELSE es.alerts.status END
                    RETURNING (xmax = 0) AS inserted,
                              (status = 'active' AND xmax <> 0) AS kept
                    """, row)
                inserted, _ = cur.fetchone()
                new += int(bool(inserted))
            # resolve alerts whose condition no longer holds
            codes = [k[0] for k in firing_keys]
            refs = [k[1] for k in firing_keys]
            cur.execute(
                """
                UPDATE es.alerts
                SET status = 'resolved', resolved_at = now()
                WHERE status <> 'resolved'
                  AND NOT EXISTS (
                      SELECT 1 FROM unnest(%s::text[], %s::text[]) AS f(rc, er)
                      WHERE f.rc = es.alerts.rule_code
                        AND f.er = es.alerts.entity_ref)
                RETURNING alert_id
                """, (codes, refs))
            resolved = cur.rowcount
        counts = conn.execute(
            "SELECT severity, count(*) FROM es.alerts "
            "WHERE status <> 'resolved' GROUP BY severity").fetchall()
    by_sev = {sev: n for sev, n in counts}
    summary = {"firing": len(fired), "new": new, "resolved": resolved,
               "active_critical": by_sev.get("critical", 0),
               "active_warning": by_sev.get("warning", 0),
               "active_info": by_sev.get("info", 0)}
    logger.info("expert evaluation: %s", summary)
    return summary


if __name__ == "__main__":
    print(evaluate_all())
