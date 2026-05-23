from decimal import Decimal
from flask import current_app
from flask_login import current_user
from extensions import db
from models import Receipt, Sale
from services.currency_service import CurrencyService
from services.gl_service import GLService
from utils.helpers import generate_number
from utils.branching import branch_scope_id_for
from utils.constants import normalize_payment_method_code


class PaymentService:

    @staticmethod
    def _resolve_branch_id(explicit_branch_id=None, *, user=None, sale=None):
        if explicit_branch_id:
            return explicit_branch_id
        if sale and getattr(sale, "branch_id", None):
            return sale.branch_id
        scoped_branch_id = branch_scope_id_for(user or current_user)
        if scoped_branch_id:
            return scoped_branch_id
        if user is not None and getattr(user, "branch_id", None):
            return user.branch_id
        return getattr(current_user, "branch_id", None) if getattr(current_user, "is_authenticated", False) else None
    
    @staticmethod
    def create_payment(payment_data):
        """
        Create outgoing payment (to supplier)
        
        Args:
            payment_data (dict): {
                'supplier_id': int,
                'amount': Decimal,
                'currency': str,
                'payment_method': str,
                'notes': str,
                ...
            }
        """
        from models import Supplier, Payment
        
        supplier_id = payment_data.get('supplier_id')
        amount = payment_data.get('amount')
        currency = payment_data.get('currency', 'AED')
        payment_method = normalize_payment_method_code(payment_data.get('payment_method', 'cash'))
        notes = payment_data.get('notes')
        user_exchange_rate = payment_data.get('user_exchange_rate')
        reference_number = payment_data.get('reference_number')
        branch_id = PaymentService._resolve_branch_id(
            payment_data.get('branch_id'),
            user=current_user if getattr(current_user, 'is_authenticated', False) else None,
        )
        
        supplier = db.session.get(Supplier, supplier_id)
        if not supplier:
             raise ValueError('المورد غير موجود')
             
        try:
            payment_number = generate_number('PAY', Payment, 'payment_number', branch_id=branch_id)
            
            exchange_rate = CurrencyService.get_exchange_rate(
                currency,
                'AED',
                user_rate=user_exchange_rate
            )
            
            payment = Payment(
                tenant_id=getattr(supplier, 'tenant_id', None) or (getattr(current_user, 'tenant_id', None) if current_user and getattr(current_user, 'is_authenticated', False) else None),
                payment_number=payment_number,
                payment_type='supplier_payment',
                direction='outgoing',
                supplier_id=supplier.id,
                supplier_name=supplier.name,
                amount=Decimal(str(amount)),
                currency=currency,
                exchange_rate=exchange_rate,
                amount_aed=Decimal(str(amount)) * exchange_rate,
                payment_method=payment_method,
                reference_number=reference_number,
                notes=notes,
                user_id=current_user.id if current_user and current_user.is_authenticated else 1,
                branch_id=branch_id,
                payment_confirmed=True # Assuming direct payment for now
            )
            
            db.session.add(payment)
            db.session.flush()

            # تحديث رصيد المورد التراكمي (ما تم دفعه له)
            from decimal import Decimal as _D
            supplier.apply_payment(_D(str(payment.amount_aed or 0)))
            
            # GL Entries
            try:
                GLService.ensure_core_accounts()
                # Debit: Accounts Payable (2110)
                # Credit: Cash/Bank (1110/1120)
                
                credit_account = GLService.get_payment_credit_account(payment_method) # Need to verify this method exists or implement logic
                # Fallback if method doesn't exist
                if not credit_account:
                     if payment_method == 'cash': credit_account = '1110'
                     else: credit_account = '1120'

                lines = [
                    {'account': '2110', 'debit': payment.amount, 'description': f'دفعة للمورد {supplier.name}'},
                    {'account': credit_account, 'credit': payment.amount, 'description': f'سند صرف {payment.payment_number}'}
                ]
                GLService.post_entry(
                    lines,
                    description=f'Payment {payment.payment_number}',
                    reference_type='Payment',
                    reference_id=payment.id,
                    currency=payment.currency,
                    exchange_rate=payment.exchange_rate,
                    branch_id=payment.branch_id
                )
            except Exception as e:
                current_app.logger.warning(f'GL posting failed: {e}')
                
            db.session.commit()
            return payment
            
        except Exception as e:
            db.session.rollback()
            raise e

    @staticmethod
    def create_receipt(payment_data):
        """
        Create receipt from payment data dict
        
        Args:
            payment_data (dict): {
                'customer_id': int,
                'amount': Decimal,
                'currency': str,
                'payment_method': str,
                'notes': str (optional),
                ...
            }
        """
        from models import Customer
        
        customer_id = payment_data.get('customer_id')
        amount = payment_data.get('amount')
        currency = payment_data.get('currency', 'AED')
        payment_method = normalize_payment_method_code(payment_data.get('payment_method', 'cash'))
        notes = payment_data.get('notes')
        user_exchange_rate = payment_data.get('user_exchange_rate')
        reference_number = payment_data.get('reference_number')
        cheque_number = payment_data.get('cheque_number')
        cheque_date = payment_data.get('cheque_date')
        bank_name = payment_data.get('bank_name')
        allocate_to_sales = payment_data.get('allocate_to_sales')
        source_sale = None
        
        # Convert cheque_date to date object if it's a string
        if cheque_date and isinstance(cheque_date, str):
            from datetime import datetime
            try:
                cheque_date = datetime.strptime(cheque_date, '%Y-%m-%d').date()
            except ValueError:
                raise ValueError('تاريخ الشيك غير صالح')
        
        customer = db.session.get(Customer, customer_id)
        try:
            # تحديد نوع المصدر والاتجاه
            source_type = 'manual'  # افتراضي
            source_id = None
            direction = 'incoming'  # سندات القبض دائماً وارد
            
            if allocate_to_sales:
                # إذا كان مرتبط بفاتورة بيع
                source_type = 'sale'
                source_id = list(allocate_to_sales.keys())[0]  # أول فاتورة
                source_sale = db.session.get(Sale, source_id)

            branch_id = PaymentService._resolve_branch_id(
                payment_data.get('branch_id'),
                user=current_user if getattr(current_user, 'is_authenticated', False) else None,
                sale=source_sale,
            )

            receipt_number = generate_number('RCV', Receipt, 'receipt_number', branch_id=branch_id)
            
            exchange_rate = CurrencyService.get_exchange_rate(
                currency,
                'AED',
                user_rate=user_exchange_rate
            )
            
            receipt = Receipt(
                tenant_id=getattr(customer, 'tenant_id', None) or (getattr(current_user, 'tenant_id', None) if current_user and getattr(current_user, 'is_authenticated', False) else None),
                receipt_number=receipt_number,
                source_type=source_type,
                source_id=source_id,
                direction=direction,
                customer_id=customer.id,
                amount=Decimal(str(amount)),
                currency=currency,
                exchange_rate=exchange_rate,
                amount_aed=Decimal(str(amount)) * exchange_rate,
                payment_method=payment_method,
                reference_number=reference_number,
                cheque_number=cheque_number,
                cheque_date=cheque_date,
                bank_name=bank_name,
                notes=notes,
                user_id=current_user.id if current_user and current_user.is_authenticated else 1,
                branch_id=branch_id,
            )
            
            db.session.add(receipt)
            db.session.flush()
            
            # إنشاء سجل الشيك إذا كانت طريقة الدفع شيك
            if payment_method == 'cheque' and cheque_number:
                from models import Cheque
                cheque = Cheque(
                    tenant_id=getattr(customer, 'tenant_id', None) or (getattr(current_user, 'tenant_id', None) if current_user and getattr(current_user, 'is_authenticated', False) else None),
                    cheque_number=cheque_number,
                    cheque_bank_number=cheque_number,  # نفس رقم الشيك
                    cheque_type='incoming',
                    customer_id=customer.id,
                    amount=Decimal(str(amount)),
                    currency=currency,
                    exchange_rate=exchange_rate,
                    amount_aed=Decimal(str(amount)) * exchange_rate,
                    issue_date=receipt.receipt_date.date(),  # تاريخ الإصدار = تاريخ السند
                    due_date=cheque_date,  # تاريخ الاستحقاق
                    bank_name=bank_name,
                    status='pending',
                    notes=notes,
                    branch_id=receipt.branch_id,
                )
                db.session.add(cheque)
                db.session.flush()
                
                # ربط الشيك بالسند
                receipt.cheque_id = cheque.id
                
                # استخدام منطق الشيك المحاسبي (شيكات تحت التحصيل -> ذمم مدينة)
                cheque.receive_cheque()
                # تحديث رصيد العميل التراكمي عند استلام الشيك
                from decimal import Decimal as _D
                customer.apply_receipt(_D(str(receipt.amount_aed or 0)))
            
            else:
                # GL Entry for Standard Receipt (Cash/Bank)
                try:
                    GLService.ensure_core_accounts()
                    payment_account = GLService.get_payment_debit_account(receipt.payment_method)
                    credit_account = GLService.get_customer_credit_account(customer)

                    # Create GL entries
                    lines = [
                        {'account': payment_account, 'debit': receipt.amount, 'description': f'قبض من {customer.name}'},
                        {'account': credit_account, 'credit': receipt.amount, 'description': f'سند قبض {receipt.receipt_number}'}
                    ]
                    GLService.post_entry(lines, description=f'Receipt {receipt.receipt_number}', reference_type='Receipt', reference_id=receipt.id, currency=receipt.currency, exchange_rate=receipt.exchange_rate, branch_id=receipt.branch_id)
                except Exception as e:
                    current_app.logger.warning(f'GL posting failed: {e}')

                # تحديث رصيد العميل التراكمي (ما دُفع منه)
                from decimal import Decimal as _D
                customer.apply_receipt(_D(str(receipt.amount_aed or 0)))
            
            # Allocation Logic (Restored & Improved)
            if allocate_to_sales:
                remaining_amount = Decimal(str(amount))
                
                for sale_id, allocated in allocate_to_sales.items():
                    if remaining_amount <= 0:
                        break
                    
                    sale = Sale.query.get(sale_id)
                    
                    if not sale or sale.customer_id != customer.id:
                        continue
                    
                    allocated_amount = min(Decimal(str(allocated)), remaining_amount, sale.balance_due)
                    
                    # Create Payment record linked to Sale (Crucial for recalculation)
                    from models import Payment
                    sale_payment = Payment(
                        tenant_id=getattr(sale, 'tenant_id', None) or getattr(customer, 'tenant_id', None),
                        payment_number=generate_number('PAY-S', Payment, 'payment_number', branch_id=sale.branch_id),
                        payment_type='sale_payment',
                        direction='incoming',
                        sale_id=sale.id,
                        customer_id=customer.id,
                        amount=allocated_amount,
                        amount_aed=allocated_amount * exchange_rate,
                        currency=currency,
                        exchange_rate=exchange_rate,
                        payment_method=payment_method,
                        reference_number=receipt.receipt_number,
                        payment_confirmed=receipt.payment_confirmed,
                        cheque_id=receipt.cheque_id,
                        notes=f"Allocated from Receipt {receipt.receipt_number}",
                        user_id=current_user.id if current_user and current_user.is_authenticated else 1,
                        branch_id=sale.branch_id or receipt.branch_id,
                    )
                    db.session.add(sale_payment)
                    
                    # Direct update (will be overwritten by recalculate, but good for immediate state)
                    sale.paid_amount += allocated_amount
                    sale.paid_amount_aed += allocated_amount * exchange_rate
                    # sale.balance_due -= allocated_amount # Let recalculate handle this
                    
                    # Trigger recalculation
                    sale.recalculate_payment_status()
                    
                    remaining_amount -= allocated_amount
            
            db.session.commit()
            
            current_app.logger.info(f'Receipt created: {receipt.receipt_number}')
            
            return receipt
        
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'Receipt creation failed: {e}')
            raise
    
    @staticmethod
    def get_customer_balance_aed(customer):
        """مصدر واحد لرصيد العميل بالدرهم - يستخدم نموذج العميل."""
        return Decimal(str(customer.get_balance_aed() or 0))

    @staticmethod
    def get_customer_balance_and_unpaid_sales(customer):
        """استجابة موحدة لرصيد العميل + فواتير غير المدفوعة (للاستخدام في API واحد)."""
        balance_aed = float(PaymentService.get_customer_balance_aed(customer))
        unpaid = PaymentService.get_unpaid_sales(customer)
        unpaid_sales = [{
            'id': s.id,
            'sale_number': s.sale_number,
            'sale_date': s.sale_date.strftime('%Y-%m-%d') if getattr(s.sale_date, 'strftime', None) else str(s.sale_date),
            'total_amount': float(s.total_amount),
            'balance_due': float(s.balance_due),
            'currency': s.currency or 'AED',
        } for s in unpaid]
        return {'balance_aed': balance_aed, 'balance': balance_aed, 'unpaid_sales': unpaid_sales}

    @staticmethod
    def get_unpaid_sales(customer):
        return Sale.query.filter(
            Sale.customer_id == customer.id,
            Sale.status == 'confirmed',
            Sale.balance_due > 0
        ).order_by(Sale.sale_date.asc()).all()
    
    @staticmethod
    def allocate_receipt_to_oldest_sales(receipt, customer):
        try:
            remaining_amount = receipt.amount
            customer.apply_receipt(remaining_amount * receipt.exchange_rate)
            
            unpaid_sales = PaymentService.get_unpaid_sales(customer)
            
            for sale in unpaid_sales:
                if remaining_amount <= 0:
                    break
                
                allocated = min(remaining_amount, sale.balance_due)
                
                sale.paid_amount += allocated
                sale.paid_amount_aed += allocated * receipt.exchange_rate
                sale.balance_due -= allocated
                
                if sale.paid_amount >= sale.total_amount:
                    sale.payment_status = 'paid'
                elif sale.paid_amount > 0:
                    sale.payment_status = 'partial'
                
                remaining_amount -= allocated
            
            db.session.commit()
            
            current_app.logger.info(f'Receipt {receipt.receipt_number} allocated to sales')
        
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'Receipt allocation failed: {e}')
            raise

