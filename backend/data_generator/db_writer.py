"""Bulk loader: writes the simulator's row store into PostgreSQL.

Foreign keys are positional: tables are TRUNCATEd with RESTART IDENTITY and
rows inserted in generation order, so row N receives identity N — the same
ids the simulator used when wiring references.
"""
from __future__ import annotations

import os

import psycopg

# Insertion order respects FK dependencies. Column lists exclude identities
# and DB-maintained columns (created_at/updated_at/line_total defaults).
TABLES: dict[str, list[str]] = {
    "clients": ["client_code", "name", "country", "sector", "is_active"],
    "suppliers": ["supplier_code", "name", "country", "city",
                  "payment_terms_days", "preferred_payment_method", "is_active"],
    "materials": ["material_code", "name", "category", "unit", "ref_unit_price", "currency"],
    "sites": ["site_code", "name", "country", "region", "site_type"],
    "tenders": ["tender_ref", "client_id", "title", "scope_engineering",
                "scope_procurement", "scope_construction", "issue_date",
                "submission_deadline", "estimated_value", "currency", "status"],
    "proposals": ["tender_id", "submitted_date", "proposed_value", "currency",
                  "status", "decision_date"],
    "projects": ["project_code", "name", "client_id", "site_id", "proposal_id",
                 "scope_engineering", "scope_procurement", "scope_construction",
                 "contract_value", "currency", "start_date", "planned_end_date",
                 "actual_end_date", "status"],
    "boqs": ["boq_ref", "project_id", "discipline", "request_date",
             "needed_by_date", "engineering_validated", "validation_date", "status"],
    "boq_lines": ["boq_id", "material_id", "quantity"],
    "rfqs": ["rfq_ref", "boq_id", "issue_date", "due_date", "status"],
    "supplier_quotations": ["rfq_id", "supplier_id", "quote_date", "quoted_total",
                            "currency", "lead_time_days", "tbe_score", "cbe_score", "status"],
    "purchase_orders": ["po_number", "project_id", "supplier_id", "rfq_id",
                        "order_date", "promised_delivery_date", "incoterm",
                        "currency", "total_amount", "status"],
    "po_lines": ["po_id", "material_id", "quantity", "unit_price"],
    "payments": ["payment_ref", "po_id", "amount", "currency", "method",
                 "due_date", "paid_date", "status"],
    "shipments": ["shipment_ref", "po_id", "destination_site_id", "carrier",
                  "transport_mode", "ship_date", "eta_date", "actual_delivery_date",
                  "requires_customs", "customs_entry_date", "customs_clearance_date",
                  "freight_cost", "currency", "status"],
    "shipment_lines": ["shipment_id", "po_line_id", "quantity"],
    "goods_receipts": ["gr_ref", "shipment_id", "receipt_date", "site_id",
                       "qc_status", "remarks"],
    "assets": ["asset_code", "name", "category", "acquisition_date",
               "acquisition_cost", "currency", "condition", "status"],
    "asset_assignments": ["asset_id", "project_id", "start_date", "end_date"],
    "maintenance_events": ["asset_id", "event_type", "event_date", "cost",
                           "currency", "downtime_days", "description"],
}


def default_dsn() -> str:
    if url := os.environ.get("DATABASE_URL"):
        return url
    user = os.environ.get("POSTGRES_USER", "supplyscope")
    pwd = os.environ.get("POSTGRES_PASSWORD", "")
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "supplyscope")
    auth = f"{user}:{pwd}@" if pwd else f"{user}@"
    return f"postgresql://{auth}{host}:{port}/{db}"


def load(rows: dict[str, list[tuple]], dsn: str | None = None, reset: bool = True) -> dict[str, int]:
    """Load all rows in one transaction. Returns per-table row counts."""
    counts: dict[str, int] = {}
    with psycopg.connect(dsn or default_dsn()) as conn:
        with conn.cursor() as cur:
            if reset:
                all_tables = ", ".join(f"erp.{t}" for t in TABLES)
                cur.execute(f"TRUNCATE {all_tables} RESTART IDENTITY CASCADE")
            for table, cols in TABLES.items():
                data = rows.get(table, [])
                counts[table] = len(data)
                if not data:
                    continue
                placeholders = ", ".join(["%s"] * len(cols))
                sql = (f"INSERT INTO erp.{table} ({', '.join(cols)}) "
                       f"VALUES ({placeholders})")
                cur.executemany(sql, data)
        conn.commit()
    return counts
