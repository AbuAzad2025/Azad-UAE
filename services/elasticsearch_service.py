import os
from typing import Any


class ElasticsearchService:
    @staticmethod
    def is_enabled() -> bool:
        return bool(os.environ.get("ELASTICSEARCH_URL"))

    @staticmethod
    def index_sale(sale_data: dict) -> dict:
        if not ElasticsearchService.is_enabled():
            return {"success": False, "error": "Elasticsearch not configured"}

        try:
            from elasticsearch import Elasticsearch

            es = Elasticsearch([os.environ.get("ELASTICSEARCH_URL", "http://localhost:9200")])

            result = es.index(index="sales", id=sale_data["id"], document=sale_data)

            return {"success": True, "id": result["_id"]}

        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def search_sales(query: str, filters: dict | None = None, limit: int = 50) -> dict:
        if not ElasticsearchService.is_enabled():
            return ElasticsearchService._fallback_search(query, filters, limit)

        try:
            from elasticsearch import Elasticsearch

            es = Elasticsearch([os.environ.get("ELASTICSEARCH_URL") or ""])

            body: dict[str, Any] = {
                "query": {
                    "multi_match": {
                        "query": query,
                        "fields": ["sale_number", "customer_name", "notes"],
                    }
                },
                "size": limit,
            }

            if filters:
                body["query"] = {
                    "bool": {
                        "must": body["query"],
                        "filter": [{"term": {k: v}} for k, v in filters.items()],
                    }
                }

            result = es.search(index="sales", body=body)

            hits = [hit["_source"] for hit in result["hits"]["hits"]]

            return {
                "success": True,
                "results": hits,
                "total": result["hits"]["total"]["value"],
            }

        except Exception:
            return ElasticsearchService._fallback_search(query, filters, limit)

    @staticmethod
    def _fallback_search(query: str, filters: dict | None = None, limit: int = 50) -> dict:
        from sqlalchemy import or_

        from models import Sale

        search_query = Sale.query

        if query:
            search_query = search_query.filter(
                or_(Sale.sale_number.ilike(f"%{query}%"), Sale.notes.ilike(f"%{query}%"))
            )

        if filters:
            for key, value in filters.items():
                search_query = search_query.filter(getattr(Sale, key) == value)

        results = search_query.limit(limit).all()

        return {
            "success": True,
            "results": [sale.to_dict() for sale in results],
            "total": len(results),
            "fallback": True,
        }
