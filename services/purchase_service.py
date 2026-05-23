from decimal import Decimal
from flask import current_app
from extensions import db
from models import Purchase, PurchaseLine, Product, Supplier, Warehouse
from services.stock_service import StockService
from services.currency_service import CurrencyService
from services.gl_service import GLService
from utils.branching import ensure_warehouse_access
from utils.helpers import generate_number, create_audit_log
from utils.tenanting import get_active_tenant_id

class PurchaseService:
    @staticmethod
    def create_purchase(user, supplier_data, lines_data, warehouse_id=None, 
                       currency=None, user_exchange_rate=None, 
                       discount_amount=0, tax_rate=0, notes=None):
        """
        Create a new purchase invoice with stock update and GL entries.
        
        Args:
            user: Current user object (creator)
            supplier_data: Dict containing supplier_id or name/phone/email
            lines_data: List of dicts [{'product_id': int, 'quantity': float, 'unit_cost': float, 'discount_percent': float}]
            warehouse_id: ID of the warehouse to add stock to
            currency: Currency code (default 'AED')
            user_exchange_rate: Optional manual exchange rate
            discount_amount: Total discount amount
            tax_rate: Tax percentage
            notes: Optional notes
            
        Returns:
            Purchase object
        """
        if not currency:
            try:
                from models import Tenant
                currency = (Tenant.get_current().default_currency or '').strip() or 'AED'
            except Exception:
                currency = 'AED'
        # Validate Warehouse
        if not warehouse_id:
            raise ValueError('⚠️ يجب اختيار المستودع الذي ستُضاف إليه البضاعة.')
        
        warehouse = ensure_warehouse_access(warehouse_id, user=user)

        # Validate Supplier
        supplier_id = supplier_data.get('supplier_id')
        supplier_name = supplier_data.get('supplier_name')
        
        supplier = None
        if supplier_id:
            supplier = Supplier.query.get(supplier_id)
            if supplier:
                supplier_name = supplier.name
                supplier_data['phone'] = supplier.phone or ''
                supplier_data['email'] = supplier.email or ''
        
        if not supplier_name:
            raise ValueError('⚠️ يجب إدخال اسم المورد.')

        # Generate Number
        purchase_branch_id = warehouse.branch_id or user.branch_id
        purchase_number = generate_number('P', Purchase, 'purchase_number', branch_id=purchase_branch_id)
        
        # Currency Handling
        exchange_rate = CurrencyService.get_exchange_rate(
            currency,
            'AED',
            user_rate=user_exchange_rate
        )
        
        # Create Purchase Header
        tenant_id = get_active_tenant_id(user) or getattr(user, 'tenant_id', None) or getattr(warehouse, 'tenant_id', None) or (getattr(supplier, 'tenant_id', None) if supplier else None)
        purchase = Purchase(
            tenant_id=tenant_id,
            purchase_number=purchase_number,
            supplier_id=supplier_id,
            warehouse_id=warehouse_id,
            branch_id=warehouse.branch_id or user.branch_id,
            supplier_name=supplier_name,
            supplier_phone=supplier_data.get('phone'),
            supplier_email=supplier_data.get('email'),
            currency=currency,
            exchange_rate=exchange_rate,
            discount_amount=Decimal(str(discount_amount or 0)),
            tax_rate=Decimal(str(tax_rate or 0)),
            notes=notes,
            user_id=user.id,
            subtotal=Decimal('0'),
            tax_amount=Decimal('0'),
            total_amount=Decimal('0'),
            amount_aed=Decimal('0')
        )
        
        db.session.add(purchase)
        db.session.flush()
        
        # Process Lines
        subtotal = Decimal('0')
        lines_added = 0
        
        for line_data in lines_data:
            product_id = line_data.get('product_id')
            quantity = Decimal(str(line_data.get('quantity') or 0))
            unit_cost = Decimal(str(line_data.get('unit_cost') or 0))
            discount_percent = Decimal(str(line_data.get('discount_percent') or 0))
            
            if product_id and quantity > 0 and unit_cost >= 0:
                product = Product.query.get(product_id)
                if product:
                    line = PurchaseLine(
                        tenant_id=tenant_id,
                        purchase_id=purchase.id,
                        product_id=product_id,
                        quantity=quantity,
                        unit_cost=unit_cost,
                        discount_percent=discount_percent
                    )
                    
                    # Calculate line totals
                    line_subtotal = quantity * unit_cost
                    line_discount = line_subtotal * (discount_percent / Decimal('100'))
                    line_total = line_subtotal - line_discount
                    
                    line.line_total = line_total # Assuming model has this field or similar logic
                    
                    db.session.add(line)
                    subtotal += line_total
                    lines_added += 1
        
        if lines_added == 0:
            db.session.rollback()
            raise ValueError('⚠️ يجب إضافة منتج واحد على الأقل للفاتورة.')
            
        # Update Totals
        purchase.subtotal = subtotal
        purchase.tax_amount = subtotal * (purchase.tax_rate / Decimal('100'))
        purchase.total_amount = subtotal + purchase.tax_amount - purchase.discount_amount
        
        purchase.amount_aed = purchase.total_amount * purchase.exchange_rate
        
        db.session.flush()
        
        # Stock Update
        StockService.process_purchase_lines(purchase, warehouse_id)
        
        # GL Entries
        GLService.ensure_core_accounts()
        
        inventory_debit = (purchase.subtotal or Decimal('0')) - (purchase.discount_amount or Decimal('0'))
        if inventory_debit < Decimal('0'):
            inventory_debit = Decimal('0')

        lines = [
            # Debit: Inventory (Amount before tax)
            {'account': '1140', 'debit': inventory_debit, 'description': f'شراء بضاعة {purchase.purchase_number}'},
            # Credit: Accounts Payable (Total Amount)
            {'account': '2110', 'credit': purchase.total_amount, 'description': f'ذمم دائنة - مورد: {purchase.supplier_name}'}
        ]
        
        if purchase.tax_amount > 0:
            lines.append({
                'account': '2130', 
                'debit': purchase.tax_amount, 
                'description': f'ضريبة القيمة المضافة (شراء) {purchase.purchase_number}'
            })
            
        GLService.post_entry(
                lines, 
                description=f'Purchase {purchase.purchase_number}', 
                reference_type='Purchase', 
                reference_id=purchase.id, 
                currency=purchase.currency, 
                exchange_rate=purchase.exchange_rate,
                branch_id=purchase.branch_id
            )
        
        # Update Supplier Stats
        if supplier:
            try:
                # Assuming update_statistics exists on Supplier model or we implement it
                if hasattr(supplier, 'update_statistics'):
                    supplier.update_statistics()
            except Exception as e:
                current_app.logger.warning(f'Supplier stats update failed: {e}')
        
        db.session.commit()
        create_audit_log('create', 'purchases', purchase.id)
        
        return purchase
