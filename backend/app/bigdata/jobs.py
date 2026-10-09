"""The feature-engineering job, twice (Phase 12.5).

ONE job specification, TWO engines. The job computes exactly the
supplier-history aggregations the operational system already relies on
(recommender criteria, ML features):

  supplier_stats:  per supplier — shipment count, on-time rate,
                   average delay in days (late shipments only counted
                   as their positive delay).
  price_index:     per (category, month) — MEDIAN unit_price/ref_unit_price
                   (median, not mean: robust to outliers, same choice as
                   the production forecaster).

The pandas implementation is the single-machine reference; the PySpark
implementation is semantically identical (exact `percentile`, not the
approximate sketch) so results are comparable to equality, and the
benchmark compares engines, not answers.
"""
from __future__ import annotations

import pandas as pd


# ------------------------------- pandas --------------------------------- #

def pandas_job(parquet_path: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = pd.read_parquet(parquet_path, columns=[
        "supplier_code", "category", "order_date", "promised_date",
        "actual_date", "unit_price", "ref_unit_price"])
    # parquet date32 arrives as python dates; normalize to datetime64
    for c in ("order_date", "promised_date", "actual_date"):
        df[c] = pd.to_datetime(df[c])
    late_days = (df["actual_date"] - df["promised_date"]).dt.days.clip(lower=0)
    df = df.assign(
        on_time=(df["actual_date"] <= df["promised_date"]).astype("int8"),
        delay_days=late_days,
        month=df["order_date"].dt.to_period("M").astype(str),
        price_ratio=df["unit_price"] / df["ref_unit_price"],
    )
    supplier_stats = (df.groupby("supplier_code", sort=True)
                        .agg(n_shipments=("on_time", "size"),
                             otd_rate=("on_time", "mean"),
                             avg_delay_days=("delay_days", "mean"))
                        .reset_index())
    price_index = (df.groupby(["category", "month"], sort=True)["price_ratio"]
                     .median().rename("median_ratio").reset_index())
    return supplier_stats, price_index


# ------------------------------- pyspark -------------------------------- #

def spark_job(spark, parquet_path: str):
    """Same job on Spark. Pass an existing SparkSession so session startup
    is measured separately from the job itself (honest benchmarking)."""
    from pyspark.sql import functions as F

    df = spark.read.parquet(parquet_path).select(
        "supplier_code", "category", "order_date", "promised_date",
        "actual_date", "unit_price", "ref_unit_price")
    df = (df
          .withColumn("on_time",
                      (F.col("actual_date") <= F.col("promised_date"))
                      .cast("int"))
          .withColumn("delay_days",
                      F.greatest(F.datediff("actual_date", "promised_date"),
                                 F.lit(0)))
          .withColumn("month", F.date_format("order_date", "yyyy-MM"))
          .withColumn("price_ratio",
                      F.col("unit_price") / F.col("ref_unit_price")))
    supplier_stats = (df.groupBy("supplier_code")
                        .agg(F.count("*").alias("n_shipments"),
                             F.avg("on_time").alias("otd_rate"),
                             F.avg("delay_days").alias("avg_delay_days"))
                        .orderBy("supplier_code"))
    price_index = (df.groupBy("category", "month")
                     .agg(F.expr("percentile(price_ratio, 0.5)")
                          .alias("median_ratio"))
                     .orderBy("category", "month"))
    # trigger full execution and bring results back (small outputs)
    return supplier_stats.toPandas(), price_index.toPandas()


def make_spark(app_name: str = "supplyscope-bench",
               driver_memory: str | None = None):
    """Local-mode session. In local mode the driver IS the executor, so
    `spark.driver.memory` is the whole heap the job can use; Spark's
    default of 1 GB is far below what a laptop offers and made the exact
    percentile fail at 30 M rows. Set SPARK_DRIVER_MEMORY (e.g. 8g) to
    size it to the machine; the benchmark records the value used."""
    import os

    from pyspark.sql import SparkSession
    mem = driver_memory or os.environ.get("SPARK_DRIVER_MEMORY", "6g")
    # the heap is a JVM launch option: pass it to spark-submit as well, so
    # it applies even if the gateway was configured before the builder
    os.environ.setdefault("PYSPARK_SUBMIT_ARGS",
                          f"--driver-memory {mem} pyspark-shell")
    return (SparkSession.builder.appName(app_name)
            .master("local[*]")
            .config("spark.driver.memory", mem)
            .config("spark.sql.shuffle.partitions", "8")
            .config("spark.ui.enabled", "false")
            .getOrCreate())
