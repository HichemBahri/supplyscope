"""Feature engineering for the delivery-risk classifier.

Grain: one row per SHIPMENT. Every feature is knowable at ORDER TIME —
supplier history is computed strictly BEFORE each shipment's order date
(leakage discipline: the model must never peek at the future it predicts).
"""
from __future__ import annotations

import warnings

import pandas as pd
import psycopg

from app.config import get_settings

CATEGORICAL = ["transport_mode", "incoterm", "supplier_country",
               "destination_country", "material_category"]
NUMERIC = ["promised_lead_days", "amount_tnd", "supplier_prior_shipments",
           "supplier_prior_late_rate", "promised_month"]
BOOLEAN = ["requires_customs", "is_import"]
LABEL = "is_late"

_BASE_SQL = """
SELECT
  s.shipment_id,
  s.shipment_ref,
  po.po_id,
  po.po_number,
  po.order_date,
  po.promised_delivery_date,
  s.actual_delivery_date,
  s.status,
  pr.project_code,
  sup.name AS supplier_name,
  -- ------------------------------------------------ features (order-time)
  (po.promised_delivery_date - po.order_date)          AS promised_lead_days,
  round(po.total_amount * fx.rate_to_tnd, 2)           AS amount_tnd,
  EXTRACT(month FROM po.promised_delivery_date)::int   AS promised_month,
  s.transport_mode,
  po.incoterm,
  s.requires_customs,
  sup.country                                          AS supplier_country,
  (sup.country <> 'Tunisie')                           AS is_import,
  dst.country                                          AS destination_country,
  COALESCE((
      SELECT m.category
      FROM erp.shipment_lines sl
      JOIN erp.po_lines pl USING (po_line_id)
      JOIN erp.materials m USING (material_id)
      WHERE sl.shipment_id = s.shipment_id
      GROUP BY m.category
      ORDER BY sum(sl.quantity * pl.unit_price) DESC
      LIMIT 1), 'unknown')                             AS material_category,
  -- supplier reliability BEFORE this order (strict inequality = no leakage)
  (SELECT count(*) FROM erp.shipments s2
     JOIN erp.purchase_orders po2 USING (po_id)
     WHERE po2.supplier_id = po.supplier_id
       AND s2.actual_delivery_date IS NOT NULL
       AND s2.actual_delivery_date < po.order_date)    AS supplier_prior_shipments,
  (SELECT COALESCE(round(avg(
        (s2.actual_delivery_date > po2.promised_delivery_date)::int)::numeric, 4),
        -1)
     FROM erp.shipments s2
     JOIN erp.purchase_orders po2 USING (po_id)
     WHERE po2.supplier_id = po.supplier_id
       AND s2.actual_delivery_date IS NOT NULL
       AND s2.actual_delivery_date < po.order_date)    AS supplier_prior_late_rate,
  (s.actual_delivery_date > po.promised_delivery_date) AS is_late
FROM erp.shipments s
JOIN erp.purchase_orders po USING (po_id)
JOIN erp.projects pr USING (project_id)
JOIN erp.suppliers sup ON sup.supplier_id = po.supplier_id
JOIN erp.sites dst ON dst.site_id = s.destination_site_id
JOIN erp.fx_rates fx ON fx.currency = po.currency
WHERE {where}
"""


def _frame(where: str) -> pd.DataFrame:
    with psycopg.connect(get_settings().app_dsn) as conn:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*SQLAlchemy.*")
            df = pd.read_sql_query(_BASE_SQL.format(where=where), conn)  # type: ignore[arg-type]
    # cold-start suppliers: no history yet -> sentinel -1 kept as numeric signal
    df["supplier_prior_late_rate"] = df["supplier_prior_late_rate"].astype(float)
    df["promised_lead_days"] = df["promised_lead_days"].astype(int)
    df["amount_tnd"] = df["amount_tnd"].astype(float)
    return df


def training_frame() -> pd.DataFrame:
    """Delivered shipments only (label observable)."""
    df = _frame("s.actual_delivery_date IS NOT NULL")
    df[LABEL] = df[LABEL].astype(bool)
    return df


def scoring_frame() -> pd.DataFrame:
    """Open shipments: planned / in transit / customs hold — label unknown."""
    return _frame("s.actual_delivery_date IS NULL AND s.status <> 'cancelled'")
