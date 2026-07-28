"""Phase 7.2 — price-index forecasting: series integrity, backtest ladder,
storage, agent access."""
from __future__ import annotations

import psycopg
import pytest

from app.config import get_settings
from app.ml import features_forecast as FF
from app.ml.train_forecast import BACKTEST_H, HORIZON, train_forecast


def test_monthly_series_is_continuous_and_clean():
    s = FF.monthly_index("steel")
    assert len(s) >= 40
    months = s["month"].dt.to_period("M")
    assert (months.astype(int).diff().dropna() == 1).all(), "gap in series"
    assert s["price_index"].notna().all()
    assert s["price_index"].between(0.3, 4.0).all()


def test_supervised_frame_has_no_leakage_columns():
    sup = FF.supervised(FF.monthly_index("steel"))
    # every lag must equal the series value k steps earlier
    for k in (1, 2, 3):
        assert (sup[f"lag{k}"].to_numpy()[k:]
                == sup["price_index"].to_numpy()[:-k]).all()


def test_train_forecast_end_to_end():
    entry = train_forecast(verbose=False)
    assert entry["model_name"] == "price_forecast"
    comp = entry["comparison"]
    assert set(comp) == set(FF.CATEGORIES)
    for cat in FF.CATEGORIES:
        assert set(comp[cat]) == {"naive", "linear_trend", "random_forest", "mlp"}
        for m in comp[cat].values():
            assert m["mae"] < 0.5
    with psycopg.connect(get_settings().app_dsn) as c:
        hist = c.execute("SELECT count(*) FROM ml.price_forecast "
                         "WHERE kind='history'").fetchone()[0]
        fc = c.execute("SELECT count(*) FROM ml.price_forecast "
                       "WHERE kind='forecast'").fetchone()[0]
    assert fc == HORIZON * len(FF.CATEGORIES)
    assert hist > 150


def test_agent_reader_can_select_forecasts():
    with psycopg.connect(get_settings().agent_dsn) as c:
        rows = c.execute("SELECT category, price_index FROM ml.price_forecast "
                         "WHERE kind='forecast' LIMIT 3").fetchall()
        assert rows
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("DELETE FROM ml.price_forecast")
