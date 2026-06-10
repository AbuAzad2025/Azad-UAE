import logging
from datetime import datetime, timezone
from decimal import Decimal
from extensions import db
from flask import current_app

logger = logging.getLogger(__name__)
from utils.gl_reference_types import GLRef
from utils.gl_services import (
    gl_post_or_fail,
    gl_ensure_core_accounts,
    gl_get_customer_credit_account,
    gl_get_customer_credit_concept,
    gl_get_default_liquidity_account,
    gl_resolve_exchange_rate,
)


def validate_cheque(cheque):
    if not cheque.cheque_number:
        raise ValueError("رقم الشيك مطلوب")
    if not cheque.cheque_bank_number:
        raise ValueError("رقم الشيك البنكي مطلوب")
    if not cheque.bank_name:
        raise ValueError("اسم البنك مطلوب")
    if not cheque.amount or cheque.amount <= 0:
        raise ValueError("المبلغ يجب أن يكون أكبر من صفر")
    if not cheque.issue_date:
        raise ValueError("تاريخ الإصدار مطلوب")
    if not cheque.due_date:
        raise ValueError("تاريخ الاستحقاق مطلوب")
    if cheque.cheque_type not in ('incoming', 'outgoing'):
        raise ValueError("نوع الشيك غير صحيح")


def calculate_amount_aed(cheque):
    if cheque.exchange_rate:
        cheque.amount_aed = cheque.amount * cheque.exchange_rate
    else:
        cheque.amount_aed = cheque.amount


def _post_gl(cheque, lines, description, reference_type):
    gl_ensure_core_accounts(tenant_id=getattr(cheque, 'tenant_id', None))
    return gl_post_or_fail(
        lines=lines,
        description=description,
        reference_type=reference_type,
        reference_id=cheque.id,
        currency='AED',
        exchange_rate=1.0,
        branch_id=cheque.branch_id,
        tenant_id=getattr(cheque, 'tenant_id', None),
    )


def process_cheque_deposit(cheque, deposit_date=None):
    if cheque.status not in ['pending', 'under_collection']:
        raise ValueError(f'لا يمكن إيداع شيك بحالة: {cheque.status_ar}')
    cheque.status = 'deposited'
    cheque.deposit_date = deposit_date or datetime.now().date()


def process_cheque_receive(cheque):
    if cheque.cheque_type != 'incoming':
        return None
    credit_account = gl_get_customer_credit_account(
        cheque.customer,
        branch_id=cheque.branch_id,
        tenant_id=getattr(cheque, 'tenant_id', None),
    ) if cheque.customer_id else '1130'
    credit_concept = gl_get_customer_credit_concept(cheque.customer) if cheque.customer_id else 'AR'
    lines = [
        {
            'account': '1150',
            'concept_code': 'CHEQUES_UNDER_COLLECTION',
            'debit': cheque.amount_aed,
            'credit': 0,
            'description': f'استلام شيك رقم {cheque.cheque_bank_number}'
        },
        {
            'account': credit_account,
            'concept_code': credit_concept,
            'debit': 0,
            'credit': cheque.amount_aed,
            'description': f'استلام شيك من عميل - رقم {cheque.cheque_bank_number}'
        }
    ]
    return _post_gl(
        cheque,
        lines,
        description=f'استلام شيك وارد رقم {cheque.cheque_bank_number}',
        reference_type=GLRef.CHEQUE_RECEIVE,
    )


def process_cheque_issue(cheque):
    if cheque.cheque_type != 'outgoing':
        return None
    if cheque.supplier_id:
        debit_account = '2110'
        debit_concept = 'AP'
    elif cheque.customer_id:
        debit_account = gl_get_customer_credit_account(
            cheque.customer,
            branch_id=cheque.branch_id,
            tenant_id=getattr(cheque, 'tenant_id', None),
        )
        debit_concept = gl_get_customer_credit_concept(cheque.customer)
    else:
        debit_account = '2110'
        debit_concept = 'AP'
    lines = [
        {
            'account': debit_account,
            'concept_code': debit_concept,
            'debit': cheque.amount_aed,
            'credit': 0,
            'description': f'إصدار شيك رقم {cheque.cheque_bank_number}'
        },
        {
            'account': '2120',
            'concept_code': 'DEFERRED_CHEQUES_PAYABLE',
            'debit': 0,
            'credit': cheque.amount_aed,
            'description': f'إصدار شيك - رقم {cheque.cheque_bank_number}'
        }
    ]
    entry = _post_gl(
        cheque,
        lines,
        description=f'إصدار شيك صادر رقم {cheque.cheque_bank_number}',
        reference_type=GLRef.CHEQUE_ISSUE,
    )
    cheque.gl_journal_entry_id = entry.id
    return entry


def _create_clearing_journal_entry(cheque):
    bank_account = gl_get_default_liquidity_account(
        'bank',
        branch_id=cheque.branch_id,
        tenant_id=getattr(cheque, 'tenant_id', None),
    )
    lines = []
    if cheque.cheque_type == 'incoming':
        lines.append({
            'account': bank_account,
            'concept_code': 'BANK',
            'debit': cheque.actual_amount_aed,
            'credit': 0,
            'description': f'صرف شيك وارد رقم {cheque.cheque_bank_number}'
        })
        lines.append({
            'account': '1150',
            'concept_code': 'CHEQUES_UNDER_COLLECTION',
            'debit': 0,
            'credit': cheque.amount_aed,
            'description': f'صرف شيك رقم {cheque.cheque_bank_number}'
        })
        if cheque.currency_gain_loss and abs(cheque.currency_gain_loss) > Decimal('0.01'):
            if cheque.currency_gain_loss > 0:
                lines.append({
                    'account': '4400',
                    'concept_code': 'FX_GAIN',
                    'debit': 0,
                    'credit': abs(cheque.currency_gain_loss),
                    'description': f'ربح فرق عملة - شيك {cheque.cheque_bank_number}'
                })
            else:
                lines.append({
                    'account': '6900',
                    'concept_code': 'FX_LOSS',
                    'debit': abs(cheque.currency_gain_loss),
                    'credit': 0,
                    'description': f'خسارة فرق عملة - شيك {cheque.cheque_bank_number}'
                })
    elif cheque.cheque_type == 'outgoing':
        lines.append({
            'account': '2120',
            'concept_code': 'DEFERRED_CHEQUES_PAYABLE',
            'debit': cheque.amount_aed,
            'credit': 0,
            'description': f'صرف شيك صادر رقم {cheque.cheque_bank_number}'
        })
        lines.append({
            'account': bank_account,
            'concept_code': 'BANK',
            'debit': 0,
            'credit': cheque.actual_amount_aed,
            'description': f'صرف شيك رقم {cheque.cheque_bank_number}'
        })
        if cheque.currency_gain_loss and abs(cheque.currency_gain_loss) > Decimal('0.01'):
            if cheque.currency_gain_loss > 0:
                lines.append({
                    'account': '6900',
                    'concept_code': 'FX_LOSS',
                    'debit': abs(cheque.currency_gain_loss),
                    'credit': 0,
                    'description': f'خسارة فرق عملة - شيك {cheque.cheque_bank_number}'
                })
            else:
                lines.append({
                    'account': '4400',
                    'concept_code': 'FX_GAIN',
                    'debit': 0,
                    'credit': abs(cheque.currency_gain_loss),
                    'description': f'ربح فرق عملة - شيك {cheque.cheque_bank_number}'
                })
    if lines:
        _post_gl(
            cheque,
            lines=lines,
            description=f'صرف شيك {cheque.cheque_type_ar} رقم {cheque.cheque_bank_number}',
            reference_type=GLRef.CHEQUE_CLEAR,
        )


def process_cheque_clear(cheque, clearance_date=None, clearance_exchange_rate=None):
    if cheque.status not in ['deposited', 'pending']:
        raise ValueError(f'لا يمكن تأكيد صرف شيك بحالة: {cheque.status_ar}')
    cheque.status = 'cleared'
    cheque.clearance_date = clearance_date or datetime.now().date()
    if cheque.currency != 'AED' and clearance_exchange_rate:
        cheque.clearance_exchange_rate = Decimal(str(clearance_exchange_rate))
    elif cheque.currency != 'AED':
        try:
            rate_info = gl_resolve_exchange_rate(cheque.currency, 'AED')
            cheque.clearance_exchange_rate = Decimal(str(rate_info['rate']))
        except:
            cheque.clearance_exchange_rate = cheque.exchange_rate
    else:
        cheque.clearance_exchange_rate = Decimal('1.0')
    cheque.actual_amount_aed = cheque.amount * cheque.clearance_exchange_rate
    cheque.currency_gain_loss = cheque.actual_amount_aed - cheque.amount_aed
    _create_clearing_journal_entry(cheque)
    from models.payment import Payment, Receipt
    tid = getattr(cheque, 'tenant_id', None)
    pmt_q = Payment.query.filter_by(cheque_id=cheque.id)
    if tid:
        pmt_q = pmt_q.filter(Payment.tenant_id == tid)
    payment = pmt_q.first()
    if payment:
        payment.confirm_payment()
    rcpt_q = Receipt.query.filter_by(cheque_id=cheque.id)
    if tid:
        rcpt_q = rcpt_q.filter(Receipt.tenant_id == tid)
    receipt = rcpt_q.first()
    if receipt:
        receipt.confirm_receipt()


def _create_bounce_journal_entry(cheque):
    lines = []
    if cheque.cheque_type == 'incoming':
        ar_account = gl_get_customer_credit_account(
            cheque.customer,
            branch_id=cheque.branch_id,
            tenant_id=getattr(cheque, 'tenant_id', None),
        ) if cheque.customer_id else '1130'
        ar_concept = gl_get_customer_credit_concept(cheque.customer) if cheque.customer_id else 'AR'
        lines.append({
            'account': ar_account,
            'concept_code': ar_concept,
            'debit': cheque.amount_aed,
            'credit': 0,
            'description': f'ارتداد شيك رقم {cheque.cheque_bank_number} - إرجاع الدين'
        })
        lines.append({
            'account': '1150',
            'concept_code': 'CHEQUES_UNDER_COLLECTION',
            'debit': 0,
            'credit': cheque.amount_aed,
            'description': f'ارتداد شيك رقم {cheque.cheque_bank_number}'
        })
    elif cheque.cheque_type == 'outgoing':
        lines.append({
            'account': '2120',
            'concept_code': 'DEFERRED_CHEQUES_PAYABLE',
            'debit': cheque.amount_aed,
            'credit': 0,
            'description': f'ارتداد شيك صادر رقم {cheque.cheque_bank_number}'
        })
        if cheque.supplier_id:
            credit_account = '2110'
            credit_concept = 'AP'
        elif cheque.customer_id:
            credit_account = gl_get_customer_credit_account(
                cheque.customer,
                branch_id=cheque.branch_id,
                tenant_id=getattr(cheque, 'tenant_id', None),
            )
            credit_concept = gl_get_customer_credit_concept(cheque.customer)
        else:
            credit_account = '2110'
            credit_concept = 'AP'
        lines.append({
            'account': credit_account,
            'concept_code': credit_concept,
            'debit': 0,
            'credit': cheque.amount_aed,
            'description': f'ارتداد شيك رقم {cheque.cheque_bank_number} - إرجاع الالتزام'
        })
    if lines:
        _post_gl(
            cheque,
            lines=lines,
            description=f'ارتداد شيك {cheque.cheque_type_ar} رقم {cheque.cheque_bank_number}',
            reference_type=GLRef.CHEQUE_BOUNCE,
        )


def process_cheque_bounce(cheque, reason):
    if cheque.status not in ['deposited', 'pending']:
        raise ValueError(f'لا يمكن رفض شيك بحالة: {cheque.status_ar}')
    cheque.status = 'bounced'
    cheque.bounce_reason = reason
    cheque.clearance_date = datetime.now().date()
    _create_bounce_journal_entry(cheque)
    if cheque.cheque_type == 'incoming' and cheque.customer_id:
        try:
            cheque.customer.adjust_balance(cheque.amount_aed or Decimal('0'))
        except Exception:
            pass
    from models.payment import Payment, Receipt
    tid = getattr(cheque, 'tenant_id', None)
    pmt_q = Payment.query.filter_by(cheque_id=cheque.id)
    if tid:
        pmt_q = pmt_q.filter(Payment.tenant_id == tid)
    payment = pmt_q.first()
    if payment:
        payment.reject_payment(reason)
    rcpt_q = Receipt.query.filter_by(cheque_id=cheque.id)
    if tid:
        rcpt_q = rcpt_q.filter(Receipt.tenant_id == tid)
    receipt = rcpt_q.first()
    if receipt:
        receipt.reject_receipt(reason)


def _create_cancel_journal_entry(cheque):
    lines = []
    if cheque.cheque_type == 'incoming':
        ar_account = gl_get_customer_credit_account(
            cheque.customer,
            branch_id=cheque.branch_id,
            tenant_id=getattr(cheque, 'tenant_id', None),
        ) if cheque.customer_id else '1130'
        ar_concept = gl_get_customer_credit_concept(cheque.customer) if cheque.customer_id else 'AR'
        lines = [
            {'account': ar_account, 'concept_code': ar_concept, 'debit': cheque.amount_aed, 'credit': 0,
             'description': f'إلغاء شيك وارد رقم {cheque.cheque_bank_number}'},
            {'account': '1150', 'concept_code': 'CHEQUES_UNDER_COLLECTION', 'debit': 0, 'credit': cheque.amount_aed,
             'description': f'إلغاء شيك رقم {cheque.cheque_bank_number}'},
        ]
    elif cheque.cheque_type == 'outgoing':
        if cheque.supplier_id:
            credit_account = '2110'
            credit_concept = 'AP'
        elif cheque.customer_id:
            credit_account = gl_get_customer_credit_account(
                cheque.customer,
                branch_id=cheque.branch_id,
                tenant_id=getattr(cheque, 'tenant_id', None),
            )
            credit_concept = gl_get_customer_credit_concept(cheque.customer)
        else:
            credit_account = '2110'
            credit_concept = 'AP'
        lines = [
            {'account': '2120', 'concept_code': 'DEFERRED_CHEQUES_PAYABLE', 'debit': cheque.amount_aed, 'credit': 0,
             'description': f'إلغاء شيك صادر رقم {cheque.cheque_bank_number}'},
            {'account': credit_account, 'concept_code': credit_concept, 'debit': 0, 'credit': cheque.amount_aed,
             'description': f'إلغاء شيك رقم {cheque.cheque_bank_number}'},
        ]
    if lines:
        _post_gl(
            cheque,
            lines=lines,
            description=f'إلغاء شيك {cheque.cheque_type_ar} رقم {cheque.cheque_bank_number}',
            reference_type=GLRef.CHEQUE_CANCEL,
        )


def process_cheque_cancel(cheque, reason=None):
    from models import Payment, Receipt
    if cheque.status == 'cancelled':
        return
    cheque.status = 'cancelled'
    if reason:
        cheque.notes = (cheque.notes or '') + f'\nسبب الإلغاء: {reason}'
    _create_cancel_journal_entry(cheque)

    # تحديث المدفوعات والسندات المرتبطة
    for payment in Payment.query.filter_by(cheque_id=cheque.id).all():
        payment.reject_payment(reason or 'تم إلغاء الشيك')
    for receipt in Receipt.query.filter_by(cheque_id=cheque.id).all():
        receipt.reject_receipt(reason or 'تم إلغاء الشيك')


def register_cheque_event_listeners():
    from models import Cheque
    from sqlalchemy import event
    from datetime import date

    @event.listens_for(Cheque, 'before_insert')
    @event.listens_for(Cheque, 'before_update')
    def _auto_update_status(mapper, connection, target):
        try:
            if target.status == 'pending' and target.due_date:
                if isinstance(target.due_date, datetime):
                    due = target.due_date.date()
                else:
                    due = target.due_date
                today = date.today()
                days_overdue = (today - due).days
                if days_overdue > 7:
                    logger.warning(f"Cheque {target.cheque_number} overdue by {days_overdue} days")
        except Exception as e:
            logger.error(f"Failed to check cheque status: {e}")

    @event.listens_for(Cheque, 'after_update')
    def _auto_log_status_change(mapper, connection, target):
        try:
            if target.status in ['cleared', 'bounced']:
                status_ar = 'تم الصرف' if target.status == 'cleared' else 'مرتد'
                logger.info(f"Cheque {target.cheque_number} status changed to: {status_ar}")
        except Exception as e:
            logger.error(f"Failed to log cheque status change: {e}")
