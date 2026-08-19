"""The expert-system rule catalog — the third reasoning paradigm.

Where the ML layer LEARNS patterns from data and the LLM agent INTERPRETS
language, this layer ENCODES explicit expert knowledge as declarative rules:
IF <condition over the data> THEN <alert with severity and explanation>.

Each rule is data, not code: a SQL condition returning the entities in
breach plus context values, and templates that turn a row into a
human-readable alert. Adding a rule = adding an entry to RULES.
Every rule's SQL must return a column `entity_ref` (stable identifier used
to track the same alert across evaluations) — remaining columns become the
alert's context payload.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    code: str
    name: str
    severity: str                 # info | warning | critical
    description: str              # shown in the rule catalog (and the thesis)
    sql: str                      # SELECT entity_ref, ...context
    title_template: str           # str.format(**row)
    detail_template: str


RULES: list[Rule] = [
    Rule(
        code="SUPPLIER_LOW_OTD",
        name="Chronically late supplier",
        severity="critical",
        description="A supplier with at least 5 delivered shipments whose "
                    "on-time rate falls below 60% — sustained delivery risk.",
        sql="""
            SELECT sup.supplier_code AS entity_ref,
                   sup.name AS supplier_name,
                   count(*) AS delivered,
                   round(avg((s.actual_delivery_date
                              <= po.promised_delivery_date)::int), 3) AS otd
            FROM erp.shipments s
            JOIN erp.purchase_orders po USING (po_id)
            JOIN erp.suppliers sup ON sup.supplier_id = po.supplier_id
            WHERE s.actual_delivery_date IS NOT NULL
            GROUP BY sup.supplier_code, sup.name
            HAVING count(*) >= 5
               AND avg((s.actual_delivery_date
                        <= po.promised_delivery_date)::int) < 0.60
        """,
        title_template="Supplier {supplier_name} on-time rate {otd:.0%}",
        detail_template="{supplier_name} delivered on time only {otd:.0%} of "
                        "{delivered} shipments — below the 60% threshold. "
                        "Review sourcing for open orders with this supplier.",
    ),
    Rule(
        code="SHIPMENT_CUSTOMS_HOLD",
        name="Shipment held at customs",
        severity="warning",
        description="A shipment currently blocked in customs clearance.",
        sql="""
            SELECT s.shipment_ref AS entity_ref,
                   po.po_number,
                   sup.name AS supplier_name,
                   dst.country AS destination,
                   (CURRENT_DATE - s.customs_entry_date) AS days_in_customs
            FROM erp.shipments s
            JOIN erp.purchase_orders po USING (po_id)
            JOIN erp.suppliers sup ON sup.supplier_id = po.supplier_id
            JOIN erp.sites dst ON dst.site_id = s.destination_site_id
            WHERE s.status = 'customs_hold'
        """,
        title_template="{entity_ref} held at customs ({destination})",
        detail_template="Shipment {entity_ref} for {po_number} "
                        "({supplier_name}) has been in customs for "
                        "{days_in_customs} days. Escalate with the clearing "
                        "agent if documentation is pending.",
    ),
    Rule(
        code="PROJECT_BUDGET_90",
        name="Project nearing budget",
        severity="warning",
        description="Procurement spend has reached 90% of the project's "
                    "contract value (TND-normalized) but is not yet over.",
        sql="""
            SELECT p.project_code AS entity_ref, p.name AS project_name,
                   round(sum(po.total_amount * fpo.rate_to_tnd)
                         / (p.contract_value * fp.rate_to_tnd), 3) AS ratio
            FROM erp.projects p
            JOIN erp.fx_rates fp ON fp.currency = p.currency
            JOIN erp.purchase_orders po USING (project_id)
            JOIN erp.fx_rates fpo ON fpo.currency = po.currency
            WHERE po.status NOT IN ('cancelled', 'draft')
            GROUP BY p.project_id, fp.rate_to_tnd
            HAVING sum(po.total_amount * fpo.rate_to_tnd)
                   / (p.contract_value * fp.rate_to_tnd) >= 0.90
               AND sum(po.total_amount * fpo.rate_to_tnd)
                   / (p.contract_value * fp.rate_to_tnd) < 1.00
        """,
        title_template="Project {entity_ref} at {ratio:.0%} of budget",
        detail_template="Procurement spend on {project_name} has reached "
                        "{ratio:.0%} of contract value. Review open "
                        "commitments before issuing further POs.",
    ),
    Rule(
        code="PROJECT_OVERBUDGET",
        name="Project over budget",
        severity="critical",
        description="Procurement spend exceeds 100% of contract value "
                    "(TND-normalized) — the project is buying at a loss.",
        sql="""
            SELECT p.project_code AS entity_ref, p.name AS project_name,
                   round(sum(po.total_amount * fpo.rate_to_tnd)
                         / (p.contract_value * fp.rate_to_tnd), 3) AS ratio
            FROM erp.projects p
            JOIN erp.fx_rates fp ON fp.currency = p.currency
            JOIN erp.purchase_orders po USING (project_id)
            JOIN erp.fx_rates fpo ON fpo.currency = po.currency
            WHERE po.status NOT IN ('cancelled', 'draft')
            GROUP BY p.project_id, fp.rate_to_tnd
            HAVING sum(po.total_amount * fpo.rate_to_tnd)
                   / (p.contract_value * fp.rate_to_tnd) >= 1.00
        """,
        title_template="Project {entity_ref} OVER budget ({ratio:.0%})",
        detail_template="Procurement spend on {project_name} stands at "
                        "{ratio:.0%} of contract value. Immediate cost "
                        "review required.",
    ),
    Rule(
        code="PAYMENT_OVERDUE",
        name="Payment overdue 30+ days",
        severity="warning",
        description="An unpaid supplier invoice more than 30 days past due — "
                    "a supplier-relationship and legal risk.",
        sql="""
            SELECT pay.payment_ref AS entity_ref,
                   po.po_number, sup.name AS supplier_name,
                   pay.amount, pay.currency,
                   (CURRENT_DATE - pay.due_date) AS days_overdue
            FROM erp.payments pay
            JOIN erp.purchase_orders po USING (po_id)
            JOIN erp.suppliers sup ON sup.supplier_id = po.supplier_id
            WHERE pay.paid_date IS NULL
              AND pay.due_date < CURRENT_DATE - INTERVAL '30 days'
        """,
        title_template="{supplier_name}: {amount} {currency} overdue "
                       "{days_overdue} days",
        detail_template="Invoice {entity_ref} on {po_number} was due "
                        "{days_overdue} days ago and remains unpaid. "
                        "Settle or negotiate to protect supplier terms.",
    ),
    Rule(
        code="SUPPLIER_CONCENTRATION",
        name="Supplier concentration risk",
        severity="warning",
        description="One supplier holds more than 40% of the last 12 months' "
                    "PO spend (TND) — a single point of failure in sourcing.",
        sql="""
            WITH spend AS (
                SELECT po.supplier_id,
                       sum(po.total_amount * fx.rate_to_tnd) AS tnd
                FROM erp.purchase_orders po
                JOIN erp.fx_rates fx ON fx.currency = po.currency
                WHERE po.status NOT IN ('cancelled', 'draft')
                  AND po.order_date >= CURRENT_DATE - INTERVAL '365 days'
                GROUP BY po.supplier_id
            )
            SELECT sup.supplier_code AS entity_ref, sup.name AS supplier_name,
                   round(s.tnd / sum(s.tnd) OVER (), 3) AS share
            FROM spend s
            JOIN erp.suppliers sup USING (supplier_id)
            ORDER BY share DESC
        """,
        title_template="{supplier_name} holds {share:.0%} of 12-month spend",
        detail_template="{supplier_name} accounts for {share:.0%} of "
                        "procurement spend over the last 12 months — above "
                        "the 40% concentration threshold. Qualify an "
                        "alternative source.",
    ),
    Rule(
        code="ASSET_ATTENTION",
        name="Asset needs attention",
        severity="info",
        description="Company equipment recorded as damaged or under repair.",
        sql="""
            SELECT a.asset_code AS entity_ref, a.name AS asset_name,
                   a.category, a.condition
            FROM erp.assets a
            WHERE a.condition IN ('damaged', 'under_repair')
        """,
        title_template="{asset_name} is {condition}",
        detail_template="Asset {entity_ref} ({category}) is recorded as "
                        "{condition}. Schedule maintenance or replacement.",
    ),
]

# SUPPLIER_CONCENTRATION returns ALL suppliers with their share; the engine
# filters to breaches so the window function can see total spend:
CONCENTRATION_THRESHOLD = 0.40
