"""Typed state flowing through the agent graph.

LangGraph merges each node's returned partial dict into this state; typing it
makes the data contract between nodes explicit and testable.
"""
from __future__ import annotations

from typing import Any, TypedDict


class SqlAttempt(TypedDict):
    sql: str
    error: str


class AgentState(TypedDict, total=False):
    # inputs
    question: str
    schema_doc: str
    current_date: str
    # SQL loop
    sql: str                     # current candidate query
    attempts: list[SqlAttempt]   # failed candidates with their DB errors
    # execution outcome
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    duration_ms: float
    error: str                   # set when the loop gave up
    # output
    answer: str
