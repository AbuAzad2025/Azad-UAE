"""Final statement-level coverage gaps across seven route modules.

Targets only the lines the combined coverage report still marks as missed:

* routes/purchases.py        — 482-483, 526-532, 551-552, 564-576
* routes/sales.py            — 224-229, 247-252, 925-927
* routes/payments.py         — 616, 618, 620, 622-623, 629-630, 1070, 1370->1373
* routes/owner/monitoring.py — 176-177, 210-211, 233-236
* routes/ai_routes/actions.py— 2055, 2096, 2114, 2405-2406
* routes/auth.py             — 103-104, 123-126
* routes/printing.py         — 390-391, 497, 672

Mocks stay at the route boundary (DB/service helpers), matching the existing
``test_*_coverage99`` / ``test_*_cov*`` patterns in this package.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.routes.test_sales_routes import _sales_patches


@contextmanager
def _atomic_noop(target: str):
    ctx = MagicMock()
    ctx.__enter__.return_value = ctx
    ctx.__exit__.return_value = False
    with patch(target, return_value=ctx) as factory:
        yield factory


# ───────────────────────────── clients ─────────────────────────────


@pytest.fixture
def purchases_client(app_factory, bypass_permission_auth):
    from routes.purchases import purchases_bp

    return app_factory(purchases_bp).test_client()


@pytest.fixture
def sales_client(app_factory, bypass_permission_auth):
    from routes.public import public_bp
    from routes.sales import sales_bp

    return app_factory(sales_bp, public_bp).test_client()


@pytest.fixture
def payments_client(app_factory, bypass_permission_auth):
    from routes.payments import payments_bp
    from routes.public import public_bp

    return app_factory(payments_bp, public_bp).test_client()


@pytest.fixture
def monitoring_client(app_factory, bypass_owner_auth):
    from routes.owner import owner_bp

    return app_factory(owner_bp).test_client()


@pytest.fixture
def printing_client(app_factory, bypass_permission_auth):
    from routes.printing import printing_bp

    return app_factory(printing_bp).test_client()


# ─────────────────────── routes/purchases.py ───────────────────────


class TestPurchaseCalculateTotalsGaps:
    """api_calculate_purchase_totals: strict parsing, product lookup, import levy."""

    URL = "/purchases/api/calculate-totals"

    def test_invalid_tax_rate_returns_400(self, purchases_client):
        resp = purchases_client.post(self.URL, json={"lines": [], "tax_rate": "not-a-number"})
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_named_products_tax_and_excise_lookup(self, purchases_client):
        row = MagicMock(id=10, excise_category="soft_drinks", tax_category="standard")
        query = MagicMock()
        query.filter.return_value.all.return_value = [row]
        with (
            patch("routes.purchases.get_active_tenant_id", return_value=1),
            patch("routes.purchases.db.session.query", return_value=query),
            patch("routes.purchases.db.session.get", return_value=MagicMock(enable_import_duties=False)),
            patch("utils.tax_settings.normalize_tax_rate", return_value=Decimal("5")),
            patch(
                "utils.tax_categories.compute_amounts",
                return_value=(Decimal("100"), Decimal("5"), Decimal("105"), Decimal("100")),
            ),
        ):
            resp = purchases_client.post(
                self.URL,
                json={
                    "lines": [
                        {"quantity": 2, "unit_cost": 50, "discount_percent": 0, "product_id": 10},
                    ],
                },
            )
        assert resp.status_code == 200
        query.filter.assert_called_once()
        assert resp.get_json()["data"]["line_count"] == 1

    def test_invalid_landed_cost_returns_400(self, purchases_client):
        with (
            patch("routes.purchases.get_active_tenant_id", return_value=1),
            patch("utils.tax_settings.normalize_tax_rate", return_value=Decimal("5")),
        ):
            resp = purchases_client.post(self.URL, json={"lines": [], "freight": "not-a-number"})
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_import_defaults_when_duties_enabled(self, purchases_client):
        row = MagicMock(id=10, excise_category="tobacco", tax_category="standard")
        query = MagicMock()
        query.filter.return_value.all.return_value = [row]
        tenant = MagicMock(enable_import_duties=True, vat_country="AE")
        with (
            patch("routes.purchases.get_active_tenant_id", return_value=1),
            patch("routes.purchases.db.session.query", return_value=query),
            patch("routes.purchases.db.session.get", return_value=tenant),
            patch("utils.tax_settings.normalize_tax_rate", return_value=Decimal("5")),
            patch("utils.tax_settings.vat_country", return_value="AE"),
            patch(
                "utils.tax_categories.compute_amounts",
                return_value=(Decimal("100"), Decimal("5"), Decimal("105"), Decimal("100")),
            ),
            patch(
                "services.purchase_service.compute_import_levy_defaults",
                return_value=(Decimal("10"), Decimal("20")),
            ) as levy,
        ):
            resp = purchases_client.post(
                self.URL,
                json={
                    "lines": [
                        {"quantity": 2, "unit_cost": 50, "discount_percent": 0, "product_id": 10},
                    ],
                    "is_import": True,
                },
            )
        assert resp.status_code == 200
        levy.assert_called_once()
        assert resp.get_json()["data"]["landed_cost"] == 30.0


# ────────────────────────── routes/sales.py ─────────────────────────


class TestSalesInvalidMoneyGaps:
    """Strict money parsing on the create form and the totals API."""

    @staticmethod
    def _line_form(**extra):
        form = {
            "customer_id": "5",
            "line_count": "1",
            "lines[0][product_id]": "10",
            "lines[0][quantity]": "2",
            "lines[0][unit_price]": "50",
        }
        form.update(extra)
        return form

    def test_invalid_tax_rate_redirects(self, sales_client):
        with _sales_patches():
            resp = sales_client.post("/sales/create", data=self._line_form(tax_rate="not-a-number"))
        assert resp.status_code in (302, 303)
        assert "/sales/create" in resp.headers.get("Location", "")

    def test_invalid_payment_amount_redirects(self, sales_client):
        with _sales_patches():
            resp = sales_client.post("/sales/create", data=self._line_form(payment_amount="not-a-number"))
        assert resp.status_code in (302, 303)
        assert "/sales/create" in resp.headers.get("Location", "")

    def test_api_invalid_money_returns_400(self, sales_client):
        resp = sales_client.post(
            "/sales/api/calculate-totals",
            json={"lines": [], "discount_amount": "not-a-number"},
        )
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False


# ──────────────────────── routes/payments.py ────────────────────────


class TestPaymentsMethodFieldGaps:
    """create_from_sale folds per-payment-method fields into the receipt payload."""

    URL = "/payments/create_from_sale/5"

    @staticmethod
    def _sale():
        return MagicMock(
            id=5,
            tenant_id=1,
            branch_id=1,
            branch=None,
            customer_id=1,
            customer=MagicMock(),
            balance_due=Decimal("100"),
            exchange_rate=Decimal("1"),
            currency="AED",
        )

    def _post(self, client, **extra):
        with (
            patch("routes.payments.tenant_get_or_404", return_value=self._sale()),
            patch("routes.payments.resolve_default_currency", return_value="AED"),
            patch("routes.payments.PaymentService.create_receipt", return_value=MagicMock(id=11)) as create,
            patch("routes.payments.LoggingCore.log_audit"),
            _atomic_noop("routes.payments.atomic_transaction"),
        ):
            resp = client.post(self.URL, data={"amount": "50", **extra}, follow_redirects=False)
        assert resp.status_code == 302
        create.assert_called_once()
        return create.call_args.args[0]

    def test_card_reference_and_last_four(self, payments_client):
        payload = self._post(
            payments_client,
            payment_method="card",
            reference_number_card="CARD-9",
            card_last4="1234",
        )
        assert payload["reference_number"] == "CARD-9"
        assert "1234" in payload["notes"]

    def test_bank_transfer_reference_and_name(self, payments_client):
        payload = self._post(
            payments_client,
            payment_method="bank_transfer",
            reference_number_transfer="TR-9",
            bank_name_transfer="ADCB",
        )
        assert payload["reference_number"] == "TR-9"
        assert payload["bank_name"] == "ADCB"

    def test_ewallet_name_is_appended_to_notes(self, payments_client):
        payload = self._post(
            payments_client,
            payment_method="e_wallet",
            ewallet_name="WalletX",
        )
        assert "WalletX" in payload["notes"]


class TestPaymentsPrintAndDeleteGaps:
    def test_print_receipt_fallback_qr_payload(self, payments_client):
        receipt = MagicMock(
            id=1,
            tenant_id=1,
            branch_id=1,
            source_type="manual",
            source_id=None,
            user_id=42,
            user=None,
            receipt_number="R-1",
            receipt_date=datetime(2026, 1, 2),
            amount=Decimal("100"),
            amount_aed=Decimal("100"),
            currency="AED",
        )
        tenant = MagicMock(name_ar="Co")
        settings = MagicMock(enable_qr_code=True, active_template="modern")
        print_service = MagicMock()
        print_service.RECEIPT_TEMPLATES = ["modern"]
        print_service.resolve_template.return_value = "receipts/modern.html"
        with (
            patch("routes.payments.tenant_get", return_value=receipt),
            patch("routes.payments.assert_tenant_record", return_value=True),
            patch(
                "services.invoice_profile_service.get_company_print_context",
                return_value=(tenant, settings, {"name_ar": "Co"}),
            ),
            patch("utils.tenant_branding.get_print_header_context", return_value={}),
            patch("services.print_service.PrintService", print_service),
            patch("routes.payments.PaymentService.get_print_branch", return_value=None),
            patch("routes.payments.resolve_default_currency", return_value="AED"),
            patch("routes.payments.number_to_arabic_words", return_value="مائة"),
            patch(
                "services.document_verification_service.DocumentVerificationService.get_or_create_verification",
                return_value=None,
            ),
            patch("routes.payments.generate_qr_data_url", return_value="data:image/png;base64,x") as qr,
            patch("routes.payments.render_template", return_value="ok"),
        ):
            resp = payments_client.get("/payments/receipts/1/print")
        assert resp.status_code == 200
        qr.assert_called_once()
        assert qr.call_args.args[0]["t"] == "receipt"

    def test_delete_payment_with_unresolvable_supplier(self, payments_client):
        payment = MagicMock(
            id=31,
            tenant_id=1,
            branch_id=None,
            payment_number="PAY-31",
            cheque_id=None,
            cheque=None,
            purchase_id=None,
            supplier_id=33,
            amount_aed=Decimal("60"),
        )
        with (
            patch("routes.payments.tenant_get_or_404", return_value=payment),
            patch("services.gl_service.GLService.reverse_entry") as reverse,
            patch("routes.payments.PaymentService.get_supplier_by_id", return_value=None) as lookup,
            patch("routes.payments.PaymentService.delete_payment") as delete,
            patch("routes.payments.LoggingCore"),
            _atomic_noop("routes.payments.atomic_transaction"),
        ):
            resp = payments_client.post("/payments/payments/31/delete", follow_redirects=False)
        assert resp.status_code == 302
        lookup.assert_called_once()
        reverse.assert_called_once()
        delete.assert_called_once()


# ───────────────── routes/owner/monitoring.py ─────────────────


class TestMonitoringWhitelistParseGuards:
    @staticmethod
    def _settings(raw):
        return MagicMock(owner_whitelist_ips=raw)

    def test_post_with_corrupt_stored_json(self, monitoring_client):
        settings = self._settings("{not-json")
        with (
            patch("routes.owner.monitoring.SystemSettings.get_current", return_value=settings),
            patch("routes.owner.monitoring.flash"),
            _atomic_noop("routes.owner.monitoring.atomic_transaction"),
        ):
            resp = monitoring_client.post(
                "/owner/ip-whitelist",
                data={"ip_address": "9.9.9.9", "description": "office"},
            )
        assert resp.status_code in (200, 302)
        assert '"ip": "9.9.9.9"' in settings.owner_whitelist_ips

    def test_get_with_corrupt_stored_json(self, monitoring_client):
        settings = self._settings("{not-json")
        with (
            patch("routes.owner.monitoring.SystemSettings.get_current", return_value=settings),
            patch("routes.owner.monitoring.render_template", return_value="ok") as render,
        ):
            resp = monitoring_client.get("/owner/ip-whitelist")
        assert resp.status_code == 200
        assert render.call_args.kwargs["whitelist"] == []

    def test_delete_with_corrupt_stored_json(self, monitoring_client):
        with patch(
            "routes.owner.monitoring.SystemSettings.get_current",
            return_value=self._settings("{not-json"),
        ):
            resp = monitoring_client.post("/owner/ip-whitelist/0/delete")
        assert resp.status_code in (200, 302)

    def test_delete_with_empty_stored_value(self, monitoring_client):
        with patch(
            "routes.owner.monitoring.SystemSettings.get_current",
            return_value=self._settings(""),
        ):
            resp = monitoring_client.post("/owner/ip-whitelist/0/delete")
        assert resp.status_code in (200, 302)


# ───────────────── routes/ai_routes/actions.py ─────────────────


class TestAiActionsFinalGaps:
    @staticmethod
    def _run(message, ctx, mock_user):
        from routes.ai_routes import _process_user_action

        with (
            patch("routes.ai_routes.actions._conversation_ctx", return_value=ctx),
            patch("routes.ai_routes.actions.get_active_tenant_id", return_value=1),
            patch("routes.ai_routes.actions.train_local_ai"),
            patch("routes.ai_routes.actions.assign_tenant_id"),
            patch("extensions.db.session") as session,
        ):
            session.add = MagicMock()
            session.flush = MagicMock()
            session.commit = MagicMock()
            return _process_user_action(message, mock_user)

    def test_empty_expense_list_message(self, mock_user):
        with patch(
            "services.ai_actions_query_service.AiActionsQueryService.all_active_expenses",
            return_value=[],
        ):
            result = self._run("2", {"last_action": "مصروف"}, mock_user)
        assert "لا يوجد مصروفات" in result

    def test_empty_purchase_list_message(self, mock_user):
        with patch(
            "services.ai_actions_query_service.AiActionsQueryService.all_active_purchases",
            return_value=[],
        ):
            result = self._run("2", {"last_action": "مشتريات"}, mock_user)
        assert "لا يوجد مشتريات" in result

    def test_empty_cheque_list_message(self, mock_user):
        with patch(
            "services.ai_actions_query_service.AiActionsQueryService.all_active_cheques",
            return_value=[],
        ):
            result = self._run("2", {"last_action": "شيك"}, mock_user)
        assert "لا يوجد شيكات" in result

    def test_bad_price_in_colon_product_command(self, mock_user):
        result = self._run("منتج: Filter, PN99, abc, 5", {}, mock_user)
        assert "خطأ في إدخال السعر" in result


# ────────────────────────── routes/auth.py ──────────────────────────


class TestAuthRenderLoginGuards:
    def test_request_args_runtime_error_falls_back_to_users(self):
        from routes.auth import _render_login

        class _ArgsUnavailable:
            @property
            def args(self):
                raise RuntimeError("outside a request")

        with (
            patch("routes.auth.request", _ArgsUnavailable()),
            patch("routes.auth.render_template", return_value="ok") as render,
            patch("services.user_service.UserService.active_tenants", return_value=[]),
        ):
            assert _render_login() == "ok"
        assert render.call_args.kwargs["access_mode"] == "users"

    def test_active_tenants_failure_is_logged_and_ignored(self):
        from routes.auth import _render_login

        with (
            patch("routes.auth.render_template", return_value="ok") as render,
            patch(
                "services.user_service.UserService.active_tenants",
                side_effect=RuntimeError("tenant service down"),
            ),
        ):
            assert _render_login(access_mode="developer") == "ok"
        assert render.call_args.kwargs["access_mode"] == "developer"
        assert render.call_args.kwargs["active_stores"] == []


# ──────────────────────── routes/printing.py ────────────────────────


class TestPrintingFinalGaps:
    def test_customer_statement_currency_fallback(self, printing_client):
        context = {"transactions": [], "final_balance": 0, "filters": {}}
        with (
            patch("utils.tenanting.tenant_get_or_404", return_value=MagicMock(tenant_id=1)),
            patch("routes.customers._customer_in_scope", return_value=True),
            patch("utils.currency_utils.resolve_default_currency", side_effect=RuntimeError("fx")),
            patch("utils.currency_utils.get_system_default_currency", return_value="AED"),
            patch(
                "services.customer_statement_service.CustomerStatementService.build_statement_context",
                return_value=context,
            ),
            patch("routes.printing.get_active_tenant_id", return_value=1),
            patch("routes.printing.branch_scope_id", return_value=None),
            patch("services.invoice_profile_service.get_company_print_context", return_value=(None, None, None)),
            patch("utils.tenant_branding.get_print_header_context", return_value={}),
            patch("routes.printing.PrintService.create_snapshot"),
            patch("routes.printing.PrintService.audit_print"),
            patch("routes.printing.PrintService.render_print", return_value="ok") as render,
        ):
            resp = printing_client.get("/printing/customer-statement/5")
        assert resp.status_code == 200
        render.assert_called_once()

    def test_supplier_statement_includes_maintenance_purchase(self, printing_client):
        mo = MagicMock(received_at=None, order_date=datetime(2026, 1, 3), po_number="MPO-1")

        def _chain(items):
            query = MagicMock()
            query.filter.return_value = query
            query.order_by.return_value.all.return_value = items
            return query

        with (
            patch("utils.tenanting.tenant_get_or_404", return_value=MagicMock(tenant_id=1)),
            patch("routes.suppliers._supplier_in_scope", return_value=True),
            patch(
                "services.supplier_service.SupplierService.print_statement_queries",
                return_value=(_chain([]), _chain([]), _chain([])),
            ),
            patch(
                "services.supplier_service.SupplierService.maintenance_purchase_query",
                return_value=_chain([mo]),
            ),
            patch(
                "services.supplier_service.SupplierService.maintenance_purchase_base_amount",
                return_value=10.0,
            ),
            patch("services.supplier_service.SupplierService.preperiod_opening_balance", return_value=0.0),
            patch("routes.printing.get_active_tenant_id", return_value=1),
            patch("routes.printing.branch_scope_id", return_value=None),
            patch("services.invoice_profile_service.get_company_print_context", return_value=(None, None, None)),
            patch("utils.tenant_branding.get_print_header_context", return_value={}),
            patch("routes.printing.PrintService.create_snapshot"),
            patch("routes.printing.PrintService.audit_print"),
            patch("routes.printing.PrintService.render_print", return_value="ok") as render,
        ):
            resp = printing_client.get("/printing/supplier-statement/6")
        assert resp.status_code == 200
        rendered = render.call_args.args[1]
        assert any(t["type"] == "maintenance_purchase" for t in rendered["transactions"])

    def test_print_settings_missing_tenant_aborts_404(self, printing_client):
        with (
            patch("services.invoice_profile_service.resolve_print_profile", return_value=MagicMock()),
            patch("routes.printing.db.session.get", return_value=None),
        ):
            resp = printing_client.post("/printing/settings", data={"paper_size": "A4"})
        assert resp.status_code == 404
