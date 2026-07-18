"""Post-load validation: invariants + verification that the injected stories
are actually present and detectable in the database (each check is written as
SQL, i.e. exactly the way the Phase-2 agent will later see the data)."""
from __future__ import annotations

import psycopg

from . import config as C

CHECKS: list[tuple[str, str, str]] = [
    # (label, sql returning a single value, expectation description)
    ("PO totals == sum of lines (mismatches)",
     """SELECT count(*) FROM erp.purchase_orders po
        WHERE abs(po.total_amount -
              (SELECT coalesce(sum(line_total),0) FROM erp.po_lines l
               WHERE l.po_id = po.po_id)) > 0.05""",
     "must be 0"),
    ("Future actual deliveries (rows)",
     f"SELECT count(*) FROM erp.shipments WHERE actual_delivery_date > DATE '{C.SIM_NOW}'",
     "must be 0"),
    ("Delivered shipments without GRN (rows)",
     """SELECT count(*) FROM erp.shipments s
        WHERE s.status='delivered'
          AND NOT EXISTS (SELECT 1 FROM erp.goods_receipts g WHERE g.shipment_id=s.shipment_id)""",
     "must be 0"),
    ("Selected quotations failing TBE threshold (rows)",
     f"SELECT count(*) FROM erp.supplier_quotations WHERE status='selected' AND tbe_score < {C.TBE_PASS_THRESHOLD}",
     "must be 0"),
    ("Projects overspending >115% of contract (TND-normalized) — story allows 1",
     """WITH fx(cur, rate) AS (VALUES ('TND',1.00),('EUR',3.40),('USD',3.10),('LYD',0.64))
        SELECT count(*) FROM (
          SELECT p.project_id
          FROM erp.projects p
          JOIN fx fp ON fp.cur = p.currency
          JOIN erp.purchase_orders po USING (project_id)
          JOIN fx fpo ON fpo.cur = po.currency
          GROUP BY p.project_id, p.contract_value, fp.rate
          HAVING sum(po.total_amount * fpo.rate) > 1.15 * p.contract_value * fp.rate
        ) x""",
     "must be 0"),
    ("RFQs on non-validated BoQs (rows)",
     """SELECT count(*) FROM erp.rfqs r JOIN erp.boqs b USING (boq_id)
        WHERE NOT b.engineering_validated""",
     "must be 0"),
]

STORY_CHECKS: list[tuple[str, str]] = [
    ("S1 OTD late supplier vs others",
     f"""SELECT round(avg(CASE WHEN s.actual_delivery_date <= po.promised_delivery_date THEN 1 ELSE 0 END)
                 FILTER (WHERE sup.supplier_code = '{C.STORY_LATE_SUPPLIER_CODE}'), 2) AS late_sup,
            round(avg(CASE WHEN s.actual_delivery_date <= po.promised_delivery_date THEN 1 ELSE 0 END)
                 FILTER (WHERE sup.supplier_code <> '{C.STORY_LATE_SUPPLIER_CODE}'), 2) AS others
     FROM erp.shipments s
     JOIN erp.purchase_orders po USING (po_id)
     JOIN erp.suppliers sup ON sup.supplier_id = po.supplier_id
     WHERE s.status = 'delivered'"""),
    ("S2 steel price index (unit_price/ref): 2023-H2 vs 2025-H1",
     """SELECT round(avg(l.unit_price / m.ref_unit_price) FILTER (WHERE po.order_date BETWEEN '2023-07-01' AND '2023-12-31'), 2),
               round(avg(l.unit_price / m.ref_unit_price) FILTER (WHERE po.order_date BETWEEN '2025-01-01' AND '2025-06-30'), 2)
        FROM erp.po_lines l
        JOIN erp.materials m USING (material_id)
        JOIN erp.purchase_orders po USING (po_id)
        WHERE m.category = 'steel'"""),
    ("S3 customs days to Libya: Q1-2025 vs other periods",
     """SELECT round(avg(customs_clearance_date - customs_entry_date)
                 FILTER (WHERE customs_entry_date BETWEEN '2025-01-01' AND '2025-03-31'), 1),
               round(avg(customs_clearance_date - customs_entry_date)
                 FILTER (WHERE customs_entry_date NOT BETWEEN '2025-01-01' AND '2025-03-31'), 1)
        FROM erp.shipments s JOIN erp.sites st ON st.site_id=s.destination_site_id
        WHERE st.country='Libye' AND customs_clearance_date IS NOT NULL"""),
    ("S4 worst spend/contract ratio, TND-normalized (overbudget project)",
     f"""WITH fx(cur, rate) AS (VALUES ('TND',1.00),('EUR',3.40),('USD',3.10),('LYD',0.64))
        SELECT p.project_code,
               round((sum(po.total_amount * fpo.rate)
                      / (p.contract_value * fp.rate))::numeric, 3) AS ratio
        FROM erp.projects p
        JOIN fx fp ON fp.cur = p.currency
        JOIN erp.purchase_orders po USING (project_id)
        JOIN fx fpo ON fpo.cur = po.currency
        GROUP BY p.project_id, fp.rate ORDER BY ratio DESC LIMIT 1"""),
]


def run_validation(dsn: str) -> bool:
    ok = True
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        print("\n=== Row counts ===")
        for t in ("tenders", "proposals", "projects", "boqs", "boq_lines", "rfqs",
                  "supplier_quotations", "purchase_orders", "po_lines", "payments",
                  "shipments", "goods_receipts", "assets", "asset_assignments",
                  "maintenance_events"):
            cur.execute(f"SELECT count(*) FROM erp.{t}")
            print(f"  {t:22s} {cur.fetchone()[0]:>6}")
        print("\n=== Invariants ===")
        for label, sql, expect in CHECKS:
            cur.execute(sql)
            val = cur.fetchone()[0]
            passed = (val == 0)
            ok &= passed
            print(f"  [{'OK ' if passed else 'FAIL'}] {label}: {val} ({expect})")
        print("\n=== Injected stories (as the agent would query them) ===")
        for label, sql in STORY_CHECKS:
            cur.execute(sql)
            print(f"  {label}: {cur.fetchone()}")
    return ok
