"""Coverage for routes/api_enhanced.py uncovered arcs 28->31 and 52->55.

Both arcs are the ``if tid:`` tenant-filter guard skipped when
``get_active_tenant_id`` returns a falsy value. Each test drives the real
route via the test client with a real logged-in user and asserts the real
response envelope.
"""

from __future__ import annotations


class TestApiEnhancedNoTenantArcs:
    def test_sales_list_without_tenant_arc_28_31(self, auth_client, sample_sale, mocker):
        """Arc 28->31: GET /api/v2/sales with tid=None skips tenant filter."""
        mocker.patch("routes.api_enhanced.get_active_tenant_id", return_value=None)
        resp = auth_client.get("/api/v2/sales?per_page=50")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert sample_sale.id in [s["id"] for s in body["data"]]

    def test_sale_detail_without_tenant_arc_52_55(self, auth_client, sample_sale, mocker):
        """Arc 52->55: GET /api/v2/sales/<id> with tid=None skips tenant filter."""
        mocker.patch("routes.api_enhanced.get_active_tenant_id", return_value=None)
        resp = auth_client.get(f"/api/v2/sales/{sample_sale.id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["data"]["sale"]["id"] == sample_sale.id
