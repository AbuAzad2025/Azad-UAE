"""Cov4: elasticsearch_service — disabled/enabled/except/fallback arcs."""

from __future__ import annotations

from unittest.mock import patch

from services.elasticsearch_service import ElasticsearchService


def test_is_enabled_false_when_no_env(monkeypatch):
    monkeypatch.delenv("ELASTICSEARCH_URL", raising=False)
    assert ElasticsearchService.is_enabled() is False


def test_is_enabled_true_when_env_set(monkeypatch):
    monkeypatch.setenv("ELASTICSEARCH_URL", "http://localhost:9200")
    assert ElasticsearchService.is_enabled() is True


def test_index_sale_disabled_returns_error(monkeypatch):
    monkeypatch.delenv("ELASTICSEARCH_URL", raising=False)
    out = ElasticsearchService.index_sale({"id": "1"})
    assert out == {"success": False, "error": "Elasticsearch not configured"}


def test_index_sale_enabled_success(monkeypatch):
    monkeypatch.setenv("ELASTICSEARCH_URL", "http://localhost:9200")

    class FakeES:
        def __init__(self, *a, **k):
            pass

        def index(self, index=None, id=None, document=None, **k):
            return {"_id": "abc123"}

    with patch.dict("sys.modules", {}):
        import sys

        fake_mod = type(sys)("elasticsearch")
        fake_mod.Elasticsearch = FakeES
        with patch.dict(sys.modules, {"elasticsearch": fake_mod}):
            out = ElasticsearchService.index_sale({"id": "s1", "sale_number": "S-1"})
    assert out == {"success": True, "id": "abc123"}


def test_index_sale_enabled_exception_path(monkeypatch):
    monkeypatch.setenv("ELASTICSEARCH_URL", "http://localhost:9200")

    class BoomES:
        def __init__(self, *a, **k):
            raise ConnectionError("down")

    import sys

    fake_mod = type(sys)("elasticsearch")
    fake_mod.Elasticsearch = BoomES
    with patch.dict(sys.modules, {"elasticsearch": fake_mod}):
        out = ElasticsearchService.index_sale({"id": "s1"})
    assert out["success"] is False
    assert "down" in out["error"]


def test_search_sales_disabled_uses_fallback(monkeypatch, db_session, sample_tenant):
    monkeypatch.delenv("ELASTICSEARCH_URL", raising=False)
    out = ElasticsearchService.search_sales("no-such-sale-xyz", limit=5)
    assert out["success"] is True
    assert out["fallback"] is True
    assert out["total"] == 0


def test_search_sales_enabled_exception_falls_back(monkeypatch):
    monkeypatch.setenv("ELASTICSEARCH_URL", "http://localhost:9200")
    import sys

    with patch.dict(sys.modules, {"elasticsearch": None}):
        # ImportError inside try -> except -> fallback (empty query hits DB)
        out = ElasticsearchService.search_sales("", limit=3)
    assert out["success"] is True
    assert out.get("fallback") is True


def test_search_sales_enabled_success(monkeypatch):
    monkeypatch.setenv("ELASTICSEARCH_URL", "http://localhost:9200")

    class FakeES:
        def __init__(self, *a, **k):
            pass

        def search(self, index=None, body=None, **k):
            assert body["size"] == 10
            assert "bool" in body["query"]  # filters branch
            return {"hits": {"hits": [{"_source": {"id": 1}}], "total": {"value": 1}}}

    import sys

    fake_mod = type(sys)("elasticsearch")
    fake_mod.Elasticsearch = FakeES
    with patch.dict(sys.modules, {"elasticsearch": fake_mod}):
        out = ElasticsearchService.search_sales("S-1", filters={"status": "confirmed"}, limit=10)
    assert out == {"success": True, "results": [{"id": 1}], "total": 1}


def test_search_sales_enabled_no_filters(monkeypatch):
    monkeypatch.setenv("ELASTICSEARCH_URL", "http://localhost:9200")

    class FakeES:
        def __init__(self, *a, **k):
            pass

        def search(self, index=None, body=None, **k):
            assert "multi_match" in body["query"]
            return {"hits": {"hits": [], "total": {"value": 0}}}

    import sys

    fake_mod = type(sys)("elasticsearch")
    fake_mod.Elasticsearch = FakeES
    with patch.dict(sys.modules, {"elasticsearch": fake_mod}):
        out = ElasticsearchService.search_sales("q", limit=5)
    assert out["total"] == 0


def test_fallback_search_with_filters_and_query(db_session, sample_tenant, sample_user, sample_warehouse, sample_customer):
    from datetime import datetime
    from decimal import Decimal

    from models import Sale

    sale = Sale(
        tenant_id=sample_tenant.id,
        sale_number="ES-FALLBACK-1",
        customer_id=sample_customer.id,
        seller_id=sample_user.id,
        warehouse_id=sample_warehouse.id,
        sale_date=datetime.now(),
        status="confirmed",
        subtotal=Decimal("10"),
        total_amount=Decimal("10"),
        amount=Decimal("10"),
        amount_aed=Decimal("10"),
        notes="special fallback note",
    )
    db_session.add(sale)
    db_session.flush()
    out = ElasticsearchService._fallback_search("FALLBACK-1", filters={"status": "confirmed"}, limit=10)
    assert out["total"] >= 1
    assert any(r["sale_number"] == "ES-FALLBACK-1" for r in out["results"])
    # empty query branch, no filters branch
    out2 = ElasticsearchService._fallback_search("", None, 5)
    assert out2["success"] is True


def test_index_sale_missing_id_key_returns_error(monkeypatch):
    # sale_data["id"] KeyError is caught by the try/except -> error dict (except arc)
    monkeypatch.setenv("ELASTICSEARCH_URL", "http://localhost:9200")

    class FakeES:
        def __init__(self, *a, **k):
            pass

        def index(self, **k):
            return {"_id": "x"}

    import sys

    fake_mod = type(sys)("elasticsearch")
    fake_mod.Elasticsearch = FakeES
    with patch.dict(sys.modules, {"elasticsearch": fake_mod}):
        out = ElasticsearchService.index_sale({})
    assert out == {"success": False, "error": "'id'"}
