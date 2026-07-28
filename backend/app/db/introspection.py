"""Schema introspection: turn the live `erp` schema into a compact document
the LLM can read.

This is where the SQL COMMENTs planted in Phase 1 pay off: table and column
comments, foreign keys and CHECK constraints (which enumerate valid status
values) are all extracted from the catalog, so the agent's knowledge of the
schema can never drift from the schema itself.
"""
from __future__ import annotations

import time

import psycopg

_SCHEMA = "erp"
_SCHEMAS = ("erp", "ml")

_TABLES_SQL = """
SELECT n.nspname AS schema_name, c.relname AS table_name,
       obj_description(c.oid) AS table_comment
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = ANY(%s) AND c.relkind = 'r'
ORDER BY n.nspname, c.relname
"""

_COLUMNS_SQL = """
SELECT c.relname AS table_name,
       a.attname AS column_name,
       format_type(a.atttypid, a.atttypmod) AS data_type,
       NOT a.attnotnull AS is_nullable,
       col_description(c.oid, a.attnum) AS column_comment
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = ANY(%s) AND c.relkind = 'r' AND a.attnum > 0 AND NOT a.attisdropped
ORDER BY c.relname, a.attnum
"""

_FKS_SQL = """
SELECT conrelid::regclass::text AS table_name,
       a.attname AS column_name,
       confrelid::regclass::text AS ref_table,
       fa.attname AS ref_column
FROM pg_constraint ct
JOIN pg_attribute a  ON a.attrelid = ct.conrelid  AND a.attnum  = ct.conkey[1]
JOIN pg_attribute fa ON fa.attrelid = ct.confrelid AND fa.attnum = ct.confkey[1]
JOIN pg_namespace n ON n.oid = ct.connamespace
WHERE ct.contype = 'f' AND n.nspname = ANY(%s)
ORDER BY 1, 2
"""

_CHECKS_SQL = """
SELECT conrelid::regclass::text AS table_name,
       pg_get_constraintdef(ct.oid) AS definition
FROM pg_constraint ct
JOIN pg_namespace n ON n.oid = ct.connamespace
WHERE ct.contype = 'c' AND n.nspname = ANY(%s)
  AND pg_get_constraintdef(ct.oid) ILIKE '%%ANY (ARRAY[%%'
ORDER BY 1
"""


def _prettify_check(definition: str) -> str:
    """Rewrite Postgres's `col = ANY (ARRAY['a'::text, 'b'::text])` form back
    into the readable `col IN ('a', 'b')` the DDL originally used."""
    import re

    def repl(m: "re.Match[str]") -> str:
        col, arr = m.group(1), m.group(2)
        values = ", ".join(v.strip() for v in arr.replace("::text", "").split(","))
        return f"{col} IN ({values})"

    out = re.sub(r"\(?(\w+)\)?\s*=\s*ANY\s*\(ARRAY\[([^\]]+)\]\)", repl, definition)
    out = re.sub(r"^CHECK\s*\(\((.*)\)\)$", r"CHECK (\1)", out)
    while out.count(")") > out.count("("):      # drop parens orphaned by rewriting
        out = out[::-1].replace(")", "", 1)[::-1]
    return out


_MAX_ENUMLIKE_CARDINALITY = 15


def _attach_sample_values(cur, tables: dict) -> None:
    """For text columns whose values are NOT already enumerated by a CHECK
    constraint, list the distinct values when there are few of them.

    Motivated by a real agent failure: the model guessed country='Libya'
    while the data stores 'Libye' — schema structure alone does not teach
    data vocabulary. Low-cardinality value lists close that gap.
    """
    for tname, info in tables.items():
        enumerated = " ".join(info["checks"])
        for col, typ, _nullable, _comment in info["columns"]:
            if typ != "text" or f"{col} IN (" in enumerated:
                continue
            cur.execute(
                f"SELECT count(DISTINCT {col}) "
                f"FROM {info['schema']}.{tname}")
            n = cur.fetchone()[0]
            if 0 < n <= _MAX_ENUMLIKE_CARDINALITY:
                cur.execute(
                    f"SELECT DISTINCT {col} FROM {info['schema']}.{tname} "
                    f"WHERE {col} IS NOT NULL ORDER BY 1")
                vals = ", ".join(repr(r[0]) for r in cur.fetchall())
                info.setdefault("samples", {})[col] = vals


def build_schema_doc(dsn: str) -> str:
    """Render the erp schema as a markdown document for LLM consumption."""
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(_TABLES_SQL, (list(_SCHEMAS),))
        tables: dict[str, dict] = {
            name: {"schema": schema, "comment": comment,
                   "columns": [], "fks": [], "checks": []}
            for schema, name, comment in cur.fetchall()
        }
        cur.execute(_COLUMNS_SQL, (list(_SCHEMAS),))
        for t, col, typ, nullable, comment in cur.fetchall():
            tables[t]["columns"].append((col, typ, nullable, comment))
        cur.execute(_FKS_SQL, (list(_SCHEMAS),))
        for t, col, rt, rc in cur.fetchall():
            tables[t.split(".")[-1]]["fks"].append((col, rt, rc))
        cur.execute(_CHECKS_SQL, (list(_SCHEMAS),))
        for t, definition in cur.fetchall():
            tables[t.split(".")[-1]]["checks"].append(_prettify_check(definition))
        _attach_sample_values(cur, tables)

    parts: list[str] = [
        f"PostgreSQL schemas `erp` (operational data) and `ml` "
        f"(machine-learning outputs) — {len(tables)} tables. All queries "
        "MUST use fully qualified names (erp.<table> / ml.<table>).\n"
    ]
    for name, info in tables.items():
        parts.append(f"### {info['schema']}.{name}")
        if info["comment"]:
            parts.append(info["comment"])
        cols = []
        for col, typ, nullable, comment in info["columns"]:
            line = f"- {col} {typ}{'' if nullable else ' NOT NULL'}"
            if comment:
                line += f" — {comment}"
            if (samples := info.get("samples", {}).get(col)):
                line += f" [values: {samples}]"
            cols.append(line)
        parts.append("\n".join(cols))
        if info["fks"]:
            parts.append("FK: " + "; ".join(
                f"{c} → {rt}.{rc}" for c, rt, rc in info["fks"]))
        if info["checks"]:
            parts.append("Constraints: " + " | ".join(info["checks"]))
        parts.append("")
    return "\n".join(parts)


class SchemaCache:
    """Tiny TTL cache so we don't introspect on every agent turn."""

    def __init__(self, dsn: str, ttl_seconds: int = 600):
        self._dsn = dsn
        self._ttl = ttl_seconds
        self._doc: str | None = None
        self._at = 0.0

    def get(self, force_refresh: bool = False) -> str:
        now = time.monotonic()
        if force_refresh or self._doc is None or (now - self._at) > self._ttl:
            self._doc = build_schema_doc(self._dsn)
            self._at = now
        return self._doc
