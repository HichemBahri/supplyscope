"""The reactivity engine (ADR-004).

One async task holds a dedicated LISTEN connection. Notifications are
debounced (bulk writes produce one refresh, not a storm), mapped to affected
charts via the dependency index, re-executed under the same read-only
agent_reader pipeline as every other query in the system, and pushed to the
owning user's subscribed clients through per-subscriber asyncio queues.
Delivery is best-effort by design (a missed update is healed by the next
one or a manual refresh — documented limitation of NOTIFY semantics).
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import threading

import psycopg

from app.config import get_settings
from app.db.app_repo import _dumps  # shared DB-native-types JSON serializer
from app.db.safe_executor import (
    SQLExecutionError, SQLValidationError, execute_readonly,
)
from app.db import app_repo
from app.reactivity.deps_index import ChartIndex

logger = logging.getLogger("supplyscope.reactivity")

DEBOUNCE_SECONDS = 1.0
QUEUE_MAXSIZE = 32
_PUSH_ROWS = 200


class ReactivityEngine:
    def __init__(self, debounce: float = DEBOUNCE_SECONDS) -> None:
        self.index = ChartIndex()
        self._shared_chart_ids: set[int] = set()
        self._debounce = debounce
        self._subscribers: dict[int, set[asyncio.Queue]] = {}
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()

    # ------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        await asyncio.to_thread(self._rebuild_all)
        self._stopping.clear()
        self._task = asyncio.create_task(self._listen_loop(), name="erp-listener")
        logger.info("reactivity engine started (%d charts indexed)", self.index.size)

    async def stop(self) -> None:
        self._stopping.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("reactivity engine stopped")

    def _rebuild_all(self) -> None:
        self.index.rebuild()
        self._shared_chart_ids = app_repo.shared_chart_ids()

    def broadcast(self, event: str, payload: str,
                  user_ids: set[int] | None = None) -> None:
        """Queue an SSE event for the given users (None = every subscriber)."""
        targets = (self._subscribers.keys() if user_ids is None
                   else [u for u in user_ids if u in self._subscribers])
        for uid in list(targets):
            for q in list(self._subscribers.get(uid, ())):
                try:
                    q.put_nowait({"event": event, "data": payload})
                except asyncio.QueueFull:
                    logger.warning("subscriber queue full; dropping %s", event)

    def broadcast_comment(self, comment: dict) -> None:
        """Push a freshly posted comment to every connected employee."""
        self.broadcast("comment_added", _dumps(comment))

    def reindex_soon(self) -> None:
        """Schedule an index rebuild (called after chart save/delete).

        Must be callable from ANY thread: FastAPI runs sync endpoints in
        threadpool workers, where no asyncio event loop is running — so a
        plain daemon thread, not loop.run_in_executor. (Bug found live by
        Hichem: RuntimeError 'no running event loop'; regression-tested in
        tests/test_reactivity.py.)"""
        threading.Thread(target=self._rebuild_all, daemon=True).start()

    # ---------------------------------------------------------- subscribers
    def subscribe(self, user_id: int) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
        self._subscribers.setdefault(user_id, set()).add(q)
        return q

    def unsubscribe(self, user_id: int, q: asyncio.Queue) -> None:
        subs = self._subscribers.get(user_id)
        if subs:
            subs.discard(q)
            if not subs:
                self._subscribers.pop(user_id, None)

    # -------------------------------------------------------------- listener
    async def _listen_loop(self) -> None:
        while not self._stopping.is_set():
            try:
                aconn = await psycopg.AsyncConnection.connect(
                    get_settings().app_dsn, autocommit=True)
                async with aconn:
                    await aconn.execute("LISTEN erp_data_change")
                    logger.info("LISTEN erp_data_change established")
                    await self._collect_forever(aconn)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("listener failed; reconnecting in 3s")
                await asyncio.sleep(3)

    async def _collect_forever(self, aconn) -> None:
        pending: set[str] = set()
        while not self._stopping.is_set():
            # gather notifications in debounce-sized windows
            async for n in aconn.notifies(timeout=self._debounce):
                try:
                    pending.add(json.loads(n.payload)["table"])
                except (json.JSONDecodeError, KeyError):
                    logger.warning("malformed notify payload: %r", n.payload)
            if pending:
                tables, pending = pending, set()
                await self._process(tables)

    # ------------------------------------------------------------ processing
    async def _process(self, tables: set[str]) -> None:
        charts = self.index.charts_for(tables)
        if not charts:
            await self._evaluate_rules(tables)
            return
        logger.info("change in %s -> refreshing %d chart(s)",
                    sorted(tables), len(charts))
        for chart in charts:
            shared = chart["chart_id"] in self._shared_chart_ids
            audience = None if shared else {chart["user_id"]}
            if not shared and chart["user_id"] not in self._subscribers:
                continue   # nobody watching this private chart right now
            try:
                res = await asyncio.to_thread(
                    execute_readonly, chart["sql_query"], _PUSH_ROWS)
            except (SQLValidationError, SQLExecutionError) as exc:
                logger.warning("chart %s refresh failed: %s", chart["chart_id"], exc)
                continue
            payload = _dumps({
                "chart_id": chart["chart_id"],
                "title": chart["title"],
                "chart_spec": chart["chart_spec"],
                "columns": res.columns,
                "rows": [list(r) for r in res.rows],
                "row_count": res.row_count,
                "truncated": res.truncated,
                "source_tables": sorted(tables),
                "refreshed_at": dt.datetime.now(dt.UTC).isoformat(),
            })
            self.broadcast("chart_update", payload, audience)
        # charts pushed first (fast path); rules evaluate after
        await self._evaluate_rules(tables)

    async def _evaluate_rules(self, tables: set[str]) -> None:
        """Expert system: re-evaluate business rules after erp changes.
        Derived tables are excluded so an alert write can never re-trigger
        evaluation in a loop. Best-effort by design."""
        _derived = {"alerts", "models", "delivery_risk", "price_forecast"}
        if not (tables - _derived):
            return
        try:
            from app.expert.engine import evaluate_all
            summary = await asyncio.to_thread(evaluate_all)
            self.broadcast("alerts_changed", _dumps(summary), None)
        except Exception:
            logger.exception("expert evaluation failed")


