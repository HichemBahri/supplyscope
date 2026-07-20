"""Declarative chart specifications (ADR-003).

The agent never draws: it emits one of these JSON specs, validated by
Pydantic against strict per-type models AND against the actual result
columns. The frontend later dispatches on chart_type to render with Plotly.
A `table` spec is the universal fallback: any result can be shown as a table.
"""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, TypeAdapter, ValidationError


class _Base(BaseModel):
    title: str = Field(min_length=3, max_length=120)


class BarChart(_Base):
    chart_type: Literal["bar"]
    x_field: str
    y_fields: list[str] = Field(min_length=1, max_length=4)
    orientation: Literal["v", "h"] = "v"
    stacked: bool = False


class LineChart(_Base):
    chart_type: Literal["line"]
    x_field: str
    y_fields: list[str] = Field(min_length=1, max_length=4)


class PieChart(_Base):
    chart_type: Literal["pie"]
    label_field: str
    value_field: str


class ScatterChart(_Base):
    chart_type: Literal["scatter"]
    x_field: str
    y_field: str
    color_field: str | None = None


class KpiCard(_Base):
    chart_type: Literal["kpi"]
    value_field: str
    unit: str | None = None


class TableSpec(_Base):
    chart_type: Literal["table"]


ChartSpec = Annotated[
    Union[BarChart, LineChart, PieChart, ScatterChart, KpiCard, TableSpec],
    Field(discriminator="chart_type"),
]
_adapter: TypeAdapter = TypeAdapter(ChartSpec)


class ChartSpecError(ValueError):
    """Invalid spec; message is safe to feed back to the LLM for one retry."""


def _referenced_fields(spec) -> list[str]:
    fields: list[str] = []
    for attr in ("x_field", "y_field", "label_field", "value_field", "color_field"):
        if (v := getattr(spec, attr, None)):
            fields.append(v)
    fields.extend(getattr(spec, "y_fields", []) or [])
    return fields


def parse_chart_spec(payload: str | dict, columns: list[str]):
    """Parse+validate a spec; every referenced field must be a result column."""
    try:
        spec = (_adapter.validate_json(payload) if isinstance(payload, str)
                else _adapter.validate_python(payload))
    except ValidationError as exc:
        raise ChartSpecError(
            f"Invalid chart specification: {exc.errors()[:3]}") from exc
    unknown = [f for f in _referenced_fields(spec) if f not in columns]
    if unknown:
        raise ChartSpecError(
            f"Spec references non-existent result columns {unknown}; "
            f"available columns: {columns}")
    return spec
