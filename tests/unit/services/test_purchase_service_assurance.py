"""Purchase service — tenant isolation, GL, landed cost, serial/MWAC paths."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from flask import Flask


@pytest.fixture
def app():
    application = Flask(__name__)
    application.config.update(
        TESTING=True,
        SECRET_KEY="test-secret",
        ENABLE_LANDED_COST_CAPITALIZATION=True,
        ENABLE_MWAC=False,
    )
    return application


@pytest.fixture
def db_session(mocker):
    session = mocker.MagicMock(name="db_session")
    session.rollback = mocker.MagicMock()
    return session


def _user(**kwargs):
    u = MagicMock()
    u.id = kwargs.get("id", 10)
    u.branch_id = kwargs.get("branch_id", 2)
    u.tenant_id = kwargs.get("tenant_id", 1)
    return u


def _warehouse(**kwargs):
    wh = MagicMock()
    wh.id = kwargs.get("id", 3)
    wh.branch_id = kwargs.get("branch_id", 2)
    wh.tenant_id = kwargs.get("tenant_id", 1)
    return wh


def _product(**kwargs):
    p = MagicMock()
    p.id = kwargs.get("id", 50)
    p.name = kwargs.get("name", "Widget")
    p.has_serial_number = kwargs.get("has_serial_number", False)
    p.warranty_days = kwargs.get("warranty_days", 0)
    return p


def _purchase(**kwargs):
    p = MagicMock()
    p.id = kwargs.get("id", 100)
    p.tenant_id = kwargs.get("tenant_id", 1)
    p.branch_id = kwargs.get("branch_id", 2)
    p.warehouse_id = kwargs.get("warehouse_id", 3)
    p.status = kwargs.get("status", "confirmed")
    p.purchase_number = kwargs.get("purchase_number", "P-001")
    p.currency = kwargs.get("currency", "AED")
    p.exchange_rate = kwargs.get("exchange_rate", Decimal("1"))
    p.subtotal = kwargs.get("subtotal", Decimal("100"))
    p.tax_amount = kwargs.get("tax_amount", Decimal("5"))
    p.tax_rate = kwargs.get("tax_rate", Decimal("5"))
    p.prices_include_vat = kwargs.get("prices_include_vat", False)
    p.amount_aed = kwargs.get("amount_aed", Decimal("105"))
    p.supplier_id = kwargs.get("supplier_id", 7)
    p.supplier = kwargs.get("supplier", MagicMock(total_purchases_aed=Decimal("500")))
    p.lines = kwargs.get("lines", [])
    return p


def _purchase_line(**kwargs):
    pl = MagicMock()
    pl.id = kwargs.get("id", 200)
    pl.line_total = kwargs.get("line_total", Decimal("100"))
    pl.landed_cost = kwargs.get("landed_cost", Decimal("0"))
    return pl


def _line_data(**kwargs):
    return {
        "product_id": kwargs.get("product_id", 50),
        "quantity": kwargs.get("quantity", 5),
        "unit_cost": kwargs.get("unit_cost", 20),
        "discount_percent": kwargs.get("discount_percent", 0),
        **({k: kwargs[k] for k in ("serials",) if k in kwargs}),
    }


def _mock_create_session(mocker, product=None, purchase_id=1, line_start_id=100):
    from models.purchase import Purchase, PurchaseLine

    session = mocker.patch("services.purchase_service.db.session")
    product = product or _product()
    state = {"purchase": None, "lines": []}
    next_line_id = {"value": line_start_id}

    def on_add(obj):
        if isinstance(obj, Purchase):
            if not getattr(obj, "id", None):
                obj.id = purchase_id
            state["purchase"] = obj
        elif isinstance(obj, PurchaseLine):
            if not getattr(obj, "id", None):
                obj.id = next_line_id["value"]
                next_line_id["value"] += 1
            state["lines"].append(obj)
            if state["purchase"] is not None:
                state["purchase"].lines = list(state["lines"])

    def on_flush():
        if state["purchase"] and state["lines"]:
            state["purchase"].lines = list(state["lines"])

    session.add.side_effect = on_add
    session.flush.side_effect = on_flush
    session.get.side_effect = lambda model, pk: product if pk == product.id else None
    return session, state


def _patch_create_common(
    mocker, *, product=None, warehouse=None, user=None, config=None, rate_info=None
):
    warehouse = warehouse or _warehouse()
    user = user or _user()
    config = dict(config or {"ENABLE_LANDED_COST_CAPITALIZATION": True})
    rate_info = rate_info or {"rate": 1.0, "rate_mode": "auto"}

    mocker.patch(
        "services.purchase_service.ensure_warehouse_access", return_value=warehouse
    )
    mocker.patch(
        "services.purchase_service.get_active_tenant_id", return_value=user.tenant_id
    )
    mocker.patch("services.purchase_service.generate_number", return_value="P-001")
    mocker.patch(
        "services.purchase_service.validate_currency_code",
        side_effect=lambda c: (c or "AED").strip() or "AED",
    )
    mocker.patch(
        "services.purchase_service.resolve_tenant_base_currency", return_value="AED"
    )
    mocker.patch(
        "services.purchase_service.ExchangeRateService.resolve_exchange_rate_for_transaction",
        return_value=rate_info,
    )
    mocker.patch("utils.tax_settings.get_prices_include_vat", return_value=False)
    mocker.patch(
        "services.purchase_service.normalize_tax_rate",
        side_effect=lambda r, tenant_id=None: Decimal(str(r or 0)),
    )
    mocker.patch("services.purchase_service.StockService.process_purchase_lines")
    mocker.patch("services.purchase_service.GLService.ensure_core_accounts")
    post = mocker.patch("services.purchase_service.post_or_fail")
    mocker.patch("services.purchase_service.LoggingCore.log_audit")
    mocker.patch("services.purchase_service.should_post_vat_gl", return_value=True)
    mocker.patch(
        "services.purchase_service.current_app.config.get",
        side_effect=lambda k, default=None: config.get(k, default),
    )
    session, state = _mock_create_session(mocker, product=product)
    return session, state, warehouse, user, post


def _patch_cancel_query(mocker, *, direct_paid=Decimal("0"), has_stock=False):
    session = mocker.patch("services.purchase_service.db.session")
    pay_q = MagicMock()
    pay_q.filter.return_value = pay_q
    pay_q.scalar.return_value = direct_paid
    session.query.return_value = pay_q

    sm_q = MagicMock()
    sm_q.filter_by.return_value.first.return_value = MagicMock() if has_stock else None
    mocker.patch("models.warehouse.StockMovement.query", sm_q)
    mocker.patch("services.purchase_service.StockService.reverse_purchase")
    mocker.patch("services.purchase_service.GLService.reverse_entry")
    mocker.patch("services.purchase_service.LoggingCore.log_audit")
    return session


class TestCreatePurchaseValidations:
    def test_missing_warehouse(self, app):
        from services.purchase_service import PurchaseService

        with app.app_context():
            with pytest.raises(ValueError, match="يجب اختيار المستودع"):
                PurchaseService.create_purchase(_user(), {"supplier_name": "X"}, [])

    def test_missing_supplier_name(self, app, mocker):
        mocker.patch(
            "services.purchase_service.ensure_warehouse_access",
            return_value=_warehouse(),
        )
        from services.purchase_service import PurchaseService

        with app.app_context():
            with pytest.raises(ValueError, match="يجب إدخال اسم المورد"):
                PurchaseService.create_purchase(_user(), {}, [], warehouse_id=3)

    def test_foreign_supplier_rejected(self, app, mocker):
        wh = _warehouse(tenant_id=1)
        mocker.patch(
            "services.purchase_service.ensure_warehouse_access", return_value=wh
        )
        supplier_q = MagicMock()
        supplier_q.filter_by.return_value.first.return_value = None
        mocker.patch("services.purchase_service.Supplier.query", supplier_q)
        from services.purchase_service import PurchaseService

        with app.app_context():
            with pytest.raises(ValueError, match="لا ينتمي لنفس الشركة"):
                PurchaseService.create_purchase(
                    _user(),
                    {"supplier_id": 99},
                    [_line_data()],
                    warehouse_id=3,
                )

    def test_exchange_rate_needs_input(self, app, mocker):
        _patch_create_common(
            mocker,
            rate_info={"rate_mode": "needs_input"},
        )
        from services.purchase_service import PurchaseService

        with app.app_context():
            with pytest.raises(ValueError, match="سعر الصرف غير متوفر"):
                PurchaseService.create_purchase(
                    _user(),
                    {"supplier_name": "Local"},
                    [_line_data()],
                    warehouse_id=3,
                )

    def test_no_lines_rejected_before_db(self, app, mocker):
        session, _, _, _, _ = _patch_create_common(mocker)
        from services.purchase_service import PurchaseService

        with app.app_context():
            with pytest.raises(ValueError, match="يجب إضافة منتج"):
                PurchaseService.create_purchase(
                    _user(),
                    {"supplier_name": "Local"},
                    [],
                    warehouse_id=3,
                )
        session.rollback.assert_not_called()
        session.flush.assert_not_called()

    def test_zero_quantity_rejected_before_db(self, app, mocker):
        session, _, _, _, _ = _patch_create_common(mocker)
        from services.purchase_service import PurchaseService

        with app.app_context():
            with pytest.raises(ValueError, match="يجب إضافة منتج"):
                PurchaseService.create_purchase(
                    _user(),
                    {"supplier_name": "Local"},
                    [_line_data(quantity=0)],
                    warehouse_id=3,
                )
        session.rollback.assert_not_called()
        session.flush.assert_not_called()

    def test_product_not_found_rollback(self, app, mocker):
        session, _, _, _, _ = _patch_create_common(mocker)
        session.get.return_value = None
        session.get.side_effect = lambda model, pk: None
        from services.purchase_service import PurchaseService

        with app.app_context():
            with pytest.raises(ValueError, match="يجب إضافة منتج"):
                PurchaseService.create_purchase(
                    _user(),
                    {"supplier_name": "Local"},
                    [_line_data()],
                    warehouse_id=3,
                )

    def test_negative_unit_cost_rejected_before_db(self, app, mocker):
        session, _, _, _, _ = _patch_create_common(mocker)
        from services.purchase_service import PurchaseService

        with app.app_context():
            with pytest.raises(ValueError, match="يجب إضافة منتج"):
                PurchaseService.create_purchase(
                    _user(),
                    {"supplier_name": "Local"},
                    [_line_data(unit_cost=-1)],
                    warehouse_id=3,
                )
        session.rollback.assert_not_called()
        session.flush.assert_not_called()


class TestCreatePurchaseCurrency:
    def test_resolve_default_currency_from_tenant(self, app, mocker):
        _patch_create_common(mocker)
        mocker.patch(
            "services.purchase_service.resolve_default_currency", return_value="EUR"
        )
        tenant = MagicMock()
        mocker.patch("models.Tenant.get_current", return_value=tenant)
        from services.purchase_service import PurchaseService

        with app.app_context():
            result = PurchaseService.create_purchase(
                _user(),
                {"supplier_name": "Local"},
                [_line_data()],
                warehouse_id=3,
            )
        assert result.currency == "EUR"

    def test_tenant_currency_fallback_on_exception(self, app, mocker):
        _patch_create_common(mocker)
        mocker.patch("models.Tenant.get_current", side_effect=RuntimeError("no tenant"))
        mocker.patch(
            "services.purchase_service.get_system_default_currency", return_value="AED"
        )
        from services.purchase_service import PurchaseService

        with app.app_context():
            result = PurchaseService.create_purchase(
                _user(),
                {"supplier_name": "Local"},
                [_line_data()],
                warehouse_id=3,
            )
        assert result.currency == "AED"

    def test_blank_currency_uses_system_default(self, app, mocker):
        _patch_create_common(mocker)
        mocker.patch(
            "services.purchase_service.get_system_default_currency", return_value="AED"
        )
        from services.purchase_service import PurchaseService

        with app.app_context():
            result = PurchaseService.create_purchase(
                _user(),
                {"supplier_name": "Local"},
                [_line_data()],
                warehouse_id=3,
                currency="   ",
            )
        assert result.currency == "AED"


class TestCreatePurchaseHappyPath:
    def test_happy_path_with_supplier_id(self, app, mocker):
        wh = _warehouse()
        supplier = MagicMock(id=7, name="ACME", phone="050", email="a@b.c", tenant_id=1)
        supplier_q = MagicMock()
        supplier_q.filter_by.return_value.first.return_value = supplier
        mocker.patch("services.purchase_service.Supplier.query", supplier_q)
        session, _, _, _, _ = _patch_create_common(mocker, warehouse=wh)
        from services.purchase_service import PurchaseService

        with app.app_context():
            result = PurchaseService.create_purchase(
                _user(),
                {"supplier_id": 7},
                [_line_data()],
                warehouse_id=3,
                tax_rate=5,
            )
        assert result.purchase_number == "P-001"
        supplier.apply_purchase.assert_called_once()
        session.flush.assert_called()

    def test_supplier_apply_purchase_failure_logged(self, app, mocker):
        wh = _warehouse()
        supplier = MagicMock(id=7, name="ACME", phone="", email="", tenant_id=1)
        supplier.apply_purchase.side_effect = RuntimeError("stats fail")
        supplier_q = MagicMock()
        supplier_q.filter_by.return_value.first.return_value = supplier
        mocker.patch("services.purchase_service.Supplier.query", supplier_q)
        mock_logger = mocker.patch("services.purchase_service.current_app.logger")
        session, _, _, _, _ = _patch_create_common(mocker, warehouse=wh)
        from services.purchase_service import PurchaseService

        with app.app_context():
            PurchaseService.create_purchase(
                _user(),
                {"supplier_id": 7},
                [_line_data()],
                warehouse_id=3,
            )
        mock_logger.warning.assert_called()
        session.flush.assert_called()


class TestCreatePurchaseSerials:
    def test_serial_numbers_with_warranty(self, app, mocker):
        product = _product(has_serial_number=True, warranty_days=365)
        session, _, _, _, _ = _patch_create_common(mocker, product=product)
        mocker.patch(
            "utils.serial_helpers.extract_serials", return_value=["SN-1", "SN-2"]
        )
        mocker.patch("utils.serial_helpers.validate_serials")
        serial_q = MagicMock()
        serial_q.filter.return_value.count.return_value = 0
        mocker.patch("models.product_serial.ProductSerial.query", serial_q)
        from services.purchase_service import PurchaseService

        with app.app_context():
            PurchaseService.create_purchase(
                _user(),
                {"supplier_name": "Local"},
                [_line_data(quantity=2, serials=["SN-1", "SN-2"])],
                warehouse_id=3,
            )
        assert session.add.call_count >= 3

    def test_duplicate_serial_raises(self, app, mocker):
        product = _product(has_serial_number=True)
        _patch_create_common(mocker, product=product)
        mocker.patch("utils.serial_helpers.extract_serials", return_value=["SN-DUP"])
        mocker.patch("utils.serial_helpers.validate_serials")
        serial_q = MagicMock()
        serial_q.filter.return_value.count.return_value = 1
        mocker.patch("models.product_serial.ProductSerial.query", serial_q)
        from services.purchase_service import PurchaseService

        with app.app_context():
            with pytest.raises(ValueError, match="موجودة مسبقاً"):
                PurchaseService.create_purchase(
                    _user(),
                    {"supplier_name": "Local"},
                    [_line_data(quantity=1, serials=["SN-DUP"])],
                    warehouse_id=3,
                )


class TestCreatePurchaseGL:
    def test_capitalized_landed_cost_in_inventory_debit(self, app, mocker):
        _, _, _, _, post = _patch_create_common(
            mocker, config={"ENABLE_LANDED_COST_CAPITALIZATION": True}
        )
        from services.purchase_service import PurchaseService

        with app.app_context():
            PurchaseService.create_purchase(
                _user(),
                {"supplier_name": "Local"},
                [_line_data()],
                warehouse_id=3,
                freight=10,
                customs_duty=5,
                tax_rate=5,
            )
        gl_lines = post.call_args[0][0]
        inventory = next(
            l for l in gl_lines if l.get("concept_code") == "INVENTORY_ASSET"
        )
        assert inventory["debit"] >= Decimal("100")

    def test_non_capitalized_landed_gl_lines(self, app, mocker):
        _, _, _, _, post = _patch_create_common(
            mocker, config={"ENABLE_LANDED_COST_CAPITALIZATION": False}
        )
        from services.purchase_service import PurchaseService

        with app.app_context():
            PurchaseService.create_purchase(
                _user(),
                {"supplier_name": "Local"},
                [_line_data()],
                warehouse_id=3,
                freight=10,
                customs_duty=5,
                insurance=3,
                other_landed_cost=2,
            )
        gl_lines = post.call_args[0][0]
        concepts = {l.get("concept_code") for l in gl_lines}
        assert "FREIGHT_IN" in concepts
        assert "CUSTOMS_DUTY" in concepts
        assert "INVENTORY_ASSET" in concepts

    def test_vat_gl_line_when_enabled(self, app, mocker):
        _, _, _, _, post = _patch_create_common(mocker)
        mocker.patch("services.purchase_service.should_post_vat_gl", return_value=True)
        from services.purchase_service import PurchaseService

        with app.app_context():
            PurchaseService.create_purchase(
                _user(),
                {"supplier_name": "Local"},
                [_line_data()],
                warehouse_id=3,
                tax_rate=5,
            )
        gl_lines = post.call_args[0][0]
        assert any(l.get("concept_code") == "VAT_INPUT" for l in gl_lines)

    def test_vat_gl_skipped_when_disabled(self, app, mocker):
        _, _, _, _, post = _patch_create_common(mocker)
        mocker.patch("services.purchase_service.should_post_vat_gl", return_value=False)
        from services.purchase_service import PurchaseService

        with app.app_context():
            PurchaseService.create_purchase(
                _user(),
                {"supplier_name": "Local"},
                [_line_data()],
                warehouse_id=3,
                tax_rate=5,
            )
        gl_lines = post.call_args[0][0]
        assert not any(l.get("concept_code") == "VAT_INPUT" for l in gl_lines)

    def test_landed_cost_allocation_to_lines(self, app, mocker):
        _, state, _, _, _ = _patch_create_common(mocker)
        from services.purchase_service import PurchaseService

        with app.app_context():
            PurchaseService.create_purchase(
                _user(),
                {"supplier_name": "Local"},
                [_line_data()],
                warehouse_id=3,
                freight=20,
            )
        assert state["lines"][0].landed_cost == Decimal("20.000")

    def test_inventory_debit_clamped_to_zero(self, app, mocker):
        _, _, _, _, post = _patch_create_common(
            mocker,
            config={"ENABLE_LANDED_COST_CAPITALIZATION": False},
        )
        from services.purchase_service import PurchaseService

        with app.app_context():
            PurchaseService.create_purchase(
                _user(),
                {"supplier_name": "Local"},
                [_line_data(unit_cost=10, quantity=1)],
                warehouse_id=3,
                discount_amount=50,
            )
        gl_lines = post.call_args[0][0]
        inventory = next(
            l for l in gl_lines if l.get("concept_code") == "INVENTORY_ASSET"
        )
        assert inventory["debit"] == Decimal("0")


class TestCancelPurchase:
    def test_already_cancelled(self, app):
        from services.purchase_service import PurchaseService

        with app.app_context():
            with pytest.raises(ValueError, match="ملغاة بالفعل"):
                PurchaseService.cancel_purchase(_purchase(status="cancelled"))

    def test_direct_payments_block_cancel(self, app, mocker):
        _patch_cancel_query(mocker, direct_paid=Decimal("100"))
        from services.purchase_service import PurchaseService

        with app.app_context():
            with pytest.raises(ValueError, match="مدفوعات مؤكدة"):
                PurchaseService.cancel_purchase(_purchase())

    def test_supplier_adjustment_no_stock(self, app, mocker):
        session = _patch_cancel_query(mocker, direct_paid=Decimal("0"), has_stock=False)
        purchase = _purchase(amount_aed=Decimal("200"))
        supplier = purchase.supplier
        supplier.total_purchases_aed = Decimal("500")
        from services.purchase_service import PurchaseService

        with app.app_context():
            PurchaseService.cancel_purchase(purchase)
        assert supplier.total_purchases_aed == Decimal("300")
        assert purchase.status == "cancelled"
        session.flush.assert_called()

    def test_stock_reverse_and_gl(self, app, mocker):
        session = _patch_cancel_query(mocker, has_stock=True)
        reverse_stock = mocker.patch(
            "services.purchase_service.StockService.reverse_purchase"
        )
        reverse_gl = mocker.patch("services.purchase_service.GLService.reverse_entry")
        purchase = _purchase(supplier=None)
        from services.purchase_service import PurchaseService

        with app.app_context():
            PurchaseService.cancel_purchase(purchase)
        reverse_stock.assert_called_once_with(purchase)
        reverse_gl.assert_called_once()
        session.flush.assert_called()

    def test_commit_failure_rolls_back(self, app, mocker):
        session = _patch_cancel_query(mocker)
        session.flush.side_effect = RuntimeError("commit fail")
        mock_logger = mocker.patch("services.purchase_service.current_app.logger")
        from services.purchase_service import PurchaseService

        with app.app_context():
            with pytest.raises(RuntimeError, match="commit fail"):
                PurchaseService.cancel_purchase(_purchase())
        mock_logger.exception.assert_called()


def _mock_return_session(mocker):
    from models.purchase_return import PurchaseReturn, PurchaseReturnLine

    session = mocker.patch("services.purchase_service.db.session")
    state = {"purchase_return": None, "lines": []}
    next_line_id = {"value": 300}

    def on_add(obj):
        if isinstance(obj, PurchaseReturn):
            if not getattr(obj, "id", None):
                obj.id = 50
            state["purchase_return"] = obj
        elif isinstance(obj, PurchaseReturnLine):
            if not getattr(obj, "id", None):
                obj.id = next_line_id["value"]
                next_line_id["value"] += 1
            state["lines"].append(obj)
            if state["purchase_return"] is not None:
                state["purchase_return"].lines = list(state["lines"])

    def on_flush():
        if state["purchase_return"] and state["lines"]:
            state["purchase_return"].lines = list(state["lines"])

    session.add.side_effect = on_add
    session.flush.side_effect = on_flush
    return session, state


def _patch_return_common(mocker, purchase, *, config=None, vat_gl=True):
    config = dict(
        config or {"ENABLE_LANDED_COST_CAPITALIZATION": True, "ENABLE_MWAC": False}
    )
    session, _state = _mock_return_session(mocker)
    post = mocker.patch("services.purchase_service.post_or_fail")
    mocker.patch("services.purchase_service.generate_number", return_value="PR-001")
    mocker.patch("services.purchase_service.StockService.remove_stock")
    mocker.patch("services.purchase_service.GLService.ensure_core_accounts")
    mocker.patch("services.purchase_service.LoggingCore.log_audit")
    mocker.patch("services.purchase_service.should_post_vat_gl", return_value=vat_gl)
    mocker.patch(
        "services.purchase_service.current_app.config.get",
        side_effect=lambda k, default=None: config.get(k, default),
    )
    serial_q = MagicMock()
    serial_q.filter_by.return_value.limit.return_value.all.return_value = []
    mocker.patch("models.product_serial.ProductSerial.query", serial_q)
    return session, post


class TestCreatePurchaseReturn:
    def test_cancelled_purchase_rejected(self, app):
        from services.purchase_service import PurchaseService

        with app.app_context():
            with pytest.raises(ValueError, match="ملغاة"):
                PurchaseService.create_purchase_return(
                    _purchase(status="cancelled"),
                    _user(),
                    [{"quantity": 1}],
                )

    def test_empty_lines_rejected(self, app, mocker):
        mocker.patch("services.purchase_service.generate_number", return_value="PR-001")
        from services.purchase_service import PurchaseService

        with app.app_context():
            with pytest.raises(ValueError, match="يجب إرجاع منتج"):
                PurchaseService.create_purchase_return(_purchase(), _user(), [])

    def test_zero_quantity_rollback(self, app, mocker):
        session, _post = _patch_return_common(mocker, _purchase())
        from services.purchase_service import PurchaseService

        with app.app_context():
            with pytest.raises(ValueError, match="يجب إرجاع منتج"):
                PurchaseService.create_purchase_return(
                    _purchase(),
                    _user(),
                    [
                        {
                            "purchase_line_id": 1,
                            "product_id": 50,
                            "quantity": 0,
                            "unit_cost": 10,
                        }
                    ],
                )

    def test_happy_path_no_tax(self, app, mocker):
        purchase = _purchase(tax_amount=None)
        session, _post = _patch_return_common(mocker, purchase)
        from services.purchase_service import PurchaseService

        with app.app_context():
            result = PurchaseService.create_purchase_return(
                purchase,
                _user(),
                [
                    {
                        "purchase_line_id": 1,
                        "product_id": 50,
                        "quantity": 2,
                        "unit_cost": 10,
                    }
                ],
            )
        assert result.return_number == "PR-001"
        session.flush.assert_called()

    def test_prices_include_vat_inventory_credit(self, app, mocker):
        purchase = _purchase(
            prices_include_vat=True, tax_rate=Decimal("5"), tax_amount=Decimal("5")
        )
        _session, post = _patch_return_common(mocker, purchase)
        from services.purchase_service import PurchaseService

        with app.app_context():
            PurchaseService.create_purchase_return(
                purchase,
                _user(),
                [
                    {
                        "purchase_line_id": 1,
                        "product_id": 50,
                        "quantity": 1,
                        "unit_cost": 105,
                    }
                ],
            )
        gl_lines = post.call_args[0][0]
        inventory = next(
            l for l in gl_lines if l.get("concept_code") == "INVENTORY_ASSET"
        )
        assert inventory["credit"] < Decimal("105")

    def test_prices_include_vat_invalid_tax_rate(self, app, mocker):
        purchase = _purchase(
            prices_include_vat=True, tax_rate="bad", tax_amount=Decimal("5")
        )
        _patch_return_common(mocker, purchase)
        from services.purchase_service import PurchaseService

        with app.app_context():
            result = PurchaseService.create_purchase_return(
                purchase,
                _user(),
                [
                    {
                        "purchase_line_id": 1,
                        "product_id": 50,
                        "quantity": 1,
                        "unit_cost": 100,
                    }
                ],
            )
        assert result is not None

    def test_capitalized_landed_on_return(self, app, mocker):
        pl = _purchase_line(id=1, line_total=Decimal("100"), landed_cost=Decimal("10"))
        purchase = _purchase(lines=[pl])
        _session, post = _patch_return_common(
            mocker, purchase, config={"ENABLE_LANDED_COST_CAPITALIZATION": True}
        )
        from services.purchase_service import PurchaseService

        with app.app_context():
            PurchaseService.create_purchase_return(
                purchase,
                _user(),
                [
                    {
                        "purchase_line_id": 1,
                        "product_id": 50,
                        "quantity": 1,
                        "unit_cost": 100,
                    }
                ],
            )
        gl_lines = post.call_args[0][0]
        inventory = next(
            l for l in gl_lines if l.get("concept_code") == "INVENTORY_ASSET"
        )
        assert inventory["credit"] > Decimal("100")

    def test_vat_gl_credit_on_return(self, app, mocker):
        purchase = _purchase(subtotal=Decimal("100"), tax_amount=Decimal("5"))
        _session, post = _patch_return_common(mocker, purchase, vat_gl=True)
        from services.purchase_service import PurchaseService

        with app.app_context():
            PurchaseService.create_purchase_return(
                purchase,
                _user(),
                [
                    {
                        "purchase_line_id": 1,
                        "product_id": 50,
                        "quantity": 1,
                        "unit_cost": 50,
                    }
                ],
            )
        gl_lines = post.call_args[0][0]
        assert any(l.get("concept_code") == "VAT_INPUT" for l in gl_lines)

    def test_vat_gl_skipped_on_return(self, app, mocker):
        purchase = _purchase(subtotal=Decimal("100"), tax_amount=Decimal("5"))
        _session, post = _patch_return_common(mocker, purchase, vat_gl=False)
        from services.purchase_service import PurchaseService

        with app.app_context():
            PurchaseService.create_purchase_return(
                purchase,
                _user(),
                [
                    {
                        "purchase_line_id": 1,
                        "product_id": 50,
                        "quantity": 1,
                        "unit_cost": 50,
                    }
                ],
            )
        gl_lines = post.call_args[0][0]
        assert not any(l.get("concept_code") == "VAT_INPUT" for l in gl_lines)

    def test_supplier_adjustment_on_return(self, app, mocker):
        purchase = _purchase(tax_amount=None)
        supplier = purchase.supplier
        supplier.total_purchases_aed = Decimal("300")
        session, _post = _patch_return_common(mocker, purchase)
        from services.purchase_service import PurchaseService

        with app.app_context():
            PurchaseService.create_purchase_return(
                purchase,
                _user(),
                [
                    {
                        "purchase_line_id": 1,
                        "product_id": 50,
                        "quantity": 1,
                        "unit_cost": 50,
                    }
                ],
            )
        assert supplier.total_purchases_aed <= Decimal("300")
        session.flush.assert_called()

    def test_serials_marked_returned(self, app, mocker):
        purchase = _purchase(tax_amount=None)
        session, _post = _patch_return_common(mocker, purchase)
        serial = MagicMock(status="available")
        serial_q = MagicMock()
        serial_q.filter_by.return_value.limit.return_value.all.return_value = [serial]
        mocker.patch("models.product_serial.ProductSerial.query", serial_q)
        from services.purchase_service import PurchaseService

        with app.app_context():
            PurchaseService.create_purchase_return(
                purchase,
                _user(),
                [
                    {
                        "purchase_line_id": 1,
                        "product_id": 50,
                        "quantity": 1,
                        "unit_cost": 10,
                    }
                ],
            )
        assert serial.status == "returned"

    def test_mwac_reversal_path(self, app, mocker, monkeypatch):
        purchase = _purchase(tax_amount=None)
        session, _post = _patch_return_common(
            mocker,
            purchase,
            config={"ENABLE_LANDED_COST_CAPITALIZATION": True, "ENABLE_MWAC": True},
        )
        pwc = MagicMock(
            total_quantity=Decimal("10"),
            total_value=Decimal("500"),
            average_cost=Decimal("50"),
        )
        cost_history = MagicMock(movement_unit_cost=Decimal("-45"))
        pwc_q = MagicMock()
        pwc_q.filter_by.return_value.first.return_value = pwc
        pch_q = MagicMock()
        pch_q.filter_by.return_value.order_by.return_value.first.return_value = (
            cost_history
        )
        monkeypatch.setattr(
            "models.product_warehouse_cost.ProductWarehouseCost.query", pwc_q
        )
        monkeypatch.setattr(
            "models.product_cost_history.ProductCostHistory.query", pch_q
        )
        mocker.patch(
            "services.purchase_service.StockService._mwac_calc",
            return_value=(Decimal("9"), Decimal("450"), Decimal("50")),
        )
        mocker.patch("services.purchase_service._safe_for_update", return_value=pwc)
        from services.purchase_service import PurchaseService

        with app.app_context():
            PurchaseService.create_purchase_return(
                purchase,
                _user(),
                [
                    {
                        "purchase_line_id": 1,
                        "product_id": 50,
                        "quantity": 1,
                        "unit_cost": 45,
                    }
                ],
            )
        session.flush.assert_called()

    def test_mwac_no_pwc_skips_reversal(self, app, mocker, monkeypatch):
        purchase = _purchase(tax_amount=None)
        session, _post = _patch_return_common(
            mocker,
            purchase,
            config={"ENABLE_MWAC": True},
        )
        pwc_q = MagicMock()
        pwc_q.filter_by.return_value.first.return_value = None
        monkeypatch.setattr(
            "models.product_warehouse_cost.ProductWarehouseCost.query", pwc_q
        )
        mocker.patch("services.purchase_service._safe_for_update", return_value=None)
        from services.purchase_service import PurchaseService

        with app.app_context():
            PurchaseService.create_purchase_return(
                purchase,
                _user(),
                [
                    {
                        "purchase_line_id": 1,
                        "product_id": 50,
                        "quantity": 1,
                        "unit_cost": 45,
                    }
                ],
            )
        session.flush.assert_called()

    def test_mwac_zero_quantity_pwc_skips(self, app, mocker, monkeypatch):
        purchase = _purchase(tax_amount=None)
        session, _post = _patch_return_common(
            mocker,
            purchase,
            config={"ENABLE_MWAC": True},
        )
        pwc = MagicMock(
            total_quantity=Decimal("0"),
            total_value=Decimal("0"),
            average_cost=Decimal("0"),
        )
        pwc_q = MagicMock()
        pwc_q.filter_by.return_value.first.return_value = pwc
        mocker.patch("services.purchase_service._safe_for_update", return_value=pwc)
        monkeypatch.setattr(
            "models.product_warehouse_cost.ProductWarehouseCost.query", pwc_q
        )
        from services.purchase_service import PurchaseService

        with app.app_context():
            PurchaseService.create_purchase_return(
                purchase,
                _user(),
                [
                    {
                        "purchase_line_id": 1,
                        "product_id": 50,
                        "quantity": 1,
                        "unit_cost": 45,
                    }
                ],
            )
        session.flush.assert_called()

    def test_mwac_negative_qty_clamped(self, app, mocker, monkeypatch):
        purchase = _purchase(tax_amount=None)
        session, _post = _patch_return_common(
            mocker,
            purchase,
            config={"ENABLE_MWAC": True},
        )
        pwc = MagicMock(
            total_quantity=Decimal("1"),
            total_value=Decimal("50"),
            average_cost=Decimal("50"),
        )
        pwc_q = MagicMock()
        pwc_q.filter_by.return_value.first.return_value = pwc
        pch_q = MagicMock()
        pch_q.filter_by.return_value.order_by.return_value.first.return_value = None
        monkeypatch.setattr(
            "models.product_warehouse_cost.ProductWarehouseCost.query", pwc_q
        )
        monkeypatch.setattr(
            "models.product_cost_history.ProductCostHistory.query", pch_q
        )
        mocker.patch(
            "services.purchase_service.StockService._mwac_calc",
            return_value=(Decimal("-1"), Decimal("-10"), Decimal("0")),
        )
        mocker.patch("services.purchase_service._safe_for_update", return_value=pwc)
        from services.purchase_service import PurchaseService

        with app.app_context():
            PurchaseService.create_purchase_return(
                purchase,
                _user(),
                [
                    {
                        "purchase_line_id": 1,
                        "product_id": 50,
                        "quantity": 2,
                        "unit_cost": 50,
                    }
                ],
            )
        assert pwc.total_quantity == Decimal("0")
        session.flush.assert_called()

    def test_commit_failure_rolls_back(self, app, mocker):
        purchase = _purchase(tax_amount=None)
        session, _post = _patch_return_common(mocker, purchase)
        session.flush.side_effect = RuntimeError("return commit fail")
        mock_logger = mocker.patch("services.purchase_service.current_app.logger")
        from services.purchase_service import PurchaseService

        with app.app_context():
            with pytest.raises(RuntimeError, match="return commit fail"):
                PurchaseService.create_purchase_return(
                    purchase,
                    _user(),
                    [
                        {
                            "purchase_line_id": 1,
                            "product_id": 50,
                            "quantity": 1,
                            "unit_cost": 10,
                        }
                    ],
                )
