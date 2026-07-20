"""API routes — telemetry origin policy and core endpoints."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def api_client(app_factory, mocker):
    user = MagicMock(is_authenticated=True, tenant_id=1, id=1)
    user.has_permission.return_value = True
    mocker.patch("flask_login.utils._get_user", return_value=user)
    mocker.patch("extensions.limiter.limit", return_value=lambda f: f)
    mocker.patch("utils.tenanting.get_active_tenant_id", return_value=1)
    from routes.api import api_bp

    app = app_factory(
        api_bp,
        config_overrides={
            "APP_ENV": "development",
            "DEBUG": True,
            "CLIENT_ERROR_TRUSTED_ORIGINS": ["http://localhost:5000"],
        },
    )
    return app.test_client()


class TestApiHelpers:
    def test_is_production_env(self, app, monkeypatch):
        from routes.api import _is_production_env

        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("DEBUG", "false")
        app.config.update(APP_ENV="production", DEBUG=False)
        with app.app_context():
            assert _is_production_env() is True

    def test_origin_from_referer(self):
        from routes.api import _origin_from_referer

        assert _origin_from_referer("https://app.test/page") == "https://app.test"
        assert _origin_from_referer("bad") is None

    def test_split_origins(self):
        from routes.api import _split_origins

        assert _split_origins("http://a.com/, http://b.com") == {
            "http://a.com",
            "http://b.com",
        }
        assert _split_origins(["http://x.com/"]) == {"http://x.com"}
        assert _split_origins("") == set()

    def test_trusted_telemetry_origins_dev_default(self, app):
        from routes.api import _trusted_telemetry_origins

        app.config.update(APP_ENV="development", DEBUG=True)
        with app.app_context():
            origins = _trusted_telemetry_origins()
            assert "http://localhost:5000" in origins

    def test_trusted_telemetry_origins_production_base_url(self, app, monkeypatch):
        from routes.api import _trusted_telemetry_origins

        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("DEBUG", "false")
        for key in (
            "CLIENT_ERROR_TRUSTED_ORIGINS",
            "TRUSTED_ORIGINS",
            "CORS_ORIGINS",
            "PAYMENT_VAULT_TRUSTED_ORIGINS",
        ):
            monkeypatch.delenv(key, raising=False)
        app.config.update(
            APP_ENV="production",
            DEBUG=False,
            BASE_URL="https://app.example.com",
            CLIENT_ERROR_TRUSTED_ORIGINS=None,
            TRUSTED_ORIGINS=None,
            CORS_ORIGINS=None,
            PAYMENT_VAULT_TRUSTED_ORIGINS=None,
        )
        with app.app_context():
            origins = _trusted_telemetry_origins()
            assert "https://app.example.com" in origins

    def test_validate_telemetry_no_origin_in_dev(self, app):
        from routes.api import _validate_public_telemetry_origin

        app.config.update(APP_ENV="development", DEBUG=True)
        with app.app_context():
            assert _validate_public_telemetry_origin() is None

    def test_validate_telemetry_referer_trusted(self, app):
        from routes.api import _validate_public_telemetry_origin

        app.config.update(
            APP_ENV="production",
            DEBUG=False,
            CLIENT_ERROR_TRUSTED_ORIGINS=["https://shop.example.com"],
        )
        with app.test_request_context(
            headers={"Referer": "https://shop.example.com/cart"},
        ):
            assert _validate_public_telemetry_origin() is None

    def test_validate_telemetry_no_trusted_origins(self, app, mocker):
        from routes.api import _validate_public_telemetry_origin

        mocker.patch("routes.api._trusted_telemetry_origins", return_value=frozenset())
        with app.test_request_context(headers={"Origin": "https://app.test"}):
            resp, code = _validate_public_telemetry_origin()
            assert code == 503

    def test_scoped_customer_balance_scoped(self, mocker):
        mocker.patch("routes.api.branch_scope_id", return_value=2)
        mocker.patch(
            "routes.api.PaymentService.get_customer_balance_scoped",
            return_value=Decimal("42.5"),
        )
        from routes.api import _customer_balance

        assert _customer_balance(5) == 42.5

    def test_validate_telemetry_missing_origin_production(self, app, mocker):
        from routes.api import _validate_public_telemetry_origin

        mocker.patch("routes.api._is_production_env", return_value=True)
        mocker.patch(
            "routes.api._trusted_telemetry_origins",
            return_value=frozenset({"https://app.test"}),
        )
        with app.test_request_context():
            resp, code = _validate_public_telemetry_origin()
            assert code == 403

    def test_scoped_customer_query_branch_scoped(self, mocker):
        mocker.patch("routes.api.branch_scope_id", return_value=3)
        mocker.patch("routes.api.get_active_tenant_id", return_value=1)
        customer_q = MagicMock()
        customer_q.filter.return_value = customer_q
        mocker.patch("routes.api.Customer.query", customer_q)
        from routes.api import _scoped_customer_query

        _scoped_customer_query()
        customer_q.filter.assert_called()

    def test_scoped_supplier_query_branch_scoped(self, mocker):
        mocker.patch("routes.api.branch_scope_id", return_value=3)
        mocker.patch("routes.api.get_active_tenant_id", return_value=1)
        supplier_q = MagicMock()
        supplier_q.filter.return_value = supplier_q
        mocker.patch("routes.api.Supplier.query", supplier_q)
        from routes.api import _scoped_supplier_query

        _scoped_supplier_query()
        supplier_q.filter.assert_called()

    def test_scoped_customer_query_unscoped_branch(self, mocker):
        mocker.patch("routes.api.branch_scope_id", return_value=None)
        mocker.patch("routes.api.get_active_tenant_id", return_value=1)
        customer_q = MagicMock()
        customer_q.filter.return_value = customer_q
        mocker.patch("routes.api.Customer.query", customer_q)
        from routes.api import _scoped_customer_query

        result = _scoped_customer_query()
        assert result is customer_q

    def test_scoped_supplier_query_unscoped_branch(self, mocker):
        mocker.patch("routes.api.branch_scope_id", return_value=None)
        mocker.patch("routes.api.get_active_tenant_id", return_value=1)
        supplier_q = MagicMock()
        supplier_q.filter.return_value = supplier_q
        mocker.patch("routes.api.Supplier.query", supplier_q)
        from routes.api import _scoped_supplier_query

        result = _scoped_supplier_query()
        assert result is supplier_q

    def test_customer_balance_no_customer(self, mocker):
        mocker.patch("routes.api.branch_scope_id", return_value=None)
        mocker.patch("routes.api._scoped_customer_query").return_value.filter.return_value.first.return_value = None
        from routes.api import _customer_balance

        assert _customer_balance(1) == 0.0

    def test_supplier_balance_scoped(self, mocker):
        mocker.patch("routes.api.branch_scope_id", return_value=2)
        mocker.patch(
            "routes.api.PaymentService.get_supplier_balance_scoped",
            return_value=Decimal("7"),
        )
        from routes.api import _supplier_balance

        assert _supplier_balance(4) == 7.0

    def test_scoped_supplier_balance_unscoped(self, mocker):
        supplier = MagicMock()
        supplier.get_balance_aed.return_value = Decimal("10")
        mocker.patch("routes.api.branch_scope_id", return_value=None)
        mocker.patch("routes.api._scoped_supplier_query").return_value.filter.return_value.first.return_value = supplier
        from routes.api import _supplier_balance

        assert _supplier_balance(3) == 10.0


class TestApiEndpoints:
    def test_health(self, api_client):
        resp = api_client.get("/api/health")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"

    def test_version(self, api_client):
        resp = api_client.get("/api/version")
        assert resp.status_code == 200
        assert "version" in resp.get_json()

    def test_echo(self, api_client):
        resp = api_client.put("/api/echo", json={"hello": "world"})
        assert resp.status_code == 200
        assert resp.get_json()["data"]["hello"] == "world"

    def test_log_client_error_rejects_unknown_origin(self, api_client):
        resp = api_client.post(
            "/api/log-client-error",
            json={"message": "x"},
            headers={"Origin": "http://evil.test"},
        )
        assert resp.status_code in (403, 503)

    def test_log_client_error_accepts_trusted_origin(self, api_client, mocker):
        mocker.patch("services.logging_core.LoggingCore.log_frontend_error")
        resp = api_client.post(
            "/api/log-client-error",
            json={"message": "err", "type": "api", "lineno": 1, "status": 500},
            headers={"Origin": "http://localhost:5000"},
        )
        assert resp.status_code == 204

    def test_log_client_error_unknown_event_type(self, api_client, mocker):
        mocker.patch("services.logging_core.LoggingCore.log_frontend_error")
        resp = api_client.post(
            "/api/log-client-error",
            json={"message": "err", "type": "not-a-real-type"},
            headers={"Origin": "http://localhost:5000"},
        )
        assert resp.status_code == 204

    def test_log_client_error_payload_too_large(self, api_client):
        resp = api_client.post(
            "/api/log-client-error",
            data="x" * (60 * 1024),
            content_type="application/json",
            headers={"Origin": "http://localhost:5000"},
        )
        assert resp.status_code == 413

    def test_currencies(self, api_client, mocker):
        mocker.patch(
            "services.currency_service.CurrencyService.get_supported_currencies",
            return_value=["AED"],
        )
        mocker.patch(
            "services.currency_service.CurrencyService.get_currency_label",
            return_value="AED",
        )
        mocker.patch(
            "services.currency_service.CurrencyService.COMMON_CURRENCIES",
            ["AED"],
        )
        resp = api_client.get("/api/currencies")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_payment_fields(self, api_client):
        resp = api_client.get("/api/payment-fields/cheque")
        assert resp.status_code == 200
        assert resp.get_json()["en_title"] == "Cheque Payment"

    def test_currency_rate_success(self, api_client, mocker):
        mocker.patch(
            "services.currency_service.CurrencyService.get_exchange_rate_details",
            return_value={
                "rate": Decimal("3.67"),
                "source": "ecb",
                "cached": True,
                "age_seconds": 5,
            },
        )
        resp = api_client.get("/api/currency-rate/USD/AED")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_currency_rate_failure(self, api_client, mocker):
        mocker.patch(
            "services.currency_service.CurrencyService.get_exchange_rate_details",
            side_effect=ValueError("no rate"),
        )
        resp = api_client.get("/api/currency-rate/USD/AED")
        assert resp.status_code == 400

    def test_check_username_short(self, api_client):
        resp = api_client.get("/api/check-username?username=ab")
        assert resp.get_json()["available"] is False

    def test_check_username_invalid_pattern(self, api_client):
        resp = api_client.get("/api/check-username?username=bad-name!")
        assert resp.get_json()["available"] is False
        assert "error" in resp.get_json()

    def test_check_username_taken(self, api_client, mocker):
        mocker.patch(
            "routes.api.User.query"
        ).filter_by.return_value.filter.return_value.first.return_value = MagicMock()
        resp = api_client.get("/api/check-username?username=existing_user")
        assert resp.get_json()["available"] is False

    def test_check_username_available(self, api_client, mocker):
        mocker.patch("routes.api.User.query").filter_by.return_value.filter.return_value.first.return_value = None
        resp = api_client.get("/api/check-username?username=valid_user")
        assert resp.get_json()["available"] is True

    def test_products_low_stock(self, api_client, mocker):
        product = SimpleNamespace(
            id=1,
            name="Low",
            sku="L1",
            current_stock=1,
            min_stock_alert=10,
            visible_stock=1,
        )
        mocker.patch("routes.api.StockService.get_low_stock_products", return_value=[product])
        resp = api_client.get("/api/products/low-stock")
        assert resp.status_code == 200
        assert resp.get_json()["count"] == 1

    def test_products_low_stock_failure(self, api_client, mocker):
        mocker.patch(
            "routes.api.StockService.get_low_stock_products",
            side_effect=RuntimeError("db"),
        )
        resp = api_client.get("/api/products/low-stock")
        assert resp.status_code == 500

    def test_exchange_rates_display(self, api_client, mocker):
        mocker.patch(
            "services.exchange_rate_service.ExchangeRateService.get_online_rates_for_display",
            return_value={"base": "USD", "rates": {}},
        )
        resp = api_client.get("/api/exchange-rates/display?base=USD&symbols=AED")
        assert resp.status_code == 200

    def test_industry_fields(self, api_client, mocker):
        field = SimpleNamespace(
            field_code="vat",
            field_name_ar="ضريبة",
            field_name_en="VAT",
            field_type="text",
            is_required=True,
        )
        mocker.patch(
            "services.industry_service.IndustryService.get_fields_for",
            return_value=[field],
        )
        resp = api_client.get("/api/industry-fields?industry=retail")
        assert resp.status_code == 200
        assert resp.get_json()["fields"][0]["field_code"] == "vat"

    def test_search_products(self, api_client, mocker):
        product = SimpleNamespace(
            id=1,
            name="Widget",
            sku="W1",
            barcode="111",
            regular_price=Decimal("10"),
            merchant_price=None,
            partner_price=None,
            cost_price=Decimal("5"),
            unit="pc",
            current_stock=Decimal("3"),
            has_serial_number=False,
        )
        product.is_low_stock = lambda: False
        products_q = MagicMock()
        products_q.filter.return_value = products_q
        products_q.order_by.return_value = products_q
        products_q.limit.return_value.all.return_value = [product]
        mocker.patch(
            "routes.api.StockService.get_visible_products_query",
            return_value=products_q,
        )
        mocker.patch("routes.api.get_accessible_warehouse_ids", return_value=[1])
        mocker.patch("routes.api.get_branch_stock_map", return_value={1: Decimal("3")})
        resp = api_client.get("/api/search?q=Widget&type=products")
        assert resp.status_code == 200
        assert resp.get_json()["results"][0]["name"] == "Widget"

    def test_search_suppliers(self, api_client, mocker):
        supplier = SimpleNamespace(
            id=2,
            name="Sup",
            company_name="Co",
            phone="050",
            email="a@t.com",
            supplier_type="local",
            rating=5,
            is_verified=True,
        )
        supplier.get_type_display = lambda: "Local"
        base_q = MagicMock()
        base_q.filter.return_value = base_q
        base_q.order_by.return_value = base_q
        base_q.limit.return_value.offset.return_value.all.return_value = [supplier]
        mocker.patch("routes.api._scoped_supplier_query", return_value=base_q)
        mocker.patch("routes.api._supplier_balance", return_value=0.0)
        resp = api_client.get("/api/search?q=Sup&type=suppliers")
        assert resp.status_code == 200
        assert resp.get_json()["results"][0]["id"] == 2

    def test_search_customers(self, api_client, mocker):
        customer = SimpleNamespace(
            id=3,
            name="Cust",
            phone="050",
            email="c@t.com",
            customer_type="retail",
        )
        base_q = MagicMock()
        base_q.filter.return_value = base_q
        base_q.order_by.return_value = base_q
        base_q.limit.return_value.offset.return_value.all.return_value = [customer]
        mocker.patch("routes.api._scoped_customer_query", return_value=base_q)
        mocker.patch("routes.api._customer_balance", return_value=12.0)
        resp = api_client.get("/api/search?q=Cust&type=customers")
        assert resp.status_code == 200
        assert resp.get_json()["results"][0]["balance_aed"] == 12.0

    def test_product_info(self, api_client, mocker):
        product = SimpleNamespace(
            id=9,
            tenant_id=1,
            name="P",
            sku="S",
            barcode="B",
            regular_price=Decimal("20"),
            current_stock=Decimal("4"),
            unit="pc",
            min_stock_alert=Decimal("1"),
        )
        mocker.patch("routes.api.db.session.get", return_value=product)
        mocker.patch("routes.api.get_branch_stock_map", return_value={9: Decimal("4")})
        mocker.patch("utils.branching.ensure_warehouse_access", return_value=MagicMock(id=1))
        resp = api_client.get("/api/products/9/info?warehouse_id=1")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_product_info_cross_tenant(self, api_client, mocker):
        product = MagicMock(id=9, tenant_id=99)
        mocker.patch("routes.api.db.session.get", return_value=product)
        resp = api_client.get("/api/products/9/info")
        assert resp.status_code == 404

    def test_product_by_barcode(self, api_client, mocker):
        product = SimpleNamespace(id=4, name="Bar", sku="SKU")
        mocker.patch("routes.api.Product.query").filter.return_value.filter.return_value.first.return_value = product
        resp = api_client.get("/api/products/barcode/ABC123")
        assert resp.status_code == 200

    def test_barcode_validate(self, api_client, mocker):
        mocker.patch("routes.api.Product.query").filter.return_value.filter.return_value.first.return_value = None
        resp = api_client.get("/api/barcode/validate?code=NEW123")
        assert resp.get_json()["valid"] is True

    def test_barcode_validate_empty(self, api_client):
        resp = api_client.get("/api/barcode/validate?code=")
        data = resp.get_json()
        assert data["valid"] is False
        assert data["exists"] is False

    def test_warehouses(self, api_client, mocker):
        import routes.api as api_module

        wh = SimpleNamespace(id=1, name="Main")
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.all.return_value = [wh]
        mocker.patch.object(api_module, "get_accessible_warehouses", return_value=mock_q, create=True)
        resp = api_client.get("/api/warehouses?q=Main")
        assert resp.status_code == 200

    def test_products_list(self, api_client, mocker):
        product = SimpleNamespace(
            id=1,
            name="Item",
            sku="SKU",
            barcode=None,
            regular_price=Decimal("5"),
            current_stock=Decimal("2"),
        )
        products_q = MagicMock()
        products_q.filter.return_value = products_q
        products_q.order_by.return_value = products_q
        products_q.limit.return_value.all.return_value = [product]
        mocker.patch(
            "routes.api.StockService.get_visible_products_query",
            return_value=products_q,
        )
        mocker.patch("routes.api.get_accessible_warehouse_ids", return_value=[1])
        mocker.patch("routes.api.get_branch_stock_map", return_value={1: Decimal("2")})
        resp = api_client.get("/api/products?q=Item")
        assert resp.status_code == 200

    def test_search_products_purchase_purpose(self, api_client, mocker):
        product = SimpleNamespace(
            id=2,
            name="Buy",
            sku="B1",
            barcode=None,
            regular_price=Decimal("1"),
            merchant_price=None,
            partner_price=None,
            cost_price=Decimal("1"),
            unit="pc",
            current_stock=Decimal("1"),
            has_serial_number=False,
        )
        product.is_low_stock = lambda: False
        products_q = MagicMock()
        products_q.filter.return_value = products_q
        products_q.order_by.return_value = products_q
        products_q.limit.return_value.all.return_value = [product]
        mocker.patch("routes.api.Product.query").filter.return_value = products_q
        mocker.patch("routes.api.get_accessible_warehouse_ids", return_value=[])
        resp = api_client.get("/api/search?q=Buy&type=products&purpose=purchase")
        assert resp.status_code == 200

    def test_product_info_missing(self, api_client, mocker):
        mocker.patch("routes.api.db.session.get", return_value=None)
        resp = api_client.get("/api/products/404/info")
        assert resp.status_code == 404

    def test_product_info_warehouse_forbidden(self, api_client, mocker):
        product = SimpleNamespace(
            id=9,
            tenant_id=1,
            name="P",
            sku="S",
            barcode="B",
            regular_price=Decimal("20"),
            current_stock=Decimal("4"),
            unit="pc",
            min_stock_alert=Decimal("1"),
        )
        mocker.patch("routes.api.db.session.get", return_value=product)
        mocker.patch("utils.branching.ensure_warehouse_access", side_effect=ValueError("denied"))
        resp = api_client.get("/api/products/9/info?warehouse_id=1")
        assert resp.status_code == 403

    def test_product_by_barcode_not_found(self, api_client, mocker):
        mocker.patch("routes.api.Product.query").filter.return_value.filter.return_value.first.return_value = None
        resp = api_client.get("/api/products/barcode/MISSING")
        assert resp.status_code == 404

    def test_exchange_rates_default_symbols(self, api_client, mocker):
        mocker.patch(
            "services.exchange_rate_service.ExchangeRateService.get_online_rates_for_display",
            return_value={"base": "USD"},
        )
        resp = api_client.get("/api/exchange-rates/display")
        assert resp.status_code == 200

    def test_echo_hidden_in_production(self, api_client, mocker):
        mocker.patch("routes.api._is_production_env", return_value=True)
        resp = api_client.put("/api/echo", json={"x": 1})
        assert resp.status_code == 404

    def test_origin_from_referer_exception(self, monkeypatch):
        from routes.api import _origin_from_referer

        def _boom(_):
            raise ValueError("parse fail")

        monkeypatch.setattr("routes.api.urlparse", _boom)
        assert _origin_from_referer("http://example.com") is None

    def test_trusted_origins_dev_fallback(self, app, monkeypatch):
        from routes.api import _DEV_TRUSTED_ORIGINS, _trusted_telemetry_origins

        app.config.update(APP_ENV="development", DEBUG=True)
        for key in (
            "CLIENT_ERROR_TRUSTED_ORIGINS",
            "TRUSTED_ORIGINS",
            "CORS_ORIGINS",
            "PAYMENT_VAULT_TRUSTED_ORIGINS",
        ):
            app.config[key] = None
            monkeypatch.delenv(key, raising=False)
        with app.app_context():
            origins = _trusted_telemetry_origins()
            assert origins == _DEV_TRUSTED_ORIGINS

    def test_validate_telemetry_rejected_referer(self, app, mocker):
        from routes.api import _validate_public_telemetry_origin

        mocker.patch("routes.api._is_production_env", return_value=True)
        mocker.patch(
            "routes.api._trusted_telemetry_origins",
            return_value=frozenset({"https://trusted.test"}),
        )
        with app.test_request_context(headers={"Referer": "https://evil.test/page"}):
            resp, code = _validate_public_telemetry_origin()
            assert code == 403

    def test_search_warehouses_endpoint(self, api_client, mocker):
        import routes.api as api_module

        wh = SimpleNamespace(id=2, name="Branch WH")
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.all.return_value = [wh]
        mocker.patch.object(api_module, "get_accessible_warehouses", return_value=mock_q)
        resp = api_client.get("/api/search_warehouses?q=Branch")
        assert resp.status_code == 200
        assert resp.get_json()["results"][0]["id"] == 2

    def test_warehouse_products_endpoint(self, api_client, mocker):
        product = SimpleNamespace(
            id=3,
            name="Stocked",
            sku="STK",
            barcode=None,
            regular_price=Decimal("8"),
            current_stock=Decimal("12"),
        )
        products_q = MagicMock()
        products_q.filter.return_value = products_q
        products_q.order_by.return_value = products_q
        products_q.limit.return_value.all.return_value = [product]
        mocker.patch(
            "routes.api.StockService.get_visible_products_query",
            return_value=products_q,
        )
        mocker.patch("routes.api.get_branch_stock_map", return_value={3: Decimal("12")})
        resp = api_client.get("/api/warehouses/1/products?q=Stocked")
        assert resp.status_code == 200
        assert resp.get_json()["results"][0]["id"] == 3
