"""Jury demo — trip alert rules in sequence against the LIVE platform.

This script only mutates ERP data and then WAITS: detection, persistence,
SSE broadcast, toast, badge and email all happen through the running
system's own reactivity — nothing here calls the expert engine directly.
That is the point of the demo.

Run with the stack up and the browser open on any SupplyScope page:
    make demo-alerts
Restore the pristine world afterwards:
    make reset
"""
from __future__ import annotations

import time

import psycopg

from app.config import get_settings


def _exec(sql: str, params=()) -> str:
    with psycopg.connect(get_settings().app_dsn, autocommit=True) as c:
        row = c.execute(sql, params).fetchone()
    if row is None:
        raise SystemExit(
            "DEMO ABORT: the mutation matched no rows — the world is not "
            "in its pristine state. Run `make reset` and try again.")
    return row[0]


ACTS = [
    ("A shipment gets stuck at customs  (warning toast)",
     """UPDATE erp.shipments SET status='customs_hold',
            customs_entry_date = CURRENT_DATE - 9
        WHERE shipment_id = (SELECT shipment_id FROM erp.shipments
                             WHERE status = 'preparing'
                             ORDER BY shipment_id LIMIT 1)
        RETURNING shipment_ref"""),
    ("A supplier payment slips past 30 days overdue  (warning toast)",
     """UPDATE erp.payments SET due_date = CURRENT_DATE - 45
        WHERE payment_id = (SELECT payment_id FROM erp.payments
                            WHERE paid_date IS NULL
                              AND due_date >= CURRENT_DATE - 30
                            ORDER BY payment_id LIMIT 1)
        RETURNING payment_ref"""),
    ("Purchase orders push a project OVER BUDGET  "
     "(CRITICAL toast + email to deciders)",
     """UPDATE erp.projects p
        SET contract_value = sub.po_tnd / fp.rate_to_tnd / 1.07
        FROM (SELECT po.project_id,
                     sum(po.total_amount * f.rate_to_tnd) AS po_tnd
              FROM erp.purchase_orders po
              JOIN erp.fx_rates f ON f.currency = po.currency
              WHERE po.status NOT IN ('cancelled', 'draft')
              GROUP BY po.project_id) sub,
             erp.fx_rates fp
        WHERE sub.project_id = p.project_id
          AND fp.currency = p.currency
          AND p.status = 'active'
          AND sub.po_tnd / (p.contract_value * fp.rate_to_tnd)
              BETWEEN 0.30 AND 0.85
          AND p.project_id = (
              SELECT p2.project_id FROM erp.projects p2
              JOIN erp.fx_rates fp2 ON fp2.currency = p2.currency
              JOIN (SELECT po.project_id,
                           sum(po.total_amount * f.rate_to_tnd) AS po_tnd
                    FROM erp.purchase_orders po
                    JOIN erp.fx_rates f ON f.currency = po.currency
                    WHERE po.status NOT IN ('cancelled', 'draft')
                    GROUP BY po.project_id) s2
                ON s2.project_id = p2.project_id
              WHERE p2.status = 'active'
                AND s2.po_tnd / (p2.contract_value * fp2.rate_to_tnd)
                    BETWEEN 0.30 AND 0.85
              ORDER BY p2.project_id LIMIT 1)
        RETURNING p.project_code"""),
]

if __name__ == "__main__":
    print("SupplyScope alert demo — watch the toasts, the sidebar badge,")
    print("the Alerts page, and MailHog (http://localhost:8025).\n")
    for i, (story, sql) in enumerate(ACTS, 1):
        input(f"[Act {i}/3] {story} — press Enter to trigger...")
        ref = _exec(sql)
        print(f"    -> {ref} mutated. The platform is reacting on its own.\n")
        time.sleep(2)
    print("Done. `make reset` restores the pristine world.")
