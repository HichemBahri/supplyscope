"""Live operations simulator — the demo's heartbeat.

Periodically performs realistic ERP write operations (as the admin identity,
never agent_reader): new purchase orders on active projects, shipment
deliveries with goods receipts, settlement of overdue payments. Each write
fires the reactivity chain, so subscribed dashboards update in front of the
audience.

Run from backend/ (module form):
    uv run python -m scripts.simulate_activity --interval 5
    uv run python -m scripts.simulate_activity --iterations 3   # finite run
"""
from __future__ import annotations

import argparse
import datetime as dt
import random
import time
import uuid

import psycopg
from psycopg.rows import dict_row

from app.config import get_settings


def _conn() -> psycopg.Connection:
    return psycopg.connect(get_settings().app_dsn, row_factory=dict_row,
                           autocommit=True)


def op_new_po(c: psycopg.Connection, rng: random.Random) -> str | None:
    proj = c.execute(
        "SELECT project_id, project_code FROM erp.projects "
        "WHERE status='active' AND scope_procurement ORDER BY random() LIMIT 1"
    ).fetchone()
    sup = c.execute(
        "SELECT supplier_id, name FROM erp.suppliers WHERE is_active "
        "ORDER BY random() LIMIT 1").fetchone()
    mats = c.execute(
        "SELECT material_id, ref_unit_price FROM erp.materials "
        "ORDER BY random() LIMIT %s", (rng.randint(1, 2),)).fetchall()
    if not (proj and sup and mats):
        return None
    today = dt.date.today()
    po_number = f"PO-LIVE-{uuid.uuid4().hex[:8].upper()}"
    po = c.execute(
        "INSERT INTO erp.purchase_orders "
        "(po_number, project_id, supplier_id, order_date, promised_delivery_date,"
        " incoterm, currency, status) "
        "VALUES (%s, %s, %s, %s, %s, 'DAP', 'TND', 'issued') RETURNING po_id",
        (po_number, proj["project_id"], sup["supplier_id"],
         today, today + dt.timedelta(days=rng.randint(10, 45)))).fetchone()
    total = 0.0
    for m in mats:
        qty = rng.randint(5, 80)
        price = round(float(m["ref_unit_price"]) * rng.uniform(0.95, 1.15), 2)
        c.execute("INSERT INTO erp.po_lines (po_id, material_id, quantity, unit_price) "
                  "VALUES (%s, %s, %s, %s)",
                  (po["po_id"], m["material_id"], qty, price))
        total += qty * price
    c.execute("UPDATE erp.purchase_orders SET total_amount=%s WHERE po_id=%s",
              (round(total, 2), po["po_id"]))
    return f"new PO {po_number} for {proj['project_code']} @ {sup['name']} ({total:,.0f} TND)"


def op_deliver_shipment(c: psycopg.Connection, rng: random.Random) -> str | None:
    shp = c.execute(
        "SELECT shipment_id, shipment_ref, destination_site_id FROM erp.shipments "
        "WHERE status IN ('preparing','in_transit','customs_hold') "
        "ORDER BY random() LIMIT 1").fetchone()
    if not shp:
        return None
    today = dt.date.today()
    c.execute("UPDATE erp.shipments SET status='delivered', "
              "actual_delivery_date=%s, "
              "customs_clearance_date=COALESCE(customs_clearance_date, "
              "  CASE WHEN requires_customs THEN %s END) "
              "WHERE shipment_id=%s", (today, today, shp["shipment_id"]))
    c.execute("INSERT INTO erp.goods_receipts (gr_ref, shipment_id, receipt_date,"
              " site_id, qc_status) VALUES (%s, %s, %s, %s, 'accepted') "
              "ON CONFLICT (shipment_id) DO NOTHING",
              (f"GRN-LIVE-{uuid.uuid4().hex[:8].upper()}", shp["shipment_id"],
               today, shp["destination_site_id"]))
    return f"shipment {shp['shipment_ref']} delivered + GRN"


def op_settle_payment(c: psycopg.Connection, rng: random.Random) -> str | None:
    pay = c.execute(
        "SELECT payment_id, payment_ref, amount, currency FROM erp.payments "
        "WHERE status='overdue' ORDER BY random() LIMIT 1").fetchone()
    if not pay:
        return None
    c.execute("UPDATE erp.payments SET status='paid', paid_date=%s "
              "WHERE payment_id=%s", (dt.date.today(), pay["payment_id"]))
    return f"payment {pay['payment_ref']} settled ({pay['amount']} {pay['currency']})"


OPS = [op_new_po, op_deliver_shipment, op_settle_payment]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--interval", type=float, default=5.0,
                   help="seconds between operations")
    p.add_argument("--iterations", type=int, default=0,
                   help="stop after N operations (0 = run forever)")
    p.add_argument("--seed", type=int, default=None)
    args = p.parse_args()
    rng = random.Random(args.seed)

    print(f"Live ERP feed — one operation every {args.interval}s. Ctrl+C to stop.")
    n = 0
    with _conn() as c:
        while True:
            op = rng.choice(OPS)
            msg = op(c, rng) or "(nothing eligible for this op, skipping)"
            n += 1
            print(f"[{dt.datetime.now():%H:%M:%S}] {msg}")
            if args.iterations and n >= args.iterations:
                break
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
