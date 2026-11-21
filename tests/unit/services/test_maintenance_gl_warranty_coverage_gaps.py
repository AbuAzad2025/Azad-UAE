"""Coverage gaps for the maintenance GL, warranty and stock posting paths.

The maintenance happy paths are pinned elsewhere; this file drives the branches
that were still uncovered: every guard in the maintenance GL poster (including
the entire refund method), the warranty helper validations and date handling,
and the remaining stock valuation / warehouse-resolution branches.

GL and audit writes are stubbed at the module boundary so a guard can be
reached without constructing a full accounting chart, but the branches, the
amount arithmetic and the document flags under test are all real.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import services.stock_service as ss
from models import (
    Customer,
    MaintenanceDeviceRegistry,
    MaintenanceOrder,
    MaintenanceOrderWarrantyStatus,
    MaintenanceSetting,
    MaintenanceWarrantyAudit,
    User,
)
from services.gl_posting import GlPostingError
from services.gl_service import GLService
from services.maintenance_gl_service import MaintenanceGLService
from services.maintenance_warranty_service import (
    WarrantyService,
    _locked_order,
    _matching_device,
    current_actor_id,
)
from services.stock_batch_service import StockBatchService
from utils.gl_reference_types import GLRef

# ───────────────────────────── maintenance GL ──────────────────────────────


@pytest.fixture
def gl_env(mocker):
    """Stub the GL boundary; return the post_or_fail spy and its fake entry."""
    entry = MagicMock()
    entry.id = 777
    post = mocker.patch("services.maintenance_gl_service.post_or_fail", return_value=entry)
    mocker.patch("services.maintenance_gl_service.log_financial")
    codes = {
        "MAINTENANCE_AR": "1134",
        "MAINTENANCE_REVENUE": "4119",
        "MAINTENANCE_COGS": "5119",
        "MAINTENANCE_DEPOSIT": "2171",
        "MAINTENANCE_AP": "2110",
        "VAT_OUTPUT": "2141",
        "VAT_INPUT": "2142",
        "INVENTORY_ASSET": "1130",
    }
    mocker.patch.object(
        GLService, "get_account_code_for_concept", side_effect=lambda concept, **kw: codes.get(concept, "9000")
    )
    mocker.patch.object(GLService, "resolve_liquidity_branch", return_value=3)
    mocker.patch.object(GLService, "get_default_liquidity_account", return_value="1110")
    return SimpleNamespace(post=post, entry=entry)


def _invoice(*, total="105", tax="5", with_order=True):
    order = SimpleNamespace(branch_id=None) if with_order else None
    return SimpleNamespace(
        tenant_id=7,
        id=12,
        order=order,
        order_id=1,
        invoice_number="MINV-GAP",
        total_amount=Decimal(total),
        tax_amount=Decimal(tax),
        invoice_date=None,
        currency="AED",
        exchange_rate=Decimal("1"),
        gl_posted=False,
        gl_posted_at=None,
        gl_entry_id=None,
        posted=False,
        posted_at=None,
    )


def _receipt(*, amount="100", mode="cash"):
    return SimpleNamespace(
        tenant_id=7,
        id=13,
        order=SimpleNamespace(branch_id=None, currency="AED", exchange_rate=Decimal("1")),
        amount=Decimal(amount),
        payment_mode=mode,
        receipt_number="PR-GAP",
        receipt_date=None,
        gl_posted=False,
        gl_posted_at=None,
        gl_entry_id=None,
    )


def _purchase_order(*, net="100", tax="5", total="105"):
    return SimpleNamespace(
        tenant_id=7,
        branch_id=None,
        id=9,
        taxable_amount=Decimal(net),
        tax_amount=Decimal(tax),
        total_amount=Decimal(total),
        po_number="PO-GAP",
        order_date=None,
        currency="AED",
        exchange_rate=Decimal("1"),
        supplier_name="Coverage Supplier",
    )


def _maintenance_return(*, gross="105", tax="5", cost="40"):
    return SimpleNamespace(
        tenant_id=7,
        order=SimpleNamespace(branch_id=None, currency="AED", exchange_rate=Decimal("1")),
        id=11,
        total_value=Decimal(gross),
        total_value_tax=Decimal(tax),
        total_value_cost=Decimal(cost),
        return_number="MR-GAP",
        return_date=None,
        gl_posted=False,
        gl_posted_at=None,
        posted=False,
        posted_at=None,
    )


class TestMaintenanceGLHelpers:
    def test_base_amount_converts_and_handles_missing(self):
        assert MaintenanceGLService._base_amount(Decimal("100"), "USD", Decimal("2"), "AED") == Decimal("200.000")
        assert MaintenanceGLService._base_amount(None, "AED", Decimal("1"), "AED") == Decimal("0")

    def test_require_account_refuses_an_unmapped_concept(self, mocker):
        mocker.patch.object(GLService, "get_account_code_for_concept", return_value=None)
        with pytest.raises(GlPostingError):
            MaintenanceGLService._require_account("MAINTENANCE_AR", 7, None)

    def test_liquidity_account_modes(self, mocker):
        mocker.patch.object(GLService, "resolve_liquidity_branch", return_value=3)
        mocker.patch.object(GLService, "get_default_liquidity_account", return_value="1110")
        assert MaintenanceGLService._liquidity_account("card", 7, None) == ("1110", "BANK", 3)
        assert MaintenanceGLService._liquidity_account(" CASH ", 7, 2) == ("1110", "CASH", 3)
        with pytest.raises(GlPostingError):
            MaintenanceGLService._liquidity_account("cheque", 7, None)
        with pytest.raises(GlPostingError):
            MaintenanceGLService._liquidity_account("gold_bar", 7, None)


class TestMaintenanceGLPosting:
    def test_invoice_rejects_zero_and_negative_net(self, gl_env):
        with pytest.raises(GlPostingError):
            MaintenanceGLService.post_invoice(_invoice(total="0", tax="0"), 1)
        with pytest.raises(GlPostingError):
            MaintenanceGLService.post_invoice(_invoice(total="5", tax="10"), 1)

    def test_invoice_with_and_without_tax(self, gl_env):
        invoice = _invoice(total="105", tax="5")
        assert MaintenanceGLService.post_invoice(invoice, 1) is gl_env.entry
        assert len(gl_env.post.call_args.kwargs["lines"]) == 3
        assert invoice.gl_posted is True and invoice.posted is True
        assert invoice.gl_entry_id == 777

        plain = _invoice(total="100", tax="0")
        MaintenanceGLService.post_invoice(plain, 1)
        assert len(gl_env.post.call_args.kwargs["lines"]) == 2

    def test_receipt_rejects_zero_amount(self, gl_env):
        with pytest.raises(GlPostingError):
            MaintenanceGLService.post_receipt(_receipt(amount="0"), 1)

    def test_receipt_cash_and_card(self, gl_env):
        for mode in ("cash", "card"):
            receipt = _receipt(mode=mode)
            assert MaintenanceGLService.post_receipt(receipt, 1) is gl_env.entry
            assert receipt.gl_posted is True
            assert len(gl_env.post.call_args.kwargs["lines"]) == 2

    def test_receipt_and_deposit_without_an_order_use_the_base_currency(self, gl_env):
        receipt = _receipt()
        receipt.order = None
        assert MaintenanceGLService.post_receipt(receipt, 1) is gl_env.entry
        assert gl_env.post.call_args.kwargs["currency"] == "AED"
        assert gl_env.post.call_args.kwargs["exchange_rate"] == Decimal("1")

        deposit = _receipt(mode="bank_transfer")
        deposit.order = None
        assert MaintenanceGLService.post_deposit(deposit, 1) is gl_env.entry

    def test_deposit_rejects_zero_amount(self, gl_env):
        with pytest.raises(GlPostingError):
            MaintenanceGLService.post_deposit(_receipt(amount="0"), 1)

    def test_deposit_posts_cash_leg(self, gl_env):
        receipt = _receipt(amount="50", mode="bank_transfer")
        assert MaintenanceGLService.post_deposit(receipt, 1) is gl_env.entry
        assert receipt.gl_entry_id == 777

    def test_purchase_receipt_guards(self, gl_env):
        with pytest.raises(ValueError):
            MaintenanceGLService.post_purchase_receipt(None, 1)
        with pytest.raises(GlPostingError):
            MaintenanceGLService.post_purchase_receipt(_purchase_order(net="0", tax="0", total="0"), 1)
        with pytest.raises(GlPostingError):
            MaintenanceGLService.post_purchase_receipt(_purchase_order(net="100", tax="5", total="999"), 1)

    def test_purchase_receipt_tax_branches(self, gl_env):
        MaintenanceGLService.post_purchase_receipt(_purchase_order(), 1)
        assert len(gl_env.post.call_args.kwargs["lines"]) == 3
        MaintenanceGLService.post_purchase_receipt(_purchase_order(net="100", tax="0", total="100"), 1)
        assert len(gl_env.post.call_args.kwargs["lines"]) == 2

    def test_refund_guards(self, gl_env):
        with pytest.raises(ValueError):
            MaintenanceGLService.post_refund(None, 1)
        with pytest.raises(GlPostingError):
            MaintenanceGLService.post_refund(_receipt(amount="0"), 1)

    def test_refund_posts_the_mirror_of_a_receipt(self, gl_env):
        for mode in ("cash", "bank"):
            receipt = _receipt(amount="30", mode=mode)
            assert MaintenanceGLService.post_refund(receipt, 1) is gl_env.entry
            assert receipt.gl_posted is True
            lines = gl_env.post.call_args.kwargs["lines"]
            assert lines[0]["concept_code"] == "MAINTENANCE_AR"
            assert lines[1]["credit"] == Decimal("30")

    def test_return_guards(self, gl_env):
        with pytest.raises(ValueError):
            MaintenanceGLService.post_return(None, 1)
        with pytest.raises(GlPostingError):
            MaintenanceGLService.post_return(_maintenance_return(gross="0", tax="0", cost="0"), 1)

    def test_return_with_tax_and_parts_cost(self, gl_env):
        result = MaintenanceGLService.post_return(_maintenance_return(), 1)
        assert result is gl_env.entry
        assert gl_env.post.call_count == 2
        first, second = [c.kwargs for c in gl_env.post.call_args_list]
        assert len(first["lines"]) == 3  # revenue + AR + VAT
        assert len(second["lines"]) == 2  # inventory + COGS

    def test_return_without_tax_or_parts_cost(self, gl_env):
        result = MaintenanceGLService.post_return(_maintenance_return(gross="100", tax="0", cost="0"), 1)
        assert result is gl_env.entry
        assert gl_env.post.call_count == 1
        assert len(gl_env.post.call_args.kwargs["lines"]) == 2


# ─────────────────────────── warranty helpers ──────────────────────────────


def _q(mocker, *, first=None, rows=None):
    """A query stand-in that returns itself from every chaining method."""
    query = mocker.MagicMock()
    for name in ("filter_by", "filter", "order_by", "join", "populate_existing", "with_for_update", "limit"):
        getattr(query, name).return_value = query
    query.first.return_value = first
    query.all.return_value = rows if rows is not None else []
    return query


@pytest.fixture
def queries(mocker):
    """Patch ``tenant_query`` with a per-model lookup table."""

    def build(mapping=None):
        table = dict(mapping or {})
        fallback = _q(mocker, first=mocker.MagicMock())

        def lookup(model, *_args, **_kwargs):
            return table.get(model, fallback)

        mocker.patch("services.maintenance_warranty_service.tenant_query", side_effect=lookup)
        return table

    return build


def _actor():
    return SimpleNamespace(has_permission=lambda code: True)


def _warranty_order(**overrides):
    values = {
        "id": 1,
        "status": "received",
        "is_archived": False,
        "warranty_checked": True,
        "device_serial_number": "SERIAL-GAP",
        "device_imei": None,
        "device_plate": None,
        "customer_id": 5,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _registry_device(**overrides):
    values = {
        "id": 3,
        "product_id": 4,
        "serial_number": "SERIAL-GAP",
        "imei": None,
        "plate": None,
        "customer_id": 5,
        "warranty_status": MaintenanceOrderWarrantyStatus.UNDER_WARRANTY,
        "is_under_warranty": True,
        "warranty_start_date": datetime.now(UTC) - timedelta(days=1),
        "warranty_end_date": datetime.now(UTC) + timedelta(days=30),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class TestWarrantyHelpers:
    def test_current_actor_id_without_authentication(self):
        assert current_actor_id() == 1

    def test_current_actor_id_authenticated(self, mocker):
        mocker.patch("flask_login.current_user", SimpleNamespace(is_authenticated=True, id=9))
        assert current_actor_id() == 9

    def test_current_actor_id_falls_back_when_identity_fails(self, mocker):
        class BrokenIdentity:
            is_authenticated = True

            @property
            def id(self):
                raise RuntimeError("no identity")

        mocker.patch("flask_login.current_user", BrokenIdentity())
        assert current_actor_id() == 1

    def test_locked_order_missing(self, mocker, queries):
        queries({MaintenanceOrder: _q(mocker, first=None)})
        with pytest.raises(ValueError):
            _locked_order(1, 7)

    @pytest.mark.parametrize("status,archived", [("closed", False), ("cancelled", False), ("received", True)])
    def test_locked_order_refuses_finished_orders(self, mocker, queries, status, archived):
        queries({MaintenanceOrder: _q(mocker, first=_warranty_order(status=status, is_archived=archived))})
        with pytest.raises(ValueError):
            _locked_order(1, 7)

    def test_matching_device_uses_all_identifiers(self, mocker, queries):
        order = _warranty_order(device_serial_number="S", device_imei="I", device_plate="P")
        device = _registry_device(serial_number="S", imei="I", plate="P")
        queries({MaintenanceDeviceRegistry: _q(mocker, rows=[device])})
        assert _matching_device(order, 7) is device

    def test_matching_device_refuses_ambiguous_registry(self, mocker, queries):
        order = _warranty_order()
        queries({MaintenanceDeviceRegistry: _q(mocker, rows=[_registry_device(), _registry_device()])})
        with pytest.raises(ValueError):
            _matching_device(order, 7)

    def test_matching_device_refuses_conflicting_identifier(self, mocker, queries):
        order = _warranty_order(device_imei="I", device_serial_number="S2")
        queries({MaintenanceDeviceRegistry: _q(mocker, rows=[_registry_device(imei="I", serial_number="S1")])})
        with pytest.raises(ValueError):
            _matching_device(order, 7)

    def test_matching_device_refuses_another_customers_device(self, mocker, queries):
        order = _warranty_order(customer_id=5)
        queries({MaintenanceDeviceRegistry: _q(mocker, rows=[_registry_device(customer_id=6)])})
        with pytest.raises(ValueError):
            _matching_device(order, 7)


class TestWarrantyServiceGuards:
    def test_empty_reason_is_refused(self):
        with pytest.raises(ValueError, match="سبب"):
            WarrantyService.cancel_warranty(1, 7, performed_by=5, reason="   ")

    def test_unauthorized_actor_is_refused(self, mocker, queries):
        queries({User: _q(mocker, first=None)})
        with pytest.raises(ValueError, match="صلاحية"):
            WarrantyService.cancel_warranty(1, 7, performed_by=5, reason="damage")

    def test_unchecked_order_is_refused(self, mocker, queries):
        queries(
            {
                User: _q(mocker, first=_actor()),
                MaintenanceOrder: _q(mocker, first=_warranty_order(warranty_checked=False)),
            }
        )
        with pytest.raises(ValueError, match="فحص"):
            WarrantyService.cancel_warranty(1, 7, performed_by=5, reason="damage")

    def test_unregistered_device_is_refused(self, mocker, queries):
        queries(
            {
                User: _q(mocker, first=_actor()),
                MaintenanceOrder: _q(mocker, first=_warranty_order()),
                MaintenanceDeviceRegistry: _q(mocker, first=None),
            }
        )
        with pytest.raises(ValueError, match="الجهاز غير موجود"):
            WarrantyService.cancel_warranty(1, 7, performed_by=5, reason="damage")

    def test_restore_without_a_cancelled_change_is_refused(self, mocker, queries):
        queries(
            {
                User: _q(mocker, first=_actor()),
                MaintenanceOrder: _q(mocker, first=_warranty_order()),
                MaintenanceDeviceRegistry: _q(mocker, rows=[_registry_device()]),
                MaintenanceWarrantyAudit: _q(mocker, first=None),
            }
        )
        with pytest.raises(ValueError, match="ملغاة"):
            WarrantyService.restore_warranty(1, 7, performed_by=5, reason="reversed")

    def test_cancel_of_a_non_active_warranty_is_refused(self, mocker, queries):
        device = _registry_device(warranty_status=MaintenanceOrderWarrantyStatus.EXPIRED)
        queries(
            {
                User: _q(mocker, first=_actor()),
                MaintenanceOrder: _q(mocker, first=_warranty_order()),
                MaintenanceDeviceRegistry: _q(mocker, rows=[device]),
            }
        )
        with pytest.raises(ValueError, match="كفالة سارية"):
            WarrantyService.cancel_warranty(1, 7, performed_by=5, reason="damage")

    def _restore_queries(self, mocker, queries, *, start, end):
        device = _registry_device(
            warranty_status=MaintenanceOrderWarrantyStatus.VOID,
            is_under_warranty=False,
            warranty_start_date=start,
            warranty_end_date=end,
        )
        queries(
            {
                User: _q(mocker, first=_actor()),
                MaintenanceOrder: _q(mocker, first=_warranty_order()),
                MaintenanceDeviceRegistry: _q(mocker, rows=[device]),
                MaintenanceWarrantyAudit: _q(mocker, first=SimpleNamespace(action="cancelled")),
                MaintenanceSetting: _q(
                    mocker,
                    first=SimpleNamespace(
                        color_warranty="#10b981",
                        color_non_warranty="#ef4444",
                        allow_engineer_restore_warranty=False,
                        allow_engineer_cancel_warranty=False,
                    ),
                ),
            }
        )
        return device

    def test_restore_normalizes_naive_dates(self, mocker, queries):
        mocker.patch("services.maintenance_warranty_service.db")
        device = self._restore_queries(
            mocker,
            queries,
            start=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1),
            end=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30),
        )
        audit = WarrantyService.restore_warranty(1, 7, performed_by=5, reason="reversed")
        assert audit.action == "restored"
        assert device.is_under_warranty is True
        assert audit.to_status == MaintenanceOrderWarrantyStatus.UNDER_WARRANTY

    def test_restore_refuses_an_expired_window(self, mocker, queries):
        self._restore_queries(
            mocker,
            queries,
            start=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30),
            end=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1),
        )
        with pytest.raises(ValueError, match="فترة الكفالة"):
            WarrantyService.restore_warranty(1, 7, performed_by=5, reason="reversed")

    def test_warranty_check_rejects_an_unknown_user(self, mocker, queries):
        queries({User: _q(mocker, first=None)})
        with pytest.raises(ValueError, match="مستخدم فحص"):
            WarrantyService.check_warranty_on_receipt(1, 7, checked_by=5)

    def test_registry_requires_an_identifier(self):
        with pytest.raises(ValueError, match="رقم سيريال"):
            WarrantyService.add_device_to_warranty_registry(
                7,
                customer_id=None,
                product_id=None,
                brand=None,
                model=None,
                serial_number=None,
                imei=None,
                plate=None,
                purchase_date=None,
                warranty_start_date=None,
                warranty_end_date=None,
                warranty_type=None,
            )

    def test_registry_rejects_an_unknown_customer(self, mocker, queries):
        queries(
            {
                Customer: _q(mocker, first=None),
                MaintenanceDeviceRegistry: _q(mocker, first=None),
            }
        )
        with pytest.raises(ValueError, match="العميل غير موجود"):
            WarrantyService.add_device_to_warranty_registry(
                7,
                customer_id=5,
                product_id=None,
                brand=None,
                model=None,
                serial_number="SERIAL-GAP",
                imei=None,
                plate=None,
                purchase_date=None,
                warranty_start_date=None,
                warranty_end_date=None,
                warranty_type=None,
            )

    def test_registry_marks_an_expired_warranty(self, mocker, queries):
        mocker.patch("services.maintenance_warranty_service.db")
        mocker.patch("services.maintenance_warranty_service.log_financial")
        device = WarrantyService.add_device_to_warranty_registry(
            7,
            performed_by=1,
            customer_id=None,
            product_id=None,
            brand=None,
            model=None,
            serial_number="EXPIRED-SERIAL",
            imei=None,
            plate=None,
            purchase_date=None,
            warranty_start_date=datetime.now(UTC) - timedelta(days=30),
            warranty_end_date=datetime.now(UTC) - timedelta(days=1),
            warranty_type=None,
        )
        assert device is not None

    def test_find_device_for_an_unknown_order(self, mocker, queries):
        queries({MaintenanceOrder: _q(mocker, first=None)})
        assert WarrantyService.find_device_for_order(1, 7) is None

    def test_register_rejects_an_unknown_actor(self, mocker, queries):
        queries({User: _q(mocker, first=None)})
        with pytest.raises(ValueError, match="المستخدم المنفّذ"):
            WarrantyService.register_order_device(1, 7, performed_by=5)

    def test_register_rejects_an_unknown_order(self, mocker, queries):
        queries({User: _q(mocker, first=_actor()), MaintenanceOrder: _q(mocker, first=None)})
        with pytest.raises(ValueError, match="أمر الصيانة غير موجود"):
            WarrantyService.register_order_device(1, 7, performed_by=5)

    def test_register_rejects_an_archived_order(self, mocker, queries):
        queries(
            {
                User: _q(mocker, first=_actor()),
                MaintenanceOrder: _q(mocker, first=_warranty_order(is_archived=True)),
            }
        )
        with pytest.raises(ValueError, match="مؤرشف"):
            WarrantyService.register_order_device(1, 7, performed_by=5)


# ───────────────────────────── stock service ───────────────────────────────


class TestStockValuationBranches:
    def test_zero_quantity_sync_returns_unchanged(self):
        movement = SimpleNamespace(quantity=0, movement_type="adjustment")
        assert ss.StockService.value_synced_movement(movement) is movement

    def test_sync_refuses_a_missing_product(self, mocker):
        movement = SimpleNamespace(quantity=1, movement_type="adjustment", product_id=999, warehouse_id=None)
        mocker.patch("services.stock_service.db.session.get", return_value=None)
        with pytest.raises(ValueError, match="not found"):
            ss.StockService.value_synced_movement(movement)

    def test_sync_refuses_an_invalid_cost(self, mocker):
        product = SimpleNamespace(id=1, tenant_id=1, name="P", cost_price="not-a-number")
        movement = SimpleNamespace(quantity=1, movement_type="adjustment", product_id=1, warehouse_id=None)
        mocker.patch("services.stock_service.db.session.get", return_value=product)
        with pytest.raises(ValueError, match="invalid unit cost"):
            ss.StockService.value_synced_movement(movement)

    def test_sync_refuses_a_nonpositive_cost(self, mocker):
        product = SimpleNamespace(id=1, tenant_id=1, name="P", cost_price=Decimal("0"))
        movement = SimpleNamespace(quantity=1, movement_type="adjustment", product_id=1, warehouse_id=None)
        mocker.patch("services.stock_service.db.session.get", return_value=product)
        with pytest.raises(ValueError, match="greater than zero"):
            ss.StockService.value_synced_movement(movement)

    def test_sync_issue_falls_back_to_product_cost(self, mocker):
        product = MagicMock(id=1, tenant_id=1, name="P", cost_price=Decimal("7"))
        warehouse = MagicMock(id=2, branch_id=3, allow_negative_inventory=False)
        movement = MagicMock(quantity=-2, movement_type="adjustment", product_id=1, warehouse_id=2, id=5)
        pwc = MagicMock(total_quantity=0, average_cost=None)
        mocker.patch.object(ss.ProductWarehouseCost, "query").filter_by.return_value.first.return_value = pwc
        mocker.patch.object(GLService, "ensure_core_accounts")
        decrement = mocker.patch.object(ss.StockService, "_decrement_wac_on_issue")
        mocker.patch.object(ss.StockService, "_post_adjustment_gl")

        assert ss.StockService.value_synced_movement(movement, product=product, warehouse=warehouse) is movement
        assert decrement.call_args.kwargs["unit_cost"] == Decimal("7")

    def test_decrement_wac_creates_pwc_when_absent(self, mocker):
        mocker.patch.object(ss, "db")
        mocker.patch("services.stock_service._safe_for_update", return_value=None)
        add = mocker.patch.object(ss.db.session, "add")

        ss.StockService._decrement_wac_on_issue(
            tenant_id=1,
            product_id=1,
            warehouse_id=2,
            issued_qty=Decimal("3"),
            unit_cost=Decimal("10"),
            movement_type="adjustment",
            reference_type=GLRef.INVENTORY_MIGRATION,
            reference_id=5,
        )
        created = [c.args[0] for c in add.call_args_list if isinstance(c.args[0], ss.ProductWarehouseCost)]
        assert created
        assert created[0].total_quantity == Decimal("-3")
        assert created[0].average_cost == Decimal("10.0000")

    def test_create_movement_uses_a_resolved_warehouse(self, mocker):
        product = MagicMock(id=1, tenant_id=1, name="P", current_stock=Decimal("10"))
        warehouse = MagicMock(id=2, tenant_id=1, branch_id=3, allow_negative_inventory=False)
        pws = MagicMock(quantity=Decimal("10"))
        mocker.patch.object(ss, "db")
        mocker.patch("services.stock_service._safe_for_update", return_value=pws)
        mocker.patch.object(ss.StockService, "_sync_current_stock")
        mocker.patch("services.websocket_service.broadcast_stock_alert")

        movement = ss.StockService.create_movement(
            product_id=1,
            quantity=2,
            movement_type="adjustment",
            resolved_product=product,
            resolved_warehouse=warehouse,
        )
        assert movement.warehouse_id == 2
        assert movement.quantity == Decimal("2")

    @staticmethod
    def _fefo_transfer_env(mocker, *, lots, consumed_qty):
        """A two-warehouse transfer with FEFO enabled and stubbed valuation."""
        product = MagicMock(id=1, tenant_id=1, name="P")
        from_wh = MagicMock(id=10, tenant_id=1, name="A", name_ar="أ", is_active=True)
        to_wh = MagicMock(id=11, tenant_id=1, name="B", name_ar="ب", is_active=True)
        src_pwc = MagicMock(total_quantity=Decimal("20"), total_value=Decimal("200"), average_cost=Decimal("10"))
        dest_pwc = MagicMock(total_quantity=Decimal("5"), total_value=Decimal("50"), average_cost=Decimal("10"))
        q_pwc = MagicMock()
        q_pwc.filter_by.return_value.first.side_effect = [src_pwc, dest_pwc]

        mocker.patch.object(ss, "db")
        mocker.patch("services.stock_service.db.session.get", return_value=product)
        mocker.patch.object(ss.Warehouse, "query").filter_by.return_value.first.side_effect = [from_wh, to_wh]
        mocker.patch.object(ss.StockService, "create_movement", return_value=MagicMock(id=9))
        mocker.patch.object(ss.StockService, "get_product_stock", return_value=Decimal("50"))
        mocker.patch.object(ss.ProductWarehouseCost, "query", q_pwc)
        mocker.patch("services.stock_service._safe_for_update", side_effect=[src_pwc, dest_pwc])
        mocker.patch.object(StockBatchService, "batches_enabled", return_value=True)
        mocker.patch.object(StockBatchService, "_fefo_query").return_value.all.return_value = lots
        mocker.patch.object(StockBatchService, "consume_fefo", return_value=(consumed_qty, Decimal("80")))
        return mocker.patch.object(StockBatchService, "record_receipt")

    def test_transfer_moves_fefo_lots_between_warehouses(self, mocker):
        lot = MagicMock(quantity=Decimal("10"), unit_cost=Decimal("8"), expiry_date=None)
        record = self._fefo_transfer_env(mocker, lots=[lot], consumed_qty=Decimal("10"))
        ss.StockService.transfer_stock(1, 10, 11, 10, user=None)
        record.assert_called_once()

    def test_transfer_rejects_insufficient_fefo_lots(self, mocker):
        self._fefo_transfer_env(mocker, lots=[], consumed_qty=Decimal("5"))
        with pytest.raises(ValueError, match="أقل من كمية التحويل"):
            ss.StockService.transfer_stock(1, 10, 11, 10, user=None)

    def test_transfer_stops_copying_lots_once_quantity_is_moved(self, mocker):
        first = MagicMock(quantity=Decimal("10"), unit_cost=Decimal("8"), expiry_date=None)
        second = MagicMock(quantity=Decimal("5"), unit_cost=Decimal("9"), expiry_date=None)
        record = self._fefo_transfer_env(mocker, lots=[first, second], consumed_qty=Decimal("10"))
        ss.StockService.transfer_stock(1, 10, 11, 10, user=None)
        record.assert_called_once()

    def test_process_sale_lines_records_issued_serials(self, mocker):
        line = MagicMock(product_id=1, quantity=2, id=5)
        line.serial_numbers = None
        sale = MagicMock(tenant_id=1, warehouse_id=2, id=3, sale_number="S", lines=[line])
        mocker.patch.object(ss.StockService, "remove_stock")
        mocker.patch(
            "services.serial_tracking_service.SerialTrackingService.issue_serials",
            return_value=["SER-A", "SER-B"],
        )
        ss.StockService.process_sale_lines(sale)
        assert line.serial_numbers == ["SER-A", "SER-B"]

    def test_purchase_lines_normalize_a_nonpositive_exchange_rate(self, mocker):
        product = MagicMock(id=1, tenant_id=1)
        line = MagicMock(
            product_id=1,
            quantity=10,
            landed_inventory_unit_cost=Decimal("5"),
            inventory_unit_cost=Decimal("5"),
        )
        purchase = MagicMock()
        purchase.tenant_id = 1
        purchase.purchase_number = "P-NEG-RATE"
        purchase.exchange_rate = Decimal("-1")
        purchase.currency = "AED"
        purchase.base_currency = "AED"
        purchase.id = 7
        purchase.lines = [line]

        mocker.patch.object(ss.StockService, "add_stock")
        mocker.patch.object(ss.StockService, "_update_wac_on_receipt")
        mocker.patch("services.stock_service.db.session.get", return_value=product)
        mocker.patch.object(ss.ProductWarehouseCost, "query").filter_by.return_value.all.return_value = []
        convert = mocker.patch("utils.currency_utils.convert_and_quantize_aed", return_value=Decimal("50"))

        ss.StockService.process_purchase_lines(purchase, warehouse_id=9)
        assert convert.call_args.args[2] == Decimal("1")
