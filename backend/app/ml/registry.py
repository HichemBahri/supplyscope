"""Model registry over ml.models: versioning, activation, retrieval."""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Callable

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

from app.config import get_settings
from app.db.app_repo import _dumps


def _conn() -> psycopg.Connection:
    return psycopg.connect(get_settings().app_dsn, row_factory=dict_row)


def register_model(*, model_name: str, task: str, algo: str,
                   split_date: dt.date, train_rows: int, test_rows: int,
                   metrics: dict, comparison: dict, feature_importance: list,
                   artifact_saver: Callable[[Path], None],
                   artifact_dir: Path) -> dict:
    with _conn() as c:
        version = c.execute(
            "SELECT COALESCE(max(version), 0) + 1 AS v FROM ml.models "
            "WHERE model_name = %s", (model_name,)).fetchone()["v"]
        path = artifact_dir / f"{model_name}_v{version}.joblib"
        artifact_saver(path)
        c.execute("UPDATE ml.models SET is_active = false WHERE model_name = %s",
                  (model_name,))
        return c.execute(
            "INSERT INTO ml.models (model_name, task, algo, version, split_date,"
            " train_rows, test_rows, metrics, comparison, feature_importance,"
            " artifact_path, is_active) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,true) RETURNING *",
            (model_name, task, algo, version, split_date, train_rows, test_rows,
             Json(metrics, dumps=_dumps), Json(comparison, dumps=_dumps),
             Json(feature_importance, dumps=_dumps), str(path))).fetchone()


def active_model(model_name: str) -> dict | None:
    with _conn() as c:
        return c.execute(
            "SELECT * FROM ml.models WHERE model_name = %s AND is_active "
            "ORDER BY version DESC LIMIT 1", (model_name,)).fetchone()


def list_models(model_name: str | None = None) -> list[dict]:
    with _conn() as c:
        if model_name:
            return c.execute("SELECT * FROM ml.models WHERE model_name = %s "
                             "ORDER BY version DESC", (model_name,)).fetchall()
        return c.execute("SELECT * FROM ml.models ORDER BY model_name, version DESC"
                         ).fetchall()


def load_artifact(model_row: dict):
    """Load a model artifact robustly across environments: the registry may
    hold an absolute path from the machine that trained (host vs container),
    so fall back to resolving the FILENAME against the canonical artifact
    directory. Lesson: store locations, not machines."""
    from pathlib import Path

    import joblib
    path = Path(model_row["artifact_path"])
    if not path.exists():
        from app.ml.train_risk import ARTIFACT_DIR
        path = ARTIFACT_DIR / path.name
    return joblib.load(path)
