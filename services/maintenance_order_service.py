"""
وحدة الصيانة - خدمة الأعمال (Maintenance Service)

منطق الأعمال النقي لوحدة الصيانة: لا تحتوي على أي أكواد HTTP أوImports من المسارات.
جميع العمليات تستخدم atomic_transaction من db_safety، وكل قراءة/كتابة تمر عبر tenant_query.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, cast

from flask_babel import gettext

from extensions import db
from models import (
    Branch,
    Customer,
    MaintenanceDeviceRegistry,
    MaintenanceDiscountMode,
    MaintenanceInvoice,
    MaintenanceOrder,
    MaintenanceOrderLine,
    MaintenanceOrderService,
    MaintenanceOrderStatus,
    MaintenanceOrderStatusLog,
    MaintenanceOrderWarrantyStatus,
    MaintenanceReceipt,
    MaintenanceReturn,
    MaintenanceReturnLine,
    MaintenanceServiceTemplate,
    MaintenanceSetting,
    MaintenanceWarrantyAudit,
    Product,
    Sale,
    Tenant,
    User,
    Warehouse,
)
from services.document_sequence_service import DocumentSequenceService
from services.maintenance_gl_service import MaintenanceGLService
from services.maintenance_stock_service import MaintenanceStockService
from utils.currency_utils import (
    convert_and_quantize_aed,
    resolve_tenant_base_currency,
)
from utils.logger import log_financial
from utils.tax_settings import normalize_tax_rate
from utils.tenanting import (
    get_active_tenant_id,
    tenant_query,
)

logger = logging.getLogger(__name__)

_BASE_QUANTUM = Decimal("0.001")

#: The payment methods the reception counter can take. ``account`` means the
#: customer pays on account: the invoice is issued and the balance stays open
#: in the maintenance receivable, with no cash entry at all.
_PAYMENT_MODES = frozenset(
    {
        "cash",
        "card",
        "bank",
        "bank_transfer",
        "e_wallet",
        "cheque",
        "account",
    }
)


def _require_tenant_id(tenant_id: int | None) -> int:
    active = get_active_tenant_id()
    tid = tenant_id or active
    if tid is None or int(tid) <= 0:
        raise ValueError(gettext("معرف المستأجر مطلوب"))
    if active is not None and int(active) != int(tid):
        raise ValueError(gettext("معرف المستأجر غير صالح"))
    return int(tid)


_TRANSITIONS = {
    MaintenanceOrderStatus.RECEIVED: {
        MaintenanceOrderStatus.DIAGNOSIS,
        MaintenanceOrderStatus.ON_HOLD,
        MaintenanceOrderStatus.CANCELLED,
    },
    MaintenanceOrderStatus.DIAGNOSIS: {
        MaintenanceOrderStatus.WAITING_APPROVAL,
        MaintenanceOrderStatus.IN_PROGRESS,
        MaintenanceOrderStatus.ON_HOLD,
        MaintenanceOrderStatus.CANCELLED,
    },
    MaintenanceOrderStatus.WAITING_APPROVAL: {
        MaintenanceOrderStatus.IN_PROGRESS,
        MaintenanceOrderStatus.ON_HOLD,
        MaintenanceOrderStatus.CANCELLED,
    },
    MaintenanceOrderStatus.IN_PROGRESS: {
        MaintenanceOrderStatus.WAITING_PARTS,
        MaintenanceOrderStatus.READY,
        MaintenanceOrderStatus.ON_HOLD,
    },
    MaintenanceOrderStatus.WAITING_PARTS: {MaintenanceOrderStatus.IN_PROGRESS, MaintenanceOrderStatus.ON_HOLD},
    MaintenanceOrderStatus.ON_HOLD: {
        MaintenanceOrderStatus.DIAGNOSIS,
        MaintenanceOrderStatus.IN_PROGRESS,
        MaintenanceOrderStatus.WAITING_PARTS,
        MaintenanceOrderStatus.CANCELLED,
    },
    MaintenanceOrderStatus.READY: {
        MaintenanceOrderStatus.CLOSED,
        MaintenanceOrderStatus.IN_PROGRESS,
        MaintenanceOrderStatus.ON_HOLD,
    },
}


def _locked_order(order_id: int, tenant_id: int) -> MaintenanceOrder:
    order = (
        tenant_query(MaintenanceOrder)
        .filter_by(id=order_id, tenant_id=tenant_id)
        .populate_existing()
        .with_for_update()
        .first()
    )
    if order is None:
        raise ValueError(gettext("أمر الصيانة غير موجود"))
    return order


def _validate_line_values(quantity, unit_price, discount_percent, discount_value, discount_mode, tax_rate) -> None:
    try:
        values = [Decimal(str(value)) for value in (quantity, unit_price, discount_percent, discount_value, tax_rate)]
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(gettext("القيم المالية يجب أن تكون أرقاماً صالحة")) from exc
    qty, price, percent, value, rate = values
    if not all(number.is_finite() for number in values):
        raise ValueError(gettext("القيم المالية يجب أن تكون أرقاماً صالحة"))
    if qty <= 0 or price < 0 or not 0 <= rate <= 100:
        raise ValueError(gettext("الكمية أو السعر أو نسبة الضريبة غير صالحة"))
    if discount_mode not in (MaintenanceDiscountMode.PERCENT, MaintenanceDiscountMode.VALUE):
        raise ValueError(gettext("نوع الخصم غير صالح"))
    if not 0 <= percent <= 100 or not 0 <= value <= price:
        raise ValueError(gettext("قيمة الخصم غير صالحة"))
    if (discount_mode == MaintenanceDiscountMode.PERCENT and value) or (
        discount_mode == MaintenanceDiscountMode.VALUE and percent
    ):
        raise ValueError(gettext("يجب اختيار نوع خصم واحد فقط"))
    if qty > Decimal("999999999999.999") or price > Decimal("999999999999.999"):
        raise ValueError(gettext("الكمية أو السعر يتجاوز الحد المسموح"))
    if qty * price > Decimal("999999999999.999"):
        raise ValueError(gettext("إجمالي السطر يتجاوز الحد المسموح"))
    for number, quantum in zip(
        values, (_BASE_QUANTUM, _BASE_QUANTUM, Decimal("0.01"), _BASE_QUANTUM, Decimal("0.01")), strict=True
    ):
        if number != number.quantize(quantum):
            raise ValueError(gettext("عدد المنازل العشرية غير صالح"))


def _authorize_discount(tenant_id, actor_id, quantity, price, percent, value, mode) -> None:
    if not percent and not value:
        return
    actor = tenant_query(User).filter_by(id=actor_id, tenant_id=tenant_id, is_active=True).first() if actor_id else None
    if actor is None or not actor.has_permission("maintenance_discount"):
        raise ValueError(gettext("لا توجد صلاحية لتطبيق خصم الصيانة"))
    setting = tenant_query(MaintenanceSetting).filter_by(tenant_id=tenant_id).first()
    limit_percent = Decimal(str(setting.max_discount_percent if setting else 15))
    limit_value = Decimal(str((setting.max_discount_value if setting else 0) or 0))
    effective_percent = percent if mode == "percent" else (value / price * 100 if price else Decimal("0"))
    discount_value = quantity * (price * percent / 100 if mode == "percent" else value)
    if (
        effective_percent > limit_percent or (limit_value and discount_value > limit_value)
    ) and not actor.has_permission("maintenance_override_discount"):
        raise ValueError(gettext("الخصم يتجاوز الحد المسموح"))


def _validate_tax_rate(tenant_id: int, requested_rate, *, product: Product | None = None) -> Decimal:
    tenant = tenant_query(Tenant).filter_by(id=tenant_id).first()
    if tenant is None:
        raise ValueError(gettext("الشركة غير موجودة"))
    rate = normalize_tax_rate(None, tenant_id)
    if product and tenant.enable_tax_categories and product.tax_category in ("zero", "exempt"):
        rate = Decimal("0")
    if requested_rate is not None:
        try:
            requested = Decimal(str(requested_rate))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError(gettext("نسبة الضريبة غير صالحة")) from exc
        if not requested.is_finite() or requested != rate:
            raise ValueError(gettext("نسبة الضريبة لا تطابق إعدادات الشركة"))
    return rate


def _authorize_price_override(tenant_id, actor_id, requested_price, standard_price) -> None:
    if Decimal(str(requested_price)) == Decimal(str(standard_price)):
        return
    actor = tenant_query(User).filter_by(id=actor_id, tenant_id=tenant_id, is_active=True).first() if actor_id else None
    if actor is None or not actor.has_permission("maintenance_override_discount"):
        raise ValueError(gettext("لا توجد صلاحية لتغيير السعر المعتمد"))


def _require_pricing_currency(order: MaintenanceOrder, tenant_id: int) -> None:
    tenant = tenant_query(Tenant).filter_by(id=tenant_id).first()
    if tenant is None or order.currency != (tenant.default_currency or "").strip().upper():
        raise ValueError(gettext("تسعير الصيانة بعملة مختلفة غير متاح حتى اكتمال تحويل الأسعار"))


def _is_hex_color(value: str) -> bool:
    """A CSS hex colour - the warranty colour tags are used as inline styles."""
    if len(value) != 7 or not value.startswith("#"):
        return False
    return all(char in "0123456789abcdefABCDEF" for char in value[1:])


def _generate_maintenance_einvoice(invoice: MaintenanceInvoice) -> None:
    """Produce the statutory e-invoice of a maintenance invoice.

    The tenant's master switch decides whether a document is produced at
    all - a tenant that opted out gets none, and that is a documented
    choice, not a failure. A jurisdiction with no e-invoice profile
    produces no document either.

    Everything else propagates. The caller runs inside
    ``atomic_transaction``, so a failure (a ZATCA credential that is not
    stored, a broken document) rolls the close back rather than
    committing an invoice the customer is entitled to a document for.
    """
    from services.einvoice_service import EInvoiceService

    EInvoiceService.generate_for_maintenance_invoice(invoice)


class MaintenanceService:
    """خدمة الصيانة — منطق الأعمال النقي. لا تحتوي على أي مفاهيم HTTP."""

    # ── إنشاء أمر صيانة جديد ──
    @staticmethod
    def create_order(
        tenant_id: int,
        *,
        branch_id: int | None,
        warehouse_id: int | None,
        customer_id: int | None,
        customer_name: str | None,
        customer_phone: str | None,
        device_brand: str | None,
        device_model: str | None,
        device_serial_number: str | None,
        device_imei: str | None,
        device_plate: str | None,
        device_km: int | None,
        device_fault_description: str | None,
        received_by: int,
        warranty_sale_id: int | None = None,
        notes: str | None = None,
        currency: str | None = None,
        exchange_rate: Decimal | None = None,
        prices_include_vat: bool = False,
    ) -> MaintenanceOrder:
        """ينشئ أمر صيانة جديد بمستوى 'received' ورقم مستند تلقائي."""
        tid = _require_tenant_id(tenant_id)

        if branch_id and not tenant_query(Branch).filter_by(id=branch_id, tenant_id=tid, is_active=True).first():
            raise ValueError(gettext("الفرع غير موجود"))
        if warehouse_id:
            warehouse = tenant_query(Warehouse).filter_by(id=warehouse_id, tenant_id=tid, is_active=True).first()
            if not warehouse:
                raise ValueError(gettext("المستودع غير موجود"))
            if branch_id and warehouse.branch_id and int(branch_id) != warehouse.branch_id:
                raise ValueError(gettext("المستودع لا يتبع الفرع المحدد"))
            branch_id = branch_id or warehouse.branch_id
            if branch_id and not tenant_query(Branch).filter_by(id=branch_id, tenant_id=tid, is_active=True).first():
                raise ValueError(gettext("فرع المستودع غير صالح"))
        if customer_id and not tenant_query(Customer).filter_by(id=customer_id, tenant_id=tid, is_active=True).first():
            raise ValueError(gettext("العميل غير موجود"))
        if warranty_sale_id:
            sale = tenant_query(Sale).filter_by(id=warranty_sale_id, tenant_id=tid).first()
            if not sale or (customer_id and int(customer_id) != sale.customer_id):
                raise ValueError(gettext("فاتورة الضمان غير صالحة لهذا العميل"))
        if not tenant_query(User).filter_by(id=received_by, tenant_id=tid, is_active=True).first():
            raise ValueError(gettext("مستلم الجهاز غير موجود"))

        tenant = tenant_query(Tenant).filter_by(id=tid).first()
        if tenant is None:
            raise ValueError(gettext("الشركة غير موجودة"))
        currency = str(currency or tenant.default_currency or "").strip().upper()
        if len(currency) != 3 or not currency.isalpha() or not currency.isascii():
            raise ValueError(gettext("العملة غير صالحة"))
        try:
            rate = Decimal(str(exchange_rate if exchange_rate is not None else "1"))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError(gettext("سعر الصرف غير صالح")) from exc
        if not rate.is_finite() or rate <= 0 or rate > Decimal("999999999.999999"):
            raise ValueError(gettext("سعر الصرف غير صالح"))
        if rate != rate.quantize(Decimal("0.000001")):
            raise ValueError(gettext("دقة سعر الصرف غير صالحة"))
        base_currency = resolve_tenant_base_currency(tenant_id=tid)
        if currency != base_currency and exchange_rate is None:
            raise ValueError(gettext("سعر الصرف مطلوب للعملة الأجنبية"))
        if currency == base_currency and rate != 1:
            raise ValueError(gettext("سعر صرف عملة الأساس يجب أن يساوي واحداً"))

        # رقم الأمر عبر DocumentSequence (قفل صف)
        order_number = DocumentSequenceService.next_number(
            tenant_id=tid,
            code="maintenance_order",
            prefix="MN",
        )

        order = MaintenanceOrder(
            tenant_id=tid,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            order_number=order_number,
            customer_id=customer_id,
            customer_name=customer_name,
            customer_phone=customer_phone,
            device_brand=device_brand,
            device_model=device_model,
            device_serial_number=device_serial_number,
            device_imei=device_imei,
            device_plate=device_plate,
            device_km=device_km,
            device_fault_description=device_fault_description,
            received_by=received_by,
            warranty_sale_id=warranty_sale_id,
            notes=notes,
            currency=currency,
            exchange_rate=rate,
            base_currency=base_currency,
            prices_include_vat=prices_include_vat,
            status=MaintenanceOrderStatus.RECEIVED,
            color_tag="#f59e0b",
        )
        db.session.add(order)
        db.session.flush()

        # سجل الحالة الأولى
        log = MaintenanceOrderStatusLog(
            tenant_id=tid,
            order_id=order.id,
            from_status=None,
            to_status=MaintenanceOrderStatus.RECEIVED,
            changed_by=received_by,
            note=gettext("استلام الجهاز وإنشاء الأمر"),
        )
        db.session.add(log)
        db.session.flush()

        log_financial(
            message=f"Maintenance order created: {order_number}",
            tenant_id=tid,
            level="INFO",
            source="services.maintenance_service.MaintenanceOrder.create_order",
            extra={"order_id": order.id, "tenant_id": tid},
        )

        return order

    # ── إضافة سطر قطع إلى أمر الصيانة ──
    @staticmethod
    def add_line(
        order_id: int,
        tenant_id: int,
        *,
        product_id: int | None,
        quantity: Decimal,
        unit_price: Decimal,
        discount_percent: Decimal = Decimal("0"),
        discount_value: Decimal = Decimal("0"),
        discount_mode: str = MaintenanceDiscountMode.PERCENT,
        tax_rate: Decimal | None = None,
        warehouse_id: int | None,
        actor_id: int | None = None,
    ) -> MaintenanceOrderLine:
        """إضافة سطر قطع إلى أمر الصيانة مع خصم للسطر."""
        tid = _require_tenant_id(tenant_id)
        order = _locked_order(order_id, tid)
        if order.status not in (
            MaintenanceOrderStatus.RECEIVED,
            MaintenanceOrderStatus.DIAGNOSIS,
            MaintenanceOrderStatus.IN_PROGRESS,
        ):
            raise ValueError(gettext(f"لا يمكن إضافة قطع لأمر بحالة {order.status}"))

        _require_pricing_currency(order, tid)
        product = tenant_query(Product).filter_by(id=product_id, tenant_id=tid, is_active=True).first()
        if product is None:
            raise ValueError(gettext("المنتج غير موجود"))
        tax_rate = _validate_tax_rate(tid, tax_rate, product=product)
        _validate_line_values(quantity, unit_price, discount_percent, discount_value, discount_mode, tax_rate)
        _authorize_price_override(tid, actor_id, unit_price, product.regular_price)
        _authorize_discount(
            tid,
            actor_id,
            Decimal(str(quantity)),
            Decimal(str(unit_price)),
            Decimal(str(discount_percent)),
            Decimal(str(discount_value)),
            discount_mode,
        )
        warehouse_id = warehouse_id or order.warehouse_id
        warehouse = tenant_query(Warehouse).filter_by(id=warehouse_id, tenant_id=tid, is_active=True).first()
        if warehouse is None or (order.branch_id and warehouse.branch_id != order.branch_id):
            raise ValueError(gettext("المستودع غير صالح لأمر الصيانة"))

        line = MaintenanceOrderLine(
            tenant_id=tid,
            order_id=order_id,
            product_id=product_id,
            quantity=Decimal(str(quantity)),
            unit_price=Decimal(str(unit_price)),
            discount_percent=Decimal(str(discount_percent)),
            discount_value=Decimal(str(discount_value)),
            discount_mode=discount_mode,
            tax_rate=Decimal(str(tax_rate)),
            warehouse_id=warehouse_id,
        )
        db.session.add(line)
        db.session.flush()

        # إعادة حساب totals
        MaintenanceService._recalculate_order_totals(order)

        db.session.flush()
        return line

    # ── إضافة سطر خدمة إلى أمر الصيانة ──
    @staticmethod
    def add_service_line(
        order_id: int,
        tenant_id: int,
        *,
        service_code: str,
        service_name: str,
        service_name_ar: str | None,
        service_category: str,
        unit_price: Decimal,
        duration_minutes: int = 0,
        discount_percent: Decimal = Decimal("0"),
        discount_value: Decimal = Decimal("0"),
        discount_mode: str = MaintenanceDiscountMode.PERCENT,
        tax_rate: Decimal | None = None,
        engineer_id: int | None,
        actor_id: int | None = None,
    ) -> MaintenanceOrderService:
        """إضافة خدمة ثابتة السعر إلى أمر الصيانة."""
        tid = _require_tenant_id(tenant_id)
        order = _locked_order(order_id, tid)
        if order.status not in (
            MaintenanceOrderStatus.RECEIVED,
            MaintenanceOrderStatus.DIAGNOSIS,
            MaintenanceOrderStatus.IN_PROGRESS,
        ):
            raise ValueError(gettext("لا يمكن إضافة خدمات في حالة الأمر الحالية"))
        _require_pricing_currency(order, tid)
        template = (
            tenant_query(MaintenanceServiceTemplate)
            .filter_by(tenant_id=tid, service_code=service_code, is_active=True)
            .first()
        )
        if template is None:
            raise ValueError(gettext("قالب الخدمة غير موجود"))
        tax_rate = _validate_tax_rate(tid, tax_rate)
        _validate_line_values(1, unit_price, discount_percent, discount_value, discount_mode, tax_rate)
        _authorize_price_override(tid, actor_id, unit_price, template.fixed_price)
        _authorize_discount(
            tid,
            actor_id,
            Decimal("1"),
            Decimal(str(unit_price)),
            Decimal(str(discount_percent)),
            Decimal(str(discount_value)),
            discount_mode,
        )
        if engineer_id and not tenant_query(User).filter_by(id=engineer_id, tenant_id=tid, is_active=True).first():
            raise ValueError(gettext("المهندس غير موجود"))

        line = MaintenanceOrderService(
            tenant_id=tid,
            order_id=order_id,
            service_code=service_code,
            service_name=template.name,
            service_name_ar=template.name_ar,
            service_category=template.service_category,
            duration_minutes=template.duration_minutes,
            unit_price=Decimal(str(unit_price)),
            discount_percent=Decimal(str(discount_percent)),
            discount_value=Decimal(str(discount_value)),
            discount_mode=discount_mode,
            tax_rate=Decimal(str(tax_rate)),
            engineer_id=engineer_id,
        )
        db.session.add(line)
        db.session.flush()

        MaintenanceService._recalculate_order_totals(order)
        db.session.flush()
        return line

    @staticmethod
    def _recalculate_order_totals(order: MaintenanceOrder) -> None:
        """إعادة حساب totals الأمر من السطور والخصومات والضريبة."""

        def quantize(amount):
            return amount.quantize(_BASE_QUANTUM, rounding=ROUND_HALF_UP)

        entries = []
        gross_subtotal = Decimal("0")
        for line, qty in [
            (line, Decimal(str(line.quantity))) for line in cast(Any, order.lines) if not line.is_archived
        ] + [(line, Decimal("1")) for line in cast(Any, order.services_lines) if not line.is_archived]:
            price = Decimal(str(line.unit_price or 0))
            percent = Decimal(str(line.discount_percent or 0))
            value = Decimal(str(line.discount_value or 0))
            rate = Decimal(str(line.tax_rate or 0))
            _validate_line_values(qty, price, percent, value, line.discount_mode, rate)
            gross = quantize(qty * price)
            discount = quantize(qty * (price * percent / Decimal("100") if line.discount_mode == "percent" else value))
            line.line_total = gross - discount
            gross_subtotal += gross
            entries.append((line, line.line_total, rate))

        subtotal = sum((amount for _, amount, _ in entries), Decimal("0"))
        order.discount_line_total = gross_subtotal - subtotal
        percent = Decimal(str(order.discount_total_percent or 0))
        value = Decimal(str(order.discount_total_value or 0))
        if not percent.is_finite() or not value.is_finite() or not 0 <= percent <= 100 or value < 0:
            raise ValueError(gettext("الخصم الإجمالي غير صالح"))
        if percent and value:
            raise ValueError(gettext("يجب اختيار نوع خصم إجمالي واحد فقط"))
        discount = quantize(subtotal * percent / Decimal("100")) if percent else value
        if discount > subtotal or discount != quantize(discount):
            raise ValueError(gettext("الخصم الإجمالي يتجاوز قيمة الأمر"))

        # Allocate the aggregate discount across rates with the largest-remainder
        # method, so the exact rounded discount is applied once and only once.
        shares = [Decimal("0")] * len(entries)
        if discount and subtotal:
            raw = [discount * amount / subtotal for _, amount, _ in entries]
            shares = [part.quantize(_BASE_QUANTUM, rounding=ROUND_DOWN) for part in raw]
            remaining = int((discount - sum(shares, Decimal("0"))) / _BASE_QUANTUM)
            for index in sorted(range(len(raw)), key=lambda i: raw[i] - shares[i], reverse=True)[:remaining]:
                shares[index] += _BASE_QUANTUM

        tax = Decimal("0")
        taxable = Decimal("0")
        for (line, amount, rate), share in zip(entries, shares, strict=True):
            net = amount - share
            # The share of the order discount that landed on this line, and
            # the taxable amount that is left, are both stored on the line.
            # A return reverses a line, and it can only reverse what the
            # line actually carried: the order discount was allocated by
            # the largest-remainder method, so its share is not derivable
            # from the line total alone.
            if hasattr(line, "aggregate_discount"):
                line.aggregate_discount = share
            if order.prices_include_vat:
                # The tax is inside the price, so the revenue the line
                # carries is the price less the tax - the same figure the
                # order's taxable amount is built from.
                line.tax_amount = quantize(net * rate / (Decimal("100") + rate))
                line_taxable = net - line.tax_amount
            else:
                line.tax_amount = quantize(net * rate / Decimal("100"))
                line_taxable = net
            if hasattr(line, "taxable_amount"):
                line.taxable_amount = line_taxable
            tax += line.tax_amount
            taxable += line_taxable

        order.subtotal = subtotal
        order.taxable_amount = taxable
        order.tax_amount = tax
        # The rate the order was actually taxed at, derived from the amounts
        # rather than from a field nobody sets. The invoice copies this
        # rate onto its face, so a stale zero would print "Tax (0.00%)"
        # next to a real tax amount. Deriving it from the amounts keeps
        # the rate and the tax consistent whatever the lines carry -
        # including VAT-inclusive pricing, where the tax sits inside the
        # price.
        order.tax_rate = (
            (tax / taxable * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if taxable > 0
            else Decimal("0")
        )
        order.total_amount = subtotal - discount + (Decimal("0") if order.prices_include_vat else tax)
        if order.total_amount > Decimal("999999999999.999"):
            raise ValueError(gettext("إجمالي الأمر يتجاوز الحد المسموح"))
        order.amount = order.total_amount
        # What is still owed: the total less what the customer handed over,
        # counting the deposit that is being held. A deposit taken at
        # reception before the diagnosis can exceed the total that is known
        # so far, so the order is not refused for it - the close is where
        # the two are reconciled.
        settled = Decimal(str(order.paid_amount or 0)) + Decimal(str(order.deposit_amount or 0))
        order.balance_due = order.total_amount - settled
        if order.balance_due < 0 and order.total_amount > 0:
            raise ValueError(gettext("المبلغ المحصّل يتجاوز الإجمالي"))
        for source, target in (
            ("total_amount", "amount_aed"),
            ("paid_amount", "paid_amount_aed"),
            ("balance_due", "balance_due_aed"),
        ):
            setattr(
                order,
                target,
                convert_and_quantize_aed(
                    getattr(order, source) or 0, order.currency, order.exchange_rate, base_currency=order.base_currency
                ),
            )

    # ── تغيير حالة الأمر ──
    @staticmethod
    def transition_status(
        order_id: int,
        tenant_id: int,
        *,
        to_status: str,
        changed_by: int,
        note: str | None = None,
        allow_close: bool = False,
    ) -> MaintenanceOrder:
        """نقل حالة أمر الصيانة مع سجل التدقيق.

        ``allow_close`` exists for one caller only: the close-and-collect
        path, which is the one place that may close an order. The status
        screen cannot set it, so an order can never be closed by moving a
        status - only by invoicing and collecting it.
        """
        tid = _require_tenant_id(tenant_id)
        order = _locked_order(order_id, tid)
        if to_status == MaintenanceOrderStatus.CLOSED and not allow_close:
            raise ValueError(gettext("لا يمكن إغلاق الأمر من شاشة تغيير الحالة"))
        if to_status not in _TRANSITIONS.get(order.status, set()) or order.is_archived:
            raise ValueError(gettext("انتقال حالة الصيانة غير مسموح"))
        if to_status == MaintenanceOrderStatus.READY:
            setting = tenant_query(MaintenanceSetting).filter_by(tenant_id=tid).first()
            if (setting is None or setting.require_warranty_check) and not order.warranty_checked:
                raise ValueError(gettext("يجب فحص الكفالة قبل تجهيز الأمر"))

        from_status = order.status
        order.status = to_status

        log = MaintenanceOrderStatusLog(
            tenant_id=tid,
            order_id=order_id,
            from_status=from_status,
            to_status=to_status,
            changed_by=changed_by,
            note=note,
        )
        db.session.add(log)
        db.session.flush()

        log_financial(
            message=f"Maintenance order status changed: {order.order_number} {from_status} -> {to_status}",
            tenant_id=tid,
            level="INFO",
            source="services.maintenance_service.MaintenanceOrder.transition_status",
            extra={"order_id": order.id, "tenant_id": tid, "from_status": from_status, "to_status": to_status},
        )

        return order

    # ── الخصم الإجمالي على الأمر ──
    @staticmethod
    def set_order_discount(
        order_id: int,
        tenant_id: int,
        *,
        actor_id: int,
        discount_percent: Decimal,
        discount_value: Decimal,
        discount_mode: str,
        note: str | None = None,
    ) -> MaintenanceOrder:
        """تطبيق خصم إجمالي على أمر الصيانة.

        The order-level discount is the discount the customer is offered on
        the whole job, and it is the one that needs the most care: it can
        take the whole order to zero. So it needs the discount permission,
        it is capped by the tenant's settings, and going over the cap
        needs the override permission - exactly like a line discount.

        The discount is allocated over the lines by the largest-remainder
        method, so a return of one line reverses the share that line
        actually carried.
        """
        tid = _require_tenant_id(tenant_id)
        order = _locked_order(order_id, tid)
        if order.status in (MaintenanceOrderStatus.CLOSED, MaintenanceOrderStatus.CANCELLED):
            raise ValueError(gettext("لا يمكن تعديل خصم أمر منتهٍ"))
        if order.is_archived:
            raise ValueError(gettext("لا يمكن تعديل خصم أمر مؤرشف"))

        percent = Decimal(str(discount_percent or 0))
        value = Decimal(str(discount_value or 0))
        if not percent.is_finite() or not value.is_finite():
            raise ValueError(gettext("الخصم الإجمالي غير صالح"))
        if not 0 <= percent <= 100:
            raise ValueError(gettext("نسبة الخصم الإجمالي يجب أن تكون بين 0 و 100"))
        if value < 0:
            raise ValueError(gettext("قيمة الخصم الإجمالي لا يمكن أن تكون سالبة"))
        if percent and value:
            raise ValueError(gettext("يجب اختيار نوع خصم إجمالي واحد فقط"))

        mode = (discount_mode or "").strip().lower()
        if mode not in (MaintenanceDiscountMode.PERCENT, MaintenanceDiscountMode.VALUE):
            raise ValueError(gettext("نوع الخصم غير صالح"))
        if mode == MaintenanceDiscountMode.PERCENT and value:
            raise ValueError(gettext("يجب اختيار نوع خصم إجمالي واحد فقط"))
        if mode == MaintenanceDiscountMode.VALUE and percent:
            raise ValueError(gettext("يجب اختيار نوع خصم إجمالي واحد فقط"))

        actor = tenant_query(User).filter_by(id=actor_id, tenant_id=tid, is_active=True).first() if actor_id else None
        if actor is None or not actor.has_permission("maintenance_discount"):
            raise ValueError(gettext("لا توجد صلاحية لتطبيق خصم الصيانة"))

        setting = tenant_query(MaintenanceSetting).filter_by(tenant_id=tid).first()
        limit_percent = Decimal(str(setting.max_discount_percent if setting else 15))
        limit_value = Decimal(str((setting.max_discount_value if setting else 0) or 0))
        subtotal = Decimal(str(order.subtotal or 0))
        effective_percent = (
            percent
            if mode == MaintenanceDiscountMode.PERCENT
            else (value / subtotal * 100 if subtotal else Decimal("0"))
        )
        if (effective_percent > limit_percent or (limit_value and value > limit_value)) and (
            not actor.has_permission("maintenance_override_discount")
        ):
            raise ValueError(gettext("الخصم يتجاوز الحد المسموح"))

        order.discount_total_percent = percent if mode == MaintenanceDiscountMode.PERCENT else Decimal("0")
        order.discount_total_value = value if mode == MaintenanceDiscountMode.VALUE else Decimal("0")

        MaintenanceService._recalculate_order_totals(order)
        db.session.flush()

        log_financial(
            message=(
                f"Maintenance order discount set: {order.order_number} "
                f"percent={order.discount_total_percent} value={order.discount_total_value}"
            ),
            tenant_id=tid,
            level="INFO",
            source="services.maintenance_order_service.MaintenanceService.set_order_discount",
            extra={
                "order_id": order.id,
                "tenant_id": tid,
                "discount_percent": float(order.discount_total_percent or 0),
                "discount_value": float(order.discount_total_value or 0),
                "actor_id": actor_id,
                "note": note,
            },
        )

        return order

    # ── فحص الكفالة عند الاستلام ──
    @staticmethod
    def check_warranty(
        order_id: int,
        tenant_id: int,
        *,
        checked_by: int,
    ) -> MaintenanceOrder:
        """فحص حالة الكفالة للجهاز."""
        from services.maintenance_warranty_service import WarrantyService

        return WarrantyService.check_warranty_on_receipt(order_id, tenant_id, checked_by=checked_by)

    # ── إلغاء كفالة المنتج ──
    @staticmethod
    def cancel_warranty(
        order_id: int,
        tenant_id: int,
        *,
        performed_by: int,
        reason: str | None,
    ) -> MaintenanceWarrantyAudit:
        """إلغاء كفالة المنتج (يضعف الضمان)."""
        from services.maintenance_warranty_service import WarrantyService

        return WarrantyService.cancel_warranty(order_id, tenant_id, performed_by=performed_by, reason=reason)

    # ── إعادة تفعيل الكفالة ──
    @staticmethod
    def restore_warranty(
        order_id: int,
        tenant_id: int,
        *,
        performed_by: int,
        reason: str | None,
    ) -> MaintenanceWarrantyAudit:
        """إعادة تفعيل الكفالة."""
        from services.maintenance_warranty_service import WarrantyService

        return WarrantyService.restore_warranty(order_id, tenant_id, performed_by=performed_by, reason=reason)

    # ── إغلاق الأمر، قبض المبلغ، إصدار الفاتورة، ترحيل GL (الاستقبال فقط) ──
    @staticmethod
    def close_and_collect(
        order_id: int,
        tenant_id: int,
        *,
        cashier_id: int,
        payment_mode: str,
        amount_received: Decimal | None = None,
        payment_reference: str | None = None,
        notes: str | None = None,
        actor_id: int | None = None,
    ) -> tuple[MaintenanceOrder, MaintenanceReceipt, MaintenanceInvoice]:
        """إغلاق أمر الصيانة: صرف القطع، إصدار الفاتورة، القبض، وترحيل القيود.

        The whole thing is one unit of work: the caller owns the transaction
        boundary (``atomic_transaction`` in the route), and every step here
        only flushes. If any step fails - the stock is not there, the period
        is closed, a GL account is not mapped - nothing is committed, so a
        half-closed order with a receipt but no invoice cannot exist.
        """
        tid = _require_tenant_id(tenant_id)
        order = _locked_order(order_id, tid)
        if order.status != MaintenanceOrderStatus.READY:
            raise ValueError(gettext("لا يمكن إغلاق أمر غير جاهز للتسليم"))
        if order.is_archived:
            raise ValueError(gettext("لا يمكن إغلاق أمر مؤرشف"))
        if order.invoice is not None:
            raise ValueError(gettext("أمر الصيانة مُصدر له فاتورة مسبقاً"))

        if not tenant_query(User).filter_by(id=cashier_id, tenant_id=tid, is_active=True).first():
            raise ValueError(gettext("موظف الاستقبال غير موجود"))

        payment_mode = (payment_mode or "").strip().lower()
        if payment_mode not in _PAYMENT_MODES:
            raise ValueError(gettext("طريقة دفع غير مدعومة: {mode}").format(mode=payment_mode))

        total = Decimal(str(order.total_amount or 0))
        if total <= 0:
            raise ValueError(gettext("لا يمكن إغلاق أمر قيمته صفر"))

        amount_to_collect = Decimal(str(amount_received if amount_received is not None else total))
        if amount_to_collect < 0:
            raise ValueError(gettext("مبلغ القبض لا يمكن أن يكون سالباً"))
        if payment_mode == "account" and amount_to_collect > 0:
            # On account means no money changed hands: the balance stays open
            # in the maintenance receivable. A receipt would be a fiction.
            amount_to_collect = Decimal("0")

        # The deposit the customer already handed over is part of what has
        # been settled, so the cash collected now cannot exceed what is
        # still owed. Counting the deposit twice would let the counter
        # collect the whole invoice and a deposit on top of it.
        deposit = Decimal(str(order.deposit_amount or 0))
        settled = Decimal(str(order.paid_amount or 0)) + deposit
        outstanding = total - settled
        if outstanding < 0:
            raise ValueError(gettext("المبلغ المحصّل مسبقاً يتجاوز إجمالي الفاتورة"))
        if amount_to_collect > outstanding:
            raise ValueError(gettext("مبلغ القبض يتجاوز إجمالي الفاتورة"))

        # 1. The parts leave the shelf, each at its real moving-average cost.
        total_cost = Decimal("0")
        for line in list(cast(Any, order.lines)):
            if line.is_archived:
                continue
            if line.movement_id:
                # Already issued (the order was closed before and reversed).
                continue
            MaintenanceStockService.consume_parts_for_order_line(line, cashier_id)
            total_cost += Decimal(str(line.cost_aed or 0))

        # 2. The invoice: the document the customer is charged on. What it
        #    shows as settled is everything the customer has handed over:
        #    the cash collected now plus the deposit being held.
        invoice = MaintenanceService._create_invoice(order=order)
        db.session.flush()

        # 3. The receipt: the money that actually changed hands.
        receipt = None
        if amount_to_collect > 0:
            receipt = MaintenanceService._create_receipt(
                order=order,
                cashier_id=cashier_id,
                amount=amount_to_collect,
                payment_mode=payment_mode,
                reference_number=payment_reference,
            )

        # The invoice's settled figure is the deposit plus what was just
        # collected: both are money the customer handed over against this
        # invoice, and the balance due is what is left of it.
        invoice.paid_amount = settled + amount_to_collect
        invoice.balance_due = total - invoice.paid_amount
        if invoice.balance_due < 0:
            invoice.balance_due = Decimal("0")
        db.session.flush()

        # 4. The ledger. The parts cost first (it is the inventory movement),
        #    then the invoice, then the receipt, then the deposit that is
        #    applied against the invoice now that it exists.
        MaintenanceGLService.post_parts_cost(order, total_cost, cashier_id)
        MaintenanceGLService.post_invoice(invoice, cashier_id)
        if receipt is not None:
            MaintenanceGLService.post_receipt(receipt, cashier_id)
        MaintenanceGLService.post_deposit_application(order, cashier_id)

        # The statutory document: a maintenance job is a sale for the tax
        # authority, so the customer is entitled to the same UBL document
        # the trade path issues. It is produced inside this transaction,
        # so a broken document rolls the whole close back rather than
        # booking an invoice the customer cannot download.
        _generate_maintenance_einvoice(invoice)

        # 5. The order is closed.
        MaintenanceService.transition_status(
            order_id,
            tid,
            to_status=MaintenanceOrderStatus.CLOSED,
            changed_by=cashier_id,
            note=notes or gettext("إغلاق الأمر وقبض المبلغ"),
            allow_close=True,
        )
        order.closed_by = cashier_id
        order.closed_at = datetime.now(UTC)

        db.session.flush()

        log_financial(
            message=(
                f"Maintenance order closed: {order.order_number} total {total} "
                f"collected {amount_to_collect} cost {total_cost}"
            ),
            tenant_id=tid,
            level="INFO",
            source="services.maintenance_order_service.MaintenanceService.close_and_collect",
            extra={
                "order_id": order.id,
                "tenant_id": tid,
                "total": float(total),
                "collected": float(amount_to_collect),
                "parts_cost": float(total_cost),
                "invoice_number": invoice.invoice_number,
                "receipt_number": receipt.receipt_number if receipt is not None else None,
                "actor_id": actor_id,
            },
        )

        return order, receipt, invoice

    # ── تحصيل عربون عند الاستلام ──
    @staticmethod
    def collect_deposit(
        order_id: int,
        tenant_id: int,
        *,
        cashier_id: int,
        amount: Decimal,
        payment_mode: str = "cash",
        payment_reference: str | None = None,
        notes: str | None = None,
    ) -> MaintenanceReceipt:
        """تحصيل عربون على أمر صيانة.

        The deposit is a liability, not revenue: it is credited to the
        maintenance deposit account and later applied against the invoice.
        """
        tid = _require_tenant_id(tenant_id)
        order = _locked_order(order_id, tid)
        if order.status in (MaintenanceOrderStatus.CLOSED, MaintenanceOrderStatus.CANCELLED):
            raise ValueError(gettext("لا يمكن تحصيل عربون على أمر منتهٍ"))
        if order.is_archived:
            raise ValueError(gettext("لا يمكن تحصيل عربون على أمر مؤرشف"))

        payment_mode = (payment_mode or "").strip().lower()
        if payment_mode not in _PAYMENT_MODES:
            raise ValueError(gettext("طريقة دفع غير مدعومة: {mode}").format(mode=payment_mode))
        if payment_mode == "account":
            raise ValueError(gettext("لا يمكن تحصيل عربون على حساب"))

        amount = Decimal(str(amount or 0)).quantize(_BASE_QUANTUM, rounding=ROUND_HALF_UP)
        if amount <= 0:
            raise ValueError(gettext("مبلغ العربون يجب أن يكون أكبر من صفر"))
        if not tenant_query(User).filter_by(id=cashier_id, tenant_id=tid, is_active=True).first():
            raise ValueError(gettext("موظف الاستقبال غير موجود"))

        already = Decimal(str(order.deposit_amount or 0))
        # The cap only applies once the order has a price: a deposit is
        # usually taken at reception, before the diagnosis, so there is no
        # total to exceed yet.
        order_total = Decimal(str(order.total_amount or 0))
        if order_total > 0 and already + amount > order_total:
            raise ValueError(gettext("مجموع العربون يتجاوز قيمة الأمر"))

        receipt = MaintenanceService._create_receipt(
            order=order,
            cashier_id=cashier_id,
            amount=amount,
            payment_mode=payment_mode,
            reference_number=payment_reference,
            is_deposit=True,
        )
        receipt.is_deposit = True
        db.session.flush()

        MaintenanceGLService.post_deposit(receipt, cashier_id)

        log_financial(
            message=f"Maintenance deposit collected: {order.order_number} amount {amount}",
            tenant_id=tid,
            level="INFO",
            source="services.maintenance_order_service.MaintenanceService.collect_deposit",
            extra={
                "order_id": order.id,
                "tenant_id": tid,
                "amount": float(amount),
                "receipt_number": receipt.receipt_number,
                "notes": notes,
            },
        )

        return receipt

    # ── إنشاء سند قبض ──
    @staticmethod
    def _create_receipt(
        order: MaintenanceOrder,
        cashier_id: int,
        amount: Decimal,
        payment_mode: str,
        reference_number: str | None,
        *,
        is_deposit: bool = False,
    ) -> MaintenanceReceipt:
        """ينشئ سند قبض (أو عربون) ويربطه بالأمر.

        The money a customer has handed over is tracked in two places, and
        the difference matters: ``paid_amount`` is what was collected
        against the invoice, ``deposit_amount`` is what is being held as a
        deposit until the work is done. A deposit that was counted in both
        would make the order look settled when it is not.
        """
        if order is None:
            raise ValueError(gettext("لا يمكن إنشاء سند قبض بدون أمر صيانة"))
        tid = order.tenant_id
        DocumentSequenceService.get_or_create(
            tenant_id=tid,
            code="maintenance_receipt",
            prefix="PT",
            pattern="{prefix}-{year}-{counter:04d}",
            counter_reset="year",
        )
        receipt_number = DocumentSequenceService.next_number(
            tenant_id=tid,
            code="maintenance_receipt",
            prefix="PT",
        )

        receipt = MaintenanceReceipt(
            tenant_id=tid,
            order_id=order.id,
            receipt_number=receipt_number,
            amount=amount,
            payment_mode=payment_mode,
            reference_number=reference_number,
            cashier_id=cashier_id,
        )
        db.session.add(receipt)
        db.session.flush()

        if is_deposit:
            order.deposit_amount = Decimal(str(order.deposit_amount or 0)) + amount
        else:
            order.paid_amount = Decimal(str(order.paid_amount or 0)) + amount

        # The balance due is what is still owed after both the collected
        # money and the held deposit: the deposit reduces it, it does not
        # disappear. An order that has no price yet (a deposit taken at
        # reception, before the diagnosis) has nothing to be owed, so the
        # balance is left alone until the lines are priced.
        settled = Decimal(str(order.paid_amount or 0)) + Decimal(str(order.deposit_amount or 0))
        order_total = Decimal(str(order.total_amount or 0))
        if order_total > 0:
            order.balance_due = order_total - settled
            if order.balance_due < 0:
                raise ValueError(gettext("المبلغ المحصّل يتجاوز إجمالي الأمر"))

        return receipt

    # ── إنشاء فاتورة الصيانة ──
    @staticmethod
    def _create_invoice(order: MaintenanceOrder) -> MaintenanceInvoice:
        if order is None:
            raise ValueError(gettext("لا يمكن إنشاء فاتورة صيانة بدون أمر"))
        tid = order.tenant_id
        DocumentSequenceService.get_or_create(
            tenant_id=tid,
            code="maintenance_invoice",
            prefix="MINV",
            pattern="{prefix}-{year}-{counter:04d}",
            counter_reset="year",
        )
        invoice_number = DocumentSequenceService.next_number(
            tenant_id=tid,
            code="maintenance_invoice",
            prefix="MINV",
        )

        invoice = MaintenanceInvoice(
            tenant_id=tid,
            order_id=order.id,
            invoice_number=invoice_number,
            subtotal=order.subtotal,
            discount_total_percent=order.discount_total_percent,
            discount_total_value=order.discount_total_value,
            tax_rate=order.tax_rate,
            tax_amount=order.tax_amount,
            taxable_amount=order.taxable_amount,
            total_amount=order.total_amount,
            amount=order.amount,
            paid_amount=order.paid_amount,
            balance_due=order.balance_due,
            currency=order.currency,
            exchange_rate=order.exchange_rate,
            base_currency=order.base_currency,
            amount_aed=order.amount_aed,
            paid_amount_aed=order.paid_amount_aed,
            balance_due_aed=order.balance_due_aed,
            prices_include_vat=order.prices_include_vat,
        )
        db.session.add(invoice)
        db.session.flush()
        return invoice

    # ── إنشاء مرتجع صيانة ──
    @staticmethod
    def create_return(
        order_id: int,
        tenant_id: int,
        *,
        returned_by: int,
        reason: str,
        quantities: dict[str, Decimal],
    ) -> MaintenanceReturn:
        """إنشاء مرتجع صيانة: إرجاع القطع إلى المستودع وعكس القيود.

        The return is a reversal of the invoice leg and of the parts-cost
        leg, and both are reversed exactly: the tax the returned lines
        carried and the cost of the parts that go back on the shelf are
        posted with it, so the maintenance receivable, the revenue and the
        inventory all land back where they were.
        """
        tid = _require_tenant_id(tenant_id)
        order = _locked_order(order_id, tid)
        if order.status not in (MaintenanceOrderStatus.CLOSED, MaintenanceOrderStatus.READY):
            raise ValueError(gettext("لا يمكن إنشاء مرتجع ل أمر في حالة {status}").format(status=order.status))
        if order.is_archived:
            raise ValueError(gettext("لا يمكن إنشاء مرتجع لأمر مؤرشف"))
        if not tenant_query(User).filter_by(id=returned_by, tenant_id=tid, is_active=True).first():
            raise ValueError(gettext("المستخدم المنفّذ غير موجود"))

        if not quantities:
            raise ValueError(gettext("يجب اختيار كمية للإرجاع"))

        total = Decimal("0")
        total_tax = Decimal("0")
        total_cost = Decimal("0")
        prepared: list[tuple[MaintenanceOrderLine, Decimal]] = []

        for line in list(cast(Any, order.lines)):
            if line.is_archived:
                continue
            qty = Decimal(str(quantities.get(f"return_qty_{line.id}", 0) or 0))
            if qty <= 0:
                continue
            if qty > line.net_quantity:
                raise ValueError(
                    gettext("كمية الإرجاع تتجاوز الكمية المتبقية للقطعة {name}").format(
                        name=line.product.name if line.product else line.product_id
                    )
                )
            prepared.append((line, qty))

        if not prepared:
            raise ValueError(gettext("لا توجد كميات صالحة للإرجاع"))

        # The lines are created first so the stock can be returned against a
        # persisted return id (the movement points at it).
        return_number = DocumentSequenceService.next_number(
            tenant_id=tid,
            code="maintenance_return",
            prefix="MR",
        )
        maintenance_return = MaintenanceReturn(
            tenant_id=tid,
            order_id=order_id,
            return_number=return_number,
            return_date=datetime.now(UTC),
            returned_by=returned_by,
            reason=reason,
        )
        db.session.add(maintenance_return)
        db.session.flush()

        for line, qty in prepared:
            # The return reverses what the line actually carried: its share
            # of the order discount comes off first, and the tax is the tax
            # that was charged on what was left. Recomputing the line total
            # without the order discount's share would credit the
            # receivable more than the order ever gave up.
            net_quantity = Decimal(str(line.net_quantity or 1))
            returned_ratio = qty / net_quantity
            line_taxable = Decimal(str(line.taxable_amount or 0))
            line_tax = Decimal(str(line.tax_amount or 0))
            line_net = (line_taxable * returned_ratio).quantize(_BASE_QUANTUM, rounding=ROUND_HALF_UP)
            tax_share = (line_tax * returned_ratio).quantize(_BASE_QUANTUM, rounding=ROUND_HALF_UP)
            # The gross the customer gave up: the net revenue plus the tax.
            line_gross = (line_net + tax_share).quantize(_BASE_QUANTUM, rounding=ROUND_HALF_UP)
            return_line = MaintenanceReturnLine(
                tenant_id=tid,
                return_id=maintenance_return.id,
                order_line_id=line.id,
                quantity=qty,
                unit_price=line.unit_price,
                line_total=line_gross,
                line_total_aed=convert_and_quantize_aed(
                    line_gross, order.currency, order.exchange_rate, base_currency=order.base_currency
                ),
                line_total_tax=tax_share,
            )
            db.session.add(return_line)
            db.session.flush()

            MaintenanceStockService.return_parts_for_return_line(return_line, returned_by)

            line.quantity_returned = Decimal(str(line.quantity_returned or 0)) + qty
            total += return_line.line_total
            total_tax += return_line.line_total_tax
            total_cost += Decimal(str(return_line.line_total_cost or 0))

        maintenance_return.total_value = total.quantize(_BASE_QUANTUM, rounding=ROUND_HALF_UP)
        maintenance_return.total_value_tax = total_tax.quantize(_BASE_QUANTUM, rounding=ROUND_HALF_UP)
        maintenance_return.total_value_cost = total_cost.quantize(_BASE_QUANTUM, rounding=ROUND_HALF_UP)
        maintenance_return.total_value_aed = convert_and_quantize_aed(
            total, order.currency, order.exchange_rate, base_currency=order.base_currency
        )
        db.session.flush()

        MaintenanceGLService.post_return(maintenance_return, returned_by)

        log_financial(
            message=(f"Maintenance return created: {return_number} value {total} tax {total_tax} cost {total_cost}"),
            tenant_id=tid,
            level="INFO",
            source="services.maintenance_order_service.MaintenanceService.create_return",
            extra={
                "order_id": order.id,
                "tenant_id": tid,
                "return_number": return_number,
                "total": float(total),
                "tax": float(total_tax),
                "cost": float(total_cost),
            },
        )

        return maintenance_return

    # ── إنشاء قالب خدمة ──
    @staticmethod
    def create_service_template(
        tenant_id: int,
        *,
        service_code: str,
        name: str,
        name_ar: str | None,
        service_category: str,
        fixed_price: Decimal,
        duration_minutes: int,
        tax_rate: Decimal,
        requires_parts: bool,
        sort_order: int,
    ) -> MaintenanceServiceTemplate:
        """إضافة قالب خدمة ثابت السعر إلى لوحة المشرف."""
        tid = _require_tenant_id(tenant_id)
        service_code = (service_code or "").strip().upper()
        name = (name or "").strip()
        if not service_code or not name:
            raise ValueError(gettext("رمز الخدمة واسمها مطلوبان"))
        if len(service_code) > 50:
            raise ValueError(gettext("رمز الخدمة طويل جداً"))
        if fixed_price < 0:
            raise ValueError(gettext("سعر الخدمة لا يمكن أن يكون سالباً"))
        if duration_minutes < 0:
            raise ValueError(gettext("مدة الخدمة لا يمكن أن تكون سالبة"))

        existing = tenant_query(MaintenanceServiceTemplate).filter_by(tenant_id=tid, service_code=service_code).first()
        if existing is not None:
            raise ValueError(gettext("رمز الخدمة {code} مستخدم مسبقاً").format(code=service_code))

        template = MaintenanceServiceTemplate(
            tenant_id=tid,
            service_code=service_code,
            name=name,
            name_ar=name_ar,
            service_category=service_category or "other",
            fixed_price=Decimal(str(fixed_price)),
            duration_minutes=int(duration_minutes),
            tax_rate=Decimal(str(tax_rate)),
            requires_parts=bool(requires_parts),
            is_active=True,
            sort_order=int(sort_order),
        )
        db.session.add(template)
        db.session.flush()
        return template

    # ── تحديث إعدادات الصيانة ──
    @staticmethod
    def update_settings(tenant_id: int, **fields) -> MaintenanceSetting:
        """تحديث إعدادات الصيانة بعد التحقق من كل قيمة."""
        tid = _require_tenant_id(tenant_id)
        setting = MaintenanceService.ensure_settings(tid)

        warehouse_id = fields.get("default_warehouse_id")
        if warehouse_id:
            if not tenant_query(Warehouse).filter_by(id=warehouse_id, tenant_id=tid, is_active=True).first():
                raise ValueError(gettext("المستودع غير موجود"))
            setting.default_warehouse_id = int(warehouse_id)

        max_percent = Decimal(str(fields.get("max_discount_percent") or 0))
        max_value = Decimal(str(fields.get("max_discount_value") or 0))
        if not 0 <= max_percent <= 100:
            raise ValueError(gettext("سقف الخصم بالنسبة المئوية يجب أن يكون بين 0 و 100"))
        if max_value < 0:
            raise ValueError(gettext("سقف الخصم بالقيمة لا يمكن أن يكون سالباً"))
        setting.max_discount_percent = max_percent
        setting.max_discount_value = max_value

        setting.allow_engineer_discount = bool(fields.get("allow_engineer_discount"))
        setting.require_manager_approval_above_discount = bool(fields.get("require_manager_approval_above_discount"))
        setting.require_warranty_check = bool(fields.get("require_warranty_check"))
        setting.allow_engineer_cancel_warranty = bool(fields.get("allow_engineer_cancel_warranty"))
        setting.allow_engineer_restore_warranty = bool(fields.get("allow_engineer_restore_warranty"))

        for field, fallback in (
            ("color_warranty", "#10b981"),
            ("color_non_warranty", "#ef4444"),
            ("color_unknown_warranty", "#f59e0b"),
        ):
            value = (fields.get(field) or fallback).strip()
            if not _is_hex_color(value):
                raise ValueError(gettext("لون غير صالح: {value}").format(value=value))
            setattr(setting, field, value)

        db.session.flush()
        return setting

    # ── ألوان تمييز الكفالة ──
    @staticmethod
    def get_warranty_colors(tenant_id: int) -> dict[str, str]:
        """The tenant's warranty colour tags, keyed by warranty state.

        The colours are the tenant's own choice, so the page emits them
        once into a style block instead of writing an inline style on
        every row.
        """
        setting = tenant_query(MaintenanceSetting).filter_by(tenant_id=tenant_id).first()
        return {
            "under_warranty": getattr(setting, "color_warranty", None) or "#10b981",
            "expired": getattr(setting, "color_non_warranty", None) or "#ef4444",
            "void": getattr(setting, "color_non_warranty", None) or "#ef4444",
            "unknown": getattr(setting, "color_unknown_warranty", None) or "#f59e0b",
        }

    # ── إنشاء إعدادات الصيانة الافتراضية لتينانت جديد ──
    @staticmethod
    def ensure_settings(tenant_id: int) -> MaintenanceSetting:
        tid = _require_tenant_id(tenant_id)
        existing = tenant_query(MaintenanceSetting).filter_by(tenant_id=tid).first()
        if existing:
            return existing

        setting = MaintenanceSetting(
            tenant_id=tid,
            default_warehouse_id=None,
            maintenance_ar_account_id=None,
            maintenance_revenue_account_id=None,
            maintenance_cogs_account_id=None,
            max_discount_percent=Decimal("15"),
            max_discount_value=Decimal("0"),
            allow_engineer_discount=True,
            require_manager_approval_above_discount=True,
            require_warranty_check=True,
            color_warranty="#10b981",
            color_non_warranty="#ef4444",
            color_unknown_warranty="#f59e0b",
            allow_engineer_cancel_warranty=False,
            allow_engineer_restore_warranty=False,
            invoice_prefix="MINV",
            receipt_prefix="PT",
            order_prefix="MN",
        )
        db.session.add(setting)
        db.session.flush()
        return setting

    # ── إنشاء خدمات صيانة افتراضية (بذور أساسية) ──
    @staticmethod
    def ensure_default_service_templates(tenant_id: int) -> list[MaintenanceServiceTemplate]:
        tid = _require_tenant_id(tenant_id)
        existing = tenant_query(MaintenanceServiceTemplate).filter_by(tenant_id=tid).count()
        if existing > 0:
            return []

        templates = [
            MaintenanceServiceTemplate(
                tenant_id=tid,
                service_code="MECH-001",
                name="تغيير زيت",
                name_ar="تغيير زيت المحرك",
                service_category="mechanical",
                fixed_price=Decimal("50.000"),
                duration_minutes=30,
                tax_rate=Decimal("0"),
                requires_parts=True,
                sort_order=1,
            ),
            MaintenanceServiceTemplate(
                tenant_id=tid,
                service_code="ELEC-001",
                name="فحص كهرباء",
                name_ar="فحص النظام الكهربائي",
                service_category="electrical",
                fixed_price=Decimal("30.000"),
                duration_minutes=20,
                tax_rate=Decimal("0"),
                requires_parts=False,
                sort_order=2,
            ),
            MaintenanceServiceTemplate(
                tenant_id=tid,
                service_code="LABOR-001",
                name="ساعة عمل",
                name_ar="ساعة عمل يدوية",
                service_category="labor",
                fixed_price=Decimal("25.000"),
                duration_minutes=60,
                tax_rate=Decimal("0"),
                requires_parts=False,
                sort_order=3,
            ),
            MaintenanceServiceTemplate(
                tenant_id=tid,
                service_code="DIAG-001",
                name="تشخيص شامل",
                name_ar="تشخيص شامل للمركبة/الجهاز",
                service_category="diagnostic",
                fixed_price=Decimal("40.000"),
                duration_minutes=45,
                tax_rate=Decimal("0"),
                requires_parts=False,
                sort_order=4,
            ),
        ]
        for t in templates:
            db.session.add(t)
        db.session.flush()
        return templates

    # ── تقرير إيرادات الصيانة ──
    @staticmethod
    def get_revenue_report(
        tenant_id: int,
        *,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> dict[str, Any]:
        """تقرير إيرادات الصيانة حسب الفترة."""
        tid = _require_tenant_id(tenant_id)
        q = tenant_query(MaintenanceInvoice).filter_by(tenant_id=tid, posted=True, gl_posted=True)
        if date_from:
            q = q.filter(MaintenanceInvoice.invoice_date >= date_from)
        if date_to:
            q = q.filter(MaintenanceInvoice.invoice_date <= date_to)

        invoices = q.all()
        base_currency = resolve_tenant_base_currency(tenant_id=tid)

        def to_base(inv, amount):
            return convert_and_quantize_aed(amount or 0, inv.currency, inv.exchange_rate, base_currency=base_currency)

        total_gross = sum((to_base(inv, inv.total_amount) for inv in invoices), Decimal("0"))
        total_tax = sum((to_base(inv, inv.tax_amount) for inv in invoices), Decimal("0"))
        total_paid = sum((to_base(inv, inv.paid_amount) for inv in invoices), Decimal("0"))
        total_due = sum((to_base(inv, inv.balance_due) for inv in invoices), Decimal("0"))

        return {
            "tenant_id": tid,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
            "invoice_count": len(invoices),
            "base_currency": base_currency,
            "total_revenue": total_gross - total_tax,
            "total_gross": total_gross,
            "total_tax": total_tax,
            "total_paid": total_paid,
            "total_due": total_due,
            "invoices": [
                {
                    "invoice_number": inv.invoice_number,
                    "invoice_date": inv.invoice_date.isoformat() if inv.invoice_date else None,
                    "order_number": inv.order.order_number if inv.order else None,
                    "customer_name": inv.order.customer_name if inv.order else None,
                    "currency": inv.currency,
                    "total_amount": Decimal(str(inv.total_amount or 0)),
                    "paid_amount": Decimal(str(inv.paid_amount or 0)),
                    "balance_due": Decimal(str(inv.balance_due or 0)),
                }
                for inv in invoices
            ],
        }

    # ── تقرير هامش الربح ──
    @staticmethod
    def get_margin_report(
        tenant_id: int,
        *,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> dict[str, Any]:
        """تقرير هامش الربح لكل أمر صيانة.

        The margin is the revenue the job carried less the cost of the
        parts it consumed - the labour is not in it, because the module
        does not cost labour: it has no wage rate for an engineer, and
        guessing one would produce a margin nobody can defend. What it
        does show is the parts margin, which is the number that tells the
        workshop whether its parts pricing is healthy.
        """
        tid = _require_tenant_id(tenant_id)
        query = tenant_query(MaintenanceOrder).filter_by(tenant_id=tid)
        if date_from:
            query = query.filter(MaintenanceOrder.order_date >= date_from)
        if date_to:
            query = query.filter(MaintenanceOrder.order_date <= date_to)

        orders = query.order_by(MaintenanceOrder.order_date.desc()).all()

        rows = []
        total_revenue = Decimal("0")
        total_cost = Decimal("0")
        for order in orders:
            revenue = Decimal(str(order.taxable_amount or 0))
            cost = Decimal("0")
            for line in cast(Any, order.lines):
                if line.is_archived:
                    continue
                cost += Decimal(str(line.cost_aed or 0))
            margin = revenue - cost
            total_revenue += revenue
            total_cost += cost
            rows.append(
                {
                    "order_id": order.id,
                    "order_number": order.order_number,
                    "order_date": order.order_date,
                    "customer_name": order.customer_name,
                    "status": order.status,
                    "revenue": revenue,
                    "parts_cost": cost,
                    "margin": margin,
                    "margin_percent": (
                        (margin / revenue * Decimal("100")).quantize(Decimal("0.01")) if revenue > 0 else Decimal("0")
                    ),
                    "engineer_name": order.engineer.full_name if order.engineer else None,
                }
            )

        total_margin = total_revenue - total_cost
        return {
            "tenant_id": tid,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
            "base_currency": resolve_tenant_base_currency(tenant_id=tid),
            "order_count": len(orders),
            "total_revenue": total_revenue,
            "total_parts_cost": total_cost,
            "total_margin": total_margin,
            "margin_percent": (
                (total_margin / total_revenue * Decimal("100")).quantize(Decimal("0.01"))
                if total_revenue > 0
                else Decimal("0")
            ),
            "orders": rows,
        }

    # ── تقرير أداء الفنيين ──
    @staticmethod
    def get_engineer_report(
        tenant_id: int,
        *,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> dict[str, Any]:
        """تقرير أداء الفنيين: كم أمراً عمل كل فني وبقيمة كم.

        The time is the sum of the durations the service lines carry. It
        is the time the work was planned to take, not the time it took -
        the module does not track a clock on the bench - and the report
        says so rather than pretending otherwise.
        """
        tid = _require_tenant_id(tenant_id)
        query = tenant_query(MaintenanceOrder).filter_by(tenant_id=tid)
        if date_from:
            query = query.filter(MaintenanceOrder.order_date >= date_from)
        if date_to:
            query = query.filter(MaintenanceOrder.order_date <= date_to)

        orders = query.all()

        by_engineer: dict[int, dict[str, Any]] = {}
        unassigned: dict[str, Any] = {
            "engineer_id": None,
            "engineer_name": None,
            "order_count": 0,
            "revenue": Decimal("0"),
            "parts_cost": Decimal("0"),
            "margin": Decimal("0"),
            "minutes": 0,
        }

        for order in orders:
            revenue = Decimal(str(order.taxable_amount or 0))
            cost = Decimal("0")
            minutes = 0
            for line in cast(Any, order.lines):
                if not line.is_archived:
                    cost += Decimal(str(line.cost_aed or 0))
            for service_line in cast(Any, order.services_lines):
                if not service_line.is_archived:
                    minutes += int(service_line.duration_minutes or 0)

            if order.engineer_id is None:
                unassigned["order_count"] += 1
                unassigned["revenue"] += revenue
                unassigned["parts_cost"] += cost
                unassigned["margin"] += revenue - cost
                unassigned["minutes"] += minutes
                continue

            entry: dict[str, Any] = by_engineer.setdefault(
                int(order.engineer_id),
                {
                    "engineer_id": order.engineer_id,
                    "engineer_name": order.engineer.full_name if order.engineer else None,
                    "order_count": 0,
                    "revenue": Decimal("0"),
                    "parts_cost": Decimal("0"),
                    "margin": Decimal("0"),
                    "minutes": 0,
                },
            )
            entry["order_count"] += 1
            entry["revenue"] += revenue
            entry["parts_cost"] += cost
            entry["margin"] += revenue - cost
            entry["minutes"] += minutes

        rows: list[dict[str, Any]] = []
        for entry in by_engineer.values():
            rows.append(
                {
                    **entry,
                    "margin_percent": (
                        (entry["margin"] / entry["revenue"] * Decimal("100")).quantize(Decimal("0.01"))
                        if entry["revenue"] > 0
                        else Decimal("0")
                    ),
                    "average_minutes": (entry["minutes"] // entry["order_count"] if entry["order_count"] else 0),
                }
            )
        rows.sort(key=lambda item: (-item["order_count"], str(item["engineer_name"] or "")))

        if unassigned["order_count"]:
            rows.append(
                {
                    **unassigned,
                    "margin_percent": (
                        (unassigned["margin"] / unassigned["revenue"] * Decimal("100")).quantize(Decimal("0.01"))
                        if unassigned["revenue"] > 0
                        else Decimal("0")
                    ),
                    "average_minutes": (
                        unassigned["minutes"] // unassigned["order_count"] if unassigned["order_count"] else 0
                    ),
                }
            )

        return {
            "tenant_id": tid,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
            "base_currency": resolve_tenant_base_currency(tenant_id=tid),
            "order_count": len(orders),
            "engineer_count": len(by_engineer),
            "total_minutes": sum(row["minutes"] for row in rows),
            "engineers": rows,
        }

    # ── تقرير القطع المصروفة ──
    @staticmethod
    def get_parts_report(
        tenant_id: int,
        *,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> dict[str, Any]:
        """تقرير القطع المصروفة من مستودع الصيانة.

        The report is built from the order lines, not from the stock
        movements: a line is what the customer was charged for, and a
        movement is what the shelf did. Joining the two would be the
        honest way, but a line that has not been issued yet is not a
        movement, and a movement with no line is a stock correction - so
        the report answers the question the workshop actually asks: which
        parts went into which jobs, and at what cost.

        The period selects the jobs, not the lines: a workshop asks for
        "the parts we used on last month's jobs", and the job's own date
        is what carries that meaning.
        """
        tid = _require_tenant_id(tenant_id)
        query = (
            tenant_query(MaintenanceOrderLine)
            .join(MaintenanceOrder, MaintenanceOrder.id == MaintenanceOrderLine.order_id)
            .filter(MaintenanceOrderLine.tenant_id == tid)
            .filter(MaintenanceOrderLine.is_archived.is_(False))
            .filter(MaintenanceOrderLine.movement_id.isnot(None))
        )
        if date_from:
            query = query.filter(MaintenanceOrder.order_date >= date_from)
        if date_to:
            query = query.filter(MaintenanceOrder.order_date <= date_to)

        lines = query.all()
        base_currency = resolve_tenant_base_currency(tenant_id=tid)

        by_product: dict[int, dict[str, Any]] = {}
        total_quantity = Decimal("0")
        total_cost = Decimal("0")

        for line in lines:
            order = line.order
            quantity = Decimal(str(line.quantity or 0))
            cost = Decimal(str(line.cost_aed or 0))
            total_quantity += quantity
            total_cost += cost

            key = int(line.product_id or 0)
            entry = by_product.setdefault(
                key,
                {
                    "product_id": line.product_id,
                    "product_name": line.product.name if line.product else str(line.product_id),
                    "sku": line.product.sku if line.product else None,
                    "quantity": Decimal("0"),
                    "cost": Decimal("0"),
                    "orders": set(),
                },
            )
            entry["quantity"] += quantity
            entry["cost"] += cost
            if order is not None:
                entry["orders"].add(order.order_number)

        rows = []
        for entry in sorted(by_product.values(), key=lambda item: str(item["product_name"])):
            rows.append(
                {
                    "product_id": entry["product_id"],
                    "product_name": entry["product_name"],
                    "sku": entry["sku"],
                    "quantity": entry["quantity"],
                    "cost": entry["cost"],
                    "order_count": len(entry["orders"]),
                    "order_numbers": sorted(entry["orders"]),
                }
            )

        return {
            "tenant_id": tid,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
            "base_currency": base_currency,
            "line_count": len(lines),
            "total_quantity": total_quantity,
            "total_cost": total_cost,
            "parts": rows,
        }

    # ── تقرير الكفالات ──
    @staticmethod
    def get_warranty_report(tenant_id: int) -> dict[str, Any]:
        """تقرير حالة الكفالات: كم جهازاً مغطّى وكم منتهٍ وكم غير معروف.

        The counts are read from the device registry - the module's own
        memory of what it has seen - and not from the orders, because an
        order is a job and a device is a machine: one machine can be in
        the workshop many times over.
        """
        tid = _require_tenant_id(tenant_id)
        devices = (
            tenant_query(MaintenanceDeviceRegistry)
            .filter_by(tenant_id=tid, is_active=True)
            .order_by(MaintenanceDeviceRegistry.id.desc())
            .all()
        )

        counts = {
            MaintenanceOrderWarrantyStatus.UNDER_WARRANTY: 0,
            MaintenanceOrderWarrantyStatus.EXPIRED: 0,
            MaintenanceOrderWarrantyStatus.VOID: 0,
            MaintenanceOrderWarrantyStatus.UNKNOWN: 0,
        }
        rows = []
        for device in devices:
            status = device.warranty_status
            counts[status] = counts.get(status, 0) + 1
            rows.append(
                {
                    "id": device.id,
                    "brand": device.brand,
                    "model": device.model,
                    "serial_number": device.serial_number,
                    "imei": device.imei,
                    "plate": device.plate,
                    "warranty_type": device.warranty_type,
                    "warranty_status": status,
                    "warranty_end_date": (device.warranty_end_date.isoformat() if device.warranty_end_date else None),
                    "customer_name": device.customer.name if device.customer else None,
                }
            )

        return {
            "tenant_id": tid,
            "device_count": len(devices),
            "under_warranty": counts.get(MaintenanceOrderWarrantyStatus.UNDER_WARRANTY, 0),
            "expired": counts.get(MaintenanceOrderWarrantyStatus.EXPIRED, 0),
            "void": counts.get(MaintenanceOrderWarrantyStatus.VOID, 0),
            "unknown": counts.get(MaintenanceOrderWarrantyStatus.UNKNOWN, 0),
            "devices": rows,
        }
