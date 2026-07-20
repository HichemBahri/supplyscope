"""Integration tests: the schema document the agent will read."""
import pytest

from app.config import get_settings
from app.db.introspection import SchemaCache, build_schema_doc


@pytest.mark.integration
def test_schema_doc_contains_tables_comments_fks_and_enums():
    doc = build_schema_doc(get_settings().app_dsn)
    # our 20 tables are present
    for t in ("boqs", "purchase_orders", "payments", "supplier_quotations", "assets"):
        assert f"### erp.{t}" in doc
    # Phase-1 comments reached the agent
    assert "Bill of Quantities" in doc
    assert "Technical Bid Evaluation" in doc
    # FKs extracted
    assert "po_id → erp.purchase_orders.po_id" in doc
    # CHECK constraints expose valid enum values to the agent
    assert "'customs_hold'" in doc and "'letter_of_credit'" in doc
    # v2: sample values for non-enum text columns (data vocabulary)
    assert "'Libye'" in doc and "'Tunisie'" in doc
    # v2.1: FX dimension visible to the agent
    assert "### erp.fx_rates" in doc and "rate_to_tnd" in doc


@pytest.mark.integration
def test_schema_cache_reuses_doc():
    cache = SchemaCache(get_settings().app_dsn, ttl_seconds=600)
    d1 = cache.get()
    d2 = cache.get()
    assert d1 is d2  # same object: no second introspection within TTL
