from decimal import Decimal
from flask import current_app
from flask_login import current_user
from extensions import db
from models import Product, StockMovement, Warehouse
from utils.branching import get_accessible_warehouse_ids, get_branch_stock_map
from utils.gl_reference_types import GLRef


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
        if Decimal(str(movement.quantity)) < 0:
            lines = [
                {'account': '5150', 'debit': cost_value, 'credit': 0, 'description': f'Inventory Adjustment (Loss) - {product.name}'},
                {'account': '1140', 'debit': 0, 'credit': cost_value, 'description': f'Stock Decrease - {product.name}'},
            ]
        else:
            lines = [
                {'account': '1140', 'debit': cost_value, 'credit': 0, 'description': f'Stock Increase - {product.name}'},
                {'account': '5150', 'debit': 0, 'credit': cost_value, 'description': f'Inventory Adjustment (Gain) - {product.name}'},
            ]
        warehouse = Warehouse.query.get(movement.warehouse_id) if getattr(movement, 'warehouse_id', None) else None
        branch_id = warehouse.branch_id if warehouse else None
        tenant_id = getattr(movement, 'tenant_id', None) or getattr(product, 'tenant_id', None)
        GLService.ensure_core_accounts(tenant_id=tenant_id)
        post_or_fail(
            lines=lines,
            description=f'Stock Adjustment - {product.name}',
            reference_type=movement.reference_type or GLRef.STOCK_ADJUSTMENT,
            reference_id=movement.id,
            branch_id=branch_id,
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
    def create_movement(product_id, quantity, movement_type, reference_type=None, reference_id=None, notes=None, warehouse_id=None):
        try:
            product = Product.query.get(product_id)
            
            if not product:
                raise ValueError(f'⚠️ المنتج غير موجود (ID: {product_id}).\n💡 تأكد من اختيار منتج صحيح من القائمة.')
            
            # تحديد المستودع
            if warehouse_id:
                # استخدام المستودع المحدد
                warehouse = Warehouse.query.filter_by(id=warehouse_id, is_active=True).first()
                if not warehouse:
                    raise ValueError(f'⚠️ المستودع المحدد غير موجود أو غير نشط (ID: {warehouse_id}).')
            else:
                # البحث عن المستودع الرئيسي أولاً، ثم أول مستودع نشط
                warehouse = Warehouse.query.filter_by(is_active=True, is_main=True).first()
                if not warehouse:
                    warehouse = Warehouse.query.filter_by(is_active=True).first()
                
                # إذا لم يوجد أي مستودع، إنشاء واحد افتراضي
                if not warehouse:
                    warehouse = Warehouse(name='Main Warehouse', name_ar='المستودع الرئيسي', is_active=True, is_main=True)
                    db.session.add(warehouse)
                    db.session.flush()
            
            try:
                user_id = current_user.id if current_user and current_user.is_authenticated else None
            except:
                user_id = None

            tenant_id = getattr(warehouse, "tenant_id", None)
            if tenant_id is None:
                try:
                    if current_user and current_user.is_authenticated:
                        tenant_id = getattr(current_user, "tenant_id", None)
                except Exception:
                    tenant_id = None
            if tenant_id is None:
                tenant_id = getattr(product, "tenant_id", None)
            if getattr(warehouse, "tenant_id", None) is None and tenant_id is not None:
                warehouse.tenant_id = tenant_id
            
            movement = StockMovement(
                tenant_id=tenant_id,
                product_id=product_id,
                warehouse_id=warehouse.id,
                movement_type=movement_type,
                quantity=Decimal(str(quantity)),
                reference_type=reference_type,
                reference_id=reference_id,
                user_id=user_id,
                notes=notes
            )
            
            db.session.add(movement)
            
            product.current_stock += Decimal(str(quantity))
            
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
    def transfer_stock(product_id, from_warehouse_id, to_warehouse_id, quantity, notes=None):
        """Transfer quantity between warehouses (net zero on product.current_stock)."""
        qty = abs(Decimal(str(quantity)))
        if qty <= 0:
            raise ValueError('الكمية يجب أن تكون أكبر من صفر.')

        from_wh = Warehouse.query.filter_by(id=int(from_warehouse_id), is_active=True).first()
        to_wh = Warehouse.query.filter_by(id=int(to_warehouse_id), is_active=True).first()
        if not from_wh or not to_wh:
            raise ValueError('المستودع المصدر أو الوجهة غير موجود أو غير نشط.')
        if from_wh.id == to_wh.id:
            raise ValueError('لا يمكن التحويل إلى نفس المستودع.')

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
    def process_purchase_lines(purchase, warehouse_id=None):
        if not warehouse_id and hasattr(purchase, 'warehouse_id'):
            warehouse_id = purchase.warehouse_id
        
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
            if product:
                # Update cost price in base currency (AED)
                # Ensure we use Decimal for precision
                unit_cost_decimal = Decimal(str(line.unit_cost))
                exchange_rate_decimal = Decimal(str(purchase.exchange_rate))
                cost_in_aed = unit_cost_decimal * exchange_rate_decimal
                product.cost_price = cost_in_aed
    
    @staticmethod
    def reverse_sale(sale):
        """إلغاء بيع - إرجاع للمستودع الأصلي"""
        # استخدام نفس المستودع الذي تم البيع منه
        warehouse_id = getattr(sale, 'warehouse_id', None)
        
        for line in sale.lines:
            StockService.add_stock(
                product_id=line.product_id,
                quantity=line.quantity,
                reference_type=GLRef.SALE_REVERSED,
                reference_id=sale.id,
                notes=f'إلغاء بيع: {sale.sale_number}',
                warehouse_id=warehouse_id  # ← نفس المستودع
            )
    
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

