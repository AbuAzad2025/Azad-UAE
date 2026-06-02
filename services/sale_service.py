from decimal import Decimal, ROUND_HALF_UP
from flask import current_app
from extensions import db
from models import PartnerCommissionEntry, Sale, SaleLine, Payment
from services.stock_service import StockService
from services.currency_service import CurrencyService
from services.gl_posting import post_or_fail, GlPostingError
from utils.gl_reference_types import GLRef
from services.commission_gl_service import post_sale_commissions
from services.gl_service import GLService
from utils.branching import ensure_warehouse_access
from utils.constants import normalize_payment_method_code
from utils.field_validators import (
    canonical_payment_type,
    validate_currency_code,
    validate_payment_method,
    validate_sale_status,
)
from utils.helpers import generate_number
from utils.tenanting import get_active_tenant_id
from utils.tax_settings import normalize_tax_rate, should_post_vat_gl


class SaleService:
    
    @staticmethod
    def create_sale(customer, seller, lines_data, warehouse_id=None, currency=None, user_exchange_rate=None, 
                    discount_amount=0, shipping_cost=0, tax_rate=0, notes=None, payment_data=None,
                    source='internal', sale_status=None, checkout_payment_method=None,
                    defer_fulfillment=False):
        """
        Create a new sale with proper validations and decimal precision
        All financial calculations use Decimal for accuracy
        Uses database transaction with automatic rollback on error
        """
        # Input validations
        if not customer or not customer.is_active:
            raise ValueError('⚠️ العميل غير صالح أو غير نشط.\n💡 اختر عميل نشط من القائمة أو قم بتفعيله.')
        
        if not seller or not seller.is_active:
            raise ValueError('البائع غير صالح أو غير نشط')
        
        if not lines_data or len(lines_data) == 0:
            raise ValueError('⚠️ يجب إضافة منتج واحد على الأقل للفاتورة.\n💡 اضغط زر "➕ إضافة صف" واختر منتجاً.')

        if not currency:
            try:
                from models import Tenant
                currency = (Tenant.get_current().default_currency or '').strip() or 'AED'
            except Exception:
                currency = 'AED'
        currency = validate_currency_code(currency)

        # Validate discount and tax (rate finalized after tenant/warehouse resolved)
        discount_decimal = Decimal(str(discount_amount)) if discount_amount else Decimal('0')
        shipping_decimal = Decimal(str(shipping_cost)) if shipping_cost else Decimal('0')
        raw_tax_rate = Decimal(str(tax_rate)) if tax_rate else Decimal('0')
        
        if discount_decimal < Decimal('0'):
            raise ValueError('قيمة الخصم لا يمكن أن تكون سالبة')
        
        if shipping_decimal < Decimal('0'):
            raise ValueError('تكلفة الشحن لا يمكن أن تكون سالبة')
        
        # تحديد المستودع بطريقة ذكية
        from models import Warehouse
        if not warehouse_id:
            warehouse = None
            seller_branch_id = getattr(seller, 'branch_id', None)
            warehouse_query = Warehouse.query.filter_by(is_active=True)
            if seller_branch_id:
                warehouse_query = warehouse_query.filter_by(branch_id=seller_branch_id)
            warehouse = warehouse_query.filter_by(is_main=True).first() or warehouse_query.first()
            if warehouse:
                warehouse_id = warehouse.id
        else:
            warehouse = ensure_warehouse_access(warehouse_id, user=seller)

        if not warehouse_id or not warehouse:
            raise ValueError('⚠️ لا يوجد مستودع متاح لهذا الفرع.\n💡 أنشئ مستودعاً للفرع أو اختر مستودعاً صحيحاً.')
        
        sale_branch_id = warehouse.branch_id or seller.branch_id
        tenant_id = get_active_tenant_id(seller) or getattr(seller, 'tenant_id', None) or getattr(customer, 'tenant_id', None)
        tax_rate_decimal = normalize_tax_rate(raw_tax_rate, tenant_id)

        try:
            sale_number = generate_number(
                'S', Sale, 'sale_number', branch_id=sale_branch_id, tenant_id=tenant_id
            )
            paid_amount_aed = Decimal('0')
            
            exchange_rate = CurrencyService.get_exchange_rate(
                currency, 
                'AED', 
                user_rate=user_exchange_rate
            )
            
            # Validate exchange rate
            if exchange_rate <= Decimal('0'):
                raise ValueError('سعر الصرف غير صالح')
            
            # Create Sale Header
            sale = Sale(
                tenant_id=tenant_id,
                sale_number=sale_number,
                customer_id=customer.id,
                seller_id=seller.id,
                warehouse_id=warehouse_id,  # ← المستودع المحدد
                branch_id=sale_branch_id,
                currency=currency,
                exchange_rate=exchange_rate,
                discount_amount=discount_decimal,
                shipping_cost=shipping_decimal,
                tax_rate=tax_rate_decimal,
                total_amount=Decimal('0'),  # Temporary - will be calculated
                amount_aed=Decimal('0'),    # Temporary - will be calculated
                notes=notes
            )
            
            db.session.add(sale)
            db.session.flush() # Get ID for lines
            
            subtotal = Decimal('0')
            
            for line_data in lines_data:
                product = line_data['product']
                quantity = Decimal(str(line_data['quantity']))
                
                # Validate quantity
                if quantity <= Decimal('0'):
                    raise ValueError(f'⚠️ المنتج "{product.name}": الكمية يجب أن تكون أكبر من صفر.\n💡 أدخل كمية صحيحة مثل: 1, 2, 5, 10')
                
                # Check stock availability
                available, msg = StockService.check_availability_in_warehouse(product.id, quantity, warehouse_id)
                if not available:
                    raise ValueError(f'{product.name}: {msg}')
                
                # Get unit price
                if line_data.get('unit_price'):
                    unit_price = Decimal(str(line_data['unit_price']))
                else:
                    unit_price = product.get_price_for_customer(customer.customer_type)
                
                # Validate unit price
                if unit_price <= Decimal('0'):
                    raise ValueError(f'⚠️ المنتج "{product.name}": السعر يجب أن يكون أكبر من صفر.\n💡 أدخل سعر صحيح بالدرهم.')
                
                discount_percent = Decimal(str(line_data.get('discount_percent', 0)))
                
                # Validate line discount
                if discount_percent < Decimal('0') or discount_percent > Decimal('100'):
                    raise ValueError(f'{product.name}: نسبة الخصم يجب أن تكون بين 0 و 100')
                
                # --- Serial Number Handling ---
                if product.has_serial_number:
                    required_serials = int(quantity)
                    provided_serials = line_data.get('serials', [])
                    
                    # Validate count
                    if len(provided_serials) != required_serials:
                        raise ValueError(f'⚠️ المنتج "{product.name}" يتطلب {required_serials} رقم تسلسلي، ولكن تم إدخال {len(provided_serials)} فقط.\n💡 اضغط على زر "سيريال" بجانب المنتج لإدخال الأرقام.')
                    
                    # Validate uniqueness and availability
                    from models import ProductSerial
                    for sn in provided_serials:
                        sn = sn.strip()
                        if not sn: continue
                        
                        # Check if SN exists for this product
                        existing_sn = ProductSerial.query.filter_by(product_id=product.id, serial_number=sn).first()
                        
                        if existing_sn:
                            # If exists, must be 'available' or 'returned' (ready to sell)
                            if existing_sn.status not in ['available', 'returned']:
                                raise ValueError(f'⚠️ السيريال "{sn}" للمنتج "{product.name}" غير متاح للبيع (حالة: {existing_sn.status}).')
                        else:
                            # If not exists, create it on fly (Scenario 1: Deferred Entry)
                            # This means we are introducing this SN to system at moment of sale
                            existing_sn = ProductSerial(
                                product_id=product.id,
                                serial_number=sn,
                                status='available', # Will change to sold below
                                purchase_line_id=None # Unknown origin
                            )
                            db.session.add(existing_sn)
                            db.session.flush() # Get ID
                # ------------------------------
                
                # Create Sale Line
                line = SaleLine(
                    tenant_id=tenant_id,
                    sale_id=sale.id,
                    product_id=product.id,
                    quantity=quantity,
                    unit_price=unit_price,
                    discount_percent=discount_percent,
                    cost_price=Decimal(str(product.cost_price)) if product.cost_price else Decimal('0'),
                    line_total=Decimal('0'), # Initialize with 0
                    notes=line_data.get('notes') # Pass notes if any
                )
                
                # Calculate total before flush
                line.calculate_line_total()
                
                db.session.add(line)
                db.session.flush() # Get Line ID for serials
                
                subtotal += line.line_total

                try:
                    base_amount_aed = (Decimal(str(line.line_total)) * exchange_rate).quantize(
                        Decimal('0.001'), rounding=ROUND_HALF_UP
                    )
                except Exception:
                    base_amount_aed = Decimal('0')

                for ps in getattr(product, 'partner_shares', []) or []:
                    partner_customer_id = getattr(ps, 'partner_customer_id', None)
                    if not partner_customer_id:
                        continue
                    pct = Decimal(str(getattr(ps, 'percentage', 0) or 0))
                    if pct <= Decimal('0'):
                        continue
                    commission_amount_aed = (base_amount_aed * (pct / Decimal('100'))).quantize(
                        Decimal('0.001'), rounding=ROUND_HALF_UP
                    )
                    if commission_amount_aed <= Decimal('0'):
                        continue
                    entry = PartnerCommissionEntry(
                        tenant_id=tenant_id,
                        branch_id=sale_branch_id,
                        sale_id=sale.id,
                        sale_line_id=line.id,
                        partner_customer_id=partner_customer_id,
                        product_id=product.id,
                        percentage=pct,
                        base_amount_aed=base_amount_aed,
                        commission_amount_aed=commission_amount_aed,
                    )
                    db.session.add(entry)
                
                # --- Link Serials to Sale Line ---
                if product.has_serial_number:
                    from models import ProductSerial
                    from datetime import datetime, timedelta
                    
                    provided_serials = line_data.get('serials', [])
                    for sn in provided_serials:
                        serial_obj = ProductSerial.query.filter_by(product_id=product.id, serial_number=sn).first()
                        if serial_obj:
                            serial_obj.status = 'sold'
                            serial_obj.sale_line_id = line.id
                            
                            # Calculate Warranty
                            if product.warranty_days > 0:
                                serial_obj.warranty_start_date = datetime.now()
                                serial_obj.warranty_end_date = datetime.now() + timedelta(days=product.warranty_days)
                            
                            db.session.add(serial_obj)
                # ---------------------------------
            
            sale.subtotal = subtotal
            sale.calculate_totals()
            
            # Handle payment if provided
            if payment_data:
                paid_amount = Decimal(str(payment_data.get('amount', 0)))
                payment_currency = payment_data.get('currency', 'AED')
                payment_exchange_rate = payment_data.get('exchange_rate', 1.0)
                
                # Convert payment to AED
                payment_exchange_decimal = Decimal(str(payment_exchange_rate)) if payment_exchange_rate else Decimal('1')
                paid_amount_aed = (paid_amount * payment_exchange_decimal).quantize(
                    Decimal('0.001'), rounding=ROUND_HALF_UP
                )
                
                # Validate payment amount (in AED)
                if paid_amount_aed < Decimal('0'):
                    raise ValueError('مبلغ الدفع لا يمكن أن يكون سالب')
                
                # Store payment in AED
                sale.paid_amount = paid_amount  # في عملة الفاتورة
                sale.paid_amount_aed = paid_amount_aed  # محول للدرهم
                
                # Handle overpayment (credit to customer)
                if paid_amount_aed > sale.amount_aed:
                    overpayment = paid_amount_aed - sale.amount_aed
                    payment_note = f"\n[دفع زائد] مبلغ {overpayment} AED سُجّل كرصيد للزبون"
                    sale.notes = (sale.notes or '') + payment_note
                
                # Add payment currency info to notes if not AED
                if payment_currency != 'AED':
                    payment_note = f"\n[دفعة] {paid_amount} {payment_currency} = {paid_amount_aed} AED (سعر: {payment_exchange_rate})"
                    sale.notes = (sale.notes or '') + payment_note
            
            sale.calculate_totals()
            
            db.session.flush()

            sale.source = source or 'internal'
            if sale_status:
                sale.status = validate_sale_status(sale_status)
            if checkout_payment_method:
                sale.checkout_payment_method = str(checkout_payment_method).strip().lower()[:50]

            if defer_fulfillment:
                db.session.commit()
                current_app.logger.info(f'Sale created (deferred): {sale.sale_number}')
                return sale

            SaleService.fulfill_sale(sale, payment_data=payment_data, paid_amount_aed=paid_amount_aed)

            db.session.commit()
            
            current_app.logger.info(f'Sale created: {sale.sale_number}')
            
            return sale
        
        except Exception as e:
            db.session.rollback()
            current_app.logger.error("Sale creation failed (%s)", e.__class__.__name__)
            raise
    
    @staticmethod
    def fulfill_sale(sale, payment_data=None, paid_amount_aed=None):
        """
        Deduct stock, post GL, commissions, and customer balances for an existing sale.
        Used at POS checkout and when confirming deferred online store orders.
        """
        customer = sale.customer
        if not customer:
            raise ValueError('العميل غير موجود')

        warehouse_id = sale.warehouse_id
        tenant_id = getattr(sale, 'tenant_id', None)
        exchange_rate = Decimal(str(sale.exchange_rate or 1))

        if SaleService.has_inventory_posted(sale):
            raise ValueError('تم تنفيذ المخزون لهذه الفاتورة مسبقاً')

        for line in sale.lines:
            available, msg = StockService.check_availability_in_warehouse(
                line.product_id, line.quantity, warehouse_id
            )
            if not available:
                product_name = line.product.name if line.product else str(line.product_id)
                raise ValueError(f'{product_name}: {msg}')

        StockService.process_sale_lines(sale, warehouse_id)

        paid_aed = Decimal(str(paid_amount_aed)) if paid_amount_aed is not None else Decimal('0')
        if payment_data and payment_data.get('amount', 0) > 0:
            paid_amount = Decimal(str(payment_data.get('amount', 0)))
            payment_exchange_rate = payment_data.get('exchange_rate', 1.0)
            payment_exchange_decimal = Decimal(str(payment_exchange_rate)) if payment_exchange_rate else Decimal('1')
            paid_aed = (paid_amount * payment_exchange_decimal).quantize(
                Decimal('0.001'), rounding=ROUND_HALF_UP
            )
            if paid_aed < Decimal('0'):
                raise ValueError('مبلغ الدفع لا يمكن أن يكون سالب')

            sale.paid_amount = paid_amount
            sale.paid_amount_aed = paid_aed
            if paid_aed > sale.amount_aed:
                overpayment = paid_aed - sale.amount_aed
                payment_note = f"\n[دفع زائد] مبلغ {overpayment} AED سُجّل كرصيد للزبون"
                sale.notes = (sale.notes or '') + payment_note

            payment_currency = payment_data.get('currency', 'AED')
            if payment_currency != 'AED':
                payment_note = (
                    f"\n[دفعة] {paid_amount} {payment_currency} = {paid_aed} AED "
                    f"(سعر: {payment_exchange_rate})"
                )
                sale.notes = (sale.notes or '') + payment_note

            SaleService.create_payment_for_sale(
                sale=sale,
                amount=payment_data['amount'],
                payment_method=payment_data['payment_method'],
                currency=payment_data.get('currency', 'AED'),
                exchange_rate=payment_data.get('exchange_rate', 1.0),
                reference_number=payment_data.get('reference_number'),
                cheque_number=payment_data.get('cheque_number'),
                cheque_date=payment_data.get('cheque_date'),
                bank_name=payment_data.get('bank_name'),
                notes=payment_data.get('notes'),
            )

        sale.calculate_totals()
        customer.total_purchases += sale.amount_aed
        customer.update_classification()

        GLService.ensure_core_accounts(tenant_id=tenant_id)

        cogs_total = sum(
            (Decimal(str(line.cost_price)) * Decimal(str(line.quantity)) for line in sale.lines),
            Decimal('0'),
        )
        cogs_total_aed = (cogs_total * exchange_rate).quantize(
            Decimal('0.001'), rounding=ROUND_HALF_UP
        )

        ar_account = '1130'
        if customer.customer_type == 'partner':
            ar_account = '3350'
        elif customer.customer_type == 'merchant':
            ar_account = '2115'

        gl_lines = [
            {
                'account': ar_account,
                'debit': sale.total_amount,
                'description': f'فاتورة {sale.sale_number}',
            },
            {
                'account': '4100',
                'credit': sale.subtotal,
                'description': 'إيرادات المبيعات',
            },
        ]

        if sale.shipping_cost > Decimal('0'):
            gl_lines.append({
                'account': '4300',
                'credit': sale.shipping_cost,
                'description': 'إيرادات الشحن',
            })

        if sale.discount_amount > Decimal('0'):
            gl_lines.append({
                'account': '5200',
                'debit': sale.discount_amount,
                'description': 'خصومات ممنوحة',
            })

        if sale.tax_amount > Decimal('0') and should_post_vat_gl(tenant_id):
            gl_lines.append({
                'account': '2130',
                'credit': sale.tax_amount,
                'description': 'ضرائب مستحقة',
            })

        post_or_fail(
            gl_lines,
            description=f'Sale {sale.sale_number}',
            reference_type=GLRef.SALE,
            reference_id=sale.id,
            currency=sale.currency,
            exchange_rate=sale.exchange_rate,
            branch_id=sale.branch_id,
        )

        if cogs_total_aed > Decimal('0'):
            cogs_lines = [
                {
                    'account': '5100',
                    'debit': cogs_total_aed,
                    'description': 'تكلفة البضاعة المباعة',
                },
                {
                    'account': '1140',
                    'credit': cogs_total_aed,
                    'description': 'خصم من المخزون',
                },
            ]
            post_or_fail(
                cogs_lines,
                description=f'COGS - Sale {sale.sale_number}',
                reference_type=GLRef.SALE_COGS,
                reference_id=sale.id,
                currency='AED',
                exchange_rate=1.0,
                branch_id=sale.branch_id,
            )

        post_sale_commissions(sale)

        from decimal import Decimal as _D
        customer.apply_sale(_D(str(sale.amount_aed or 0)))
        if paid_aed > Decimal('0'):
            customer.apply_receipt(_D(str(paid_aed)))

    @staticmethod
    def has_inventory_posted(sale):
        from models.warehouse import StockMovement
        return StockMovement.query.filter_by(
            reference_type=GLRef.SALE,
            reference_id=sale.id,
            movement_type='sale',
        ).first() is not None
    
    @staticmethod
    def create_payment_for_sale(sale, amount, payment_method, currency='AED', exchange_rate=1.0,
                                reference_number=None, cheque_number=None, cheque_date=None, 
                                bank_name=None, notes=None):
        """
        Create a payment for a sale with proper validations
        Uses Decimal for accurate financial calculations
        """
        from utils.helpers import generate_number
        from datetime import datetime, date
        
        # Validate payment amount
        amount_decimal = Decimal(str(amount))
        if amount_decimal <= Decimal('0'):
            raise ValueError('مبلغ الدفع يجب أن يكون أكبر من صفر')
        
        payment_method = validate_payment_method(payment_method)
        currency = validate_currency_code(currency)
        
        # Validate cheque details if payment method is cheque
        if payment_method == 'cheque':
            if not cheque_number:
                raise ValueError('⚠️ رقم الشيك مطلوب عند الدفع بشيك.\n💡 أدخل رقم الشيك وتاريخ الاستحقاق واسم البنك.')
            if not cheque_date:
                raise ValueError('⚠️ تاريخ الاستحقاق مطلوب للشيك.\n💡 حدد تاريخ صرف الشيك من البنك.')
            if not bank_name:
                raise ValueError('⚠️ اسم البنك مطلوب للشيك.\n💡 أدخل اسم البنك المسحوب عليه الشيك.')
            
            # Convert cheque_date to date object if it's a string
            if isinstance(cheque_date, str):
                try:
                    cheque_date = datetime.strptime(cheque_date, '%Y-%m-%d').date()
                except ValueError:
                    raise ValueError('تاريخ الشيك غير صالح')
        
        payment_number = generate_number(
            'PAY',
            Payment,
            'payment_number',
            branch_id=sale.branch_id,
            tenant_id=getattr(sale, 'tenant_id', None),
        )
        
        # Calculate AED amount with proper rounding using PROVIDED exchange rate
        exchange_rate_decimal = Decimal(str(exchange_rate))
        amount_aed = (amount_decimal * exchange_rate_decimal).quantize(
            Decimal('0.001'), rounding=ROUND_HALF_UP
        )
        
        payment = Payment(
            tenant_id=getattr(sale, 'tenant_id', None),
            payment_number=payment_number,
            payment_type=canonical_payment_type('sale_payment'),
            sale_id=sale.id,
            customer_id=sale.customer_id,
            amount=amount_decimal,
            currency=currency,
            exchange_rate=exchange_rate_decimal,
            amount_aed=amount_aed,
            payment_method=payment_method,
            reference_number=reference_number,
            cheque_number=cheque_number,
            cheque_date=cheque_date,
            bank_name=bank_name,
            notes=notes,
            user_id=sale.seller_id,
            branch_id=sale.branch_id,
        )
        
        db.session.add(payment)
        db.session.flush()
        
        # إنشاء سجل الشيك إذا كانت طريقة الدفع شيك
        if payment_method == 'cheque' and cheque_number:
            from models import Cheque
            cheque = Cheque(
                tenant_id=getattr(sale, 'tenant_id', None),
                cheque_number=cheque_number,
                cheque_bank_number=cheque_number,  # نفس رقم الشيك
                cheque_type='incoming',
                customer_id=sale.customer_id,
                amount=amount_decimal,
                currency=currency,
                exchange_rate=exchange_rate_decimal,
                amount_aed=amount_aed,
                issue_date=sale.sale_date.date(),  # تاريخ الإصدار = تاريخ الفاتورة
                due_date=cheque_date,  # تاريخ الاستحقاق
                bank_name=bank_name,
                status='pending',
                notes=notes
            )
            db.session.add(cheque)
            db.session.flush()
            
            # ربط الشيك بالدفعة
            payment.cheque_id = cheque.id

        # GL Integration for Payment
        try:
            GLService.ensure_core_accounts(tenant_id=getattr(sale, 'tenant_id', None))
            
            debit_account = GLService.get_payment_debit_account(payment_method)
            credit_account = GLService.get_customer_credit_account(sale.customer)

            post_or_fail(
                [
                    {
                        'account': debit_account, 
                        'debit': amount_decimal, 
                        'description': f'Payment for Sale {sale.sale_number} ({payment_method})'
                    },
                    {
                        'account': credit_account,
                        'credit': amount_decimal, 
                        'description': f'Payment Received {payment.payment_number}'
                    }
                ],
                description=f'Payment {payment.payment_number}', 
                reference_type=GLRef.PAYMENT, 
                reference_id=payment.id, 
                currency=currency, 
                exchange_rate=exchange_rate_decimal,
                branch_id=sale.branch_id
            )
        except Exception as e:
            current_app.logger.error(f'GL posting failed for payment: {e}')
            raise
        
        return payment
    
    @staticmethod
    def cancel_sale(sale):
        if sale.status == 'cancelled':
            raise ValueError('الفاتورة ملغاة بالفعل')
        
        sale.status = 'cancelled'
        
        if SaleService.has_inventory_posted(sale):
            StockService.reverse_sale(sale)
        
            # Reverse GL Entry for Sale (Revenue & AR)
            try:
                GLService.reverse_entry(
                    reference_type=GLRef.SALE,
                    reference_id=sale.id,
                    description=f'Reverse Sale {sale.sale_number} (Cancelled)',
                    tenant_id=getattr(sale, 'tenant_id', None),
                )
                GLService.reverse_entry(
                    reference_type=GLRef.SALE_COGS,
                    reference_id=sale.id,
                    description=f'Reverse COGS {sale.sale_number} (Cancelled)',
                    tenant_id=getattr(sale, 'tenant_id', None),
                )
            except Exception as e:
                db.session.rollback()
                raise ValueError(f'فشل عكس القيد المحاسبي: {e}') from e
            
        db.session.commit()
        
        current_app.logger.info(f'Sale cancelled: {sale.sale_number}')
    
    @staticmethod
    def update_payment_status(sale):
        """
        Update payment status based on paid amount
        Uses Decimal for accurate comparisons
        """
        paid = Decimal(str(sale.paid_amount)) if sale.paid_amount else Decimal('0')
        total = Decimal(str(sale.total_amount))
        
        balance = (total - paid).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
        
        if balance <= Decimal('0'):
            sale.payment_status = 'paid'
            sale.balance_due = Decimal('0')
        elif paid > Decimal('0'):
            sale.payment_status = 'partial'
            sale.balance_due = balance
        else:
            sale.payment_status = 'unpaid'
            sale.balance_due = total
        
        db.session.commit()

