"""Partner-only prices follow the tenant's ``enable_partners`` flag.

Product lookup is a shared endpoint (POS, sales and purchase forms), so the
whole route must keep working. Only the module-specific price fields are
redacted when the partner module is locked, mirroring the 403 on the partner
blueprint's own screens.
"""

from __future__ import annotations

from decimal import Decimal


class TestPartnerPriceRedaction:
    @staticmethod
    def _row(auth_client, path, sku):
        payload = auth_client.get(path).get_json()
        return next(r for r in payload["data"]["results"] if r.get("sku") == sku)

    @staticmethod
    def _prices(product, merchant="80.000", partner="70.000"):
        product.merchant_price = Decimal(merchant)
        product.partner_price = Decimal(partner)

    def test_api_products_includes_prices_when_enabled(self, auth_client, db_session, sample_tenant, sample_product):
        self._prices(sample_product)
        sample_tenant.enable_partners = True
        db_session.flush()

        row = self._row(auth_client, "/api/products", sample_product.sku)
        assert row["merchant_price"] == 80.0
        assert row["partner_price"] == 70.0

    def test_api_products_omits_prices_when_disabled(self, auth_client, db_session, sample_tenant, sample_product):
        self._prices(sample_product)
        sample_tenant.enable_partners = False
        db_session.flush()

        row = self._row(auth_client, "/api/products", sample_product.sku)
        assert "merchant_price" not in row
        assert "partner_price" not in row

    def test_api_search_products_omits_prices_when_disabled(
        self, auth_client, db_session, sample_tenant, sample_product
    ):
        self._prices(sample_product)
        sample_tenant.enable_partners = False
        db_session.flush()

        path = f"/api/search?type=products&q={sample_product.sku}"
        row = self._row(auth_client, path, sample_product.sku)
        assert "merchant_price" not in row
        assert "partner_price" not in row

    def test_api_product_info_omits_prices_when_disabled(self, auth_client, db_session, sample_tenant, sample_product):
        self._prices(sample_product)
        sample_tenant.enable_partners = False
        db_session.flush()

        data = auth_client.get(f"/api/products/{sample_product.id}/info").get_json()["data"]
        assert "merchant_price" not in data
        assert "partner_price" not in data

    def test_api_product_info_includes_prices_when_enabled(
        self, auth_client, db_session, sample_tenant, sample_product
    ):
        self._prices(sample_product)
        sample_tenant.enable_partners = True
        db_session.flush()

        data = auth_client.get(f"/api/products/{sample_product.id}/info").get_json()["data"]
        assert data["merchant_price"] == 80.0
        assert data["partner_price"] == 70.0

    def test_partner_screens_still_403_when_disabled(self, auth_client, db_session, sample_tenant):
        sample_tenant.enable_partners = False
        db_session.flush()
        assert auth_client.get("/partners/").status_code == 403
