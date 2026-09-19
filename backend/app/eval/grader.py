"""Answer grading for the agent benchmark (Phase 15).

The agent chooses its own column names, row order and number formats, so
grading compares CONTENT, not shape. Every leniency is deliberate and
listed here so the methodology can be defended:

  * numbers are compared with a relative tolerance (default 2%);
  * a rate may be expressed as a ratio (0.77) or a percent (77.0) — both
    are accepted for `scalar`, because either is a correct reading of
    "what is the on-time rate";
  * for `top1` / `ordered` / `set`, an entity matches when ANY cell of the
    truth row (name, code, year...) appears, case-insensitively, inside ANY
    cell of the agent row — the agent may show a code where we expect a
    name, and vice versa;
  * numbers are only searched in the agent's FIRST 3 rows for scalar/count:
    a correct value buried in row 40 of an unrelated listing is not an
    answer.

What is NOT lenient: a wrong ordering (best vs worst) fails `top1`; extra
or missing entities fail `set`; an empty result fails everything.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Sequence


@dataclass
class Verdict:
    correct: bool
    reason: str


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float, Decimal)):
        return float(v)
    if isinstance(v, str):
        s = v.replace(",", "").replace("%", "").strip()
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _close(a: float, b: float, tol: float) -> bool:
    if math.isnan(a) or math.isnan(b):
        return False
    if b == 0:
        return abs(a) <= max(tol, 0.5)
    return abs(a - b) <= max(tol * abs(b), 1e-9)


def _cells_text(row: Sequence[Any]) -> list[str]:
    out = []
    for c in row:
        if c is None:
            continue
        out.append(str(c).strip().lower())
    return out


def _entity_in_row(truth_row: Sequence[Any], agent_row: Sequence[Any]) -> bool:
    agent_cells = _cells_text(agent_row)
    for t in truth_row:
        if t is None:
            continue
        tn = _num(t)
        if isinstance(t, (int, Decimal, float)) and not isinstance(t, bool) and tn is not None:
            # numeric entity (e.g. a year): exact-ish numeric match on a cell
            for c in agent_row:
                cn = _num(c)
                if cn is not None and _close(cn, tn, 1e-6):
                    return True
            continue
        ts = str(t).strip().lower()
        if len(ts) < 2:
            continue
        if any(ts in ac or ac in ts and len(ac) >= 4 for ac in agent_cells):
            return True
    return False


def grade(kind: str, truth_rows: list[Sequence[Any]], agent_rows: list[Sequence[Any]],
          tolerance: float = 0.02) -> Verdict:
    if not agent_rows:
        return Verdict(False, "agent returned no rows")

    if kind in ("count", "scalar"):
        expected = _num(truth_rows[0][0])
        if expected is None:
            return Verdict(False, "truth is not numeric")
        tol = 1e-9 if kind == "count" else tolerance
        candidates = [expected] if kind == "count" else [expected, expected * 100, expected / 100]
        for row in agent_rows[:3]:
            for c in row:
                cn = _num(c)
                if cn is None:
                    continue
                for e in candidates:
                    if _close(cn, e, tol):
                        return Verdict(True, f"found {cn:g} ≈ {expected:g}")
        got = [c for row in agent_rows[:3] for c in row if _num(c) is not None][:6]
        return Verdict(False, f"expected {expected:g}, numeric cells seen {got}")

    if kind == "top1":
        if _entity_in_row(truth_rows[0], agent_rows[0]):
            return Verdict(True, "first row names the expected entity")
        # diagnostic: is it present at all (wrong order) or absent?
        anywhere = any(_entity_in_row(truth_rows[0], r) for r in agent_rows)
        return Verdict(False, "expected entity is " + ("present but not first (ordering)"
                                                    if anywhere else "absent"))

    if kind == "ordered":
        k = len(truth_rows)
        if len(agent_rows) < k:
            return Verdict(False, f"fewer than {k} rows")
        for i, t in enumerate(truth_rows):
            if not _entity_in_row(t, agent_rows[i]):
                return Verdict(False, f"position {i + 1} mismatch")
        return Verdict(True, f"top {k} in order")

    if kind == "set":
        if len(agent_rows) != len(truth_rows):
            return Verdict(False, f"expected {len(truth_rows)} rows, got {len(agent_rows)}")
        for t in truth_rows:
            if not any(_entity_in_row(t, r) for r in agent_rows):
                return Verdict(False, f"missing entity {t[0]!r}")
        return Verdict(True, "exact set")

    return Verdict(False, f"unknown kind {kind}")
