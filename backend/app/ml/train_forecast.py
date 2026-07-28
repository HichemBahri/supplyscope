"""Price-index forecasting: expanding-window backtest ladder per category.

Methodology:
1. EXPANDING-WINDOW BACKTEST — for each of the last BACKTEST_H months,
   models are fit on all data strictly before that month and predict it.
   The only honest evaluation for time series; random CV leaks the future.
2. LADDER — naive last-value (the baseline every forecaster must beat),
   linear trend, random forest on lags, MLPRegressor on lags+trend.
3. Winner per category (lowest backtest MAE) is refit on the full history
   and rolled forward RECURSIVELY for HORIZON months.
4. History + forecast land in ml.price_forecast: queryable by the agent,
   reactive like every other table.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import psycopg
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error
from sklearn.neural_network import MLPRegressor

from app.config import get_settings
from app.ml import features_forecast as FF
from app.ml.registry import register_model
from app.ml.train_risk import ARTIFACT_DIR

BACKTEST_H = 9
HORIZON = 6
FEATS = ["lag1", "lag2", "lag3", "roll3", "t"]

_DDL = """
CREATE TABLE IF NOT EXISTS ml.price_forecast (
    row_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    category text NOT NULL,
    month date NOT NULL,
    price_index numeric(8,4) NOT NULL,
    kind text NOT NULL CHECK (kind IN ('history','forecast')),
    model_version integer,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (category, month, kind)
);
COMMENT ON TABLE ml.price_forecast IS
 'Monthly material price index (median unit_price/ref_unit_price) per category: kind=history are observed values, kind=forecast are model projections for future months. Produced by the price_forecast model.';
GRANT SELECT ON ml.price_forecast TO agent_reader;
DO $$ BEGIN
  CREATE TRIGGER trg_notify_change
  AFTER INSERT OR UPDATE OR DELETE ON ml.price_forecast
  FOR EACH STATEMENT EXECUTE FUNCTION erp.notify_data_change();
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
"""


def _models():
    return {
        "naive": None,                              # prediction = lag1
        "linear_trend": LinearRegression(),
        "random_forest": RandomForestRegressor(
            n_estimators=150, max_depth=5, min_samples_leaf=3, random_state=42),
        "mlp": MLPRegressor(hidden_layer_sizes=(8,), solver="lbfgs",
                            alpha=1.0, max_iter=5000, random_state=42),
    }


def _backtest(sup: pd.DataFrame) -> dict[str, dict]:
    """Expanding-window one-step-ahead backtest over the last BACKTEST_H rows."""
    res: dict[str, list[tuple[float, float]]] = {m: [] for m in _models()}
    start = len(sup) - BACKTEST_H
    for i in range(start, len(sup)):
        fit, target = sup.iloc[:i], sup.iloc[i]
        y_true = float(target["price_index"])
        for name, model in _models().items():
            if name == "naive":
                y_hat = float(target["lag1"])
            else:
                model.fit(fit[FEATS], fit["price_index"])
                y_hat = float(model.predict(target[FEATS].to_frame().T)[0])
            res[name].append((y_true, y_hat))
    out = {}
    for name, pairs in res.items():
        yt, yh = np.array([p[0] for p in pairs]), np.array([p[1] for p in pairs])
        out[name] = {
            "mae": round(float(mean_absolute_error(yt, yh)), 4),
            "rmse": round(float(np.sqrt(((yt - yh) ** 2).mean())), 4),
            "mape_pct": round(float((np.abs((yt - yh) / yt)).mean() * 100), 2),
        }
    return out


def _recursive_forecast(series: pd.DataFrame, winner: str) -> list[tuple]:
    """Refit winner on full history; roll HORIZON months forward."""
    hist = list(series["price_index"].astype(float))
    sup = FF.supervised(series)
    model = _models()[winner]
    if model is not None:
        model.fit(sup[FEATS], sup["price_index"])
    t_next = len(series)
    months = pd.date_range(series["month"].iloc[-1], periods=HORIZON + 1,
                           freq="MS")[1:]
    rows = []
    for step, month in enumerate(months):
        lag1, lag2, lag3 = hist[-1], hist[-2], hist[-3]
        roll3 = float(np.mean(hist[-3:]))
        if winner == "naive":
            y = lag1
        else:
            X = pd.DataFrame([{"lag1": lag1, "lag2": lag2, "lag3": lag3,
                               "roll3": roll3, "t": t_next + step}])
            y = float(model.predict(X)[0])
        hist.append(y)
        rows.append((month.date(), round(y, 4)))
    return rows


def train_forecast(verbose: bool = True) -> dict:
    comparison: dict[str, dict] = {}
    winners: dict[str, str] = {}
    forecasts: dict[str, list[tuple]] = {}
    histories: dict[str, pd.DataFrame] = {}
    for cat in FF.CATEGORIES:
        series = FF.monthly_index(cat)
        sup = FF.supervised(series)
        metrics = _backtest(sup)
        winner = min(metrics, key=lambda m: metrics[m]["mae"])
        comparison[cat] = metrics
        winners[cat] = winner
        forecasts[cat] = _recursive_forecast(series, winner)
        histories[cat] = series
        if verbose:
            row = "  ".join(f"{m} {metrics[m]['mae']:.3f}" for m in metrics)
            print(f"  {cat:16s} MAE: {row}  -> {winner}")

    steel_winner = winners["steel"]
    entry = register_model(
        model_name="price_forecast", task="regression",
        algo=f"per-category winners: {winners}",
        split_date=None, train_rows=sum(len(h) for h in histories.values()),
        test_rows=BACKTEST_H * len(FF.CATEGORIES),
        metrics=comparison["steel"][steel_winner],
        comparison=comparison,
        feature_importance=[],
        artifact_saver=lambda path: path.write_text(repr(winners)),
        artifact_dir=ARTIFACT_DIR)

    with psycopg.connect(get_settings().app_dsn, autocommit=True) as c:
        c.execute(_DDL)
        c.execute("TRUNCATE ml.price_forecast")
        with c.cursor() as cur:
            for cat, hist in histories.items():
                cur.executemany(
                    "INSERT INTO ml.price_forecast (category, month, price_index,"
                    " kind, model_version) VALUES (%s,%s,%s,'history',%s)",
                    [(cat, m.date(), round(float(v), 4), entry["version"])
                     for m, v in zip(hist["month"], hist["price_index"])])
                cur.executemany(
                    "INSERT INTO ml.price_forecast (category, month, price_index,"
                    " kind, model_version) VALUES (%s,%s,%s,'forecast',%s)",
                    [(cat, m, v, entry["version"]) for m, v in forecasts[cat]])
    if verbose:
        print(f"\nRegistered price_forecast v{entry['version']}; "
              f"{HORIZON}-month forecasts stored for {len(FF.CATEGORIES)} categories")
    return entry


if __name__ == "__main__":
    train_forecast()
