from utils.tenanting import get_active_tenant_id
from decimal import Decimal, ROUND_HALF_UP
from flask import current_app
from flask_login import current_user
from extensions import db
from models import Receipt, Sale
from services.exchange_rate_service import ExchangeRateService
from services.gl_service import GLService
from services.gl_posting import post_or_fail, GlPostingError
from services.cheque_service import process_cheque_receive
from utils.gl_reference_types import GLRef
from utils.helpers import generate_number
from utils.branching import branch_scope_id_for
from utils.constants import normalize_payment_method_code
from utils.currency_utils import get_system_default_currency, resolve_tenant_base_currency
from utils.field_validators import (
    canonical_payment_type,
    validate_currency_code,
    validate_payment_method,
)


class PaymentService:

    @staticmethod
    def _resolve_transaction_rate(currency, user_exchange_rate=None, tenant_id=None):
        from utils.currency_utils import resolve_tenant_base_currency
        base_currency = resolve_tenant_base_currency(tenant_id=tenant_id)
        rate_info = ExchangeRateService.resolve_exchange_rate_for_transaction(
            currency,
            base_currency,
            user_rate=user_exchange_rate,
            tenant_id=tenant_id,
        )
        if rate_info.get('rate_mode') == 'needs_input':
            raise ValueError(
                '⚠️ سعر الصرف غير متوفر.\n'
                '💡 اذهب إلى إعدادات المالك ← أسعار الصرف ← أدخل سعر يدوي، '
                'أو أدخل سعراً في حقل "سعر الصرف".'
            )
        return Decimal(str(rate_info['rate']))

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
        currency = validate_currency_code(payment_data.get('currency', get_system_default_currency()))
        payment_method = validate_payment_method(payment_data.get('payment_method', 'cash'))
        notes = payment_data.get('notes')
        user_exchange_rate = payment_data.get('user_exchange_rate')
        reference_number = payment_data.get('reference_number')
        cheque_number = payment_data.get('cheque_number')
        cheque_date = payment_data.get('cheque_date')
        bank_name = payment_data.get('bank_name') or 'Bank'
        branch_id = PaymentService._resolve_branch_id(
            payment_data.get('branch_id'),
            user=current_user if getattr(current_user, 'is_authenticated', False) else None,
        )

        supplier = db.session.get(Supplier, supplier_id)
        if not supplier:
             raise ValueError('المورد غير موجود')

        try:
            payment_number = generate_number(
                'PAY',
                Payment,
                'payment_number',
                branch_id=branch_id,
                tenant_id=getattr(supplier, 'tenant_id', None),
            )

            exchange_rate = PaymentService._resolve_transaction_rate(currency, user_exchange_rate)

            payment = Payment(
                tenant_id=getattr(supplier, 'tenant_id', None) or (getattr(current_user, 'tenant_id', None) if current_user and getattr(current_user, 'is_authenticated', False) else None),
                payment_number=payment_number,
                payment_type=canonical_payment_type('supplier_payment'),
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
                payment_confirmed=(payment_method != 'cheque')
            )

            db.session.add(payment)
            db.session.flush()

            if payment_method == 'cheque' and cheque_number:
                from models import Cheque
                cheque = Cheque(
                    tenant_id=getattr(supplier, 'tenant_id', None) or (getattr(current_user, 'tenant_id', None) if current_user and getattr(current_user, 'is_authenticated', False) else None),
                    cheque_number=cheque_number,
                    cheque_bank_number=cheque_number,
                    cheque_type='outgoing',
                    supplier_id=supplier.id,
                    amount=Decimal(str(amount)),
                    currency=currency,
                    exchange_rate=exchange_rate,
                    amount_aed=Decimal(str(amount)) * exchange_rate,
                    issue_date=datetime.now(timezone.utc).date(),
                    due_date=cheque_date or datetime.now(timezone.utc).date(),
                    bank_name=bank_name,
                    status='pending',
                    notes=notes,
                    branch_id=branch_id,
                )
                db.session.add(cheque)
                db.session.flush()
                payment.cheque_id = cheque.id

            # تحديث رصيد المورد التراكمي للدفعات المؤكدة والشيكات الصادرة
            # الشيك الصادر يخفض AP فوراً (قيد الإصدار: Dr AP / Cr Deferred Cheques)
            if payment.payment_confirmed or payment_method == 'cheque':
                from decimal import Decimal as _D
                supplier.apply_payment(_D(str(payment.amount_aed or 0)))

            # GL Entries
            tenant_id = getattr(supplier, 'tenant_id', None) or (getattr(current_user, 'tenant_id', None) if current_user and getattr(current_user, 'is_authenticated', False) else None)
            try:
                GLService.ensure_core_accounts(tenant_id=tenant_id)
                # Debit: Accounts Payable (2110)
                # Credit: Cash/Bank (1110/1120)

                credit_account = GLService.get_payment_credit_account(
                    payment_method,
                    branch_id=payment.branch_id,
                    tenant_id=tenant_id,
                )
                lines = [
                    {'account': '2110', 'concept_code': 'AP', 'debit': payment.amount, 'description': f'دفعة للمورد {supplier.name}'},
                    {'account': credit_account, 'concept_code': GLService.get_payment_credit_concept(payment_method), 'credit': payment.amount, 'description': f'سند صرف {payment.payment_number}'}
                ]
                post_or_fail(
                    lines,
                    description=f'Payment {payment.payment_number}',
                    reference_type=GLRef.PAYMENT,
                    reference_id=payment.id,
                    currency=payment.currency,
                    exchange_rate=payment.exchange_rate,
                    branch_id=payment.branch_id,
                    tenant_id=tenant_id,
                )
            except Exception as _e:
                current_app.logger.exception('GL posting failed for payment: %s', _e)
                db.session.rollback()
                raise ValueError(f'فشل الترحيل المحاسبي للدفعة: {_e}') from _e

            try:
                db.session.commit()
            except Exception:
                current_app.logger.exception('Payment commit failed for supplier payment')
                db.session.rollback()
                raise

            return payment

        except Exception:
            current_app.logger.exception('Payment creation failed')
            db.session.rollback()
            raise

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
        currency = validate_currency_code(payment_data.get('currency', get_system_default_currency()))
        payment_method = validate_payment_method(payment_data.get('payment_method', 'cash'))
        notes = payment_data.get('notes')
        user_exchange_rate = payment_data.get('user_exchange_rate')
        reference_number = payment_data.get('reference_number')
        cheque_number = payment_data.get('cheque_number')
        cheque_date = payment_data.get('cheque_date')
        bank_name = payment_data.get('bank_name') or 'Bank'
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
        if not customer:
            raise ValueError('Customer not found.')

        tenant_id = getattr(customer, 'tenant_id', None) or (
            getattr(current_user, 'tenant_id', None)
            if current_user and getattr(current_user, 'is_authenticated', False)
            else None
        )
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

            receipt_number = generate_number(
                'RCV',
                Receipt,
                'receipt_number',
                branch_id=branch_id,
                tenant_id=tenant_id,
            )

            exchange_rate = PaymentService._resolve_transaction_rate(currency, user_exchange_rate)

            receipt = Receipt(
                tenant_id=tenant_id,
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
                payment_confirmed=(payment_method != 'cheque'),
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
                gl_entry = process_cheque_receive(cheque)
                if gl_entry is None:
                    raise GlPostingError('فشل ترحيل الشيك محاسبياً')
                # تحديث رصيد العميل فوراً لأن قيد الاستلام (Dr CUC / Cr AR) يخفض الذمم
                from decimal import Decimal as _D
                customer.apply_receipt(_D(str(receipt.amount_aed or 0)))

            else:
                # GL Entry for Standard Receipt (Cash/Bank)
                try:
                    GLService.ensure_core_accounts(tenant_id=getattr(receipt, 'tenant_id', None))
                    payment_account = GLService.get_payment_debit_account(
                        receipt.payment_method,
                        branch_id=receipt.branch_id,
                        tenant_id=getattr(receipt, 'tenant_id', None),
                    )
                    credit_account = GLService.get_customer_credit_account(
                        customer,
                        branch_id=receipt.branch_id,
                        tenant_id=getattr(receipt, 'tenant_id', None),
                    )

                    # Create GL entries
                    lines = [
                        {'account': payment_account, 'concept_code': GLService.get_payment_debit_concept(receipt.payment_method), 'debit': receipt.amount, 'description': f'قبض من {customer.name}'},
                        {'account': credit_account, 'concept_code': GLService.get_customer_credit_concept(customer), 'credit': receipt.amount, 'description': f'سند قبض {receipt.receipt_number}'}
                    ]
                    post_or_fail(
                        lines,
                        description=f'Receipt {receipt.receipt_number}',
                        reference_type=GLRef.RECEIPT,
                        reference_id=receipt.id,
                        currency=receipt.currency,
                        exchange_rate=receipt.exchange_rate,
                        branch_id=receipt.branch_id,
                        tenant_id=tenant_id,
                    )

                    # FX Gain/Loss auto-posting for direct receipt (same currency, different rate vs original invoice)
                    if allocate_to_sales and source_sale and source_sale.currency == receipt.currency:
                        sale_rate = Decimal(str(source_sale.exchange_rate or 1))
                        receipt_rate = Decimal(str(receipt.exchange_rate or 1))
                        if sale_rate != receipt_rate and receipt.amount > 0:
                            expected_aed = (receipt.amount * sale_rate).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
                            actual_aed = (receipt.amount * receipt_rate).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
                            fx_diff = (actual_aed - expected_aed).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
                            if abs(fx_diff) > Decimal('0.01'):
                                try:
                                    fx_lines = []
                                    if fx_diff > 0:
                                        fx_lines = [
                                            {'account': GLService.get_account_code_for_concept('AR', branch_id=receipt.branch_id, tenant_id=tenant_id, fallback_key='receivable'), 'concept_code': 'AR', 'debit': fx_diff, 'description': f'FX Gain Adjustment - Receipt {receipt.receipt_number}'},
                                            {'account': GLService.get_account_code_for_concept('FX_GAIN', branch_id=receipt.branch_id, tenant_id=tenant_id, fallback_key='fx_gain'), 'concept_code': 'FX_GAIN', 'credit': fx_diff, 'description': f'FX Gain - Receipt {receipt.receipt_number}'},
                                        ]
                                    else:
                                        fx_lines = [
                                            {'account': GLService.get_account_code_for_concept('FX_LOSS', branch_id=receipt.branch_id, tenant_id=tenant_id, fallback_key='fx_loss'), 'concept_code': 'FX_LOSS', 'debit': abs(fx_diff), 'description': f'FX Loss - Receipt {receipt.receipt_number}'},
                                            {'account': GLService.get_account_code_for_concept('AR', branch_id=receipt.branch_id, tenant_id=tenant_id, fallback_key='receivable'), 'concept_code': 'AR', 'credit': abs(fx_diff), 'description': f'FX Loss Adjustment - Receipt {receipt.receipt_number}'},
                                        ]
                                    post_or_fail(
                                        fx_lines,
                                        description=f'FX Gain/Loss - Receipt {receipt.receipt_number}',
                                        reference_type=GLRef.RECEIPT,
                                        reference_id=receipt.id,
                                        currency=resolve_tenant_base_currency(tenant_id=tenant_id),
                                        exchange_rate=1.0,
                                        branch_id=receipt.branch_id,
                                        tenant_id=tenant_id,
                                    )
                                except Exception as fx_err:
                                    current_app.logger.warning('FX auto-posting skipped for receipt %s: %s', receipt.receipt_number, fx_err)
                except Exception as _e:
                    current_app.logger.exception('GL posting failed for receipt: %s', _e)
                    db.session.rollback()
                    raise ValueError(f'فشل الترحيل المحاسبي لسند القبض: {_e}') from _e

                # تحديث رصيد العميل التراكمي (ما دُفع منه)
                from decimal import Decimal as _D
                customer.apply_receipt(_D(str(receipt.amount_aed or 0)))

            # Allocation Logic (Restored & Improved)
            if allocate_to_sales:
                remaining_amount_aed = Decimal(str(receipt.amount_aed or 0))

                for sale_id, allocated in allocate_to_sales.items():
                    if remaining_amount_aed <= 0:
                        break

                    sale = Sale.query.get(sale_id)

                    if not sale or sale.customer_id != customer.id:
                        continue

                    sale_balance_aed = Decimal(str(sale.balance_due or 0))
                    requested_amount = Decimal(str(allocated or 0))
                    requested_amount_aed = (requested_amount * exchange_rate).quantize(
                        Decimal('0.001')
                    )
                    allocated_amount_aed = min(requested_amount_aed, remaining_amount_aed, sale_balance_aed)
                    if allocated_amount_aed <= 0:
                        continue
                    allocated_amount = (allocated_amount_aed / exchange_rate).quantize(
                        Decimal('0.001')
                    )

                    # Create Payment record linked to Sale (Crucial for recalculation)
                    from models import Payment
                    sale_payment = Payment(
                        tenant_id=getattr(sale, 'tenant_id', None) or getattr(customer, 'tenant_id', None),
                        payment_number=generate_number(
                            'PAY-S',
                            Payment,
                            'payment_number',
                            branch_id=sale.branch_id,
                            tenant_id=getattr(sale, 'tenant_id', None),
                        ),
                        payment_type='sale_payment',
                        direction='incoming',
                        sale_id=sale.id,
                        customer_id=customer.id,
                        amount=allocated_amount,
                        amount_aed=allocated_amount_aed,
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
                    db.session.flush()

                    # Direct update (will be overwritten by recalculate, but good for immediate state)
                    sale.paid_amount_aed += allocated_amount_aed
                    sale_rate = Decimal(str(sale.exchange_rate or 1))
                    if sale_rate > 0:
                        sale.paid_amount += (allocated_amount_aed / sale_rate).quantize(
                            Decimal('0.001')
                        )
                    # sale.balance_due -= allocated_amount # Let recalculate handle this

                    # Trigger recalculation
                    sale.recalculate_payment_status()

                    remaining_amount_aed -= allocated_amount_aed

            try:
                db.session.commit()
            except Exception:
                current_app.logger.exception('Receipt commit failed for %s', receipt.receipt_number)
                db.session.rollback()
                raise


            current_app.logger.info(f'Receipt created: {receipt.receipt_number}')

            return receipt

        except Exception:
            current_app.logger.exception('Receipt creation failed')
            db.session.rollback()
            raise

    @staticmethod
    def get_customer_balance_aed(customer):
        """مصدر واحد لرصيد العميل بالدرهم - يستخدم نموذج العميل."""
        return Decimal(str(customer.get_balance_aed() or 0))

    @staticmethod
    def get_customer_balance_scoped(customer_id, branch_id=None, tenant_id=None):
        """رصيد العميل مقيد بالتينانت والفرع. يحسب من SQL مباشر.
        الدلالة: موجب = رصيد للعميل، سالب = ذمة على العميل.
        الصيغة: Receipts - Sales - Outgoing_Payments_to_customer (refunds)
        يعيد Decimal. إذا كان branch_id = None يُرجع الرصيد الكامل (غير مقيد بالفرع)."""
        from models import Payment as PaymentModel

        if tenant_id is None:
            tenant_id = get_active_tenant_id()

        sales_total = db.session.query(db.func.sum(Sale.amount_aed)).filter(
            Sale.customer_id == customer_id,
            Sale.status == 'confirmed',
        )
        receipts_total = db.session.query(db.func.sum(Receipt.amount_aed)).filter(
            Receipt.customer_id == customer_id,
        )
        outgoing_total = db.session.query(db.func.sum(PaymentModel.amount_aed)).filter(
            PaymentModel.customer_id == customer_id,
            PaymentModel.direction == 'outgoing',
        )
        if tenant_id is not None:
            sales_total = sales_total.filter(Sale.tenant_id == tenant_id)
            receipts_total = receipts_total.filter(Receipt.tenant_id == tenant_id)
            outgoing_total = outgoing_total.filter(PaymentModel.tenant_id == tenant_id)
        if branch_id is not None:
            sales_total = sales_total.filter(Sale.branch_id == branch_id)
            receipts_total = receipts_total.filter(Receipt.branch_id == branch_id)
            outgoing_total = outgoing_total.filter(PaymentModel.branch_id == branch_id)

        return (
            (receipts_total.scalar() or Decimal('0'))
            - (sales_total.scalar() or Decimal('0'))
            - (outgoing_total.scalar() or Decimal('0'))
        )

    @staticmethod
    def get_supplier_balance_scoped(supplier_id, branch_id=None, tenant_id=None):
        """رصيد المورد مقيد بالتينانت والفرع. يحسب من SQL مباشر.
        الدلالة: موجب = مستحق للمورد (نحن ندين له)، سالب = المورد مدين لنا.
        الصيغة: Purchases - Outgoing_Payments + Incoming_Payments (refunds from supplier)"""
        if tenant_id is None:
            tenant_id = get_active_tenant_id()

        purchases_total = db.session.query(db.func.sum(Purchase.amount_aed)).filter(
            Purchase.supplier_id == supplier_id,
            Purchase.status == 'confirmed',
        )
        outgoing_total = db.session.query(db.func.sum(Payment.amount_aed)).filter(
            Payment.supplier_id == supplier_id,
            Payment.direction == 'outgoing',
        )
        incoming_total = db.session.query(db.func.sum(Payment.amount_aed)).filter(
            Payment.supplier_id == supplier_id,
            Payment.direction == 'incoming',
        )
        if tenant_id is not None:
            purchases_total = purchases_total.filter(Purchase.tenant_id == tenant_id)
            outgoing_total = outgoing_total.filter(Payment.tenant_id == tenant_id)
            incoming_total = incoming_total.filter(Payment.tenant_id == tenant_id)
        if branch_id is not None:
            purchases_total = purchases_total.filter(Purchase.branch_id == branch_id)
            outgoing_total = outgoing_total.filter(Payment.branch_id == branch_id)
            incoming_total = incoming_total.filter(Payment.branch_id == branch_id)

        return (
            (purchases_total.scalar() or Decimal('0'))
            - (outgoing_total.scalar() or Decimal('0'))
            + (incoming_total.scalar() or Decimal('0'))
        )

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
            'currency': s.currency or get_system_default_currency(),
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
            remaining_amount_aed = Decimal(str(receipt.amount_aed or 0))
            customer.apply_receipt(remaining_amount_aed)

            unpaid_sales = PaymentService.get_unpaid_sales(customer)

            for sale in unpaid_sales:
                if remaining_amount_aed <= 0:
                    break

                sale_balance_aed = Decimal(str(sale.balance_due or 0))
                allocated_aed = min(remaining_amount_aed, sale_balance_aed)
                if allocated_aed <= 0:
                    continue
                sale_rate = Decimal(str(sale.exchange_rate or 1))
                allocated = (allocated_aed / sale_rate).quantize(Decimal('0.001'))

                from models import Payment
                sale_payment = Payment(
                    tenant_id=getattr(sale, 'tenant_id', None) or getattr(customer, 'tenant_id', None),
                    payment_number=generate_number(
                        'PAY-S', Payment, 'payment_number',
                        branch_id=sale.branch_id,
                        tenant_id=getattr(sale, 'tenant_id', None),
                    ),
                    payment_type='sale_payment',
                    direction='incoming',
                    sale_id=sale.id,
                    customer_id=customer.id,
                    amount=allocated,
                    amount_aed=allocated_aed,
                    currency=receipt.currency,
                    exchange_rate=receipt.exchange_rate,
                    payment_method=receipt.payment_method,
                    reference_number=receipt.receipt_number,
                    payment_confirmed=receipt.payment_confirmed,
                    cheque_id=receipt.cheque_id,
                    notes=f"Allocated from Receipt {receipt.receipt_number}",
                    user_id=current_user.id if current_user and current_user.is_authenticated else 1,
                    branch_id=sale.branch_id or receipt.branch_id,
                )
                db.session.add(sale_payment)
                sale.recalculate_payment_status()
                remaining_amount_aed -= allocated_aed

            try:
                db.session.commit()
            except Exception:
                current_app.logger.exception('Receipt allocation commit failed for %s', receipt.receipt_number)
                db.session.rollback()
                raise
            current_app.logger.info(f'Receipt {receipt.receipt_number} allocated to sales')
        except Exception:
            current_app.logger.exception('Receipt allocation failed')
            db.session.rollback()
            raise

