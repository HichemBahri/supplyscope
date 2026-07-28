"""Chart dependency index: which saved charts read which erp tables.

Built by parsing each saved chart's SQL for `erp.<table>` references —
possible precisely because charts are stored as SQL text (ADR-003), and
guaranteed meaningful because charts are validated executable at save time.
"""
from __future__ import annotations

import re
import threading

from app.db import app_repo

_TABLE_RE = re.compile(r"\b(?:erp|ml)\.([a-z_]+)")


def extract_tables(sql: str) -> set[str]:
    """All erp/ml tables referenced by a SQL text."""
    return set(_TABLE_RE.findall(sql.lower()))


class ChartIndex:
    """In-memory map table -> chart_ids, plus chart records for refresh/push.

    Rebuilt from app.saved_charts on demand (startup, chart save/delete).
    Thread-safe: rebuilt under a lock, read via atomic dict swaps.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_table: dict[str, set[int]] = {}
        self._charts: dict[int, dict] = {}

    def rebuild(self) -> None:
        by_table: dict[str, set[int]] = {}
        charts: dict[int, dict] = {}
        for row in app_repo.list_all_saved_charts():
            charts[row["chart_id"]] = row
            for t in extract_tables(row["sql_query"]):
                by_table.setdefault(t, set()).add(row["chart_id"])
        with self._lock:
            self._by_table = by_table
            self._charts = charts

    def charts_for(self, tables: set[str]) -> list[dict]:
        with self._lock:
            ids: set[int] = set()
            for t in tables:
                ids |= self._by_table.get(t, set())
            return [self._charts[i] for i in sorted(ids)]

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._charts)
