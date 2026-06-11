from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone
from flask import current_app
from flask_login import current_user
from extensions import db
from models import Product, StockMovement, Warehouse, ProductWarehouseCost, ProductCostHistory
from models.warehouse import ProductWarehouseStock
from utils.branching import get_accessible_warehouse_ids, get_branch_stock_map
from utils.gl_reference_types import GLRef


def _mwac_calc(old_qty: Decimal, old_value: Decimal, change_qty: Decimal, unit_cost: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    """Pure MWAC math — no DB, no models, no side effects.
    Returns (new_qty, new_value, new_avg)."""
    new_qty = old_qty + change_qty
    new_value = old_value + (change_qty * unit_cost)
    new_avg = (new_value / new_qty).quantize(Decimal('0.0001')) if new_qty > 0 else Decimal('0')
    return new_qty, new_value, new_avg


def _resolve_gl_concept_account(concept_code, fallback_account_code, tenant_id=None):
    from services.gl_service import GL_ACCOUNTS, GL_ACCOUNT_CONCEPTS
    from services.gl_account_resolver import resolve_gl_account, is_dynamic_gl_mapping_enabled
    if is_dynamic_gl_mapping_enabled() and tenant_id:
        try:
            resolved = resolve_gl_account(tenant_id=tenant_id, concept_code=concept_code)
            if resolved:
                return resolved.account_code
        except Exception:
            pass
    concept_key = {v: k for k, v in GL_ACCOUNT_CONCEPTS.items()}.get(concept_code)
    if concept_key and concept_key in GL_ACCOUNTS:
        return GL_ACCOUNTS[concept_key]
    return fallback_account_code


class StockService:
    
    @staticmethod
    def add_stock(product_id, quantity, reference_type=None, reference_id=None, notes=None, warehouse_id=None):
        return StockService.create_movement(
            product_id=product_id,
            quantity=abs(Decimal(str(quantity))),
            movement_type='purchase',
            reference_type=reference_type,
            reference_id=reference_id,
            notes=notes,
            warehouse_id=warehouse_id
        )
    
    @staticmethod
    def remove_stock(product_id, quantity, reference_type=None, reference_id=None, notes=None, warehouse_id=None):
        return StockService.create_movement(
            product_id=product_id,
            quantity=-abs(Decimal(str(quantity))),
            movement_type='sale',
            reference_type=reference_type,
            reference_id=reference_id,
            notes=notes,
            warehouse_id=warehouse_id
        )
    
    @staticmethod
    def _post_adjustment_gl(movement):
        from services.gl_posting import post_or_fail
        from services.gl_service import GLService

        product = Product.query.get(movement.product_id)
        if not product or not product.cost_price:
            return
        cost_value = abs(Decimal(str(movement.quantity))) * Decimal(str(product.cost_price))
        if cost_value <= 0:
            return
        warehouse = Warehouse.query.get(movement.warehouse_id) if getattr(movement, 'warehouse_id', None) else None
        tenant_id = getattr(movement, 'tenant_id', None) or getattr(product, 'tenant_id', None)
        loss_account = _resolve_gl_concept_account('INVENTORY_ADJUSTMENT_LOSS', '5150', tenant_id)
        asset_account = _resolve_gl_concept_account('INVENTORY_ASSET', '1140', tenant_id)
        gain_account = _resolve_gl_concept_account('INVENTORY_ADJUSTMENT_GAIN', '5150', tenant_id)

        if Decimal(str(movement.quantity)) < 0:
            lines = [
                {'account': loss_account, 'concept_code': 'INVENTORY_ADJUSTMENT_LOSS', 'debit': cost_value, 'credit': 0, 'description': f'Inventory Adjustment (Loss) - {product.name}'},
                {'account': asset_account, 'concept_code': 'INVENTORY_ASSET', 'debit': 0, 'credit': cost_value, 'description': f'Stock Decrease - {product.name}'},
            ]
        else:
            lines = [
                {'account': asset_account, 'concept_code': 'INVENTORY_ASSET', 'debit': cost_value, 'credit': 0, 'description': f'Stock Increase - {product.name}'},
                {'account': gain_account, 'concept_code': 'INVENTORY_ADJUSTMENT_GAIN', 'debit': 0, 'credit': cost_value, 'description': f'Inventory Adjustment (Gain) - {product.name}'},
            ]
        branch_id = warehouse.branch_id if warehouse else None
        GLService.ensure_core_accounts(tenant_id=tenant_id)
        post_or_fail(
            lines=lines,
            description=f'Stock Adjustment - {product.name}',
            reference_type=movement.reference_type or GLRef.STOCK_ADJUSTMENT,
            reference_id=movement.id,
            branch_id=branch_id,
            tenant_id=tenant_id,
        )

    @staticmethod
    def adjust_stock(product_id, quantity, notes=None, warehouse_id=None, reference_type=None, reference_id=None):
        try:
            movement = StockService.create_movement(
                product_id=product_id,
                quantity=Decimal(str(quantity)),
                movement_type='adjustment',
                notes=notes,
                warehouse_id=warehouse_id,
                reference_type=reference_type or GLRef.STOCK_ADJUSTMENT,
                reference_id=reference_id,
            )
            StockService._post_adjustment_gl(movement)
            return movement
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Failed stock adjustment: {e}")
            raise

    @staticmethod
    def add_opening_stock(product_id, quantity, notes=None, warehouse_id=None, cost_price=None):
        movement = StockService.create_movement(
            product_id=product_id,
            quantity=Decimal(str(quantity)),
            movement_type='purchase',
            notes=notes or 'مخزون افتتاحي',
            warehouse_id=warehouse_id,
            reference_type=GLRef.PRODUCT_CREATION,
        )
        from services.gl_posting import post_or_fail
        from services.gl_service import GLService
        from models import Product, Warehouse
        product = Product.query.get(product_id)
        warehouse = Warehouse.query.get(warehouse_id) if warehouse_id else None
        if product and product.cost_price:
            cost_value = Decimal(str(quantity)) * Decimal(str(product.cost_price))
            if cost_value > 0:
                tenant_id = getattr(product, 'tenant_id', None)
                asset_account = _resolve_gl_concept_account('INVENTORY_ASSET', '1140', tenant_id)
                equity_account = _resolve_gl_concept_account('OPENING_BALANCE_EQUITY', '3130', tenant_id)
                GLService.ensure_core_accounts(tenant_id=tenant_id)
                post_or_fail(
                    lines=[
                        {'account': asset_account, 'concept_code': 'INVENTORY_ASSET', 'debit': cost_value, 'credit': 0, 'description': f'مخزون افتتاحي - {product.name}'},
                        {'account': equity_account, 'concept_code': 'OPENING_BALANCE_EQUITY', 'debit': 0, 'credit': cost_value, 'description': f'مخزون افتتاحي - {product.name}'},
                    ],
                    description=f'مخزون افتتاحي - {product.name}',
                    reference_type=GLRef.PRODUCT_CREATION,
                    reference_id=product.id,
                    branch_id=warehouse.branch_id if warehouse else None,
                    tenant_id=tenant_id,
                )
        return movement
    
    @staticmethod
    def create_movement(product_id, quantity, movement_type, reference_type=None, reference_id=None, notes=None, warehouse_id=None):
        from utils.field_validators import validate_stock_movement_type

        movement_type = validate_stock_movement_type(movement_type)
        qty = Decimal(str(quantity))
        try:
            product = Product.query.get(product_id)
            
            if not product:
                raise ValueError(f'⚠️ المنتج غير موجود (ID: {product_id}).\n💡 تأكد من اختيار منتج صحيح من القائمة.')
            
            try:
                user_id = current_user.id if current_user and current_user.is_authenticated else None
            except:
                user_id = None

            tenant_id = getattr(product, "tenant_id", None)
            
            # تحديد المستودع
            if warehouse_id:
                warehouse = Warehouse.query.filter_by(id=warehouse_id, is_active=True).first()
                if not warehouse:
                    raise ValueError(f'⚠️ المستودع المحدد غير موجود أو غير نشط (ID: {warehouse_id}).')
            else:
                warehouse = Warehouse.query.filter_by(tenant_id=tenant_id, is_active=True, is_main=True).first()
                if not warehouse:
                    warehouse = Warehouse.query.filter_by(tenant_id=tenant_id, is_active=True).first()
                
                if not warehouse:
                    warehouse = Warehouse(
                        name='Main Warehouse', name_ar='المستودع الرئيسي',
                        is_active=True, is_main=True, tenant_id=tenant_id,
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
                notes=notes
            )
            
            db.session.add(movement)
            
            # Update ProductWarehouseStock (per-warehouse tracking)
            pws = ProductWarehouseStock.query.filter_by(
                tenant_id=tenant_id,
                product_id=product_id,
                warehouse_id=warehouse.id,
            ).first()
            if pws:
                pws.quantity += qty
                pws.updated_at = datetime.now(timezone.utc)
            else:
                pws = ProductWarehouseStock(
                    tenant_id=tenant_id,
                    product_id=product_id,
                    warehouse_id=warehouse.id,
                    quantity=qty,
                )
                db.session.add(pws)
            
            # Update global current_stock (legacy)
            product.current_stock += qty
            
            if product.current_stock < 0:
                raise ValueError(f'❌ المخزون غير كافٍ للمنتج "{product.name}"!\n📦 المتوفر: {product.current_stock} | المطلوب: {quantity}\n💡 قلل الكمية أو اطلب مخزون جديد من المورد.')
            
            db.session.flush()
            
            current_app.logger.info(
                f'Stock movement: {movement_type} {quantity} of product #{product_id}'
            )
            
            return movement
        
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'Stock movement failed: {e}')
            raise

    @staticmethod
    def transfer_stock(product_id, from_warehouse_id, to_warehouse_id, quantity, notes=None, user=None):
        """Transfer quantity between warehouses (net zero on product.current_stock)."""
        qty = abs(Decimal(str(quantity)))
        if qty <= 0:
            raise ValueError('الكمية يجب أن تكون أكبر من صفر.')

        product = Product.query.get(product_id)
        if not product:
            raise ValueError('المنتج غير موجود.')
        tenant_id = getattr(product, 'tenant_id', None)

        from_wh = Warehouse.query.filter_by(id=int(from_warehouse_id), is_active=True).first()
        to_wh = Warehouse.query.filter_by(id=int(to_warehouse_id), is_active=True).first()
        if not from_wh or not to_wh:
            raise ValueError('المستودع المصدر أو الوجهة غير موجود أو غير نشط.')
        if from_wh.id == to_wh.id:
            raise ValueError('لا يمكن التحويل إلى نفس المستودع.')

        # التحقق من التينانت
        if tenant_id is not None:
            wh_tenant_ids = [getattr(from_wh, 'tenant_id', None), getattr(to_wh, 'tenant_id', None)]
            if tenant_id not in wh_tenant_ids:
                raise ValueError('المنتج لا ينتمي إلى نفس المستودع (تعارض في التينانت).')
            if from_wh.tenant_id != tenant_id or to_wh.tenant_id != tenant_id:
                raise ValueError('المستودع المصدر والوجهة يجب أن ينتميان لنفس شركة المنتج.')

        # التحقق من صلاحية المستخدم - إذا تم تمرير مستخدم
        if user is not None:
            from utils.auth_helpers import is_global_owner_user
            if not is_global_owner_user(user):
                from utils.branching import get_accessible_warehouse_ids
                accessible = get_accessible_warehouse_ids(user)
                if accessible and (from_wh.id not in accessible or to_wh.id not in accessible):
                    raise ValueError('ليس لديك صلاحية الوصول لأحد المستودعين.')

        available = StockService.get_product_stock(product_id, warehouse_id=from_wh.id)
        if available < qty:
            raise ValueError(f'الكمية غير متوفرة في المستودع المصدر (المتوفر: {available}).')

        label = notes or f'تحويل من {from_wh.name_ar or from_wh.name} إلى {to_wh.name_ar or to_wh.name}'
        out_movement = StockService.create_movement(
            product_id=product_id,
            quantity=-qty,
            movement_type='transfer',
            reference_type=GLRef.STOCK_TRANSFER,
            notes=label,
            warehouse_id=from_wh.id,
        )
        in_movement = StockService.create_movement(
            product_id=product_id,
            quantity=qty,
            movement_type='transfer',
            reference_type=GLRef.STOCK_TRANSFER,
            reference_id=out_movement.id,
            notes=label,
            warehouse_id=to_wh.id,
        )
        return out_movement, in_movement
    
    @staticmethod
    def process_sale_lines(sale, warehouse_id=None):
        """معالجة بيوع مع خصم من مستودع محدد"""
        # استخدام warehouse_id من sale إذا لم يُمرر
        if not warehouse_id and hasattr(sale, 'warehouse_id'):
            warehouse_id = sale.warehouse_id
        
        for line in sale.lines:
            StockService.remove_stock(
                product_id=line.product_id,
                quantity=line.quantity,
                reference_type=GLRef.SALE,
                reference_id=sale.id,
                notes=f'بيع: {sale.sale_number}',
                warehouse_id=warehouse_id  # ← تمرير المستودع
            )
    
    @staticmethod
    def _resolve_cogs_unit_cost(product_id, warehouse_id, tenant_id, line_cost_price=None):
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
        if pwc and pwc.total_quantity > 0 and pwc.average_cost and pwc.average_cost > Decimal('0'):
            return pwc.average_cost, 'mwac'
        if line_cost_price:
            cost = Decimal(str(line_cost_price))
            if cost > Decimal('0'):
                return cost, 'cost_price'
        last_purchase = ProductCostHistory.query.filter_by(
            tenant_id=tenant_id,
            product_id=product_id,
            warehouse_id=warehouse_id,
            movement_type='purchase',
        ).order_by(ProductCostHistory.created_at.desc()).first()
        if last_purchase and last_purchase.movement_unit_cost and last_purchase.movement_unit_cost > Decimal('0'):
            return Decimal(str(last_purchase.movement_unit_cost)), 'last_purchase'
        raise ValueError(
            f'لا يمكن تحديد تكلفة البضاعة المباعة (COGS) للمنتج {product_id}: '
            'لا يوجد مخزون، ولا سعر تكلفة، ولا سجل شراء سابق. '
            'يرجى إدخال تكلفة المنتج أو توريد مخزون قبل البيع.'
        )

    @staticmethod
    def calculate_sale_cogs_and_deduct(sale, warehouse_id=None):
        """
        Compute COGS using MWAC, deduct stock, update PWC, create audit trail.
        Returns total COGS in AED (Decimal).
        Falls back to SaleLine.cost_price when ENABLE_MWAC is False.
        Never silently posts COGS=0 — raises error if cost cannot be resolved.
        """
        from datetime import datetime, timezone
        from config import Config
        
        if not warehouse_id and hasattr(sale, 'warehouse_id'):
            warehouse_id = sale.warehouse_id
        
        tenant_id = getattr(sale, 'tenant_id', None)
        mwac_enabled = current_app.config.get('ENABLE_MWAC', False)
        total_cogs = Decimal('0')
        
        for line in sale.lines:
            qty = Decimal(str(line.quantity))
            
            if mwac_enabled and tenant_id and warehouse_id:
                pwc = ProductWarehouseCost.query.filter_by(
                    tenant_id=tenant_id,
                    product_id=line.product_id,
                    warehouse_id=warehouse_id,
                ).first()
                
                if pwc and pwc.total_quantity > 0:
                    avg_cost = pwc.average_cost
                    cogs = (avg_cost * qty).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
                    
                    new_qty, new_value, new_avg = _mwac_calc(
                        pwc.total_quantity, pwc.total_value, -qty,
                        avg_cost.quantize(Decimal('0.0001'))
                    )
                    
                    pwc.total_quantity = new_qty
                    pwc.total_value = new_value
                    pwc.average_cost = new_avg.quantize(Decimal('0.0001'))
                    pwc.last_updated = datetime.now(timezone.utc)
                    
                    # Audit trail
                    pch = ProductCostHistory(
                        tenant_id=tenant_id,
                        product_id=line.product_id,
                        warehouse_id=warehouse_id,
                        movement_type='sale',
                        reference_type=GLRef.SALE,
                        reference_id=sale.id,
                        old_average_cost=old_avg.quantize(Decimal('0.0001')),
                        new_average_cost=pwc.average_cost,
                        quantity_change=-qty,
                        old_total_quantity=old_qty,
                        new_total_quantity=new_qty,
                        old_total_value=old_value,
                        new_total_value=new_value,
                        movement_unit_cost=avg_cost.quantize(Decimal('0.0001')),
                    )
                    db.session.add(pch)
                else:
                    avg_cost, source = StockService._resolve_cogs_unit_cost(
                        line.product_id, warehouse_id, tenant_id, line_cost_price=line.cost_price
                    )
                    cogs = (avg_cost * qty).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
                    current_app.logger.warning(
                        'COGS resolved via fallback (%s) for product %s sale %s: unit_cost=%s',
                        source, line.product_id, sale.sale_number, avg_cost
                    )
            else:
                avg_cost, source = StockService._resolve_cogs_unit_cost(
                    line.product_id, warehouse_id, tenant_id, line_cost_price=line.cost_price
                )
                cogs = (avg_cost * qty).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
            
            total_cogs += cogs
        
        return total_cogs.quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
    
    @staticmethod
    def process_purchase_lines(purchase, warehouse_id=None):
        if not warehouse_id and hasattr(purchase, 'warehouse_id'):
            warehouse_id = purchase.warehouse_id
        
        tenant_id = getattr(purchase, 'tenant_id', None)
        mwac_enabled = current_app.config.get('ENABLE_MWAC', False)
        
        for line in purchase.lines:
            StockService.add_stock(
                product_id=line.product_id,
                quantity=line.quantity,
                reference_type=GLRef.PURCHASE,
                reference_id=purchase.id,
                notes=f'شراء: {purchase.purchase_number}',
                warehouse_id=warehouse_id
            )
            
            product = Product.query.get(line.product_id)
            if not product:
                continue
                
            # Phase 5: Use landed_unit_cost (FOB + allocated landed cost) for valuation
            capitalize_landed = current_app.config.get('ENABLE_LANDED_COST_CAPITALIZATION', True)
            if capitalize_landed:
                unit_cost_for_valuation = line.landed_unit_cost
            else:
                unit_cost_for_valuation = Decimal(str(line.unit_cost)) if line.unit_cost else Decimal('0')
            exchange_rate_decimal = Decimal(str(purchase.exchange_rate))
            cost_in_aed = unit_cost_for_valuation * exchange_rate_decimal
            product.cost_price = cost_in_aed
            
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
    
    @staticmethod
    def _update_wac_on_receipt(tenant_id, product_id, warehouse_id, received_qty, unit_cost_aed, reference_type, reference_id):
        """Recalculate MWAC when stock is received. Must run inside an existing transaction."""
        from datetime import datetime, timezone
        
        query = ProductWarehouseCost.query.filter_by(
            tenant_id=tenant_id,
            product_id=product_id,
            warehouse_id=warehouse_id,
        )
        try:
            pwc = query.with_for_update().first()
        except Exception:
            pwc = query.first()
        
        if pwc:
            old_qty = pwc.total_quantity
            old_value = pwc.total_value
            old_avg = pwc.average_cost
            new_qty, new_value, new_avg = _mwac_calc(old_qty, old_value, received_qty, unit_cost_aed)
            
            pwc.total_quantity = new_qty
            pwc.total_value = new_value
            pwc.average_cost = new_avg.quantize(Decimal('0.0001'))
            pwc.last_updated = datetime.now(timezone.utc)
        else:
            # First receipt for this product+warehouse
            old_qty = Decimal('0')
            old_value = Decimal('0')
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
                average_cost=new_avg.quantize(Decimal('0.0001')),
            )
            db.session.add(pwc)
        
        # Immutable audit trail
        pch = ProductCostHistory(
            tenant_id=tenant_id,
            product_id=product_id,
            warehouse_id=warehouse_id,
            movement_type='purchase',
            reference_type=reference_type,
            reference_id=reference_id,
            old_average_cost=old_avg.quantize(Decimal('0.0001')) if old_avg is not None else None,
            new_average_cost=pwc.average_cost,
            quantity_change=received_qty,
            old_total_quantity=old_qty,
            new_total_quantity=new_qty,
            old_total_value=old_value,
            new_total_value=new_value,
            movement_unit_cost=unit_cost_aed.quantize(Decimal('0.0001')),
        )
        db.session.add(pch)
    
    @staticmethod
    def reverse_sale(sale):
        """إلغاء بيع - إرجاع للمستودع الأصلي مع عكس MWAC"""
        from datetime import datetime, timezone
        warehouse_id = getattr(sale, 'warehouse_id', None)
        tenant_id = getattr(sale, 'tenant_id', None)
        mwac_enabled = current_app.config.get('ENABLE_MWAC', False)
        
        for line in sale.lines:
            StockService.add_stock(
                product_id=line.product_id,
                quantity=line.quantity,
                reference_type=GLRef.SALE_REVERSED,
                reference_id=sale.id,
                notes=f'إلغاء بيع: {sale.sale_number}',
                warehouse_id=warehouse_id
            )
            
            # عكس MWAC إذا كان مفعلاً
            if mwac_enabled and tenant_id and warehouse_id:
                pwc = ProductWarehouseCost.query.filter_by(
                    tenant_id=tenant_id,
                    product_id=line.product_id,
                    warehouse_id=warehouse_id,
                ).first()
                
                if pwc:
                    # البحث عن سجل التكلفة الأصلي للبيع لاستخدام قيمة COGS الأصلية
                    cost_history = ProductCostHistory.query.filter_by(
                        tenant_id=tenant_id,
                        product_id=line.product_id,
                        warehouse_id=warehouse_id,
                        movement_type='sale',
                        reference_type=GLRef.SALE,
                        reference_id=sale.id,
                    ).order_by(ProductCostHistory.id.desc()).first()
                    
                    qty = Decimal(str(line.quantity))
                    if cost_history:
                        # استخدام قيم COGS الأصلية من سجل التكلفة
                        original_cogs = abs(Decimal(str(cost_history.movement_unit_cost)) * qty)
                    else:
                        # Fallback: استخدام متوسط التكلفة الحالي
                        original_cogs = pwc.average_cost * qty if pwc.average_cost else Decimal('0')
                    
                    old_qty = pwc.total_quantity
                    old_value = pwc.total_value
                    old_avg = pwc.average_cost
                    new_qty, new_value, new_avg = _mwac_calc(
                        old_qty, old_value, qty,
                        (original_cogs / qty).quantize(Decimal('0.0001')) if qty > 0 else Decimal('0')
                    )
                    
                    pwc.total_quantity = new_qty
                    pwc.total_value = new_value
                    pwc.average_cost = new_avg.quantize(Decimal('0.0001'))
                    pwc.last_updated = datetime.now(timezone.utc)
                    
                    # سجل تدقيق عكس التكلفة
                    pch = ProductCostHistory(
                        tenant_id=tenant_id,
                        product_id=line.product_id,
                        warehouse_id=warehouse_id,
                        movement_type='sale_reversal',
                        reference_type=GLRef.SALE_REVERSED,
                        reference_id=sale.id,
                        old_average_cost=old_avg.quantize(Decimal('0.0001')) if old_avg else None,
                        new_average_cost=pwc.average_cost,
                        quantity_change=qty,
                        old_total_quantity=old_qty,
                        new_total_quantity=new_qty,
                        old_total_value=old_value,
                        new_total_value=new_value,
                        movement_unit_cost=(original_cogs / qty).quantize(Decimal('0.0001')) if qty > 0 else Decimal('0'),
                    )
                    db.session.add(pch)
    
    @staticmethod
    def reverse_purchase(purchase):
        """إلغاء شراء - حذف المخزون مع عكس MWAC واستخدام التكلفة الأصلية من سجل التدقيق"""
        from datetime import datetime, timezone
        warehouse_id = getattr(purchase, 'warehouse_id', None)
        tenant_id = getattr(purchase, 'tenant_id', None)
        mwac_enabled = current_app.config.get('ENABLE_MWAC', False)

        for line in purchase.lines:
            StockService.remove_stock(
                product_id=line.product_id,
                quantity=line.quantity,
                reference_type=GLRef.PURCHASE,
                reference_id=purchase.id,
                notes=f'إلغاء شراء: {purchase.purchase_number}',
                warehouse_id=warehouse_id,
            )

            if mwac_enabled and tenant_id and warehouse_id:
                pwc = ProductWarehouseCost.query.filter_by(
                    tenant_id=tenant_id,
                    product_id=line.product_id,
                    warehouse_id=warehouse_id,
                ).first()

                if pwc:
                    cost_history = ProductCostHistory.query.filter_by(
                        tenant_id=tenant_id,
                        product_id=line.product_id,
                        warehouse_id=warehouse_id,
                        movement_type='purchase',
                        reference_type=GLRef.PURCHASE,
                        reference_id=purchase.id,
                    ).order_by(ProductCostHistory.id.desc()).first()

                    qty = Decimal(str(line.quantity))

                    if cost_history:
                        original_unit_cost = abs(Decimal(str(cost_history.movement_unit_cost)))
                    else:
                        original_unit_cost = pwc.average_cost if pwc.average_cost else Decimal('0')

                    old_qty = pwc.total_quantity
                    old_value = pwc.total_value
                    old_avg = pwc.average_cost
                    reversed_value = qty * original_unit_cost
                    new_qty, new_value, new_avg = _mwac_calc(old_qty, old_value, -qty, original_unit_cost)

                    pwc.total_quantity = new_qty if new_qty >= 0 else Decimal('0')
                    pwc.total_value = new_value if new_value >= 0 else Decimal('0')
                    pwc.average_cost = new_avg.quantize(Decimal('0.0001')) if new_qty > 0 else Decimal('0')
                    pwc.last_updated = datetime.now(timezone.utc)

                    pch = ProductCostHistory(
                        tenant_id=tenant_id,
                        product_id=line.product_id,
                        warehouse_id=warehouse_id,
                        movement_type='purchase_reversal',
                        reference_type=GLRef.PURCHASE,
                        reference_id=purchase.id,
                        old_average_cost=old_avg.quantize(Decimal('0.0001')) if old_avg else None,
                        new_average_cost=pwc.average_cost,
                        quantity_change=-qty,
                        old_total_quantity=old_qty,
                        new_total_quantity=pwc.total_quantity,
                        old_total_value=old_value,
                        new_total_value=pwc.total_value,
                        movement_unit_cost=original_unit_cost.quantize(Decimal('0.0001')),
                    )
                    db.session.add(pch)

    @staticmethod
    def check_availability(product_id, quantity):
        product = Product.query.get(product_id)
        
        if not product:
            return False, 'المنتج غير موجود'
        
        if not product.is_active:
            return False, 'المنتج غير نشط'
        
        if product.current_stock < Decimal(str(quantity)):
            return False, f'المخزون غير كافٍ (المتوفر: {product.current_stock})'
        
        return True, 'متوفر'

    @staticmethod
    def check_availability_in_warehouse(product_id, quantity, warehouse_id):
        product = Product.query.get(product_id)

        if not product:
            return False, 'المنتج غير موجود'

        if not product.is_active:
            return False, 'المنتج غير نشط'

        warehouse = Warehouse.query.filter_by(id=warehouse_id, is_active=True).first()
        if not warehouse:
            return False, 'المستودع غير موجود أو غير نشط'

        available_qty = StockService.get_product_stock(product_id, warehouse_id=warehouse_id)
        if available_qty < Decimal(str(quantity)):
            return False, f'المخزون غير كافٍ في المستودع المحدد (المتوفر: {available_qty})'

        return True, 'متوفر'

    @staticmethod
    def get_product_stock(product_id, warehouse_id=None, warehouse_ids=None, user=None):
        if warehouse_id is not None:
            warehouse_ids = [warehouse_id]
        elif warehouse_ids is None:
            warehouse_ids = get_accessible_warehouse_ids(user)

        stock_map = get_branch_stock_map(product_ids=[product_id], warehouse_ids=warehouse_ids)
        return stock_map.get(product_id, Decimal('0'))

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
                product for product in products
                if stock_map.get(product.id, Decimal('0')) <= (product.min_stock_alert or Decimal('0'))
            ]
        else:
            products = [
                product for product in products
                if (product.current_stock or Decimal('0')) <= (product.min_stock_alert or Decimal('0'))
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
                product for product in products
                if stock_map.get(product.id, Decimal('0')) <= 0
            ]

        return [
            product for product in products
            if (product.current_stock or Decimal('0')) <= 0
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
            func.sum(StockMovement.quantity).label('total_qty'),
        )
        if tenant_id:
            movement_totals = movement_totals.filter(StockMovement.tenant_id == tenant_id)
        movement_totals = movement_totals.group_by(
            StockMovement.product_id, StockMovement.warehouse_id
        ).all()

        now = datetime.now(timezone.utc)
        created = 0
        updated = 0
        deleted = 0
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
            move_qty = mov_map.get(key, Decimal('0'))
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
                warehouse = Warehouse.query.get(wid)
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
            func.sum(ProductWarehouseStock.quantity).label('total'),
        )
        if tenant_id:
            all_pws = all_pws.filter(ProductWarehouseStock.tenant_id == tenant_id)
        all_pws = all_pws.group_by(ProductWarehouseStock.product_id).all()

        prod_ids = [r.product_id for r in all_pws]
        products = Product.query.filter(Product.id.in_(prod_ids)).all() if prod_ids else []
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
                db.session.commit()
            except Exception:
                db.session.rollback()
                errors += 1
        else:
            db.session.flush()

        return {
            'created': created,
            'updated': updated,
            'errors': errors,
            'total_pws': len(existing) + created,
        }

