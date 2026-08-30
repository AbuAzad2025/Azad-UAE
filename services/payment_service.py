from datetime import UTC
from decimal import ROUND_HALF_UP, Decimal

from flask import current_app
from flask_babel import gettext
from flask_login import current_user

from extensions import db
from models import Sale
from models.receipt import Receipt
from services.cheque_service import process_cheque_receive
from services.exchange_rate_service import ExchangeRateService
from services.gl_posting import GlPostingError, post_or_fail
from services.gl_service import GLService
from utils.branching import branch_scope_id_for
from utils.currency_utils import (
    convert_and_quantize_aed,
    get_system_default_currency,
    resolve_tenant_base_currency,
)
from utils.field_validators import (
    canonical_payment_type,
    validate_currency_code,
    validate_payment_method,
)
from utils.gl_reference_types import GLRef
from utils.helpers import generate_number
from utils.tenanting import get_active_tenant_id


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
        if rate_info.get("rate_mode") == "needs_input":
            raise ValueError(
                gettext(
                    "⚠️ سعر الصرف غير متوفر.\n"
                    "💡 اذهب إلى إعدادات المالك ← أسعار الصرف ← أدخل سعر يدوي، "
                    'أو أدخل سعراً في حقل "سعر الصرف".'
                )
            )
        return Decimal(str(rate_info["rate"]))

    @staticmethod
    def _resolve_branch_id(explicit_branch_id=None, *, user=None, sale=None):
        if explicit_branch_id:
            return explicit_branch_id
        if sale and (sale.branch_id if sale is not None else None):
            return sale.branch_id
        scoped_branch_id = branch_scope_id_for(user or current_user)
        if scoped_branch_id:
            return scoped_branch_id
        if user is not None and user.branch_id:
            return user.branch_id
        if current_user is not None and getattr(current_user, "is_authenticated", False):
            return current_user.branch_id
        return None

    @staticmethod
    def _post_supplier_fx_gain_loss(payment, purchase, tenant_id):
        """ترحيل فروقات العملة المحققة عند تسوية ذمة مورد (AP) بعملة أجنبية.

        - نفس العملة بسعرين مختلفين: الفرق يُحسب على مبلغ الدفعة نفسها.
        - تسوية متقاطعة العملات: لا فروقات على الدفعات الجزئية — الفرق يبقى في
          الرصيد المفتوح المحمول بالعملة الأساسية، ويُحسب عند الإقفال النهائي
          كفرق بين القيمة الفعلية للدفعة والرصيد الدفتري المتبقي قبلها.
        الشيكات غير المؤكدة تُستثنى — فروقاتها تُرحّل عند التحصيل.
        يرمي الاستثناء كما هو — الذرّية يضمنها atomic_transaction لدى المتصل.
        """
        if not purchase:
            return
        if not getattr(payment, "payment_confirmed", True):
            return
        purchase_rate = Decimal(str(getattr(purchase, "exchange_rate", None) or 1))
        payment_rate = Decimal(str(payment.exchange_rate or 1))
        if not payment.amount or payment.amount <= 0:
            return
        purchase_currency = getattr(purchase, "currency", None) or ""
        payment_currency = getattr(payment, "currency", None) or ""
        actual_aed = convert_and_quantize_aed(payment.amount, payment_currency, payment_rate, tenant_id=tenant_id)
        if purchase_currency.upper() == payment_currency.upper():
            if purchase_rate == payment_rate:
                return
            expected_aed = convert_and_quantize_aed(
                payment.amount, payment_currency, purchase_rate, tenant_id=tenant_id
            )
        else:
            paid_incl_current = Decimal(str(purchase.get_paid_amount() or 0))
            paid_before = paid_incl_current - Decimal(str(payment.amount_aed or actual_aed))
            open_before = (Decimal(str(purchase.amount_aed or 0)) - paid_before).quantize(
                Decimal("0.001"), rounding=ROUND_HALF_UP
            )
            if open_before <= 0:
                return
            remaining_after = (open_before - actual_aed).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
            if remaining_after > Decimal("0.01"):
                return
            expected_aed = open_before
        fx_diff = (actual_aed - expected_aed).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        if abs(fx_diff) <= Decimal("0.01"):
            return
        ap_account = GLService.get_account_code_for_concept(
            "AP",
            branch_id=payment.branch_id,
            tenant_id=tenant_id,
            fallback_key="payable",
        )
        if fx_diff > 0:
            fx_lines = [
                {
                    "account": GLService.get_account_code_for_concept(
                        "FX_LOSS",
                        branch_id=payment.branch_id,
                        tenant_id=tenant_id,
                        fallback_key="fx_loss",
                    ),
                    "concept_code": "FX_LOSS",
                    "debit": fx_diff,
                    "description": f"FX Loss - Payment {payment.payment_number}",
                },
                {
                    "account": ap_account,
                    "concept_code": "AP",
                    "credit": fx_diff,
                    "description": f"FX Loss Adjustment - Payment {payment.payment_number}",
                },
            ]
        else:
            gain = abs(fx_diff)
            fx_lines = [
                {
                    "account": ap_account,
                    "concept_code": "AP",
                    "debit": gain,
                    "description": f"FX Gain Adjustment - Payment {payment.payment_number}",
                },
                {
                    "account": GLService.get_account_code_for_concept(
                        "FX_GAIN",
                        branch_id=payment.branch_id,
                        tenant_id=tenant_id,
                        fallback_key="fx_gain",
                    ),
                    "concept_code": "FX_GAIN",
                    "credit": gain,
                    "description": f"FX Gain - Payment {payment.payment_number}",
                },
            ]
        post_or_fail(
            fx_lines,
            description=f"FX Gain/Loss - Payment {payment.payment_number}",
            reference_type=GLRef.PAYMENT,
            reference_id=payment.id,
            currency=resolve_tenant_base_currency(tenant_id=tenant_id),
            exchange_rate=1.0,
            branch_id=payment.branch_id,
            tenant_id=tenant_id,
        )

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
        from models import Payment, Supplier

        supplier_id = payment_data.get("supplier_id")
        amount = payment_data.get("amount")
        currency = validate_currency_code(payment_data.get("currency", get_system_default_currency()))
        payment_method = validate_payment_method(payment_data.get("payment_method", "cash"))
        notes = payment_data.get("notes")
        user_exchange_rate = payment_data.get("user_exchange_rate")
        reference_number = payment_data.get("reference_number")
        cheque_number = payment_data.get("cheque_number")
        cheque_date = payment_data.get("cheque_date")
        bank_name = payment_data.get("bank_name") or "Bank"
        branch_id = PaymentService._resolve_branch_id(
            payment_data.get("branch_id"),
            user=(current_user if getattr(current_user, "is_authenticated", False) else None),
        )

        supplier = db.session.get(Supplier, supplier_id)
        if not supplier:
            raise ValueError(gettext("المورد غير موجود"))

        try:
            payment_number = generate_number(
                "PAY",
                Payment,
                "payment_number",
                branch_id=branch_id,
                tenant_id=(supplier.tenant_id if supplier is not None else None),
            )

            exchange_rate = PaymentService._resolve_transaction_rate(currency, user_exchange_rate)
            base_currency = resolve_tenant_base_currency(
                tenant_id=(supplier.tenant_id if supplier is not None else None)
            )

            payment = Payment(
                tenant_id=(supplier.tenant_id if supplier is not None else None)
                or (
                    (current_user.tenant_id if current_user is not None else None)
                    if current_user and getattr(current_user, "is_authenticated", False)
                    else None
                ),
                payment_number=payment_number,
                payment_type=canonical_payment_type("supplier_payment"),
                direction="outgoing",
                supplier_id=supplier.id,
                supplier_name=supplier.name,
                amount=Decimal(str(amount)),
                currency=currency,
                exchange_rate=exchange_rate,
                base_currency=base_currency,
                amount_aed=convert_and_quantize_aed(
                    amount, currency, exchange_rate, tenant_id=(supplier.tenant_id if supplier is not None else None)
                ),
                payment_method=payment_method,
                reference_number=reference_number,
                notes=notes,
                user_id=(current_user.id if current_user and current_user.is_authenticated else 1),
                branch_id=branch_id,
                payment_confirmed=(payment_method != "cheque"),
            )

            db.session.add(payment)
            db.session.flush()

            if payment_method == "cheque" and cheque_number:
                from datetime import datetime

                from models import Cheque

                cheque = Cheque(
                    tenant_id=(supplier.tenant_id if supplier is not None else None)
                    or (
                        (current_user.tenant_id if current_user is not None else None)
                        if current_user and getattr(current_user, "is_authenticated", False)
                        else None
                    ),
                    cheque_number=cheque_number,
                    cheque_bank_number=cheque_number,
                    cheque_type="outgoing",
                    supplier_id=supplier.id,
                    amount=Decimal(str(amount)),
                    currency=currency,
                    exchange_rate=exchange_rate,
                    amount_aed=convert_and_quantize_aed(
                        amount, currency, exchange_rate, tenant_id=supplier.tenant_id if supplier is not None else None
                    ),
                    issue_date=datetime.now(UTC).date(),
                    due_date=cheque_date or datetime.now(UTC).date(),
                    bank_name=bank_name,
                    status="pending",
                    notes=notes,
                    branch_id=branch_id,
                )
                db.session.add(cheque)
                db.session.flush()
                payment.cheque_id = cheque.id

            # تحديث رصيد المورد التراكمي للدفعات المؤكدة والشيكات الصادرة
            # الشيك الصادر يخفض AP فوراً (قيد الإصدار: Dr AP / Cr Deferred Cheques)
            if payment.payment_confirmed or payment_method == "cheque":
                from decimal import Decimal as _D

                supplier.apply_payment(_D(str(payment.amount_aed or 0)))

            # GL Entries
            tenant_id = (supplier.tenant_id if supplier is not None else None) or (
                (current_user.tenant_id if current_user is not None else None)
                if current_user and getattr(current_user, "is_authenticated", False)
                else None
            )
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
                    {
                        "account": "2110",
                        "concept_code": "AP",
                        "debit": payment.amount,
                        "description": gettext(f"دفعة للمورد {supplier.name}"),
                    },
                    {
                        "account": credit_account,
                        "concept_code": GLService.get_payment_credit_concept(payment_method),
                        "credit": payment.amount,
                        "description": gettext(f"سند صرف {payment.payment_number}"),
                    },
                ]
                post_or_fail(
                    lines,
                    description=f"Payment {payment.payment_number}",
                    reference_type=GLRef.PAYMENT,
                    reference_id=payment.id,
                    currency=payment.currency,
                    exchange_rate=payment.exchange_rate,
                    branch_id=payment.branch_id,
                    tenant_id=tenant_id,
                )
            except Exception as _e:
                current_app.logger.exception("GL posting failed for payment: %s", _e)
                raise ValueError(gettext(f"فشل الترحيل المحاسبي للدفعة: {_e}")) from _e

            purchase_id = payment_data.get("purchase_id")
            if purchase_id:
                from models import Purchase

                purchase = db.session.get(Purchase, purchase_id)
                if purchase is not None:
                    payment.purchase_id = purchase.id
                    PaymentService._post_supplier_fx_gain_loss(payment, purchase, tenant_id)

            try:
                db.session.flush()
            except Exception:
                current_app.logger.exception("Payment flush failed for supplier payment")
                raise

            return payment

        except Exception:
            current_app.logger.exception("Payment creation failed")
            raise

    @staticmethod
    def create_supplier_refund(
        supplier_id: int,
        amount,
        currency: str,
        payment_method: str,
        notes: str = "",
        cheque_number: str = "",
        cheque_date=None,
        bank_name: str = "",
        branch_id: int | None = None,
    ):
        """Create incoming payment (refund from supplier) with GL posting."""
        from models import Payment, Supplier
        from services.gl_service import GLService

        supplier = db.session.get(Supplier, supplier_id)
        if not supplier:
            raise ValueError(gettext("المورد غير موجود"))

        tenant_id = (supplier.tenant_id if supplier is not None else None) or get_active_tenant_id(current_user)

        payment_number = generate_number(
            "PAY",
            Payment,
            "payment_number",
            branch_id=branch_id,
            tenant_id=tenant_id,
        )

        exchange_rate = PaymentService._resolve_transaction_rate(currency)
        base_currency = resolve_tenant_base_currency(tenant_id=tenant_id)
        amount_decimal = Decimal(str(amount))
        amount_aed = convert_and_quantize_aed(amount_decimal, currency, exchange_rate, tenant_id=tenant_id)

        payment = Payment(
            tenant_id=tenant_id,
            payment_number=payment_number,
            payment_type="refund",
            direction="incoming",
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            amount=amount_decimal,
            currency=currency,
            exchange_rate=exchange_rate,
            base_currency=base_currency,
            amount_aed=amount_aed,
            payment_method=payment_method,
            notes=notes,
            cheque_number=(cheque_number if payment_method == "cheque" else None),
            cheque_date=cheque_date if payment_method == "cheque" else None,
            bank_name=bank_name if payment_method == "cheque" else None,
            user_id=(current_user.id if current_user and current_user.is_authenticated else 1),
            branch_id=branch_id,
        )

        db.session.add(payment)
        db.session.flush()

        # GL Entries for refund: Debit cash/bank, Credit AP (2110)
        GLService.ensure_core_accounts(tenant_id=tenant_id)
        credit_account = GLService.get_payment_debit_account(
            payment_method,
            branch_id=payment.branch_id,
            tenant_id=tenant_id,
        )
        post_or_fail(
            [
                {
                    "account": credit_account,
                    "concept_code": GLService.get_payment_debit_concept(payment_method),
                    "debit": payment.amount,
                    "description": gettext(f"استرداد من مورد {supplier.name}"),
                },
                {
                    "account": "2110",
                    "concept_code": "AP",
                    "credit": payment.amount,
                    "description": gettext(f"سند قبض {payment.payment_number}"),
                },
            ],
            description=f"Supplier refund {payment.payment_number}",
            reference_type=GLRef.PAYMENT,
            reference_id=payment.id,
            currency=currency,
            exchange_rate=exchange_rate,
            branch_id=payment.branch_id,
            tenant_id=tenant_id,
        )

        # Refund reduces supplier's cached paid total
        supplier.apply_payment(-Decimal(str(payment.amount_aed or 0)))

        return payment

    @staticmethod
    def create_customer_payment(
        customer_id: int,
        amount,
        payment_method: str = "cash",
        notes: str = "",
        tenant_id: int | None = None,
        user_id: int | None = None,
        branch_id: int | None = None,
    ):
        """Create incoming payment (receipt from customer). Updates customer balance."""
        from datetime import datetime

        from models import Customer, Payment
        from utils.helpers import generate_number

        customer = db.session.get(Customer, customer_id)
        if not customer:
            raise ValueError(gettext("العميل غير موجود"))

        resolved_branch_id = branch_id
        if resolved_branch_id is None and user_id is not None:
            from models import User

            user = db.session.get(User, user_id)
            if user:
                resolved_branch_id = user.branch_id

        payment_number = generate_number(
            "PAY",
            Payment,
            "payment_number",
            branch_id=resolved_branch_id,
            tenant_id=tenant_id or (customer.tenant_id if customer is not None else None),
        )
        payment = Payment(
            payment_number=payment_number,
            customer_id=customer.id,
            amount=Decimal(str(amount or 0)),
            amount_aed=Decimal(str(amount or 0)),
            currency="AED",
            exchange_rate=1,
            payment_date=datetime.now(UTC),
            payment_method=payment_method,
            user_id=user_id or (current_user.id if current_user and current_user.is_authenticated else None),
            direction="incoming",
            payment_type="customer_payment",
            tenant_id=tenant_id or (customer.tenant_id if customer is not None else None),
            branch_id=resolved_branch_id,
        )
        db.session.add(payment)
        db.session.flush()

        customer.apply_receipt(Decimal(str(amount or 0)))

        return payment

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

        customer_id = payment_data.get("customer_id")
        amount = payment_data.get("amount")
        currency = validate_currency_code(payment_data.get("currency", get_system_default_currency()))
        payment_method = validate_payment_method(payment_data.get("payment_method", "cash"))
        notes = payment_data.get("notes")
        user_exchange_rate = payment_data.get("user_exchange_rate")
        reference_number = payment_data.get("reference_number")
        cheque_number = payment_data.get("cheque_number")
        cheque_date = payment_data.get("cheque_date")
        bank_name = payment_data.get("bank_name") or "Bank"
        allocate_to_sales = payment_data.get("allocate_to_sales")
        source_sale = None

        # Convert cheque_date to date object if it's a string
        if cheque_date and isinstance(cheque_date, str):
            from datetime import datetime

            try:
                cheque_date = datetime.strptime(cheque_date, "%Y-%m-%d").date()
            except ValueError as e:
                raise ValueError(gettext("تاريخ الشيك غير صالح")) from e

        customer = db.session.get(Customer, customer_id)
        if not customer:
            raise ValueError("Customer not found.")

        tenant_id = (customer.tenant_id if customer is not None else None) or (
            (current_user.tenant_id if current_user is not None else None)
            if current_user and getattr(current_user, "is_authenticated", False)
            else None
        )
        try:
            # تحديد نوع المصدر والاتجاه
            source_type = "manual"  # افتراضي
            source_id = None
            direction = "incoming"  # سندات القبض دائماً وارد

            if allocate_to_sales:
                # إذا كان مرتبط بفاتورة بيع
                source_type = "sale"
                source_id = list(allocate_to_sales.keys())[0]  # أول فاتورة
                source_sale = db.session.get(Sale, source_id)

            branch_id = PaymentService._resolve_branch_id(
                payment_data.get("branch_id"),
                user=(current_user if getattr(current_user, "is_authenticated", False) else None),
                sale=source_sale,
            )

            receipt_number = generate_number(
                "RCV",
                Receipt,
                "receipt_number",
                branch_id=branch_id,
                tenant_id=tenant_id,
            )

            exchange_rate = PaymentService._resolve_transaction_rate(currency, user_exchange_rate)
            base_currency = resolve_tenant_base_currency(tenant_id=tenant_id)

            receipt = Receipt(
                tenant_id=tenant_id,
                receipt_number=receipt_number,
                source_type=source_type,
                source_id=source_id,
                sale_id=source_id if source_type in ("sale", "refund", "adjustment") and source_id else None,
                direction=direction,
                customer_id=customer.id,
                amount=Decimal(str(amount)),
                currency=currency,
                exchange_rate=exchange_rate,
                base_currency=base_currency,
                amount_aed=convert_and_quantize_aed(amount, currency, exchange_rate, tenant_id=tenant_id),
                payment_method=payment_method,
                payment_confirmed=(payment_method != "cheque"),
                reference_number=reference_number,
                cheque_number=cheque_number,
                cheque_date=cheque_date,
                bank_name=bank_name,
                notes=notes,
                user_id=(current_user.id if current_user and current_user.is_authenticated else 1),
                branch_id=branch_id,
            )

            db.session.add(receipt)
            db.session.flush()

            # إنشاء سجل الشيك إذا كانت طريقة الدفع شيك
            if payment_method == "cheque" and cheque_number:
                from models import Cheque

                cheque = Cheque(
                    tenant_id=(customer.tenant_id if customer is not None else None)
                    or (
                        (current_user.tenant_id if current_user is not None else None)
                        if current_user and getattr(current_user, "is_authenticated", False)
                        else None
                    ),
                    cheque_number=cheque_number,
                    cheque_bank_number=cheque_number,  # نفس رقم الشيك
                    cheque_type="incoming",
                    customer_id=customer.id,
                    amount=Decimal(str(amount)),
                    currency=currency,
                    exchange_rate=exchange_rate,
                    amount_aed=convert_and_quantize_aed(amount, currency, exchange_rate, tenant_id=tenant_id),
                    issue_date=receipt.receipt_date.date(),  # تاريخ الإصدار = تاريخ السند
                    due_date=cheque_date,  # تاريخ الاستحقاق
                    bank_name=bank_name,
                    status="pending",
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
                    raise GlPostingError(gettext("فشل ترحيل الشيك محاسبياً"))
                # تحديث رصيد العميل فوراً لأن قيد الاستلام (Dr CUC / Cr AR) يخفض الذمم
                from decimal import Decimal as _D

                customer.apply_receipt(_D(str(receipt.amount_aed or 0)))

            else:
                # GL Entry for Standard Receipt (Cash/Bank)
                try:
                    GLService.ensure_core_accounts(tenant_id=(receipt.tenant_id if receipt is not None else None))
                    payment_account = GLService.get_payment_debit_account(
                        receipt.payment_method,
                        branch_id=receipt.branch_id,
                        tenant_id=(receipt.tenant_id if receipt is not None else None),
                    )
                    credit_account = GLService.get_customer_credit_account(
                        customer,
                        branch_id=receipt.branch_id,
                        tenant_id=(receipt.tenant_id if receipt is not None else None),
                    )

                    # Create GL entries
                    lines = [
                        {
                            "account": payment_account,
                            "concept_code": GLService.get_payment_debit_concept(receipt.payment_method),
                            "debit": receipt.amount,
                            "description": gettext(f"قبض من {customer.name}"),
                        },
                        {
                            "account": credit_account,
                            "concept_code": GLService.get_customer_credit_concept(customer),
                            "credit": receipt.amount,
                            "description": gettext(f"سند قبض {receipt.receipt_number}"),
                        },
                    ]
                    post_or_fail(
                        lines,
                        description=f"Receipt {receipt.receipt_number}",
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
                            expected_aed = convert_and_quantize_aed(
                                receipt.amount, receipt.currency, sale_rate, tenant_id=tenant_id
                            )
                            actual_aed = convert_and_quantize_aed(
                                receipt.amount, receipt.currency, receipt_rate, tenant_id=tenant_id
                            )
                            fx_diff = (actual_aed - expected_aed).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
                            if abs(fx_diff) > Decimal("0.01"):
                                try:
                                    fx_lines = []
                                    if fx_diff > 0:
                                        fx_lines = [
                                            {
                                                "account": GLService.get_account_code_for_concept(
                                                    "AR",
                                                    branch_id=receipt.branch_id,
                                                    tenant_id=tenant_id,
                                                    fallback_key="receivable",
                                                ),
                                                "concept_code": "AR",
                                                "debit": fx_diff,
                                                "description": f"FX Gain Adjustment - Receipt {receipt.receipt_number}",
                                            },
                                            {
                                                "account": GLService.get_account_code_for_concept(
                                                    "FX_GAIN",
                                                    branch_id=receipt.branch_id,
                                                    tenant_id=tenant_id,
                                                    fallback_key="fx_gain",
                                                ),
                                                "concept_code": "FX_GAIN",
                                                "credit": fx_diff,
                                                "description": f"FX Gain - Receipt {receipt.receipt_number}",
                                            },
                                        ]
                                    else:
                                        fx_lines = [
                                            {
                                                "account": GLService.get_account_code_for_concept(
                                                    "FX_LOSS",
                                                    branch_id=receipt.branch_id,
                                                    tenant_id=tenant_id,
                                                    fallback_key="fx_loss",
                                                ),
                                                "concept_code": "FX_LOSS",
                                                "debit": abs(fx_diff),
                                                "description": f"FX Loss - Receipt {receipt.receipt_number}",
                                            },
                                            {
                                                "account": GLService.get_account_code_for_concept(
                                                    "AR",
                                                    branch_id=receipt.branch_id,
                                                    tenant_id=tenant_id,
                                                    fallback_key="receivable",
                                                ),
                                                "concept_code": "AR",
                                                "credit": abs(fx_diff),
                                                "description": f"FX Loss Adjustment - Receipt {receipt.receipt_number}",
                                            },
                                        ]
                                    post_or_fail(
                                        fx_lines,
                                        description=f"FX Gain/Loss - Receipt {receipt.receipt_number}",
                                        reference_type=GLRef.RECEIPT,
                                        reference_id=receipt.id,
                                        currency=resolve_tenant_base_currency(tenant_id=tenant_id),
                                        exchange_rate=1.0,
                                        branch_id=receipt.branch_id,
                                        tenant_id=tenant_id,
                                    )
                                except Exception as fx_err:
                                    current_app.logger.exception(
                                        "FX auto-posting failed for receipt %s: %s",
                                        receipt.receipt_number,
                                        fx_err,
                                    )
                                    raise
                except Exception as _e:
                    current_app.logger.exception("GL posting failed for receipt: %s", _e)
                    raise ValueError(gettext(f"فشل الترحيل المحاسبي لسند القبض: {_e}")) from _e

                # تحديث رصيد العميل التراكمي (ما دُفع منه)
                from decimal import Decimal as _D

                customer.apply_receipt(_D(str(receipt.amount_aed or 0)))

            # Allocation Logic (Restored & Improved)
            if allocate_to_sales:
                remaining_amount_aed = Decimal(str(receipt.amount_aed or 0))

                for sale_id, allocated in allocate_to_sales.items():
                    if remaining_amount_aed <= 0:
                        break

                    sale = db.session.get(Sale, sale_id)

                    if not sale or sale.customer_id != customer.id:
                        continue

                    sale_balance_aed = Decimal(str(sale.balance_due or 0))
                    requested_amount = Decimal(str(allocated or 0))
                    requested_amount_aed = convert_and_quantize_aed(
                        requested_amount, currency, exchange_rate, tenant_id=tenant_id
                    )
                    allocated_amount_aed = min(requested_amount_aed, remaining_amount_aed, sale_balance_aed)
                    if allocated_amount_aed <= 0:
                        continue
                    allocated_amount = (allocated_amount_aed / exchange_rate).quantize(Decimal("0.001"))

                    # Create Payment record linked to Sale (Crucial for recalculation)
                    from models import Payment

                    sale_payment = Payment(
                        tenant_id=(
                            sale.tenant_id if sale is not None else customer.tenant_id if customer is not None else None
                        ),
                        payment_number=generate_number(
                            "PAY-S",
                            Payment,
                            "payment_number",
                            branch_id=sale.branch_id,
                            tenant_id=sale.tenant_id if sale is not None else None,
                        ),
                        payment_type="sale_payment",
                        direction="incoming",
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
                        user_id=(current_user.id if current_user and current_user.is_authenticated else 1),
                        branch_id=sale.branch_id or receipt.branch_id,
                    )
                    db.session.add(sale_payment)
                    db.session.flush()

                    # Direct update (will be overwritten by recalculate, but good for immediate state)
                    sale.paid_amount_aed += allocated_amount_aed
                    sale_rate = Decimal(str(sale.exchange_rate or 1))
                    if sale_rate > 0:
                        sale.paid_amount += (allocated_amount_aed / sale_rate).quantize(Decimal("0.001"))
                    # sale.balance_due -= allocated_amount # Let recalculate handle this

                    sale.recalculate_payment_status()

                    remaining_amount_aed -= allocated_amount_aed

            try:
                db.session.flush()
            except Exception:
                current_app.logger.exception("Receipt flush failed for %s", receipt.receipt_number)
                raise

            current_app.logger.info(f"Receipt created: {receipt.receipt_number}")

            return receipt

        except Exception:
            current_app.logger.exception("Receipt creation failed")
            raise

    @staticmethod
    def create_customer_refund(
        customer_id: int,
        amount,
        currency: str,
        exchange_rate,
        amount_aed,
        payment_method: str,
        notes: str = "",
        cheque_number: str = "",
        cheque_date=None,
        bank_name: str = "",
        date_str: str = "",
        branch_id: int | None = None,
        tenant_id: int | None = None,
    ):
        """Create outgoing payment (refund to customer) with GL posting and optional cheque."""
        from models import Customer, Payment
        from utils.helpers import generate_number

        customer = db.session.get(Customer, customer_id)
        if not customer:
            raise ValueError(gettext("العميل غير موجود"))

        payment_number = generate_number(
            "PAY",
            Payment,
            "payment_number",
            branch_id=branch_id,
            tenant_id=tenant_id,
        )
        payment = Payment(
            tenant_id=tenant_id,
            payment_number=payment_number,
            payment_type="refund",
            direction="outgoing",
            customer_id=customer.id,
            amount=amount,
            currency=currency,
            exchange_rate=exchange_rate,
            amount_aed=amount_aed,
            payment_method=payment_method,
            notes=notes,
            cheque_number=(cheque_number if payment_method == "cheque" else None),
            cheque_date=cheque_date if payment_method == "cheque" else None,
            bank_name=bank_name if payment_method == "cheque" else None,
            user_id=(current_user.id if current_user and current_user.is_authenticated else None),
            branch_id=branch_id,
        )
        db.session.add(payment)
        db.session.flush()

        if payment_method == "cheque" and cheque_number:
            from datetime import datetime

            from services.cheque_service import ChequeService, process_cheque_issue

            cheque = ChequeService.create_cheque(
                cheque_number=cheque_number,
                cheque_bank_number=cheque_number,
                cheque_type="outgoing",
                customer_id=customer.id,
                payment_id=payment.id,
                amount=payment.amount,
                currency=payment.currency,
                exchange_rate=payment.exchange_rate,
                due_date=cheque_date or datetime.now().date(),
                bank_name=bank_name,
                payee_name=customer.name,
                notes=notes,
                branch_id=branch_id,
                tenant_id=tenant_id,
            )
            payment.cheque_id = cheque.id
            payment.payment_confirmed = False
            process_cheque_issue(cheque)
        else:
            from services.gl_service import GLService

            GLService.ensure_core_accounts(tenant_id=tenant_id)
            credit_account = GLService.get_payment_credit_account(
                payment_method,
                branch_id=payment.branch_id,
                tenant_id=tenant_id,
            )
            debit_account = GLService.get_customer_credit_account(
                customer,
                branch_id=payment.branch_id,
                tenant_id=tenant_id,
            )
            post_or_fail(
                [
                    {
                        "account": debit_account,
                        "concept_code": GLService.get_customer_credit_concept(customer),
                        "debit": payment.amount,
                        "description": gettext(f"سداد/سحب {customer.name}"),
                    },
                    {
                        "account": credit_account,
                        "concept_code": GLService.get_payment_credit_concept(payment_method),
                        "credit": payment.amount,
                        "description": gettext(f"سند صرف {payment.payment_number}"),
                    },
                ],
                description=f"Customer refund {payment.payment_number}",
                reference_type=GLRef.PAYMENT,
                reference_id=payment.id,
                currency=currency,
                exchange_rate=exchange_rate,
                branch_id=payment.branch_id,
                tenant_id=tenant_id,
            )

        return payment

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
        from models.payment import payment_affects_balance

        if tenant_id is None:
            tenant_id = get_active_tenant_id()

        sales_total = db.session.query(db.func.sum(Sale.amount_aed)).filter(
            Sale.customer_id == customer_id,
            Sale.status == "confirmed",
        )
        receipts_total = db.session.query(db.func.sum(Receipt.amount_aed)).filter(
            Receipt.customer_id == customer_id,
            payment_affects_balance(Receipt),
        )
        outgoing_total = db.session.query(db.func.sum(PaymentModel.amount_aed)).filter(
            PaymentModel.customer_id == customer_id,
            PaymentModel.direction == "outgoing",
            payment_affects_balance(PaymentModel),
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
            (receipts_total.scalar() or Decimal("0"))
            - (sales_total.scalar() or Decimal("0"))
            - (outgoing_total.scalar() or Decimal("0"))
        )

    @staticmethod
    def get_supplier_balance_scoped(supplier_id, branch_id=None, tenant_id=None):
        """رصيد المورد مقيد بالتينانت والفرع. يحسب من SQL مباشر.
        الدلالة: موجب = مستحق للمورد (نحن ندين له)، سالب = المورد مدين لنا.
        الصيغة: Purchases - Outgoing_Payments + Incoming_Payments (refunds from supplier)
        """
        from models import Payment, Purchase
        from models.payment import payment_affects_balance

        if tenant_id is None:
            tenant_id = get_active_tenant_id()

        purchases_total = db.session.query(db.func.sum(Purchase.amount_aed)).filter(
            Purchase.supplier_id == supplier_id,
            Purchase.status == "confirmed",
        )
        outgoing_total = db.session.query(db.func.sum(Payment.amount_aed)).filter(
            Payment.supplier_id == supplier_id,
            Payment.direction == "outgoing",
            payment_affects_balance(Payment),
        )
        incoming_total = db.session.query(db.func.sum(Payment.amount_aed)).filter(
            Payment.supplier_id == supplier_id,
            Payment.direction == "incoming",
            payment_affects_balance(Payment),
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
            (purchases_total.scalar() or Decimal("0"))
            - (outgoing_total.scalar() or Decimal("0"))
            + (incoming_total.scalar() or Decimal("0"))
        )

    @staticmethod
    def get_customer_balance_and_unpaid_sales(customer):
        """استجابة موحدة لرصيد العميل + فواتير غير المدفوعة (للاستخدام في API واحد)."""
        balance_aed = float(PaymentService.get_customer_balance_aed(customer))
        unpaid = PaymentService.get_unpaid_sales(customer)
        unpaid_sales = [
            {
                "id": s.id,
                "sale_number": s.sale_number,
                "sale_date": (
                    s.sale_date.strftime("%Y-%m-%d") if getattr(s.sale_date, "strftime", None) else str(s.sale_date)
                ),
                "total_amount": float(s.total_amount),
                "balance_due": float(s.balance_due),
                "currency": s.currency or get_system_default_currency(),
            }
            for s in unpaid
        ]
        return {
            "balance_aed": balance_aed,
            "balance": balance_aed,
            "unpaid_sales": unpaid_sales,
        }

    @staticmethod
    def get_unpaid_sales(customer):
        return (
            Sale.query.filter(
                Sale.customer_id == customer.id,
                Sale.status == "confirmed",
                Sale.balance_due > 0,
            )
            .order_by(Sale.sale_date.asc())
            .all()
        )

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
                allocated = (allocated_aed / sale_rate).quantize(Decimal("0.001"))

                from models import Payment

                sale_payment = Payment(
                    tenant_id=(
                        sale.tenant_id if sale is not None else customer.tenant_id if customer is not None else None
                    ),
                    payment_number=generate_number(
                        "PAY-S",
                        Payment,
                        "payment_number",
                        branch_id=sale.branch_id,
                        tenant_id=(sale.tenant_id if sale is not None else None),
                    ),
                    payment_type="sale_payment",
                    direction="incoming",
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
                    user_id=(current_user.id if current_user and current_user.is_authenticated else 1),
                    branch_id=sale.branch_id or receipt.branch_id,
                )
                db.session.add(sale_payment)
                sale.recalculate_payment_status()
                remaining_amount_aed -= allocated_aed

            try:
                db.session.flush()
            except Exception:
                current_app.logger.exception("Receipt allocation flush failed for %s", receipt.receipt_number)
                raise
            current_app.logger.info(f"Receipt {receipt.receipt_number} allocated to sales")
        except Exception:
            current_app.logger.exception("Receipt allocation failed")

    @staticmethod
    def delete_receipt(receipt):
        """Delete a receipt and its associated cheque if any."""
        if receipt.cheque:
            db.session.delete(receipt.cheque)
        db.session.delete(receipt)

    @staticmethod
    def delete_payment(payment):
        """Delete a payment and its associated cheque if any."""
        if payment.cheque:
            db.session.delete(payment.cheque)
        db.session.delete(payment)

    # ── read-side lookups extracted from routes/payments.py ──

    @staticmethod
    def get_print_branch(branch_id, tenant_id):
        """Branch for a printable voucher, scoped to the tenant; None when no branch."""
        from models import Branch

        if not branch_id:
            return None
        return Branch.query.filter_by(id=branch_id, tenant_id=tenant_id).first()

    @staticmethod
    def find_archived_record(table_name, record_id, tenant_id=None):
        """ArchivedRecord by table + record id, optionally tenant filtered."""
        from models import ArchivedRecord

        archived_query = ArchivedRecord.query.filter_by(table_name=table_name, record_id=record_id)
        if tenant_id is not None:
            archived_query = archived_query.filter(ArchivedRecord.tenant_id == tenant_id)
        return archived_query.first()

    @staticmethod
    def list_archived_records(table_name, tenant_id=None):
        """All archived records of one table, optionally tenant filtered."""
        from models import ArchivedRecord

        query = ArchivedRecord.query.filter(ArchivedRecord.table_name == table_name)
        if tenant_id is not None:
            query = query.filter(ArchivedRecord.tenant_id == tenant_id)
        return query.all()

    @staticmethod
    def get_sale_for_receipt(receipt):
        """Tenant-scoped sale backing a receipt, or None."""
        from models import Sale

        if not receipt.source_id:
            return None
        return Sale.query.filter_by(id=receipt.source_id, tenant_id=receipt.tenant_id).first()

    @staticmethod
    def get_supplier_by_id(supplier_id, tenant_id):
        """Tenant-scoped supplier lookup, or None."""
        from models import Supplier

        if not supplier_id:
            return None
        return Supplier.query.filter_by(id=supplier_id, tenant_id=tenant_id).first()

    @staticmethod
    def get_confirmed_purchase_paid_total(purchase_id, tenant_id):
        """Sum of confirmed AED payments booked against a purchase (0 when none)."""
        from sqlalchemy import func

        from models import Payment

        return (
            db.session.query(func.sum(Payment.amount_aed))
            .filter(
                Payment.purchase_id == purchase_id,
                Payment.tenant_id == tenant_id,
                Payment.payment_confirmed,
            )
            .scalar()
            or 0
        )
