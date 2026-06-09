from decimal import Decimal
from flask import current_app
from extensions import db
from models import Purchase, PurchaseLine, Product, Supplier, Warehouse
from services.stock_service import StockService
from services.exchange_rate_service import ExchangeRateService
from services.gl_service import GLService, GL_ACCOUNTS
from services.gl_posting import post_or_fail
from utils.gl_reference_types import GLRef
from utils.branching import ensure_warehouse_access
from utils.helpers import generate_number
from services.logging_core import LoggingCore
from utils.tenanting import get_active_tenant_id
from utils.currency_utils import resolve_default_currency, get_system_default_currency
from utils.field_validators import validate_currency_code
from utils.tax_settings import normalize_tax_rate, should_post_vat_gl

class PurchaseService:
    @staticmethod
    def create_purchase(user, supplier_data, lines_data, warehouse_id=None, 
                       currency=None, user_exchange_rate=None, 
                       discount_amount=0, tax_rate=0, notes=None,
                       freight=0, insurance=0, customs_duty=0, other_landed_cost=0):
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
            freight: Freight/shipping cost (in purchase currency)
            insurance: Insurance cost (in purchase currency)
            customs_duty: Customs/duty cost (in purchase currency)
            other_landed_cost: Other landed costs (in purchase currency)

        Returns:
            Purchase object
        """
        if not currency:
            try:
                from models import Tenant
                currency = resolve_default_currency(Tenant.get_current())
            except Exception:
                currency = get_system_default_currency()
        currency = (currency or '').strip() or get_system_default_currency()
        currency = validate_currency_code(currency)
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

        # Resolve tenant before numbering, tax normalization, header, lines, and GL posting.
        tenant_id = (
            get_active_tenant_id(user)
            or getattr(user, 'tenant_id', None)
            or getattr(warehouse, 'tenant_id', None)
            or (getattr(supplier, 'tenant_id', None) if supplier else None)
        )

        # Generate Number
        purchase_branch_id = warehouse.branch_id or user.branch_id
        purchase_number = generate_number(
            'P',
            Purchase,
            'purchase_number',
            branch_id=purchase_branch_id,
            tenant_id=tenant_id,
        )
        
        # Currency Handling
        rate_info = ExchangeRateService.resolve_exchange_rate_for_transaction(
            currency,
            'AED',
            user_rate=user_exchange_rate,
        )
        exchange_rate = Decimal(str(rate_info['rate']))
        
        # Create Purchase Header
        effective_tax_rate = normalize_tax_rate(tax_rate, tenant_id)
        purchase = Purchase(
            tenant_id=tenant_id,
            purchase_number=purchase_number,
            supplier_id=supplier_id,
            warehouse_id=warehouse_id,
            branch_id=purchase_branch_id,
            supplier_name=supplier_name,
            supplier_phone=supplier_data.get('phone'),
            supplier_email=supplier_data.get('email'),
            currency=currency,
            exchange_rate=exchange_rate,
            discount_amount=Decimal(str(discount_amount or 0)),
            tax_rate=effective_tax_rate,
            notes=notes,
            user_id=user.id,
            subtotal=Decimal('0'),
            tax_amount=Decimal('0'),
            total_amount=Decimal('0'),
            amount_aed=Decimal('0'),
            freight=Decimal(str(freight or 0)),
            insurance=Decimal(str(insurance or 0)),
            customs_duty=Decimal(str(customs_duty or 0)),
            other_landed_cost=Decimal(str(other_landed_cost or 0)),
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
            
        purchase.subtotal = subtotal
        purchase.calculate_totals()

        # Phase 5: Allocate landed costs proportionally by line value
        total_landed = purchase.total_landed_cost
        if total_landed > 0 and purchase.subtotal > 0:
            for line in purchase.lines:
                if line.line_total and line.line_total > 0:
                    ratio = line.line_total / purchase.subtotal
                    line.landed_cost = (total_landed * ratio).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)

        db.session.flush()

        # Stock Update (uses landed_unit_cost for WAC when MWAC is enabled)
        StockService.process_purchase_lines(purchase, warehouse_id)

        # GL Entries
        GLService.ensure_core_accounts(tenant_id=tenant_id)

        inventory_debit = (purchase.subtotal or Decimal('0')) - (purchase.discount_amount or Decimal('0')) + total_landed
        if inventory_debit < Decimal('0'):
            inventory_debit = Decimal('0')

        total_payable = purchase.total_amount

        lines = [
            {'account': GL_ACCOUNTS['inventory'], 'concept_code': 'INVENTORY_ASSET', 'debit': inventory_debit, 'description': f'شراء بضاعة {purchase.purchase_number}'},
            {'account': GL_ACCOUNTS['payable'], 'concept_code': 'AP', 'credit': total_payable, 'description': f'ذمم دائنة - مورد: {purchase.supplier_name}'}
        ]
        
        if purchase.tax_amount > 0 and should_post_vat_gl(tenant_id):
            lines.append({
                'account': GL_ACCOUNTS['vat_input'],
                'concept_code': 'VAT_INPUT',
                'debit': purchase.tax_amount, 
                'description': f'ضريبة مدخلات (شراء) {purchase.purchase_number}'
            })
            
        post_or_fail(
                lines, 
                description=f'Purchase {purchase.purchase_number}', 
                reference_type=GLRef.PURCHASE, 
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
        LoggingCore.log_audit('create', 'purchases', purchase.id)
        
        return purchase
