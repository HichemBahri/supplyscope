"""Phase 12.5 — scale pipeline: the two engines must agree exactly.
Skips cleanly when pyspark/Java are not installed (optional dependency
group `bigdata`), so the core suite never requires a JVM."""
from __future__ import annotations

import pandas as pd
import pytest

pyspark = pytest.importorskip("pyspark")


@pytest.fixture(scope="module")
def spark():
    from app.bigdata.jobs import make_spark
    try:
        s = make_spark("parity-test")
    except Exception as e:                              # noqa: BLE001
        pytest.skip(f"no usable JVM: {e}")
    yield s
    s.stop()


def test_pandas_and_spark_agree_exactly(tmp_path_factory, spark):
    from app.bigdata.jobs import pandas_job, spark_job
    from data_generator.scale import generate
    pq = str(tmp_path_factory.mktemp("scale") / "s.parquet")
    generate(50_000, pq, seed=7)
    p_sup, p_idx = pandas_job(pq)
    s_sup, s_idx = spark_job(spark, pq)
    # supplier stats: identical to numerical tolerance
    m = p_sup.merge(s_sup, on="supplier_code", suffixes=("_p", "_s"))
    assert len(m) == len(p_sup) > 10
    assert (m["n_shipments_p"] == m["n_shipments_s"]).all()
    assert (m["otd_rate_p"] - m["otd_rate_s"]).abs().max() < 1e-9
    assert (m["avg_delay_days_p"] - m["avg_delay_days_s"]).abs().max() < 1e-9
    # price index: exact percentile in both engines
    i = p_idx.merge(s_idx, on=["category", "month"], suffixes=("_p", "_s"))
    assert len(i) == len(p_idx)
    assert (i["median_ratio_p"] - i["median_ratio_s"]).abs().max() < 1e-9


def test_scale_generation_is_deterministic(tmp_path_factory):
    from data_generator.scale import generate
    from app.bigdata.jobs import pandas_job
    d = tmp_path_factory.mktemp("det")
    generate(20_000, str(d / "a.parquet"), seed=11)
    generate(20_000, str(d / "b.parquet"), seed=11)
    a_sup, _ = pandas_job(str(d / "a.parquet"))
    b_sup, _ = pandas_job(str(d / "b.parquet"))
    pd.testing.assert_frame_equal(a_sup, b_sup)
