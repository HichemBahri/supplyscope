"""Training pipeline for the delivery-risk classifier.

Methodology (defensible, in order):
1. TIME-BASED SPLIT — train on orders up to SPLIT_DATE, test on everything
   after. Random splits leak temporal patterns; supply chains drift.
2. BASELINE LADDER — logistic regression (linear baseline), random forest
   (non-linear ensemble), multilayer perceptron (neural). A model earns its
   complexity only by beating the simpler rung.
3. PERMUTATION IMPORTANCE on the held-out test set for the winning model —
   model-agnostic, honest (train-set importances flatter the model).
4. REGISTRY — every run is versioned in ml.models with full comparison, and
   the artifact is persisted for the scoring service.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score, confusion_matrix, f1_score, precision_score,
    recall_score, roc_auc_score,
)
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from app.ml import features as F
from app.ml.registry import register_model

SPLIT_DATE = dt.date(2025, 1, 1)
ARTIFACT_DIR = Path(__file__).resolve().parent.parent.parent / "ml_artifacts"


def _preprocessor() -> ColumnTransformer:
    return ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore"), F.CATEGORICAL),
        ("num", StandardScaler(), F.NUMERIC),
        ("bool", "passthrough", F.BOOLEAN),
    ])


def _ladder() -> dict[str, Pipeline]:
    return {
        "logistic_regression": Pipeline([
            ("prep", _preprocessor()),
            ("clf", LogisticRegression(max_iter=3000, class_weight="balanced")),
        ]),
        "random_forest": Pipeline([
            ("prep", _preprocessor()),
            ("clf", RandomForestClassifier(
                n_estimators=400, max_depth=6, min_samples_leaf=8,
                random_state=42, class_weight="balanced_subsample", n_jobs=-1)),
        ]),
        "mlp": Pipeline([
            ("prep", _preprocessor()),
            # small-data regime: lbfgs converges reliably where adam +
            # early-stopping (10% validation = ~30 rows) is unstable
            ("clf", MLPClassifier(
                hidden_layer_sizes=(16, 8), activation="relu",
                solver="lbfgs", alpha=1.0, max_iter=5000, random_state=42)),
        ]),
    }


def _evaluate(model: Pipeline, X, y) -> dict:
    proba = model.predict_proba(X)[:, 1]
    pred = proba >= 0.5
    return {
        "roc_auc": round(float(roc_auc_score(y, proba)), 4),
        "accuracy": round(float(accuracy_score(y, pred)), 4),
        "precision": round(float(precision_score(y, pred)), 4),
        "recall": round(float(recall_score(y, pred)), 4),
        "f1": round(float(f1_score(y, pred)), 4),
        "confusion_matrix": confusion_matrix(y, pred).tolist(),
    }


def train(verbose: bool = True) -> dict:
    df = F.training_frame()
    train_df = df[df["order_date"] < SPLIT_DATE]
    test_df = df[df["order_date"] >= SPLIT_DATE]
    cols = F.CATEGORICAL + F.NUMERIC + F.BOOLEAN
    X_tr, y_tr = train_df[cols], train_df[F.LABEL].to_numpy()
    X_te, y_te = test_df[cols], test_df[F.LABEL].to_numpy()

    # MLP hyperparameters are selected on a TIME-ORDERED validation tail of
    # the training window (last 20%) — never on the test set (no leakage).
    cut = train_df["order_date"].quantile(0.8)
    fit_idx, val_idx = train_df["order_date"] < cut, train_df["order_date"] >= cut
    best_val, best_cfg = -1.0, {"hidden_layer_sizes": (16, 8), "alpha": 1.0}
    for hidden in [(16, 8), (8,)]:
        for alpha in [0.1, 1.0, 3.0]:
            probe = Pipeline([
                ("prep", _preprocessor()),
                ("clf", MLPClassifier(hidden_layer_sizes=hidden, activation="relu",
                                      solver="lbfgs", alpha=alpha, max_iter=5000,
                                      random_state=42))])
            probe.fit(X_tr[fit_idx.to_numpy()], y_tr[fit_idx.to_numpy()])
            auc = roc_auc_score(y_tr[val_idx.to_numpy()],
                                probe.predict_proba(X_tr[val_idx.to_numpy()])[:, 1])
            if auc > best_val:
                best_val, best_cfg = auc, {"hidden_layer_sizes": hidden, "alpha": alpha}
    if verbose:
        print(f"  (mlp selected {best_cfg} @ val AUC {best_val:.3f})")

    ladder = _ladder()
    ladder["mlp"] = Pipeline([
        ("prep", _preprocessor()),
        ("clf", MLPClassifier(**best_cfg, activation="relu", solver="lbfgs",
                              max_iter=5000, random_state=42))])

    comparison: dict[str, dict] = {}
    fitted: dict[str, Pipeline] = {}
    for name, pipe in ladder.items():
        pipe.fit(X_tr, y_tr)
        fitted[name] = pipe
        comparison[name] = _evaluate(pipe, X_te, y_te)
        if verbose:
            m = comparison[name]
            print(f"  {name:22s} AUC {m['roc_auc']:.3f}  F1 {m['f1']:.3f} "
                  f" P {m['precision']:.3f}  R {m['recall']:.3f}")

    best_name = max(comparison, key=lambda k: comparison[k]["roc_auc"])
    best = fitted[best_name]

    # honest importances: permutation on the held-out test set
    perm = permutation_importance(best, X_te, y_te, scoring="roc_auc",
                                  n_repeats=10, random_state=42)
    importance = sorted(
        ({"feature": c, "importance": round(float(m), 4)}
         for c, m in zip(cols, perm.importances_mean)),
        key=lambda d: -d["importance"])

    ARTIFACT_DIR.mkdir(exist_ok=True)
    entry = register_model(
        model_name="delivery_risk", task="classification", algo=best_name,
        split_date=SPLIT_DATE, train_rows=len(train_df), test_rows=len(test_df),
        metrics=comparison[best_name], comparison=comparison,
        feature_importance=importance,
        artifact_saver=lambda path: joblib.dump(best, path),
        artifact_dir=ARTIFACT_DIR)

    if verbose:
        print(f"\nWinner: {best_name} -> ml.models v{entry['version']} (active)")
        print("Top signals:", ", ".join(d["feature"] for d in importance[:4]))
    return entry


if __name__ == "__main__":
    train()
