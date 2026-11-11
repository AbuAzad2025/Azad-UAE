"""خدمة شراء قطع الصيانة - Maintenance Purchase Service

ورشة الصيانة تشتري قطع الغيار من الموردين. هذا الملف هو المسار الذي
توريد فيه تلك القطع إلى مستودع الصيانة:

* ``create_purchase_order`` — يفتح أمر شراء باسم مورد ومستودع.
* ``add_line`` — يضيف قطعة بسعر تكلفتها من المورد.
* ``receive_purchase_order`` — **الاستلام**: القطع تدخل المستودع،
  المتوسط المتحرك المرجح يُحدَّث، القيود تُرحَّل.

القاعدة المحاسبية: القطعة التي تدخل المستودع تُقيَّم بسعر شرائها من
المورد، لا بسعر بيعها. منه هو المتوسط المتحرك المرجح الذي يخرج لاحقًا
مع كل أمر صيانة — فالدورة تبدأ من هنا.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, cast

from flask_babel import gettext

from extensions import db
from models import (
    MaintenancePurchaseOrder,
    MaintenancePurchaseOrderLine,
    MaintenancePurchaseOrderStatus,
    Product,
    ProductCostHistory,
    ProductWarehouseCost,
    Supplier,
    User,
    Warehouse,
)
from services.document_sequence_service import DocumentSequenceService
from services.maintenance_gl_service import MaintenanceGLService
from services.stock_service import StockService, _safe_for_update
from utils.gl_reference_types import GLRef
from utils.logger import log_financial
from utils.tenanting import tenant_query

logger = logging.getLogger(__name__)

_COST_QUANTUM = Decimal("0.0001")
_MONEY_QUANTUM = Decimal("0.001")

#: The stock movement the receipt creates. It is the trade path's own type,
#: so the inventory report reads a maintenance delivery as what it is -
#: goods arriving - rather than inventing a type the rest of the system
#: does not know.
RECEIPT_MOVEMENT_TYPE = "purchase"


def _require_tenant_id(tenant_id: int | None) -> int:
    """The tenant the write belongs to.

    A cross-tenant write is a P0 defect, so the tenant is resolved and
    checked against the active one rather than trusted.
    """
    from utils.tenanting import get_active_tenant_id

    if tenant_id is None:
        raise ValueError(gettext("لا يمكن تنفيذ العملية بدون شركة"))
    active = get_active_tenant_id()
    if active is not None and int(tenant_id) != int(active):
        raise ValueError(gettext("لا يمكن تنفيذ العملية لشركة أخرى"))
    return int(tenant_id)


def _locked_purchase_order(purchase_order_id: int, tenant_id: int) -> MaintenancePurchaseOrder:
    order = (
        tenant_query(MaintenancePurchaseOrder)
        .filter_by(id=purchase_order_id, tenant_id=tenant_id)
        .populate_existing()
        .with_for_update()
        .first()
    )
    if order is None:
        raise ValueError(gettext("أمر شراء قطع الصيانة غير موجود"))
    return order


class MaintenancePurchaseService:
    """شراء قطع غيار الصيانة - منطق الأعمال النقي."""

    # ── إنشاء أمر شراء ──
    @staticmethod
    def create_purchase_order(
        tenant_id: int,
        *,
        branch_id: int | None,
        warehouse_id: int | None,
        supplier_id: int | None,
        supplier_name: str | None,
        tax_rate: Decimal,
        notes: str | None = None,
        currency: str | None = None,
        exchange_rate: Decimal | None = None,
    ) -> MaintenancePurchaseOrder:
        """فتح أمر شراء قطع صيانة.

        The order names the supplier and the warehouse before it names any
        part: the goods have to be destined for a shelf, and the shelf has
        to belong to this tenant.
        """
        tid = _require_tenant_id(tenant_id)

        warehouse = None
        if warehouse_id:
            warehouse = tenant_query(Warehouse).filter_by(id=warehouse_id, tenant_id=tid, is_active=True).first()
            if warehouse is None:
                raise ValueError(gettext("المستودع غير موجود"))
            branch_id = warehouse.branch_id or branch_id

        supplier = None
        if supplier_id:
            supplier = tenant_query(Supplier).filter_by(id=supplier_id, tenant_id=tid).first()
            if supplier is None:
                raise ValueError(gettext("المورد غير موجود"))
            supplier_name = supplier.name

        rate = Decimal(str(tax_rate or 0))
        if not 0 <= rate <= 100:
            raise ValueError(gettext("نسبة الضريبة غير صالحة"))

        DocumentSequenceService.get_or_create(
            tenant_id=tid,
            code="maintenance_purchase",
            prefix="MPO",
            pattern="{prefix}-{year}-{counter:04d}",
            counter_reset="year",
        )
        po_number = DocumentSequenceService.next_number(
            tenant_id=tid,
            code="maintenance_purchase",
            prefix="MPO",
        )

        tenant_currency = currency
        if not tenant_currency:
            from models import Tenant

            tenant = tenant_query(Tenant).filter_by(id=tid).first()
            tenant_currency = (tenant.default_currency if tenant else None) or "AED"

        order = MaintenancePurchaseOrder(
            tenant_id=tid,
            branch_id=branch_id,
            warehouse_id=warehouse.id if warehouse else None,
            supplier_id=supplier.id if supplier else None,
            supplier_name=supplier_name,
            po_number=po_number,
            order_date=datetime.now(UTC),
            status=MaintenancePurchaseOrderStatus.DRAFT,
            tax_rate=rate,
            currency=(tenant_currency or "AED").strip().upper()[:3],
            exchange_rate=Decimal(str(exchange_rate if exchange_rate is not None else 1)),
            notes=notes,
        )
        db.session.add(order)
        db.session.flush()

        log_financial(
            message=f"Maintenance purchase order created: {po_number}",
            tenant_id=tid,
            level="INFO",
            source="services.maintenance_purchase_service.MaintenancePurchaseService.create_purchase_order",
            extra={
                "tenant_id": tid,
                "purchase_order_id": order.id,
                "po_number": po_number,
                "supplier_id": supplier.id if supplier else None,
            },
        )

        return order

    # ── إضافة سطر ──
    @staticmethod
    def add_line(
        purchase_order_id: int,
        tenant_id: int,
        *,
        product_id: int,
        quantity: Decimal,
        unit_cost: Decimal,
        warehouse_id: int | None = None,
    ) -> MaintenancePurchaseOrderLine:
        """إضافة قطعة إلى أمر الشراء بسعر تكلفتها من المورد."""
        tid = _require_tenant_id(tenant_id)
        order = _locked_purchase_order(purchase_order_id, tid)
        if order.status != MaintenancePurchaseOrderStatus.DRAFT:
            raise ValueError(gettext("لا يمكن تعديل أمر شراء تم استلامه"))
        if order.is_archived:
            raise ValueError(gettext("لا يمكن تعديل أمر شراء مؤرشف"))

        qty = Decimal(str(quantity or 0))
        cost = Decimal(str(unit_cost or 0))
        if qty <= 0:
            raise ValueError(gettext("الكمية يجب أن تكون أكبر من صفر"))
        if cost < 0:
            raise ValueError(gettext("سعر التكلفة لا يمكن أن يكون سالباً"))
        if cost != cost.quantize(_COST_QUANTUM, rounding=ROUND_HALF_UP):
            raise ValueError(gettext("سعر التكلفة يحتوي على منازل عشرية غير مسموح بها"))
        if qty > Decimal("999999999999.999") or cost > Decimal("999999999999.999"):
            raise ValueError(gettext("الكمية أو السعر يتجاوز الحد المسموح"))

        product = tenant_query(Product).filter_by(id=product_id, tenant_id=tid, is_active=True).first()
        if product is None:
            raise ValueError(gettext("المنتج غير موجود"))

        line = MaintenancePurchaseOrderLine(
            tenant_id=tid,
            purchase_order_id=order.id,
            product_id=product.id,
            warehouse_id=warehouse_id or order.warehouse_id,
            quantity=qty,
            unit_cost=cost,
            line_total=(qty * cost).quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP),
        )
        db.session.add(line)
        db.session.flush()

        MaintenancePurchaseService._recalculate(order)
        db.session.flush()
        return line

    # ── إعادة حساب الإجماليات ──
    @staticmethod
    def _recalculate(order: MaintenancePurchaseOrder) -> None:
        """حساب إجماليات أمر الشراء.

        The tax is not part of the stock: it is recoverable, so it is
        posted to the input-tax account and only the net amount
        capitalises into the inventory. Getting this wrong would inflate
        the moving average of every part the workshop buys.
        """
        subtotal = Decimal("0")
        for line in cast(Any, order.lines):
            line.line_total = (Decimal(str(line.quantity or 0)) * Decimal(str(line.unit_cost or 0))).quantize(
                _MONEY_QUANTUM, rounding=ROUND_HALF_UP
            )
            subtotal += line.line_total

        rate = Decimal(str(order.tax_rate or 0))
        taxable = subtotal
        tax = (taxable * rate / Decimal("100")).quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)

        order.subtotal = subtotal
        order.taxable_amount = taxable
        order.tax_amount = tax
        order.total_amount = taxable + tax
        db.session.flush()

    # ── استلام الأمر ──
    @staticmethod
    def receive_purchase_order(
        purchase_order_id: int,
        tenant_id: int,
        *,
        received_by: int,
    ) -> MaintenancePurchaseOrder:
        """استلام أمر الشراء: القطع تدخل المستودع والقيود تُرحَّل.

        This is the moment the goods become the workshop's stock, and it
        is one unit of work: the stock arrives, the moving average is
        rebuilt from the supplier's cost, and the ledger records the
        inventory against the payable. If any step fails, the caller's
        transaction rolls back and the warehouse is left exactly as it
        was.
        """
        tid = _require_tenant_id(tenant_id)
        order = _locked_purchase_order(purchase_order_id, tid)
        if order.status == MaintenancePurchaseOrderStatus.RECEIVED:
            raise ValueError(gettext("تم استلام أمر الشراء مسبقاً"))
        if order.status == MaintenancePurchaseOrderStatus.CANCELLED:
            raise ValueError(gettext("لا يمكن استلام أمر شراء ملغى"))
        if order.is_archived:
            raise ValueError(gettext("لا يمكن استلام أمر شراء مؤرشف"))
        if not tenant_query(User).filter_by(id=received_by, tenant_id=tid, is_active=True).first():
            raise ValueError(gettext("مستخدم الاستلام غير موجود"))

        lines = [line for line in cast(Any, order.lines) if not line.is_archived]
        if not lines:
            raise ValueError(gettext("لا يمكن استلام أمر شراء بدون سطور"))

        warehouse_id = order.warehouse_id
        if not warehouse_id:
            raise ValueError(gettext("أمر الشراء لا يحتوي على مستودع"))

        for line in lines:
            qty = Decimal(str(line.quantity or 0))
            if qty <= 0:
                raise ValueError(gettext("كمية سطر غير صالحة"))
            line_warehouse_id = line.warehouse_id or warehouse_id
            warehouse = tenant_query(Warehouse).filter_by(id=line_warehouse_id, tenant_id=tid, is_active=True).first()
            if warehouse is None:
                raise ValueError(gettext("المستودع غير موجود"))
            product = tenant_query(Product).filter_by(id=line.product_id, tenant_id=tid, is_active=True).first()
            if product is None:
                raise ValueError(gettext("المنتج غير موجود"))

            unit_cost = Decimal(str(line.unit_cost or 0))
            movement = StockService.create_movement(
                product_id=product.id,
                quantity=qty,
                movement_type=RECEIPT_MOVEMENT_TYPE,
                reference_type=GLRef.MAINTENANCE,
                reference_id=order.id,
                notes=gettext("توريد قطع صيانة - أمر شراء {number}").format(number=order.po_number),
                warehouse_id=warehouse.id,
                resolved_product=product,
                resolved_warehouse=warehouse,
            )
            if movement.user_id is None:
                movement.user_id = received_by

            MaintenancePurchaseService._apply_mwac_inflow(
                tenant_id=tid,
                product_id=product.id,
                warehouse_id=warehouse.id,
                quantity=qty,
                unit_cost=unit_cost,
                movement=movement,
                reference_id=order.id,
            )

            line.movement_id = movement.id
            line.received_quantity = qty

        order.status = MaintenancePurchaseOrderStatus.RECEIVED
        order.received_at = datetime.now(UTC)
        order.received_by = received_by
        db.session.flush()

        MaintenanceGLService.post_purchase_receipt(order, received_by)

        order.posted = True
        order.posted_at = datetime.now(UTC)
        order.gl_posted = True
        db.session.flush()

        log_financial(
            message=f"Maintenance purchase received: {order.po_number} total {order.total_amount}",
            tenant_id=tid,
            level="INFO",
            source="services.maintenance_purchase_service.MaintenancePurchaseService.receive_purchase_order",
            extra={
                "tenant_id": tid,
                "purchase_order_id": order.id,
                "po_number": order.po_number,
                "total": float(order.total_amount),
                "received_by": received_by,
            },
        )

        return order

    # ── المتوسط المتحرك بعد التوريد ──
    @staticmethod
    def _apply_mwac_inflow(
        *,
        tenant_id: int,
        product_id: int,
        warehouse_id: int,
        quantity: Decimal,
        unit_cost: Decimal,
        movement: Any,
        reference_id: int,
    ) -> None:
        """يرفع المتوسط المتحرك المرجح بالكمية الواردة وتكلفتها.

        The incoming goods are priced at what the supplier charged, so
        the moving average the workshop later issues at is a real cost
        and not a leftover from an earlier purchase.
        """
        pwc = _safe_for_update(
            ProductWarehouseCost.query.filter_by(
                tenant_id=tenant_id,
                product_id=product_id,
                warehouse_id=warehouse_id,
            ),
            label=f"mnt_purchase_PWC_p={product_id}_w={warehouse_id}",
        )
        old_qty = Decimal(str(pwc.total_quantity)) if pwc and pwc.total_quantity is not None else Decimal("0")
        old_value = Decimal(str(pwc.total_value)) if pwc and pwc.total_value is not None else Decimal("0")
        old_avg = Decimal(str(pwc.average_cost)) if pwc and pwc.average_cost is not None else Decimal("0")

        new_qty, new_value, new_avg = StockService._mwac_calc(old_qty, old_value, quantity, unit_cost)
        new_avg = new_avg.quantize(_COST_QUANTUM, rounding=ROUND_HALF_UP) if new_qty > 0 else Decimal("0")

        if pwc is None:
            pwc = ProductWarehouseCost(
                tenant_id=tenant_id,
                product_id=product_id,
                warehouse_id=warehouse_id,
                total_quantity=new_qty,
                total_value=new_value,
                average_cost=new_avg,
            )
            db.session.add(pwc)
        else:
            pwc.total_quantity = new_qty
            pwc.total_value = new_value
            pwc.average_cost = new_avg
            pwc.last_updated = datetime.now(UTC)
            pwc.updated_by_movement_id = movement.id
        db.session.flush()

        db.session.add(
            ProductCostHistory(
                tenant_id=tenant_id,
                product_id=product_id,
                warehouse_id=warehouse_id,
                movement_type=RECEIPT_MOVEMENT_TYPE,
                movement_id=movement.id,
                reference_type=GLRef.MAINTENANCE,
                reference_id=reference_id,
                old_average_cost=old_avg,
                new_average_cost=new_avg,
                quantity_change=quantity,
                old_total_quantity=old_qty,
                new_total_quantity=new_qty,
                old_total_value=old_value,
                new_total_value=new_value,
                movement_unit_cost=unit_cost,
            )
        )
        db.session.flush()
