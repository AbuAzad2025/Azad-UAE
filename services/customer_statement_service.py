"""Customer statement business logic."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask_babel import gettext
from sqlalchemy import func

from models import ProductReturn, Sale
from models.receipt import Receipt


def _scalar_to_decimal(value) -> Decimal:
    """Coerce an aggregate scalar (Decimal/float/int) to Decimal; zero when unavailable."""
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


class CustomerStatementService:
    """Build the render context for a customer statement."""

    @classmethod
    def build_statement_context(
        cls,
        *,
        record_id: int,
        date_from: str | None,
        date_to: str | None,
        transaction_type: str,
        default_currency: str,
        tenant_id: int,
        branch_id: int | None,
    ) -> dict:
        """Return ``{"transactions": ..., "final_balance": ..., "filters": ...}``.

        All data access is scoped to ``tenant_id`` and optional ``branch_id``.
        """
        from models import Payment

        sales_query = Sale.query.filter_by(customer_id=record_id, status="confirmed", tenant_id=tenant_id)
        payments_query = Payment.query.filter_by(customer_id=record_id, tenant_id=tenant_id)
        receipts_query = Receipt.query.filter_by(customer_id=record_id, tenant_id=tenant_id)
        returns_query = ProductReturn.query.filter_by(customer_id=record_id, status="approved", tenant_id=tenant_id)

        if branch_id is not None:
            sales_query = sales_query.filter(Sale.branch_id == branch_id)
            payments_query = payments_query.filter(Payment.branch_id == branch_id)
            receipts_query = receipts_query.filter(Receipt.branch_id == branch_id)
            returns_query = returns_query.filter(ProductReturn.branch_id == branch_id)

        if date_from:
            sales_query = sales_query.filter(func.date(Sale.sale_date) >= date_from)
            payments_query = payments_query.filter(func.date(Payment.payment_date) >= date_from)
            receipts_query = receipts_query.filter(func.date(Receipt.receipt_date) >= date_from)
            returns_query = returns_query.filter(func.date(ProductReturn.return_date) >= date_from)

        opening_balance = Decimal("0")
        if date_from:
            pre_sales_q = Sale.query.filter(
                Sale.customer_id == record_id,
                Sale.status == "confirmed",
                Sale.tenant_id == tenant_id,
                func.date(Sale.sale_date) < date_from,
            )
            pre_payments_q = Payment.query.filter(
                Payment.customer_id == record_id,
                Payment.tenant_id == tenant_id,
                func.date(Payment.payment_date) < date_from,
            )
            pre_receipts_q = Receipt.query.filter(
                Receipt.customer_id == record_id,
                Receipt.tenant_id == tenant_id,
                func.date(Receipt.receipt_date) < date_from,
            )
            pre_returns_q = ProductReturn.query.filter(
                ProductReturn.customer_id == record_id,
                ProductReturn.status == "approved",
                ProductReturn.tenant_id == tenant_id,
                func.date(ProductReturn.return_date) < date_from,
            )
            if branch_id is not None:
                pre_sales_q = pre_sales_q.filter(Sale.branch_id == branch_id)
                pre_payments_q = pre_payments_q.filter(Payment.branch_id == branch_id)
                pre_receipts_q = pre_receipts_q.filter(Receipt.branch_id == branch_id)
                pre_returns_q = pre_returns_q.filter(ProductReturn.branch_id == branch_id)

            pre_sales_total = _scalar_to_decimal(
                pre_sales_q.with_entities(func.coalesce(func.sum(Sale.amount_aed), 0)).scalar()
            )
            pre_pay_rows = pre_payments_q.with_entities(
                Payment.direction,
                Payment.amount_aed,
                Payment.payment_confirmed,
                Payment.payment_method,
                Payment.rejection_reason,
            ).all()
            pre_payments_net = sum(
                (Decimal(str(amount or 0)) if direction == "incoming" else -Decimal(str(amount or 0)))
                for direction, amount, confirmed, method, rejection in pre_pay_rows
                if confirmed or (method == "cheque" and not rejection)
            )
            pre_payment_refs = {ref for (ref,) in pre_payments_q.with_entities(Payment.reference_number).all() if ref}
            pre_receipts_total = sum(
                (
                    Decimal(str(r.amount_aed or 0))
                    for r in pre_receipts_q.all()
                    if (r.payment_confirmed or (r.payment_method == "cheque" and not r.rejection_reason))
                    and (r.receipt_number or "") not in pre_payment_refs
                ),
                Decimal("0"),
            )
            pre_returns_total = _scalar_to_decimal(
                pre_returns_q.with_entities(func.coalesce(func.sum(ProductReturn.amount_aed), 0)).scalar()
            )
            opening_balance = (pre_payments_net + pre_receipts_total + pre_returns_total) - pre_sales_total

        if date_to:
            sales_query = sales_query.filter(func.date(Sale.sale_date) <= date_to)
            payments_query = payments_query.filter(func.date(Payment.payment_date) <= date_to)
            receipts_query = receipts_query.filter(func.date(Receipt.receipt_date) <= date_to)
            returns_query = returns_query.filter(func.date(ProductReturn.return_date) <= date_to)

        sales = sales_query.order_by(Sale.sale_date).all()
        payments = payments_query.order_by(Payment.payment_date).all()
        receipts = receipts_query.order_by(Receipt.receipt_date).all()
        returns_list = returns_query.order_by(ProductReturn.return_date).all()

        transactions = []

        for sale in sales:
            sale_lines_data = []
            for idx, line in enumerate(sale.lines, start=1):
                quantity = Decimal(str(line.quantity or 0))
                unit_price = Decimal(str(line.unit_price or 0))
                discount_percent = Decimal(str(line.discount_percent or 0))
                gross_amount = quantity * unit_price
                discount_value = (
                    (gross_amount * discount_percent / Decimal("100")) if discount_percent else Decimal("0")
                )
                sale_lines_data.append(
                    {
                        "index": idx,
                        "product_name": (
                            line.product.get_display_name("ar") if line.product else gettext("بند غير معرف")
                        ),
                        "product_sku": (line.product.sku if line.product and line.product.sku else None),
                        "unit": (line.product.unit if line.product and hasattr(line.product, "unit") else None),
                        "quantity": float(quantity),
                        "unit_price": float(unit_price),
                        "discount_percent": float(discount_percent),
                        "discount_value": float(discount_value),
                        "gross_amount": float(gross_amount),
                        "line_total": float(line.line_total or 0),
                        "notes": line.notes or "",
                    }
                )

            sale_payments = sale.payments.order_by(Payment.payment_date.asc()).all()
            sale_payments_data = []
            last_payment_date = None

            for payment in sale_payments:
                if last_payment_date is None or payment.payment_date > last_payment_date:
                    last_payment_date = payment.payment_date

                cheque = payment.cheque if hasattr(payment, "cheque") else None
                sale_payments_data.append(
                    {
                        "id": payment.id,
                        "payment_number": payment.payment_number,
                        "payment_date": payment.payment_date,
                        "amount_aed": float(payment.amount_aed or 0),
                        "amount_original": float(payment.amount or 0),
                        "currency": payment.currency or default_currency,
                        "exchange_rate": float(payment.exchange_rate or 1),
                        "reference_number": payment.reference_number or "-",
                        "payment_method": payment.payment_method,
                        "payment_method_display": (
                            payment.get_method_display("ar")
                            if hasattr(payment, "get_method_display")
                            else payment.payment_method
                        ),
                        "status_ar": (
                            payment.status_ar
                            if hasattr(payment, "status_ar")
                            else (gettext("مؤكدة ✅") if payment.payment_confirmed else gettext("معلقة ⏳"))
                        ),
                        "payment_confirmed": payment.payment_confirmed,
                        "user": (
                            payment.user.get_display_name("ar")
                            if payment.user and hasattr(payment.user, "get_display_name")
                            else (payment.user.full_name if payment.user else None)
                        ),
                        "notes": payment.notes or "",
                        "direction": payment.direction,
                        "cheque_number": (cheque.cheque_number if cheque else payment.cheque_number),
                        "cheque_bank": cheque.bank_name if cheque else payment.bank_name,
                        "cheque_due_date": cheque.due_date if cheque else None,
                    }
                )

            sale_data = {
                "id": sale.id,
                "number": sale.sale_number,
                "date": sale.sale_date,
                "status": sale.payment_status,
                "subtotal": float(sale.subtotal or 0),
                "discount_amount": float(sale.discount_amount or 0),
                "shipping_cost": float(sale.shipping_cost or 0),
                "tax_rate": float(sale.tax_rate or 0),
                "tax_amount": float(sale.tax_amount or 0),
                "total_amount": float(sale.total_amount or sale.amount_aed or 0),
                "amount_aed": float(sale.amount_aed or 0),
                "paid_amount": float(sale.paid_amount_aed or 0),
                "balance_due": float(sale.balance_due or 0),
                "currency": sale.currency or default_currency,
                "exchange_rate": float(sale.exchange_rate or 1),
                "seller": (
                    sale.seller.get_display_name("ar")
                    if sale.seller and hasattr(sale.seller, "get_display_name")
                    else (sale.seller.full_name if sale.seller else None)
                ),
                "notes": sale.notes or "",
                "lines": sale_lines_data,
                "payments": sale_payments_data,
                "last_payment_date": last_payment_date,
            }

            transactions.append(
                {
                    "date": sale.sale_date,
                    "type": "sale",
                    "reference": sale.sale_number,
                    "debit": float(sale.amount_aed or 0),
                    "credit": 0,
                    "balance": 0,
                    "description": gettext("فاتورة بيع"),
                    "currency": sale.currency or default_currency,
                    "exchange_rate": float(sale.exchange_rate or 1),
                    "paid_amount": float(sale.paid_amount_aed or 0),
                    "balance_due": float(sale.balance_due or 0),
                    "status": sale.payment_status,
                    "sale": sale_data,
                    "_debit_exact": Decimal(str(sale.amount_aed or 0)),
                    "_credit_exact": Decimal("0"),
                }
            )

        for payment in payments:
            payment_amount_dec = Decimal(str(payment.amount_aed or 0))
            is_incoming = payment.direction == "incoming"
            credit_amount = float(payment_amount_dec) if is_incoming else 0.0
            debit_amount = float(payment_amount_dec) if not is_incoming else 0.0

            cheque = payment.cheque if hasattr(payment, "cheque") else None

            transactions.append(
                {
                    "date": payment.payment_date,
                    "type": "payment",
                    "reference": payment.reference_number or payment.payment_number or gettext(f"دفع #{payment.id}"),
                    "debit": debit_amount,
                    "credit": credit_amount,
                    "balance": 0,
                    "description": gettext(
                        f"دفعة - {payment.get_method_display('ar') if hasattr(payment, 'get_method_display') else payment.payment_method}"
                    ),
                    "currency": payment.currency or default_currency,
                    "exchange_rate": float(payment.exchange_rate or 1),
                    "paid_amount": credit_amount,
                    "balance_due": 0,
                    "status": (
                        payment.status_ar
                        if hasattr(payment, "status_ar")
                        else (gettext("مؤكدة ✅") if payment.payment_confirmed else gettext("معلقة ⏳"))
                    ),
                    "payment": {
                        "id": payment.id,
                        "payment_number": payment.payment_number,
                        "payment_date": payment.payment_date,
                        "amount_aed": float(payment.amount_aed or 0),
                        "amount_original": float(payment.amount or 0),
                        "base_amount": float(payment.amount_aed or 0),
                        "currency": payment.currency or default_currency,
                        "exchange_rate": float(payment.exchange_rate or 1),
                        "payment_method": payment.payment_method,
                        "payment_method_display": (
                            payment.get_method_display("ar")
                            if hasattr(payment, "get_method_display")
                            else payment.payment_method
                        ),
                        "reference_number": payment.reference_number or "-",
                        "direction": payment.direction,
                        "payment_confirmed": payment.payment_confirmed,
                        "rejection_reason": getattr(payment, "rejection_reason", None),
                        "status_ar": (
                            payment.status_ar
                            if hasattr(payment, "status_ar")
                            else (gettext("مؤكدة ✅") if payment.payment_confirmed else gettext("معلقة ⏳"))
                        ),
                        "user": (
                            payment.user.get_display_name("ar")
                            if payment.user and hasattr(payment.user, "get_display_name")
                            else (payment.user.full_name if payment.user else None)
                        ),
                        "notes": payment.notes or "",
                        "cheque_number": (cheque.cheque_number if cheque else payment.cheque_number),
                        "cheque_bank": cheque.bank_name if cheque else payment.bank_name,
                        "cheque_due_date": (cheque.due_date if cheque else payment.cheque_date),
                        "cheque_clearance_date": cheque.clearance_date if cheque else None,
                    },
                    "_debit_exact": payment_amount_dec if not is_incoming else Decimal("0"),
                    "_credit_exact": payment_amount_dec if is_incoming else Decimal("0"),
                }
            )

        allocated_receipt_numbers = set()
        for t in transactions:
            if t["type"] == "payment":
                ref = t.get("reference", "") or t.get("payment", {}).get("reference_number", "")
                if ref:
                    allocated_receipt_numbers.add(ref)

        for receipt in receipts:
            receipt_ref = receipt.receipt_number or gettext(f"قبض #{receipt.id}")
            if receipt_ref in allocated_receipt_numbers:
                continue
            transactions.append(
                {
                    "date": receipt.receipt_date,
                    "type": "receipt",
                    "reference": receipt_ref,
                    "debit": 0,
                    "credit": float(receipt.amount_aed or 0),
                    "balance": 0,
                    "description": gettext("سند قبض"),
                    "currency": default_currency,
                    "exchange_rate": 1.0,
                    "paid_amount": float(receipt.amount_aed or 0),
                    "balance_due": 0,
                    "status": gettext("مؤكدة") if receipt.payment_confirmed else gettext("معلقة"),
                    "payment_method": receipt.payment_method,
                    "payment_confirmed": receipt.payment_confirmed,
                    "rejection_reason": getattr(receipt, "rejection_reason", None),
                    "_debit_exact": Decimal("0"),
                    "_credit_exact": Decimal(str(receipt.amount_aed or 0)),
                }
            )

        for ret in returns_list:
            transactions.append(
                {
                    "date": ret.return_date,
                    "type": "return",
                    "reference": ret.return_number,
                    "debit": 0,
                    "credit": float(ret.amount_aed or 0),
                    "balance": 0,
                    "description": gettext("مرتجع مبيعات"),
                    "currency": ret.currency or default_currency,
                    "exchange_rate": float(ret.exchange_rate or 1),
                    "paid_amount": 0,
                    "balance_due": 0,
                    "status": gettext("معتمد"),
                    "_debit_exact": Decimal("0"),
                    "_credit_exact": Decimal(str(ret.amount_aed or 0)),
                }
            )

        def _sort_key(trans):
            d = trans.get("date")
            if d is None:
                return datetime.min
            if isinstance(d, datetime):
                return d.replace(tzinfo=None) if d.tzinfo else d
            return datetime(d.year, d.month, d.day)

        transactions.sort(key=_sort_key)

        if transaction_type in {"sale", "payment", "receipt", "return"}:
            transactions = [trans for trans in transactions if trans["type"] == transaction_type]

        if opening_balance != 0 or date_from:
            transactions.insert(
                0,
                {
                    "date": date_from if date_from else "",
                    "type": "opening",
                    "reference": "",
                    "debit": 0,
                    "credit": 0,
                    "balance": float(opening_balance),
                    "description": gettext("الرصيد الافتتاحي"),
                    "currency": default_currency,
                    "exchange_rate": 1.0,
                    "paid_amount": 0,
                    "balance_due": 0,
                    "status": "",
                    "is_confirmed": True,
                },
            )

        running_balance = opening_balance
        for trans in transactions:
            if trans["type"] == "opening":
                trans["balance"] = float(running_balance)
                continue
            if trans["type"] in ("payment", "receipt"):
                source = trans.get("payment") or trans
                confirmed = bool(source.get("payment_confirmed"))
                pending_cheque = source.get("payment_method") == "cheque" and not source.get("rejection_reason")
                is_confirmed = confirmed or pending_cheque
            else:
                is_confirmed = True
            credit_exact = trans.pop("_credit_exact", Decimal("0"))
            debit_exact = trans.pop("_debit_exact", Decimal("0"))
            if is_confirmed:
                running_balance += credit_exact - debit_exact
            trans["balance"] = float(running_balance)
            trans["is_confirmed"] = is_confirmed

        return {
            "transactions": transactions,
            "final_balance": float(running_balance),
            "filters": {
                "date_from": date_from or "",
                "date_to": date_to or "",
                "transaction_type": transaction_type,
            },
        }
