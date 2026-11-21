"""Coverage gaps for ``services/maintenance_order_service.py``.

The maintenance suite already pins the happy paths. This file drives the
branches it never reached: every validation guard, the refund path, the
close-path collection variants, and the three report methods that had no
caller at all.

Validators and reports are exercised with in-memory objects and a patched
``tenant_query`` (the service boundary). Money-moving paths use the real ORM
and stub only the GL / stock / e-invoice collaborators, so the document,
discount and permission contracts are never weakened.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from models import (
    Branch,
    Customer,
    MaintenanceInvoice,
    MaintenanceOrder,
    MaintenanceOrderLine,
    MaintenanceReceipt,
    MaintenanceReturn,
    MaintenanceServiceTemplate,
    MaintenanceSetting,
    Product,
    Sale,
    StockMovement,
    Tenant,
    User,
    Warehouse,
)
from services.maintenance_order_service import (
    MaintenanceService,
    _apply_customer_movement,
    _authorize_discount,
    _authorize_price_override,
    _locked_order,
    _require_tenant_id,
    _validate_line_values,
    _validate_tax_rate,
)


def _q(mocker, *, first=None, rows=None, count=0):
    """A query stand-in that returns itself from every chaining method."""
    query = mocker.MagicMock()
    for name in ("filter_by", "filter", "order_by", "join", "populate_existing", "with_for_update"):
        getattr(query, name).return_value = query
    query.first.return_value = first
    query.all.return_value = rows if rows is not None else []
    query.count.return_value = count
    return query


@pytest.fixture
def queries(mocker):
    """Patch ``tenant_query`` with a per-model lookup table."""

    def build(mapping=None, *, default_first=None):
        table = dict(mapping or {})
        positions: dict[object, int] = {}
        fallback = _q(mocker, first=mocker.MagicMock() if default_first is None else default_first)

        def lookup(model, *_args, **_kwargs):
            value = table.get(model, fallback)
            if isinstance(value, (list, tuple)):
                index = positions.get(model, 0)
                positions[model] = index + 1
                return value[min(index, len(value) - 1)]
            return value

        mocker.patch("services.maintenance_order_service.tenant_query", side_effect=lookup)
        return table

    return build


@pytest.fixture
def no_active_tenant(mocker):
    mocker.patch("services.maintenance_order_service.get_active_tenant_id", return_value=None)


def _order_kwargs(**overrides):
    kwargs = {
        "branch_id": None,
        "warehouse_id": None,
        "customer_id": None,
        "customer_name": None,
        "customer_phone": None,
        "device_brand": None,
        "device_model": None,
        "device_serial_number": None,
        "device_imei": None,
        "device_plate": None,
        "device_km": None,
        "device_fault_description": None,
        "received_by": 5,
    }
    kwargs.update(overrides)
    return kwargs


def _real_order(db_session, tenant, user, warehouse, *, customer=None, status=None):
    order = MaintenanceService.create_order(
        tenant_id=tenant.id,
        branch_id=warehouse.branch_id,
        warehouse_id=warehouse.id,
        customer_id=customer.id if customer else None,
        customer_name="Coverage Customer",
        customer_phone=None,
        device_brand="Toyota",
        device_model="Camry",
        device_serial_number=f"COV-{uuid4().hex[:10]}",
        device_imei=None,
        device_plate=None,
        device_km=None,
        device_fault_description=None,
        received_by=user.id,
    )
    if status is not None:
        order.status = status
    db_session.flush()
    return order


def _money_line(*, qty="1", price="10", percent="0", value="0", mode="percent", tax="0"):
    return SimpleNamespace(
        quantity=Decimal(qty),
        unit_price=Decimal(price),
        discount_percent=Decimal(percent),
        discount_value=Decimal(value),
        discount_mode=mode,
        tax_rate=Decimal(tax),
        is_archived=False,
    )


def _money_order(lines, *, percent="0", value="0", paid="0", deposit="0", inclusive=False):
    return SimpleNamespace(
        lines=lines,
        services_lines=[],
        discount_total_percent=Decimal(percent),
        discount_total_value=Decimal(value),
        prices_include_vat=inclusive,
        paid_amount=Decimal(paid),
        deposit_amount=Decimal(deposit),
        currency="AED",
        base_currency="AED",
        exchange_rate=Decimal("1"),
    )


# ── module-level helpers ──────────────────────────────────────────────────


class TestMoneyMovementHelper:
    def test_missing_customer_is_a_noop(self, mocker, queries, db_session):
        queries({Customer: _q(mocker, first=None)})
        order = SimpleNamespace(customer_id=99, currency="AED", base_currency="AED", exchange_rate=Decimal("1"))
        _apply_customer_movement(order, 1, Decimal("10"), "charge")

    def test_return_and_refund_move_the_customer_balance(self, mocker, queries, db_session):
        customer = mocker.MagicMock()
        queries({Customer: _q(mocker, first=customer)})
        order = SimpleNamespace(customer_id=5, currency="AED", base_currency="AED", exchange_rate=Decimal("1"))
        _apply_customer_movement(order, 1, Decimal("10"), "return")
        customer.apply_return.assert_called_once_with(Decimal("10"))
        _apply_customer_movement(order, 1, Decimal("4"), "refund")
        customer.adjust_balance.assert_called_once_with(Decimal("-4"))

    def test_no_customer_id_is_a_noop(self, no_active_tenant, db_session):
        _apply_customer_movement(SimpleNamespace(customer_id=None), 1, Decimal("10"), "charge")


class TestTenantAndOrderGuards:
    def test_tenant_id_must_match_the_active_tenant(self, mocker):
        mocker.patch("services.maintenance_order_service.get_active_tenant_id", return_value=2)
        with pytest.raises(ValueError, match="غير صالح"):
            _require_tenant_id(1)

    def test_missing_order_is_refused(self, mocker, queries):
        queries({MaintenanceOrder: _q(mocker, first=None)})
        with pytest.raises(ValueError, match="غير موجود"):
            _locked_order(999, 1)


class TestLineValueValidation:
    @pytest.mark.parametrize("value", ["abc", None, "NaN", "Infinity"])
    def test_unparseable_numbers_are_refused(self, no_active_tenant, value):
        with pytest.raises(ValueError, match="أرقاماً صالحة"):
            _validate_line_values(value, "10", "0", "0", "percent", "5")

    def test_quantity_and_price_have_individual_caps(self, no_active_tenant):
        with pytest.raises(ValueError, match="الحد المسموح"):
            _validate_line_values("1000000000000", "1", "0", "0", "percent", "5")


class TestDiscountAndTaxAuthorization:
    def test_discount_without_permission_is_refused(self, mocker, queries, no_active_tenant):
        queries({User: _q(mocker, first=None)})
        with pytest.raises(ValueError, match="صلاحية"):
            _authorize_discount(1, 7, Decimal("1"), Decimal("100"), Decimal("10"), Decimal("0"), "percent")

    def test_discount_over_the_cap_needs_override(self, mocker, queries, no_active_tenant):
        actor = mocker.MagicMock()
        actor.has_permission.side_effect = [True, False]
        setting = SimpleNamespace(max_discount_percent=Decimal("5"), max_discount_value=Decimal("0"))
        queries({User: _q(mocker, first=actor), MaintenanceSetting: _q(mocker, first=setting)})
        with pytest.raises(ValueError, match="الحد المسموح"):
            _authorize_discount(1, 7, Decimal("1"), Decimal("100"), Decimal("50"), Decimal("0"), "percent")

    def test_unchanged_price_does_not_need_a_permissions_lookup(self, no_active_tenant):
        _authorize_price_override(1, None, Decimal("100"), Decimal("100"))

    def test_override_permission_allows_a_price_change(self, mocker, queries, no_active_tenant):
        actor = mocker.MagicMock()
        actor.has_permission.return_value = True
        queries({User: _q(mocker, first=actor)})
        _authorize_price_override(1, 7, Decimal("200"), Decimal("100"))
        actor.has_permission.assert_called_once_with("maintenance_override_discount")

    def test_missing_tenant_is_refused_by_tax_validation(self, mocker, queries, no_active_tenant):
        queries({Tenant: _q(mocker, first=None)})
        with pytest.raises(ValueError, match="الشركة غير موجودة"):
            _validate_tax_rate(1, None)

    def test_zero_rated_category_is_exempt(self, mocker, queries, no_active_tenant):
        tenant = SimpleNamespace(enable_tax_categories=True)
        queries({Tenant: _q(mocker, first=tenant)})
        mocker.patch("services.maintenance_order_service.normalize_tax_rate", return_value=Decimal("5"))
        product = SimpleNamespace(tax_category="zero")
        assert _validate_tax_rate(1, None, product=product) == Decimal("0")

    @pytest.mark.parametrize("requested", ["abc", None])
    def test_unparseable_requested_rate_is_refused(self, mocker, queries, no_active_tenant, requested):
        tenant = SimpleNamespace(enable_tax_categories=False)
        queries({Tenant: _q(mocker, first=tenant)})
        mocker.patch("services.maintenance_order_service.normalize_tax_rate", return_value=Decimal("5"))
        if requested is None:
            # None means "use the tenant rate": pass an object that Decimal rejects.
            requested = object()
        with pytest.raises(ValueError, match="نسبة الضريبة غير صالحة"):
            _validate_tax_rate(1, requested)


# ── create_order guards ───────────────────────────────────────────────────


class TestCreateOrderGuards:
    @pytest.fixture(autouse=True)
    def deps(self, mocker, no_active_tenant):
        mocker.patch("services.maintenance_order_service.resolve_tenant_base_currency", return_value="AED")
        mocker.patch(
            "services.maintenance_order_service.DocumentSequenceService.next_number",
            return_value="MN-COV-1",
        )

    def test_warehouse_must_exist(self, mocker, queries):
        queries({Branch: _q(mocker, first="ok"), Warehouse: _q(mocker, first=None)})
        with pytest.raises(ValueError, match="المستودع غير موجود"):
            MaintenanceService.create_order(1, **_order_kwargs(branch_id=1, warehouse_id=2))

    def test_warehouse_must_belong_to_the_branch(self, mocker, queries):
        warehouse = SimpleNamespace(branch_id=9)
        queries(
            {
                Branch: _q(mocker, first="ok"),
                Warehouse: _q(mocker, first=warehouse),
            }
        )
        with pytest.raises(ValueError, match="المستودع لا يتبع"):
            MaintenanceService.create_order(1, **_order_kwargs(branch_id=1, warehouse_id=2))

    def test_warehouse_branch_must_be_active(self, mocker, queries):
        warehouse = SimpleNamespace(branch_id=9)
        queries({Warehouse: _q(mocker, first=warehouse), Branch: _q(mocker, first=None)})
        with pytest.raises(ValueError, match="فرع المستودع غير صالح"):
            MaintenanceService.create_order(1, **_order_kwargs(warehouse_id=2))

    def test_customer_must_exist(self, mocker, queries):
        queries({Customer: _q(mocker, first=None)})
        with pytest.raises(ValueError, match="العميل غير موجود"):
            MaintenanceService.create_order(1, **_order_kwargs(customer_id=3))

    def test_warranty_sale_must_belong_to_the_customer(self, mocker, queries):
        queries({Sale: _q(mocker, first=None)})
        with pytest.raises(ValueError, match="فاتورة الضمان غير صالحة"):
            MaintenanceService.create_order(1, **_order_kwargs(warranty_sale_id=4))

    def test_warranty_sale_mismatch(self, mocker, queries):
        queries({Sale: _q(mocker, first=SimpleNamespace(customer_id=77))})
        with pytest.raises(ValueError, match="فاتورة الضمان غير صالحة"):
            MaintenanceService.create_order(1, **_order_kwargs(warranty_sale_id=4, customer_id=3))

    def test_matching_warranty_sale_advances_to_the_receiver_check(self, mocker, queries):
        queries(
            {
                Sale: _q(mocker, first=SimpleNamespace(customer_id=3)),
                Customer: _q(mocker, first="ok"),
                User: _q(mocker, first=None),
            }
        )
        with pytest.raises(ValueError, match="مستلم الجهاز غير موجود"):
            MaintenanceService.create_order(1, **_order_kwargs(warranty_sale_id=4, customer_id=3))

    def test_receiver_must_exist(self, mocker, queries):
        queries({User: _q(mocker, first=None)})
        with pytest.raises(ValueError, match="مستلم الجهاز غير موجود"):
            MaintenanceService.create_order(1, **_order_kwargs())

    def test_tenant_must_exist(self, mocker, queries):
        queries({Tenant: _q(mocker, first=None)})
        with pytest.raises(ValueError, match="الشركة غير موجودة"):
            MaintenanceService.create_order(1, **_order_kwargs())

    def test_currency_code_must_have_three_letters(self, mocker, queries):
        queries({Tenant: _q(mocker, first=SimpleNamespace(default_currency="AED"))})
        with pytest.raises(ValueError, match="العملة غير صالحة"):
            MaintenanceService.create_order(1, **_order_kwargs(currency="12"))

    @pytest.mark.parametrize("rate", ["abc", object()])
    def test_unparseable_exchange_rate_is_refused(self, mocker, queries, rate):
        queries({Tenant: _q(mocker, first=SimpleNamespace(default_currency="AED"))})
        with pytest.raises(ValueError, match="سعر الصرف غير صالح"):
            MaintenanceService.create_order(1, **_order_kwargs(exchange_rate=rate))

    @pytest.mark.parametrize("rate", [Decimal("0"), Decimal("-1"), Decimal("1000000000")])
    def test_out_of_range_exchange_rate_is_refused(self, mocker, queries, rate):
        queries({Tenant: _q(mocker, first=SimpleNamespace(default_currency="AED"))})
        with pytest.raises(ValueError, match="سعر الصرف غير صالح"):
            MaintenanceService.create_order(1, **_order_kwargs(exchange_rate=rate))

    def test_exchange_rate_precision_is_limited(self, mocker, queries):
        queries({Tenant: _q(mocker, first=SimpleNamespace(default_currency="AED"))})
        with pytest.raises(ValueError, match="دقة سعر الصرف"):
            MaintenanceService.create_order(1, **_order_kwargs(exchange_rate=Decimal("1.0000001")))

    def test_foreign_currency_requires_an_explicit_rate(self, mocker, queries):
        queries({Tenant: _q(mocker, first=SimpleNamespace(default_currency="AED"))})
        with pytest.raises(ValueError, match="سعر الصرف مطلوب"):
            MaintenanceService.create_order(1, **_order_kwargs(currency="USD"))

    def test_base_currency_rate_must_be_one(self, mocker, queries):
        queries({Tenant: _q(mocker, first=SimpleNamespace(default_currency="AED"))})
        with pytest.raises(ValueError, match="عملة الأساس يجب أن يساوي واحداً"):
            MaintenanceService.create_order(1, **_order_kwargs(exchange_rate=Decimal("2")))


# ── line guards and recalculation ─────────────────────────────────────────


class TestLineGuards:
    def test_add_line_refuses_a_warehouse_outside_the_order(
        self, db_session, sample_tenant, sample_user, sample_warehouse, sample_product
    ):
        order = _real_order(db_session, sample_tenant, sample_user, sample_warehouse)
        with pytest.raises(ValueError, match="المستودع غير صالح"):
            MaintenanceService.add_line(
                order.id,
                sample_tenant.id,
                product_id=sample_product.id,
                quantity=Decimal("1"),
                unit_price=Decimal("100"),
                warehouse_id=999999,
                actor_id=sample_user.id,
            )

    def test_services_cannot_be_added_to_a_closed_order(self, db_session, sample_tenant, sample_user, sample_warehouse):
        order = _real_order(db_session, sample_tenant, sample_user, sample_warehouse, status="closed")
        with pytest.raises(ValueError, match="حالة الأمر"):
            MaintenanceService.add_service_line(
                order.id,
                sample_tenant.id,
                service_code="X",
                service_name="x",
                service_name_ar=None,
                service_category="other",
                unit_price=Decimal("10"),
                engineer_id=None,
            )

    def test_service_template_must_exist(self, db_session, sample_tenant, sample_user, sample_warehouse):
        order = _real_order(db_session, sample_tenant, sample_user, sample_warehouse)
        with pytest.raises(ValueError, match="قالب الخدمة غير موجود"):
            MaintenanceService.add_service_line(
                order.id,
                sample_tenant.id,
                service_code="MISSING-CODE",
                service_name="x",
                service_name_ar=None,
                service_category="other",
                unit_price=Decimal("10"),
                engineer_id=None,
            )

    def test_engineer_must_exist(self, db_session, sample_tenant, sample_user, sample_warehouse):
        template = MaintenanceService.create_service_template(
            sample_tenant.id,
            service_code="COV-SVC",
            name="Service",
            name_ar=None,
            service_category="other",
            fixed_price=Decimal("50"),
            duration_minutes=30,
            tax_rate=Decimal("5"),
            requires_parts=False,
            sort_order=1,
        )
        order = _real_order(db_session, sample_tenant, sample_user, sample_warehouse)
        with pytest.raises(ValueError, match="المهندس غير موجود"):
            MaintenanceService.add_service_line(
                order.id,
                sample_tenant.id,
                service_code=template.service_code,
                service_name=template.name,
                service_name_ar=template.name_ar,
                service_category=template.service_category,
                unit_price=Decimal("50"),
                engineer_id=999999,
            )


class TestRecalculationGuards:
    def test_non_finite_order_discount_is_refused(self, no_active_tenant):
        order = _money_order([_money_line()], percent="NaN")
        with pytest.raises(ValueError, match="الخصم الإجمالي غير صالح"):
            MaintenanceService._recalculate_order_totals(order)

    def test_two_order_discount_types_are_refused(self, no_active_tenant):
        order = _money_order([_money_line()], percent="10", value="5")
        with pytest.raises(ValueError, match="نوع خصم إجمالي واحد"):
            MaintenanceService._recalculate_order_totals(order)

    def test_order_discount_cannot_exceed_the_order(self, no_active_tenant):
        order = _money_order([_money_line()], value="20")
        with pytest.raises(ValueError, match="يتجاوز قيمة الأمر"):
            MaintenanceService._recalculate_order_totals(order)

    def test_largest_remainder_allocation(self, no_active_tenant):
        order = _money_order([_money_line(price="10"), _money_line(price="10"), _money_line(price="10")], value="0.002")
        MaintenanceService._recalculate_order_totals(order)
        assert order.subtotal == Decimal("30.000")
        assert order.total_amount == Decimal("29.998")

    def test_total_has_a_cap(self, no_active_tenant):
        lines = [_money_line(price="500000000000"), _money_line(price="500000000000")]
        order = _money_order(lines)
        with pytest.raises(ValueError, match="إجمالي الأمر"):
            MaintenanceService._recalculate_order_totals(order)

    def test_collected_money_cannot_exceed_the_total(self, no_active_tenant):
        order = _money_order([_money_line()], paid="100")
        with pytest.raises(ValueError, match="المبلغ المحصّل يتجاوز"):
            MaintenanceService._recalculate_order_totals(order)


# ── status and order discount ─────────────────────────────────────────────


class TestStatusAndDiscountGuards:
    def test_invalid_transition_is_refused(self, db_session, sample_tenant, sample_user, sample_warehouse):
        order = _real_order(db_session, sample_tenant, sample_user, sample_warehouse)
        with pytest.raises(ValueError, match="انتقال حالة"):
            MaintenanceService.transition_status(
                order.id, sample_tenant.id, to_status="ready", changed_by=sample_user.id
            )

    def test_discount_on_a_closed_order_is_refused(self, db_session, sample_tenant, sample_user, sample_warehouse):
        order = _real_order(db_session, sample_tenant, sample_user, sample_warehouse, status="closed")
        with pytest.raises(ValueError, match="منتهٍ"):
            MaintenanceService.set_order_discount(
                order.id,
                sample_tenant.id,
                actor_id=sample_user.id,
                discount_percent=Decimal("10"),
                discount_value=Decimal("0"),
                discount_mode="percent",
            )

    def test_discount_on_an_archived_order_is_refused(self, db_session, sample_tenant, sample_user, sample_warehouse):
        order = _real_order(db_session, sample_tenant, sample_user, sample_warehouse)
        order.is_archived = True
        db_session.flush()
        with pytest.raises(ValueError, match="مؤرشف"):
            MaintenanceService.set_order_discount(
                order.id,
                sample_tenant.id,
                actor_id=sample_user.id,
                discount_percent=Decimal("10"),
                discount_value=Decimal("0"),
                discount_mode="percent",
            )

    @pytest.mark.parametrize(
        "kwargs, message",
        [
            ({"discount_percent": Decimal("NaN")}, "الخصم الإجمالي غير صالح"),
            ({"discount_percent": Decimal("101")}, "بين 0 و 100"),
            ({"discount_value": Decimal("-1")}, "سالبة"),
            ({"discount_percent": Decimal("10"), "discount_value": Decimal("5")}, "نوع خصم إجمالي واحد"),
            ({"discount_mode": "bogus"}, "نوع الخصم غير صالح"),
            ({"discount_mode": "percent", "discount_value": Decimal("5")}, "نوع خصم إجمالي واحد"),
            ({"discount_mode": "value", "discount_percent": Decimal("10")}, "نوع خصم إجمالي واحد"),
        ],
    )
    def test_invalid_discount_payloads_are_refused(
        self, db_session, sample_tenant, sample_user, sample_warehouse, kwargs, message
    ):
        order = _real_order(db_session, sample_tenant, sample_user, sample_warehouse)
        payload = {
            "discount_percent": Decimal("0"),
            "discount_value": Decimal("0"),
            "discount_mode": "percent",
        }
        payload.update(kwargs)
        with pytest.raises(ValueError, match=message):
            MaintenanceService.set_order_discount(order.id, sample_tenant.id, actor_id=sample_user.id, **payload)


# ── refund ────────────────────────────────────────────────────────────────


def _credit_order(db_session, tenant, user, warehouse, customer):
    """A closed order with a return and a cash receipt behind a credit balance."""
    order = _real_order(db_session, tenant, user, warehouse, customer=customer, status="closed")
    tag = uuid4().hex[:10]
    db_session.add(
        MaintenanceReturn(
            tenant_id=tenant.id,
            order_id=order.id,
            return_number=f"MR-COV-{tag}",
            returned_by=user.id,
            total_value=Decimal("30"),
            total_value_aed=Decimal("30"),
            posted=True,
        )
    )
    db_session.add(
        MaintenanceReceipt(
            tenant_id=tenant.id,
            order_id=order.id,
            receipt_number=f"PT-COV-{tag}",
            amount=Decimal("100"),
            payment_mode="cash",
            cashier_id=user.id,
        )
    )
    db_session.flush()
    return order


class TestRefundCredit:
    @pytest.fixture(autouse=True)
    def gl(self, mocker):
        mocker.patch("services.maintenance_order_service.MaintenanceGLService.post_refund")

    def test_refund_pays_the_credit_and_records_the_receipt(
        self, db_session, sample_tenant, sample_user, sample_warehouse, sample_customer
    ):
        order = _credit_order(db_session, sample_tenant, sample_user, sample_warehouse, sample_customer)
        receipt = MaintenanceService.refund_credit(
            order.id,
            sample_tenant.id,
            cashier_id=sample_user.id,
            payment_mode="cash",
            notes="coverage",
        )
        assert receipt.is_refund is True
        assert receipt.amount == Decimal("30.000")
        assert order.refunded_amount == Decimal("30.000")
        assert sample_customer.balance is not None

    def test_archived_order_cannot_be_refunded(
        self, db_session, sample_tenant, sample_user, sample_warehouse, sample_customer
    ):
        order = _credit_order(db_session, sample_tenant, sample_user, sample_warehouse, sample_customer)
        order.is_archived = True
        db_session.flush()
        with pytest.raises(ValueError, match="مؤرشف"):
            MaintenanceService.refund_credit(order.id, sample_tenant.id, cashier_id=sample_user.id)

    def test_no_credit_means_no_refund(self, db_session, sample_tenant, sample_user, sample_warehouse):
        order = _real_order(db_session, sample_tenant, sample_user, sample_warehouse, status="closed")
        with pytest.raises(ValueError, match="رصيد دائن"):
            MaintenanceService.refund_credit(order.id, sample_tenant.id, cashier_id=sample_user.id)

    @pytest.mark.parametrize("mode", ["gold_bar", "account", ""])
    def test_unsupported_refund_mode(
        self, db_session, sample_tenant, sample_user, sample_warehouse, sample_customer, mode
    ):
        order = _credit_order(db_session, sample_tenant, sample_user, sample_warehouse, sample_customer)
        with pytest.raises(ValueError, match="طريقة دفع غير مدعومة"):
            MaintenanceService.refund_credit(order.id, sample_tenant.id, cashier_id=sample_user.id, payment_mode=mode)

    @pytest.mark.parametrize("amount", [Decimal("0"), Decimal("-1")])
    def test_refund_amount_must_be_positive(
        self, db_session, sample_tenant, sample_user, sample_warehouse, sample_customer, amount
    ):
        order = _credit_order(db_session, sample_tenant, sample_user, sample_warehouse, sample_customer)
        with pytest.raises(ValueError, match="أكبر من صفر"):
            MaintenanceService.refund_credit(order.id, sample_tenant.id, cashier_id=sample_user.id, amount=amount)

    def test_refund_cannot_exceed_the_credit(
        self, db_session, sample_tenant, sample_user, sample_warehouse, sample_customer
    ):
        order = _credit_order(db_session, sample_tenant, sample_user, sample_warehouse, sample_customer)
        with pytest.raises(ValueError, match="يتجاوز الرصيد الدائن"):
            MaintenanceService.refund_credit(
                order.id, sample_tenant.id, cashier_id=sample_user.id, amount=Decimal("40")
            )

    def test_cashier_must_exist(self, db_session, sample_tenant, sample_user, sample_warehouse, sample_customer):
        order = _credit_order(db_session, sample_tenant, sample_user, sample_warehouse, sample_customer)
        with pytest.raises(ValueError, match="موظف الاستقبال غير موجود"):
            MaintenanceService.refund_credit(order.id, sample_tenant.id, cashier_id=999999)


# ── Warranty delegation ───────────────────────────────────────────────────


class TestWarrantyDelegation:
    def test_cancel_delegates_to_the_warranty_service(self, mocker):
        result = SimpleNamespace(action="cancelled")
        cancel = mocker.patch(
            "services.maintenance_warranty_service.WarrantyService.cancel_warranty", return_value=result
        )
        assert MaintenanceService.cancel_warranty(3, 4, performed_by=5, reason="damage") is result
        cancel.assert_called_once_with(3, 4, performed_by=5, reason="damage")

    def test_restore_delegates_to_the_warranty_service(self, mocker):
        result = SimpleNamespace(action="restored")
        restore = mocker.patch(
            "services.maintenance_warranty_service.WarrantyService.restore_warranty", return_value=result
        )
        assert MaintenanceService.restore_warranty(3, 4, performed_by=5, reason="reversed") is result
        restore.assert_called_once_with(3, 4, performed_by=5, reason="reversed")


# ── close and collect ─────────────────────────────────────────────────────


class TestCloseGuards:
    @pytest.fixture(autouse=True)
    def boundaries(self, mocker):
        mocker.patch("services.maintenance_order_service.MaintenanceGLService.post_parts_cost")
        mocker.patch("services.maintenance_order_service.MaintenanceGLService.post_invoice")
        mocker.patch("services.maintenance_order_service.MaintenanceGLService.post_receipt")
        mocker.patch("services.maintenance_order_service.MaintenanceGLService.post_deposit_application")
        mocker.patch("services.maintenance_order_service.MaintenanceStockService.consume_parts_for_order_line")
        mocker.patch("services.maintenance_order_service._generate_maintenance_einvoice")

    def _ready(self, db_session, tenant, user, warehouse, *, total="100"):
        order = _real_order(db_session, tenant, user, warehouse, status="ready")
        order.total_amount = Decimal(total)
        order.amount = Decimal(total)
        order.subtotal = Decimal(total)
        order.amount_aed = Decimal(total)
        db_session.flush()
        return order

    def test_archived_order_cannot_close(self, db_session, sample_tenant, sample_user, sample_warehouse):
        order = self._ready(db_session, sample_tenant, sample_user, sample_warehouse)
        order.is_archived = True
        db_session.flush()
        with pytest.raises(ValueError, match="مؤرشف"):
            MaintenanceService.close_and_collect(
                order.id, sample_tenant.id, cashier_id=sample_user.id, payment_mode="cash"
            )

    def test_order_with_an_invoice_cannot_close_again(self, db_session, sample_tenant, sample_user, sample_warehouse):
        order = self._ready(db_session, sample_tenant, sample_user, sample_warehouse)
        db_session.add(
            MaintenanceInvoice(
                tenant_id=sample_tenant.id,
                order_id=order.id,
                invoice_number=f"MINV-COV-{uuid4().hex[:8]}",
                total_amount=Decimal("100"),
                amount=Decimal("100"),
                amount_aed=Decimal("100"),
                currency="AED",
                base_currency="AED",
                exchange_rate=Decimal("1"),
            )
        )
        db_session.flush()
        with pytest.raises(ValueError, match="فاتورة مسبقاً"):
            MaintenanceService.close_and_collect(
                order.id, sample_tenant.id, cashier_id=sample_user.id, payment_mode="cash"
            )

    def test_cashier_must_exist(self, db_session, sample_tenant, sample_user, sample_warehouse):
        order = self._ready(db_session, sample_tenant, sample_user, sample_warehouse)
        with pytest.raises(ValueError, match="موظف الاستقبال غير موجود"):
            MaintenanceService.close_and_collect(order.id, sample_tenant.id, cashier_id=999999, payment_mode="cash")

    def test_zero_value_order_cannot_close(self, db_session, sample_tenant, sample_user, sample_warehouse):
        order = self._ready(db_session, sample_tenant, sample_user, sample_warehouse, total="0")
        with pytest.raises(ValueError, match="قيمته صفر"):
            MaintenanceService.close_and_collect(
                order.id, sample_tenant.id, cashier_id=sample_user.id, payment_mode="cash"
            )

    def test_negative_collection_is_refused(self, db_session, sample_tenant, sample_user, sample_warehouse):
        order = self._ready(db_session, sample_tenant, sample_user, sample_warehouse)
        with pytest.raises(ValueError, match="سالباً"):
            MaintenanceService.close_and_collect(
                order.id,
                sample_tenant.id,
                cashier_id=sample_user.id,
                payment_mode="cash",
                amount_received=Decimal("-1"),
            )

    def test_over_settled_order_cannot_close(self, db_session, sample_tenant, sample_user, sample_warehouse):
        order = self._ready(db_session, sample_tenant, sample_user, sample_warehouse)
        order.paid_amount = Decimal("200")
        db_session.flush()
        with pytest.raises(ValueError, match="المحصّل مسبقاً"):
            MaintenanceService.close_and_collect(
                order.id, sample_tenant.id, cashier_id=sample_user.id, payment_mode="cash"
            )

    def test_archived_and_already_issued_lines_are_skipped(
        self, db_session, sample_tenant, sample_user, sample_warehouse, sample_product
    ):
        order = _real_order(db_session, sample_tenant, sample_user, sample_warehouse)
        first = MaintenanceService.add_line(
            order.id,
            sample_tenant.id,
            product_id=sample_product.id,
            quantity=Decimal("1"),
            unit_price=Decimal("100"),
            warehouse_id=sample_warehouse.id,
            actor_id=sample_user.id,
        )
        second_product = Product(
            tenant_id=sample_tenant.id,
            name="Second Coverage Part",
            sku=f"COV-{uuid4().hex[:8]}",
            cost_price=Decimal("50"),
            regular_price=Decimal("100"),
            current_stock=Decimal("100"),
        )
        db_session.add(second_product)
        db_session.flush()
        second = MaintenanceService.add_line(
            order.id,
            sample_tenant.id,
            product_id=second_product.id,
            quantity=Decimal("1"),
            unit_price=Decimal("100"),
            warehouse_id=sample_warehouse.id,
            actor_id=sample_user.id,
        )
        first.is_archived = True
        movement = StockMovement(
            tenant_id=sample_tenant.id,
            product_id=second_product.id,
            warehouse_id=sample_warehouse.id,
            movement_type="adjustment",
            quantity=Decimal("0"),
            user_id=sample_user.id,
        )
        db_session.add(movement)
        db_session.flush()
        second.movement_id = movement.id
        order.status = "ready"
        order.total_amount = Decimal("100")
        order.amount = Decimal("100")
        db_session.flush()

        closed, receipt, invoice = MaintenanceService.close_and_collect(
            order.id, sample_tenant.id, cashier_id=sample_user.id, payment_mode="cash"
        )
        assert closed.status == "closed"
        assert receipt is not None
        assert invoice.order_id == order.id

    def test_account_sale_creates_no_receipt(self, db_session, sample_tenant, sample_user, sample_warehouse):
        order = self._ready(db_session, sample_tenant, sample_user, sample_warehouse)
        closed, receipt, invoice = MaintenanceService.close_and_collect(
            order.id,
            sample_tenant.id,
            cashier_id=sample_user.id,
            payment_mode="account",
            amount_received=Decimal("100"),
        )
        assert receipt is None
        assert closed.status == "closed"
        assert invoice.balance_due == Decimal("100.000")


class TestDepositGuards:
    def _ready(self, db_session, tenant, user, warehouse):
        return _real_order(db_session, tenant, user, warehouse, status="ready")

    def test_closed_order_cannot_take_a_deposit(self, db_session, sample_tenant, sample_user, sample_warehouse):
        order = _real_order(db_session, sample_tenant, sample_user, sample_warehouse, status="closed")
        with pytest.raises(ValueError, match="منتهٍ"):
            MaintenanceService.collect_deposit(
                order.id, sample_tenant.id, cashier_id=sample_user.id, amount=Decimal("10")
            )

    def test_archived_order_cannot_take_a_deposit(self, db_session, sample_tenant, sample_user, sample_warehouse):
        order = self._ready(db_session, sample_tenant, sample_user, sample_warehouse)
        order.is_archived = True
        db_session.flush()
        with pytest.raises(ValueError, match="مؤرشف"):
            MaintenanceService.collect_deposit(
                order.id, sample_tenant.id, cashier_id=sample_user.id, amount=Decimal("10")
            )

    @pytest.mark.parametrize("mode", ["gold_bar", "account"])
    def test_deposit_mode_must_be_a_real_payment(self, db_session, sample_tenant, sample_user, sample_warehouse, mode):
        order = self._ready(db_session, sample_tenant, sample_user, sample_warehouse)
        with pytest.raises(ValueError, match="طريقة دفع غير مدعومة|على حساب"):
            MaintenanceService.collect_deposit(
                order.id, sample_tenant.id, cashier_id=sample_user.id, amount=Decimal("10"), payment_mode=mode
            )

    def test_zero_deposit_is_refused(self, db_session, sample_tenant, sample_user, sample_warehouse):
        order = self._ready(db_session, sample_tenant, sample_user, sample_warehouse)
        with pytest.raises(ValueError, match="أكبر من صفر"):
            MaintenanceService.collect_deposit(
                order.id, sample_tenant.id, cashier_id=sample_user.id, amount=Decimal("0")
            )

    def test_cashier_must_exist_for_a_deposit(self, db_session, sample_tenant, sample_user, sample_warehouse):
        order = self._ready(db_session, sample_tenant, sample_user, sample_warehouse)
        with pytest.raises(ValueError, match="موظف الاستقبال غير موجود"):
            MaintenanceService.collect_deposit(order.id, sample_tenant.id, cashier_id=999999, amount=Decimal("10"))


class TestReceiptCreationGuards:
    def test_unpriced_order_has_no_balance_to_check(self, db_session, sample_tenant, sample_user, sample_warehouse):
        order = _real_order(db_session, sample_tenant, sample_user, sample_warehouse)
        receipt = MaintenanceService._create_receipt(order, sample_user.id, Decimal("10"), "cash", None)
        assert receipt.amount == Decimal("10")
        assert order.deposit_amount == Decimal("0")

    def test_overcollection_is_refused(self, db_session, sample_tenant, sample_user, sample_warehouse):
        order = _real_order(db_session, sample_tenant, sample_user, sample_warehouse)
        order.total_amount = Decimal("10")
        order.paid_amount = Decimal("100")
        db_session.flush()
        with pytest.raises(ValueError, match="المبلغ المحصّل يتجاوز"):
            MaintenanceService._create_receipt(order, sample_user.id, Decimal("1"), "cash", None)


# ── returns ───────────────────────────────────────────────────────────────


class TestReturnGuards:
    def _closed(self, db_session, tenant, user, warehouse):
        return _real_order(db_session, tenant, user, warehouse, status="closed")

    def test_only_a_closed_order_can_be_returned(self, db_session, sample_tenant, sample_user, sample_warehouse):
        order = _real_order(db_session, sample_tenant, sample_user, sample_warehouse)
        with pytest.raises(ValueError, match="أمر مغلق ومفوتر"):
            MaintenanceService.create_return(
                order.id,
                sample_tenant.id,
                returned_by=sample_user.id,
                reason="x",
                quantities={"return_qty_1": Decimal("1")},
            )

    def test_archived_order_cannot_be_returned(self, db_session, sample_tenant, sample_user, sample_warehouse):
        order = self._closed(db_session, sample_tenant, sample_user, sample_warehouse)
        order.is_archived = True
        db_session.flush()
        with pytest.raises(ValueError, match="مؤرشف"):
            MaintenanceService.create_return(
                order.id,
                sample_tenant.id,
                returned_by=sample_user.id,
                reason="x",
                quantities={"return_qty_1": Decimal("1")},
            )

    def test_user_must_exist(self, db_session, sample_tenant, sample_user, sample_warehouse):
        order = self._closed(db_session, sample_tenant, sample_user, sample_warehouse)
        with pytest.raises(ValueError, match="المستخدم المنفّذ غير موجود"):
            MaintenanceService.create_return(
                order.id,
                sample_tenant.id,
                returned_by=999999,
                reason="x",
                quantities={"return_qty_1": Decimal("1")},
            )

    def test_empty_quantities_are_refused(self, db_session, sample_tenant, sample_user, sample_warehouse):
        order = self._closed(db_session, sample_tenant, sample_user, sample_warehouse)
        with pytest.raises(ValueError, match="كمية للإرجاع"):
            MaintenanceService.create_return(
                order.id, sample_tenant.id, returned_by=sample_user.id, reason="x", quantities={}
            )

    def test_archived_lines_are_not_returnable(
        self, db_session, sample_tenant, sample_user, sample_warehouse, sample_product
    ):
        order = _real_order(db_session, sample_tenant, sample_user, sample_warehouse)
        line = MaintenanceService.add_line(
            order.id,
            sample_tenant.id,
            product_id=sample_product.id,
            quantity=Decimal("1"),
            unit_price=Decimal("100"),
            warehouse_id=sample_warehouse.id,
            actor_id=sample_user.id,
        )
        line.is_archived = True
        order.status = "closed"
        db_session.flush()
        with pytest.raises(ValueError, match="كميات صالحة"):
            MaintenanceService.create_return(
                order.id,
                sample_tenant.id,
                returned_by=sample_user.id,
                reason="x",
                quantities={f"return_qty_{line.id}": Decimal("1")},
            )

    @pytest.mark.parametrize("qty", [Decimal("0"), Decimal("-1")])
    def test_non_positive_quantities_are_skipped(
        self, db_session, sample_tenant, sample_user, sample_warehouse, sample_product, qty
    ):
        order = _real_order(db_session, sample_tenant, sample_user, sample_warehouse)
        line = MaintenanceService.add_line(
            order.id,
            sample_tenant.id,
            product_id=sample_product.id,
            quantity=Decimal("1"),
            unit_price=Decimal("100"),
            warehouse_id=sample_warehouse.id,
            actor_id=sample_user.id,
        )
        order.status = "closed"
        db_session.flush()
        with pytest.raises(ValueError, match="كميات صالحة"):
            MaintenanceService.create_return(
                order.id,
                sample_tenant.id,
                returned_by=sample_user.id,
                reason="x",
                quantities={f"return_qty_{line.id}": qty},
            )

    def test_return_cannot_exceed_the_remaining_quantity(
        self, db_session, sample_tenant, sample_user, sample_warehouse, sample_product
    ):
        order = _real_order(db_session, sample_tenant, sample_user, sample_warehouse)
        line = MaintenanceService.add_line(
            order.id,
            sample_tenant.id,
            product_id=sample_product.id,
            quantity=Decimal("1"),
            unit_price=Decimal("100"),
            warehouse_id=sample_warehouse.id,
            actor_id=sample_user.id,
        )
        order.status = "closed"
        db_session.flush()
        with pytest.raises(ValueError, match="تتجاوز الكمية المتبقية"):
            MaintenanceService.create_return(
                order.id,
                sample_tenant.id,
                returned_by=sample_user.id,
                reason="x",
                quantities={f"return_qty_{line.id}": Decimal("2")},
            )


# ── templates and settings ────────────────────────────────────────────────


class TestServiceTemplateGuards:
    def _template(self, **overrides):
        values = {
            "service_code": "SVC-1",
            "name": "Service",
            "name_ar": None,
            "service_category": "other",
            "fixed_price": Decimal("10"),
            "duration_minutes": 10,
            "tax_rate": Decimal("5"),
            "requires_parts": False,
            "sort_order": 1,
        }
        values.update(overrides)
        return values

    @pytest.mark.parametrize("field, bad", [("service_code", ""), ("name", "")])
    def test_code_and_name_are_required(self, no_active_tenant, field, bad):
        with pytest.raises(ValueError, match="مطلوبان"):
            MaintenanceService.create_service_template(1, **self._template(**{field: bad}))

    def test_code_length_is_limited(self, no_active_tenant):
        with pytest.raises(ValueError, match="طويل جداً"):
            MaintenanceService.create_service_template(1, **self._template(service_code="X" * 51))

    def test_price_cannot_be_negative(self, no_active_tenant):
        with pytest.raises(ValueError, match="سالباً"):
            MaintenanceService.create_service_template(1, **self._template(fixed_price=Decimal("-1")))

    def test_duration_cannot_be_negative(self, no_active_tenant):
        with pytest.raises(ValueError, match="سالبة"):
            MaintenanceService.create_service_template(1, **self._template(duration_minutes=-1))

    def test_duplicate_code_is_refused(self, mocker, queries, no_active_tenant):
        queries({MaintenanceServiceTemplate: _q(mocker, first=mocker.MagicMock())})
        with pytest.raises(ValueError, match="مستخدم مسبقاً"):
            MaintenanceService.create_service_template(1, **self._template())


class TestSettingsGuards:
    def test_valid_warehouse_is_saved(self, db_session, sample_tenant, sample_warehouse):
        setting = MaintenanceService.update_settings(sample_tenant.id, default_warehouse_id=sample_warehouse.id)
        assert setting.default_warehouse_id == sample_warehouse.id

    def test_missing_warehouse_is_refused(self, db_session, sample_tenant):
        with pytest.raises(ValueError, match="المستودع غير موجود"):
            MaintenanceService.update_settings(sample_tenant.id, default_warehouse_id=999999)

    def test_discount_cap_bounds(self, db_session, sample_tenant):
        with pytest.raises(ValueError, match="بين 0 و 100"):
            MaintenanceService.update_settings(sample_tenant.id, max_discount_percent=101)
        with pytest.raises(ValueError, match="سالباً"):
            MaintenanceService.update_settings(sample_tenant.id, max_discount_value=-1)

    def test_hourly_rate_cannot_be_negative(self, db_session, sample_tenant):
        with pytest.raises(ValueError, match="سعر ساعة العمل"):
            MaintenanceService.update_settings(sample_tenant.id, engineer_hourly_rate=-1)


# ── reports ───────────────────────────────────────────────────────────────


class TestReports:
    @pytest.fixture(autouse=True)
    def currency(self, mocker):
        mocker.patch("services.maintenance_order_service.resolve_tenant_base_currency", return_value="AED")

    def _report_order(self, *, number, revenue, cost="0", minutes=0, engineer_id=None, with_engineer=False):
        return SimpleNamespace(
            id=int(number.split("-")[-1]),
            order_number=number,
            order_date=None,
            customer_name="Workshop Customer",
            status="closed",
            taxable_amount=Decimal(revenue),
            lines=[
                SimpleNamespace(is_archived=False, cost_aed=Decimal(cost)),
                SimpleNamespace(is_archived=True, cost_aed=Decimal("999")),
            ],
            services_lines=[
                SimpleNamespace(is_archived=False, duration_minutes=minutes),
                SimpleNamespace(is_archived=True, duration_minutes=999),
            ],
            engineer_id=engineer_id,
            engineer=SimpleNamespace(full_name="Engineer One") if with_engineer else None,
        )

    @pytest.mark.parametrize("with_dates", [True, False])
    def test_revenue_report_filters_by_date(self, mocker, queries, no_active_tenant, with_dates):
        invoice = SimpleNamespace(
            currency="USD",
            exchange_rate=Decimal("2"),
            total_amount=Decimal("110"),
            tax_amount=Decimal("10"),
            paid_amount=Decimal("100"),
            balance_due=Decimal("10"),
            invoice_number="MINV-1",
            invoice_date=datetime(2026, 5, 1, tzinfo=UTC),
            order=SimpleNamespace(order_number="MO-1", customer_name="Customer"),
        )
        queries({MaintenanceInvoice: _q(mocker, rows=[invoice])})
        start = datetime(2026, 5, 1, tzinfo=UTC) if with_dates else None
        end = datetime(2026, 5, 31, tzinfo=UTC) if with_dates else None
        report = MaintenanceService.get_revenue_report(1, date_from=start, date_to=end)
        assert report["invoice_count"] == 1
        assert report["total_revenue"] == Decimal("200.000")
        assert report["invoices"][0]["order_number"] == "MO-1"

    @pytest.mark.parametrize("with_dates", [True, False])
    def test_margin_report_prices_parts_and_labour(self, mocker, queries, no_active_tenant, with_dates):
        orders = [
            self._report_order(number="MO-1", revenue="100", cost="20", minutes=90, engineer_id=3, with_engineer=True),
            self._report_order(number="MO-2", revenue="0"),
        ]
        queries(
            {
                MaintenanceOrder: _q(mocker, rows=orders),
                MaintenanceSetting: _q(mocker, first=SimpleNamespace(engineer_hourly_rate=Decimal("60"))),
            }
        )
        start = datetime(2026, 5, 1, tzinfo=UTC) if with_dates else None
        end = datetime(2026, 5, 31, tzinfo=UTC) if with_dates else None
        report = MaintenanceService.get_margin_report(1, date_from=start, date_to=end)
        assert report["order_count"] == 2
        assert report["total_parts_cost"] == Decimal("20.000")
        assert report["total_labour_cost"] == Decimal("90.000")
        first, second = report["orders"]
        assert first["margin"] == Decimal("-10.000")
        assert first["engineer_name"] == "Engineer One"
        assert second["margin_percent"] == Decimal("0")

    @pytest.mark.parametrize("with_dates", [True, False])
    def test_engineer_report_groups_assigned_and_unassigned_work(self, mocker, queries, no_active_tenant, with_dates):
        orders = [
            self._report_order(number="MO-1", revenue="100", cost="20", minutes=90, engineer_id=3, with_engineer=True),
            self._report_order(number="MO-2", revenue="50", cost="10", minutes=30),
            self._report_order(number="MO-3", revenue="0", engineer_id=4),
        ]
        queries({MaintenanceOrder: _q(mocker, rows=orders)})
        start = datetime(2026, 5, 1, tzinfo=UTC) if with_dates else None
        end = datetime(2026, 5, 31, tzinfo=UTC) if with_dates else None
        report = MaintenanceService.get_engineer_report(1, date_from=start, date_to=end)
        assert report["order_count"] == 3
        assert report["engineer_count"] == 2
        unassigned = next(row for row in report["engineers"] if row["engineer_id"] is None)
        assert unassigned["order_count"] == 1
        assert unassigned["minutes"] == 30
        zero = next(row for row in report["engineers"] if row["engineer_id"] == 4)
        assert zero["margin_percent"] == Decimal("0")

    def test_engineer_report_omits_the_unassigned_bucket_when_empty(self, mocker, queries, no_active_tenant):
        queries(
            {
                MaintenanceOrder: _q(
                    mocker,
                    rows=[self._report_order(number="MO-9", revenue="100", engineer_id=3, with_engineer=True)],
                )
            }
        )
        report = MaintenanceService.get_engineer_report(1, date_from=None, date_to=None)
        assert report["engineer_count"] == 1
        assert all(row["engineer_id"] is not None for row in report["engineers"])

    @pytest.mark.parametrize("with_dates", [True, False])
    def test_parts_report_skips_lines_without_an_order(self, mocker, queries, no_active_tenant, with_dates):
        lines = [
            SimpleNamespace(
                product_id=1,
                product=SimpleNamespace(name="Brake Pad", sku="BP-1"),
                order=SimpleNamespace(order_number="MO-1"),
                quantity=Decimal("2"),
                cost_aed=Decimal("8"),
            ),
            SimpleNamespace(
                product_id=2,
                product=None,
                order=None,
                quantity=Decimal("1"),
                cost_aed=Decimal("3"),
            ),
        ]
        queries({MaintenanceOrderLine: _q(mocker, rows=lines)})
        start = datetime(2026, 5, 1, tzinfo=UTC) if with_dates else None
        end = datetime(2026, 5, 31, tzinfo=UTC) if with_dates else None
        report = MaintenanceService.get_parts_report(1, date_from=start, date_to=end)
        assert report["line_count"] == 2
        assert report["total_quantity"] == Decimal("3")
        assert report["total_cost"] == Decimal("11")
        with_order = next(row for row in report["parts"] if row["product_id"] == 1)
        without_order = next(row for row in report["parts"] if row["product_id"] == 2)
        assert with_order["order_count"] == 1
        assert with_order["order_numbers"] == ["MO-1"]
        assert without_order["order_count"] == 0
