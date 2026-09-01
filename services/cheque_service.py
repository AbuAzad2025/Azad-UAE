import logging
from datetime import datetime
from decimal import Decimal

from flask_babel import gettext

from extensions import db
from services.gl_service import GLService
from utils.gl_reference_types import GLRef
from utils.gl_services import (
    gl_ensure_core_accounts,
    gl_get_customer_credit_account,
    gl_get_customer_credit_concept,
    gl_get_default_liquidity_account,
    gl_post_or_fail,
    gl_resolve_exchange_rate,
)

logger = logging.getLogger(__name__)


class ChequeService:
    """Pure business logic for cheque operations. Uses flush only — callers manage transactions."""

    @staticmethod
    def create_cheque(
        cheque_number: str,
        cheque_bank_number: str,
        cheque_type: str,
        bank_name: str,
        bank_branch: str = "",
        account_number: str = "",
        amount=None,
        currency: str = "AED",
        exchange_rate=None,
        issue_date=None,
        due_date=None,
        status: str = "pending",
        drawer_name: str = "",
        drawer_id_number: str = "",
        payee_name: str = "",
        customer_id: int | None = None,
        supplier_id: int | None = None,
        expense_id: int | None = None,
        payment_id: int | None = None,
        notes: str = "",
        user_id: int | None = None,
        branch_id: int | None = None,
        tenant_id: int | None = None,
    ):
        """Create a new cheque. Returns the created cheque (not yet committed)."""
        from models import Cheque
        from services.cheque_service import calculate_amount_aed

        cheque = Cheque(
            cheque_number=cheque_number,
            cheque_bank_number=cheque_bank_number,
            cheque_type=cheque_type,
            bank_name=bank_name,
            bank_branch=bank_branch,
            account_number=account_number,
            amount=amount,
            currency=currency,
            exchange_rate=exchange_rate,
            issue_date=issue_date,
            due_date=due_date,
            drawer_name=drawer_name,
            drawer_id_number=drawer_id_number,
            payee_name=payee_name,
            customer_id=customer_id,
            supplier_id=supplier_id,
            expense_id=expense_id,
            payment_id=payment_id,
            notes=notes,
            user_id=user_id,
            branch_id=branch_id,
            tenant_id=tenant_id,
            status=status,
        )
        calculate_amount_aed(cheque)
        cheque.update_status_based_on_date()
        db.session.add(cheque)
        return cheque

    # ── read-side scoped lookups extracted from routes/cheques.py ──

    @staticmethod
    def scoped_cheques_query(tenant_id=None, branch_id=None):
        """Active-cheque query filtered by tenant and branch scope."""
        from models import Cheque

        query = Cheque.query.filter_by(is_active=True)
        if tenant_id is not None:
            query = query.filter(Cheque.tenant_id == tenant_id)
        if branch_id is not None:
            query = query.filter(Cheque.branch_id == branch_id)
        return query

    @staticmethod
    def scoped_customers_query(tenant_id=None, branch_id=None):
        """Active-customer query visible from the branch (sales/payments/receipts union)."""
        from sqlalchemy import select

        from models import Customer, Payment, Sale
        from models.receipt import Receipt

        query = Customer.query.filter(Customer.is_active)
        if tenant_id is not None:
            query = query.filter(Customer.tenant_id == tenant_id)
        if branch_id is None:
            return query

        sale_ids = select(Sale.customer_id).where(
            Sale.customer_id.isnot(None),
            Sale.branch_id == branch_id,
        )
        payment_ids = select(Payment.customer_id).where(
            Payment.customer_id.isnot(None),
            Payment.branch_id == branch_id,
        )
        receipt_ids = select(Receipt.customer_id).where(
            Receipt.customer_id.isnot(None),
            Receipt.branch_id == branch_id,
        )
        return query.filter(Customer.id.in_(sale_ids.union(payment_ids, receipt_ids)))

    @staticmethod
    def scoped_suppliers_query(tenant_id=None, branch_id=None):
        """Active-supplier query visible from the branch (purchases/payments union)."""
        from sqlalchemy import select

        from models import Payment, Purchase, Supplier

        query = Supplier.query.filter(Supplier.is_active)
        if tenant_id is not None:
            query = query.filter(Supplier.tenant_id == tenant_id)
        if branch_id is None:
            return query

        purchase_ids = select(Purchase.supplier_id).where(
            Purchase.supplier_id.isnot(None),
            Purchase.branch_id == branch_id,
        )
        payment_ids = select(Payment.supplier_id).where(
            Payment.supplier_id.isnot(None),
            Payment.branch_id == branch_id,
        )
        return query.filter(Supplier.id.in_(purchase_ids.union(payment_ids)))

    @staticmethod
    def has_gl_references(cheque, ref_types):
        """True when any GL journal entry references this cheque."""
        from models import GLJournalEntry

        return (
            GLJournalEntry.query.filter(
                GLJournalEntry.reference_type.in_(ref_types),
                GLJournalEntry.reference_id == cheque.id,
                GLJournalEntry.tenant_id == cheque.tenant_id,
            ).first()
            is not None
        )


def validate_cheque(cheque):
    if not cheque.cheque_number:
        raise ValueError(gettext("رقم الشيك مطلوب"))
    if not cheque.cheque_bank_number:
        raise ValueError(gettext("رقم الشيك البنكي مطلوب"))
    if not cheque.bank_name:
        raise ValueError(gettext("اسم البنك مطلوب"))
    if not cheque.amount or cheque.amount <= 0:
        raise ValueError(gettext("المبلغ يجب أن يكون أكبر من صفر"))
    if not cheque.issue_date:
        raise ValueError(gettext("تاريخ الإصدار مطلوب"))
    if not cheque.due_date:
        raise ValueError(gettext("تاريخ الاستحقاق مطلوب"))
    if cheque.cheque_type not in ("incoming", "outgoing"):
        raise ValueError(gettext("نوع الشيك غير صحيح"))


def calculate_amount_aed(cheque):
    from utils.currency_utils import convert_and_quantize_aed, get_system_default_currency

    base_currency = get_system_default_currency()
    cheque.amount_aed = convert_and_quantize_aed(
        cheque.amount,
        cheque.currency,
        cheque.exchange_rate,
        base_currency=base_currency,
        tenant_id=(cheque.tenant_id if cheque is not None else None),
    )


def _post_gl(cheque, lines, description, reference_type):
    from utils.currency_utils import get_system_default_currency

    base_currency = get_system_default_currency()
    gl_ensure_core_accounts(tenant_id=(cheque.tenant_id if cheque is not None else None))
    return gl_post_or_fail(
        lines=lines,
        description=description,
        reference_type=reference_type,
        reference_id=cheque.id,
        currency=base_currency,
        exchange_rate=1.0,
        branch_id=cheque.branch_id,
        tenant_id=(cheque.tenant_id if cheque is not None else None),
    )


def _existing_posted_entry(cheque, reference_type):
    """حارس عدم التكرار — القيد المرحّل لا يُرحَّل مرة أخرى أبداً."""
    from models import GLJournalEntry
    from utils.gl_reference_types import ref_variants

    q = GLJournalEntry.query.filter(
        GLJournalEntry.reference_type.in_(ref_variants(reference_type)),
        GLJournalEntry.reference_id == cheque.id,
        GLJournalEntry.status == "posted",
    )
    tid = cheque.tenant_id if cheque is not None else None
    if tid is not None:
        q = q.filter(GLJournalEntry.tenant_id == tid)
    return q.order_by(GLJournalEntry.id.desc()).first()


def process_cheque_deposit(cheque, deposit_date=None):
    if cheque.status not in ["pending", "under_collection"]:
        raise ValueError(gettext(f"لا يمكن إيداع شيك بحالة: {cheque.status_ar}"))
    cheque.status = "deposited"
    cheque.deposit_date = deposit_date or datetime.now().date()


def process_cheque_receive(cheque):
    if cheque.cheque_type != "incoming":
        return None
    existing = _existing_posted_entry(cheque, GLRef.CHEQUE_RECEIVE)
    if existing is not None:
        return existing
    credit_account = (
        gl_get_customer_credit_account(
            cheque.customer,
            branch_id=cheque.branch_id,
            tenant_id=(cheque.tenant_id if cheque is not None else None),
        )
        if cheque.customer_id
        else GLService.get_account_code_for_concept(
            "AR",
            branch_id=cheque.branch_id,
            tenant_id=(cheque.tenant_id if cheque is not None else None),
            fallback_key="receivable",
        )
    )
    credit_concept = gl_get_customer_credit_concept(cheque.customer) if cheque.customer_id else "AR"
    lines = [
        {
            "account": GLService.get_account_code_for_concept(
                "CHEQUES_UNDER_COLLECTION",
                branch_id=cheque.branch_id,
                tenant_id=(cheque.tenant_id if cheque is not None else None),
                fallback_key="cheques_under_collection",
            ),
            "concept_code": "CHEQUES_UNDER_COLLECTION",
            "debit": cheque.amount_aed,
            "credit": 0,
            "description": gettext(f"استلام شيك رقم {cheque.cheque_bank_number}"),
        },
        {
            "account": credit_account,
            "concept_code": credit_concept,
            "debit": 0,
            "credit": cheque.amount_aed,
            "description": gettext(f"استلام شيك من عميل - رقم {cheque.cheque_bank_number}"),
        },
    ]
    return _post_gl(
        cheque,
        lines,
        description=gettext(f"استلام شيك وارد رقم {cheque.cheque_bank_number}"),
        reference_type=GLRef.CHEQUE_RECEIVE,
    )


def process_cheque_issue(cheque):
    if cheque.cheque_type != "outgoing":
        return None

    # الشيكات المرتبطة بالمصروفات: قيد المصروف سجّل Cr. Deferred Cheques Payable مباشرة
    if cheque.expense_id:
        return None

    existing = _existing_posted_entry(cheque, GLRef.CHEQUE_ISSUE)
    if existing is not None:
        return existing

    if cheque.supplier_id:
        debit_account = GLService.get_account_code_for_concept(
            "AP",
            branch_id=cheque.branch_id,
            tenant_id=(cheque.tenant_id if cheque is not None else None),
            fallback_key="payable",
        )
        debit_concept = "AP"
    elif cheque.customer_id:
        debit_account = gl_get_customer_credit_account(
            cheque.customer,
            branch_id=cheque.branch_id,
            tenant_id=(cheque.tenant_id if cheque is not None else None),
        )
        debit_concept = gl_get_customer_credit_concept(cheque.customer)
    else:
        debit_account = GLService.get_account_code_for_concept(
            "AP",
            branch_id=cheque.branch_id,
            tenant_id=(cheque.tenant_id if cheque is not None else None),
            fallback_key="payable",
        )
        debit_concept = "AP"
    lines = [
        {
            "account": debit_account,
            "concept_code": debit_concept,
            "debit": cheque.amount_aed,
            "credit": 0,
            "description": gettext(f"إصدار شيك رقم {cheque.cheque_bank_number}"),
        },
        {
            "account": GLService.get_account_code_for_concept(
                "DEFERRED_CHEQUES_PAYABLE",
                branch_id=cheque.branch_id,
                tenant_id=(cheque.tenant_id if cheque is not None else None),
                fallback_key="deferred_cheques",
            ),
            "concept_code": "DEFERRED_CHEQUES_PAYABLE",
            "debit": 0,
            "credit": cheque.amount_aed,
            "description": gettext(f"إصدار شيك - رقم {cheque.cheque_bank_number}"),
        },
    ]
    entry = _post_gl(
        cheque,
        lines,
        description=gettext(f"إصدار شيك صادر رقم {cheque.cheque_bank_number}"),
        reference_type=GLRef.CHEQUE_ISSUE,
    )
    cheque.gl_journal_entry_id = entry.id
    return entry


def _create_clearing_journal_entry(cheque):
    bank_account = gl_get_default_liquidity_account(
        "bank",
        branch_id=cheque.branch_id,
        tenant_id=(cheque.tenant_id if cheque is not None else None),
    )
    lines = []
    if cheque.cheque_type == "incoming":
        lines.append(
            {
                "account": bank_account,
                "explicit_account_allowed": True,
                "debit": cheque.actual_amount_aed,
                "credit": 0,
                "description": gettext(f"صرف شيك وارد رقم {cheque.cheque_bank_number}"),
            }
        )
        lines.append(
            {
                "account": GLService.get_account_code_for_concept(
                    "CHEQUES_UNDER_COLLECTION",
                    branch_id=cheque.branch_id,
                    tenant_id=(cheque.tenant_id if cheque is not None else None),
                    fallback_key="cheques_under_collection",
                ),
                "concept_code": "CHEQUES_UNDER_COLLECTION",
                "debit": 0,
                "credit": cheque.amount_aed,
                "description": gettext(f"صرف شيك رقم {cheque.cheque_bank_number}"),
            }
        )
        if cheque.currency_gain_loss and abs(cheque.currency_gain_loss) > Decimal("0.01"):
            if cheque.currency_gain_loss > 0:
                lines.append(
                    {
                        "account": GLService.get_account_code_for_concept(
                            "FX_GAIN",
                            branch_id=cheque.branch_id,
                            tenant_id=(cheque.tenant_id if cheque is not None else None),
                            fallback_key="fx_gain",
                        ),
                        "concept_code": "FX_GAIN",
                        "debit": 0,
                        "credit": abs(cheque.currency_gain_loss),
                        "description": gettext(f"ربح فرق عملة - شيك {cheque.cheque_bank_number}"),
                    }
                )
            else:
                lines.append(
                    {
                        "account": GLService.get_account_code_for_concept(
                            "FX_LOSS",
                            branch_id=cheque.branch_id,
                            tenant_id=(cheque.tenant_id if cheque is not None else None),
                            fallback_key="fx_loss",
                        ),
                        "concept_code": "FX_LOSS",
                        "debit": abs(cheque.currency_gain_loss),
                        "credit": 0,
                        "description": gettext(f"خسارة فرق عملة - شيك {cheque.cheque_bank_number}"),
                    }
                )
    elif cheque.cheque_type == "outgoing":
        lines.append(
            {
                "account": GLService.get_account_code_for_concept(
                    "DEFERRED_CHEQUES_PAYABLE",
                    branch_id=cheque.branch_id,
                    tenant_id=(cheque.tenant_id if cheque is not None else None),
                    fallback_key="deferred_cheques",
                ),
                "concept_code": "DEFERRED_CHEQUES_PAYABLE",
                "debit": cheque.amount_aed,
                "credit": 0,
                "description": gettext(f"صرف شيك صادر رقم {cheque.cheque_bank_number}"),
            }
        )
        lines.append(
            {
                "account": bank_account,
                "explicit_account_allowed": True,
                "debit": 0,
                "credit": cheque.actual_amount_aed,
                "description": gettext(f"صرف شيك رقم {cheque.cheque_bank_number}"),
            }
        )
        if cheque.currency_gain_loss and abs(cheque.currency_gain_loss) > Decimal("0.01"):
            if cheque.currency_gain_loss > 0:
                lines.append(
                    {
                        "account": GLService.get_account_code_for_concept(
                            "FX_LOSS",
                            branch_id=cheque.branch_id,
                            tenant_id=(cheque.tenant_id if cheque is not None else None),
                            fallback_key="fx_loss",
                        ),
                        "concept_code": "FX_LOSS",
                        "debit": abs(cheque.currency_gain_loss),
                        "credit": 0,
                        "description": gettext(f"خسارة فرق عملة - شيك {cheque.cheque_bank_number}"),
                    }
                )
            else:
                lines.append(
                    {
                        "account": GLService.get_account_code_for_concept(
                            "FX_GAIN",
                            branch_id=cheque.branch_id,
                            tenant_id=(cheque.tenant_id if cheque is not None else None),
                            fallback_key="fx_gain",
                        ),
                        "concept_code": "FX_GAIN",
                        "debit": 0,
                        "credit": abs(cheque.currency_gain_loss),
                        "description": gettext(f"ربح فرق عملة - شيك {cheque.cheque_bank_number}"),
                    }
                )
    if lines:
        _post_gl(
            cheque,
            lines=lines,
            description=gettext(f"صرف شيك {cheque.cheque_type_ar} رقم {cheque.cheque_bank_number}"),
            reference_type=GLRef.CHEQUE_CLEAR,
        )


def process_cheque_clear(cheque, clearance_date=None, clearance_exchange_rate=None):
    if cheque.status not in ["deposited", "pending"]:
        raise ValueError(gettext(f"لا يمكن تأكيد صرف شيك بحالة: {cheque.status_ar}"))
    try:
        cheque.status = "cleared"
        cheque.clearance_date = clearance_date or datetime.now().date()
        if cheque.currency != "AED" and clearance_exchange_rate:
            cheque.clearance_exchange_rate = Decimal(str(clearance_exchange_rate))
        elif cheque.currency != "AED":
            try:
                rate_info = gl_resolve_exchange_rate(
                    cheque.issue_date,
                    cheque.currency,
                    "AED",
                    (cheque.tenant_id if cheque is not None else None),
                )
                cheque.clearance_exchange_rate = Decimal(str(rate_info["rate"]))
            except Exception:
                logger.warning("Clearance rate resolution failed; using issue rate", exc_info=True)
                cheque.clearance_exchange_rate = Decimal(str(cheque.exchange_rate))
        else:
            cheque.clearance_exchange_rate = Decimal("1.0")
        from utils.currency_utils import convert_and_quantize_aed as _cq

        cheque.actual_amount_aed = _cq(
            cheque.amount,
            cheque.currency,
            cheque.clearance_exchange_rate,
            tenant_id=(cheque.tenant_id if cheque is not None else None),
        )
        cheque.currency_gain_loss = cheque.actual_amount_aed - cheque.amount_aed
        _create_clearing_journal_entry(cheque)
        from models.payment import Payment
        from models.receipt import Receipt

        tid = cheque.tenant_id if cheque is not None else None

        # تأكيد الدفعات/السندات المرتبطة
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
    except Exception:
        logger.exception(f"Fatal error processing clear for cheque {cheque.id}")
        raise


def _create_bounce_journal_entry(cheque):
    lines = []
    if cheque.cheque_type == "incoming":
        ar_account = (
            gl_get_customer_credit_account(
                cheque.customer,
                branch_id=cheque.branch_id,
                tenant_id=(cheque.tenant_id if cheque is not None else None),
            )
            if cheque.customer_id
            else GLService.get_account_code_for_concept(
                "AR",
                branch_id=cheque.branch_id,
                tenant_id=(cheque.tenant_id if cheque is not None else None),
                fallback_key="receivable",
            )
        )
        ar_concept = gl_get_customer_credit_concept(cheque.customer) if cheque.customer_id else "AR"
        lines.append(
            {
                "account": ar_account,
                "concept_code": ar_concept,
                "debit": cheque.amount_aed,
                "credit": 0,
                "description": gettext(f"ارتداد شيك رقم {cheque.cheque_bank_number} - إرجاع الدين"),
            }
        )
        lines.append(
            {
                "account": GLService.get_account_code_for_concept(
                    "CHEQUES_UNDER_COLLECTION",
                    branch_id=cheque.branch_id,
                    tenant_id=(cheque.tenant_id if cheque is not None else None),
                    fallback_key="cheques_under_collection",
                ),
                "concept_code": "CHEQUES_UNDER_COLLECTION",
                "debit": 0,
                "credit": cheque.amount_aed,
                "description": gettext(f"ارتداد شيك رقم {cheque.cheque_bank_number}"),
            }
        )
    elif cheque.cheque_type == "outgoing":
        lines.append(
            {
                "account": GLService.get_account_code_for_concept(
                    "DEFERRED_CHEQUES_PAYABLE",
                    branch_id=cheque.branch_id,
                    tenant_id=(cheque.tenant_id if cheque is not None else None),
                    fallback_key="deferred_cheques",
                ),
                "concept_code": "DEFERRED_CHEQUES_PAYABLE",
                "debit": cheque.amount_aed,
                "credit": 0,
                "description": gettext(f"ارتداد شيك صادر رقم {cheque.cheque_bank_number}"),
            }
        )
        if cheque.expense_id:
            from models.expense import Expense

            expense = db.session.get(Expense, cheque.expense_id)
            credit_account = (
                expense.category.gl_account_code
                if expense and expense.category and expense.category.gl_account_code
                else GLService.get_account_code_for_concept(
                    "MISC_EXPENSE",
                    branch_id=cheque.branch_id,
                    tenant_id=(cheque.tenant_id if cheque is not None else None),
                    fallback_key="misc_expense",
                )
            )
            credit_concept = "MISC_EXPENSE"
        elif cheque.supplier_id:
            credit_account = GLService.get_account_code_for_concept(
                "AP",
                branch_id=cheque.branch_id,
                tenant_id=(cheque.tenant_id if cheque is not None else None),
                fallback_key="payable",
            )
            credit_concept = "AP"
        elif cheque.customer_id:
            credit_account = gl_get_customer_credit_account(
                cheque.customer,
                branch_id=cheque.branch_id,
                tenant_id=(cheque.tenant_id if cheque is not None else None),
            )
            credit_concept = gl_get_customer_credit_concept(cheque.customer)
        else:
            credit_account = GLService.get_account_code_for_concept(
                "AP",
                branch_id=cheque.branch_id,
                tenant_id=(cheque.tenant_id if cheque is not None else None),
                fallback_key="payable",
            )
            credit_concept = "AP"
        lines.append(
            {
                "account": credit_account,
                "concept_code": credit_concept,
                "debit": 0,
                "credit": cheque.amount_aed,
                "description": gettext(f"ارتداد شيك رقم {cheque.cheque_bank_number} - إرجاع الالتزام"),
            }
        )
    if lines:
        _post_gl(
            cheque,
            lines=lines,
            description=gettext(f"ارتداد شيك {cheque.cheque_type_ar} رقم {cheque.cheque_bank_number}"),
            reference_type=GLRef.CHEQUE_BOUNCE,
        )


def process_cheque_bounce(cheque, reason, bounce_fee=None):
    # Enforce proper lifecycle: bounce should only happen after deposit
    # (incoming) or from pending/outgoing. Prevent direct pending→bounce for incoming.
    if cheque.cheque_type == "incoming" and cheque.status == "pending":
        raise ValueError(
            gettext(
                "لا يمكن رفض شيك وارد بحالة معلق — يجب إيداعه أولاً. "
                "Use process_cheque_deposit() before bouncing an incoming cheque."
            )
        )
    if cheque.status not in ["deposited", "pending"]:
        raise ValueError(gettext(f"لا يمكن رفض شيك بحالة: {cheque.status_ar}"))
    try:
        cheque.status = "bounced"
        cheque.bounce_reason = reason
        cheque.clearance_date = datetime.now().date()
        _create_bounce_journal_entry(cheque)
        if bounce_fee is not None and bounce_fee > 0:
            try:
                from models import GLJournalEntry
                from services.gl_posting import post_or_fail

                fee_desc = gettext(f"رسوم ارتداد شيك {cheque.cheque_type_ar} رقم {cheque.cheque_bank_number}")
                existing_fee_q = GLJournalEntry.query.filter(
                    GLJournalEntry.reference_type == GLRef.CHEQUE_BOUNCE,
                    GLJournalEntry.reference_id == cheque.id,
                    GLJournalEntry.status == "posted",
                    GLJournalEntry.description == fee_desc,
                )
                if cheque.tenant_id is not None:
                    existing_fee_q = existing_fee_q.filter(GLJournalEntry.tenant_id == cheque.tenant_id)
                if existing_fee_q.first() is None:
                    expense_account = GLService.get_account_code_for_concept(
                        "MISC_EXPENSE",
                        branch_id=cheque.branch_id,
                        tenant_id=(cheque.tenant_id if cheque is not None else None),
                        fallback_key="misc_expense",
                    )
                    bank_account = gl_get_default_liquidity_account(
                        "bank",
                        branch_id=cheque.branch_id,
                        tenant_id=(cheque.tenant_id if cheque is not None else None),
                    )
                    fee_lines = [
                        {
                            "account": expense_account,
                            "concept_code": "MISC_EXPENSE",
                            "debit": Decimal(str(bounce_fee)),
                            "credit": 0,
                            "description": gettext(f"رسوم ارتداد شيك رقم {cheque.cheque_bank_number}"),
                        },
                        {
                            "account": bank_account,
                            "concept_code": "BANK",
                            "debit": 0,
                            "credit": Decimal(str(bounce_fee)),
                            "description": gettext(f"خصم رسوم ارتداد شيك رقم {cheque.cheque_bank_number}"),
                        },
                    ]
                    post_or_fail(
                        fee_lines,
                        description=fee_desc,
                        reference_type=GLRef.CHEQUE_BOUNCE,
                        reference_id=cheque.id,
                        branch_id=cheque.branch_id,
                        tenant_id=(cheque.tenant_id if cheque is not None else None),
                    )
            except Exception as fee_err:
                logger.error(f"Failed to post bounce fee for cheque {cheque.id}: {fee_err}")
        if cheque.cheque_type == "incoming" and cheque.customer_id:
            try:
                cheque.customer.adjust_balance(-(cheque.amount_aed or Decimal("0")))
            except Exception as cust_err:
                logger.error(f"Failed to adjust customer balance on bounce cheque {cheque.id}: {cust_err}")
        from models.payment import Payment
        from models.receipt import Receipt

        tid = cheque.tenant_id if cheque is not None else None
        pmt_q = Payment.query.filter_by(cheque_id=cheque.id)
        if tid:
            pmt_q = pmt_q.filter(Payment.tenant_id == tid)
        payment = pmt_q.first()
        if payment:
            payment.reject_payment(reason)
        if cheque.cheque_type == "outgoing" and cheque.supplier_id and not cheque.expense_id:
            from models.supplier import Supplier

            supplier_q = Supplier.query.filter_by(id=cheque.supplier_id)
            if tid:
                supplier_q = supplier_q.filter(Supplier.tenant_id == tid)
            supplier = supplier_q.first()
            if supplier:
                supplier.apply_payment(-Decimal(str(cheque.amount_aed or 0)))
        rcpt_q = Receipt.query.filter_by(cheque_id=cheque.id)
        if tid:
            rcpt_q = rcpt_q.filter(Receipt.tenant_id == tid)
        receipt = rcpt_q.first()
        if receipt:
            receipt.reject_receipt(reason)
    except Exception:
        logger.exception(f"Fatal error processing bounce for cheque {cheque.id}")
        raise


def _create_cancel_journal_entry(cheque):
    lines = []
    if cheque.cheque_type == "incoming":
        ar_account = (
            gl_get_customer_credit_account(
                cheque.customer,
                branch_id=cheque.branch_id,
                tenant_id=(cheque.tenant_id if cheque is not None else None),
            )
            if cheque.customer_id
            else GLService.get_account_code_for_concept(
                "AR",
                branch_id=cheque.branch_id,
                tenant_id=(cheque.tenant_id if cheque is not None else None),
                fallback_key="receivable",
            )
        )
        ar_concept = gl_get_customer_credit_concept(cheque.customer) if cheque.customer_id else "AR"
        lines = [
            {
                "account": ar_account,
                "concept_code": ar_concept,
                "debit": cheque.amount_aed,
                "credit": 0,
                "description": gettext(f"إلغاء شيك وارد رقم {cheque.cheque_bank_number}"),
            },
            {
                "account": GLService.get_account_code_for_concept(
                    "CHEQUES_UNDER_COLLECTION",
                    branch_id=cheque.branch_id,
                    tenant_id=(cheque.tenant_id if cheque is not None else None),
                    fallback_key="cheques_under_collection",
                ),
                "concept_code": "CHEQUES_UNDER_COLLECTION",
                "debit": 0,
                "credit": cheque.amount_aed,
                "description": gettext(f"إلغاء شيك رقم {cheque.cheque_bank_number}"),
            },
        ]
    elif cheque.cheque_type == "outgoing":
        if cheque.expense_id:
            from models.expense import Expense

            expense = db.session.get(Expense, cheque.expense_id)
            if expense and expense.category and expense.category.gl_account_code:
                credit_account = expense.category.gl_account_code
                credit_concept = None
            else:
                credit_account = GLService.get_account_code_for_concept(
                    "MISC_EXPENSE",
                    branch_id=cheque.branch_id,
                    tenant_id=(cheque.tenant_id if cheque is not None else None),
                    fallback_key="misc_expense",
                )
                credit_concept = "MISC_EXPENSE"
        elif cheque.supplier_id:
            credit_account = GLService.get_account_code_for_concept(
                "AP",
                branch_id=cheque.branch_id,
                tenant_id=(cheque.tenant_id if cheque is not None else None),
                fallback_key="payable",
            )
            credit_concept = "AP"
        elif cheque.customer_id:
            credit_account = gl_get_customer_credit_account(
                cheque.customer,
                branch_id=cheque.branch_id,
                tenant_id=(cheque.tenant_id if cheque is not None else None),
            )
            credit_concept = gl_get_customer_credit_concept(cheque.customer)
        else:
            credit_account = GLService.get_account_code_for_concept(
                "AP",
                branch_id=cheque.branch_id,
                tenant_id=(cheque.tenant_id if cheque is not None else None),
                fallback_key="payable",
            )
            credit_concept = "AP"
        lines = [
            {
                "account": GLService.get_account_code_for_concept(
                    "DEFERRED_CHEQUES_PAYABLE",
                    branch_id=cheque.branch_id,
                    tenant_id=(cheque.tenant_id if cheque is not None else None),
                    fallback_key="deferred_cheques",
                ),
                "concept_code": "DEFERRED_CHEQUES_PAYABLE",
                "debit": cheque.amount_aed,
                "credit": 0,
                "description": gettext(f"إلغاء شيك صادر رقم {cheque.cheque_bank_number}"),
            },
            {
                "account": credit_account,
                "concept_code": credit_concept,
                "debit": 0,
                "credit": cheque.amount_aed,
                "description": gettext(f"إلغاء شيك رقم {cheque.cheque_bank_number}"),
            },
        ]
    if lines:
        _post_gl(
            cheque,
            lines=lines,
            description=gettext(f"إلغاء شيك {cheque.cheque_type_ar} رقم {cheque.cheque_bank_number}"),
            reference_type=GLRef.CHEQUE_CANCEL,
        )


def process_cheque_cancel(cheque, reason=None, *, create_gl=True):
    from models import Payment
    from models.receipt import Receipt

    if cheque.status == "cancelled":
        return
    if cheque.status == "cleared":
        raise ValueError(gettext("لا يمكن إلغاء شيك تم صرفه"))
    # A bounced cheque is already fully reversed by the bounce entry —
    # cancelling it must not post the same reversal a second time.
    skip_gl = cheque.status == "bounced"
    cheque.status = "cancelled"
    if reason:
        cheque.notes = (cheque.notes or "") + f"\nسبب الإلغاء: {reason}"
    if create_gl and not skip_gl:
        _create_cancel_journal_entry(cheque)

    tid = cheque.tenant_id if cheque is not None else None
    pmt_q = Payment.query.filter_by(cheque_id=cheque.id)
    if tid:
        pmt_q = pmt_q.filter(Payment.tenant_id == tid)
    for payment in pmt_q.all():
        payment.reject_payment(reason or gettext("تم إلغاء الشيك"))
    rcpt_q = Receipt.query.filter_by(cheque_id=cheque.id)
    if tid:
        rcpt_q = rcpt_q.filter(Receipt.tenant_id == tid)
    for receipt in rcpt_q.all():
        receipt.reject_receipt(reason or gettext("تم إلغاء الشيك"))

    # Cancelling an outgoing supplier cheque restores AP in the GL, so restore
    # the cached supplier paid total to keep the balance consistent.
    if create_gl and cheque.cheque_type == "outgoing" and cheque.supplier_id and not cheque.expense_id:
        from models.supplier import Supplier

        tid = cheque.tenant_id if cheque is not None else None
        supplier_q = Supplier.query.filter_by(id=cheque.supplier_id)
        if tid:
            supplier_q = supplier_q.filter(Supplier.tenant_id == tid)
        supplier = supplier_q.first()
        if supplier:
            supplier.apply_payment(-Decimal(str(cheque.amount_aed or 0)))


def register_cheque_event_listeners():
    from datetime import date

    from sqlalchemy import event

    from models import Cheque

    @event.listens_for(Cheque, "before_insert")
    @event.listens_for(Cheque, "before_update")
    def _auto_update_status(mapper, connection, target):
        try:
            if target.status == "pending" and target.due_date:
                due = target.due_date.date() if isinstance(target.due_date, datetime) else target.due_date
                today = date.today()
                days_overdue = (today - due).days
                if days_overdue > 7:
                    logger.warning(f"Cheque {target.cheque_number} overdue by {days_overdue} days")
        except Exception as e:
            logger.error(f"Failed to check cheque status: {e}")

    @event.listens_for(Cheque, "after_update")
    def _auto_log_status_change(mapper, connection, target):
        try:
            if target.status in ["cleared", "bounced"]:
                status_ar = gettext("تم الصرف") if target.status == "cleared" else gettext("مرتد")
                logger.info(f"Cheque {target.cheque_number} status changed to: {status_ar}")
        except Exception as e:
            logger.error(f"Failed to log cheque status change: {e}")
