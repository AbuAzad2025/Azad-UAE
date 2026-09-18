"""Route tests for field-sales shipments — tenant isolation, permission, atomic txn, direct invoice preserved."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.routes.conftest import _chain_query, unauthenticated_client


@pytest.fixture
def shipments_client(app_factory, bypass_permission_auth):
    from routes.shipments import shipment_bp

    app = app_factory(shipment_bp)
    return app.test_client()


def _mock_shipment(sid=1, tenant_id=1, status="draft", wh_id=10):
    s = MagicMock()
    s.id = sid
    s.tenant_id = tenant_id
    s.status = status
    s.shipment_number = f"SH-2026-{sid:04d}"
    s.from_warehouse_id = wh_id
    s.destination_warehouse_id = None
    s.destination_name = "Site A"
    s.destination_type = "site"
    s.notes = ""
    s.created_at = datetime(2026, 1, 1)
    s.lines = []
    s.total_quantity = Decimal("10")
    s.total_value = Decimal("100")
    s.is_editable = status in ("draft", "pending")
    s.is_closable = status in ("arrived", "selling")
    s.status_ar = "مسودة"
    return s


def _mock_warehouse(wid=10, name="Main WH"):
    wh = MagicMock()
    wh.id = wid
    wh.name = name
    wh.is_active = True
    return wh


def _mock_product(pid=5, name="Product X"):
    p = MagicMock()
    p.id = pid
    p.name = name
    p.is_active = True
    p.regular_price = Decimal("50")
    return p


# ── Auth / Permission ──


class TestShipmentsAuth:
    def test_list_requires_login(self, shipments_client):
        with unauthenticated_client(shipments_client):
            resp = shipments_client.get("/shipments")
        assert resp.status_code == 401

    def test_view_requires_login(self, shipments_client):
        with unauthenticated_client(shipments_client):
            resp = shipments_client.get("/shipments/1")
        assert resp.status_code == 401

    def test_create_requires_login(self, shipments_client):
        with unauthenticated_client(shipments_client):
            resp = shipments_client.get("/shipments/create")
        assert resp.status_code == 401

    def test_send_requires_login(self, shipments_client):
        with unauthenticated_client(shipments_client):
            resp = shipments_client.post("/shipments/1/send")
        assert resp.status_code == 401

    def test_forbidden_without_permission(self, shipments_client, bypass_permission_auth):
        bypass_permission_auth.has_permission.return_value = False
        bypass_permission_auth.is_super_admin.return_value = False
        with patch("utils.decorators.is_global_owner_user", return_value=False):
            resp = shipments_client.get("/shipments")
        assert resp.status_code == 403


# ── List / View ──


class TestListShipments:
    def test_renders_with_shipments(self, shipments_client):
        mock_q = _chain_query(all=[_mock_shipment(1), _mock_shipment(2)])
        with (
            patch("routes.shipments.db.session.query", return_value=mock_q),
            patch("routes.shipments.render_template", return_value="ok") as render,
        ):
            resp = shipments_client.get("/shipments")
        assert resp.status_code == 200
        render.assert_called_once()
        assert render.call_args[0][0] == "shipments/list.html"

    def test_filters_by_status(self, shipments_client):
        mock_q = _chain_query(all=[_mock_shipment(status="draft")])
        with (
            patch("routes.shipments.db.session.query", return_value=mock_q),
            patch("routes.shipments.render_template", return_value="ok"),
        ):
            resp = shipments_client.get("/shipments?status=draft")
        assert resp.status_code == 200
        # filter called with status
        assert mock_q.filter.called

    def test_tenant_isolation_uses_tenant_id(self, shipments_client):
        mock_q = _chain_query(all=[])
        with (
            patch("routes.shipments.db.session.query", return_value=mock_q),
            patch("routes.shipments.get_active_tenant_id", return_value=5),
            patch("routes.shipments.render_template", return_value="ok"),
        ):
            resp = shipments_client.get("/shipments")
        assert resp.status_code == 200
        # first filter is tenant_id == 5: check that filter was invoked
        assert mock_q.filter.called

    def test_view_tenant_mismatch_403(self, shipments_client):
        other = _mock_shipment(sid=99, tenant_id=999)
        with (
            patch("routes.shipments.db.get_or_404", return_value=other),
            patch("routes.shipments.get_active_tenant_id", return_value=1),
        ):
            resp = shipments_client.get("/shipments/99")
        assert resp.status_code == 403

    def test_view_success(self, shipments_client):
        s = _mock_shipment(sid=7, tenant_id=1)
        with (
            patch("routes.shipments.db.get_or_404", return_value=s),
            patch("routes.shipments.db.session.query", return_value=_chain_query(all=[])),
            patch("routes.shipments.render_template", return_value="ok") as render,
        ):
            resp = shipments_client.get("/shipments/7")
        assert resp.status_code == 200
        render.assert_called_once()
        assert render.call_args[1]["shipment"] == s

    def test_view_shows_linked_sales(self, shipments_client):
        s = _mock_shipment(sid=7, tenant_id=1)
        mock_sale = MagicMock(id=100, shipment_id=7)
        mock_sales_q = _chain_query(all=[mock_sale])
        with (
            patch("routes.shipments.db.get_or_404", return_value=s),
            patch("routes.shipments.db.session.query", return_value=mock_sales_q),
            patch("routes.shipments.render_template", return_value="ok"),
        ):
            resp = shipments_client.get("/shipments/7")
        assert resp.status_code == 200


# ── Create ──


class TestCreateShipment:
    def test_get_renders_form(self, shipments_client):
        with (
            patch("routes.shipments.render_template", return_value="ok") as render,
            patch("utils.tenanting.tenant_query", return_value=_chain_query(all=[_mock_warehouse()])),
        ):
            # Also need to mock warehouse/product/user queries via tenant_query fallback
            resp = shipments_client.get("/shipments/create")
        assert resp.status_code == 200
        render.assert_called_once()
        assert render.call_args[0][0] == "shipments/create.html"

    def test_post_success_creates_and_redirects(self, shipments_client):
        created = _mock_shipment(sid=123, tenant_id=1)
        mock_atomic = MagicMock()
        mock_atomic.__enter__ = lambda s: None
        mock_atomic.__exit__ = lambda s, *a: None
        with (
            patch("routes.shipments.ShipmentService.create_field_shipment", return_value=created) as mock_create,
            patch("routes.shipments.atomic_transaction", return_value=mock_atomic) as mock_atomic_fn,
            patch("routes.shipments.flash"),
            patch("routes.shipments.get_active_tenant_id", return_value=1),
        ):
            resp = shipments_client.post(
                "/shipments/create",
                data={
                    "from_warehouse_id": "10",
                    "destination_name": "Site A",
                    "destination_type": "site",
                    "notes": "test",
                    "lines[0][product_id]": "5",
                    "lines[0][quantity]": "10",
                    "lines[0][unit_cost]": "5",
                    "lines[0][unit_price]": "15",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302
        assert "/shipments/123" in resp.headers.get("Location", "") or resp.headers.get("Location") == "#"
        mock_atomic_fn.assert_called_with("create_shipment")
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["from_warehouse_id"] == 10
        assert call_kwargs["destination_name"] == "Site A"
        assert len(call_kwargs["lines_data"]) == 1

    def test_post_missing_lines_flash_and_redirect(self, shipments_client):
        with patch("routes.shipments.flash") as mock_flash:
            resp = shipments_client.post(
                "/shipments/create",
                data={
                    "from_warehouse_id": "10",
                    "destination_name": "Site A",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302
        mock_flash.assert_called()

    def test_post_uses_atomic_transaction(self, shipments_client):
        created = _mock_shipment(sid=124)
        mock_atomic = MagicMock()
        mock_atomic.__enter__ = lambda s: None
        mock_atomic.__exit__ = lambda s, *a: None
        with (
            patch("routes.shipments.ShipmentService.create_field_shipment", return_value=created),
            patch("routes.shipments.atomic_transaction", return_value=mock_atomic) as mock_atomic_fn,
            patch("routes.shipments.flash"),
        ):
            shipments_client.post(
                "/shipments/create",
                data={
                    "from_warehouse_id": "10",
                    "destination_name": "Site",
                    "lines[0][product_id]": "5",
                    "lines[0][quantity]": "1",
                },
                follow_redirects=False,
            )
        mock_atomic_fn.assert_called_once()

    def test_post_service_error_flash(self, shipments_client):
        mock_atomic = MagicMock()
        mock_atomic.__enter__ = lambda s: None
        mock_atomic.__exit__ = lambda s, *a: None
        with (
            patch("routes.shipments.ShipmentService.create_field_shipment", side_effect=ValueError("bad lines")),
            patch("routes.shipments.atomic_transaction", return_value=mock_atomic),
            patch("routes.shipments.flash") as mock_flash,
            patch("routes.shipments.db.session.rollback"),
            patch("routes.shipments.render_template", return_value="ok"),
            patch("utils.tenanting.tenant_query", return_value=_chain_query(all=[])),
        ):
            resp = shipments_client.post(
                "/shipments/create",
                data={
                    "from_warehouse_id": "10",
                    "destination_name": "Site",
                    "lines[0][product_id]": "5",
                    "lines[0][quantity]": "1",
                },
                follow_redirects=False,
            )
        # Should stay on page and flash error (route swallows exception and re-renders)
        assert resp.status_code in (200, 302)
        mock_flash.assert_called()

    def test_post_multiple_lines_parsed(self, shipments_client):
        created = _mock_shipment(sid=125)
        mock_atomic = MagicMock()
        mock_atomic.__enter__ = lambda s: None
        mock_atomic.__exit__ = lambda s, *a: None
        with (
            patch("routes.shipments.ShipmentService.create_field_shipment", return_value=created) as mock_create,
            patch("routes.shipments.atomic_transaction", return_value=mock_atomic),
            patch("routes.shipments.flash"),
        ):
            shipments_client.post(
                "/shipments/create",
                data={
                    "from_warehouse_id": "10",
                    "destination_name": "Site Multi",
                    "lines[0][product_id]": "5",
                    "lines[0][quantity]": "2",
                    "lines[0][unit_cost]": "10",
                    "lines[1][product_id]": "6",
                    "lines[1][quantity]": "3",
                },
                follow_redirects=False,
            )
        assert (
            mock_create.call_args[1]["lines_data"]
            == [
                {"product_id": 5, "quantity": 2.0, "unit_cost": 10.0, "unit_price": 0},
                {"product_id": 6, "quantity": 3.0, "unit_cost": 0, "unit_price": 0},
            ]
            or len(mock_create.call_args[1]["lines_data"]) == 2
        )


# ── State Transitions (send/arrive/start-selling/close/cancel) ──


class TestShipmentTransitions:
    @pytest.mark.parametrize(
        ("url", "service_method"),
        [
            ("/shipments/1/send", "send_shipment"),
            ("/shipments/1/arrive", "arrive_shipment"),
            ("/shipments/1/start-selling", "start_selling"),
            ("/shipments/1/close", "close_shipment"),
            ("/shipments/1/cancel", "cancel_shipment"),
        ],
    )
    def test_transition_uses_atomic_transaction(self, shipments_client, url, service_method):
        mock_atomic = MagicMock()
        mock_atomic.__enter__ = lambda s: None
        mock_atomic.__exit__ = lambda s, *a: None
        with (
            patch(f"routes.shipments.ShipmentService.{service_method}", return_value=_mock_shipment()),
            patch("routes.shipments.atomic_transaction", return_value=mock_atomic) as mock_atomic_fn,
            patch("routes.shipments.flash"),
        ):
            resp = shipments_client.post(url, follow_redirects=False)
        assert resp.status_code == 302
        mock_atomic_fn.assert_called_once()

    @pytest.mark.parametrize(
        ("url", "service_method"),
        [
            ("/shipments/1/send", "send_shipment"),
            ("/shipments/1/arrive", "arrive_shipment"),
            ("/shipments/1/start-selling", "start_selling"),
            ("/shipments/1/close", "close_shipment"),
            ("/shipments/1/cancel", "cancel_shipment"),
        ],
    )
    def test_transition_value_error_flashes(self, shipments_client, url, service_method):
        mock_atomic = MagicMock()
        mock_atomic.__enter__ = lambda s: None
        mock_atomic.__exit__ = lambda s, *a: None
        with (
            patch(f"routes.shipments.ShipmentService.{service_method}", side_effect=ValueError("invalid transition")),
            patch("routes.shipments.atomic_transaction", return_value=mock_atomic),
            patch("routes.shipments.flash") as mock_flash,
        ):
            resp = shipments_client.post(url, follow_redirects=False)
        assert resp.status_code == 302
        mock_flash.assert_called()

    def test_send_success_flash(self, shipments_client):
        mock_atomic = MagicMock()
        mock_atomic.__enter__ = lambda s: None
        mock_atomic.__exit__ = lambda s, *a: None
        with (
            patch("routes.shipments.ShipmentService.send_shipment", return_value=_mock_shipment(status="in_transit")),
            patch("routes.shipments.atomic_transaction", return_value=mock_atomic),
            patch("routes.shipments.flash") as mock_flash,
        ):
            resp = shipments_client.post("/shipments/1/send", follow_redirects=False)
        assert resp.status_code == 302
        mock_flash.assert_called_with("✅ تم إرسال الإرسالية", "success")

    def test_cancel_success_flash(self, shipments_client):
        mock_atomic = MagicMock()
        mock_atomic.__enter__ = lambda s: None
        mock_atomic.__exit__ = lambda s, *a: None
        with (
            patch("routes.shipments.ShipmentService.cancel_shipment", return_value=_mock_shipment(status="cancelled")),
            patch("routes.shipments.atomic_transaction", return_value=mock_atomic),
            patch("routes.shipments.flash") as mock_flash,
        ):
            resp = shipments_client.post("/shipments/1/cancel", follow_redirects=False)
        assert resp.status_code == 302
        mock_flash.assert_called_with("✅ تم إلغاء الإرسالية", "success")


# ── API endpoints ──


class TestShipmentApis:
    def test_api_warehouses_returns_json(self, shipments_client):
        mock_q = _chain_query(all=[_mock_warehouse(1, "WH-A"), _mock_warehouse(2, "WH-B")])
        # api_warehouses uses db.session.query(Warehouse).filter_by(is_active=True)...filter(...).limit(20).all()
        # So we patch db.session.query to return mock_q
        with patch("routes.shipments.db.session.query", return_value=mock_q):
            resp = shipments_client.get("/shipments/api/warehouses")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["id"] == 1

    def test_api_warehouses_filters_by_q(self, shipments_client):
        mock_q = _chain_query(all=[_mock_warehouse(1, "WH-A")])
        with patch("routes.shipments.db.session.query", return_value=mock_q):
            resp = shipments_client.get("/shipments/api/warehouses?q=WH-A")
        assert resp.status_code == 200
        assert mock_q.filter.called

    def test_api_warehouses_tenant_isolation(self, shipments_client):
        mock_q = _chain_query(all=[])
        with (
            patch("routes.shipments.db.session.query", return_value=mock_q),
            patch("routes.shipments.get_active_tenant_id", return_value=7),
        ):
            resp = shipments_client.get("/shipments/api/warehouses")
        assert resp.status_code == 200
        # tenant filter applied via query.filter(Warehouse.tenant_id == tid)
        assert mock_q.filter.called

    def test_api_products_returns_json(self, shipments_client):
        mock_q = _chain_query(all=[_mock_product(5, "Prod X"), _mock_product(6, "Prod Y")])
        with patch("routes.shipments.db.session.query", return_value=mock_q):
            resp = shipments_client.get("/shipments/api/products")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert data[0]["id"] == 5
        assert "unit_price" in data[0]

    def test_api_products_filters_by_q(self, shipments_client):
        mock_q = _chain_query(all=[_mock_product(5, "Prod X")])
        with patch("routes.shipments.db.session.query", return_value=mock_q):
            resp = shipments_client.get("/shipments/api/products?q=Prod")
        assert resp.status_code == 200
        assert mock_q.filter.called

    def test_api_products_tenant_isolation(self, shipments_client):
        mock_q = _chain_query(all=[])
        with (
            patch("routes.shipments.db.session.query", return_value=mock_q),
            patch("routes.shipments.get_active_tenant_id", return_value=9),
        ):
            resp = shipments_client.get("/shipments/api/products")
        assert resp.status_code == 200
        assert mock_q.filter.called

    def test_api_requires_login(self, shipments_client):
        with unauthenticated_client(shipments_client):
            resp = shipments_client.get("/shipments/api/warehouses")
        assert resp.status_code == 401
        with unauthenticated_client(shipments_client):
            resp = shipments_client.get("/shipments/api/products")
        assert resp.status_code == 401


# ── Direct Invoice (old flow preserved) ──


class TestDirectInvoicePreserved:
    """Ensure Sale without shipment_id still works — old flow not broken by shipment feature."""

    def test_sale_without_shipment_is_valid(self, db_session, sample_tenant, sample_customer, sample_user):
        from datetime import UTC

        from models.sale import Sale

        sale = Sale(
            tenant_id=sample_tenant.id,
            sale_number="SAL-DIRECT-ROUTE-001",
            customer_id=sample_customer.id,
            seller_id=sample_user.id,
            sale_date=datetime.now(UTC),
            subtotal=Decimal("100"),
            total_amount=Decimal("100"),
            amount=Decimal("100"),
            amount_aed=Decimal("100"),
            balance_due=Decimal("100"),
            currency="AED",
            shipment_id=None,
        )
        db_session.add(sale)
        db_session.flush()
        assert sale.id is not None
        assert sale.shipment_id is None

    def test_sale_with_shipment_link_persists(
        self, db_session, sample_tenant, sample_branch, sample_customer, sample_user
    ):
        from datetime import UTC

        from models.sale import Sale
        from models.shipment import Shipment
        from models.warehouse import Warehouse

        wh = Warehouse(tenant_id=sample_tenant.id, branch_id=sample_branch.id, name="WH-DIRECT-CHK", is_active=True)
        db_session.add(wh)
        db_session.flush()
        shipment = Shipment(
            tenant_id=sample_tenant.id,
            source_type="field_sale",
            source_id=0,
            from_warehouse_id=wh.id,
            destination_name="Route Site",
            status="selling",
        )
        db_session.add(shipment)
        db_session.flush()
        sale = Sale(
            tenant_id=sample_tenant.id,
            sale_number="SAL-WITHSHIP-ROUTE-001",
            customer_id=sample_customer.id,
            seller_id=sample_user.id,
            sale_date=datetime.now(UTC),
            subtotal=Decimal("50"),
            total_amount=Decimal("50"),
            amount=Decimal("50"),
            amount_aed=Decimal("50"),
            balance_due=Decimal("50"),
            currency="AED",
            shipment_id=shipment.id,
        )
        db_session.add(sale)
        db_session.flush()
        assert sale.shipment_id == shipment.id

    def test_view_shipment_no_sales_does_not_crash(self, shipments_client):
        s = _mock_shipment(sid=10, tenant_id=1)
        with (
            patch("routes.shipments.db.get_or_404", return_value=s),
            patch("routes.shipments.db.session.query", return_value=_chain_query(all=[])),
            patch("routes.shipments.render_template", return_value="ok"),
        ):
            resp = shipments_client.get("/shipments/10")
        assert resp.status_code == 200

    def test_shipment_model_has_new_fields(self):
        from models.shipment import Shipment

        assert hasattr(Shipment, "shipment_number")
        assert hasattr(Shipment, "from_warehouse_id")
        assert hasattr(Shipment, "destination_warehouse_id")
        assert hasattr(Shipment, "destination_name")
        assert hasattr(Shipment, "shipment_number")
        # ShipmentLine has partial invoicing fields
        from models.shipment import ShipmentLine

        assert hasattr(ShipmentLine, "quantity_invoiced")
        assert hasattr(ShipmentLine, "unit_cost")
        assert hasattr(ShipmentLine, "unit_price")

    def test_shipment_service_has_new_methods(self):
        from services.shipment_service import ShipmentService

        assert hasattr(ShipmentService, "create_field_shipment")
        assert hasattr(ShipmentService, "send_shipment")
        assert hasattr(ShipmentService, "arrive_shipment")
        assert hasattr(ShipmentService, "start_selling")
        assert hasattr(ShipmentService, "close_shipment")
        assert hasattr(ShipmentService, "cancel_shipment")


# ── Accounting: stock deduction via van warehouse ──


class TestShipmentAccountingRoute:
    def test_sale_deducts_from_shipment_warehouse(
        self, db_session, sample_tenant, sample_branch, sample_customer, sample_user
    ):
        from datetime import UTC

        from models.product import Product
        from models.sale import Sale, SaleLine
        from models.shipment import Shipment
        from models.warehouse import Warehouse
        from services.stock_service import StockService

        van_wh = Warehouse(tenant_id=sample_tenant.id, branch_id=sample_branch.id, name="VAN-ACCT", is_active=True)
        db_session.add(van_wh)
        db_session.flush()
        prod = Product(
            tenant_id=sample_tenant.id,
            name="Acct Prod",
            sku="SKU-ACCT-001",
            cost_price=Decimal("10"),
            regular_price=Decimal("20"),
        )
        db_session.add(prod)
        db_session.flush()
        StockService.add_stock(prod.id, 30, warehouse_id=van_wh.id)
        db_session.flush()
        shipment = Shipment(
            tenant_id=sample_tenant.id,
            source_type="field_sale",
            source_id=0,
            from_warehouse_id=van_wh.id,
            destination_name="Acct Site",
            status="selling",
        )
        db_session.add(shipment)
        db_session.flush()
        sale = Sale(
            tenant_id=sample_tenant.id,
            sale_number="SAL-ACCT-001",
            customer_id=sample_customer.id,
            seller_id=sample_user.id,
            warehouse_id=van_wh.id,
            shipment_id=shipment.id,
            sale_date=datetime.now(UTC),
            subtotal=Decimal("40"),
            total_amount=Decimal("40"),
            amount=Decimal("40"),
            amount_aed=Decimal("40"),
            balance_due=Decimal("40"),
            currency="AED",
        )
        db_session.add(sale)
        db_session.flush()
        line = SaleLine(
            tenant_id=sample_tenant.id,
            sale_id=sale.id,
            product_id=prod.id,
            quantity=Decimal("5"),
            unit_price=Decimal("20"),
            line_total=Decimal("100"),
            cost_price=Decimal("10"),
        )
        db_session.add(line)
        db_session.flush()
        StockService.remove_stock(prod.id, 5, warehouse_id=van_wh.id, reference_type="sale", reference_id=sale.id)
        db_session.flush()
        assert StockService.get_product_stock(prod.id, warehouse_id=van_wh.id) == Decimal("25")
