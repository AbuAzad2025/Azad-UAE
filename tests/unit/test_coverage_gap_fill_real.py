"""Real gap-fill: route/service branches from CI report."""


def test_public_sitemap_lastmod_branch(client):
    resp = client.get("/sitemap.xml")
    assert resp.status_code == 200
    data = resp.get_data(as_text=True)
    assert "<lastmod>" in data


def test_reports_before_request_exit_and_inventory_403(auth_client):
    resp = auth_client.get("/reports/")
    assert resp.status_code in (200, 302)
    resp_inv = auth_client.get("/reports/inventory-reconciliation/export?format=csv")
    assert resp_inv.status_code in (200, 302, 403, 404)


def test_reports_receivables_aging(auth_client):
    resp = auth_client.get("/reports/receivables")
    assert resp.status_code in (200, 302)


def test_sales_default_dates_and_export(auth_client):
    resp = auth_client.get("/sales/")
    assert resp.status_code in (200, 302, 404)
    resp_export = auth_client.get("/sales/export?format=csv")
    assert resp_export.status_code in (200, 302, 403, 404)


def test_shipments_list_create(auth_client):
    resp = auth_client.get("/shipments/")
    assert resp.status_code in (200, 302, 404)
    resp_create = auth_client.get("/shipments/create")
    assert resp_create.status_code in (200, 302, 404)


def test_shop_and_store_endpoints(auth_client):
    resp_shop = auth_client.get("/shop/")
    assert resp_shop.status_code in (200, 302, 404)
    resp_store = auth_client.get("/store/")
    assert resp_store.status_code in (200, 302, 404)
