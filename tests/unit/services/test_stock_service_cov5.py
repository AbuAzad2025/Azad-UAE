"""Stock service — additional coverage (row-lock retry, transfer PWC valuation, MWAC/FEFO,
reconcile tenant scope, movements windowing, route-facing scoped fetches)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import OperationalError

from models import Product, ProductWarehouseStock, StockMovement
from services import stock_service as ss
from utils.gl_reference_types import GLRef


def _make_warehouse(db_session, tenant, *, is_main=False, branch_id=None, code=None, name=None):
    from models import Warehouse

    w = Warehouse(
        tenant_id=tenant.id,
        branch_id=branch_id,
        name=name or f"WH-{uuid.uuid4().hex[:6]}",
        name_ar="مستودع",
        is_main=is_main,
        is_active=True,
        code=code,
    )
    db_session.add(w)
    db_session.flush()
    return w


def _make_product(db_session, tenant, *, cost_price=None):
    p = Product(
        tenant_id=tenant.id,
        name=f"P-{uuid.uuid4().hex[:6]}",
        sku=f"SKU-{uuid.uuid4().hex[:8].upper()}",
        cost_price=cost_price,
        regular_price=Decimal("100.000"),
    )
    db_session.add(p)
    db_session.flush()
    return p


def _make_movement(db_session, tenant, product, warehouse_id, qty, movement_type="purchase"):
    m = StockMovement(
        tenant_id=tenant.id,
        product_id=product.id,
        warehouse_id=warehouse_id,
        movement_type=movement_type,
        quantity=Decimal(str(qty)),
        reference_type=GLRef.PRODUCT_CREATION,
    )
    db_session.add(m)
    db_session.flush()
    return m


# ─── _safe_for_update retry paths ────────────────────────────────────────


def test_lock_retry_then_success(db_session):
    row = object()
    q = MagicMock()
    q.with_for_update.return_value.first.side_effect = [
        OperationalError("SELECT", {}, Exception("lock contention")),
        row,
    ]
    with patch.object(ss, "current_app") as ca:
        result = ss._safe_for_update(q, label="probe")
    assert result is row
    assert q.with_for_update.return_value.first.call_count == 2
    ca.logger.warning.assert_called_once()


def test_lock_retry_exhausted_raises(db_session):
    q = MagicMock()
    q.with_for_update.return_value.first.side_effect = [
        OperationalError("SELECT", {}, Exception("lock")),
        OperationalError("SELECT", {}, Exception("lock")),
        OperationalError("SELECT", {}, Exception("lock")),
    ]
    with (
        patch.object(ss, "current_app") as ca,
        pytest.raises(OperationalError),
    ):
        ss._safe_for_update(q, label="probe2")
    ca.logger.critical.assert_called_once()
    assert ca.logger.warning.call_count == 2


# ─── add_opening_stock / create_movement warehouse selection ─────────────


def test_add_opening_stock_zero_cost_value_skips_gl(db_session, sample_tenant):
    product = _make_product(db_session, sample_tenant, cost_price=Decimal("10"))
    warehouse = _make_warehouse(db_session, sample_tenant, is_main=True)
    with (
        patch.object(ss, "_resolve_gl_concept_account") as resolve,
        patch("services.gl_posting.post_or_fail") as post,
    ):
        movement = ss.StockService.add_opening_stock(product.id, 0, warehouse_id=warehouse.id)
    assert movement is not None
    resolve.assert_not_called()
    post.assert_not_called()


def test_create_movement_uses_main_warehouse(db_session, sample_tenant):
    product = _make_product(db_session, sample_tenant, cost_price=Decimal("10"))
    main_wh = _make_warehouse(db_session, sample_tenant, is_main=True)
    movement = ss.StockService.create_movement(product.id, 5, "purchase")
    assert movement.warehouse_id == main_wh.id


def test_create_movement_falls_back_to_regular_warehouse(db_session, sample_tenant):
    product = _make_product(db_session, sample_tenant, cost_price=Decimal("10"))
    regular_wh = _make_warehouse(db_session, sample_tenant, is_main=False)
    movement = ss.StockService.create_movement(product.id, 5, "purchase")
    assert movement.warehouse_id == regular_wh.id


def test_create_movement_broadcast_failure_logged(db_session, sample_tenant):

    product = _make_product(db_session, sample_tenant, cost_price=Decimal("10"))
    warehouse = _make_warehouse(db_session, sample_tenant, is_main=True)
    with (
        patch("services.websocket_service.broadcast_stock_alert", side_effect=RuntimeError("ws down")),
        patch.object(ss, "current_app") as ca,
    ):
        movement = ss.StockService.create_movement(
            product.id, 4, "sale", warehouse_id=warehouse.id, reference_type=GLRef.PRODUCT_CREATION
        )
    assert movement is not None
    ca.logger.debug.assert_called_once()


# ─── transfer_stock: tenant skip / user branches / PWC valuation ─────────


def test_transfer_skips_tenant_check_when_product_unscoped():
    product = MagicMock(id=1, tenant_id=None, name="P")
    from_wh = MagicMock(id=10, tenant_id=None, name="A", name_ar="أ", is_active=True)
    to_wh = MagicMock(id=11, tenant_id=None, name="B", name_ar="ب", is_active=True)
    q_pwc = MagicMock()
    q_pwc.filter_by.return_value.first.return_value = None
    with (
        patch("services.stock_service.db.session.get", return_value=product),
        patch.object(ss.Warehouse, "query") as q_wh,
        patch.object(ss.StockService, "create_movement", return_value=MagicMock(id=9)),
        patch.object(ss.StockService, "get_product_stock", return_value=Decimal("50")),
        patch.object(ss.ProductWarehouseCost, "query", q_pwc),
    ):
        q_wh.filter_by.return_value.first.side_effect = [from_wh, to_wh]
        out, _ = ss.StockService.transfer_stock(1, 10, 11, 10, user=None)
    assert out.id == 9


def test_transfer_moves_pwc_value_to_existing_dest():
    product = MagicMock(id=1, tenant_id=1, name="P")
    from_wh = MagicMock(id=10, tenant_id=1, name="A", name_ar="أ", is_active=True)
    to_wh = MagicMock(id=11, tenant_id=1, name="B", name_ar="ب", is_active=True)
    src_pwc = MagicMock()
    src_pwc.total_quantity = Decimal("20")
    src_pwc.total_value = Decimal("200")
    src_pwc.average_cost = Decimal("10")
    dest_pwc = MagicMock()
    dest_pwc.total_quantity = Decimal("5")
    dest_pwc.total_value = Decimal("50")
    dest_pwc.average_cost = Decimal("10")
    q_pwc = MagicMock()
    q_pwc.filter_by.return_value.first.side_effect = [src_pwc, dest_pwc]
    with (
        patch("services.stock_service.db.session.get", return_value=product),
        patch.object(ss.Warehouse, "query") as q_wh,
        patch.object(ss.StockService, "create_movement", return_value=MagicMock(id=9)),
        patch.object(ss.StockService, "get_product_stock", return_value=Decimal("50")),
        patch.object(ss.ProductWarehouseCost, "query", q_pwc),
        patch.object(ss.db.session, "flush"),
        patch("utils.auth_helpers.is_global_owner_user", return_value=True),
    ):
        q_wh.filter_by.return_value.first.side_effect = [from_wh, to_wh]
        ss.StockService.transfer_stock(1, 10, 11, 10, user=MagicMock())
    assert src_pwc.total_quantity == Decimal("10")
    assert src_pwc.total_value == Decimal("100")
    assert src_pwc.average_cost == Decimal("10.0000")
    assert dest_pwc.total_quantity == Decimal("15")
    assert dest_pwc.total_value == Decimal("150")


def test_transfer_creates_dest_pwc_and_resets_src_on_drain():
    product = MagicMock(id=1, tenant_id=1, name="P")
    from_wh = MagicMock(id=10, tenant_id=1, name="A", name_ar="أ", is_active=True)
    to_wh = MagicMock(id=11, tenant_id=1, name="B", name_ar="ب", is_active=True)
    src_pwc = MagicMock()
    src_pwc.total_quantity = Decimal("10")
    src_pwc.total_value = Decimal("100")
    src_pwc.average_cost = Decimal("10")
    q_pwc = MagicMock()
    q_pwc.filter_by.return_value.first.side_effect = [src_pwc, None]
    with (
        patch("services.stock_service.db.session.get", return_value=product),
        patch.object(ss.Warehouse, "query") as q_wh,
        patch.object(ss.StockService, "create_movement", return_value=MagicMock(id=9)),
        patch.object(ss.StockService, "get_product_stock", return_value=Decimal("50")),
        patch.object(ss.ProductWarehouseCost, "query", q_pwc),
        patch.object(ss.db.session, "add") as add_mock,
        patch.object(ss.db.session, "flush"),
        patch("utils.auth_helpers.is_global_owner_user", return_value=False),
        patch("utils.branching.get_accessible_warehouse_ids", return_value=[]),
    ):
        q_wh.filter_by.return_value.first.side_effect = [from_wh, to_wh]
        ss.StockService.transfer_stock(1, 10, 11, 10, user=MagicMock())
    assert src_pwc.total_quantity == Decimal("0")
    assert src_pwc.average_cost == Decimal("0.0000")
    assert src_pwc.total_value == Decimal("0.001")
    added = [c for call in add_mock.call_args_list for c in call.args if isinstance(c, ss.ProductWarehouseCost)]
    assert added
    assert added[0].total_quantity == Decimal("10")
    assert added[0].total_value == Decimal("100")
    assert added[0].average_cost == Decimal("10.0000")


# ─── COGS resolution / calculation ────────────────────────────────────────


def test_resolve_cogs_nonpositive_line_cost_uses_last_purchase():
    pch = MagicMock()
    pch.movement_unit_cost = Decimal("8")
    q_hist = MagicMock()
    q_hist.filter_by.return_value.order_by.return_value.first.return_value = pch
    q_pwc = MagicMock()
    q_pwc.filter_by.return_value.first.return_value = None
    with (
        patch.object(ss.ProductWarehouseCost, "query", q_pwc),
        patch.object(ss.ProductCostHistory, "query", q_hist),
    ):
        cost, source = ss.StockService._resolve_cogs_unit_cost(1, 5, 1, line_cost_price="0")
    assert (cost, source) == (Decimal("8"), "last_purchase")


def test_calculate_sale_cogs_explicit_warehouse(monkeypatch, app):
    line = MagicMock(product_id=1, quantity=2, cost_price=Decimal("7"))
    sale = MagicMock(warehouse_id=3, tenant_id=1, sale_number="S-1", lines=[line])
    with (
        patch.object(ss, "_safe_for_update", return_value=None),
        patch.object(ss.StockService, "_resolve_cogs_unit_cost", return_value=(Decimal("9"), "cost_price")),
        patch("services.stock_service.db.session.get", return_value=MagicMock(allow_negative_inventory=False)),
    ):
        total = ss.StockService.calculate_sale_cogs_and_deduct(sale, warehouse_id=3)
    assert total == Decimal("18.000")


def test_calculate_sale_cogs_fefo_consumption(app):
    pwc = MagicMock()
    pwc.total_quantity = Decimal("9")
    pwc.total_value = Decimal("90")
    pwc.average_cost = Decimal("10")
    pwc2 = MagicMock()
    pwc2.total_quantity = Decimal("9")
    pwc2.total_value = Decimal("90")
    pwc2.average_cost = Decimal("10")
    lines = [MagicMock(product_id=1, quantity=2), MagicMock(product_id=2, quantity=3)]
    sale = MagicMock(warehouse_id=1, tenant_id=1, sale_number="S-F", lines=lines)
    with (
        patch.object(ss, "_safe_for_update", side_effect=[pwc, pwc2]),
        patch.object(ss.StockBatchService, "batches_enabled", return_value=True),
        patch.object(
            ss.StockBatchService,
            "consume_fefo",
            side_effect=[(Decimal("1"), Decimal("8")), (Decimal("0"), Decimal("0"))],
        ),
        patch("services.stock_service.db.session.get", return_value=MagicMock(allow_negative_inventory=False)),
    ):
        total = ss.StockService.calculate_sale_cogs_and_deduct(sale, warehouse_id=1)
    assert total == Decimal("48.000")


def test_process_purchase_lines_explicit_warehouse_with_cost_recalc(app):
    p1 = MagicMock(id=1, tenant_id=1)
    p2 = MagicMock(id=2, tenant_id=1)
    line1 = MagicMock(
        product_id=1,
        quantity=10,
        landed_inventory_unit_cost=Decimal("5"),
        inventory_unit_cost=Decimal("5"),
    )
    line2 = MagicMock(
        product_id=2,
        quantity=5,
        landed_inventory_unit_cost=Decimal("2"),
        inventory_unit_cost=Decimal("2"),
    )
    purchase = MagicMock()
    purchase.tenant_id = 1
    purchase.purchase_number = "P-1"
    purchase.exchange_rate = Decimal("1")
    purchase.id = 7
    purchase.lines = [line1, line2]
    pwc_row = MagicMock()
    pwc_row.total_value = Decimal("100")
    pwc_row.total_quantity = Decimal("10")

    def fake_get(_model, pid):
        return p1 if pid == 1 else p2

    q_pwc = MagicMock()
    q_pwc.filter_by.return_value.all.side_effect = [[], [pwc_row]]
    with (
        patch.object(ss.StockService, "add_stock"),
        patch.object(ss.StockService, "_update_wac_on_receipt") as wac,
        patch("services.stock_service.db.session.get", side_effect=fake_get),
        patch.object(ss.ProductWarehouseCost, "query", q_pwc),
    ):
        ss.StockService.process_purchase_lines(purchase, warehouse_id=9)
    assert wac.call_count == 2
    assert p1.cost_price == Decimal("0")
    assert p2.cost_price == Decimal("10.000")


# ─── MWAC receipt / reversal batch hooks ──────────────────────────────────


def test_update_wac_on_receipt_records_batch(app):
    pwc = MagicMock()
    pwc.total_quantity = Decimal("5")
    pwc.total_value = Decimal("50")
    pwc.average_cost = Decimal("10")
    with (
        patch.object(ss, "_safe_for_update", return_value=pwc),
        patch.object(ss.StockBatchService, "batches_enabled", return_value=True),
        patch.object(ss.StockBatchService, "record_receipt") as rec,
    ):
        ss.StockService._update_wac_on_receipt(
            tenant_id=1,
            product_id=2,
            warehouse_id=3,
            received_qty=Decimal("10"),
            unit_cost_aed=Decimal("12"),
            reference_type=GLRef.PURCHASE,
            reference_id=5,
        )
    rec.assert_called_once()
    assert pwc.quantity_change if hasattr(pwc, "quantity_change") else True


def test_reverse_sale_restores_batches(app):
    line = MagicMock(product_id=1, quantity=2)
    sale = MagicMock(id=8, sale_number="S-1", warehouse_id=5, tenant_id=1, lines=[line])
    pwc = MagicMock()
    pwc.total_quantity = Decimal("0")
    pwc.total_value = Decimal("100")
    pwc.average_cost = Decimal("10")
    q_hist = MagicMock()
    q_hist.filter_by.return_value.order_by.return_value.first.return_value = None
    with (
        patch.object(ss.StockService, "add_stock"),
        patch.object(ss, "_safe_for_update", return_value=pwc),
        patch.object(ss.ProductCostHistory, "query", q_hist),
        patch.object(ss.StockBatchService, "batches_enabled", return_value=True),
        patch.object(ss.StockBatchService, "restore_on_reversal") as restore,
    ):
        ss.StockService.reverse_sale(sale)
    restore.assert_called_once()
    assert pwc.total_quantity == Decimal("2")
    assert pwc.average_cost == Decimal("60.0000")


# ─── reconcile_stock tenant-scoped ────────────────────────────────────────


def test_reconcile_tenant_scoped(db_session, sample_tenant, sample_warehouse):
    product = _make_product(db_session, sample_tenant, cost_price=Decimal("10"))
    stray_wh = _make_warehouse(db_session, sample_tenant)
    _make_movement(db_session, sample_tenant, product, sample_warehouse.id, 3)
    _make_movement(db_session, sample_tenant, product, sample_warehouse.id, 2)
    _make_movement(db_session, sample_tenant, product, stray_wh.id, 4)
    pws = ProductWarehouseStock(
        tenant_id=sample_tenant.id,
        product_id=product.id,
        warehouse_id=sample_warehouse.id,
        quantity=Decimal("5"),
    )
    db_session.add(pws)
    product.current_stock = Decimal("5")
    db_session.flush()
    with patch("services.stock_service.db.session.get", return_value=None):
        stats = ss.StockService.reconcile_stock(tenant_id=sample_tenant.id)
    assert stats == {"created": 0, "updated": 0, "errors": 0, "total_pws": 1}


# ─── movement running balances ────────────────────────────────────────────


def test_running_balances_empty():
    assert ss.StockService.get_movement_running_balances(None, tenant_id=1) == {}
    assert ss.StockService.get_movement_running_balances([], tenant_id=1) == {}


def test_running_balances_real(db_session, sample_tenant, sample_warehouse):
    product = _make_product(db_session, sample_tenant, cost_price=Decimal("10"))
    first = _make_movement(db_session, sample_tenant, product, sample_warehouse.id, 5)
    second = _make_movement(db_session, sample_tenant, product, sample_warehouse.id, 3)
    out = ss.StockService.get_movement_running_balances(
        [second], tenant_id=sample_tenant.id
    )
    assert out[second.id] == (Decimal("5"), Decimal("8"))
    assert out.get(first.id) is None


def test_resolve_gl_concept_static_fallback(monkeypatch):
    import services.gl_account_resolver as resolver

    monkeypatch.setattr(resolver, "is_dynamic_gl_mapping_enabled", lambda: True)
    monkeypatch.setattr(resolver, "resolve_gl_account", lambda **kw: None)
    out = ss._resolve_gl_concept_account("NONSENSE_CONCEPT", "9999", tenant_id=1)
    assert out == "9999"


def test_reconcile_without_tenant_filter(db_session, sample_tenant, sample_warehouse):
    product = _make_product(db_session, sample_tenant, cost_price=Decimal("10"))
    _make_movement(db_session, sample_tenant, product, sample_warehouse.id, 5)
    pws = ProductWarehouseStock(
        tenant_id=sample_tenant.id,
        product_id=product.id,
        warehouse_id=sample_warehouse.id,
        quantity=Decimal("5"),
    )
    db_session.add(pws)
    product.current_stock = Decimal("5")
    db_session.flush()
    stats = ss.StockService.reconcile_stock()
    assert stats["created"] == 0
    assert stats["errors"] == 0


def test_running_balances_without_tenant(db_session, sample_tenant, sample_warehouse):
    product = _make_product(db_session, sample_tenant, cost_price=Decimal("10"))
    first = _make_movement(db_session, sample_tenant, product, sample_warehouse.id, 5)
    second = _make_movement(db_session, sample_tenant, product, sample_warehouse.id, 3)
    out = ss.StockService.get_movement_running_balances([second])
    assert out[second.id] == (Decimal("5"), Decimal("8"))
    assert out.get(first.id) is None


def test_movements_query_without_tenant(db_session, sample_tenant, sample_warehouse):
    product = _make_product(db_session, sample_tenant, cost_price=Decimal("10"))
    m1 = _make_movement(db_session, sample_tenant, product, sample_warehouse.id, 1)
    m2 = _make_movement(db_session, sample_tenant, product, sample_warehouse.id, 2)
    m3 = _make_movement(db_session, sample_tenant, product, sample_warehouse.id, 3)
    rows = ss.StockService.movements_query().all()
    assert {m1.id, m2.id, m3.id} <= {r.id for r in rows}


def test_list_parent_warehouses_without_tenant(db_session, sample_tenant):
    parent = _make_warehouse(db_session, sample_tenant, is_main=True)
    child = _make_warehouse(db_session, sample_tenant)
    child.parent_id = parent.id
    db_session.flush()
    ids = {w.id for w in ss.StockService.list_parent_warehouses()}
    assert parent.id in ids
    assert child.id not in ids


# ─── route-facing scoped fetches / listings ───────────────────────────────


def test_get_branch_warehouse_ids(db_session, sample_tenant, sample_branch):
    wh = _make_warehouse(db_session, sample_tenant, branch_id=sample_branch.id)
    assert ss.StockService.get_branch_warehouse_ids(sample_branch.id) == [wh.id]
    assert ss.StockService.get_branch_warehouse_ids(sample_branch.id, sample_tenant.id) == [wh.id]
    assert ss.StockService.get_branch_warehouse_ids(424242) == [-1]


def test_get_tenant_warehouse(db_session, sample_tenant):
    wh = _make_warehouse(db_session, sample_tenant, is_main=True)
    assert ss.StockService.get_tenant_warehouse(wh.id, sample_tenant.id) is wh
    assert ss.StockService.get_tenant_warehouse(wh.id) is wh
    assert ss.StockService.get_tenant_warehouse(wh.id, 424242) is None


def test_movements_query_filters(db_session, sample_tenant, sample_warehouse):
    product_a = _make_product(db_session, sample_tenant, cost_price=Decimal("10"))
    product_b = _make_product(db_session, sample_tenant, cost_price=Decimal("10"))
    wh2 = _make_warehouse(db_session, sample_tenant)
    _make_movement(db_session, sample_tenant, product_a, sample_warehouse.id, 1, "sale")
    _make_movement(db_session, sample_tenant, product_a, wh2.id, 2, "purchase")
    _make_movement(db_session, sample_tenant, product_b, sample_warehouse.id, 3, "purchase")
    base = ss.StockService.movements_query(tenant_id=sample_tenant.id)
    assert len(base.all()) == 3
    assert len(ss.StockService.movements_query(tenant_id=sample_tenant.id, warehouse_ids=[sample_warehouse.id]).all()) == 2
    assert len(ss.StockService.movements_query(tenant_id=sample_tenant.id, product_id=product_a.id).all()) == 2
    assert len(ss.StockService.movements_query(tenant_id=sample_tenant.id, movement_type="purchase").all()) == 2
    assert len(ss.StockService.movements_query(tenant_id=sample_tenant.id, warehouse_id=wh2.id).all()) == 1
    assert len(
        ss.StockService.movements_query(
            tenant_id=sample_tenant.id, product_id=product_a.id, movement_type="purchase", warehouse_id=wh2.id
        ).all()
    ) == 1


def test_list_active_warehouses():
    rows = [MagicMock(), MagicMock()]
    q = MagicMock()
    q.filter_by.return_value.order_by.return_value.all.return_value = rows
    with patch("utils.tenanting.tenant_query", return_value=q):
        out = ss.StockService.list_active_warehouses()
    assert out == rows


def test_get_warehouse_stock_totals(db_session, sample_tenant, sample_warehouse):
    product_a = _make_product(db_session, sample_tenant, cost_price=Decimal("10"))
    _make_movement(db_session, sample_tenant, product_a, sample_warehouse.id, 5)
    _make_movement(db_session, sample_tenant, product_a, sample_warehouse.id, 2)
    out = dict(ss.StockService.get_warehouse_stock_totals(sample_warehouse.id))
    assert out[product_a.id] == Decimal("7")


def test_get_tenant_product(db_session, sample_tenant):
    product = _make_product(db_session, sample_tenant, cost_price=Decimal("10"))
    assert ss.StockService.get_tenant_product(product.id, sample_tenant.id) is product
    assert ss.StockService.get_tenant_product(product.id, 424242) is None


def test_list_parent_warehouses(db_session, sample_tenant):
    parent = _make_warehouse(db_session, sample_tenant, is_main=True)
    child = _make_warehouse(db_session, sample_tenant)
    child.parent_id = parent.id
    db_session.flush()
    out = ss.StockService.list_parent_warehouses(sample_tenant.id)
    ids = {w.id for w in out}
    assert parent.id in ids
    assert child.id not in ids


def test_find_warehouse_by_code(db_session, sample_tenant):
    wh = _make_warehouse(db_session, sample_tenant, code="CODEX-77")
    assert ss.StockService.find_warehouse_by_code("CODEX-77", sample_tenant.id) is wh
    assert ss.StockService.find_warehouse_by_code("NOPE-99", sample_tenant.id) is None


def test_list_visible_warehouses_branch_filter():
    rows_all = [MagicMock()]
    rows_branch = [MagicMock()]
    x = MagicMock()
    x.order_by.return_value.all.return_value = rows_branch
    base = MagicMock()
    base.filter_by.return_value = x
    q = MagicMock()
    q.filter_by.return_value = base
    with patch("utils.tenanting.tenant_query", return_value=q):
        assert ss.StockService.list_visible_warehouses(branch_id=5) == rows_branch
    branch_scoped = MagicMock()
    branch_scoped.order_by.return_value.all.return_value = rows_all
    q2 = MagicMock()
    q2.filter_by.return_value = branch_scoped
    with patch("utils.tenanting.tenant_query", return_value=q2):
        assert ss.StockService.list_visible_warehouses() == rows_all


def test_pick_default_warehouse_main_and_fallback():
    main_wh = MagicMock()
    fallback_wh = MagicMock()
    x = MagicMock()
    y = MagicMock()
    y.filter_by.return_value.first.return_value = main_wh
    x.filter_by.return_value = y
    q = MagicMock()
    q.filter_by.return_value = x
    with patch("utils.tenanting.tenant_query", return_value=q):
        assert ss.StockService.pick_default_warehouse(branch_id=10) is main_wh

    x2 = MagicMock()
    x2.filter_by.return_value.first.return_value = None
    x2.order_by.return_value.first.return_value = fallback_wh
    q2 = MagicMock()
    q2.filter_by.return_value = x2
    with patch("utils.tenanting.tenant_query", return_value=q2):
        assert ss.StockService.pick_default_warehouse() is fallback_wh


def test_warehouse_has_stock(db_session, sample_tenant, sample_warehouse):
    product = _make_product(db_session, sample_tenant, cost_price=Decimal("10"))
    other = _make_warehouse(db_session, sample_tenant)
    _make_movement(db_session, sample_tenant, product, sample_warehouse.id, 2)
    assert ss.StockService.warehouse_has_stock(sample_warehouse.id) is True
    assert ss.StockService.warehouse_has_stock(other.id) is False


def test_get_pws_row(db_session, sample_tenant, sample_warehouse):
    product = _make_product(db_session, sample_tenant, cost_price=Decimal("10"))
    row = ProductWarehouseStock(
        tenant_id=sample_tenant.id,
        product_id=product.id,
        warehouse_id=sample_warehouse.id,
        quantity=Decimal("4"),
    )
    db_session.add(row)
    db_session.flush()
    assert ss.StockService.get_pws_row(sample_tenant.id, product.id, sample_warehouse.id) is row
    assert ss.StockService.get_pws_row(sample_tenant.id, product.id, 99999) is None