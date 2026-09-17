"""Scale-mode data generator (Phase 12.5 — the Big Data laboratory).

Produces an ARBITRARILY LARGE synthetic shipment-events dataset in Parquet,
for benchmarking the feature-engineering pipeline at ERP scale. This is a
SEPARATE dataset from the frozen seed-42 world: it never touches PostgreSQL,
never consumes the operational generator's RNG, and exists purely so the
pandas-vs-Spark comparison is run on data with realistic statistical
structure (supplier reliability spectrum, category price levels, seasonal
volume) rather than uniform noise.

Design notes for the thesis:
- Generation is fully VECTORIZED with NumPy (millions of rows per second)
  and written in CHUNKS through a single pyarrow ParquetWriter, so memory
  stays flat regardless of target size.
- The lateness process mirrors the operational world's logistic form
  (supplier log-odds + customs + mode effects) so aggregates computed at
  scale are qualitatively comparable to the production features.
- Deterministic per (seed, rows): the same command always yields the same
  file, byte-for-byte comparable aggregates.

Usage:
    python -m data_generator.scale --rows 5_000_000 --out /tmp/scale.parquet
"""
from __future__ import annotations

import argparse
import time

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

CHUNK = 1_000_000
N_SUPPLIERS = 40
CATEGORIES = ["steel", "electrical", "instrumentation", "safety", "piping",
              "valves", "mechanical_equipment", "welding_consumables"]
CAT_REF_PRICE = np.array([850.0, 120.0, 2400.0, 65.0, 310.0, 540.0,
                          15500.0, 22.0])
COUNTRIES = ["Tunisie", "Libye", "Italie", "France", "Turquie", "Chine"]
COUNTRY_P = [0.35, 0.10, 0.15, 0.12, 0.13, 0.15]
DEST = ["Tunisie", "Libye"]
MODES = ["road", "sea", "air"]
MODE_BETA = {"road": 0.0, "sea": 0.8, "air": -1.1}
EPOCH = np.datetime64("2021-07-01")
DAYS_SPAN = 5 * 365


def _suppliers(rng: np.random.Generator):
    """A reliability spectrum: mostly decent, a tail of chronic offenders."""
    otd = rng.beta(8, 2, N_SUPPLIERS)
    otd[: max(2, N_SUPPLIERS // 12)] = rng.uniform(0.15, 0.45,
                                                   max(2, N_SUPPLIERS // 12))
    country = rng.choice(len(COUNTRIES), N_SUPPLIERS, p=COUNTRY_P)
    price_factor = rng.normal(1.0, 0.08, N_SUPPLIERS).clip(0.8, 1.3)
    return otd, country, price_factor


def generate(rows: int, out: str, seed: int = 4242) -> dict:
    rng = np.random.default_rng(seed)
    sup_otd, sup_country, sup_pf = _suppliers(rng)
    writer = None
    t0 = time.perf_counter()
    written = 0
    while written < rows:
        n = min(CHUNK, rows - written)
        sup = rng.integers(0, N_SUPPLIERS, n)
        cat = rng.integers(0, len(CATEGORIES), n)
        dest = rng.integers(0, len(DEST), n)
        mode = rng.integers(0, len(MODES), n)
        order_day = rng.integers(0, DAYS_SPAN, n)
        lead = (rng.gamma(4.0, 8.0, n) + 5).astype(np.int32)

        # logistic lateness: supplier log-odds + customs + destination + mode
        base = np.clip(1.0 - sup_otd[sup], 0.02, 0.98)
        a = 1.6 * np.log(base / (1 - base)) - 0.9
        is_import = sup_country[sup] != np.where(dest == 0, 0, 1)
        a = a + 1.2 * is_import
        a = a + 0.7 * (dest == 1)                      # the fragile corridor
        a = a + np.take(np.array([MODE_BETA[m] for m in MODES]), mode)
        p_late = 1.0 / (1.0 + np.exp(-a))
        late = rng.random(n) < p_late
        delay = np.where(late, rng.gamma(2.0, 6.0, n) + 1, 0).astype(np.int32)
        early = np.where(~late, rng.integers(0, 3, n), 0).astype(np.int32)

        ref_price = CAT_REF_PRICE[cat]
        drift = 1.0 + 0.06 * (order_day / 365.0)       # slow escalation
        unit_price = (ref_price * drift * sup_pf[sup]
                      * rng.normal(1.0, 0.05, n)).round(2)

        order_date = EPOCH + order_day.astype("timedelta64[D]")
        promised = order_date + lead.astype("timedelta64[D]")
        actual = promised + delay.astype("timedelta64[D]") \
            - early.astype("timedelta64[D]")

        table = pa.table({
            "shipment_id": np.arange(written, written + n, dtype=np.int64),
            "supplier_code": np.char.add("SUPS-",
                                         np.char.zfill(sup.astype(str), 3)),
            "supplier_country": np.take(np.array(COUNTRIES), sup_country[sup]),
            "category": np.take(np.array(CATEGORIES), cat),
            "destination_country": np.take(np.array(DEST), dest),
            "transport_mode": np.take(np.array(MODES), mode),
            "order_date": order_date,
            "promised_date": promised,
            "actual_date": actual,
            "quantity": rng.integers(1, 500, n),
            "unit_price": unit_price,
            "ref_unit_price": ref_price * drift,
        })
        if writer is None:
            writer = pq.ParquetWriter(out, table.schema)
        writer.write_table(table)
        written += n
    if writer:
        writer.close()
    secs = time.perf_counter() - t0
    return {"rows": rows, "out": out, "gen_seconds": round(secs, 2)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=4242)
    args = ap.parse_args()
    print(generate(args.rows, args.out, args.seed))
