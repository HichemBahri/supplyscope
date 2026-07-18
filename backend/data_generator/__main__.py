"""CLI entrypoint.

Usage:
    python -m data_generator [--seed 42] [--dsn postgresql://...] [--no-reset]
Environment: DATABASE_URL or POSTGRES_* variables (see db_writer.default_dsn).
"""
from __future__ import annotations

import argparse
import sys
import time

from . import config as C
from .db_writer import default_dsn, load
from .simulator import Simulator
from .validate import run_validation


def main() -> int:
    parser = argparse.ArgumentParser(prog="data_generator",
                                     description="SupplyScope synthetic ERP data generator")
    parser.add_argument("--seed", type=int, default=C.DEFAULT_SEED)
    parser.add_argument("--dsn", default=None, help="PostgreSQL DSN (default: env)")
    parser.add_argument("--no-reset", action="store_true",
                        help="do not TRUNCATE erp tables before loading")
    parser.add_argument("--skip-validation", action="store_true")
    args = parser.parse_args()

    dsn = args.dsn or default_dsn()
    print(f"Simulating company history {C.SIM_START} → {C.SIM_NOW} (seed={args.seed})...")
    t0 = time.perf_counter()
    sim = Simulator(seed=args.seed)
    rows = sim.run()
    t1 = time.perf_counter()
    total = sum(len(v) for v in rows.values())
    print(f"Generated {total} rows in {t1 - t0:.2f}s. Loading into PostgreSQL...")
    counts = load(rows, dsn=dsn, reset=not args.no_reset)
    t2 = time.perf_counter()
    print(f"Loaded in {t2 - t1:.2f}s.")
    if sim._overbudget_project_id:
        code = sim.project_info[sim._overbudget_project_id]["code"]
        print(f"Overbudget story applied to project {code}.")
    if not args.skip_validation:
        ok = run_validation(dsn)
        print("\nValidation:", "ALL CHECKS PASSED ✅" if ok else "FAILURES DETECTED ❌")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
