"""
خدمة مخزون الصيانة - Maintenance Stock Service

قطع الغيار تُستهلك من مستودع الصيانة عبر نفس آلية المخزون في النظام:

* ``StockService.create_movement`` — إنشاء الحركة مع قفل صف حصة المخزون
  (``ProductWarehouseStock``) ومنع السالب، وتحديث ``Product.current_stock``.
* ``ProductWarehouseCost`` — المتوسط المتحرك المرجح (MWAC) هو مصدر التكلفة،
  لا سعر الشراء أو سعر البيع. التكلفة تُسجَّل في ``ProductCostHistory``
  كأثر تدقيق لكل حركة.
* ``StockBatchService`` — عند تفعيل الدفعات، الاستهلاك يتبع FEFO.

القاعدة المحاسبية: قطعة تخرج من المستودع يجب أن تحمل تكلفتها الحقيقية في
نفس اللحظة، وإلا اختلّت قيمة المخزون أمام دفتر الأستاذ.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from flask_babel import gettext

from extensions import db
from models import (
    MaintenanceOrderLine,
    MaintenanceReturnLine,
    Product,
    ProductCostHistory,
    ProductWarehouseCost,
    StockMovement,
    Warehouse,
)
from services.gl_posting import GlPostingError
from services.serial_tracking_service import SerialTrackingService
from services.stock_batch_service import StockBatchService
from services.stock_service import StockService, _safe_for_update
from utils.gl_reference_types import GLRef
from utils.logger import log_financial
from utils.tenanting import tenant_query

logger = logging.getLogger(__name__)

_COST_QUANTUM = Decimal("0.0001")
_MONEY_QUANTUM = Decimal("0.001")

#: The stock movement types this module writes. Both are recorded so the
#: inventory report can tell a maintenance issue from a sale.
MAINTENANCE_MOVEMENT_TYPE = "maintenance"
MAINTENANCE_RETURN_MOVEMENT_TYPE = "maintenance_return"


class MaintenanceStockService:
    """إدارة مخزون الصيانة - قطع الغيار المستهلكة من مستودع الصيانة."""

    # ── cost resolution ──────────────────────────────────────────────────
    @staticmethod
    def _resolve_unit_cost(
        product_id: int,
        warehouse_id: int,
        tenant_id: int,
        line_cost_price: Decimal | None = None,
    ) -> tuple[Decimal, str]:
        """The unit cost of one unit leaving the shelf.

        The chain is the same one the sales path uses: the warehouse's moving
        average first, then the cost recorded on the line, then the last
        purchase price. It never falls back to zero - a part that leaves the
        shelf at no cost silently overstates the inventory forever.
        """
        pwc = ProductWarehouseCost.query.filter_by(
            tenant_id=tenant_id,
            product_id=product_id,
            warehouse_id=warehouse_id,
        ).first()
        if pwc and pwc.total_quantity and pwc.total_quantity > 0:
            average = Decimal(str(pwc.average_cost or 0))
            if average > 0:
                return average.quantize(_COST_QUANTUM, rounding=ROUND_HALF_UP), "mwac"

        if line_cost_price and Decimal(str(line_cost_price)) > 0:
            return Decimal(str(line_cost_price)).quantize(_COST_QUANTUM, rounding=ROUND_HALF_UP), "cost_price"

        from models import ProductCostHistory

        last_purchase = (
            ProductCostHistory.query.filter_by(
                tenant_id=tenant_id,
                product_id=product_id,
                warehouse_id=warehouse_id,
                movement_type="purchase",
            )
            .order_by(ProductCostHistory.created_at.desc())
            .first()
        )
        if last_purchase and last_purchase.movement_unit_cost and last_purchase.movement_unit_cost > 0:
            return (
                Decimal(str(last_purchase.movement_unit_cost)).quantize(_COST_QUANTUM, rounding=ROUND_HALF_UP),
                "last_purchase",
            )

        raise GlPostingError(
            gettext(
                "لا يمكن تحديد تكلفة القطعة {product_id}: لا يوجد متوسط تكلفة في المستودع "
                "ولا سجل شراء سابق. يرجى توريد المخزون أو ضبط تكلفة المنتج."
            ).format(product_id=product_id)
        )

    # ── consumption ──────────────────────────────────────────────────────
    @staticmethod
    def consume_parts_for_order_line(
        line: MaintenanceOrderLine,
        user_id: int,
    ) -> StockMovement:
        """استهلاك قطع من مستودع الصيانة عند إغلاق أمر الصيانة.

        الحركة تُنشأ عبر ``StockService.create_movement``، وهي المسار نفسه
        الذي يستخدمه البيع: قفل صف حصة المخزون، منع الرصيد السالب، ومزامنة
        ``Product.current_stock``. التكلفة تُؤخذ من المتوسط المتحرك المرجح
        وتُسجَّل في سجل تاريخ التكلفة.
        """
        if line is None:
            raise ValueError(gettext("لا يمكن صرف قطع بدون سطر أمر صيانة"))
        tid = line.tenant_id
        order = line.order
        if order is None:
            raise GlPostingError(gettext("سطر الصيانة غير مرتبط بأمر"))

        warehouse_id = line.warehouse_id or order.warehouse_id
        if not warehouse_id:
            raise GlPostingError(gettext("أمر الصيانة لا يحتوي على مستودع"))

        product = tenant_query(Product).filter_by(id=line.product_id, tenant_id=tid).first()
        if not product:
            raise GlPostingError(gettext("المنتج غير موجود"))

        warehouse = tenant_query(Warehouse).filter_by(id=warehouse_id, tenant_id=tid).first()
        if not warehouse:
            raise GlPostingError(gettext("المستودع غير موجود"))

        qty = Decimal(str(line.quantity or 0))
        if qty <= 0:
            raise GlPostingError(gettext("كمية صرف القطع غير صالحة"))

        unit_cost, cost_source = MaintenanceStockService._resolve_unit_cost(
            product.id, warehouse.id, tid, line_cost_price=line.cost_price
        )

        movement = StockService.create_movement(
            product_id=product.id,
            quantity=-qty,
            movement_type=MAINTENANCE_MOVEMENT_TYPE,
            reference_type=GLRef.MAINTENANCE,
            reference_id=order.id,
            notes=gettext("صرف قطع لأمر صيانة {order_number}").format(order_number=order.order_number),
            warehouse_id=warehouse.id,
            resolved_product=product,
            resolved_warehouse=warehouse,
        )
        if movement.user_id is None:
            movement.user_id = user_id

        # Batch consumption (FEFO) when the tenant has batches enabled: the
        # part leaves the shelf from the lot that expires first.
        if StockBatchService.batches_enabled():
            consumed_qty, consumed_value = StockBatchService.consume_fefo(
                product_id=product.id,
                warehouse_id=warehouse.id,
                quantity=qty,
                tenant_id=tid,
            )
            if consumed_qty > 0 and consumed_qty < qty:
                # Partial: the remainder is priced at the moving average.
                remainder = unit_cost * (qty - consumed_qty)
                unit_cost = ((consumed_value + remainder) / qty).quantize(_COST_QUANTUM, rounding=ROUND_HALF_UP)
            elif consumed_qty > 0:
                unit_cost = (consumed_value / qty).quantize(_COST_QUANTUM, rounding=ROUND_HALF_UP)

        total_cost = (unit_cost * qty).quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)

        MaintenanceStockService._apply_mwac_outflow(
            tenant_id=tid,
            product_id=product.id,
            warehouse_id=warehouse.id,
            quantity=qty,
            unit_cost=unit_cost,
            movement=movement,
        )

        line.movement_id = movement.id
        line.cost_price = unit_cost
        line.cost_aed = total_cost

        # Serial trace: if the part is serial-tracked, the individual units
        # that left the shelf are recorded against the line. A product
        # with no serials registered returns an empty list, and the
        # quantity alone describes what was consumed - the same contract
        # the trade path uses.
        try:
            issued_serials = SerialTrackingService.issue_serials(
                product_id=product.id,
                warehouse_id=warehouse.id,
                quantity=int(qty) if qty == qty.to_integral_value() else 0,
                tenant_id=tid,
                reference_type="maintenance",
                reference_id=line.id,
            )
        except Exception:
            logger.debug("Serial tracking unavailable for maintenance line %s", line.id, exc_info=True)
            issued_serials = []
        if issued_serials:
            line.serial_numbers = issued_serials

        db.session.flush()

        log_financial(
            message=(
                f"Maintenance stock consumed: product {product.id} qty {qty} "
                f"for order {order.order_number} cost {total_cost}"
            ),
            tenant_id=tid,
            level="INFO",
            source="services.maintenance_stock_service.MaintenanceStockService.consume_parts_for_order_line",
            extra={
                "order_id": order.id,
                "tenant_id": tid,
                "product_id": product.id,
                "warehouse_id": warehouse.id,
                "qty": float(qty),
                "unit_cost": float(unit_cost),
                "cost": float(total_cost),
                "cost_source": cost_source,
            },
        )

        return movement

    @staticmethod
    def _apply_mwac_outflow(
        *,
        tenant_id: int,
        product_id: int,
        warehouse_id: int,
        quantity: Decimal,
        unit_cost: Decimal,
        movement: StockMovement,
    ) -> None:
        """Move the warehouse's moving average down and record the change."""
        query = ProductWarehouseCost.query.filter_by(
            tenant_id=tenant_id,
            product_id=product_id,
            warehouse_id=warehouse_id,
        )
        pwc = _safe_for_update(query, label=f"PWC maintenance p={product_id} w={warehouse_id}")
        old_qty = Decimal(str(pwc.total_quantity)) if pwc and pwc.total_quantity is not None else Decimal("0")
        old_value = Decimal(str(pwc.total_value)) if pwc and pwc.total_value is not None else Decimal("0")
        old_avg = Decimal(str(pwc.average_cost)) if pwc and pwc.average_cost is not None else Decimal("0")

        new_qty = old_qty - quantity
        new_value = old_value - (quantity * unit_cost)
        if new_qty > 0:
            new_avg = (new_value / new_qty).quantize(_COST_QUANTUM, rounding=ROUND_HALF_UP)
        else:
            new_avg = Decimal("0")
            new_value = Decimal("0")

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
                movement_type=MAINTENANCE_MOVEMENT_TYPE,
                movement_id=movement.id,
                reference_type=GLRef.MAINTENANCE,
                reference_id=movement.reference_id,
                old_average_cost=old_avg,
                new_average_cost=new_avg,
                quantity_change=-quantity,
                old_total_quantity=old_qty,
                new_total_quantity=new_qty,
                old_total_value=old_value,
                new_total_value=new_value,
                movement_unit_cost=unit_cost,
            )
        )
        db.session.flush()

    # ── returns ──────────────────────────────────────────────────────────
    @staticmethod
    def return_parts_for_return_line(
        return_line: MaintenanceReturnLine,
        user_id: int,
    ) -> StockMovement:
        """إرجاع قطع إلى مستودع الصيانة عند مرتجع الصيانة.

        القطعة تعود بنفس التكلفة التي خرجت بها، فيعود متوسط التكلفة إلى
        ما كان عليه وتُسجَّل الحركة في سجل تاريخ التكلفة.
        """
        if return_line is None:
            raise ValueError(gettext("لا يمكن إرجاع قطع بدون سطر مرتجع"))
        tid = return_line.tenant_id
        order_line = return_line.order_line
        if not order_line:
            raise GlPostingError(gettext("سطر المرتجع غير مرتبط بسطر الأمر"))

        order = order_line.order
        warehouse_id = order_line.warehouse_id or (order.warehouse_id if order else None)
        if not warehouse_id:
            raise GlPostingError(gettext("سطر الأمر لا يحتوي على مستودع"))

        product = tenant_query(Product).filter_by(id=order_line.product_id, tenant_id=tid).first()
        if not product:
            raise GlPostingError(gettext("المنتج غير موجود"))

        warehouse = tenant_query(Warehouse).filter_by(id=warehouse_id, tenant_id=tid).first()
        if not warehouse:
            raise GlPostingError(gettext("المستودع غير موجود"))

        qty = Decimal(str(return_line.quantity or 0))
        if qty <= 0:
            raise GlPostingError(gettext("كمية إرجاع القطع غير صالحة"))

        # The part goes back at the cost it left the shelf at.
        unit_cost = Decimal(str(order_line.cost_price or 0))
        if unit_cost <= 0:
            unit_cost, _source = MaintenanceStockService._resolve_unit_cost(product.id, warehouse.id, tid)
        unit_cost = unit_cost.quantize(_COST_QUANTUM, rounding=ROUND_HALF_UP)
        total_cost = (unit_cost * qty).quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)

        movement = StockService.create_movement(
            product_id=product.id,
            quantity=qty,
            movement_type=MAINTENANCE_RETURN_MOVEMENT_TYPE,
            reference_type=GLRef.MAINTENANCE_RETURN,
            reference_id=return_line.return_id,
            notes=gettext("إرجاع قطع من أمر صيانة {order_number}").format(
                order_number=order.order_number if order else ""
            ),
            warehouse_id=warehouse.id,
            resolved_product=product,
            resolved_warehouse=warehouse,
        )
        if movement.user_id is None:
            movement.user_id = user_id

        if StockBatchService.batches_enabled():
            StockBatchService.restore_on_reversal(
                tenant_id=tid,
                product_id=product.id,
                warehouse_id=warehouse.id,
                quantity=qty,
                unit_cost=unit_cost,
                reference_id=return_line.return_id,
            )

        MaintenanceStockService._apply_mwac_inflow(
            tenant_id=tid,
            product_id=product.id,
            warehouse_id=warehouse.id,
            quantity=qty,
            unit_cost=unit_cost,
            movement=movement,
        )

        return_line.unit_cost = unit_cost
        return_line.line_total_cost = total_cost

        # The parts went back on the shelf, so their serials are
        # available again.
        if order_line.serial_numbers:
            try:
                SerialTrackingService.restore_serials(
                    order_line.serial_numbers,
                    tenant_id=tid,
                )
            except Exception:
                logger.debug("Serial restore unavailable for maintenance return", exc_info=True)

        db.session.flush()

        log_financial(
            message=(
                f"Maintenance stock returned: product {product.id} qty {qty} "
                f"for return {return_line.return_id} cost {total_cost}"
            ),
            tenant_id=tid,
            level="INFO",
            source="services.maintenance_stock_service.MaintenanceStockService.return_parts_for_return_line",
            extra={
                "return_id": return_line.return_id,
                "tenant_id": tid,
                "product_id": product.id,
                "warehouse_id": warehouse.id,
                "qty": float(qty),
                "cost": float(total_cost),
            },
        )

        return movement

    @staticmethod
    def _apply_mwac_inflow(
        *,
        tenant_id: int,
        product_id: int,
        warehouse_id: int,
        quantity: Decimal,
        unit_cost: Decimal,
        movement: StockMovement,
    ) -> None:
        """Move the warehouse's moving average back up and record the change."""
        query = ProductWarehouseCost.query.filter_by(
            tenant_id=tenant_id,
            product_id=product_id,
            warehouse_id=warehouse_id,
        )
        pwc = _safe_for_update(query, label=f"PWC maintenance return p={product_id} w={warehouse_id}")
        old_qty = Decimal(str(pwc.total_quantity)) if pwc and pwc.total_quantity is not None else Decimal("0")
        old_value = Decimal(str(pwc.total_value)) if pwc and pwc.total_value is not None else Decimal("0")
        old_avg = Decimal(str(pwc.average_cost)) if pwc and pwc.average_cost is not None else Decimal("0")

        new_qty = old_qty + quantity
        new_value = old_value + (quantity * unit_cost)
        new_avg = (
            (new_value / new_qty).quantize(_COST_QUANTUM, rounding=ROUND_HALF_UP) if new_qty != 0 else Decimal("0")
        )

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
                movement_type=MAINTENANCE_RETURN_MOVEMENT_TYPE,
                movement_id=movement.id,
                reference_type=GLRef.MAINTENANCE_RETURN,
                reference_id=movement.reference_id,
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
