"""Agent benchmark — the question bank (Phase 15).

Every question carries a GROUND-TRUTH SQL that is executed against the
live database at benchmark time, so the expected answer is always the
database's, never a hand-typed constant that could drift from the world.

Grading kinds (see app.eval.grader):
  count    — exact integer (a numeric cell in the agent's first rows)
  scalar   — numeric within tolerance; ratio/percent equivalence accepted
  top1     — the agent's FIRST row must name the expected entity
             (any of the truth row's cells, case-insensitive substring)
  ordered  — the agent's first k rows must name the expected entities
             in order
  set      — the agent must return exactly len(expected) rows and every
             expected entity must appear somewhere in them

Tiers:
  easy    — one table, one aggregate or filter
  medium  — joins across 2–3 tables, business definitions (on-time, open)
  hard    — multi-step logic: FX normalization, time windows, ratios,
            derived schemas (ml.*, es.*), the injected stories
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BenchQuestion:
    qid: str
    tier: str                 # easy | medium | hard
    topic: str                # procurement | logistics | finance | tendering | assets | ml | expert
    question: str
    truth_sql: str
    kind: str                 # count | scalar | top1 | ordered | set
    tolerance: float = 0.02   # relative tolerance for scalar
    notes: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)


_OTD = """
    SELECT po.supplier_id, s.shipment_id,
           (s.actual_delivery_date <= po.promised_delivery_date)::int AS on_time,
           GREATEST(s.actual_delivery_date - po.promised_delivery_date, 0) AS days_late
    FROM erp.shipments s JOIN erp.purchase_orders po USING (po_id)
    WHERE s.actual_delivery_date IS NOT NULL
"""

QUESTIONS: list[BenchQuestion] = [
    # ------------------------------------------------------------ EASY
    BenchQuestion("E01", "easy", "procurement",
                  "How many active suppliers do we have?",
                  "SELECT count(*) FROM erp.suppliers WHERE is_active", "count"),
    BenchQuestion("E02", "easy", "procurement",
                  "How many purchase orders have been issued in total?",
                  "SELECT count(*) FROM erp.purchase_orders", "count"),
    BenchQuestion("E03", "easy", "tendering",
                  "How many projects are currently active?",
                  "SELECT count(*) FROM erp.projects WHERE status='active'", "count"),
    BenchQuestion("E04", "easy", "procurement",
                  "Which country has the most suppliers?",
                  "SELECT country, count(*) AS n FROM erp.suppliers "
                  "GROUP BY country ORDER BY n DESC, country LIMIT 1", "top1"),
    BenchQuestion("E05", "easy", "logistics",
                  "How many shipments are currently on customs hold?",
                  "SELECT count(*) FROM erp.shipments WHERE status='customs_hold'", "count"),
    BenchQuestion("E06", "easy", "tendering",
                  "How many tenders have been awarded?",
                  "SELECT count(*) FROM erp.tenders WHERE status='awarded'", "count"),
    BenchQuestion("E07", "easy", "procurement",
                  "What is the average payment terms in days across active suppliers?",
                  "SELECT round(avg(payment_terms_days)::numeric, 2) FROM erp.suppliers "
                  "WHERE is_active", "scalar"),
    BenchQuestion("E08", "easy", "procurement",
                  "How many distinct material categories do we purchase?",
                  "SELECT count(DISTINCT category) FROM erp.materials", "count"),
    BenchQuestion("E09", "easy", "assets",
                  "How many assets are currently under maintenance?",
                  "SELECT count(*) FROM erp.assets WHERE status='under_maintenance'", "count"),
    BenchQuestion("E10", "easy", "logistics",
                  "How many goods receipts were rejected at quality control?",
                  "SELECT count(*) FROM erp.goods_receipts WHERE qc_status='rejected'", "count"),
    BenchQuestion("E11", "easy", "tendering",
                  "How many clients are active?",
                  "SELECT count(*) FROM erp.clients WHERE is_active", "count"),
    BenchQuestion("E12", "easy", "procurement",
                  "How many RFQs were cancelled?",
                  "SELECT count(*) FROM erp.rfqs WHERE status='cancelled'", "count"),
    BenchQuestion("E13", "easy", "logistics",
                  "In which countries do we have sites?",
                  "SELECT DISTINCT country FROM erp.sites ORDER BY country", "set"),
    BenchQuestion("E14", "easy", "procurement",
                  "What is the average quoted lead time in days across all supplier quotations?",
                  "SELECT round(avg(lead_time_days)::numeric, 2) FROM erp.supplier_quotations",
                  "scalar"),

    # ---------------------------------------------------------- MEDIUM
    BenchQuestion("M01", "medium", "logistics",
                  "Which supplier has the worst on-time delivery rate, considering only "
                  "suppliers with at least 5 completed deliveries?",
                  f"WITH d AS ({_OTD}) SELECT sup.name, sup.supplier_code, "
                  "round(avg(on_time)::numeric,3) AS otd FROM d JOIN erp.suppliers sup "
                  "USING (supplier_id) GROUP BY sup.name, sup.supplier_code "
                  "HAVING count(*) >= 5 ORDER BY otd ASC LIMIT 1", "top1",
                  notes="story S1", tags=("story",)),
    BenchQuestion("M02", "medium", "logistics",
                  "Which supplier has the best on-time delivery rate, considering only "
                  "suppliers with at least 5 completed deliveries?",
                  f"WITH d AS ({_OTD}) SELECT sup.name, sup.supplier_code, "
                  "round(avg(on_time)::numeric,3) AS otd FROM d JOIN erp.suppliers sup "
                  "USING (supplier_id) GROUP BY sup.name, sup.supplier_code "
                  "HAVING count(*) >= 5 ORDER BY otd DESC, sup.name LIMIT 1", "top1"),
    BenchQuestion("M03", "medium", "procurement",
                  "Who are the top 3 suppliers by total purchase order value in TND?",
                  "SELECT sup.name, sup.supplier_code, "
                  "round(sum(po.total_amount*f.rate_to_tnd)::numeric,0) AS tnd "
                  "FROM erp.purchase_orders po JOIN erp.suppliers sup USING (supplier_id) "
                  "JOIN erp.fx_rates f ON f.currency=po.currency "
                  "GROUP BY sup.name, sup.supplier_code ORDER BY tnd DESC LIMIT 3", "ordered"),
    BenchQuestion("M04", "medium", "logistics",
                  "How many shipments were delivered late during 2025?",
                  "SELECT count(*) FROM erp.shipments s JOIN erp.purchase_orders po USING (po_id) "
                  "WHERE s.actual_delivery_date > po.promised_delivery_date "
                  "AND s.actual_delivery_date BETWEEN '2025-01-01' AND '2025-12-31'", "count"),
    BenchQuestion("M05", "medium", "logistics",
                  "What was the average number of days shipments to Libya spent in customs "
                  "during the first quarter of 2025?",
                  "SELECT round(avg(s.customs_clearance_date - s.customs_entry_date)::numeric,1) "
                  "FROM erp.shipments s JOIN erp.sites st ON st.site_id=s.destination_site_id "
                  "WHERE st.country='Libye' AND s.customs_entry_date IS NOT NULL "
                  "AND s.customs_clearance_date IS NOT NULL "
                  "AND s.customs_entry_date BETWEEN '2025-01-01' AND '2025-03-31'", "scalar",
                  tolerance=0.05, notes="story S3", tags=("story",)),
    BenchQuestion("M06", "medium", "procurement",
                  "Which material category has the highest total purchase order line value?",
                  "SELECT m.category, sum(pl.line_total*f.rate_to_tnd) AS v FROM erp.po_lines pl "
                  "JOIN erp.materials m USING (material_id) JOIN erp.purchase_orders po USING (po_id) "
                  "JOIN erp.fx_rates f ON f.currency=po.currency GROUP BY m.category "
                  "ORDER BY v DESC LIMIT 1", "top1", notes="FX-normalized to TND"),
    BenchQuestion("M07", "medium", "finance",
                  "Which project has the highest ratio of committed purchase order spend to "
                  "contract value, with both normalized to TND?",
                  "SELECT p.project_code, p.name, "
                  "round((sum(po.total_amount*fpo.rate_to_tnd)/(p.contract_value*fp.rate_to_tnd))::numeric,3) AS r "
                  "FROM erp.projects p JOIN erp.fx_rates fp ON fp.currency=p.currency "
                  "JOIN erp.purchase_orders po USING (project_id) "
                  "JOIN erp.fx_rates fpo ON fpo.currency=po.currency "
                  "WHERE po.status NOT IN ('cancelled','draft') "
                  "GROUP BY p.project_id, p.project_code, p.name, fp.rate_to_tnd "
                  "ORDER BY r DESC LIMIT 1", "top1", notes="story S4", tags=("story",)),
    BenchQuestion("M08", "medium", "procurement",
                  "How many purchase orders are still open (issued, confirmed or partially delivered)?",
                  "SELECT count(*) FROM erp.purchase_orders "
                  "WHERE status IN ('issued','confirmed','partially_delivered')", "count"),
    BenchQuestion("M09", "medium", "logistics",
                  "What is the overall on-time delivery rate across all delivered shipments, "
                  "as a percentage?",
                  f"WITH d AS ({_OTD}) SELECT round(100*avg(on_time)::numeric,1) FROM d", "scalar"),
    BenchQuestion("M10", "medium", "tendering",
                  "Which client has the most projects?",
                  "SELECT c.name, count(*) AS n FROM erp.projects p JOIN erp.clients c USING (client_id) "
                  "GROUP BY c.name ORDER BY n DESC, c.name LIMIT 1", "top1"),
    BenchQuestion("M11", "medium", "logistics",
                  "What is the total freight cost in TND of all shipments delivered to Libya?",
                  "SELECT round(sum(s.freight_cost*f.rate_to_tnd)::numeric,0) FROM erp.shipments s "
                  "JOIN erp.sites st ON st.site_id=s.destination_site_id "
                  "JOIN erp.fx_rates f ON f.currency=s.currency WHERE st.country='Libye'", "scalar"),
    BenchQuestion("M12", "medium", "procurement",
                  "How many supplier quotations scored below the technical evaluation threshold of 70?",
                  "SELECT count(*) FROM erp.supplier_quotations WHERE tbe_score < 70", "count"),
    BenchQuestion("M13", "medium", "procurement",
                  "Which supplier submitted the most quotations?",
                  "SELECT sup.name, sup.supplier_code, count(*) AS n FROM erp.supplier_quotations q "
                  "JOIN erp.suppliers sup USING (supplier_id) GROUP BY sup.name, sup.supplier_code "
                  "ORDER BY n DESC, sup.name LIMIT 1", "top1"),
    BenchQuestion("M14", "medium", "procurement",
                  "Which supplier has the highest average technical evaluation (TBE) score, "
                  "considering suppliers with at least 10 quotations?",
                  "SELECT sup.name, sup.supplier_code, round(avg(q.tbe_score)::numeric,2) AS t "
                  "FROM erp.supplier_quotations q JOIN erp.suppliers sup USING (supplier_id) "
                  "WHERE q.tbe_score IS NOT NULL GROUP BY sup.name, sup.supplier_code "
                  "HAVING count(*) >= 10 ORDER BY t DESC LIMIT 1", "top1"),
    BenchQuestion("M15", "medium", "finance",
                  "How many payments are currently overdue?",
                  "SELECT count(*) FROM erp.payments WHERE paid_date IS NULL AND due_date < CURRENT_DATE",
                  "count", notes="status column also says 'overdue'; both definitions agree"),

    # ------------------------------------------------------------ HARD
    BenchQuestion("H01", "hard", "procurement",
                  "What was the average steel price index (purchase order unit price divided by "
                  "the material's reference unit price) during the first half of 2025?",
                  "SELECT round(avg(pl.unit_price/m.ref_unit_price)::numeric,3) FROM erp.po_lines pl "
                  "JOIN erp.materials m USING (material_id) JOIN erp.purchase_orders po USING (po_id) "
                  "WHERE m.category='steel' AND po.order_date BETWEEN '2025-01-01' AND '2025-06-30'",
                  "scalar", tolerance=0.05, notes="story S2", tags=("story",)),
    BenchQuestion("H02", "hard", "ml",
                  "Which supplier's open shipment currently has the highest predicted "
                  "late-delivery probability according to the ML model?",
                  "SELECT supplier_name, shipment_ref, probability FROM ml.delivery_risk "
                  "ORDER BY probability DESC LIMIT 1", "top1", tags=("ml",)),
    BenchQuestion("H03", "hard", "expert",
                  "How many critical alerts are currently active (not resolved)?",
                  "SELECT count(*) FROM es.alerts WHERE severity='critical' AND status<>'resolved'",
                  "count", tags=("expert",)),
    BenchQuestion("H04", "hard", "logistics",
                  "Which calendar year had the lowest on-time delivery rate?",
                  "SELECT extract(year FROM s.actual_delivery_date)::int AS y, "
                  "round(avg((s.actual_delivery_date <= po.promised_delivery_date)::int)::numeric,3) AS otd "
                  "FROM erp.shipments s JOIN erp.purchase_orders po USING (po_id) "
                  "WHERE s.actual_delivery_date IS NOT NULL GROUP BY y ORDER BY otd ASC, y LIMIT 1",
                  "top1"),
    BenchQuestion("H05", "hard", "finance",
                  "How many projects have committed purchase order spend above 90% of their "
                  "contract value, with both normalized to TND?",
                  "SELECT count(*) FROM (SELECT p.project_id FROM erp.projects p "
                  "JOIN erp.fx_rates fp ON fp.currency=p.currency "
                  "JOIN erp.purchase_orders po USING (project_id) "
                  "JOIN erp.fx_rates fpo ON fpo.currency=po.currency "
                  "WHERE po.status NOT IN ('cancelled','draft') "
                  "GROUP BY p.project_id, p.contract_value, fp.rate_to_tnd "
                  "HAVING sum(po.total_amount*fpo.rate_to_tnd) > 0.9*p.contract_value*fp.rate_to_tnd) x",
                  "count"),
    BenchQuestion("H06", "hard", "logistics",
                  "Which supplier country has the highest average delivery delay in days "
                  "(late shipments counted by their days late, on-time as zero)?",
                  f"WITH d AS ({_OTD}) SELECT sup.country, round(avg(days_late)::numeric,2) AS dl "
                  "FROM d JOIN erp.suppliers sup USING (supplier_id) GROUP BY sup.country "
                  "ORDER BY dl DESC LIMIT 1", "top1"),
    BenchQuestion("H07", "hard", "procurement",
                  "What percentage of total purchase order value in TND goes to our single "
                  "largest supplier?",
                  "WITH t AS (SELECT sup.supplier_id, sum(po.total_amount*f.rate_to_tnd) AS v "
                  "FROM erp.purchase_orders po JOIN erp.suppliers sup USING (supplier_id) "
                  "JOIN erp.fx_rates f ON f.currency=po.currency GROUP BY sup.supplier_id) "
                  "SELECT round((100*max(v)/sum(v))::numeric,1) FROM t", "scalar", tolerance=0.03),
    BenchQuestion("H08", "hard", "logistics",
                  "How many shipments spent more than 20 days in customs?",
                  "SELECT count(*) FROM erp.shipments WHERE customs_entry_date IS NOT NULL "
                  "AND customs_clearance_date IS NOT NULL "
                  "AND customs_clearance_date - customs_entry_date > 20", "count"),
    BenchQuestion("H09", "hard", "ml",
                  "What is the forecasted steel price index for the next forecast month?",
                  "SELECT round(price_index::numeric,3) FROM ml.price_forecast "
                  "WHERE category='steel' AND kind='forecast' ORDER BY month LIMIT 1",
                  "scalar", tolerance=0.02, tags=("ml",)),
    BenchQuestion("H10", "hard", "finance",
                  "Which supplier has the largest total amount of overdue payments in TND?",
                  "SELECT sup.name, sup.supplier_code, round(sum(pay.amount*f.rate_to_tnd)::numeric,0) AS v "
                  "FROM erp.payments pay JOIN erp.purchase_orders po USING (po_id) "
                  "JOIN erp.suppliers sup USING (supplier_id) JOIN erp.fx_rates f ON f.currency=pay.currency "
                  "WHERE pay.paid_date IS NULL AND pay.due_date < CURRENT_DATE "
                  "GROUP BY sup.name, sup.supplier_code ORDER BY v DESC LIMIT 1", "top1"),
    BenchQuestion("H11", "hard", "logistics",
                  "What is the on-time delivery rate, as a percentage, for shipments from "
                  "foreign (non-Tunisian) suppliers?",
                  f"WITH d AS ({_OTD}) SELECT round(100*avg(on_time)::numeric,1) FROM d "
                  "JOIN erp.suppliers sup USING (supplier_id) WHERE sup.country <> 'Tunisie'",
                  "scalar"),
    BenchQuestion("H12", "hard", "assets",
                  "Which asset category has the highest total maintenance cost in TND?",
                  "SELECT a.category, round(sum(me.cost*f.rate_to_tnd)::numeric,0) AS v "
                  "FROM erp.maintenance_events me JOIN erp.assets a USING (asset_id) "
                  "JOIN erp.fx_rates f ON f.currency=me.currency GROUP BY a.category "
                  "ORDER BY v DESC LIMIT 1", "top1"),
    BenchQuestion("H13", "hard", "expert",
                  "Which suppliers are currently flagged by the expert system for low "
                  "on-time delivery? List them.",
                  "SELECT sup.name, a.entity_ref FROM es.alerts a JOIN erp.suppliers sup "
                  "ON sup.supplier_code=a.entity_ref WHERE a.rule_code='SUPPLIER_LOW_OTD' "
                  "AND a.status<>'resolved' ORDER BY sup.name", "set",
                  tags=("expert", "story")),
    BenchQuestion("H14", "hard", "tendering",
                  "What is the total value in TND of proposals we won during 2025?",
                  "SELECT round(sum(pr.proposed_value*f.rate_to_tnd)::numeric,0) FROM erp.proposals pr "
                  "JOIN erp.fx_rates f ON f.currency=pr.currency WHERE pr.status='won' "
                  "AND pr.decision_date BETWEEN '2025-01-01' AND '2025-12-31'", "scalar"),
]

BY_ID = {q.qid: q for q in QUESTIONS}
TIERS = ("easy", "medium", "hard")
