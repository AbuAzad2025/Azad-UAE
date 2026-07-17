"""Stock service — mocked unit assurance (no real DB)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, PropertyMock

import pytest
from flask import Flask

from utils.gl_reference_types import GLRef


@pytest.fixture
def app():
    application = Flask(__name__)
    application.config.update(
        TESTING=True,
        ENABLE_MWAC=False,
        ENABLE_LANDED_COST_CAPITALIZATION=True,
    )
    return application


@pytest.fixture
def db_session(mocker):
    """Satisfy services/conftest autouse rollback without a real DB."""
    session = mocker.MagicMock(name="db_session")
    yield session


def _product(**kwargs):
    p = MagicMock()
    p.id = kwargs.get("id", 1)
    p.name = kwargs.get("name", "Widget")
    p.tenant_id = kwargs.get("tenant_id", 1)
    p.current_stock = kwargs.get("current_stock", Decimal("100"))
    p.is_active = kwargs.get("is_active", True)
    p.cost_price = kwargs.get("cost_price", Decimal("10"))
    p.min_stock_alert = kwargs.get("min_stock_alert", Decimal("5"))
    return p


def _warehouse(**kwargs):
    wh = MagicMock()
    wh.id = kwargs.get("id", 5)
    wh.tenant_id = kwargs.get("tenant_id", 1)
    wh.is_active = True
    wh.is_main = kwargs.get("is_main", True)
    wh.allow_negative_inventory = kwargs.get("allow_negative_inventory", False)
    wh.name = kwargs.get("name", "Main WH")
    wh.name_ar = kwargs.get("name_ar", "المستودع")
    wh.branch_id = kwargs.get("branch_id", 2)
    return wh


def _pws(**kwargs):
    pws = MagicMock()
    pws.quantity = kwargs.get("quantity", Decimal("50"))
    pws.tenant_id = kwargs.get("tenant_id", 1)
    pws.product_id = kwargs.get("product_id", 1)
    pws.warehouse_id = kwargs.get("warehouse_id", 5)
    return pws


def _pwc(**kwargs):
    pwc = MagicMock()
    pwc.total_quantity = kwargs.get("total_quantity", Decimal("10"))
    pwc.total_value = kwargs.get("total_value", Decimal("100"))
    pwc.average_cost = kwargs.get("average_cost", Decimal("10"))
    return pwc


def _sale_line(**kwargs):
    line = MagicMock()
    line.product_id = kwargs.get("product_id", 1)
    line.quantity = kwargs.get("quantity", Decimal("2"))
    line.cost_price = kwargs.get("cost_price", Decimal("30"))
    return line


def _sale(**kwargs):
    sale = MagicMock()
    sale.id = kwargs.get("id", 100)
    sale.tenant_id = kwargs.get("tenant_id", 1)
    sale.warehouse_id = kwargs.get("warehouse_id", 5)
    sale.sale_number = kwargs.get("sale_number", "S-001")
    sale.lines = kwargs.get("lines", [_sale_line()])
    return sale


def _purchase_line(**kwargs):
    line = MagicMock()
    line.product_id = kwargs.get("product_id", 1)
    line.quantity = kwargs.get("quantity", Decimal("5"))
    line.landed_inventory_unit_cost = kwargs.get(
        "landed_inventory_unit_cost", Decimal("10")
    )
    line.inventory_unit_cost = kwargs.get("inventory_unit_cost", Decimal("8"))
    return line


def _purchase(**kwargs):
    purchase = MagicMock()
    purchase.id = kwargs.get("id", 200)
    purchase.tenant_id = kwargs.get("tenant_id", 1)
    purchase.warehouse_id = kwargs.get("warehouse_id", 5)
    purchase.purchase_number = kwargs.get("purchase_number", "P-001")
    purchase.exchange_rate = kwargs.get("exchange_rate", Decimal("1"))
    purchase.lines = kwargs.get("lines", [_purchase_line()])
    return purchase


def _patch_session(mocker, *, get_map=None):
    session = mocker.patch("services.stock_service.db.session")
    session.commit = MagicMock()
    session.rollback = MagicMock()
    session.flush = MagicMock()
    session.add = MagicMock()
    session.query.return_value.filter.return_value.scalar.return_value = 0

    if get_map is not None:

        def _get(model, pk):
            return get_map.get(pk)

        session.get.side_effect = _get
    return session


def _patch_warehouse_query(mocker, warehouse=None, side_effect=None):
    wh_q = MagicMock()
    chain = wh_q.filter_by.return_value
    chain.first.return_value = warehouse
    if side_effect is not None:
        chain.first.side_effect = side_effect
    mocker.patch("services.stock_service.Warehouse.query", wh_q)
    return wh_q


def _patch_pws_query(mocker, pws=None, lock_error=False):
    pws_q = MagicMock()
    chain = pws_q.filter_by.return_value
    if lock_error:
        chain.with_for_update.side_effect = RuntimeError("no lock")
        chain.first.return_value = pws
    else:
        chain.with_for_update.return_value.first.return_value = pws
    mocker.patch("services.stock_service.ProductWarehouseStock.query", pws_q)
    return pws_q


class TestMWACHelper:
    def test_positive_receipt(self):
        from services.stock_service import _MWACHelper

        new_qty, new_value, new_avg = _MWACHelper.calc(
            Decimal("10"),
            Decimal("100"),
            Decimal("5"),
            Decimal("12"),
        )
        assert new_qty == Decimal("15")
        assert new_value == Decimal("160")
        assert new_avg == Decimal("10.6667")

    def test_zero_qty_returns_zero_avg(self):
        from services.stock_service import _MWACHelper

        new_qty, new_value, new_avg = _MWACHelper.calc(
            Decimal("10"),
            Decimal("100"),
            Decimal("-10"),
            Decimal("10"),
        )
        assert new_qty == Decimal("0")
        assert new_avg == Decimal("0")

    def test_mwac_calc_delegates(self):
        from services.stock_service import StockService

        result = StockService._mwac_calc(
            Decimal("5"),
            Decimal("50"),
            Decimal("5"),
            Decimal("10"),
        )
        assert result[0] == Decimal("10")


class TestResolveGlConceptAccount:
    def test_dynamic_mapping_enabled(self, mocker):
        resolved = MagicMock(account_code="9999")
        mocker.patch(
            "services.gl_account_resolver.is_dynamic_gl_mapping_enabled",
            return_value=True,
        )
        mocker.patch(
            "services.gl_account_resolver.resolve_gl_account", return_value=resolved
        )
        from services.stock_service import _resolve_gl_concept_account

        assert (
            _resolve_gl_concept_account("INVENTORY_ASSET", "1140", tenant_id=1)
            == "9999"
        )

    def test_dynamic_mapping_exception_falls_back(self, mocker):
        mocker.patch(
            "services.gl_account_resolver.is_dynamic_gl_mapping_enabled",
            return_value=True,
        )
        mocker.patch(
            "services.gl_account_resolver.resolve_gl_account",
            side_effect=RuntimeError("fail"),
        )
        mocker.patch(
            "services.gl_service.GL_ACCOUNT_CONCEPTS", {"INV": "INVENTORY_ASSET"}
        )
        mocker.patch("services.gl_service.GL_ACCOUNTS", {})
        from services.stock_service import _resolve_gl_concept_account

        assert (
            _resolve_gl_concept_account("INVENTORY_ASSET", "1140", tenant_id=1)
            == "1140"
        )

    def test_legacy_concept_lookup(self, mocker):
        mocker.patch(
            "services.gl_account_resolver.is_dynamic_gl_mapping_enabled",
            return_value=False,
        )
        mocker.patch(
            "services.gl_service.GL_ACCOUNT_CONCEPTS", {"INV": "INVENTORY_ASSET"}
        )
        mocker.patch("services.gl_service.GL_ACCOUNTS", {"INV": "1140"})
        from services.stock_service import _resolve_gl_concept_account

        assert (
            _resolve_gl_concept_account("INVENTORY_ASSET", "9999", tenant_id=1)
            == "1140"
        )

    def test_fallback_when_no_tenant(self, mocker):
        mocker.patch(
            "services.gl_account_resolver.is_dynamic_gl_mapping_enabled",
            return_value=True,
        )
        from services.stock_service import _resolve_gl_concept_account

        assert (
            _resolve_gl_concept_account("INVENTORY_ASSET", "1140", tenant_id=None)
            == "1140"
        )


class TestAddRemoveStock:
    def test_add_stock_positive_quantity(self, mocker):
        movement = MagicMock()
        mock_create = mocker.patch(
            "services.stock_service.StockService.create_movement", return_value=movement
        )
        from services.stock_service import StockService

        result = StockService.add_stock(1, 5, warehouse_id=5)
        assert result is movement
        assert mock_create.call_args.kwargs["quantity"] == Decimal("5")
        assert mock_create.call_args.kwargs["movement_type"] == "purchase"

    def test_remove_stock_negative_quantity(self, mocker):
        mock_create = mocker.patch(
            "services.stock_service.StockService.create_movement",
            return_value=MagicMock(),
        )
        from services.stock_service import StockService

        StockService.remove_stock(1, 3, warehouse_id=5)
        assert mock_create.call_args.kwargs["quantity"] == Decimal("-3")
        assert mock_create.call_args.kwargs["movement_type"] == "sale"


class TestAdjustStock:
    def test_happy_path_posts_gl(self, mocker, app):
        movement = MagicMock()
        mocker.patch(
            "services.stock_service.StockService.create_movement", return_value=movement
        )
        mocker.patch("services.stock_service.StockService._post_adjustment_gl")
        from services.stock_service import StockService

        with app.app_context():
            result = StockService.adjust_stock(1, Decimal("2"), warehouse_id=5)
        assert result is movement

    def test_rollback_on_create_failure(self, mocker, app):
        mocker.patch("services.stock_service.db.session")
        mocker.patch(
            "services.stock_service.StockService.create_movement",
            side_effect=RuntimeError("fail"),
        )
        mock_logger = mocker.patch("services.stock_service.current_app.logger")
        from services.stock_service import StockService

        with app.app_context():
            with pytest.raises(RuntimeError, match="fail"):
                StockService.adjust_stock(1, Decimal("1"))
        mock_logger.error.assert_called_once()


class TestPostAdjustmentGl:
    def test_skips_missing_product(self, mocker):
        mocker.patch("services.stock_service.db.session").get.return_value = None
        from services.stock_service import StockService

        StockService._post_adjustment_gl(MagicMock(product_id=1))

    def test_skips_no_cost_price(self, mocker):
        product = _product(cost_price=None)
        mocker.patch("services.stock_service.db.session").get.return_value = product
        from services.stock_service import StockService

        StockService._post_adjustment_gl(MagicMock(product_id=1, quantity=Decimal("1")))

    def test_skips_zero_cost_price(self, mocker):
        product = _product(cost_price=Decimal("0"))
        mocker.patch("services.stock_service.db.session").get.return_value = product
        from services.stock_service import StockService

        StockService._post_adjustment_gl(MagicMock(product_id=1, quantity=Decimal("1")))

    def test_skips_zero_quantity_movement(self, mocker):
        product = _product(cost_price=Decimal("10"))
        mocker.patch("services.stock_service.db.session").get.return_value = product
        from services.stock_service import StockService

        StockService._post_adjustment_gl(MagicMock(product_id=1, quantity=Decimal("0")))

    def test_loss_lines_for_negative_qty(self, mocker):
        product = _product()
        warehouse = _warehouse()
        session = mocker.patch("services.stock_service.db.session")
        session.get.side_effect = lambda model, pk: product if pk == 1 else warehouse
        mocker.patch(
            "services.stock_service._resolve_gl_concept_account", return_value="1140"
        )
        mocker.patch("services.gl_service.GLService.ensure_core_accounts")
        mock_post = mocker.patch("services.gl_posting.post_or_fail")
        from services.stock_service import StockService

        StockService._post_adjustment_gl(
            MagicMock(
                product_id=1,
                quantity=Decimal("-2"),
                warehouse_id=5,
                id=9,
                tenant_id=1,
            )
        )
        assert mock_post.called
        assert mock_post.call_args.kwargs["lines"][0]["debit"] > 0

    def test_gain_lines_for_positive_qty(self, mocker):
        product = _product()
        session = mocker.patch("services.stock_service.db.session")
        session.get.return_value = product
        mocker.patch(
            "services.stock_service._resolve_gl_concept_account", return_value="1140"
        )
        mocker.patch("services.gl_service.GLService.ensure_core_accounts")
        mock_post = mocker.patch("services.gl_posting.post_or_fail")
        from services.stock_service import StockService

        StockService._post_adjustment_gl(
            MagicMock(
                product_id=1,
                quantity=Decimal("2"),
                warehouse_id=None,
                id=9,
            )
        )
        assert mock_post.call_args.kwargs["lines"][0]["debit"] > 0


class TestAddOpeningStock:
    def test_with_cost_posts_gl(self, mocker, app):
        product = _product()
        warehouse = _warehouse()
        session = mocker.patch("services.stock_service.db.session")
        session.get.side_effect = lambda model, pk: product if pk == 1 else warehouse
        movement = MagicMock()
        mocker.patch(
            "services.stock_service.StockService.create_movement", return_value=movement
        )
        mocker.patch(
            "services.stock_service._resolve_gl_concept_account", return_value="1140"
        )
        mocker.patch("services.gl_service.GLService.ensure_core_accounts")
        mock_post = mocker.patch("services.gl_posting.post_or_fail")
        from services.stock_service import StockService

        with app.app_context():
            result = StockService.add_opening_stock(1, Decimal("10"), warehouse_id=5)
        assert result is movement
        assert mock_post.called

    def test_without_cost_skips_gl(self, mocker, app):
        product = _product(cost_price=None)
        session = mocker.patch("services.stock_service.db.session")
        session.get.return_value = product
        mocker.patch(
            "services.stock_service.StockService.create_movement",
            return_value=MagicMock(),
        )
        mock_post = mocker.patch("services.gl_posting.post_or_fail")
        from services.stock_service import StockService

        with app.app_context():
            StockService.add_opening_stock(1, Decimal("10"), warehouse_id=5)
        mock_post.assert_not_called()


class TestCreateMovement:
    def test_missing_product_raises(self, mocker, app):
        session = mocker.patch("services.stock_service.db.session")
        session.get.return_value = None
        mocker.patch(
            "services.stock_service.current_user", MagicMock(is_authenticated=False)
        )
        from services.stock_service import StockService

        with app.app_context():
            with pytest.raises(ValueError, match="المنتج غير موجود"):
                StockService.create_movement(
                    999, Decimal("1"), "purchase", warehouse_id=5
                )

    def test_invalid_warehouse_raises(self, mocker, app):
        product = _product()
        session = mocker.patch("services.stock_service.db.session")
        session.get.return_value = product
        _patch_warehouse_query(mocker, warehouse=None)
        from services.stock_service import StockService

        with app.app_context():
            with pytest.raises(ValueError, match="المستودع"):
                StockService.create_movement(
                    1, Decimal("1"), "purchase", warehouse_id=99
                )

    def test_cross_tenant_warehouse_raises(self, mocker, app):
        product = _product(tenant_id=1)
        foreign_wh = _warehouse(id=9, tenant_id=2)
        session = mocker.patch("services.stock_service.db.session")
        session.get.return_value = product
        _patch_warehouse_query(mocker, warehouse=foreign_wh)
        from services.stock_service import StockService

        with app.app_context():
            with pytest.raises(ValueError, match="لا ينتمي"):
                StockService.create_movement(
                    1, Decimal("1"), "purchase", warehouse_id=9
                )

    def test_auto_creates_warehouse_when_missing(self, mocker, app):
        product = _product(tenant_id=1)
        new_wh = _warehouse(id=88)
        session = _patch_session(mocker)
        session.get.return_value = product
        wh_q = MagicMock()
        wh_q.filter_by.return_value.first.side_effect = [None, None]
        wh_cls = mocker.patch("services.stock_service.Warehouse")
        wh_cls.query = wh_q
        wh_cls.return_value = new_wh
        mocker.patch("services.stock_service.StockMovement", return_value=MagicMock())
        pws_q = _patch_pws_query(mocker, pws=None)
        pws_cls = mocker.patch(
            "services.stock_service.ProductWarehouseStock", return_value=MagicMock()
        )
        pws_cls.query = pws_q
        mocker.patch(
            "services.stock_service.current_user",
            MagicMock(is_authenticated=True, id=10),
        )
        from services.stock_service import StockService

        with app.app_context():
            StockService.create_movement(1, Decimal("2"), "purchase")
        session.add.assert_called()
        session.flush.assert_called()

    def test_updates_existing_pws(self, mocker, app):
        product = _product(current_stock=Decimal("100"))
        warehouse = _warehouse()
        pws = _pws(quantity=Decimal("50"))
        session = _patch_session(mocker)
        session.get.return_value = product
        _patch_warehouse_query(mocker, warehouse=warehouse)
        _patch_pws_query(mocker, pws=pws)
        movement = MagicMock()
        mocker.patch("services.stock_service.StockMovement", return_value=movement)
        mocker.patch(
            "services.stock_service.current_user",
            MagicMock(is_authenticated=True, id=10),
        )
        from services.stock_service import StockService

        with app.app_context():
            result = StockService.create_movement(
                1, Decimal("5"), "purchase", warehouse_id=5
            )
        assert result is movement
        assert pws.quantity == Decimal("55")

    def test_creates_pws_when_missing(self, mocker, app):
        product = _product(current_stock=Decimal("0"))
        warehouse = _warehouse()
        session = _patch_session(mocker)
        session.get.return_value = product
        _patch_warehouse_query(mocker, warehouse=warehouse)
        pws_q = _patch_pws_query(mocker, pws=None)
        new_pws = MagicMock()
        pws_cls = mocker.patch("services.stock_service.ProductWarehouseStock")
        pws_cls.return_value = new_pws
        pws_cls.query = pws_q
        mocker.patch("services.stock_service.StockMovement", return_value=MagicMock())
        mocker.patch(
            "services.stock_service.current_user", MagicMock(is_authenticated=False)
        )
        from services.stock_service import StockService

        with app.app_context():
            StockService.create_movement(1, Decimal("7"), "purchase", warehouse_id=5)
        session.add.assert_called()

    def test_insufficient_pws_stock_raises(self, mocker, app):
        product = _product(current_stock=Decimal("5"))
        warehouse = _warehouse(allow_negative_inventory=False)
        pws = _pws(quantity=Decimal("2"))
        session = _patch_session(mocker)
        session.get.return_value = product
        _patch_warehouse_query(mocker, warehouse=warehouse)
        _patch_pws_query(mocker, pws=pws)
        mocker.patch("services.stock_service.StockMovement", return_value=MagicMock())
        from services.stock_service import StockService

        with app.app_context():
            with pytest.raises(ValueError, match="المخزون غير كاف"):
                StockService.create_movement(1, Decimal("-5"), "sale", warehouse_id=5)

    def test_insufficient_new_pws_raises(self, mocker, app):
        product = _product(current_stock=Decimal("0"))
        warehouse = _warehouse()
        session = _patch_session(mocker)
        session.get.return_value = product
        _patch_warehouse_query(mocker, warehouse=warehouse)
        _patch_pws_query(mocker, pws=None)
        mocker.patch("services.stock_service.StockMovement", return_value=MagicMock())
        from services.stock_service import StockService

        with app.app_context():
            with pytest.raises(ValueError, match="أضف مخزوناً"):
                StockService.create_movement(1, Decimal("-1"), "sale", warehouse_id=5)

    def test_global_stock_insufficient_raises(self, mocker, app):
        product = _product(current_stock=Decimal("1"))
        warehouse = _warehouse()
        pws = _pws(quantity=Decimal("10"))
        session = _patch_session(mocker)
        session.get.return_value = product
        session.query.return_value.filter.return_value.scalar.return_value = -1
        _patch_warehouse_query(mocker, warehouse=warehouse)
        _patch_pws_query(mocker, pws=pws)
        mocker.patch("services.stock_service.StockMovement", return_value=MagicMock())
        from services.stock_service import StockService

        with app.app_context():
            with pytest.raises(ValueError, match="المخزون غير كاف"):
                StockService.create_movement(1, Decimal("-5"), "sale", warehouse_id=5)

    def test_current_user_resolution_failure(self, mocker, app):
        product = _product()
        warehouse = _warehouse()
        broken_user = MagicMock(is_authenticated=True)
        type(broken_user).id = PropertyMock(side_effect=RuntimeError("no user"))
        session = _patch_session(mocker)
        session.get.return_value = product
        _patch_warehouse_query(mocker, warehouse=warehouse)
        _patch_pws_query(mocker, pws=_pws())
        movement = MagicMock(user_id=None)
        mocker.patch("services.stock_service.StockMovement", return_value=movement)
        mocker.patch("services.stock_service.current_user", broken_user)
        mock_logger = mocker.patch("services.stock_service.current_app.logger")
        from services.stock_service import StockService

        with app.app_context():
            result = StockService.create_movement(
                1, Decimal("1"), "purchase", warehouse_id=5
            )
        assert result.user_id is None
        mock_logger.debug.assert_called_once()

    def test_logging_exception_swallowed(self, mocker, app):
        product = _product()
        warehouse = _warehouse()
        session = _patch_session(mocker)
        session.get.return_value = product
        _patch_warehouse_query(mocker, warehouse=warehouse)
        _patch_pws_query(mocker, pws=_pws())
        mocker.patch("services.stock_service.StockMovement", return_value=MagicMock())
        mocker.patch(
            "services.stock_service.current_user", MagicMock(is_authenticated=False)
        )
        mock_logger = mocker.patch("services.stock_service.current_app.logger")
        mock_logger.info.side_effect = RuntimeError("log fail")
        from services.stock_service import StockService

        with app.app_context():
            StockService.create_movement(1, Decimal("1"), "purchase", warehouse_id=5)

    def test_pws_lock_fallback(self, mocker, app):
        product = _product()
        warehouse = _warehouse()
        pws = _pws()
        session = _patch_session(mocker)
        session.get.return_value = product
        _patch_warehouse_query(mocker, warehouse=warehouse)
        _patch_pws_query(mocker, pws=pws, lock_error=True)
        mocker.patch("services.stock_service.StockMovement", return_value=MagicMock())
        mocker.patch(
            "services.stock_service.current_user", MagicMock(is_authenticated=False)
        )
        from services.stock_service import StockService

        with app.app_context():
            with pytest.raises(RuntimeError, match="no lock"):
                StockService.create_movement(
                    1, Decimal("1"), "purchase", warehouse_id=5
                )

    def test_warehouse_tenant_backfill(self, mocker, app):
        product = _product(tenant_id=1)
        warehouse = _warehouse(tenant_id=None)
        session = _patch_session(mocker)
        session.get.return_value = product
        _patch_warehouse_query(mocker, warehouse=warehouse)
        _patch_pws_query(mocker, pws=_pws())
        mocker.patch("services.stock_service.StockMovement", return_value=MagicMock())
        from services.stock_service import StockService

        with app.app_context():
            StockService.create_movement(1, Decimal("1"), "purchase", warehouse_id=5)
        assert warehouse.tenant_id == 1


class TestTransferStock:
    def test_invalid_quantity(self, mocker):
        from services.stock_service import StockService

        with pytest.raises(ValueError, match="أكبر من صفر"):
            StockService.transfer_stock(1, 1, 2, Decimal("0"))

    def test_missing_product(self, mocker):
        mocker.patch("services.stock_service.db.session").get.return_value = None
        from services.stock_service import StockService

        with pytest.raises(ValueError, match="المنتج غير موجود"):
            StockService.transfer_stock(999, 1, 2, Decimal("1"))

    def test_missing_warehouse(self, mocker):
        product = _product()
        mocker.patch("services.stock_service.db.session").get.return_value = product
        _patch_warehouse_query(mocker, warehouse=None)
        from services.stock_service import StockService

        with pytest.raises(ValueError, match="غير موجود"):
            StockService.transfer_stock(1, 1, 2, Decimal("1"))

    def test_same_warehouse(self, mocker):
        product = _product()
        wh = _warehouse(id=5)
        mocker.patch("services.stock_service.db.session").get.return_value = product
        wh_q = _patch_warehouse_query(mocker)
        wh_q.filter_by.return_value.first.return_value = wh
        from services.stock_service import StockService

        with pytest.raises(ValueError, match="نفس المستودع"):
            StockService.transfer_stock(1, 5, 5, Decimal("1"))

    def test_tenant_mismatch_product(self, mocker):
        product = _product(tenant_id=1)
        from_wh = _warehouse(id=1, tenant_id=2)
        to_wh = _warehouse(id=2, tenant_id=3)
        mocker.patch("services.stock_service.db.session").get.return_value = product
        wh_q = _patch_warehouse_query(mocker)
        wh_q.filter_by.return_value.first.side_effect = [from_wh, to_wh]
        from services.stock_service import StockService

        with pytest.raises(ValueError, match="تعارض"):
            StockService.transfer_stock(1, 1, 2, Decimal("1"))

    def test_tenant_mismatch_warehouses(self, mocker):
        product = _product(tenant_id=1)
        from_wh = _warehouse(id=1, tenant_id=1)
        to_wh = _warehouse(id=2, tenant_id=2)
        mocker.patch("services.stock_service.db.session").get.return_value = product
        wh_q = _patch_warehouse_query(mocker)
        wh_q.filter_by.return_value.first.side_effect = [from_wh, to_wh]
        from services.stock_service import StockService

        with pytest.raises(ValueError, match="نفس شركة"):
            StockService.transfer_stock(1, 1, 2, Decimal("1"))

    def test_user_permission_denied(self, mocker):
        product = _product(tenant_id=1)
        from_wh = _warehouse(id=1, tenant_id=1)
        to_wh = _warehouse(id=2, tenant_id=1)
        mocker.patch("services.stock_service.db.session").get.return_value = product
        wh_q = _patch_warehouse_query(mocker)
        wh_q.filter_by.return_value.first.side_effect = [from_wh, to_wh]
        mocker.patch("utils.auth_helpers.is_global_owner_user", return_value=False)
        mocker.patch("utils.branching.get_accessible_warehouse_ids", return_value=[1])
        from services.stock_service import StockService

        with pytest.raises(ValueError, match="صلاحية"):
            StockService.transfer_stock(1, 1, 2, Decimal("1"), user=MagicMock())

    def test_insufficient_stock(self, mocker):
        product = _product()
        from_wh = _warehouse(id=1)
        to_wh = _warehouse(id=2)
        mocker.patch("services.stock_service.db.session").get.return_value = product
        wh_q = _patch_warehouse_query(mocker)
        wh_q.filter_by.return_value.first.side_effect = [from_wh, to_wh]
        mocker.patch(
            "services.stock_service.StockService.get_product_stock",
            return_value=Decimal("0"),
        )
        from services.stock_service import StockService

        with pytest.raises(ValueError, match="غير متوفرة"):
            StockService.transfer_stock(1, 1, 2, Decimal("5"))

    def test_happy_path(self, mocker):
        product = _product()
        from_wh = _warehouse(id=1, name="A", name_ar="أ")
        to_wh = _warehouse(id=2, name="B", name_ar="ب")
        mocker.patch("services.stock_service.db.session").get.return_value = product
        wh_q = _patch_warehouse_query(mocker)
        wh_q.filter_by.return_value.first.side_effect = [from_wh, to_wh]
        mocker.patch(
            "services.stock_service.StockService.get_product_stock",
            return_value=Decimal("20"),
        )
        out_mv = MagicMock(id=50)
        in_mv = MagicMock()
        mocker.patch(
            "services.stock_service.StockService.create_movement",
            side_effect=[out_mv, in_mv],
        )
        from services.stock_service import StockService

        result = StockService.transfer_stock(1, 1, 2, Decimal("5"))
        assert result == (out_mv, in_mv)


class TestProcessSaleLines:
    def test_calls_remove_stock_per_line(self, mocker):
        sale = _sale(lines=[_sale_line(product_id=1), _sale_line(product_id=2)])
        mock_remove = mocker.patch("services.stock_service.StockService.remove_stock")
        from services.stock_service import StockService

        StockService.process_sale_lines(sale, warehouse_id=5)
        assert mock_remove.call_count == 2

    def test_uses_sale_warehouse_when_not_passed(self, mocker):
        sale = _sale(warehouse_id=7, lines=[_sale_line()])
        mock_remove = mocker.patch("services.stock_service.StockService.remove_stock")
        from services.stock_service import StockService

        StockService.process_sale_lines(sale)
        assert mock_remove.call_args.kwargs["warehouse_id"] == 7


class TestResolveCogsUnitCost:
    def test_from_pwc_mwac(self, mocker):
        pwc = _pwc(total_quantity=Decimal("10"), average_cost=Decimal("15"))
        pwc_q = MagicMock()
        pwc_q.filter_by.return_value.first.return_value = pwc
        mocker.patch("services.stock_service.ProductWarehouseCost.query", pwc_q)
        from services.stock_service import StockService

        cost, source = StockService._resolve_cogs_unit_cost(1, 5, 1)
        assert cost == Decimal("15")
        assert source == "mwac"

    def test_from_line_cost_price(self, mocker):
        pwc_q = MagicMock()
        pwc_q.filter_by.return_value.first.return_value = None
        mocker.patch("services.stock_service.ProductWarehouseCost.query", pwc_q)
        from services.stock_service import StockService

        cost, source = StockService._resolve_cogs_unit_cost(
            1, 5, 1, line_cost_price=Decimal("25")
        )
        assert cost == Decimal("25")
        assert source == "cost_price"

    def test_from_last_purchase(self, mocker):
        pwc_q = MagicMock()
        pwc_q.filter_by.return_value.first.return_value = None
        mocker.patch("services.stock_service.ProductWarehouseCost.query", pwc_q)
        history = MagicMock()
        history.movement_unit_cost = Decimal("33")
        pch_q = MagicMock()
        pch_q.filter_by.return_value.order_by.return_value.first.return_value = history
        mocker.patch("services.stock_service.ProductCostHistory.query", pch_q)
        from services.stock_service import StockService

        cost, source = StockService._resolve_cogs_unit_cost(1, 5, 1)
        assert cost == Decimal("33")
        assert source == "last_purchase"

    def test_raises_when_unresolved(self, mocker):
        pwc_q = MagicMock()
        pwc_q.filter_by.return_value.first.return_value = None
        mocker.patch("services.stock_service.ProductWarehouseCost.query", pwc_q)
        pch_q = MagicMock()
        pch_q.filter_by.return_value.order_by.return_value.first.return_value = None
        mocker.patch("services.stock_service.ProductCostHistory.query", pch_q)
        from services.stock_service import StockService

        with pytest.raises(ValueError, match="COGS"):
            StockService._resolve_cogs_unit_cost(1, 5, 1)


class TestCalculateSaleCogs:
    def test_mwac_positive_stock(self, mocker, app):
        pwc = _pwc(
            total_quantity=Decimal("100"),
            total_value=Decimal("5000"),
            average_cost=Decimal("50"),
        )
        pwc_q = MagicMock()
        pwc_q.filter_by.return_value.with_for_update.return_value.first.return_value = (
            pwc
        )
        mocker.patch("services.stock_service.ProductWarehouseCost.query", pwc_q)
        mocker.patch("services.stock_service.ProductCostHistory")
        mocker.patch("services.stock_service.db.session")
        warehouse = _warehouse()
        mocker.patch("services.stock_service.db.session").get.return_value = warehouse
        from services.stock_service import StockService

        sale = _sale(
            lines=[_sale_line(quantity=Decimal("2"), cost_price=Decimal("50"))]
        )
        with app.app_context():
            app.config["ENABLE_MWAC"] = True
            total = StockService.calculate_sale_cogs_and_deduct(sale)
        assert total == Decimal("100.000")

    def test_mwac_fallback_warning(self, mocker, app):
        pwc_q = MagicMock()
        pwc_q.filter_by.return_value.with_for_update.return_value.first.return_value = (
            None
        )
        mocker.patch("services.stock_service.ProductWarehouseCost.query", pwc_q)
        mocker.patch("services.stock_service.db.session")
        warehouse = _warehouse(allow_negative_inventory=False)
        mocker.patch("services.stock_service.db.session").get.return_value = warehouse
        mocker.patch(
            "services.stock_service.StockService._resolve_cogs_unit_cost",
            return_value=(Decimal("40"), "cost_price"),
        )
        mock_logger = mocker.patch("services.stock_service.current_app.logger")
        from services.stock_service import StockService

        sale = _sale(lines=[_sale_line(cost_price=Decimal("40"))])
        with app.app_context():
            app.config["ENABLE_MWAC"] = True
            total = StockService.calculate_sale_cogs_and_deduct(sale)
        assert total == Decimal("80.000")
        mock_logger.warning.assert_called()

    def test_negative_inventory_new_pwc(self, mocker, app):
        pwc_q = MagicMock()
        pwc_q.filter_by.return_value.with_for_update.return_value.first.return_value = (
            None
        )
        new_pwc = MagicMock(average_cost=Decimal("30"))
        pwc_cls = mocker.patch("services.stock_service.ProductWarehouseCost")
        pwc_cls.query = pwc_q
        pwc_cls.return_value = new_pwc
        mocker.patch("services.stock_service.ProductCostHistory")
        session = mocker.patch("services.stock_service.db.session")
        warehouse = _warehouse(allow_negative_inventory=True)
        session.get.return_value = warehouse
        mocker.patch(
            "services.stock_service.StockService._resolve_cogs_unit_cost",
            return_value=(Decimal("30"), "cost_price"),
        )
        from services.stock_service import StockService

        sale = _sale(lines=[_sale_line(quantity=Decimal("2"))])
        with app.app_context():
            app.config["ENABLE_MWAC"] = True
            total = StockService.calculate_sale_cogs_and_deduct(sale)
        assert total == Decimal("60.000")

    def test_negative_inventory_existing_pwc(self, mocker, app):
        pwc = _pwc(
            total_quantity=Decimal("-1"),
            total_value=Decimal("-50"),
            average_cost=Decimal("50"),
        )
        pwc_q = MagicMock()
        pwc_q.filter_by.return_value.with_for_update.return_value.first.return_value = (
            pwc
        )
        mocker.patch("services.stock_service.ProductWarehouseCost.query", pwc_q)
        mocker.patch("services.stock_service.ProductCostHistory")
        session = mocker.patch("services.stock_service.db.session")
        warehouse = _warehouse(allow_negative_inventory=True)
        session.get.return_value = warehouse
        mocker.patch(
            "services.stock_service.StockService._resolve_cogs_unit_cost",
            return_value=(Decimal("50"), "mwac"),
        )
        from services.stock_service import StockService

        sale = _sale(lines=[_sale_line(quantity=Decimal("2"))])
        with app.app_context():
            app.config["ENABLE_MWAC"] = True
            total = StockService.calculate_sale_cogs_and_deduct(sale)
        assert total == Decimal("100.000")

    def test_mwac_disabled_fallback(self, mocker, app):
        mocker.patch("services.stock_service.db.session")
        mocker.patch(
            "services.stock_service.StockService._resolve_cogs_unit_cost",
            return_value=(Decimal("30"), "cost_price"),
        )
        from services.stock_service import StockService

        sale = _sale(lines=[_sale_line(quantity=Decimal("2"))])
        with app.app_context():
            app.config["ENABLE_MWAC"] = False
            total = StockService.calculate_sale_cogs_and_deduct(sale)
        assert total == Decimal("60.000")

    def test_lock_fallback(self, mocker, app):
        pwc = _pwc(
            total_quantity=Decimal("50"),
            total_value=Decimal("2500"),
            average_cost=Decimal("50"),
        )
        mocker.patch("services.stock_service._safe_for_update", return_value=pwc)
        mocker.patch("services.stock_service.ProductCostHistory")
        mocker.patch("services.stock_service.db.session").get.return_value = (
            _warehouse()
        )
        from services.stock_service import StockService

        sale = _sale(lines=[_sale_line(quantity=Decimal("1"))])
        with app.app_context():
            app.config["ENABLE_MWAC"] = True
            total = StockService.calculate_sale_cogs_and_deduct(sale)
        assert total == Decimal("50.000")


class TestProcessPurchaseLines:
    def test_without_mwac(self, mocker, app):
        mocker.patch("services.stock_service.StockService.add_stock")
        product = _product()
        session = mocker.patch("services.stock_service.db.session")
        session.get.return_value = product
        from services.stock_service import StockService

        purchase = _purchase()
        with app.app_context():
            app.config["ENABLE_MWAC"] = False
            StockService.process_purchase_lines(purchase)
        session.get.assert_called()

    def test_with_mwac_and_landed_cost(self, mocker, app):
        mocker.patch("services.stock_service.StockService.add_stock")
        mock_wac = mocker.patch(
            "services.stock_service.StockService._update_wac_on_receipt"
        )
        product = _product()
        pwc = _pwc(total_quantity=Decimal("10"), total_value=Decimal("100"))
        pwc_q = MagicMock()
        pwc_q.filter_by.return_value.all.return_value = [pwc]
        mocker.patch("services.stock_service.ProductWarehouseCost.query", pwc_q)
        session = mocker.patch("services.stock_service.db.session")
        session.get.return_value = product
        from services.stock_service import StockService

        purchase = _purchase()
        with app.app_context():
            app.config["ENABLE_MWAC"] = True
            app.config["ENABLE_LANDED_COST_CAPITALIZATION"] = True
            StockService.process_purchase_lines(purchase)
        mock_wac.assert_called_once()

    def test_inventory_unit_cost_when_landed_disabled(self, mocker, app):
        mocker.patch("services.stock_service.StockService.add_stock")
        mock_wac = mocker.patch(
            "services.stock_service.StockService._update_wac_on_receipt"
        )
        product = _product()
        pwc_q = MagicMock()
        pwc_q.filter_by.return_value.all.return_value = []
        mocker.patch("services.stock_service.ProductWarehouseCost.query", pwc_q)
        session = mocker.patch("services.stock_service.db.session")
        session.get.return_value = product
        from services.stock_service import StockService

        purchase = _purchase()
        with app.app_context():
            app.config["ENABLE_MWAC"] = True
            app.config["ENABLE_LANDED_COST_CAPITALIZATION"] = False
            StockService.process_purchase_lines(purchase)
        unit_cost = mock_wac.call_args.kwargs["unit_cost_aed"]
        assert unit_cost == Decimal("8")

    def test_missing_product_skipped(self, mocker, app):
        mocker.patch("services.stock_service.StockService.add_stock")
        session = mocker.patch("services.stock_service.db.session")
        session.get.return_value = None
        from services.stock_service import StockService

        purchase = _purchase()
        with app.app_context():
            app.config["ENABLE_MWAC"] = False
            StockService.process_purchase_lines(purchase)

    def test_zero_qty_cost_price_reset(self, mocker, app):
        mocker.patch("services.stock_service.StockService.add_stock")
        product = _product()
        pwc = _pwc(total_quantity=Decimal("0"), total_value=Decimal("0"))
        pwc_q = MagicMock()
        pwc_q.filter_by.return_value.all.return_value = [pwc]
        mocker.patch("services.stock_service.ProductWarehouseCost.query", pwc_q)
        session = mocker.patch("services.stock_service.db.session")
        session.get.return_value = product
        from services.stock_service import StockService

        purchase = _purchase()
        with app.app_context():
            app.config["ENABLE_MWAC"] = False
            StockService.process_purchase_lines(purchase)
        assert product.cost_price == Decimal("0")

    def test_recalc_skips_missing_product(self, mocker, app):
        mocker.patch("services.stock_service.StockService.add_stock")
        product = _product(id=1)
        pwc_q = MagicMock()
        pwc_q.filter_by.return_value.all.return_value = []
        mocker.patch("services.stock_service.ProductWarehouseCost.query", pwc_q)
        session = mocker.patch("services.stock_service.db.session")
        session.get.side_effect = [product, None]
        from services.stock_service import StockService

        purchase = _purchase()
        with app.app_context():
            app.config["ENABLE_MWAC"] = False
            StockService.process_purchase_lines(purchase)


class TestUpdateWacOnReceipt:
    def test_first_receipt_creates_pwc(self, mocker):
        pwc_q = MagicMock()
        pwc_q.filter_by.return_value.with_for_update.return_value.first.return_value = (
            None
        )
        new_pwc = MagicMock(average_cost=Decimal("5.0000"))
        pwc_cls = mocker.patch("services.stock_service.ProductWarehouseCost")
        pwc_cls.query = pwc_q
        pwc_cls.return_value = new_pwc
        mocker.patch("services.stock_service.ProductCostHistory")
        session = mocker.patch("services.stock_service.db.session")
        from services.stock_service import StockService

        StockService._update_wac_on_receipt(
            tenant_id=1,
            product_id=1,
            warehouse_id=5,
            received_qty=Decimal("10"),
            unit_cost_aed=Decimal("5"),
            reference_type=GLRef.PURCHASE,
            reference_id=1,
        )
        session.add.assert_called()

    def test_existing_pwc_updated(self, mocker):
        pwc = _pwc(
            total_quantity=Decimal("10"),
            total_value=Decimal("100"),
            average_cost=Decimal("10"),
        )
        pwc_q = MagicMock()
        pwc_q.filter_by.return_value.with_for_update.return_value.first.return_value = (
            pwc
        )
        mocker.patch("services.stock_service.ProductWarehouseCost.query", pwc_q)
        mocker.patch("services.stock_service.ProductCostHistory")
        mocker.patch("services.stock_service.db.session")
        from services.stock_service import StockService

        StockService._update_wac_on_receipt(
            tenant_id=1,
            product_id=1,
            warehouse_id=5,
            received_qty=Decimal("10"),
            unit_cost_aed=Decimal("12"),
            reference_type=GLRef.PURCHASE,
            reference_id=2,
        )
        assert pwc.total_quantity == Decimal("20")

    def test_negative_stock_retrospective(self, mocker):
        pwc = _pwc(
            total_quantity=Decimal("-2"),
            total_value=Decimal("-20"),
            average_cost=Decimal("10"),
        )
        pwc_q = MagicMock()
        pwc_q.filter_by.return_value.with_for_update.return_value.first.return_value = (
            pwc
        )
        mocker.patch("services.stock_service.ProductWarehouseCost.query", pwc_q)
        mocker.patch("services.stock_service.ProductCostHistory")
        mocker.patch("services.stock_service.db.session")
        mock_retro = mocker.patch(
            "services.stock_service.StockService._post_retrospective_cost_adjustment",
            return_value=Decimal("1"),
        )
        from services.stock_service import StockService

        StockService._update_wac_on_receipt(
            tenant_id=1,
            product_id=1,
            warehouse_id=5,
            received_qty=Decimal("5"),
            unit_cost_aed=Decimal("12"),
            reference_type=GLRef.PURCHASE,
            reference_id=7,
        )
        mock_retro.assert_called_once()

    def test_lock_fallback(self, mocker):
        pwc = _pwc()
        pwc_q = MagicMock()
        pwc_q.filter_by.return_value.with_for_update.side_effect = RuntimeError("lock")
        pwc_q.filter_by.return_value.first.return_value = pwc
        mocker.patch("services.stock_service.ProductWarehouseCost.query", pwc_q)
        mocker.patch("services.stock_service.ProductCostHistory")
        mocker.patch("services.stock_service.db.session")
        from services.stock_service import StockService

        with pytest.raises(RuntimeError, match="lock"):
            StockService._update_wac_on_receipt(
                tenant_id=1,
                product_id=1,
                warehouse_id=5,
                received_qty=Decimal("1"),
                unit_cost_aed=Decimal("10"),
                reference_type=GLRef.PURCHASE,
                reference_id=1,
            )


class TestPostRetrospectiveCostAdjustment:
    def test_skips_non_negative_qty(self, mocker):
        from services.stock_service import StockService

        assert StockService._post_retrospective_cost_adjustment(
            1,
            1,
            5,
            Decimal("5"),
            Decimal("10"),
            Decimal("12"),
            Decimal("5"),
            GLRef.PURCHASE,
            1,
        ) == Decimal("0")

    def test_skips_invalid_old_avg(self, mocker):
        from services.stock_service import StockService

        assert StockService._post_retrospective_cost_adjustment(
            1,
            1,
            5,
            Decimal("-2"),
            None,
            Decimal("12"),
            Decimal("5"),
            GLRef.PURCHASE,
            1,
        ) == Decimal("0")

    def test_skips_invalid_unit_cost(self, mocker):
        from services.stock_service import StockService

        assert StockService._post_retrospective_cost_adjustment(
            1,
            1,
            5,
            Decimal("-2"),
            Decimal("10"),
            Decimal("0"),
            Decimal("5"),
            GLRef.PURCHASE,
            1,
        ) == Decimal("0")

    def test_skips_near_zero_variance(self, mocker):
        from services.stock_service import StockService

        assert StockService._post_retrospective_cost_adjustment(
            1,
            1,
            5,
            Decimal("-2"),
            Decimal("10"),
            Decimal("10"),
            Decimal("5"),
            GLRef.PURCHASE,
            1,
        ) == Decimal("0")

    def test_loss_variance(self, mocker):
        product = _product()
        warehouse = _warehouse()
        session = mocker.patch("services.stock_service.db.session")
        session.get.side_effect = lambda model, pk: product if pk == 1 else warehouse
        mocker.patch(
            "services.stock_service._resolve_gl_concept_account", return_value="1140"
        )
        mocker.patch("services.gl_service.GLService.ensure_core_accounts")
        mocker.patch("services.gl_posting.post_or_fail")
        from services.stock_service import StockService

        result = StockService._post_retrospective_cost_adjustment(
            1,
            1,
            5,
            Decimal("-5"),
            Decimal("10"),
            Decimal("15"),
            Decimal("10"),
            GLRef.PURCHASE,
            3,
        )
        assert result > Decimal("0")

    def test_gain_variance(self, mocker):
        product = _product()
        warehouse = _warehouse()
        session = mocker.patch("services.stock_service.db.session")
        session.get.side_effect = lambda model, pk: product if pk == 1 else warehouse
        mocker.patch(
            "services.stock_service._resolve_gl_concept_account", return_value="1140"
        )
        mocker.patch("services.gl_service.GLService.ensure_core_accounts")
        mocker.patch("services.gl_posting.post_or_fail")
        from services.stock_service import StockService

        result = StockService._post_retrospective_cost_adjustment(
            1,
            1,
            5,
            Decimal("-5"),
            Decimal("20"),
            Decimal("10"),
            Decimal("10"),
            GLRef.PURCHASE,
            4,
        )
        assert result < Decimal("0")

    def test_post_failure_logged(self, mocker, app):
        product = _product()
        warehouse = _warehouse()
        session = mocker.patch("services.stock_service.db.session")
        session.get.side_effect = lambda model, pk: product if pk == 1 else warehouse
        mocker.patch(
            "services.stock_service._resolve_gl_concept_account", return_value="1140"
        )
        mocker.patch("services.gl_service.GLService.ensure_core_accounts")
        mocker.patch(
            "services.gl_posting.post_or_fail", side_effect=RuntimeError("gl fail")
        )
        mock_logger = mocker.patch("services.stock_service.current_app.logger")
        from services.stock_service import StockService

        with app.app_context():
            result = StockService._post_retrospective_cost_adjustment(
                1,
                1,
                5,
                Decimal("-2"),
                Decimal("10"),
                Decimal("15"),
                Decimal("5"),
                GLRef.PURCHASE,
                5,
            )
        assert result > Decimal("0")
        mock_logger.warning.assert_called_once()


class TestReverseSale:
    def test_without_mwac(self, mocker, app):
        mocker.patch("services.stock_service.StockService.add_stock")
        from services.stock_service import StockService

        with app.app_context():
            app.config["ENABLE_MWAC"] = False
            StockService.reverse_sale(_sale())

    def test_mwac_with_history(self, mocker, app):
        mocker.patch("services.stock_service.StockService.add_stock")
        pwc = _pwc(
            total_quantity=Decimal("8"),
            total_value=Decimal("400"),
            average_cost=Decimal("50"),
        )
        pwc_q = MagicMock()
        pwc_q.filter_by.return_value.with_for_update.return_value.first.return_value = (
            pwc
        )
        mocker.patch("services.stock_service.ProductWarehouseCost.query", pwc_q)
        history = MagicMock()
        history.movement_unit_cost = Decimal("50")
        pch_q = MagicMock()
        pch_q.filter_by.return_value.order_by.return_value.first.return_value = history
        pch_cls = mocker.patch("services.stock_service.ProductCostHistory")
        pch_cls.query = pch_q
        mocker.patch("services.stock_service.db.session")
        from services.stock_service import StockService

        with app.app_context():
            app.config["ENABLE_MWAC"] = True
            StockService.reverse_sale(_sale(id=99))

    def test_mwac_without_history(self, mocker, app):
        mocker.patch("services.stock_service.StockService.add_stock")
        pwc = _pwc(
            total_quantity=Decimal("5"),
            total_value=Decimal("250"),
            average_cost=Decimal("50"),
        )
        pwc_q = MagicMock()
        pwc_q.filter_by.return_value.with_for_update.return_value.first.return_value = (
            pwc
        )
        mocker.patch("services.stock_service.ProductWarehouseCost.query", pwc_q)
        pch_q = MagicMock()
        pch_q.filter_by.return_value.order_by.return_value.first.return_value = None
        pch_cls = mocker.patch("services.stock_service.ProductCostHistory")
        pch_cls.query = pch_q
        mocker.patch("services.stock_service.db.session")
        from services.stock_service import StockService

        with app.app_context():
            app.config["ENABLE_MWAC"] = True
            StockService.reverse_sale(_sale(id=77))

    def test_lock_fallback(self, mocker, app):
        mocker.patch("services.stock_service.StockService.add_stock")
        pwc = _pwc()
        pwc_q = MagicMock()
        pwc_q.filter_by.return_value.with_for_update.side_effect = RuntimeError("lock")
        pwc_q.filter_by.return_value.first.return_value = pwc
        mocker.patch("services.stock_service.ProductWarehouseCost.query", pwc_q)
        pch_q = MagicMock()
        pch_q.filter_by.return_value.order_by.return_value.first.return_value = None
        pch_cls = mocker.patch("services.stock_service.ProductCostHistory")
        pch_cls.query = pch_q
        mocker.patch("services.stock_service.db.session")
        from services.stock_service import StockService

        with app.app_context():
            app.config["ENABLE_MWAC"] = True
            with pytest.raises(RuntimeError, match="lock"):
                StockService.reverse_sale(_sale())


class TestReversePurchase:
    def test_without_mwac(self, mocker, app):
        mocker.patch("services.stock_service.StockService.remove_stock")
        from services.stock_service import StockService

        with app.app_context():
            app.config["ENABLE_MWAC"] = False
            StockService.reverse_purchase(_purchase())

    def test_mwac_with_history(self, mocker, app):
        mocker.patch("services.stock_service.StockService.remove_stock")
        pwc = _pwc(
            total_quantity=Decimal("10"),
            total_value=Decimal("100"),
            average_cost=Decimal("10"),
        )
        pwc_q = MagicMock()
        pwc_q.filter_by.return_value.with_for_update.return_value.first.return_value = (
            pwc
        )
        mocker.patch("services.stock_service.ProductWarehouseCost.query", pwc_q)
        history = MagicMock()
        history.movement_unit_cost = Decimal("10")
        pch_q = MagicMock()
        pch_q.filter_by.return_value.order_by.return_value.first.return_value = history
        pch_cls = mocker.patch("services.stock_service.ProductCostHistory")
        pch_cls.query = pch_q
        mocker.patch("services.stock_service.db.session")
        from services.stock_service import StockService

        with app.app_context():
            app.config["ENABLE_MWAC"] = True
            StockService.reverse_purchase(_purchase(id=50))

    def test_mwac_clamps_negative_qty(self, mocker, app):
        mocker.patch("services.stock_service.StockService.remove_stock")
        pwc = _pwc(
            total_quantity=Decimal("1"),
            total_value=Decimal("10"),
            average_cost=Decimal("10"),
        )
        pwc_q = MagicMock()
        pwc_q.filter_by.return_value.with_for_update.return_value.first.return_value = (
            pwc
        )
        mocker.patch("services.stock_service.ProductWarehouseCost.query", pwc_q)
        history = MagicMock()
        history.movement_unit_cost = Decimal("10")
        pch_q = MagicMock()
        pch_q.filter_by.return_value.order_by.return_value.first.return_value = history
        pch_cls = mocker.patch("services.stock_service.ProductCostHistory")
        pch_cls.query = pch_q
        mocker.patch("services.stock_service.db.session")
        from services.stock_service import StockService

        purchase = _purchase(lines=[_purchase_line(quantity=Decimal("5"))])
        with app.app_context():
            app.config["ENABLE_MWAC"] = True
            StockService.reverse_purchase(purchase)
        assert pwc.total_quantity >= Decimal("0")

    def test_lock_fallback(self, mocker, app):
        mocker.patch("services.stock_service.StockService.remove_stock")
        pwc = _pwc()
        pwc_q = MagicMock()
        pwc_q.filter_by.return_value.with_for_update.side_effect = RuntimeError("lock")
        pwc_q.filter_by.return_value.first.return_value = pwc
        mocker.patch("services.stock_service.ProductWarehouseCost.query", pwc_q)
        pch_q = MagicMock()
        pch_q.filter_by.return_value.order_by.return_value.first.return_value = None
        pch_cls = mocker.patch("services.stock_service.ProductCostHistory")
        pch_cls.query = pch_q
        mocker.patch("services.stock_service.db.session")
        from services.stock_service import StockService

        with app.app_context():
            app.config["ENABLE_MWAC"] = True
            with pytest.raises(RuntimeError, match="lock"):
                StockService.reverse_purchase(_purchase())

    def test_without_cost_history_uses_pwc_avg(self, mocker, app):
        mocker.patch("services.stock_service.StockService.remove_stock")
        pwc = _pwc(
            total_quantity=Decimal("10"),
            total_value=Decimal("100"),
            average_cost=Decimal("12"),
        )
        pwc_q = MagicMock()
        pwc_q.filter_by.return_value.with_for_update.return_value.first.return_value = (
            pwc
        )
        mocker.patch("services.stock_service.ProductWarehouseCost.query", pwc_q)
        pch_q = MagicMock()
        pch_q.filter_by.return_value.order_by.return_value.first.return_value = None
        pch_cls = mocker.patch("services.stock_service.ProductCostHistory")
        pch_cls.query = pch_q
        mocker.patch("services.stock_service.db.session")
        from services.stock_service import StockService

        with app.app_context():
            app.config["ENABLE_MWAC"] = True
            StockService.reverse_purchase(_purchase())


class TestAvailability:
    def test_check_missing_product(self, mocker):
        mocker.patch("services.stock_service.db.session").get.return_value = None
        from services.stock_service import StockService

        ok, msg = StockService.check_availability(999, 1)
        assert ok is False
        assert "غير موجود" in msg

    def test_check_inactive_product(self, mocker):
        mocker.patch("services.stock_service.db.session").get.return_value = _product(
            is_active=False
        )
        from services.stock_service import StockService

        ok, msg = StockService.check_availability(1, 1)
        assert ok is False
        assert "غير نشط" in msg

    def test_check_insufficient(self, mocker):
        mocker.patch("services.stock_service.db.session").get.return_value = _product(
            current_stock=Decimal("1")
        )
        from services.stock_service import StockService

        ok, msg = StockService.check_availability(1, 5)
        assert ok is False
        assert "غير كاف" in msg

    def test_check_success(self, mocker):
        mocker.patch("services.stock_service.db.session").get.return_value = _product(
            current_stock=Decimal("10")
        )
        from services.stock_service import StockService

        ok, msg = StockService.check_availability(1, 3)
        assert ok is True
        assert msg == "متوفر"

    def test_check_in_warehouse_missing_product(self, mocker):
        mocker.patch("services.stock_service.db.session").get.return_value = None
        from services.stock_service import StockService

        ok, msg = StockService.check_availability_in_warehouse(1, 1, 5)
        assert ok is False

    def test_check_in_warehouse_inactive_product(self, mocker):
        mocker.patch("services.stock_service.db.session").get.return_value = _product(
            is_active=False
        )
        from services.stock_service import StockService

        ok, msg = StockService.check_availability_in_warehouse(1, 1, 5)
        assert ok is False
        assert "غير نشط" in msg

    def test_check_in_warehouse_missing_wh(self, mocker):
        mocker.patch("services.stock_service.db.session").get.return_value = _product()
        _patch_warehouse_query(mocker, warehouse=None)
        from services.stock_service import StockService

        ok, msg = StockService.check_availability_in_warehouse(1, 1, 999)
        assert ok is False
        assert "المستودع" in msg

    def test_check_in_warehouse_negative_allowed(self, mocker):
        mocker.patch("services.stock_service.db.session").get.return_value = _product()
        _patch_warehouse_query(
            mocker, warehouse=_warehouse(allow_negative_inventory=True)
        )
        from services.stock_service import StockService

        ok, msg = StockService.check_availability_in_warehouse(1, 999, 5)
        assert ok is True
        assert "السالب" in msg

    def test_check_in_warehouse_insufficient(self, mocker):
        mocker.patch("services.stock_service.db.session").get.return_value = _product()
        _patch_warehouse_query(mocker, warehouse=_warehouse())
        mocker.patch(
            "services.stock_service.StockService.get_product_stock",
            return_value=Decimal("1"),
        )
        from services.stock_service import StockService

        ok, msg = StockService.check_availability_in_warehouse(1, 5, 5)
        assert ok is False

    def test_check_in_warehouse_success(self, mocker):
        mocker.patch("services.stock_service.db.session").get.return_value = _product()
        _patch_warehouse_query(mocker, warehouse=_warehouse())
        mocker.patch(
            "services.stock_service.StockService.get_product_stock",
            return_value=Decimal("10"),
        )
        from services.stock_service import StockService

        ok, msg = StockService.check_availability_in_warehouse(1, 3, 5)
        assert ok is True


class TestInventoryQueries:
    def test_get_product_stock_by_warehouse(self, mocker):
        mocker.patch(
            "services.stock_service.get_branch_stock_map",
            return_value={1: Decimal("42")},
        )
        from services.stock_service import StockService

        assert StockService.get_product_stock(1, warehouse_id=5) == Decimal("42")

    def test_get_product_stock_by_warehouse_ids(self, mocker):
        mocker.patch(
            "services.stock_service.get_branch_stock_map",
            return_value={1: Decimal("9")},
        )
        from services.stock_service import StockService

        assert StockService.get_product_stock(1, warehouse_ids=[1, 2]) == Decimal("9")

    def test_get_product_stock_with_user(self, mocker):
        mocker.patch(
            "services.stock_service.get_accessible_warehouse_ids", return_value=[1]
        )
        mocker.patch(
            "services.stock_service.get_branch_stock_map",
            return_value={1: Decimal("3")},
        )
        from services.stock_service import StockService

        assert StockService.get_product_stock(1, user=MagicMock()) == Decimal("3")

    def test_get_low_stock_with_warehouses(self, mocker):
        product = _product(min_stock_alert=Decimal("5"))
        query = MagicMock()
        query.order_by.return_value.all.return_value = [product]
        mocker.patch(
            "services.stock_service.StockService.get_visible_products_query",
            return_value=query,
        )
        mocker.patch(
            "services.stock_service.get_accessible_warehouse_ids", return_value=[1]
        )
        mocker.patch(
            "services.stock_service.get_branch_stock_map",
            return_value={1: Decimal("2")},
        )
        from services.stock_service import StockService

        assert StockService.get_low_stock_products() == [product]

    def test_get_low_stock_no_access(self, mocker):
        mocker.patch(
            "services.stock_service.StockService.get_visible_products_query",
            return_value=MagicMock(),
        )
        mocker.patch(
            "services.stock_service.get_accessible_warehouse_ids", return_value=[]
        )
        from services.stock_service import StockService

        assert StockService.get_low_stock_products(user=MagicMock()) == []

    def test_get_low_stock_global_fallback(self, mocker):
        product = _product(min_stock_alert=Decimal("5"), current_stock=Decimal("1"))
        query = MagicMock()
        query.order_by.return_value.all.return_value = [product]
        mocker.patch(
            "services.stock_service.StockService.get_visible_products_query",
            return_value=query,
        )
        mocker.patch(
            "services.stock_service.get_accessible_warehouse_ids", return_value=None
        )
        from services.stock_service import StockService

        assert StockService.get_low_stock_products() == [product]

    def test_get_low_stock_with_limit(self, mocker):
        products = [
            _product(id=1, current_stock=Decimal("1")),
            _product(id=2, current_stock=Decimal("2")),
        ]
        query = MagicMock()
        query.order_by.return_value.all.return_value = products
        mocker.patch(
            "services.stock_service.StockService.get_visible_products_query",
            return_value=query,
        )
        mocker.patch(
            "services.stock_service.get_accessible_warehouse_ids", return_value=None
        )
        from services.stock_service import StockService

        result = StockService.get_low_stock_products(limit=1)
        assert len(result) == 1

    def test_get_out_of_stock_with_warehouses(self, mocker):
        product = _product()
        query = MagicMock()
        query.order_by.return_value.all.return_value = [product]
        mocker.patch(
            "services.stock_service.StockService.get_visible_products_query",
            return_value=query,
        )
        mocker.patch(
            "services.stock_service.get_accessible_warehouse_ids", return_value=[1]
        )
        mocker.patch(
            "services.stock_service.get_branch_stock_map",
            return_value={1: Decimal("0")},
        )
        from services.stock_service import StockService

        assert product in StockService.get_out_of_stock_products()

    def test_get_out_of_stock_no_access(self, mocker):
        mocker.patch(
            "services.stock_service.StockService.get_visible_products_query",
            return_value=MagicMock(),
        )
        mocker.patch(
            "services.stock_service.get_accessible_warehouse_ids", return_value=[]
        )
        from services.stock_service import StockService

        assert StockService.get_out_of_stock_products(user=MagicMock()) == []

    def test_get_out_of_stock_global(self, mocker):
        product = _product(current_stock=Decimal("0"))
        query = MagicMock()
        query.order_by.return_value.all.return_value = [product]
        mocker.patch(
            "services.stock_service.StockService.get_visible_products_query",
            return_value=query,
        )
        mocker.patch(
            "services.stock_service.get_accessible_warehouse_ids", return_value=None
        )
        from services.stock_service import StockService

        assert product in StockService.get_out_of_stock_products()

    def test_get_visible_products_query_delegates(self, mocker):
        mocker.patch("utils.branching.get_visible_products_query", return_value="query")
        from services.stock_service import StockService

        assert StockService.get_visible_products_query() == "query"


class TestReconcileStock:
    def _setup_reconcile_queries(
        self, mocker, *, existing_rows, movement_rows, pws_sum_rows, products
    ):
        session = mocker.patch("services.stock_service.db.session")

        existing_q = MagicMock()
        existing_q.filter.return_value = existing_q
        existing_q.all.return_value = existing_rows

        movement_q = MagicMock()
        movement_q.filter.return_value = movement_q
        movement_q.group_by.return_value.all.return_value = movement_rows

        pws_q = MagicMock()
        pws_q.filter.return_value = pws_q
        pws_q.filter_by.return_value.first.return_value = MagicMock(
            quantity=Decimal("5")
        )
        pws_q.group_by.return_value.all.return_value = pws_sum_rows

        product_q = MagicMock()
        product_q.filter.return_value.all.return_value = products

        session.query.side_effect = [existing_q, movement_q, pws_q, product_q]
        session.get.return_value = _warehouse()
        return session

    def test_updates_mismatch(self, mocker):
        existing = MagicMock(tenant_id=1, product_id=1, warehouse_id=5)
        movement = MagicMock(product_id=1, warehouse_id=5, total_qty=Decimal("10"))
        pws = MagicMock(product_id=1, total=Decimal("10"))
        product = _product(current_stock=Decimal("5"))
        pws_row = MagicMock(quantity=Decimal("5"))
        session = self._setup_reconcile_queries(
            mocker,
            existing_rows=[existing],
            movement_rows=[movement],
            pws_sum_rows=[pws],
            products=[product],
        )
        pws_q = MagicMock()
        pws_q.filter_by.return_value.first.return_value = pws_row
        mocker.patch("services.stock_service.ProductWarehouseStock.query", pws_q)
        product_q = MagicMock()
        product_q.filter.return_value.all.return_value = [product]
        mocker.patch("services.stock_service.Product.query", product_q)
        from services.stock_service import StockService

        result = StockService.reconcile_stock(tenant_id=1, commit=False)
        assert result["updated"] >= 1
        assert product.current_stock == Decimal("10")
        session.flush.assert_called_once()

    def test_creates_missing_pws(self, mocker):
        movement = MagicMock(product_id=1, warehouse_id=5, total_qty=Decimal("3"))
        pws_sum = MagicMock(product_id=1, total=Decimal("3"))
        product = _product(current_stock=Decimal("3"))
        self._setup_reconcile_queries(
            mocker,
            existing_rows=[],
            movement_rows=[movement],
            pws_sum_rows=[pws_sum],
            products=[product],
        )
        pws_cls = mocker.patch("services.stock_service.ProductWarehouseStock")
        pws_cls.return_value = MagicMock()
        from services.stock_service import StockService

        result = StockService.reconcile_stock(tenant_id=1, commit=False)
        assert result["created"] >= 1

    def test_commit_error_increments_errors(self, mocker):
        session = self._setup_reconcile_queries(
            mocker,
            existing_rows=[],
            movement_rows=[],
            pws_sum_rows=[],
            products=[],
        )
        session.flush.side_effect = RuntimeError("commit fail")
        from services.stock_service import StockService

        result = StockService.reconcile_stock(tenant_id=1, commit=True)
        assert result["errors"] == 1
