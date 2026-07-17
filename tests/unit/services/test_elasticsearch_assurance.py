"""Elasticsearch service — indexing, search, offline fallback."""

from __future__ import annotations

import os
from unittest.mock import MagicMock


class TestElasticsearchEnabled:
    """is_enabled — env gate."""

    def test_disabled_without_url(self, mocker):
        mocker.patch.dict(os.environ, {}, clear=True)
        os.environ.pop("ELASTICSEARCH_URL", None)
        from services.elasticsearch_service import ElasticsearchService

        assert ElasticsearchService.is_enabled() is False

    def test_enabled_with_url(self, mocker):
        mocker.patch.dict(os.environ, {"ELASTICSEARCH_URL": "http://es:9200"})
        from services.elasticsearch_service import ElasticsearchService

        assert ElasticsearchService.is_enabled() is True


class TestIndexSale:
    """index_sale — single document pipeline."""

    def _inject_es(self, mock_es):
        import sys

        es_mod = MagicMock()
        es_mod.Elasticsearch = MagicMock(return_value=mock_es)
        sys.modules["elasticsearch"] = es_mod
        return es_mod

    def test_not_configured_returns_error(self, mocker):
        mocker.patch(
            "services.elasticsearch_service.ElasticsearchService.is_enabled",
            return_value=False,
        )
        from services.elasticsearch_service import ElasticsearchService

        result = ElasticsearchService.index_sale({"id": 1})
        assert result["success"] is False
        assert "not configured" in result["error"].lower()

    def test_successful_index(self, mocker):
        mocker.patch(
            "services.elasticsearch_service.ElasticsearchService.is_enabled",
            return_value=True,
        )
        mocker.patch.dict(os.environ, {"ELASTICSEARCH_URL": "http://localhost:9200"})

        mock_es = MagicMock()
        mock_es.index.return_value = {"_id": "42"}
        self._inject_es(mock_es)

        from services.elasticsearch_service import ElasticsearchService

        result = ElasticsearchService.index_sale({"id": 42, "sale_number": "S-1"})
        assert result["success"] is True
        assert result["id"] == "42"
        mock_es.index.assert_called_once_with(
            index="sales", id=42, document={"id": 42, "sale_number": "S-1"}
        )

    def test_index_timeout_returns_error(self, mocker):
        mocker.patch(
            "services.elasticsearch_service.ElasticsearchService.is_enabled",
            return_value=True,
        )
        mocker.patch.dict(os.environ, {"ELASTICSEARCH_URL": "http://localhost:9200"})
        mock_es = MagicMock()
        mock_es.index.side_effect = TimeoutError("node timeout")
        self._inject_es(mock_es)

        from services.elasticsearch_service import ElasticsearchService

        result = ElasticsearchService.index_sale({"id": 1})
        assert result["success"] is False
        assert "timeout" in result["error"].lower()


class TestSearchSales:
    """search_sales — query body, filters, fallback when ES offline."""

    def test_offline_uses_sql_fallback(self, mocker):
        mocker.patch(
            "services.elasticsearch_service.ElasticsearchService.is_enabled",
            return_value=False,
        )
        mocker.patch(
            "services.elasticsearch_service.ElasticsearchService._fallback_search",
            return_value={
                "success": True,
                "results": [{"id": 1}],
                "total": 1,
                "fallback": True,
            },
        )
        from services.elasticsearch_service import ElasticsearchService

        result = ElasticsearchService.search_sales("INV-100")
        assert result["fallback"] is True
        assert result["total"] == 1

    def test_es_search_with_filters(self, mocker):
        mocker.patch(
            "services.elasticsearch_service.ElasticsearchService.is_enabled",
            return_value=True,
        )
        mocker.patch.dict(os.environ, {"ELASTICSEARCH_URL": "http://es:9200"})

        mock_es = MagicMock()
        mock_es.search.return_value = {
            "hits": {
                "hits": [{"_source": {"sale_number": "S-9"}}],
                "total": {"value": 1},
            },
        }
        import sys

        es_mod = MagicMock()
        es_mod.Elasticsearch = MagicMock(return_value=mock_es)
        sys.modules["elasticsearch"] = es_mod

        from services.elasticsearch_service import ElasticsearchService

        result = ElasticsearchService.search_sales(
            "S-9", filters={"tenant_id": 1}, limit=10
        )
        assert result["success"] is True
        assert result["total"] == 1
        body = mock_es.search.call_args.kwargs["body"]
        assert "bool" in body["query"]

    def test_es_exception_falls_back(self, mocker):
        mocker.patch(
            "services.elasticsearch_service.ElasticsearchService.is_enabled",
            return_value=True,
        )
        mocker.patch.dict(os.environ, {"ELASTICSEARCH_URL": "http://es:9200"})
        import sys

        es_mod = MagicMock()
        es_mod.Elasticsearch = MagicMock(side_effect=ConnectionError("ES offline"))
        sys.modules["elasticsearch"] = es_mod
        fallback = mocker.patch(
            "services.elasticsearch_service.ElasticsearchService._fallback_search",
            return_value={"success": True, "results": [], "total": 0, "fallback": True},
        )

        from services.elasticsearch_service import ElasticsearchService

        ElasticsearchService.search_sales("query")
        fallback.assert_called_once()


class TestFallbackSearch:
    """_fallback_search — ORM ilike query."""

    def test_fallback_filters_and_serializes(self, mocker):
        sale = MagicMock()
        sale.to_dict.return_value = {"id": 5, "sale_number": "S-5"}

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.all.return_value = [sale]
        mocker.patch.object(
            __import__("models", fromlist=["Sale"]).Sale,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=mock_q,
        )

        from services.elasticsearch_service import ElasticsearchService

        result = ElasticsearchService._fallback_search(
            "S-5", filters={"tenant_id": 1}, limit=25
        )
        assert result["fallback"] is True
        assert result["results"][0]["sale_number"] == "S-5"
        assert mock_q.filter.call_count >= 2
