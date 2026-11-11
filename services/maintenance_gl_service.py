"""خدمة محاسبة الصيانة - Maintenance GL Service

ترحيل قيود الصيانة إلى دفتر الأستاذ العام.

وحدة الصيانة محاسبياً مستقلة عن المبيعات:

* ``MAINTENANCE_AR`` (1134)      ذمم صيانة مدينة — مستقلة عن ذمم التجارة (1130)
* ``MAINTENANCE_REVENUE`` (4119) إيراد الصيانة — مستقل عن إيراد المبيعات (4100)
* ``MAINTENANCE_COGS`` (5119)    تكلفة قطع الصيانة — مستقلة عن تكلفة المبيعات (5100)
* ``MAINTENANCE_DEPOSIT`` (2171) عربون الصيانة
* ``MAINTENANCE_CASH_DIFFERENCE`` (6560) فروقات صندوق الاستقبال

ال”的原则: كل قيد متوازن، ومرحَل عبر ``post_or_fail`` الذي يرفض القيد غير
المتوازن أو المقيد على حساب رئيسي أو على فترة محاسبية مقفلة.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from flask_babel import gettext

from extensions import db
from models import GLJournalEntry
from services.gl_posting import GlPostingError, post_or_fail
from services.gl_service import GLService
from utils.currency_utils import convert_and_quantize_aed
from utils.gl_reference_types import GLRef
from utils.logger import log_financial

logger = logging.getLogger(__name__)

_BASE_QUANTUM = Decimal("0.001")

#: How a maintenance receipt lands. Every method names the account it must
#: debit; the concept is what the ledger records the movement as.
_LIQUIDITY_BY_MODE = {
    "cash": "cash",
    "card": "bank",
    "bank": "bank",
    "bank_transfer": "bank",
    "e_wallet": "bank",
    "cheque": None,  # handled separately - a cheque is a receivable, not cash
}


class MaintenanceGLService:
    """خدمة ترحيل قيود الصيانة إلى دفتر الأستاذ العام."""

    # ── helpers ──────────────────────────────────────────────────────────
    @staticmethod
    def _base_amount(amount, currency, exchange_rate, base_currency) -> Decimal:
        return convert_and_quantize_aed(amount or 0, currency, exchange_rate, base_currency=base_currency)

    @staticmethod
    def _require_account(concept: str, tenant_id: int, branch_id: int | None) -> str:
        """Resolve a maintenance concept to the tenant's own account code.

        A concept nobody mapped is refused by the resolver itself, which is
        the point of the rail: the tenant's mapping governs, so the posting
        names the concept and the account comes from the tenant's chart.
        """
        code = GLService.get_account_code_for_concept(concept, branch_id=branch_id, tenant_id=tenant_id)
        if not code:
            raise GlPostingError(gettext("لم يتم ضبط حساب الصيانة {concept} لهذا المستأجر").format(concept=concept))
        return code

    @staticmethod
    def _liquidity_account(payment_mode: str, tenant_id: int, branch_id: int | None) -> tuple[str, str, int | None]:
        """The account the money lands in, its concept, and its branch.

        Liquidity concepts are not mapping-owned: they resolve from the
        tenant's own cash/bank account, and the posting validator requires
        the entry's branch to match that account's branch. So the branch is
        resolved together with the account and returned to the caller, which
        stamps it on the document and the entry so all three agree.
        """
        mode = (payment_mode or "cash").strip().lower()
        if mode == "cheque":
            raise GlPostingError(gettext("قبض الشيك يُعالَج ضمن مسار الشيكات"))

        kind = _LIQUIDITY_BY_MODE.get(mode)
        if kind is None:
            raise GlPostingError(gettext("طريقة الدفع غير مدعومة: {mode}").format(mode=payment_mode))

        resolved_branch = GLService.resolve_liquidity_branch(kind, branch_id, tenant_id)
        account = GLService.get_default_liquidity_account(kind, branch_id=resolved_branch, tenant_id=tenant_id)
        concept = "CASH" if kind == "cash" else "BANK"
        return account, concept, resolved_branch

    # ── invoice ──────────────────────────────────────────────────────────
    @staticmethod
    def post_invoice(invoice, user_id: int) -> GLJournalEntry:
        """ترحيل فاتورة الصيانة إلى GL:

        Dr: MAINTENANCE_AR (ذمم صيانة مدينة) — الإجمالي شامل الضريبة
        Cr: MAINTENANCE_REVENUE (إيراد الصيانة) — الصافي قبل الضريبة
        Cr: VAT_OUTPUT (ضريبة المخرجات)
        """
        if invoice is None:
            raise ValueError(gettext("لا يمكن ترحيل فاتورة صيانة بدون مستند"))
        tid = invoice.tenant_id
        order = invoice.order
        branch_id = order.branch_id if order is not None else None

        ar_account = MaintenanceGLService._require_account("MAINTENANCE_AR", tid, branch_id)
        revenue_account = MaintenanceGLService._require_account("MAINTENANCE_REVENUE", tid, branch_id)

        total = Decimal(str(invoice.total_amount or 0))
        tax = Decimal(str(invoice.tax_amount or 0))
        if total <= 0:
            raise GlPostingError(gettext("لا يمكن ترحيل فاتورة صيانة بقيمة صفرية"))

        # The revenue leg is the amount the customer owes net of tax: with
        # tax-inclusive prices the tax is inside the total, with exclusive
        # prices it is on top. Either way total == net + tax.
        net = total - tax
        if net < 0:
            raise GlPostingError(gettext("قيمة فاتورة الصيانة غير صالحة"))

        lines = [
            {
                "account": ar_account,
                "concept_code": "MAINTENANCE_AR",
                "debit": total,
                "description": gettext("ذمم صيانة - فاتورة {number}").format(number=invoice.invoice_number),
            },
            {
                "account": revenue_account,
                "concept_code": "MAINTENANCE_REVENUE",
                "credit": net,
                "description": gettext("إيراد صيانة - فاتورة {number}").format(number=invoice.invoice_number),
            },
        ]

        if tax > 0:
            vat_account = MaintenanceGLService._require_account("VAT_OUTPUT", tid, branch_id)
            lines.append(
                {
                    "account": vat_account,
                    "concept_code": "VAT_OUTPUT",
                    "credit": tax,
                    "description": gettext("ضريبة مخرجات - فاتورة صيانة {number}").format(
                        number=invoice.invoice_number
                    ),
                }
            )

        entry = post_or_fail(
            lines=lines,
            description=gettext("إيراد صيانة - فاتورة {number}").format(number=invoice.invoice_number),
            reference_type=GLRef.MAINTENANCE,
            reference_id=invoice.order_id,
            date=invoice.invoice_date,
            currency=invoice.currency,
            exchange_rate=invoice.exchange_rate,
            branch_id=branch_id,
            user_id=user_id,
            tenant_id=tid,
        )

        invoice.gl_posted = True
        invoice.gl_posted_at = datetime.now(UTC)
        invoice.gl_entry_id = entry.id
        invoice.posted = True
        invoice.posted_at = datetime.now(UTC)
        db.session.flush()

        log_financial(
            message=f"Maintenance invoice posted to GL: {invoice.invoice_number}",
            tenant_id=tid,
            level="INFO",
            source="services.maintenance_gl_service.MaintenanceGLService.post_invoice",
            extra={
                "invoice_id": invoice.id,
                "tenant_id": tid,
                "gl_entry_id": entry.id,
                "total": float(total),
            },
        )

        return entry

    # ── receipt ──────────────────────────────────────────────────────────
    @staticmethod
    def post_receipt(receipt, user_id: int) -> GLJournalEntry:
        """ترحيل سند قبض الصيانة إلى GL:

        Dr: CASH / BANK (صندوق أو حساب الاستقبال)
        Cr: MAINTENANCE_AR (ذمم صيانة مدينة)
        """
        if receipt is None:
            raise ValueError(gettext("لا يمكن ترحيل سند قبض صيانة بدون مستند"))
        tid = receipt.tenant_id
        order = receipt.order
        amount = Decimal(str(receipt.amount or 0))
        if amount <= 0:
            raise GlPostingError(gettext("لا يمكن ترحيل سند قبض صيانة بقيمة صفرية"))

        cash_account, cash_concept, resolved_branch = MaintenanceGLService._liquidity_account(
            receipt.payment_mode, tid, order.branch_id if order is not None else None
        )
        ar_account = MaintenanceGLService._require_account("MAINTENANCE_AR", tid, resolved_branch)

        currency = order.currency if order is not None else receipt.order.currency
        exchange_rate = order.exchange_rate if order is not None else Decimal("1")

        lines = [
            {
                "account": cash_account,
                "concept_code": cash_concept,
                "debit": amount,
                "description": gettext("قبض صيانة - سند {number}").format(number=receipt.receipt_number),
            },
            {
                "account": ar_account,
                "concept_code": "MAINTENANCE_AR",
                "credit": amount,
                "description": gettext("تسوية ذمم صيانة - سند {number}").format(number=receipt.receipt_number),
            },
        ]

        entry = post_or_fail(
            lines=lines,
            description=gettext("قبض صيانة - سند {number}").format(number=receipt.receipt_number),
            reference_type=GLRef.MAINTENANCE_RECEIPT,
            reference_id=receipt.id,
            date=receipt.receipt_date,
            currency=currency,
            exchange_rate=exchange_rate,
            branch_id=resolved_branch,
            user_id=user_id,
            tenant_id=tid,
        )

        receipt.gl_posted = True
        receipt.gl_posted_at = datetime.now(UTC)
        receipt.gl_entry_id = entry.id
        db.session.flush()

        log_financial(
            message=f"Maintenance receipt posted to GL: {receipt.receipt_number}",
            tenant_id=tid,
            level="INFO",
            source="services.maintenance_gl_service.MaintenanceGLService.post_receipt",
            extra={
                "receipt_id": receipt.id,
                "tenant_id": tid,
                "gl_entry_id": entry.id,
                "amount": float(amount),
            },
        )

        return entry

    # ── deposit ──────────────────────────────────────────────────────────
    @staticmethod
    def post_deposit(receipt, user_id: int) -> GLJournalEntry:
        """ترحيل عربون الصيانة:

        Dr: CASH / BANK
        Cr: MAINTENANCE_DEPOSIT (عربون صيانة)
        """
        if receipt is None:
            raise ValueError(gettext("لا يمكن ترحيل عربون صيانة بدون سند"))
        tid = receipt.tenant_id
        order = receipt.order
        amount = Decimal(str(receipt.amount or 0))
        if amount <= 0:
            raise GlPostingError(gettext("لا يمكن ترحيل عربون صيانة بقيمة صفرية"))

        cash_account, cash_concept, resolved_branch = MaintenanceGLService._liquidity_account(
            receipt.payment_mode, tid, order.branch_id if order is not None else None
        )
        deposit_account = MaintenanceGLService._require_account("MAINTENANCE_DEPOSIT", tid, resolved_branch)

        currency = order.currency if order is not None else receipt.order.currency
        exchange_rate = order.exchange_rate if order is not None else Decimal("1")

        entry = post_or_fail(
            lines=[
                {
                    "account": cash_account,
                    "concept_code": cash_concept,
                    "debit": amount,
                    "description": gettext("عربون صيانة - سند {number}").format(number=receipt.receipt_number),
                },
                {
                    "account": deposit_account,
                    "concept_code": "MAINTENANCE_DEPOSIT",
                    "credit": amount,
                    "description": gettext("عربون صيانة - سند {number}").format(number=receipt.receipt_number),
                },
            ],
            description=gettext("عربون صيانة - سند {number}").format(number=receipt.receipt_number),
            reference_type=GLRef.MAINTENANCE_RECEIPT,
            reference_id=receipt.id,
            date=receipt.receipt_date,
            currency=currency,
            exchange_rate=exchange_rate,
            branch_id=resolved_branch,
            user_id=user_id,
            tenant_id=tid,
        )

        receipt.gl_posted = True
        receipt.gl_posted_at = datetime.now(UTC)
        receipt.gl_entry_id = entry.id
        db.session.flush()

        log_financial(
            message=f"Maintenance deposit posted to GL: {receipt.receipt_number}",
            tenant_id=tid,
            level="INFO",
            source="services.maintenance_gl_service.MaintenanceGLService.post_deposit",
            extra={
                "receipt_id": receipt.id,
                "tenant_id": tid,
                "gl_entry_id": entry.id,
                "amount": float(amount),
            },
        )

        return entry

    # ── purchase receipt ──────────────────────────────────────────────────
    @staticmethod
    def post_purchase_receipt(order, user_id: int) -> GLJournalEntry:
        """ترحيل توريد قطع الصيانة إلى GL:

        Dr: INVENTORY_ASSET (المخزون) — المبلغ الصافي فقط
        Dr: VAT_INPUT (ضريبة المدخلات) — الضريبة القابلة للخصم
        Cr: MAINTENANCE_AP (ذمم الموردين)

        The tax is not capitalised into the stock: it is recoverable, so
        it belongs to the input-tax account. Capitalising it would inflate
        the moving average of every part the workshop buys and would
        overstate the cost of the jobs that consume them.
        """
        if order is None:
            raise ValueError(gettext("لا يمكن ترحيل توريد قطع بدون أمر شراء"))

        tid = order.tenant_id
        branch_id = order.branch_id

        net = Decimal(str(order.taxable_amount or 0)).quantize(_BASE_QUANTUM, rounding=ROUND_HALF_UP)
        tax = Decimal(str(order.tax_amount or 0)).quantize(_BASE_QUANTUM, rounding=ROUND_HALF_UP)
        total = Decimal(str(order.total_amount or 0)).quantize(_BASE_QUANTUM, rounding=ROUND_HALF_UP)
        if total <= 0:
            raise GlPostingError(gettext("لا يمكن ترحيل توريد بقيمة صفرية"))
        if abs((net + tax) - total) > Decimal("0.001"):
            raise GlPostingError(gettext("إجماليات توريد قطع الصيانة غير متسقة"))

        inventory_account = MaintenanceGLService._require_account("INVENTORY_ASSET", tid, branch_id)
        ap_account = MaintenanceGLService._require_account("MAINTENANCE_AP", tid, branch_id)

        lines = [
            {
                "account": inventory_account,
                "concept_code": "INVENTORY_ASSET",
                "debit": net,
                "description": gettext("توريد قطع صيانة - أمر شراء {number}").format(number=order.po_number),
            },
            {
                "account": ap_account,
                "concept_code": "MAINTENANCE_AP",
                "credit": total,
                "description": gettext("ذمم موردي قطع الصيانة - {supplier}").format(
                    supplier=order.supplier_name or gettext("مورد")
                ),
            },
        ]

        if tax > 0:
            vat_account = MaintenanceGLService._require_account("VAT_INPUT", tid, branch_id)
            lines.append(
                {
                    "account": vat_account,
                    "concept_code": "VAT_INPUT",
                    "debit": tax,
                    "description": gettext("ضريبة مدخلات - توريد قطع صيانة {number}").format(number=order.po_number),
                }
            )

        entry = post_or_fail(
            lines=lines,
            description=gettext("توريد قطع صيانة - أمر شراء {number}").format(number=order.po_number),
            reference_type=GLRef.MAINTENANCE,
            reference_id=order.id,
            date=order.order_date,
            currency=order.currency,
            exchange_rate=order.exchange_rate,
            branch_id=branch_id,
            user_id=user_id,
            tenant_id=tid,
        )

        log_financial(
            message=f"Maintenance purchase receipt posted: {order.po_number} total {total}",
            tenant_id=tid,
            level="INFO",
            source="services.maintenance_gl_service.MaintenanceGLService.post_purchase_receipt",
            extra={
                "purchase_order_id": order.id,
                "tenant_id": tid,
                "gl_entry_id": entry.id,
                "total": float(total),
            },
        )

        return entry

    # ── deposit reclassification ─────────────────────────────────────────
    @staticmethod
    def post_deposit_application(order, user_id: int) -> GLJournalEntry | None:
        """ترحيل عربون الصيانة على فاتورتها.

        The deposit was taken before there was an invoice, so it was
        credited to the deposit liability (MAINTENANCE_DEPOSIT). Now that
        the invoice exists, the deposit is applied against it:

        Dr: MAINTENANCE_DEPOSIT (694/2171 — يسقط الالتزام)
        Cr: MAINTENANCE_AR (1134 — يقلّ رصيد الذمم)

        Without this leg the maintenance receivable would still carry the
        full invoice while the deposit sat on the liability side, and the
        sub-ledger would not reconcile with the order's balance due.
        """
        if order is None:
            raise ValueError(gettext("لا يمكن ترحيل عربون صيانة بدون أمر"))
        tid = order.tenant_id
        deposit = Decimal(str(order.deposit_amount or 0)).quantize(_BASE_QUANTUM, rounding=ROUND_HALF_UP)
        if deposit <= 0:
            return None

        branch_id = order.branch_id
        deposit_account = MaintenanceGLService._require_account("MAINTENANCE_DEPOSIT", tid, branch_id)
        ar_account = MaintenanceGLService._require_account("MAINTENANCE_AR", tid, branch_id)

        entry = post_or_fail(
            lines=[
                {
                    "account": deposit_account,
                    "concept_code": "MAINTENANCE_DEPOSIT",
                    "debit": deposit,
                    "description": gettext("تسوية عربون صيانة على فاتورة {number}").format(number=order.order_number),
                },
                {
                    "account": ar_account,
                    "concept_code": "MAINTENANCE_AR",
                    "credit": deposit,
                    "description": gettext("تسوية عربون صيانة على فاتورة {number}").format(number=order.order_number),
                },
            ],
            description=gettext("تسوية عربون صيانة - أمر {number}").format(number=order.order_number),
            reference_type=GLRef.MAINTENANCE,
            reference_id=order.id,
            date=order.order_date,
            currency=order.currency,
            exchange_rate=order.exchange_rate,
            branch_id=branch_id,
            user_id=user_id,
            tenant_id=tid,
        )

        log_financial(
            message=f"Maintenance deposit applied: order {order.order_number} amount {deposit}",
            tenant_id=tid,
            level="INFO",
            source="services.maintenance_gl_service.MaintenanceGLService.post_deposit_application",
            extra={
                "order_id": order.id,
                "tenant_id": tid,
                "gl_entry_id": entry.id,
                "amount": float(deposit),
            },
        )

        return entry

    # ── parts cost ───────────────────────────────────────────────────────
    @staticmethod
    def post_parts_cost(order, total_cost: Decimal, user_id: int) -> GLJournalEntry | None:
        """ترحيل تكلفة قطع الغيار المستهلكة في أمر الصيانة:

        Dr: MAINTENANCE_COGS (تكلفة قطع الصيانة)
        Cr: INVENTORY_ASSET (المخزون)

        A maintenance job consumes parts from the shelf: the stock leaves the
        warehouse and becomes the cost of the job. The parts leg is posted
        with the same money the receipt path uses, so the inventory account
        and the physical stock move together.
        """
        if order is None:
            raise ValueError(gettext("لا يمكن ترحيل تكلفة قطع الصيانة بدون أمر"))
        tid = order.tenant_id
        cost = Decimal(str(total_cost or 0)).quantize(_BASE_QUANTUM, rounding=ROUND_HALF_UP)
        if cost <= 0:
            return None

        branch_id = order.branch_id
        cogs_account = MaintenanceGLService._require_account("MAINTENANCE_COGS", tid, branch_id)
        inventory_account = MaintenanceGLService._require_account("INVENTORY_ASSET", tid, branch_id)

        entry = post_or_fail(
            lines=[
                {
                    "account": cogs_account,
                    "concept_code": "MAINTENANCE_COGS",
                    "debit": cost,
                    "description": gettext("تكلفة قطع الصيانة - أمر {number}").format(number=order.order_number),
                },
                {
                    "account": inventory_account,
                    "concept_code": "INVENTORY_ASSET",
                    "credit": cost,
                    "description": gettext("خصم قطع من مخزون الصيانة - أمر {number}").format(number=order.order_number),
                },
            ],
            description=gettext("تكلفة قطع الصيانة - أمر {number}").format(number=order.order_number),
            reference_type=GLRef.MAINTENANCE_COGS,
            reference_id=order.id,
            date=order.order_date,
            currency=order.currency,
            exchange_rate=order.exchange_rate,
            branch_id=branch_id,
            user_id=user_id,
            tenant_id=tid,
        )

        log_financial(
            message=f"Maintenance parts cost posted: order {order.order_number} cost {cost}",
            tenant_id=tid,
            level="INFO",
            source="services.maintenance_gl_service.MaintenanceGLService.post_parts_cost",
            extra={
                "order_id": order.id,
                "tenant_id": tid,
                "gl_entry_id": entry.id,
                "cost": float(cost),
            },
        )

        return entry

    # ── return ───────────────────────────────────────────────────────────
    @staticmethod
    def post_return(maintenance_return, user_id: int) -> GLJournalEntry:
        """ترحيل مرتجع الصيانة:

        Dr: MAINTENANCE_REVENUE (عكس الإيراد) + VAT_OUTPUT (عكس الضريبة)
        Cr: MAINTENANCE_AR (عكس الذمم)

        The returned parts go back to the shelf, so their cost comes off the
        maintenance cost of goods sold and the inventory account is credited.
        """
        if maintenance_return is None:
            raise ValueError(gettext("لا يمكن ترحيل مرتجع صيانة بدون مستند"))
        tid = maintenance_return.tenant_id
        order = maintenance_return.order
        branch_id = order.branch_id if order is not None else None

        gross = Decimal(str(maintenance_return.total_value or 0))
        tax = Decimal(str(maintenance_return.total_value_tax or 0))
        net = gross - tax
        if gross <= 0:
            raise GlPostingError(gettext("لا يمكن ترحيل مرتجع صيانة بقيمة صفرية"))

        revenue_account = MaintenanceGLService._require_account("MAINTENANCE_REVENUE", tid, branch_id)
        ar_account = MaintenanceGLService._require_account("MAINTENANCE_AR", tid, branch_id)

        lines = [
            {
                "account": revenue_account,
                "concept_code": "MAINTENANCE_REVENUE",
                "debit": net,
                "description": gettext("عكس إيراد صيانة - مرتجع {number}").format(
                    number=maintenance_return.return_number
                ),
            },
            {
                "account": ar_account,
                "concept_code": "MAINTENANCE_AR",
                "credit": gross,
                "description": gettext("عكس ذمم صيانة - مرتجع {number}").format(
                    number=maintenance_return.return_number
                ),
            },
        ]

        if tax > 0:
            vat_account = MaintenanceGLService._require_account("VAT_OUTPUT", tid, branch_id)
            lines.append(
                {
                    "account": vat_account,
                    "concept_code": "VAT_OUTPUT",
                    "debit": tax,
                    "description": gettext("عكس ضريبة مخرجات - مرتجع صيانة {number}").format(
                        number=maintenance_return.return_number
                    ),
                }
            )

        entry = post_or_fail(
            lines=lines,
            description=gettext("عكس إيراد صيانة - مرتجع {number}").format(number=maintenance_return.return_number),
            reference_type=GLRef.MAINTENANCE_RETURN,
            reference_id=maintenance_return.id,
            date=maintenance_return.return_date,
            currency=order.currency if order is not None else "AED",
            exchange_rate=order.exchange_rate if order is not None else Decimal("1"),
            branch_id=branch_id,
            user_id=user_id,
            tenant_id=tid,
        )

        # The returned parts go back on the shelf: their cost leaves the
        # maintenance cost of goods sold and returns to the inventory account.
        cost = Decimal(str(maintenance_return.total_value_cost or 0))
        if cost > 0:
            cogs_account = MaintenanceGLService._require_account("MAINTENANCE_COGS", tid, branch_id)
            inventory_account = MaintenanceGLService._require_account("INVENTORY_ASSET", tid, branch_id)
            post_or_fail(
                lines=[
                    {
                        "account": inventory_account,
                        "concept_code": "INVENTORY_ASSET",
                        "debit": cost,
                        "description": gettext("إرجاع قطع الصيانة إلى المخزون - {number}").format(
                            number=maintenance_return.return_number
                        ),
                    },
                    {
                        "account": cogs_account,
                        "concept_code": "MAINTENANCE_COGS",
                        "credit": cost,
                        "description": gettext("عكس تكلفة قطع الصيانة - {number}").format(
                            number=maintenance_return.return_number
                        ),
                    },
                ],
                description=gettext("عكس تكلفة قطع الصيانة - {number}").format(number=maintenance_return.return_number),
                reference_type=GLRef.MAINTENANCE_RETURN,
                reference_id=maintenance_return.id,
                date=maintenance_return.return_date,
                currency=order.currency if order is not None else "AED",
                exchange_rate=order.exchange_rate if order is not None else Decimal("1"),
                branch_id=branch_id,
                user_id=user_id,
                tenant_id=tid,
            )

        maintenance_return.gl_posted = True
        maintenance_return.gl_posted_at = datetime.now(UTC)
        maintenance_return.posted = True
        maintenance_return.posted_at = datetime.now(UTC)
        db.session.flush()

        log_financial(
            message=f"Maintenance return posted to GL: {maintenance_return.return_number}",
            tenant_id=tid,
            level="INFO",
            source="services.maintenance_gl_service.MaintenanceGLService.post_return",
            extra={
                "return_id": maintenance_return.id,
                "tenant_id": tid,
                "gl_entry_id": entry.id,
                "total": float(gross),
            },
        )

        return entry
