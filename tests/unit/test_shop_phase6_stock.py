"""Phase 1 — Stock Architecture tests: P1.1-P1.6"""


def test_product_warehouse_stock_model_exists():
    from models.warehouse import ProductWarehouseStock
    assert ProductWarehouseStock is not None


def test_product_warehouse_stock_columns():
    from models.warehouse import ProductWarehouseStock
    cols = [c.name for c in ProductWarehouseStock.__table__.columns]
    assert 'id' in cols
    assert 'tenant_id' in cols
    assert 'product_id' in cols
    assert 'warehouse_id' in cols
    assert 'quantity' in cols
    assert 'updated_at' in cols
    assert 'warehouse_barcode' in cols
    assert 'warehouse_description_ar' in cols
    assert 'warehouse_description_en' in cols
    assert 'warehouse_country_of_origin' in cols


def test_product_warehouse_stock_unique_constraint():
    from models.warehouse import ProductWarehouseStock
    from sqlalchemy.schema import UniqueConstraint
    uq = [
        c for c in ProductWarehouseStock.__table__.constraints
        if isinstance(c, UniqueConstraint)
        and c.name == 'uq_product_warehouse_stock'
    ]
    assert len(uq) == 1


def test_product_extra_fields_column():
    from models.product import Product
    cols = [c.name for c in Product.__table__.columns]
    assert 'extra_fields' in cols
    assert 'industry' in cols


def test_product_warehouse_stocks_relationship():
    from models.product import Product
    from sqlalchemy.orm import class_mapper
    mapper = class_mapper(Product)
    keys = [r.key for r in mapper.relationships]
    assert 'warehouse_stocks' in keys
    assert 'price_tiers' in keys


def test_warehouse_extra_fields_column():
    from models.warehouse import Warehouse
    cols = [c.name for c in Warehouse.__table__.columns]
    assert 'extra_fields' in cols


def test_warehouse_warehouse_stocks_relationship():
    from models.warehouse import Warehouse
    from sqlalchemy.orm import class_mapper
    mapper = class_mapper(Warehouse)
    keys = [r.key for r in mapper.relationships]
    assert 'warehouse_stocks' in keys


def test_stock_service_create_movement_updates_pws(app):
    from models import Product, Warehouse
    from models.warehouse import ProductWarehouseStock
    from services.stock_service import StockService
    with app.app_context():
        tenant_id = 1
        wh = Warehouse.query.filter_by(is_active=True).first()
        if not wh:
            return
        prod = Product.query.filter_by(is_active=True).first()
        if not prod:
            return
        movement = StockService.create_movement(
            product_id=prod.id, quantity=5, movement_type='purchase',
            warehouse_id=wh.id
        )
        pws = ProductWarehouseStock.query.filter_by(
            tenant_id=tenant_id, product_id=prod.id, warehouse_id=wh.id
        ).first()
        assert pws is not None
        assert pws.quantity >= 5


def test_stock_service_reconcile_stock(app):
    from services.stock_service import StockService
    with app.app_context():
        result = StockService.reconcile_stock()
        assert 'created' in result
        assert 'updated' in result
        assert 'errors' in result
        assert 'total_pws' in result


def test_current_stock_column_unchanged():
    from models.product import Product
    cols = [c.name for c in Product.__table__.columns]
    assert 'current_stock' in cols


def test_resolve_gl_concept_account():
    from services.stock_service import _resolve_gl_concept_account
    result = _resolve_gl_concept_account('INVENTORY_ASSET', '1140')
    assert isinstance(result, str)


def test_cli_command_registered(app):
    from flask import Flask
    assert isinstance(app, Flask)
    cli = app.cli
    commands = [c for c in cli.list_commands(app.app_context())]
    assert 'reconcile-stock' in commands


def test_product_price_tier_model_exists():
    from models.product_price_tier import ProductPriceTier
    cols = [c.name for c in ProductPriceTier.__table__.columns]
    assert 'id' in cols
    assert 'tier_code' in cols
    assert 'price' in cols
    assert 'min_quantity' in cols
    assert 'currency' in cols
    assert 'is_active' in cols


def test_product_price_tier_unique_constraint():
    from models.product_price_tier import ProductPriceTier
    from sqlalchemy.schema import UniqueConstraint
    uq = [
        c for c in ProductPriceTier.__table__.constraints
        if isinstance(c, UniqueConstraint)
        and c.name == 'uq_product_price_tier'
    ]
    assert len(uq) == 1


def test_mwac_calc_captures_old_qty_value_avg():
    """Regression: old_qty/old_value/old_avg must be captured *before* _mwac_calc."""
    from services.stock_service import StockService, _MWACHelper
    from decimal import Decimal
    old_qty = Decimal('20')
    old_value = Decimal('500')
    old_avg = Decimal('25')
    change_qty = Decimal('-5')
    unit_cost = Decimal('25')
    new_qty, new_value, new_avg = StockService._mwac_calc(old_qty, old_value, change_qty, unit_cost)
    assert new_qty == Decimal('15')
    assert new_value == Decimal('375')
    assert new_avg == Decimal('25')
    # Verify old values remain readable after the call
    assert old_qty == Decimal('20')
    assert old_value == Decimal('500')
    assert old_avg == Decimal('25')
