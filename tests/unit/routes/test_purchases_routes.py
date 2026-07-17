from contextlib import contextmanager
from decimal import ROUND_HALF_UP, Decimal
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.routes.conftest import _chain_query, unauthenticated_client


def _mock_purchase(**kwargs):
    purchase = MagicMock()
    purchase.id = kwargs.get("id", 1)
    purchase.branch_id = kwargs.get("branch_id", 1)
    purchase.tenant_id = kwargs.get("tenant_id", 1)
    purchase.purchase_number = kwargs.get("purchase_number", "PO-001")
    purchase.status = kwargs.get("status", "confirmed")
    purchase.notes = kwargs.get("notes", "")
    purchase.supplier_id = kwargs.get("supplier_id")
    purchase.amount_aed = kwargs.get("amount_aed", Decimal("0"))
    purchase.get_paid_amount.return_value = kwargs.get("paid_amount", Decimal("0"))
    return purchase


@contextmanager
def _atomic_transaction_mock():
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=None)
    cm.__exit__ = MagicMock(return_value=False)
    with patch("routes.purchases.atomic_transaction", return_value=cm):
        yield cm


@contextmanager
def _purchase_patches(
    purchase=None,
    pag_items=None,
    branch_scope=None,
    warehouses=None,
):
    purchase = purchase or _mock_purchase()
    pag_items = pag_items if pag_items is not None else [purchase]
    query = _chain_query(all=pag_items, count=len(pag_items))

    with (
        patch("routes.purchases.tenant_query", return_value=query),
        patch("routes.purchases.tenant_get_or_404", return_value=purchase),
        patch("routes.purchases.render_template", return_value="ok") as render,
        patch("utils.decorators.branch_scope_id", return_value=branch_scope),
        patch("routes.purchases.db.session") as session,
        patch("routes.purchases.LoggingCore.log_audit") as log_audit,
        patch("routes.purchases.should_show_all_branch_columns", return_value=True),
        patch("routes.purchases.PurchaseService") as purchase_service,
        patch(
            "routes.purchases.CurrencyService.get_all_rates", return_value={"AED": 1.0}
        ),
        patch(
            "routes.purchases.get_accessible_warehouses", return_value=warehouses or []
        ),
        patch("routes.purchases.ensure_warehouse_access"),
        patch("routes.purchases.resolve_default_currency", return_value="AED"),
        patch("routes.purchases.get_system_default_currency", return_value="AED"),
        patch("routes.purchases.get_active_tenant_id", return_value=1),
        patch("utils.branching.get_active_branch_id", return_value=None),
        patch(
            "routes.purchases.get_active_branch_id",
            MagicMock(return_value=None),
            create=True,
        ),
        patch("utils.tax_settings.get_prices_include_vat", return_value=False),
        patch("routes.purchases.ROUND_HALF_UP", ROUND_HALF_UP, create=True),
    ):
        yield {
            "render": render,
            "session": session,
            "log_audit": log_audit,
            "purchase": purchase,
            "purchase_service": purchase_service,
            "query": query,
        }


@pytest.fixture
def purchases_client(app_factory, bypass_permission_auth):
    from routes.purchases import purchases_bp
    from routes.public import public_bp

    app = app_factory(purchases_bp, public_bp)
    return app.test_client()


class TestPurchasesAuth:
    def test_index_unauthenticated(self, purchases_client):
        with unauthenticated_client(purchases_client):
            resp = purchases_client.get("/purchases/")
        assert resp.status_code in (302, 401)

    def test_index_forbidden_without_permission(self, purchases_client, mock_user):
        mock_user.has_permission.return_value = False
        with (
            patch("utils.auth_helpers.is_global_owner_user", return_value=False),
            patch("utils.decorators.is_global_owner_user", return_value=False),
        ):
            resp = purchases_client.get("/purchases/")
        assert resp.status_code == 403


class TestPurchasesIndex:
    def test_index_pagination(self, purchases_client):
        items = [_mock_purchase(id=1), _mock_purchase(id=2, purchase_number="PO-002")]
        with _purchase_patches(pag_items=items) as ctx:
            resp = purchases_client.get("/purchases/?page=1&per_page=10")
        assert resp.status_code == 200
        assert ctx["render"].call_args[1]["purchases"] == items

    def test_index_with_search(self, purchases_client):
        with _purchase_patches() as ctx:
            resp = purchases_client.get("/purchases/?search=PO-001")
        assert resp.status_code == 200
        ctx["query"].filter.assert_called()


class TestPurchasesCreate:
    def test_create_get(self, purchases_client):
        wh = [MagicMock(id=1, name="Main")]
        with (
            _purchase_patches(warehouses=wh) as ctx,
            patch("models.Tenant.get_current", return_value=MagicMock()),
        ):
            resp = purchases_client.get("/purchases/create")
        assert resp.status_code == 200
        assert ctx["render"].call_args[0][0] == "purchases/create.html"
        assert ctx["render"].call_args[1]["warehouses"] == wh

    def test_create_post_missing_warehouse(self, purchases_client):
        with _purchase_patches():
            resp = purchases_client.post("/purchases/create", data={"line_count": "0"})
        assert resp.status_code == 302
        assert resp.location.endswith("/purchases/create")

    def test_create_post_success(self, purchases_client):
        created = _mock_purchase(id=42)
        with _purchase_patches() as ctx, _atomic_transaction_mock():
            ctx["purchase_service"].create_purchase.return_value = created
            resp = purchases_client.post(
                "/purchases/create",
                data={
                    "warehouse_id": "1",
                    "line_count": "1",
                    "lines[0][product_id]": "10",
                    "lines[0][quantity]": "2",
                    "lines[0][unit_cost]": "50",
                },
            )
        assert resp.status_code == 302
        assert "/purchases/42" in resp.location
        ctx["purchase_service"].create_purchase.assert_called_once()


class TestPurchasesBranchScope:
    def test_view_branch_mismatch_403(self, purchases_client):
        purchase = _mock_purchase(branch_id=5)
        with _purchase_patches(purchase=purchase, branch_scope=2) as ctx:
            resp = purchases_client.get("/purchases/1")
        assert resp.status_code == 403
        assert ctx["render"].call_args[0][0] == "errors/403.html"

    def test_print_branch_mismatch_403(self, purchases_client):
        purchase = _mock_purchase(branch_id=5)
        with _purchase_patches(purchase=purchase, branch_scope=2) as _ctx:
            resp = purchases_client.get("/purchases/1/print")
        assert resp.status_code == 403

    def test_edit_branch_mismatch_403(self, purchases_client):
        purchase = _mock_purchase(branch_id=5)
        with _purchase_patches(purchase=purchase, branch_scope=2):
            resp = purchases_client.get("/purchases/1/edit")
        assert resp.status_code == 403


class TestPurchasesViewAndPrint:
    def test_view_success(self, purchases_client):
        purchase = _mock_purchase()
        with _purchase_patches(purchase=purchase, branch_scope=None) as ctx:
            resp = purchases_client.get("/purchases/1")
        assert resp.status_code == 200
        assert ctx["render"].call_args[1]["purchase"] is purchase

    def test_print_success(self, purchases_client):
        purchase = _mock_purchase()
        company_ctx = (MagicMock(), MagicMock(), MagicMock())
        with (
            _purchase_patches(purchase=purchase) as ctx,
            patch(
                "models.invoice_settings.InvoiceSettings.company_print_context",
                return_value=company_ctx,
            ),
            patch(
                "utils.tenant_branding.get_print_header_context",
                return_value={"logo": "x"},
            ),
        ):
            resp = purchases_client.get("/purchases/1/print")
        assert resp.status_code == 200
        assert ctx["render"].call_args[0][0] == "purchases/print.html"


class TestPurchasesEdit:
    def test_edit_get(self, purchases_client):
        purchase = _mock_purchase()
        with _purchase_patches(purchase=purchase) as ctx:
            resp = purchases_client.get("/purchases/1/edit")
        assert resp.status_code == 200
        assert ctx["render"].call_args[0][0] == "purchases/edit.html"

    def test_edit_blocked_when_paid(self, purchases_client):
        purchase = _mock_purchase(paid_amount=Decimal("100"))
        with _purchase_patches(purchase=purchase):
            resp = purchases_client.get("/purchases/1/edit")
        assert resp.status_code == 302
        assert resp.location.endswith("/purchases/1")

    def test_edit_post_success(self, purchases_client):
        purchase = _mock_purchase()
        with _purchase_patches(purchase=purchase) as ctx:
            resp = purchases_client.post("/purchases/1/edit", data={"notes": "updated"})
        assert resp.status_code == 302
        assert purchase.notes == "updated"
        ctx["log_audit"].assert_called_with("update", "purchases", 1)


class TestPurchasesDelete:
    def test_delete_success_no_links(self, purchases_client):
        purchase = _mock_purchase(supplier_id=None)
        with (
            _purchase_patches(purchase=purchase) as ctx,
            patch("models.Cheque") as cheque_model,
            patch("models.warehouse.StockMovement") as stock_model,
            patch("services.gl_service.GLService.reverse_entry"),
            patch("models.PurchaseLine") as _line_model,
        ):
            cheque_model.query.filter_by.return_value.count.return_value = 0
            stock_model.query.filter_by.return_value.count.return_value = 0
            resp = purchases_client.post("/purchases/1/delete")
        assert resp.status_code == 302
        ctx["session"].delete.assert_called_with(purchase)
        ctx["log_audit"].assert_called_with("delete", "purchases", 1)

    def test_delete_archives_when_paid(self, purchases_client):
        purchase = _mock_purchase(paid_amount=Decimal("50"))
        archive = MagicMock()
        with (
            _purchase_patches(purchase=purchase),
            patch("services.archive_service.ArchiveService", return_value=archive),
            patch("models.Cheque") as cheque_model,
            patch("models.warehouse.StockMovement") as stock_model,
        ):
            cheque_model.query.filter_by.return_value.count.return_value = 0
            stock_model.query.filter_by.return_value.count.return_value = 0
            resp = purchases_client.post("/purchases/1/delete")
        assert resp.status_code == 302
        archive.archive_record.assert_called_once()


class TestPurchasesCancel:
    def test_cancel_success(self, purchases_client):
        purchase = _mock_purchase()
        with _purchase_patches(purchase=purchase) as ctx:
            resp = purchases_client.post("/purchases/1/cancel")
        assert resp.status_code == 302
        ctx["purchase_service"].cancel_purchase.assert_called_with(purchase)
        ctx["log_audit"].assert_called_with("cancel", "purchases", 1)

    def test_cancel_value_error(self, purchases_client):
        purchase = _mock_purchase()
        with _purchase_patches(purchase=purchase) as ctx:
            ctx["purchase_service"].cancel_purchase.side_effect = ValueError(
                "cannot cancel"
            )
            resp = purchases_client.post("/purchases/1/cancel")
        assert resp.status_code == 302


class TestPurchasesReturn:
    def test_return_get(self, purchases_client):
        purchase = _mock_purchase()
        with (
            _purchase_patches(purchase=purchase) as ctx,
            patch("routes.purchases.PurchaseReturn") as ret_model,
            patch("routes.purchases.PurchaseReturnLine") as _line_model,
        ):
            ret_model.query.filter.return_value.filter.return_value.order_by.return_value.all.return_value = (
                []
            )
            resp = purchases_client.get("/purchases/1/return")
        assert resp.status_code == 200
        assert ctx["render"].call_args[0][0] == "purchases/return.html"

    def test_return_post_success(self, purchases_client):
        purchase = _mock_purchase()
        result = MagicMock(return_number="PR-001")
        with (
            _purchase_patches(purchase=purchase) as ctx,
            patch("routes.purchases.PurchaseReturn") as ret_model,
            patch("routes.purchases.PurchaseReturnLine"),
        ):
            ret_model.query.filter.return_value.filter.return_value.order_by.return_value.all.return_value = (
                []
            )
            ctx["purchase_service"].create_purchase_return.return_value = result
            resp = purchases_client.post(
                "/purchases/1/return",
                data={"lines": "1", "reason": "damaged"},
            )
        assert resp.status_code == 302
        ctx["purchase_service"].create_purchase_return.assert_called_once()

    def test_return_blocked_for_draft(self, purchases_client):
        purchase = _mock_purchase(status="draft")
        with _purchase_patches(purchase=purchase):
            resp = purchases_client.get("/purchases/1/return")
        assert resp.status_code == 302


class TestPurchasesApiCalculateTotals:
    def test_api_calculate_totals_no_data_400(self, purchases_client):
        with _purchase_patches():
            resp = purchases_client.post("/purchases/api/calculate-totals", json={})
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_api_calculate_totals_success(self, purchases_client):
        payload = {
            "lines": [{"quantity": 2, "unit_cost": 100, "discount_percent": 0}],
            "tax_rate": 5,
            "freight": 10,
        }
        with (
            _purchase_patches(),
            patch("utils.tax_settings.normalize_tax_rate", side_effect=lambda x: x),
        ):
            resp = purchases_client.post(
                "/purchases/api/calculate-totals", json=payload
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["subtotal"] == 200.0
        assert data["total"] == 220.0

    def test_api_calculate_totals_prices_include_vat(self, purchases_client):
        payload = {
            "lines": [{"quantity": 1, "unit_cost": 105, "discount_percent": 0}],
            "tax_rate": 5,
            "prices_include_vat": True,
        }
        with (
            _purchase_patches(),
            patch("utils.tax_settings.normalize_tax_rate", side_effect=lambda x: x),
        ):
            resp = purchases_client.post(
                "/purchases/api/calculate-totals", json=payload
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["prices_include_vat"] is True
        assert data["subtotal"] == 105.0


class TestPurchasesExtended:
    def test_index_with_branch_scope(self, purchases_client):
        with _purchase_patches(branch_scope=3) as ctx:
            resp = purchases_client.get("/purchases/")
        assert resp.status_code == 200
        ctx["query"].filter.assert_called()

    def test_create_post_value_error(self, purchases_client):
        with _purchase_patches() as ctx, _atomic_transaction_mock():
            ctx["purchase_service"].create_purchase.side_effect = ValueError("bad line")
            resp = purchases_client.post(
                "/purchases/create",
                data={"warehouse_id": "1", "line_count": "0"},
            )
        assert resp.status_code == 200

    def test_create_post_generic_exception(self, purchases_client):
        with _purchase_patches() as ctx, _atomic_transaction_mock():
            ctx["purchase_service"].create_purchase.side_effect = RuntimeError(
                "db down"
            )
            resp = purchases_client.post(
                "/purchases/create",
                data={"warehouse_id": "1", "line_count": "0"},
            )
        assert resp.status_code == 200

    def test_edit_post_exception(self, purchases_client):
        purchase = _mock_purchase()
        with _purchase_patches(purchase=purchase) as ctx:
            ctx["session"].commit.side_effect = RuntimeError("commit failed")
            resp = purchases_client.post("/purchases/1/edit", data={"notes": "x"})
        assert resp.status_code == 200

    def test_delete_with_cheques_archives(self, purchases_client):
        purchase = _mock_purchase()
        archive = MagicMock()
        with (
            _purchase_patches(purchase=purchase),
            patch("services.archive_service.ArchiveService", return_value=archive),
            patch("models.Cheque") as cheque_model,
            patch("models.warehouse.StockMovement") as stock_model,
        ):
            cheque_model.query.filter_by.return_value.count.return_value = 2
            stock_model.query.filter_by.return_value.count.return_value = 0
            resp = purchases_client.post("/purchases/1/delete")
        assert resp.status_code == 302
        archive.archive_record.assert_called_once()

    def test_delete_with_stock_archives(self, purchases_client):
        purchase = _mock_purchase()
        archive = MagicMock()
        with (
            _purchase_patches(purchase=purchase),
            patch("services.archive_service.ArchiveService", return_value=archive),
            patch("models.Cheque") as cheque_model,
            patch("models.warehouse.StockMovement") as stock_model,
        ):
            cheque_model.query.filter_by.return_value.count.return_value = 0
            stock_model.query.filter_by.return_value.count.return_value = 3
            resp = purchases_client.post("/purchases/1/delete")
        assert resp.status_code == 302
        assert archive.archive_record.call_count >= 1

    def test_delete_with_supplier_reverses_balance(self, purchases_client):
        purchase = _mock_purchase(supplier_id=5, amount_aed=Decimal("200"))
        supplier = MagicMock()
        with (
            _purchase_patches(purchase=purchase) as _ctx,
            patch("models.Cheque") as cheque_model,
            patch("models.warehouse.StockMovement") as stock_model,
            patch("services.gl_service.GLService.reverse_entry"),
            patch("models.PurchaseLine") as _line_model,
            patch("models.Supplier") as supplier_model,
        ):
            cheque_model.query.filter_by.return_value.count.return_value = 0
            stock_model.query.filter_by.return_value.count.return_value = 0
            supplier_model.query.filter_by.return_value.first.return_value = supplier
            resp = purchases_client.post("/purchases/1/delete")
        assert resp.status_code == 302
        supplier.apply_payment.assert_called_once()

    def test_delete_exception_redirects_to_view(self, purchases_client):
        purchase = _mock_purchase(supplier_id=None)
        with (
            _purchase_patches(purchase=purchase) as _ctx,
            patch("models.Cheque") as cheque_model,
            patch("models.warehouse.StockMovement") as stock_model,
            patch(
                "services.gl_service.GLService.reverse_entry",
                side_effect=RuntimeError("gl fail"),
            ),
        ):
            cheque_model.query.filter_by.return_value.count.return_value = 0
            stock_model.query.filter_by.return_value.count.return_value = 0
            resp = purchases_client.post("/purchases/1/delete")
        assert resp.status_code == 302
        assert resp.location.endswith("/purchases/1")

    def test_cancel_branch_mismatch_403(self, purchases_client):
        purchase = _mock_purchase(branch_id=9)
        with _purchase_patches(purchase=purchase, branch_scope=2) as _ctx:
            resp = purchases_client.post("/purchases/1/cancel")
        assert resp.status_code == 403

    def test_cancel_generic_exception(self, purchases_client):
        purchase = _mock_purchase()
        with _purchase_patches(purchase=purchase) as ctx:
            ctx["purchase_service"].cancel_purchase.side_effect = RuntimeError("fail")
            resp = purchases_client.post("/purchases/1/cancel")
        assert resp.status_code == 302

    def test_return_branch_mismatch_403(self, purchases_client):
        purchase = _mock_purchase(branch_id=9)
        with _purchase_patches(purchase=purchase, branch_scope=2):
            resp = purchases_client.get("/purchases/1/return")
        assert resp.status_code == 403

    def test_return_post_empty_lines(self, purchases_client):
        purchase = _mock_purchase()
        with (
            _purchase_patches(purchase=purchase),
            patch("routes.purchases.PurchaseReturn") as ret_model,
            patch("routes.purchases.PurchaseReturnLine"),
        ):
            ret_model.query.filter.return_value.filter.return_value.order_by.return_value.all.return_value = (
                []
            )
            resp = purchases_client.post("/purchases/1/return", data={})
        assert resp.status_code == 302

    def test_return_post_exception(self, purchases_client):
        purchase = _mock_purchase()
        with (
            _purchase_patches(purchase=purchase) as ctx,
            patch("routes.purchases.PurchaseReturn") as ret_model,
            patch("routes.purchases.PurchaseReturnLine"),
        ):
            ret_model.query.filter.return_value.filter.return_value.order_by.return_value.all.return_value = (
                []
            )
            ctx["purchase_service"].create_purchase_return.side_effect = RuntimeError(
                "fail"
            )
            resp = purchases_client.post(
                "/purchases/1/return",
                data={"lines": "1", "reason": "damaged"},
            )
        assert resp.status_code == 200

    def test_api_calculate_totals_skips_zero_qty_lines(self, purchases_client):
        payload = {
            "lines": [{"quantity": 0, "unit_cost": 10}],
            "tax_rate": 0,
        }
        with (
            _purchase_patches(),
            patch("utils.tax_settings.normalize_tax_rate", side_effect=lambda x: x),
        ):
            resp = purchases_client.post(
                "/purchases/api/calculate-totals", json=payload
            )
        assert resp.status_code == 200
        assert resp.get_json()["line_count"] == 0

    def test_api_calculate_totals_zero_tax_included(self, purchases_client):
        payload = {
            "lines": [{"quantity": 1, "unit_cost": 100, "discount_percent": 0}],
            "tax_rate": 0,
            "prices_include_vat": True,
        }
        with (
            _purchase_patches(),
            patch("utils.tax_settings.normalize_tax_rate", side_effect=lambda x: x),
        ):
            resp = purchases_client.post(
                "/purchases/api/calculate-totals", json=payload
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["tax_amount"] == 0.0

    def test_api_calculate_totals_server_error(self, purchases_client):
        with (
            _purchase_patches(),
            patch(
                "utils.tax_settings.normalize_tax_rate",
                side_effect=RuntimeError("boom"),
            ),
        ):
            resp = purchases_client.post(
                "/purchases/api/calculate-totals",
                json={"lines": [{"quantity": 1, "unit_cost": 1}]},
            )
        assert resp.status_code == 500

    def test_delete_branch_mismatch_403(self, purchases_client):
        purchase = _mock_purchase(branch_id=9)
        with _purchase_patches(purchase=purchase, branch_scope=2) as ctx:
            resp = purchases_client.post("/purchases/1/delete")
        assert resp.status_code == 403
        assert ctx["render"].call_args[0][0] == "errors/403.html"

    def test_return_post_value_error(self, purchases_client):
        purchase = _mock_purchase()
        with (
            _purchase_patches(purchase=purchase) as ctx,
            patch("routes.purchases.PurchaseReturn") as ret_model,
            patch("routes.purchases.PurchaseReturnLine"),
        ):
            ret_model.query.filter.return_value.filter.return_value.order_by.return_value.all.return_value = (
                []
            )
            ctx["purchase_service"].create_purchase_return.side_effect = ValueError(
                "invalid qty"
            )
            resp = purchases_client.post(
                "/purchases/1/return",
                data={"lines": "1", "reason": "damaged"},
            )
        assert resp.status_code == 200

    def test_api_calculate_totals_skips_invalid_line(self, purchases_client):
        payload = {
            "lines": [{"quantity": "bad", "unit_cost": 10}],
            "tax_rate": 0,
        }
        with (
            _purchase_patches(),
            patch("utils.tax_settings.normalize_tax_rate", side_effect=lambda x: x),
        ):
            resp = purchases_client.post(
                "/purchases/api/calculate-totals", json=payload
            )
        assert resp.status_code == 200
        assert resp.get_json()["line_count"] == 0
