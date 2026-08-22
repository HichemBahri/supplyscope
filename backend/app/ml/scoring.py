"""Batch scoring: apply the active delivery_risk model to open shipments.

Writes a fresh snapshot into ml.delivery_risk in ONE statement, so the
reactivity triggers fire once and every chart built on predictions refreshes
live. Model outputs become ordinary, queryable, reactive data.
"""
from __future__ import annotations

import psycopg

from app.config import get_settings
from app.ml import features as F
from app.ml.registry import active_model, load_artifact

BANDS = ((0.7, "high"), (0.4, "medium"), (0.0, "low"))


def band(p: float) -> str:
    return next(b for threshold, b in BANDS if p >= threshold)


def score_open_orders() -> dict:
    model_row = active_model("delivery_risk")
    if model_row is None:
        raise RuntimeError("No active delivery_risk model — run training first")
    pipe = load_artifact(model_row)

    df = F.scoring_frame()
    if df.empty:
        n = 0
    else:
        proba = pipe.predict_proba(df[F.CATEGORICAL + F.NUMERIC + F.BOOLEAN])[:, 1]
        df = df.assign(probability=proba.round(4),
                       risk_band=[band(p) for p in proba])
        n = len(df)

    with psycopg.connect(get_settings().app_dsn, autocommit=True) as c:
        c.execute("TRUNCATE ml.delivery_risk RESTART IDENTITY")
        if n:
            rows = [(int(r.shipment_id), r.shipment_ref, int(r.po_id),
                     r.po_number, r.project_code, r.supplier_name,
                     r.promised_delivery_date, r.status,
                     float(r.probability), r.risk_band,
                     int(model_row["version"]))
                    for r in df.itertuples()]
            with c.cursor() as cur:
                cur.executemany(
                    "INSERT INTO ml.delivery_risk (shipment_id, shipment_ref,"
                    " po_id, po_number, project_code, supplier_name,"
                    " promised_delivery_date, status, probability, risk_band,"
                    " model_version) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    rows)
    return {"scored": n, "model_version": model_row["version"],
            "high": 0 if not n else int((df["risk_band"] == "high").sum()),
            "medium": 0 if not n else int((df["risk_band"] == "medium").sum())}


if __name__ == "__main__":
    print(score_open_orders())
