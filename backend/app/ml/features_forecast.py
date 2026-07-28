"""Monthly price-index series per material category.

Index = median(unit_price / ref_unit_price) over the month's PO lines —
median, not mean, because the deliberately-injected overbudget story (S4)
scales one project's unit prices and would pollute a mean. Missing months
(no purchases in that category) are linearly interpolated and flagged.
"""
from __future__ import annotations

import warnings

import pandas as pd
import psycopg

from app.config import get_settings

CATEGORIES = ["steel", "safety", "instrumentation", "electrical"]
MIN_MONTHS = 24            # refuse to model sparser categories

_SQL = """
SELECT date_trunc('month', po.order_date)::date AS month,
       percentile_cont(0.5) WITHIN GROUP
           (ORDER BY pl.unit_price / m.ref_unit_price) AS price_index,
       count(*) AS n_lines
FROM erp.po_lines pl
JOIN erp.materials m USING (material_id)
JOIN erp.purchase_orders po USING (po_id)
WHERE m.category = %s
GROUP BY 1 ORDER BY 1
"""


def monthly_index(category: str) -> pd.DataFrame:
    """Continuous monthly series: month, price_index, observed."""
    with psycopg.connect(get_settings().app_dsn) as conn:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*SQLAlchemy.*")
            df = pd.read_sql_query(_SQL, conn, params=(category,))  # type: ignore[arg-type]
    if len(df) < MIN_MONTHS:
        raise ValueError(f"{category}: only {len(df)} observed months")
    df["month"] = pd.to_datetime(df["month"])
    full = pd.DataFrame({"month": pd.date_range(df["month"].min(),
                                                df["month"].max(), freq="MS")})
    out = full.merge(df, on="month", how="left")
    out["observed"] = out["price_index"].notna()
    out["price_index"] = out["price_index"].astype(float).interpolate("linear")
    out["n_lines"] = out["n_lines"].fillna(0).astype(int)
    return out


LAGS = 3


def supervised(series: pd.DataFrame) -> pd.DataFrame:
    """Lag features + linear time step t for regression models."""
    s = series.copy()
    for k in range(1, LAGS + 1):
        s[f"lag{k}"] = s["price_index"].shift(k)
    s["roll3"] = s["price_index"].shift(1).rolling(3).mean()
    s["t"] = range(len(s))
    return s.dropna().reset_index(drop=True)
