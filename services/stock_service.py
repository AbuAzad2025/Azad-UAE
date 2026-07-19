import logging
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone
from flask import current_app
from flask_login import current_user

logger = logging.getLogger(__name__)
from sqlalchemy.exc import OperationalError
from extensions import db
from models import (
    Product,
    StockMovement,
    Warehouse,
    ProductWarehouseCost,
    ProductCostHistory,
)
from models.warehouse import ProductWarehouseStock
from utils.branching import get_accessible_warehouse_ids, get_branch_stock_map
from utils.gl_reference_types import GLRef

_MAX_LOCK_RETRIES = 3


def _safe_for_update(query, label="row"):
    """Execute SELECT … FOR UPDATE with savepoint-based retry.

    Uses savepoints so that a failed lock attempt does NOT roll back the
    caller's entire transaction.  On final failure, aborts — never silently
    drops the lock.

    Rationale: The previous try/except pattern silently fell back to an unlocked
    read when the lock could not be acquired, opening the door to MWAC race
    conditions where two concurrent transactions read the same old cost and
    both update it incorrectly ("floating costs").
    """
    for attempt in range(1, _MAX_LOCK_RETRIES + 1):
        savepoint = db.session.begin_nested()
        try:
            result = query.with_for_update().first()
            savepoint.commit()
            return result
        except OperationalError:
            savepoint.rollback()
            if attempt == _MAX_LOCK_RETRIES:
                current_app.logger.critical(
                    "Row-level lock acquisition failed after %d attempts for %s — aborting to prevent MWAC race condition.",
                    _MAX_LOCK_RETRIES,
                    label,
                )
                raise
            current_app.logger.warning(
                "Lock contention on %s (attempt %d/%d) — retrying.",
                label,
                attempt,
                _MAX_LOCK_RETRIES,
            )
    raise RuntimeError(f"Failed to acquire row lock for {label}")


class _MWACHelper:
    """Pure MWAC math — no DB, no models, no side effects."""

    @staticmethod
    def calc(
        old_qty: Decimal, old_value: Decimal, change_qty: Decimal, unit_cost: Decimal
    ) -> tuple[Decimal, Decimal, Decimal]:
        new_qty = old_qty + change_qty
        new_value = old_value + (change_qty * unit_cost)
        new_avg: Decimal = (
            (new_value / new_qty).quantize(Decimal("0.0001"))
            if new_qty != 0
            else Decimal("0")
        )
        return new_qty, new_value, new_avg


def _resolve_gl_concept_account(concept_code, fallback_account_code, tenant_id=None):
    from services.gl_service import GL_ACCOUNTS, GL_ACCOUNT_CONCEPTS
    from services.gl_account_resolver import (
        resolve_gl_account,
        is_dynamic_gl_mapping_enabled,
    )

    if is_dynamic_gl_mapping_enabled() and tenant_id:
        try:
            resolved = resolve_gl_account(
                tenant_id=tenant_id, concept_code=concept_code
            )
            if resolved:
                return resolved.account_code
        except Exception:
            logger.warning("Dynamic GL mapping failed for concept %s, falling back to static", concept_code, exc_info=True)
    concept_key = {v: k for k, v in GL_ACCOUNT_CONCEPTS.items()}.get(concept_code)
    if concept_key and concept_key in GL_ACCOUNTS:
        return GL_ACCOUNTS[concept_key]
    return fallback_account_code


class StockService:
    @staticmethod
    def _mwac_calc(old_qty, old_value, change_qty, unit_cost):
        return _MWACHelper.calc(old_qty, old_value, change_qty, unit_cost)

    @staticmethod
    def add_stock(
        product_id,
        quantity,
        reference_type=None,
        reference_id=None,
        notes=None,
        warehouse_id=None,
    ):
        return StockService.create_movement(
            product_id=product_id,
            quantity=abs(Decimal(str(quantity))),
            movement_type="purchase",
            reference_type=reference_type,
            reference_id=reference_id,
            notes=notes,
            warehouse_id=warehouse_id,
        )

    @staticmethod
    def remove_stock(
        product_id,
        quantity,
        reference_type=None,
        reference_id=None,
        notes=None,
        warehouse_id=None,
    ):
        return StockService.create_movement(
            product_id=product_id,
            quantity=-abs(Decimal(str(quantity))),
            movement_type="sale",
            reference_type=reference_type,
            reference_id=reference_id,
            notes=notes,
            warehouse_id=warehouse_id,
        )

    @staticmethod
    def _post_adjustment_gl(movement):
        from services.gl_posting import post_or_fail
        from services.gl_service import GLService

        product = db.session.get(Product, movement.product_id)
        if not product or not product.cost_price:
            return
        cost_value = abs(Decimal(str(movement.quantity))) * Decimal(
            str(product.cost_price)
        )
        if cost_value <= 0:
            return
        warehouse = (
            db.session.get(Warehouse, movement.warehouse_id)
            if getattr(movement, "warehouse_id", None)
            else None
        )
        tenant_id = getattr(movement, "tenant_id", None) or getattr(
            product, "tenant_id", None
        )
        loss_account = _resolve_gl_concept_account(
            "INVENTORY_ADJUSTMENT_LOSS", "5150", tenant_id
        )
        asset_account = _resolve_gl_concept_account(
            "INVENTORY_ASSET", "1140", tenant_id
        )
        gain_account = _resolve_gl_concept_account(
            "INVENTORY_ADJUSTMENT_GAIN", "5150", tenant_id
        )

        if Decimal(str(movement.quantity)) < 0:
            lines = [
                {
                    "account": loss_account,
                    "concept_code": "INVENTORY_ADJUSTMENT_LOSS",
                    "debit": cost_value,
                    "credit": 0,
                    "description": f"Inventory Adjustment (Loss) - {product.name}",
                },
                {
                    "account": asset_account,
                    "concept_code": "INVENTORY_ASSET",
                    "debit": 0,
                    "credit": cost_value,
                    "description": f"Stock Decrease - {product.name}",
                },
            ]
        else:
            lines = [
                {
                    "account": asset_account,
                    "concept_code": "INVENTORY_ASSET",
                    "debit": cost_value,
                    "credit": 0,
                    "description": f"Stock Increase - {product.name}",
                },
                {
                    "account": gain_account,
                    "concept_code": "INVENTORY_ADJUSTMENT_GAIN",
                    "debit": 0,
                    "credit": cost_value,
                    "description": f"Inventory Adjustment (Gain) - {product.name}",
                },
            ]
        branch_id = warehouse.branch_id if warehouse else None
        GLService.ensure_core_accounts(tenant_id=tenant_id)
        post_or_fail(
            lines=lines,
            description=f"Stock Adjustment - {product.name}",
            reference_type=movement.reference_type or GLRef.STOCK_ADJUSTMENT,
            reference_id=movement.id,
            branch_id=branch_id,
            tenant_id=tenant_id,
        )

    @staticmethod
    def adjust_stock(
        product_id,
        quantity,
        notes=None,
        warehouse_id=None,
        reference_type=None,
        reference_id=None,
    ):
        try:
            movement = StockService.create_movement(
                product_id=product_id,
                quantity=Decimal(str(quantity)),
                movement_type="adjustment",
                notes=notes,
                warehouse_id=warehouse_id,
                reference_type=reference_type or GLRef.STOCK_ADJUSTMENT,
                reference_id=reference_id,
            )
            StockService._post_adjustment_gl(movement)
            return movement
        except Exception as e:
            current_app.logger.error(f"Failed stock adjustment: {e}")
            raise

    @staticmethod
    def add_opening_stock(
        product_id, quantity, notes=None, warehouse_id=None, cost_price=None
    ):
        movement = StockService.create_movement(
            product_id=product_id,
            quantity=Decimal(str(quantity)),
            movement_type="purchase",
            notes=notes or "مخزون افتتاحي",
            warehouse_id=warehouse_id,
            reference_type=GLRef.PRODUCT_CREATION,
        )
        from services.gl_posting import post_or_fail
        from services.gl_service import GLService
        from models import Product, Warehouse

        product = db.session.get(Product, product_id)
        warehouse = db.session.get(Warehouse, warehouse_id) if warehouse_id else None
        if product and product.cost_price:
            cost_value = Decimal(str(quantity)) * Decimal(str(product.cost_price))
            if cost_value > 0:
                tenant_id = getattr(product, "tenant_id", None)
                asset_account = _resolve_gl_concept_account(
                    "INVENTORY_ASSET", "1140", tenant_id
                )
                equity_account = _resolve_gl_concept_account(
                    "OPENING_BALANCE_EQUITY", "3130", tenant_id
                )
                GLService.ensure_core_accounts(tenant_id=tenant_id)
                post_or_fail(
                    lines=[
                        {
                            "account": asset_account,
                            "concept_code": "INVENTORY_ASSET",
                            "debit": cost_value,
                            "credit": 0,
                            "description": f"مخزون افتتاحي - {product.name}",
                        },
                        {
                            "account": equity_account,
                            "concept_code": "OPENING_BALANCE_EQUITY",
                            "debit": 0,
                            "credit": cost_value,
                            "description": f"مخزون افتتاحي - {product.name}",
                        },
                    ],
                    description=f"مخزون افتتاحي - {product.name}",
                    reference_type=GLRef.PRODUCT_CREATION,
                    reference_id=product.id,
                    branch_id=warehouse.branch_id if warehouse else None,
                    tenant_id=tenant_id,
                )
        return movement

    @staticmethod
    def create_movement(
        product_id,
        quantity,
        movement_type,
        reference_type=None,
        reference_id=None,
        notes=None,
        warehouse_id=None,
    ):
        from utils.field_validators import validate_stock_movement_type

        movement_type = validate_stock_movement_type(movement_type)
        qty = Decimal(str(quantity))
        try:
            product = db.session.get(Product, product_id)

            if not product:
                raise ValueError(
                    f"⚠️ المنتج غير موجود (ID: {product_id}).\n💡 تأكد من اختيار منتج صحيح من القائمة."
                )

            try:
                user_id = (
                    current_user.id
                    if current_user and current_user.is_authenticated
                    else None
                )
            except Exception:
                current_app.logger.debug(
                    "Could not resolve current_user.id for stock movement"
                )
                user_id = None

            tenant_id = getattr(product, "tenant_id", None)

            # تحديد المستودع
            if warehouse_id:
                warehouse = Warehouse.query.filter_by(
                    id=warehouse_id, is_active=True
                ).first()
                if not warehouse:
                    raise ValueError(
                        f"⚠️ المستودع المحدد غير موجود أو غير نشط (ID: {warehouse_id})."
                    )
                if (
                    tenant_id is not None
                    and getattr(warehouse, "tenant_id", None) is not None
                    and warehouse.tenant_id != tenant_id
                ):
                    raise ValueError(
                        f"⚠️ المستودع (ID: {warehouse_id}) لا ينتمي لنفس شركة المنتج."
                    )
            else:
                warehouse = Warehouse.query.filter_by(
                    tenant_id=tenant_id, is_active=True, is_main=True
                ).first()
                if not warehouse:
                    warehouse = Warehouse.query.filter_by(
                        tenant_id=tenant_id, is_active=True
                    ).first()

                if not warehouse:
                    warehouse = Warehouse(
                        name="Main Warehouse",
                        name_ar="المستودع الرئيسي",
                        is_active=True,
                        is_main=True,
                        tenant_id=tenant_id,
                    )
                    db.session.add(warehouse)
                    db.session.flush()

            if getattr(warehouse, "tenant_id", None) is None and tenant_id is not None:
                warehouse.tenant_id = tenant_id

            movement = StockMovement(
                tenant_id=tenant_id,
                product_id=product_id,
                warehouse_id=warehouse.id,
                movement_type=movement_type,
                quantity=qty,
                reference_type=reference_type,
                reference_id=reference_id,
                user_id=user_id,
                notes=notes,
            )

            db.session.add(movement)

            # Update ProductWarehouseStock (per-warehouse tracking) with row lock
            q_pws = ProductWarehouseStock.query.filter_by(
                tenant_id=tenant_id,
                product_id=product_id,
                warehouse_id=warehouse.id,
            )
            pws = _safe_for_update(q_pws, label=f"PWS p={product_id} w={warehouse.id}")
            if pws:
                new_qty_pws = pws.quantity + qty
                if new_qty_pws < 0 and not warehouse.allow_negative_inventory:
                    raise ValueError(
                        f'❌ المخزون غير كافٍ في المستودع للمنتج "{product.name}"!\n'
                        f"📦 المتوفر في المستودع: {pws.quantity} | المطلوب: {abs(qty)}\n"
                        f"💡 قلل الكمية أو انقل مخزوناً من مستودع آخر."
                    )
                pws.quantity = new_qty_pws
                pws.updated_at = datetime.now(timezone.utc)
            else:
                if qty < 0 and not warehouse.allow_negative_inventory:
                    raise ValueError(
                        f'❌ المخزون غير كافٍ في المستودع للمنتج "{product.name}"!\n'
                        f"📦 المتوفر في المستودع: 0 | المطلوب: {abs(qty)}\n"
                        f"💡 أضف مخزوناً أولاً."
                    )
                pws = ProductWarehouseStock(
                    tenant_id=tenant_id,
                    product_id=product_id,
                    warehouse_id=warehouse.id,
                    quantity=qty,
                )
                db.session.add(pws)

            # Sync Product.current_stock from PWS aggregate to eliminate drift.
            # This ensures current_stock always reflects the true sum of all
            # per-warehouse quantities, preventing desync.
            StockService._sync_current_stock(product)

            if product.current_stock < 0 and not warehouse.allow_negative_inventory:
                raise ValueError(
                    f'❌ المخزون غير كافٍ للمنتج "{product.name}"!\n📦 المتوفر: {product.current_stock} | المطلوب: {quantity}\n💡 قلل الكمية أو اطلب مخزون جديد من المورد.'
                )

            try:
                current_app.logger.info(
                    f"Stock movement: {movement_type} {quantity} of product #{product_id}"
                )
            except Exception:
                logger.warning("Failed to log stock movement info for product #%s", product_id, exc_info=True)

            return movement

        except Exception as e:
            current_app.logger.error(f"Stock movement failed: {e}")
            raise

    @staticmethod
    def transfer_stock(
        product_id, from_warehouse_id, to_warehouse_id, quantity, notes=None, user=None
    ):
        """Transfer quantity between warehouses (net zero on product.current_stock)."""
        qty = abs(Decimal(str(quantity)))
        if qty <= 0:
            raise ValueError("الكمية يجب أن تكون أكبر من صفر.")

        product = db.session.get(Product, product_id)
        if not product:
            raise ValueError("المنتج غير موجود.")
        tenant_id = getattr(product, "tenant_id", None)

        from_wh = Warehouse.query.filter_by(
            id=int(from_warehouse_id), is_active=True
        ).first()
        to_wh = Warehouse.query.filter_by(
            id=int(to_warehouse_id), is_active=True
        ).first()
        if not from_wh or not to_wh:
            raise ValueError("المستودع المصدر أو الوجهة غير موجود أو غير نشط.")
        if from_wh.id == to_wh.id:
            raise ValueError("لا يمكن التحويل إلى نفس المستودع.")

        # التحقق من التينانت
        if tenant_id is not None:
            wh_tenant_ids = [
                getattr(from_wh, "tenant_id", None),
                getattr(to_wh, "tenant_id", None),
            ]
            if tenant_id not in wh_tenant_ids:
                raise ValueError(
                    "المنتج لا ينتمي إلى نفس المستودع (تعارض في التينانت)."
                )
            if from_wh.tenant_id != tenant_id or to_wh.tenant_id != tenant_id:
                raise ValueError(
                    "المستودع المصدر والوجهة يجب أن ينتميان لنفس شركة المنتج."
                )

        # التحقق من صلاحية المستخدم - إذا تم تمرير مستخدم
        if user is not None:
            from utils.auth_helpers import is_global_owner_user

            if not is_global_owner_user(user):
                from utils.branching import get_accessible_warehouse_ids

                accessible = get_accessible_warehouse_ids(user)
                if accessible and (
                    from_wh.id not in accessible or to_wh.id not in accessible
                ):
                    raise ValueError("ليس لديك صلاحية الوصول لأحد المستودعين.")

        available = StockService.get_product_stock(product_id, warehouse_id=from_wh.id)
        if available < qty:
            raise ValueError(
                f"الكمية غير متوفرة في المستودع المصدر (المتوفر: {available})."
            )

        label = (
            notes
            or f"تحويل من {from_wh.name_ar or from_wh.name} إلى {to_wh.name_ar or to_wh.name}"
        )
        out_movement = StockService.create_movement(
            product_id=product_id,
            quantity=-qty,
            movement_type="transfer",
            reference_type=GLRef.STOCK_TRANSFER,
            notes=label,
            warehouse_id=from_wh.id,
        )
        in_movement = StockService.create_movement(
            product_id=product_id,
            quantity=qty,
            movement_type="transfer",
            reference_type=GLRef.STOCK_TRANSFER,
            reference_id=out_movement.id,
            notes=label,
            warehouse_id=to_wh.id,
        )
        return out_movement, in_movement

    @staticmethod
    def _sync_current_stock(product):
        """
        Reconcile Product.current_stock against the PWS aggregate sum.
        Called after every stock mutation to eliminate data drift between
        per-warehouse tracking and the global stock column.
        """
        from sqlalchemy import func

        total = (
            db.session.query(func.coalesce(func.sum(ProductWarehouseStock.quantity), 0))
            .filter(
                ProductWarehouseStock.product_id == product.id,
                ProductWarehouseStock.tenant_id == product.tenant_id,
            )
            .scalar()
        )
        product.current_stock = Decimal(str(total))

    @staticmethod
    def process_sale_lines(sale, warehouse_id=None):
        """معالجة بيوع مع خصم من مستودع محدد"""
        # استخدام warehouse_id من sale إذا لم يُمرر
        if not warehouse_id and hasattr(sale, "warehouse_id"):
            warehouse_id = sale.warehouse_id

        for line in sale.lines:
            StockService.remove_stock(
                product_id=line.product_id,
                quantity=line.quantity,
                reference_type=GLRef.SALE,
                reference_id=sale.id,
                notes=f"بيع: {sale.sale_number}",
                warehouse_id=warehouse_id,  # ← تمرير المستودع
            )

    @staticmethod
    def _resolve_cogs_unit_cost(
        product_id, warehouse_id, tenant_id, line_cost_price=None
    ):
        """Resolve unit cost for COGS using Odoo-style fallback chain:
        1. ProductWarehouseCost.average_cost (if stock > 0)
        2. SaleLine.cost_price
        3. Last purchase price from ProductCostHistory
        4. Raise error if all fail — never silently post COGS=0.
        """
        pwc = ProductWarehouseCost.query.filter_by(
            tenant_id=tenant_id,
            product_id=product_id,
            warehouse_id=warehouse_id,
        ).first()
        if (
            pwc
            and pwc.total_quantity > 0
            and pwc.average_cost
            and pwc.average_cost > Decimal("0")
        ):
            return pwc.average_cost, "mwac"
        if line_cost_price:
            cost = Decimal(str(line_cost_price))
            if cost > Decimal("0"):
                return cost, "cost_price"
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
        if (
            last_purchase
            and last_purchase.movement_unit_cost
            and last_purchase.movement_unit_cost > Decimal("0")
        ):
            return Decimal(str(last_purchase.movement_unit_cost)), "last_purchase"
        raise ValueError(
            f"لا يمكن تحديد تكلفة البضاعة المباعة (COGS) للمنتج {product_id}: "
            "لا يوجد مخزون، ولا سعر تكلفة، ولا سجل شراء سابق. "
            "يرجى إدخال تكلفة المنتج أو توريد مخزون قبل البيع."
        )

    @staticmethod
    def calculate_sale_cogs_and_deduct(sale, warehouse_id=None):
        """
        Compute COGS using MWAC, deduct stock, update PWC, create audit trail.
        Returns total COGS in AED (Decimal).
        Falls back to SaleLine.cost_price when ENABLE_MWAC is False.
        Never silently posts COGS=0 — raises error if cost cannot be resolved.

        Negative inventory support:
        - If warehouse allows negative inventory, COGS is calculated using the best
          available cost (MWAC, last purchase, or cost_price) and PWC is updated
          even if quantity goes negative. This preserves the cost for future
          retrospective adjustment when the purchase arrives.
        """
        from datetime import datetime, timezone

        if not warehouse_id and hasattr(sale, "warehouse_id"):
            warehouse_id = sale.warehouse_id

        tenant_id = getattr(sale, "tenant_id", None)
        mwac_enabled = current_app.config.get("ENABLE_MWAC", False)
        total_cogs = Decimal("0")

        # Determine if negative inventory is allowed for this warehouse
        warehouse = db.session.get(Warehouse, warehouse_id) if warehouse_id else None
        allow_negative = (
            getattr(warehouse, "allow_negative_inventory", False)
            if warehouse
            else False
        )

        for line in sale.lines:
            qty = Decimal(str(line.quantity))

            pwc = None
            if mwac_enabled and tenant_id and warehouse_id:
                query = ProductWarehouseCost.query.filter_by(
                    tenant_id=tenant_id,
                    product_id=line.product_id,
                    warehouse_id=warehouse_id,
                )
                pwc = _safe_for_update(
                    query, label=f"PWC p={line.product_id} w={warehouse_id}"
                )

            if pwc and pwc.total_quantity > 0:
                # Normal positive-stock case
                avg_cost = (
                    Decimal(str(pwc.average_cost))
                    if pwc.average_cost is not None
                    else Decimal("0")
                )
                cogs = (avg_cost * qty).quantize(
                    Decimal("0.001"), rounding=ROUND_HALF_UP
                )
                old_qty = (
                    Decimal(str(pwc.total_quantity))
                    if pwc.total_quantity is not None
                    else Decimal("0")
                )
                old_value = (
                    Decimal(str(pwc.total_value))
                    if pwc.total_value is not None
                    else Decimal("0")
                )
                old_avg = avg_cost
                new_qty, new_value, new_avg = StockService._mwac_calc(
                    old_qty, old_value, -qty, avg_cost.quantize(Decimal("0.0001"))
                )
                pwc.total_quantity = new_qty
                pwc.total_value = new_value
                pwc.average_cost = new_avg.quantize(Decimal("0.0001"))
                pwc.last_updated = datetime.now(timezone.utc)
                pch = ProductCostHistory(
                    tenant_id=tenant_id,
                    product_id=line.product_id,
                    warehouse_id=warehouse_id,
                    movement_type="sale",
                    reference_type=GLRef.SALE,
                    reference_id=sale.id,
                    old_average_cost=old_avg.quantize(Decimal("0.0001")),
                    new_average_cost=pwc.average_cost,
                    quantity_change=-qty,
                    old_total_quantity=old_qty,
                    new_total_quantity=new_qty,
                    old_total_value=old_value,
                    new_total_value=new_value,
                    movement_unit_cost=avg_cost.quantize(Decimal("0.0001")),
                )
                db.session.add(pch)
            elif allow_negative:
                avg_cost, source = StockService._resolve_cogs_unit_cost(
                    line.product_id,
                    warehouse_id,
                    tenant_id,
                    line_cost_price=line.cost_price,
                )
                cogs = (avg_cost * qty).quantize(
                    Decimal("0.001"), rounding=ROUND_HALF_UP
                )
                current_app.logger.warning(
                    "Negative inventory sale (%s) for product %s sale %s: unit_cost=%s, qty=%s",
                    source,
                    line.product_id,
                    sale.sale_number,
                    avg_cost,
                    qty,
                )

                if pwc:
                    old_qty = (
                        Decimal(str(pwc.total_quantity))
                        if pwc.total_quantity is not None
                        else Decimal("0")
                    )
                    old_value = (
                        Decimal(str(pwc.total_value))
                        if pwc.total_value is not None
                        else Decimal("0")
                    )
                    old_avg = (
                        Decimal(str(pwc.average_cost))
                        if pwc.average_cost is not None
                        else Decimal("0")
                    )
                    new_qty, new_value, new_avg = StockService._mwac_calc(
                        old_qty, old_value, -qty, avg_cost.quantize(Decimal("0.0001"))
                    )
                    pwc.total_quantity = new_qty
                    pwc.total_value = new_value
                    pwc.average_cost = new_avg.quantize(Decimal("0.0001"))
                    pwc.last_updated = datetime.now(timezone.utc)
                else:
                    # Create PWC with negative quantity (first negative sale for this product+warehouse)
                    old_qty = Decimal("0")
                    old_value = Decimal("0")
                    old_avg = None
                    new_qty = -qty
                    new_value = -(qty * avg_cost)
                    new_avg = avg_cost

                    pwc = ProductWarehouseCost(
                        tenant_id=tenant_id,
                        product_id=line.product_id,
                        warehouse_id=warehouse_id,
                        total_quantity=new_qty,
                        total_value=new_value,
                        average_cost=new_avg.quantize(Decimal("0.0001")),
                    )
                    db.session.add(pwc)

                pch = ProductCostHistory(
                    tenant_id=tenant_id,
                    product_id=line.product_id,
                    warehouse_id=warehouse_id,
                    movement_type="sale",
                    reference_type=GLRef.SALE,
                    reference_id=sale.id,
                    old_average_cost=(
                        old_avg.quantize(Decimal("0.0001"))
                        if old_avg is not None
                        else None
                    ),
                    new_average_cost=pwc.average_cost,
                    quantity_change=-qty,
                    old_total_quantity=old_qty,
                    new_total_quantity=new_qty,
                    old_total_value=old_value,
                    new_total_value=new_value,
                    movement_unit_cost=avg_cost.quantize(Decimal("0.0001")),
                )
                db.session.add(pch)
            else:
                avg_cost, source = StockService._resolve_cogs_unit_cost(
                    line.product_id,
                    warehouse_id,
                    tenant_id,
                    line_cost_price=line.cost_price,
                )
                cogs = (avg_cost * qty).quantize(
                    Decimal("0.001"), rounding=ROUND_HALF_UP
                )
                current_app.logger.warning(
                    "COGS resolved via fallback (%s) for product %s sale %s: unit_cost=%s",
                    source,
                    line.product_id,
                    sale.sale_number,
                    avg_cost,
                )

            total_cogs += cogs

        return total_cogs.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    @staticmethod
    def process_purchase_lines(purchase, warehouse_id=None):
        if not warehouse_id and hasattr(purchase, "warehouse_id"):
            warehouse_id = purchase.warehouse_id

        tenant_id = getattr(purchase, "tenant_id", None)
        mwac_enabled = current_app.config.get("ENABLE_MWAC", False)
        processed_product_ids = set()

        for line in purchase.lines:
            StockService.add_stock(
                product_id=line.product_id,
                quantity=line.quantity,
                reference_type=GLRef.PURCHASE,
                reference_id=purchase.id,
                notes=f"شراء: {purchase.purchase_number}",
                warehouse_id=warehouse_id,
            )

            product = db.session.get(Product, line.product_id)
            if not product:
                continue
            processed_product_ids.add(product.id)

            capitalize_landed = current_app.config.get(
                "ENABLE_LANDED_COST_CAPITALIZATION", True
            )
            if capitalize_landed:
                unit_cost_for_valuation = line.landed_inventory_unit_cost
            else:
                unit_cost_for_valuation = line.inventory_unit_cost
            exchange_rate_decimal = Decimal(str(purchase.exchange_rate))
            cost_in_aed = unit_cost_for_valuation * exchange_rate_decimal

            # MWAC recalculation (Phase 4)
            if mwac_enabled and tenant_id and warehouse_id:
                StockService._update_wac_on_receipt(
                    tenant_id=tenant_id,
                    product_id=line.product_id,
                    warehouse_id=warehouse_id,
                    received_qty=Decimal(str(line.quantity)),
                    unit_cost_aed=cost_in_aed,
                    reference_type=GLRef.PURCHASE,
                    reference_id=purchase.id,
                )

        # Recalculate global product.cost_price as weighted average across all warehouses
        # to prevent a single warehouse receipt from corrupting the global cost
        for pid in processed_product_ids:
            product = db.session.get(Product, pid)
            if not product:
                continue
            pwc_list = ProductWarehouseCost.query.filter_by(
                tenant_id=tenant_id,
                product_id=pid,
            ).all()
            total_val = Decimal("0")
            total_qty = Decimal("0")
            for pwc in pwc_list:
                total_val += Decimal(str(pwc.total_value or 0))
                total_qty += Decimal(str(pwc.total_quantity or 0))
            if total_qty > 0:
                product.cost_price = (total_val / total_qty).quantize(
                    Decimal("0.001"), rounding=ROUND_HALF_UP
                )
            else:
                product.cost_price = Decimal("0")

    @staticmethod
    def _post_retrospective_cost_adjustment(
        tenant_id,
        product_id,
        warehouse_id,
        old_qty,
        old_avg,
        unit_cost_aed,
        received_qty,
        reference_type,
        reference_id,
    ):
        """
        Post a GL adjustment when a purchase is received for a product that had negative stock.
        The accumulated cost difference (between the fallback cost used for negative sales
        and the actual new purchase cost) is posted to the inventory adjustment account.
        """
        from services.gl_posting import post_or_fail
        from services.gl_service import GLService

        # Only adjust if there was negative stock before this purchase
        if old_qty >= 0:
            return Decimal("0")

        if old_avg is None or old_avg <= 0:
            return Decimal("0")

        if unit_cost_aed is None or unit_cost_aed <= 0:
            return Decimal("0")

        negative_qty = abs(old_qty)
        # Variance = negative_qty * (new_cost - old_avg)
        variance = (negative_qty * (unit_cost_aed - old_avg)).quantize(Decimal("0.001"))
        if abs(variance) <= Decimal("0.001"):
            return Decimal("0")

        product = db.session.get(Product, product_id)
        warehouse = db.session.get(Warehouse, warehouse_id) if warehouse_id else None
        branch_id = warehouse.branch_id if warehouse else None
        product_name = product.name if product else f"Product #{product_id}"

        GLService.ensure_core_accounts(tenant_id=tenant_id)
        asset_account = _resolve_gl_concept_account(
            "INVENTORY_ASSET", "1140", tenant_id
        )

        if variance > 0:
            # New cost > old average: inventory value needs to be reduced (loss)
            loss_account = _resolve_gl_concept_account(
                "INVENTORY_ADJUSTMENT_LOSS", "5150", tenant_id
            )
            lines = [
                {
                    "account": loss_account,
                    "concept_code": "INVENTORY_ADJUSTMENT_LOSS",
                    "debit": variance,
                    "credit": 0,
                    "description": f"Retrospective cost adjustment (negative stock) - {product_name}",
                },
                {
                    "account": asset_account,
                    "concept_code": "INVENTORY_ASSET",
                    "debit": 0,
                    "credit": variance,
                    "description": f"Retrospective cost adjustment (negative stock) - {product_name}",
                },
            ]
            description = f"Retrospective Cost Adjustment (Loss) — {product_name}"
        else:
            # New cost < old average: inventory value needs to be increased (gain)
            gain_account = _resolve_gl_concept_account(
                "INVENTORY_ADJUSTMENT_GAIN", "5150", tenant_id
            )
            lines = [
                {
                    "account": asset_account,
                    "concept_code": "INVENTORY_ASSET",
                    "debit": abs(variance),
                    "credit": 0,
                    "description": f"Retrospective cost adjustment (negative stock) - {product_name}",
                },
                {
                    "account": gain_account,
                    "concept_code": "INVENTORY_ADJUSTMENT_GAIN",
                    "debit": 0,
                    "credit": abs(variance),
                    "description": f"Retrospective cost adjustment (negative stock) - {product_name}",
                },
            ]
            description = f"Retrospective Cost Adjustment (Gain) — {product_name}"

        try:
            post_or_fail(
                lines=lines,
                description=description,
                reference_type=reference_type,
                reference_id=reference_id,
                branch_id=branch_id,
                tenant_id=tenant_id,
            )
            current_app.logger.info(
                "Retrospective cost adjustment posted for product %s, warehouse %s: variance=%s",
                product_id,
                warehouse_id,
                variance,
            )
        except Exception as e:
            current_app.logger.warning(
                "Failed to post retrospective cost adjustment for product %s, warehouse %s: %s",
                product_id,
                warehouse_id,
                e,
            )

        return variance

    @staticmethod
    def _update_wac_on_receipt(
        tenant_id,
        product_id,
        warehouse_id,
        received_qty,
        unit_cost_aed,
        reference_type,
        reference_id,
    ):
        """Recalculate MWAC when stock is received. Must run inside an existing transaction."""
        from datetime import datetime, timezone

        query = ProductWarehouseCost.query.filter_by(
            tenant_id=tenant_id,
            product_id=product_id,
            warehouse_id=warehouse_id,
        )
        pwc = _safe_for_update(
            query, label=f"PWC(receipt) p={product_id} w={warehouse_id}"
        )

        if pwc:
            old_qty = pwc.total_quantity
            old_value = pwc.total_value
            old_avg = (
                Decimal(str(pwc.average_cost))
                if pwc.average_cost is not None
                else Decimal("0")
            )
            new_qty, new_value, new_avg = StockService._mwac_calc(
                old_qty, old_value, received_qty, unit_cost_aed
            )

            pwc.total_quantity = new_qty
            pwc.total_value = new_value
            pwc.average_cost = new_avg.quantize(Decimal("0.0001"))
            pwc.last_updated = datetime.now(timezone.utc)

            # Retrospective cost adjustment for negative stock
            had_negative_stock = old_qty < 0
            had_positive_avg = old_avg > 0
            if had_negative_stock and had_positive_avg:
                StockService._post_retrospective_cost_adjustment(
                    tenant_id=tenant_id,
                    product_id=product_id,
                    warehouse_id=warehouse_id,
                    old_qty=old_qty,
                    old_avg=old_avg,
                    unit_cost_aed=unit_cost_aed,
                    received_qty=received_qty,
                    reference_type=reference_type,
                    reference_id=reference_id,
                )
        else:
            # First receipt for this product+warehouse
            old_qty = Decimal("0")
            old_value = Decimal("0")
            old_avg = None
            new_qty = received_qty
            new_value = received_qty * unit_cost_aed
            new_avg = unit_cost_aed

            pwc = ProductWarehouseCost(
                tenant_id=tenant_id,
                product_id=product_id,
                warehouse_id=warehouse_id,
                total_quantity=new_qty,
                total_value=new_value,
                average_cost=new_avg.quantize(Decimal("0.0001")),
            )
            db.session.add(pwc)

        # Immutable audit trail
        pch = ProductCostHistory(
            tenant_id=tenant_id,
            product_id=product_id,
            warehouse_id=warehouse_id,
            movement_type="purchase",
            reference_type=reference_type,
            reference_id=reference_id,
            old_average_cost=(
                old_avg.quantize(Decimal("0.0001")) if old_avg is not None else None
            ),
            new_average_cost=pwc.average_cost,
            quantity_change=received_qty,
            old_total_quantity=old_qty,
            new_total_quantity=new_qty,
            old_total_value=old_value,
            new_total_value=new_value,
            movement_unit_cost=unit_cost_aed.quantize(Decimal("0.0001")),
        )
        db.session.add(pch)

    @staticmethod
    def reverse_sale(sale):
        """إلغاء بيع - إرجاع للمستودع الأصلي مع عكس MWAC"""
        from datetime import datetime, timezone

        warehouse_id = getattr(sale, "warehouse_id", None)
        tenant_id = getattr(sale, "tenant_id", None)
        mwac_enabled = current_app.config.get("ENABLE_MWAC", False)

        for line in sale.lines:
            StockService.add_stock(
                product_id=line.product_id,
                quantity=line.quantity,
                reference_type=GLRef.SALE_REVERSED,
                reference_id=sale.id,
                notes=f"إلغاء بيع: {sale.sale_number}",
                warehouse_id=warehouse_id,
            )

            # عكس MWAC إذا كان مفعلاً
            if mwac_enabled and tenant_id and warehouse_id:
                q_rev = ProductWarehouseCost.query.filter_by(
                    tenant_id=tenant_id,
                    product_id=line.product_id,
                    warehouse_id=warehouse_id,
                )
                pwc = _safe_for_update(
                    q_rev,
                    label=f"PWC(reverse_sale) p={line.product_id} w={warehouse_id}",
                )

                if pwc:
                    # البحث عن سجل التكلفة الأصلي للبيع لاستخدام قيمة COGS الأصلية
                    cost_history = (
                        ProductCostHistory.query.filter_by(
                            tenant_id=tenant_id,
                            product_id=line.product_id,
                            warehouse_id=warehouse_id,
                            movement_type="sale",
                            reference_type=GLRef.SALE,
                            reference_id=sale.id,
                        )
                        .order_by(ProductCostHistory.id.desc())
                        .first()
                    )

                    qty = Decimal(str(line.quantity))
                    if cost_history:
                        # استخدام قيم COGS الأصلية من سجل التكلفة
                        original_cogs = abs(
                            Decimal(str(cost_history.movement_unit_cost)) * qty
                        )
                    else:
                        original_cogs = (
                            pwc.average_cost * qty if pwc.average_cost else Decimal("0")
                        )

                    old_qty = pwc.total_quantity
                    old_value = pwc.total_value
                    old_avg = (
                        Decimal(str(pwc.average_cost))
                        if pwc.average_cost is not None
                        else Decimal("0")
                    )
                    new_qty, new_value, new_avg = StockService._mwac_calc(
                        old_qty,
                        old_value,
                        qty,
                        (
                            (original_cogs / qty).quantize(Decimal("0.0001"))
                            if qty > 0
                            else Decimal("0")
                        ),
                    )

                    pwc.total_quantity = new_qty
                    pwc.total_value = new_value
                    pwc.average_cost = new_avg.quantize(Decimal("0.0001"))
                    pwc.last_updated = datetime.now(timezone.utc)

                    # سجل تدقيق عكس التكلفة
                    pch = ProductCostHistory(
                        tenant_id=tenant_id,
                        product_id=line.product_id,
                        warehouse_id=warehouse_id,
                        movement_type="sale_reversal",
                        reference_type=GLRef.SALE_REVERSED,
                        reference_id=sale.id,
                        old_average_cost=(
                            old_avg.quantize(Decimal("0.0001")) if old_avg else None
                        ),
                        new_average_cost=pwc.average_cost,
                        quantity_change=qty,
                        old_total_quantity=old_qty,
                        new_total_quantity=new_qty,
                        old_total_value=old_value,
                        new_total_value=new_value,
                        movement_unit_cost=(
                            (original_cogs / qty).quantize(Decimal("0.0001"))
                            if qty > 0
                            else Decimal("0")
                        ),
                    )
                    db.session.add(pch)

    @staticmethod
    def reverse_purchase(purchase):
        """إلغاء شراء - حذف المخزون مع عكس MWAC واستخدام التكلفة الأصلية من سجل التدقيق"""
        from datetime import datetime, timezone

        warehouse_id = getattr(purchase, "warehouse_id", None)
        tenant_id = getattr(purchase, "tenant_id", None)
        mwac_enabled = current_app.config.get("ENABLE_MWAC", False)

        for line in purchase.lines:
            StockService.remove_stock(
                product_id=line.product_id,
                quantity=line.quantity,
                reference_type=GLRef.PURCHASE,
                reference_id=purchase.id,
                notes=f"إلغاء شراء: {purchase.purchase_number}",
                warehouse_id=warehouse_id,
            )

            if mwac_enabled and tenant_id and warehouse_id:
                q_rev_pur = ProductWarehouseCost.query.filter_by(
                    tenant_id=tenant_id,
                    product_id=line.product_id,
                    warehouse_id=warehouse_id,
                )
                pwc = _safe_for_update(
                    q_rev_pur,
                    label=f"PWC(reverse_purchase) p={line.product_id} w={warehouse_id}",
                )

                if pwc:
                    cost_history = (
                        ProductCostHistory.query.filter_by(
                            tenant_id=tenant_id,
                            product_id=line.product_id,
                            warehouse_id=warehouse_id,
                            movement_type="purchase",
                            reference_type=GLRef.PURCHASE,
                            reference_id=purchase.id,
                        )
                        .order_by(ProductCostHistory.id.desc())
                        .first()
                    )

                    qty = Decimal(str(line.quantity))

                    if cost_history:
                        original_unit_cost = abs(
                            Decimal(str(cost_history.movement_unit_cost))
                        )
                    else:
                        original_unit_cost = (
                            pwc.average_cost if pwc.average_cost else Decimal("0")
                        )

                    old_qty = pwc.total_quantity
                    old_value = pwc.total_value
                    old_avg = (
                        Decimal(str(pwc.average_cost))
                        if pwc.average_cost is not None
                        else Decimal("0")
                    )
                    new_qty, new_value, new_avg = StockService._mwac_calc(
                        old_qty, old_value, -qty, original_unit_cost
                    )

                    # Preserve the MWAC cost even when the reversal drives stock
                    # to zero/negative so subsequent purchases can apply the
                    # retrospective cost adjustment. Zeroing average_cost here
                    # destroyed cost history for later transactions (H01).
                    pwc.total_quantity = new_qty
                    pwc.total_value = new_value
                    pwc.average_cost = (
                        new_avg.quantize(Decimal("0.0001"))
                        if new_qty > 0
                        else (original_unit_cost or new_avg).quantize(Decimal("0.0001"))
                    )
                    pwc.last_updated = datetime.now(timezone.utc)

                    pch = ProductCostHistory(
                        tenant_id=tenant_id,
                        product_id=line.product_id,
                        warehouse_id=warehouse_id,
                        movement_type="purchase_reversal",
                        reference_type=GLRef.PURCHASE,
                        reference_id=purchase.id,
                        old_average_cost=(
                            old_avg.quantize(Decimal("0.0001")) if old_avg else None
                        ),
                        new_average_cost=pwc.average_cost,
                        quantity_change=-qty,
                        old_total_quantity=old_qty,
                        new_total_quantity=pwc.total_quantity,
                        old_total_value=old_value,
                        new_total_value=pwc.total_value,
                        movement_unit_cost=original_unit_cost.quantize(
                            Decimal("0.0001")
                        ),
                    )
                    db.session.add(pch)

    @staticmethod
    def check_availability(product_id, quantity):
        product = db.session.get(Product, product_id)

        if not product:
            return False, "المنتج غير موجود"

        if not product.is_active:
            return False, "المنتج غير نشط"

        if product.current_stock < Decimal(str(quantity)):
            return False, f"المخزون غير كافٍ (المتوفر: {product.current_stock})"

        return True, "متوفر"

    @staticmethod
    def check_availability_in_warehouse(product_id, quantity, warehouse_id):
        product = db.session.get(Product, product_id)

        if not product:
            return False, "المنتج غير موجود"

        if not product.is_active:
            return False, "المنتج غير نشط"

        warehouse = Warehouse.query.filter_by(id=warehouse_id, is_active=True).first()
        if not warehouse:
            return False, "المستودع غير موجود أو غير نشط"

        if warehouse.allow_negative_inventory:
            return True, "متوفر (البيع بالسالب مفعل)"

        available_qty = StockService.get_product_stock(
            product_id, warehouse_id=warehouse_id
        )
        if available_qty < Decimal(str(quantity)):
            return (
                False,
                f"المخزون غير كافٍ في المستودع المحدد (المتوفر: {available_qty})",
            )

        return True, "متوفر"

    @staticmethod
    def get_product_stock(product_id, warehouse_id=None, warehouse_ids=None, user=None):
        if warehouse_id is not None:
            warehouse_ids = [warehouse_id]
        elif warehouse_ids is None:
            warehouse_ids = get_accessible_warehouse_ids(user)

        stock_map = get_branch_stock_map(
            product_ids=[product_id], warehouse_ids=warehouse_ids
        )
        return stock_map.get(product_id, Decimal("0"))

    @staticmethod
    def get_visible_products_query(user=None):
        from utils.branching import get_visible_products_query

        return get_visible_products_query(user)

    @staticmethod
    def get_low_stock_products(limit=None, user=None):
        branch_warehouse_ids = get_accessible_warehouse_ids(user)
        query = StockService.get_visible_products_query(user).order_by(Product.name)

        if not branch_warehouse_ids and user is not None:
            return []

        products = query.all()
        if branch_warehouse_ids:
            stock_map = get_branch_stock_map(
                product_ids=[product.id for product in products],
                warehouse_ids=branch_warehouse_ids,
            )
            products = [
                product
                for product in products
                if stock_map.get(product.id, Decimal("0"))
                <= (product.min_stock_alert or Decimal("0"))
            ]
        else:
            products = [
                product
                for product in products
                if (product.current_stock or Decimal("0"))
                <= (product.min_stock_alert or Decimal("0"))
            ]

        if limit:
            products = products[:limit]

        return products

    @staticmethod
    def get_out_of_stock_products(user=None):
        branch_warehouse_ids = get_accessible_warehouse_ids(user)
        query = StockService.get_visible_products_query(user).order_by(Product.name)

        if not branch_warehouse_ids and user is not None:
            return []

        products = query.all()
        if branch_warehouse_ids:
            stock_map = get_branch_stock_map(
                product_ids=[product.id for product in products],
                warehouse_ids=branch_warehouse_ids,
            )
            return [
                product
                for product in products
                if stock_map.get(product.id, Decimal("0")) <= 0
            ]

        return [
            product
            for product in products
            if (product.current_stock or Decimal("0")) <= 0
        ]

    @staticmethod
    def reconcile_stock(tenant_id=None, commit=False):
        """Sync ProductWarehouseStock with aggregated StockMovement data
        and update Product.current_stock from PWS sums.
        Returns dict with reconciliation stats."""
        from sqlalchemy import func
        from datetime import datetime, timezone

        query = db.session.query(
            ProductWarehouseStock.tenant_id,
            ProductWarehouseStock.product_id,
            ProductWarehouseStock.warehouse_id,
        )
        if tenant_id:
            query = query.filter(ProductWarehouseStock.tenant_id == tenant_id)

        movement_totals = db.session.query(
            StockMovement.product_id,
            StockMovement.warehouse_id,
            func.sum(StockMovement.quantity).label("total_qty"),
        )
        if tenant_id:
            movement_totals = movement_totals.filter(
                StockMovement.tenant_id == tenant_id
            )
        movement_totals = movement_totals.group_by(
            StockMovement.product_id, StockMovement.warehouse_id
        ).all()

        now = datetime.now(timezone.utc)
        created = 0
        updated = 0
        errors = 0

        mov_map = {}
        for row in movement_totals:
            key = (row.product_id, row.warehouse_id)
            mov_map[key] = Decimal(str(row.total_qty))

        existing = query.all()
        existing_keys = set()
        for row in existing:
            key = (row.product_id, row.warehouse_id)
            existing_keys.add(key)
            move_qty = mov_map.get(key, Decimal("0"))
            pws = ProductWarehouseStock.query.filter_by(
                tenant_id=row.tenant_id,
                product_id=row.product_id,
                warehouse_id=row.warehouse_id,
            ).first()
            if pws and pws.quantity != move_qty:
                pws.quantity = move_qty
                pws.updated_at = now
                updated += 1

        for (pid, wid), move_qty in mov_map.items():
            if (pid, wid) not in existing_keys:
                warehouse = db.session.get(Warehouse, wid)
                if warehouse:
                    tid = warehouse.tenant_id if tenant_id is None else tenant_id
                    pws = ProductWarehouseStock(
                        tenant_id=tid,
                        product_id=pid,
                        warehouse_id=wid,
                        quantity=move_qty,
                    )
                    db.session.add(pws)
                    created += 1

        all_pws = db.session.query(
            ProductWarehouseStock.product_id,
            func.sum(ProductWarehouseStock.quantity).label("total"),
        )
        if tenant_id:
            all_pws = all_pws.filter(ProductWarehouseStock.tenant_id == tenant_id)
        all_pws = all_pws.group_by(ProductWarehouseStock.product_id).all()

        prod_ids = [r.product_id for r in all_pws]
        products = (
            Product.query.filter(Product.id.in_(prod_ids)).all() if prod_ids else []
        )
        prod_map = {p.id: p for p in products}
        for row in all_pws:
            prod = prod_map.get(row.product_id)
            if prod:
                pws_sum = Decimal(str(row.total))
                if prod.current_stock != pws_sum:
                    prod.current_stock = pws_sum
                    updated += 1

        if commit:
            try:
                db.session.flush()
            except Exception:
                errors += 1
        else:
            db.session.flush()

        return {
            "created": created,
            "updated": updated,
            "errors": errors,
            "total_pws": len(existing) + created,
        }
