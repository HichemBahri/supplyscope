"""pandas-vs-Spark benchmark harness (Phase 12.5).

For each dataset size on a geometric ladder: generate (once, cached),
run the SAME feature job on pandas and on Spark (local[*]), record wall
times, then emit a CSV and a log-log crossover chart.

Methodology notes (thesis-facing):
- The Spark SESSION is created once and its startup time reported
  separately: session startup is a fixed cost paid once per application,
  not per job, so folding it into every measurement would bias against
  Spark. Both numbers are reported; the reader can judge.
- Each (engine, size) measurement is repeated REPS times; the MINIMUM is
  kept (standard micro-benchmark practice: the min is the least-noise
  estimate of true cost on a shared machine).
- Sizes default to a dense geometric ladder so the crossover point is
  localized, per the experimental goal.

Usage:
    python -m scripts.bench_scale                       # default ladder
    python -m scripts.bench_scale --sizes 1e4 1e5 1e6 3e6 --reps 3
"""
from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

DEFAULT_SIZES = [10_000, 30_000, 100_000, 300_000, 1_000_000,
                 3_000_000, 10_000_000, 30_000_000]


def bench(sizes: list[int], reps: int, workdir: Path, out_prefix: Path):
    from app.bigdata.jobs import make_spark, pandas_job, spark_job
    from data_generator.scale import generate

    workdir.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    spark = make_spark()
    spark_startup_s = time.perf_counter() - t0

    results = []
    for n in sizes:
        pq_path = workdir / f"scale_{n}.parquet"
        if not pq_path.exists():
            info = generate(n, str(pq_path))
            print(f"generated {n:>12,} rows in {info['gen_seconds']}s")
        pd_times, sp_times = [], []
        for _ in range(reps):
            t = time.perf_counter()
            pandas_job(str(pq_path))
            pd_times.append(time.perf_counter() - t)
            t = time.perf_counter()
            spark_job(spark, str(pq_path))
            sp_times.append(time.perf_counter() - t)
        row = {"rows": n,
               "pandas_s": round(min(pd_times), 3),
               "spark_s": round(min(sp_times), 3)}
        results.append(row)
        print(f"{n:>12,} rows   pandas {row['pandas_s']:>8.3f}s   "
              f"spark {row['spark_s']:>8.3f}s")
    spark.stop()

    csv_path = out_prefix.with_suffix(".csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["rows", "pandas_s", "spark_s"])
        w.writeheader()
        w.writerows(results)

    # crossover chart
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    xs = [r["rows"] for r in results]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(xs, [r["pandas_s"] for r in results], "o-", color="#155E97",
            label="pandas (single core)")
    ax.plot(xs, [r["spark_s"] for r in results], "s-", color="#B23A48",
            label="PySpark local[*]")
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("dataset size (rows, log)")
    ax.set_ylabel("feature-job wall time (s, log)")
    ax.set_title("Feature-engineering job: pandas vs Spark\n"
                 f"(min of {reps} runs; Spark session startup "
                 f"{spark_startup_s:.1f}s excluded, reported separately)")
    ax.grid(True, which="both", alpha=0.3)
    # mark the crossover if one exists
    cross = next((i for i in range(1, len(results))
                  if (results[i - 1]["pandas_s"] < results[i - 1]["spark_s"])
                  and (results[i]["pandas_s"] >= results[i]["spark_s"])), None)
    if cross is not None:
        ax.axvline(xs[cross], color="#F2620F", linestyle="--", alpha=0.8)
        ax.annotate(f"crossover ≈ {xs[cross]:,} rows",
                    xy=(xs[cross], results[cross]["spark_s"]),
                    xytext=(10, 12), textcoords="offset points",
                    color="#F2620F", fontweight="bold")
    ax.legend()
    png_path = out_prefix.with_suffix(".png")
    fig.tight_layout(); fig.savefig(png_path, dpi=150)
    print(f"\nwrote {csv_path} and {png_path} "
          f"(spark session startup: {spark_startup_s:.1f}s)")
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", nargs="*", type=float, default=None)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--workdir", default="/tmp/supplyscope_scale")
    ap.add_argument("--out", default="bench_scale")
    args = ap.parse_args()
    sizes = ([int(s) for s in args.sizes] if args.sizes else DEFAULT_SIZES)
    bench(sizes, args.reps, Path(args.workdir), Path(args.out))
