from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from extensions import db
from models import (
    Product,
    ProductCostHistory,
    ProductWarehouseCost,
    StockMovement,
    Tenant,
    Warehouse,
)
from models.warehouse import ProductWarehouseStock
from services.stock_service import (
    StockService,
    _MWACHelper,
    _resolve_gl_concept_account,
)
from utils.gl_reference_types import GLRef


@pytest.fixture
def enable_mwac(app, mocker):
    with app.app_context():
        app.config["ENABLE_MWAC"] = True
        mocker.patch("services.stock_service.current_app", app)
        yield app


class TestMWACHelper:
    def test_positive_receipt(self):
        new_qty, new_value, new_avg = _MWACHelper.calc(
            Decimal("10"), Decimal("100"), Decimal("5"), Decimal("12")
        )
        assert new_qty == Decimal("15")
        assert new_value == Decimal("160")
        assert new_avg == Decimal("10.6667")

    def test_zero_qty_returns_zero_avg(self):
        new_qty, new_value, new_avg = _MWACHelper.calc(
            Decimal("10"), Decimal("100"), Decimal("-10"), Decimal("10")
        )
        assert new_qty == Decimal("0")
        assert new_avg == Decimal("0")


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
        code = _resolve_gl_concept_account("INVENTORY_ASSET", "1140", tenant_id=1)
        assert code == "9999"

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
            "services.gl_service.GL_ACCOUNT_CONCEPTS",
            {"INVENTORY_ASSET": "INVENTORY_ASSET"},
        )
        mocker.patch("services.gl_service.GL_ACCOUNTS", {})
        code = _resolve_gl_concept_account("INVENTORY_ASSET", "1140", tenant_id=1)
        assert code == "1140"

    def test_legacy_concept_lookup(self, mocker):
        mocker.patch(
            "services.gl_account_resolver.is_dynamic_gl_mapping_enabled",
            return_value=False,
        )
        mocker.patch(
            "services.gl_service.GL_ACCOUNT_CONCEPTS", {"INV": "INVENTORY_ASSET"}
        )
        mocker.patch("services.gl_service.GL_ACCOUNTS", {"INV": "1140"})
        code = _resolve_gl_concept_account("INVENTORY_ASSET", "9999", tenant_id=1)
        assert code == "1140"


class TestCreateMovement:
    def test_add_stock_increases_quantity(
        self, db_session, sample_product, sample_warehouse
    ):
        movement = StockService.add_stock(
            sample_product.id,
            Decimal("5"),
            warehouse_id=sample_warehouse.id,
        )
        assert movement.quantity == Decimal("5")
        db_session.flush()
        db_session.refresh(sample_product)
        assert sample_product.current_stock == Decimal("5")

    def test_remove_stock_decreases_quantity(
        self, db_session, sample_product, sample_warehouse
    ):
        StockService.add_stock(
            sample_product.id, Decimal("10"), warehouse_id=sample_warehouse.id
        )
        db_session.flush()
        movement = StockService.remove_stock(
            sample_product.id,
            Decimal("3"),
            warehouse_id=sample_warehouse.id,
        )
        assert movement.quantity == Decimal("-3")

    def test_missing_product_raises(self, db_session, sample_warehouse):
        with pytest.raises(ValueError, match="المنتج غير موجود"):
            StockService.create_movement(
                999999,
                Decimal("1"),
                "purchase",
                warehouse_id=sample_warehouse.id,
            )

    def test_invalid_warehouse_raises(self, db_session, sample_product):
        with pytest.raises(ValueError, match="المستودع"):
            StockService.create_movement(
                sample_product.id,
                Decimal("1"),
                "purchase",
                warehouse_id=999999,
            )

    def test_cross_tenant_warehouse_raises(self, db_session, sample_product):
        uid = uuid.uuid4().hex[:12]
        foreign_tenant = Tenant(
            name=f"Foreign Co {uid}",
            name_ar=f"شركة أجنبية {uid}",
            slug=f"foreign-co-{uid}",
            email=f"foreign-{uid}@example.com",
            phone_1="0500000099",
            country="AE",
            subscription_plan="basic",
            default_currency="AED",
            base_currency="AED",
            is_active=True,
        )
        db_session.add(foreign_tenant)
        db_session.flush()
        foreign_wh = Warehouse(
            tenant_id=foreign_tenant.id,
            name=f"Foreign WH {uid}",
            name_ar=f"مستودع أجنبي {uid}",
            is_active=True,
        )
        db_session.add(foreign_wh)
        db_session.flush()
        with pytest.raises(ValueError, match="لا ينتمي"):
            StockService.create_movement(
                sample_product.id,
                Decimal("1"),
                "purchase",
                warehouse_id=foreign_wh.id,
            )

    def test_insufficient_stock_raises(
        self, db_session, sample_product, sample_warehouse
    ):
        with pytest.raises(ValueError, match="المخزون غير كاف"):
            StockService.remove_stock(
                sample_product.id,
                Decimal("1000"),
                warehouse_id=sample_warehouse.id,
            )

    def test_creates_pws_when_missing(
        self, db_session, sample_tenant, sample_warehouse
    ):
        product = Product(
            tenant_id=sample_tenant.id,
            name="New Product",
            sku=f"SKU-{uuid.uuid4().hex[:6]}",
            cost_price=Decimal("10"),
            regular_price=Decimal("20"),
            current_stock=Decimal("0"),
        )
        db_session.add(product)
        db_session.flush()
        StockService.add_stock(
            product.id, Decimal("7"), warehouse_id=sample_warehouse.id
        )
        pws = ProductWarehouseStock.query.filter_by(
            product_id=product.id,
            warehouse_id=sample_warehouse.id,
        ).first()
        assert pws.quantity == Decimal("7")

    def test_auto_creates_main_warehouse(self, db_session, sample_tenant):
        product = Product(
            tenant_id=sample_tenant.id,
            name="No WH Product",
            sku=f"SKU-{uuid.uuid4().hex[:6]}",
            cost_price=Decimal("10"),
            regular_price=Decimal("20"),
            current_stock=Decimal("0"),
        )
        db_session.add(product)
        db_session.flush()
        Warehouse.query.filter_by(tenant_id=sample_tenant.id).delete()
        db_session.flush()
        movement = StockService.add_stock(product.id, Decimal("2"))
        assert movement.warehouse_id is not None


class TestTransferStock:
    def test_transfer_between_warehouses(
        self, db_session, sample_product, sample_tenant, sample_branch
    ):
        wh_a = Warehouse(
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            name="WH A",
            is_active=True,
        )
        wh_b = Warehouse(
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            name="WH B",
            is_active=True,
        )
        db_session.add_all([wh_a, wh_b])
        db_session.flush()
        StockService.add_stock(sample_product.id, Decimal("20"), warehouse_id=wh_a.id)
        db_session.flush()
        before = sample_product.current_stock
        out_mv, in_mv = StockService.transfer_stock(
            sample_product.id,
            wh_a.id,
            wh_b.id,
            Decimal("5"),
        )
        db_session.flush()
        db_session.refresh(sample_product)
        assert out_mv.quantity == Decimal("-5")
        assert in_mv.quantity == Decimal("5")
        assert sample_product.current_stock == before

    def test_transfer_invalid_quantity(
        self, db_session, sample_product, sample_warehouse
    ):
        with pytest.raises(ValueError, match="أكبر من صفر"):
            StockService.transfer_stock(
                sample_product.id,
                sample_warehouse.id,
                sample_warehouse.id,
                Decimal("0"),
            )

    def test_transfer_same_warehouse(
        self, db_session, sample_product, sample_warehouse
    ):
        wh2 = Warehouse(
            tenant_id=sample_warehouse.tenant_id,
            branch_id=sample_warehouse.branch_id,
            name="WH2",
            is_active=True,
        )
        db_session.add(wh2)
        db_session.flush()
        with pytest.raises(ValueError, match="نفس المستودع"):
            StockService.transfer_stock(
                sample_product.id,
                sample_warehouse.id,
                sample_warehouse.id,
                Decimal("1"),
            )

    def test_transfer_user_access_denied(
        self, db_session, sample_product, sample_tenant, sample_branch, mocker
    ):
        wh_a = Warehouse(
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            name="A",
            is_active=True,
        )
        wh_b = Warehouse(
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            name="B",
            is_active=True,
        )
        db_session.add_all([wh_a, wh_b])
        db_session.flush()
        StockService.add_stock(sample_product.id, Decimal("10"), warehouse_id=wh_a.id)
        db_session.flush()
        user = MagicMock()
        mocker.patch("utils.auth_helpers.is_global_owner_user", return_value=False)
        mocker.patch(
            "utils.branching.get_accessible_warehouse_ids", return_value=[wh_a.id]
        )
        with pytest.raises(ValueError, match="صلاحية"):
            StockService.transfer_stock(
                sample_product.id,
                wh_a.id,
                wh_b.id,
                Decimal("1"),
                user=user,
            )


class TestAdjustAndOpeningStock:
    def test_adjust_stock_posts_gl(
        self, db_session, sample_product, sample_warehouse, mocker
    ):
        mocker.patch(
            "services.stock_service._resolve_gl_concept_account", return_value="1140"
        )
        mocker.patch("services.gl_service.GLService.ensure_core_accounts")
        mocker.patch("services.gl_posting.post_or_fail")
        movement = StockService.adjust_stock(
            sample_product.id,
            Decimal("2"),
            warehouse_id=sample_warehouse.id,
        )
        assert movement.movement_type == "adjustment"

    def test_adjust_stock_rollback_on_error(
        self, db_session, sample_product, mocker, app
    ):
        mocker.patch.object(
            StockService, "create_movement", side_effect=RuntimeError("fail")
        )
        with pytest.raises(RuntimeError):
            with app.app_context():
                StockService.adjust_stock(sample_product.id, Decimal("1"))

    def test_post_adjustment_gl_skips_no_cost(
        self, db_session, sample_tenant, sample_warehouse
    ):
        product = Product(
            tenant_id=sample_tenant.id,
            name="No Cost",
            sku=f"SKU-{uuid.uuid4().hex[:6]}",
            cost_price=None,
            regular_price=Decimal("20"),
            current_stock=Decimal("0"),
        )
        db_session.add(product)
        db_session.flush()
        movement = MagicMock(
            product_id=product.id,
            quantity=Decimal("1"),
            warehouse_id=sample_warehouse.id,
        )
        StockService._post_adjustment_gl(movement)

    def test_add_opening_stock_with_gl(
        self, db_session, sample_product, sample_warehouse, mocker
    ):
        mocker.patch(
            "services.stock_service._resolve_gl_concept_account", return_value="1140"
        )
        mocker.patch("services.gl_service.GLService.ensure_core_accounts")
        mock_post = mocker.patch("services.gl_posting.post_or_fail")
        StockService.add_opening_stock(
            sample_product.id,
            Decimal("10"),
            warehouse_id=sample_warehouse.id,
        )
        assert mock_post.called


class TestAvailability:
    def test_check_availability_ok(self, sample_product):
        ok, msg = StockService.check_availability(sample_product.id, Decimal("10"))
        assert ok is True

    def test_check_availability_insufficient(self, sample_product):
        ok, msg = StockService.check_availability(sample_product.id, Decimal("99999"))
        assert ok is False

    def test_check_availability_missing_product(self):
        ok, msg = StockService.check_availability(999999, Decimal("1"))
        assert ok is False

    def test_check_availability_inactive_product(self, db_session, sample_product):
        sample_product.is_active = False
        db_session.flush()
        ok, msg = StockService.check_availability(sample_product.id, Decimal("1"))
        assert ok is False

    def test_check_availability_in_warehouse_negative_allowed(
        self, db_session, sample_product, sample_warehouse
    ):
        sample_warehouse.allow_negative_inventory = True
        db_session.flush()
        ok, msg = StockService.check_availability_in_warehouse(
            sample_product.id,
            Decimal("99999"),
            sample_warehouse.id,
        )
        assert ok is True

    def test_check_availability_in_warehouse_insufficient(
        self, db_session, sample_product, sample_warehouse
    ):
        ok, msg = StockService.check_availability_in_warehouse(
            sample_product.id,
            Decimal("99999"),
            sample_warehouse.id,
        )
        assert ok is False

    def test_get_product_stock(
        self, db_session, sample_product, sample_warehouse, mocker
    ):
        mocker.patch(
            "services.stock_service.get_branch_stock_map",
            return_value={sample_product.id: Decimal("42")},
        )
        qty = StockService.get_product_stock(
            sample_product.id, warehouse_id=sample_warehouse.id
        )
        assert qty == Decimal("42")


class TestCogsAndPurchase:
    def test_resolve_cogs_from_pwc(
        self, db_session, sample_tenant, sample_product, sample_warehouse
    ):
        pwc = ProductWarehouseCost(
            tenant_id=sample_tenant.id,
            product_id=sample_product.id,
            warehouse_id=sample_warehouse.id,
            total_quantity=Decimal("10"),
            total_value=Decimal("100"),
            average_cost=Decimal("10"),
        )
        db_session.add(pwc)
        db_session.flush()
        cost, source = StockService._resolve_cogs_unit_cost(
            sample_product.id,
            sample_warehouse.id,
            sample_tenant.id,
        )
        assert cost == Decimal("10")
        assert source == "mwac"

    def test_resolve_cogs_from_line_cost(
        self, db_session, sample_tenant, sample_product, sample_warehouse
    ):
        cost, source = StockService._resolve_cogs_unit_cost(
            sample_product.id,
            sample_warehouse.id,
            sample_tenant.id,
            line_cost_price=Decimal("25"),
        )
        assert cost == Decimal("25")
        assert source == "cost_price"

    def test_resolve_cogs_raises_when_unresolved(
        self, db_session, sample_tenant, sample_product, sample_warehouse
    ):
        with pytest.raises(ValueError, match="COGS"):
            StockService._resolve_cogs_unit_cost(
                sample_product.id,
                sample_warehouse.id,
                sample_tenant.id,
            )

    def test_calculate_sale_cogs_mwac(
        self, db_session, sample_tenant, sample_product, sample_warehouse, enable_mwac
    ):
        pwc = ProductWarehouseCost(
            tenant_id=sample_tenant.id,
            product_id=sample_product.id,
            warehouse_id=sample_warehouse.id,
            total_quantity=Decimal("100"),
            total_value=Decimal("5000"),
            average_cost=Decimal("50"),
        )
        db_session.add(pwc)
        db_session.flush()
        line = SimpleNamespace(
            product_id=sample_product.id,
            quantity=Decimal("2"),
            cost_price=Decimal("50"),
        )
        sale = SimpleNamespace(
            tenant_id=sample_tenant.id,
            warehouse_id=sample_warehouse.id,
            sale_number="S-1",
            id=1,
            lines=[line],
        )
        with enable_mwac.app_context():
            total = StockService.calculate_sale_cogs_and_deduct(sale)
        assert total == Decimal("100.000")

    def test_calculate_sale_cogs_fallback(
        self, db_session, sample_tenant, sample_product, sample_warehouse, app
    ):
        line = MagicMock(
            product_id=sample_product.id,
            quantity=Decimal("2"),
            cost_price=Decimal("30"),
        )
        sale = MagicMock(
            tenant_id=sample_tenant.id,
            warehouse_id=sample_warehouse.id,
            sale_number="S-2",
            lines=[line],
        )
        with app.app_context():
            app.config["ENABLE_MWAC"] = False
            total = StockService.calculate_sale_cogs_and_deduct(sale)
        assert total == Decimal("60.000")

    def test_process_sale_lines(self, mocker):
        sale = MagicMock(
            id=1,
            sale_number="S-3",
            warehouse_id=5,
            lines=[MagicMock(product_id=1, quantity=Decimal("1"))],
        )
        mock_remove = mocker.patch.object(StockService, "remove_stock")
        StockService.process_sale_lines(sale)
        assert mock_remove.called

    def test_process_purchase_lines(
        self, db_session, sample_tenant, sample_product, sample_warehouse, app, mocker
    ):
        mocker.patch.object(StockService, "add_stock")
        line = MagicMock(
            product_id=sample_product.id,
            quantity=Decimal("5"),
            landed_inventory_unit_cost=Decimal("10"),
            inventory_unit_cost=Decimal("8"),
        )
        purchase = MagicMock(
            tenant_id=sample_tenant.id,
            warehouse_id=sample_warehouse.id,
            purchase_number="P-1",
            exchange_rate=Decimal("1"),
            lines=[line],
        )
        with app.app_context():
            app.config["ENABLE_MWAC"] = False
            app.config["ENABLE_LANDED_COST_CAPITALIZATION"] = True
            StockService.process_purchase_lines(purchase)


class TestWacAndRetrospective:
    def test_update_wac_on_receipt_first_time(
        self, db_session, sample_tenant, sample_product, sample_warehouse
    ):
        StockService._update_wac_on_receipt(
            tenant_id=sample_tenant.id,
            product_id=sample_product.id,
            warehouse_id=sample_warehouse.id,
            received_qty=Decimal("10"),
            unit_cost_aed=Decimal("5"),
            reference_type=GLRef.PURCHASE,
            reference_id=1,
        )
        pwc = ProductWarehouseCost.query.filter_by(
            tenant_id=sample_tenant.id,
            product_id=sample_product.id,
            warehouse_id=sample_warehouse.id,
        ).first()
        assert pwc.total_quantity == Decimal("10")
        assert pwc.average_cost == Decimal("5.0000")

    def test_update_wac_on_receipt_existing(
        self, db_session, sample_tenant, sample_product, sample_warehouse
    ):
        pwc = ProductWarehouseCost(
            tenant_id=sample_tenant.id,
            product_id=sample_product.id,
            warehouse_id=sample_warehouse.id,
            total_quantity=Decimal("10"),
            total_value=Decimal("100"),
            average_cost=Decimal("10"),
        )
        db_session.add(pwc)
        db_session.flush()
        StockService._update_wac_on_receipt(
            tenant_id=sample_tenant.id,
            product_id=sample_product.id,
            warehouse_id=sample_warehouse.id,
            received_qty=Decimal("10"),
            unit_cost_aed=Decimal("12"),
            reference_type=GLRef.PURCHASE,
            reference_id=2,
        )
        db_session.flush()
        db_session.refresh(pwc)
        assert pwc.total_quantity == Decimal("20")

    def test_post_retrospective_skips_non_negative(self, mocker):
        mocker.patch("services.gl_posting.post_or_fail")
        result = StockService._post_retrospective_cost_adjustment(
            tenant_id=1,
            product_id=1,
            warehouse_id=1,
            old_qty=Decimal("5"),
            old_avg=Decimal("10"),
            unit_cost_aed=Decimal("12"),
            received_qty=Decimal("5"),
            reference_type=GLRef.PURCHASE,
            reference_id=1,
        )
        assert result == Decimal("0")

    def test_post_retrospective_variance_loss(
        self, db_session, sample_tenant, sample_product, sample_warehouse, mocker
    ):
        mocker.patch(
            "services.stock_service._resolve_gl_concept_account", return_value="1140"
        )
        mocker.patch("services.gl_service.GLService.ensure_core_accounts")
        mocker.patch("services.gl_posting.post_or_fail")
        result = StockService._post_retrospective_cost_adjustment(
            tenant_id=sample_tenant.id,
            product_id=sample_product.id,
            warehouse_id=sample_warehouse.id,
            old_qty=Decimal("-5"),
            old_avg=Decimal("10"),
            unit_cost_aed=Decimal("15"),
            received_qty=Decimal("10"),
            reference_type=GLRef.PURCHASE,
            reference_id=3,
        )
        assert result > Decimal("0")

    def test_post_retrospective_variance_gain(
        self, db_session, sample_tenant, sample_product, sample_warehouse, mocker
    ):
        mocker.patch(
            "services.stock_service._resolve_gl_concept_account", return_value="1140"
        )
        mocker.patch("services.gl_service.GLService.ensure_core_accounts")
        mocker.patch("services.gl_posting.post_or_fail")
        result = StockService._post_retrospective_cost_adjustment(
            tenant_id=sample_tenant.id,
            product_id=sample_product.id,
            warehouse_id=sample_warehouse.id,
            old_qty=Decimal("-5"),
            old_avg=Decimal("20"),
            unit_cost_aed=Decimal("10"),
            received_qty=Decimal("10"),
            reference_type=GLRef.PURCHASE,
            reference_id=4,
        )
        assert result < Decimal("0")

    def test_post_retrospective_post_failure_logged(
        self, db_session, sample_tenant, sample_product, sample_warehouse, mocker, app
    ):
        mocker.patch(
            "services.stock_service._resolve_gl_concept_account", return_value="1140"
        )
        mocker.patch("services.gl_service.GLService.ensure_core_accounts")
        mocker.patch(
            "services.gl_posting.post_or_fail", side_effect=RuntimeError("gl fail")
        )
        with app.app_context():
            result = StockService._post_retrospective_cost_adjustment(
                tenant_id=sample_tenant.id,
                product_id=sample_product.id,
                warehouse_id=sample_warehouse.id,
                old_qty=Decimal("-2"),
                old_avg=Decimal("10"),
                unit_cost_aed=Decimal("15"),
                received_qty=Decimal("5"),
                reference_type=GLRef.PURCHASE,
                reference_id=5,
            )
        assert result > Decimal("0")


class TestReverseOperations:
    def test_reverse_sale(
        self, db_session, sample_tenant, sample_product, sample_warehouse, app, mocker
    ):
        mocker.patch.object(StockService, "add_stock")
        line = MagicMock(product_id=sample_product.id, quantity=Decimal("2"))
        sale = MagicMock(
            tenant_id=sample_tenant.id,
            warehouse_id=sample_warehouse.id,
            sale_number="S-REV",
            lines=[line],
        )
        with app.app_context():
            app.config["ENABLE_MWAC"] = False
            StockService.reverse_sale(sale)

    def test_reverse_sale_mwac_with_history(
        self,
        db_session,
        sample_tenant,
        sample_product,
        sample_warehouse,
        enable_mwac,
        mocker,
    ):
        mocker.patch.object(StockService, "add_stock")
        pwc = ProductWarehouseCost(
            tenant_id=sample_tenant.id,
            product_id=sample_product.id,
            warehouse_id=sample_warehouse.id,
            total_quantity=Decimal("8"),
            total_value=Decimal("400"),
            average_cost=Decimal("50"),
        )
        db_session.add(pwc)
        db_session.flush()
        history = MagicMock(movement_unit_cost=Decimal("50"))
        mocker.patch.object(
            ProductCostHistory.query,
            "filter_by",
            return_value=MagicMock(
                order_by=MagicMock(
                    return_value=MagicMock(first=MagicMock(return_value=history))
                )
            ),
        )
        line = MagicMock(product_id=sample_product.id, quantity=Decimal("2"))
        sale = MagicMock(
            tenant_id=sample_tenant.id,
            warehouse_id=sample_warehouse.id,
            sale_number="S-REV2",
            id=99,
            lines=[line],
        )
        with enable_mwac.app_context():
            StockService.reverse_sale(sale)

    def test_reverse_purchase(
        self, db_session, sample_tenant, sample_product, sample_warehouse, app, mocker
    ):
        mocker.patch.object(StockService, "remove_stock")
        line = MagicMock(product_id=sample_product.id, quantity=Decimal("3"))
        purchase = MagicMock(
            tenant_id=sample_tenant.id,
            warehouse_id=sample_warehouse.id,
            purchase_number="P-REV",
            id=50,
            lines=[line],
        )
        with app.app_context():
            app.config["ENABLE_MWAC"] = False
            StockService.reverse_purchase(purchase)

    def test_reverse_purchase_mwac(
        self,
        db_session,
        sample_tenant,
        sample_product,
        sample_warehouse,
        enable_mwac,
        mocker,
    ):
        mocker.patch.object(StockService, "remove_stock")
        pwc = ProductWarehouseCost(
            tenant_id=sample_tenant.id,
            product_id=sample_product.id,
            warehouse_id=sample_warehouse.id,
            total_quantity=Decimal("10"),
            total_value=Decimal("100"),
            average_cost=Decimal("10"),
        )
        db_session.add(pwc)
        db_session.flush()
        history = MagicMock(movement_unit_cost=Decimal("10"))
        mocker.patch.object(
            ProductCostHistory.query,
            "filter_by",
            return_value=MagicMock(
                order_by=MagicMock(
                    return_value=MagicMock(first=MagicMock(return_value=history))
                )
            ),
        )
        line = MagicMock(product_id=sample_product.id, quantity=Decimal("3"))
        purchase = MagicMock(
            tenant_id=sample_tenant.id,
            warehouse_id=sample_warehouse.id,
            purchase_number="P-REV2",
            id=50,
            lines=[line],
        )
        with enable_mwac.app_context():
            StockService.reverse_purchase(purchase)


class TestInventoryQueries:
    def test_get_low_stock_products(self, mocker):
        product = MagicMock(id=1, min_stock_alert=Decimal("5"))
        query = MagicMock()
        query.order_by.return_value.all.return_value = [product]
        mocker.patch.object(
            StockService, "get_visible_products_query", return_value=query
        )
        mocker.patch(
            "services.stock_service.get_accessible_warehouse_ids", return_value=[1]
        )
        mocker.patch(
            "services.stock_service.get_branch_stock_map",
            return_value={1: Decimal("2")},
        )
        low = StockService.get_low_stock_products()
        assert low == [product]

    def test_get_low_stock_no_access(self, mocker):
        query = MagicMock()
        mocker.patch.object(
            StockService, "get_visible_products_query", return_value=query
        )
        mocker.patch(
            "services.stock_service.get_accessible_warehouse_ids", return_value=[]
        )
        user = MagicMock()
        assert StockService.get_low_stock_products(user=user) == []

    def test_get_out_of_stock_products(self, mocker):
        product = MagicMock(id=1, current_stock=Decimal("0"))
        query = MagicMock()
        query.order_by.return_value.all.return_value = [product]
        mocker.patch.object(
            StockService, "get_visible_products_query", return_value=query
        )
        mocker.patch(
            "services.stock_service.get_accessible_warehouse_ids", return_value=None
        )
        out = StockService.get_out_of_stock_products()
        assert product in out

    def test_get_visible_products_query_delegates(self, mocker):
        mocker.patch("utils.branching.get_visible_products_query", return_value="query")
        assert StockService.get_visible_products_query() == "query"


class TestReconcileStock:
    def test_reconcile_updates_mismatch(
        self, db_session, sample_tenant, sample_product, sample_warehouse
    ):
        pws = ProductWarehouseStock(
            tenant_id=sample_tenant.id,
            product_id=sample_product.id,
            warehouse_id=sample_warehouse.id,
            quantity=Decimal("5"),
        )
        db_session.add(pws)
        movement = StockMovement(
            tenant_id=sample_tenant.id,
            product_id=sample_product.id,
            warehouse_id=sample_warehouse.id,
            movement_type="purchase",
            quantity=Decimal("10"),
        )
        db_session.add(movement)
        db_session.flush()
        result = StockService.reconcile_stock(tenant_id=sample_tenant.id, commit=False)
        assert result["updated"] >= 1

    def test_reconcile_commit_error(self, db_session, sample_tenant, mocker):
        mocker.patch.object(
            db.session, "flush", side_effect=RuntimeError("commit fail")
        )
        result = StockService.reconcile_stock(tenant_id=sample_tenant.id, commit=True)
        assert result["errors"] == 1

    def test_negative_inventory_sale_with_allow(
        self,
        db_session,
        sample_tenant,
        sample_product,
        sample_warehouse,
        enable_mwac,
        mocker,
    ):
        sample_warehouse.allow_negative_inventory = True
        db_session.flush()
        real_get = db.session.get
        mocker.patch.object(
            db.session,
            "get",
            side_effect=lambda model, pk, _get=real_get: (
                sample_warehouse if model is Warehouse else _get(model, pk)
            ),
        )
        line = SimpleNamespace(
            product_id=sample_product.id,
            quantity=Decimal("2"),
            cost_price=Decimal("30"),
        )
        sale = SimpleNamespace(
            tenant_id=sample_tenant.id,
            warehouse_id=sample_warehouse.id,
            sale_number="S-NEG",
            id=1,
            lines=[line],
        )
        with enable_mwac.app_context():
            total = StockService.calculate_sale_cogs_and_deduct(sale)
        assert total == Decimal("60.000")


class TestAdditionalStockCoverage:
    def test_post_adjustment_gl_loss_lines(
        self, db_session, sample_product, sample_warehouse, mocker
    ):
        mocker.patch(
            "services.stock_service._resolve_gl_concept_account", return_value="1140"
        )
        mocker.patch("services.gl_service.GLService.ensure_core_accounts")
        mocker.patch("services.gl_posting.post_or_fail")
        movement = MagicMock(
            product_id=sample_product.id,
            quantity=Decimal("-2"),
            warehouse_id=sample_warehouse.id,
            reference_type=GLRef.STOCK_ADJUSTMENT,
            id=1,
            tenant_id=sample_product.tenant_id,
        )
        StockService._post_adjustment_gl(movement)

    def test_post_adjustment_gl_zero_cost_value(
        self, db_session, sample_tenant, sample_warehouse
    ):
        product = Product(
            tenant_id=sample_tenant.id,
            name="Zero Cost",
            sku=f"SKU-{uuid.uuid4().hex[:6]}",
            cost_price=Decimal("0"),
            regular_price=Decimal("10"),
            current_stock=Decimal("0"),
        )
        db_session.add(product)
        db_session.flush()
        movement = MagicMock(
            product_id=product.id,
            quantity=Decimal("1"),
            warehouse_id=sample_warehouse.id,
        )
        StockService._post_adjustment_gl(movement)

    def test_calculate_sale_cogs_mwac_positive_stock(
        self, db_session, sample_tenant, sample_product, sample_warehouse, enable_mwac
    ):
        pwc = ProductWarehouseCost(
            tenant_id=sample_tenant.id,
            product_id=sample_product.id,
            warehouse_id=sample_warehouse.id,
            total_quantity=Decimal("50"),
            total_value=Decimal("2500"),
            average_cost=Decimal("50"),
        )
        db_session.add(pwc)
        db_session.flush()
        line = SimpleNamespace(
            product_id=sample_product.id,
            quantity=Decimal("3"),
            cost_price=Decimal("50"),
        )
        sale = SimpleNamespace(
            tenant_id=sample_tenant.id,
            warehouse_id=sample_warehouse.id,
            sale_number="S-MWAC",
            id=1,
            lines=[line],
        )
        with enable_mwac.app_context():
            total = StockService.calculate_sale_cogs_and_deduct(sale)
        assert total == Decimal("150.000")

    def test_calculate_sale_cogs_mwac_fallback_warning(
        self, db_session, sample_tenant, sample_product, sample_warehouse, app
    ):
        line = MagicMock(
            product_id=sample_product.id,
            quantity=Decimal("1"),
            cost_price=Decimal("40"),
        )
        sale = MagicMock(
            tenant_id=sample_tenant.id,
            warehouse_id=sample_warehouse.id,
            sale_number="S-FB",
            lines=[line],
        )
        with app.app_context():
            app.config["ENABLE_MWAC"] = True
            total = StockService.calculate_sale_cogs_and_deduct(sale)
        assert total == Decimal("40.000")

    def test_process_purchase_lines_mwac(
        self, db_session, sample_tenant, sample_product, sample_warehouse, app, mocker
    ):
        mocker.patch.object(StockService, "add_stock")
        mocker.patch.object(StockService, "_update_wac_on_receipt")
        line = MagicMock(
            product_id=sample_product.id,
            quantity=Decimal("5"),
            landed_inventory_unit_cost=Decimal("10"),
            inventory_unit_cost=Decimal("8"),
        )
        purchase = MagicMock(
            tenant_id=sample_tenant.id,
            warehouse_id=sample_warehouse.id,
            purchase_number="P-MWAC",
            exchange_rate=Decimal("1"),
            lines=[line],
        )
        pwc = ProductWarehouseCost(
            tenant_id=sample_tenant.id,
            product_id=sample_product.id,
            warehouse_id=sample_warehouse.id,
            total_quantity=Decimal("10"),
            total_value=Decimal("100"),
            average_cost=Decimal("10"),
        )
        db_session.add(pwc)
        db_session.flush()
        with app.app_context():
            old_mwac = app.config.get("ENABLE_MWAC")
            old_landed = app.config.get("ENABLE_LANDED_COST_CAPITALIZATION")
            app.config["ENABLE_MWAC"] = True
            app.config["ENABLE_LANDED_COST_CAPITALIZATION"] = False
            try:
                StockService.process_purchase_lines(purchase)
            finally:
                app.config["ENABLE_MWAC"] = old_mwac
                app.config["ENABLE_LANDED_COST_CAPITALIZATION"] = old_landed

    def test_resolve_cogs_last_purchase(
        self, db_session, sample_tenant, sample_product, sample_warehouse
    ):
        pch = ProductCostHistory(
            tenant_id=sample_tenant.id,
            product_id=sample_product.id,
            warehouse_id=sample_warehouse.id,
            movement_type="purchase",
            reference_type=GLRef.PURCHASE,
            reference_id=1,
            movement_unit_cost=Decimal("33"),
            new_average_cost=Decimal("33"),
            quantity_change=Decimal("5"),
            old_total_quantity=Decimal("0"),
            new_total_quantity=Decimal("5"),
            old_total_value=Decimal("0"),
            new_total_value=Decimal("165"),
            old_average_cost=None,
        )
        db_session.add(pch)
        db_session.flush()
        cost, source = StockService._resolve_cogs_unit_cost(
            sample_product.id,
            sample_warehouse.id,
            sample_tenant.id,
        )
        assert cost == Decimal("33")
        assert source == "last_purchase"

    def test_check_availability_in_warehouse_missing_wh(self, sample_product):
        ok, msg = StockService.check_availability_in_warehouse(
            sample_product.id, Decimal("1"), 999999
        )
        assert ok is False

    def test_get_product_stock_with_warehouse_ids(self, mocker):
        mocker.patch(
            "services.stock_service.get_branch_stock_map",
            return_value={1: Decimal("9")},
        )
        qty = StockService.get_product_stock(1, warehouse_ids=[1, 2])
        assert qty == Decimal("9")

    def test_get_low_stock_global_fallback(self, mocker):
        product = MagicMock(
            id=1, min_stock_alert=Decimal("5"), current_stock=Decimal("1")
        )
        query = MagicMock()
        query.order_by.return_value.all.return_value = [product]
        mocker.patch.object(
            StockService, "get_visible_products_query", return_value=query
        )
        mocker.patch(
            "services.stock_service.get_accessible_warehouse_ids", return_value=None
        )
        low = StockService.get_low_stock_products()
        assert low == [product]

    def test_get_out_of_stock_with_warehouses(self, mocker):
        product = MagicMock(id=1)
        query = MagicMock()
        query.order_by.return_value.all.return_value = [product]
        mocker.patch.object(
            StockService, "get_visible_products_query", return_value=query
        )
        mocker.patch(
            "services.stock_service.get_accessible_warehouse_ids", return_value=[1]
        )
        mocker.patch(
            "services.stock_service.get_branch_stock_map",
            return_value={1: Decimal("0")},
        )
        out = StockService.get_out_of_stock_products()
        assert product in out

    def test_reconcile_creates_missing_pws(
        self, db_session, sample_tenant, sample_product, sample_warehouse
    ):
        movement = StockMovement(
            tenant_id=sample_tenant.id,
            product_id=sample_product.id,
            warehouse_id=sample_warehouse.id,
            movement_type="purchase",
            quantity=Decimal("3"),
        )
        db_session.add(movement)
        db_session.flush()
        ProductWarehouseStock.query.filter_by(
            product_id=sample_product.id,
            warehouse_id=sample_warehouse.id,
        ).delete()
        db_session.flush()
        result = StockService.reconcile_stock(tenant_id=sample_tenant.id, commit=False)
        assert result["created"] >= 1

    def test_update_wac_negative_stock_retrospective(
        self, db_session, sample_tenant, sample_product, sample_warehouse, mocker
    ):
        mocker.patch.object(
            StockService,
            "_post_retrospective_cost_adjustment",
            return_value=Decimal("1"),
        )
        pwc = ProductWarehouseCost(
            tenant_id=sample_tenant.id,
            product_id=sample_product.id,
            warehouse_id=sample_warehouse.id,
            total_quantity=Decimal("-2"),
            total_value=Decimal("-20"),
            average_cost=Decimal("10"),
        )
        db_session.add(pwc)
        db_session.flush()
        StockService._update_wac_on_receipt(
            tenant_id=sample_tenant.id,
            product_id=sample_product.id,
            warehouse_id=sample_warehouse.id,
            received_qty=Decimal("5"),
            unit_cost_aed=Decimal("12"),
            reference_type=GLRef.PURCHASE,
            reference_id=7,
        )

    def test_transfer_missing_warehouse(self, db_session, sample_product):
        with pytest.raises(ValueError, match="غير موجود"):
            StockService.transfer_stock(sample_product.id, 999999, 999998, Decimal("1"))

    def test_create_movement_without_authenticated_user(
        self, db_session, sample_product, sample_warehouse, mocker, app
    ):
        mocker.patch(
            "services.stock_service.current_user",
            create=True,
            new=MagicMock(is_authenticated=False),
        )
        with app.app_context():
            movement = StockService.add_stock(
                sample_product.id, Decimal("1"), warehouse_id=sample_warehouse.id
            )
        assert movement.user_id is None

    def test_calculate_sale_cogs_mwac_with_lock_fallback(
        self,
        db_session,
        sample_tenant,
        sample_product,
        sample_warehouse,
        enable_mwac,
        mocker,
    ):
        pwc = ProductWarehouseCost(
            tenant_id=sample_tenant.id,
            product_id=sample_product.id,
            warehouse_id=sample_warehouse.id,
            total_quantity=Decimal("50"),
            total_value=Decimal("2500"),
            average_cost=Decimal("50"),
        )
        db_session.add(pwc)
        db_session.flush()
        mocker.patch("services.stock_service._safe_for_update", return_value=pwc)
        line = SimpleNamespace(
            product_id=sample_product.id,
            quantity=Decimal("1"),
            cost_price=Decimal("50"),
        )
        sale = SimpleNamespace(
            tenant_id=sample_tenant.id,
            warehouse_id=sample_warehouse.id,
            sale_number="S-LOCK",
            id=999,
            lines=[line],
        )
        with enable_mwac.app_context():
            total = StockService.calculate_sale_cogs_and_deduct(sale)
        assert total == Decimal("50.000")

    def test_calculate_sale_cogs_negative_inventory_new_pwc(
        self,
        db_session,
        sample_tenant,
        sample_product,
        sample_warehouse,
        enable_mwac,
        mocker,
    ):
        sample_warehouse.allow_negative_inventory = True
        db_session.flush()
        mocker.patch(
            "services.stock_service.db.session.get",
            side_effect=lambda model, pk: (
                sample_warehouse if model is Warehouse else None
            ),
        )
        line = SimpleNamespace(
            product_id=sample_product.id,
            quantity=Decimal("2"),
            cost_price=Decimal("30"),
        )
        sale = SimpleNamespace(
            tenant_id=sample_tenant.id,
            warehouse_id=sample_warehouse.id,
            sale_number="S-NEW-PWC",
            id=2,
            lines=[line],
        )
        total = StockService.calculate_sale_cogs_and_deduct(sale)
        assert total == Decimal("60.000")

    def test_reverse_sale_without_cost_history(
        self, db_session, sample_tenant, sample_product, sample_warehouse, app, mocker
    ):
        mocker.patch.object(StockService, "add_stock")
        pwc = ProductWarehouseCost(
            tenant_id=sample_tenant.id,
            product_id=sample_product.id,
            warehouse_id=sample_warehouse.id,
            total_quantity=Decimal("5"),
            total_value=Decimal("250"),
            average_cost=Decimal("50"),
        )
        db_session.add(pwc)
        db_session.flush()
        mocker.patch.object(
            ProductCostHistory.query,
            "filter_by",
            return_value=MagicMock(
                order_by=MagicMock(
                    return_value=MagicMock(first=MagicMock(return_value=None))
                )
            ),
        )
        line = MagicMock(product_id=sample_product.id, quantity=Decimal("1"))
        sale = MagicMock(
            tenant_id=sample_tenant.id,
            warehouse_id=sample_warehouse.id,
            sale_number="S-NOHIST",
            id=77,
            lines=[line],
        )
        with app.app_context():
            app.config["ENABLE_MWAC"] = True
            StockService.reverse_sale(sale)

    def test_process_purchase_missing_product_skipped(
        self, db_session, sample_tenant, sample_warehouse, app, mocker
    ):
        mocker.patch.object(StockService, "add_stock")
        line = MagicMock(
            product_id=999999,
            quantity=Decimal("1"),
            landed_inventory_unit_cost=Decimal("10"),
            inventory_unit_cost=Decimal("8"),
        )
        purchase = MagicMock(
            tenant_id=sample_tenant.id,
            warehouse_id=sample_warehouse.id,
            purchase_number="P-MISS",
            exchange_rate=Decimal("1"),
            lines=[line],
        )
        mocker.patch.object(db.session, "get", return_value=None)
        with app.app_context():
            app.config["ENABLE_MWAC"] = False
            StockService.process_purchase_lines(purchase)

    def test_transfer_insufficient_stock(
        self, db_session, sample_product, sample_warehouse, mocker
    ):
        mocker.patch.object(
            StockService, "get_product_stock", return_value=Decimal("0")
        )
        wh2 = Warehouse(
            tenant_id=sample_warehouse.tenant_id,
            branch_id=sample_warehouse.branch_id,
            name="WH2",
            name_ar="مستودع 2",
            is_active=True,
        )
        db_session.add(wh2)
        db_session.flush()
        with pytest.raises(ValueError, match="غير متوفرة"):
            StockService.transfer_stock(
                sample_product.id,
                sample_warehouse.id,
                wh2.id,
                Decimal("5"),
            )

    def test_create_movement_user_resolution_failure(
        self, db_session, sample_product, sample_warehouse, mocker, app
    ):
        broken_user = MagicMock()
        broken_user.is_authenticated = True
        type(broken_user).id = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("no user"))
        )
        mocker.patch("services.stock_service.current_user", broken_user)
        with app.app_context():
            movement = StockService.add_stock(
                sample_product.id, Decimal("2"), warehouse_id=sample_warehouse.id
            )
        assert movement.user_id is None

    def test_check_availability_missing_product(self):
        ok, msg = StockService.check_availability(999999, 1)
        assert ok is False
        assert "غير موجود" in msg

    def test_check_availability_inactive_product(self, db_session, sample_product):
        sample_product.is_active = False
        db_session.flush()
        ok, msg = StockService.check_availability(sample_product.id, 1)
        assert ok is False
        assert "غير نشط" in msg

    def test_check_availability_insufficient(self, db_session, sample_product):
        sample_product.current_stock = Decimal("1")
        db_session.flush()
        ok, msg = StockService.check_availability(sample_product.id, 5)
        assert ok is False
        assert "غير كاف" in msg

    def test_check_availability_success(self, db_session, sample_product):
        sample_product.current_stock = Decimal("10")
        db_session.flush()
        ok, msg = StockService.check_availability(sample_product.id, 3)
        assert ok is True
        assert msg == "متوفر"

    def test_calculate_sale_cogs_negative_with_existing_pwc(
        self, db_session, sample_tenant, sample_product, sample_warehouse, enable_mwac
    ):
        sample_warehouse.allow_negative_inventory = True
        pwc = ProductWarehouseCost(
            tenant_id=sample_tenant.id,
            product_id=sample_product.id,
            warehouse_id=sample_warehouse.id,
            total_quantity=Decimal("-1"),
            total_value=Decimal("-50"),
            average_cost=Decimal("50"),
        )
        db_session.add(pwc)
        db_session.flush()
        line = SimpleNamespace(
            product_id=sample_product.id,
            quantity=Decimal("2"),
            cost_price=Decimal("50"),
        )
        sale = SimpleNamespace(
            tenant_id=sample_tenant.id,
            warehouse_id=sample_warehouse.id,
            sale_number="S-NEG-PWC",
            id=3,
            lines=[line],
        )
        with enable_mwac.app_context():
            total = StockService.calculate_sale_cogs_and_deduct(sale)
        assert total == Decimal("100.000")
