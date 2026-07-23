"""POS Phase 4 — smart returns (RMA) + cross-branch stock visibility.

Register-facing orchestration on top of the full-featured
``ReturnService.create_return``:

- ``lookup_receipt`` — exact receipt (sale_number) lookup for the returns
  screen, with per-line already-returned quantities and proportional
  promotional-discount allocations so the cashier sees exactly what a return
  will reverse. Tenant isolation is absolute; branch scope is enforced;
  holders of the ``pos_return`` permission may look up sales beyond the
  own-sales restriction the HTML returns flow keeps for sellers.
- ``create_pos_return`` — wraps ReturnService inside the caller's atomic
  transaction. The reversal ALWAYS uses the original sale's exchange_rate
  (ReturnService copies it onto the ProductReturn), never today's rate, so
  GL parity with the original invoice is exact. Optional ``refund_method``
  'cash' settles the return credit immediately out of the session drawer
  (Dr customer credit / Cr branch cash, at the original rate) and decrements
  the session/shift expected drawer via ``total_cash_refunds``; the default
  'credit' keeps the existing AR-credit behavior.
- ``stock_breakdown`` — per-warehouse on-hand breakdown across the tenant's
  accessible branches via a single grouped aggregate (no N+1).

Flush-only service; routes own the transaction boundary.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from extensions import db
from models import Payment, ProductReturn, ProductReturnLine, Sale
from models.enums import PermissionEnum
from services.gl_posting import post_or_fail
from services.gl_service import GLService
from services.return_service import ReturnService
from utils.branching import (
    branch_scope_id_for,
    get_accessible_warehouses,
    get_warehouse_stock_map,
)
from utils.gl_reference_types import GLRef
from utils.helpers import generate_number
from utils.pos_helpers import resolve_pos_cash_account_code
from utils.tenanting import tenant_query

_QUANTUM = Decimal("0.001")

REFUND_METHOD_CREDIT = "credit"
REFUND_METHOD_CASH = "cash"
REFUND_METHODS = frozenset({REFUND_METHOD_CREDIT, REFUND_METHOD_CASH})


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(_QUANTUM, rounding=ROUND_HALF_UP)


def _returned_quantities(sale_id: int, tenant_id: int) -> dict[int, Decimal]:
    """Sale-line → quantity already returned (non-rejected returns), one query."""
    rows = (
        db.session.query(
            ProductReturnLine.sale_line_id,
            db.func.coalesce(db.func.sum(ProductReturnLine.quantity), 0),
        )
        .join(ProductReturn, ProductReturnLine.return_id == ProductReturn.id)
        .filter(
            ProductReturn.sale_id == sale_id,
            ProductReturn.tenant_id == tenant_id,
            ProductReturn.status != "rejected",
        )
        .group_by(ProductReturnLine.sale_line_id)
        .all()
    )
    return {int(line_id): Decimal(str(qty or 0)) for line_id, qty in rows}


def _promo_allocations(sale) -> dict[int, Decimal]:
    """Proportional per-line allocation of ``sale.promotion_discount_amount``.

    Shares are proportional to each line's ``line_total``; the largest line
    absorbs the rounding residual so the allocation sums EXACTLY to the
    recorded promotional discount.
    """
    promo_raw = sale.__dict__.get("promotion_discount_amount")
    promo_total = _money(promo_raw) if promo_raw else Decimal("0")
    if promo_total <= 0:
        return {}
    subtotal = Decimal(str(sale.subtotal or 0))
    if subtotal <= 0:
        return {}
    lines = list(sale.lines or [])
    shares: dict[int, Decimal] = {}
    allocated = Decimal("0")
    largest_id = None
    largest_total = Decimal("-1")
    for line in lines:
        line_total = Decimal(str(line.line_total or 0))
        share = (line_total / subtotal * promo_total).quantize(_QUANTUM, rounding=ROUND_HALF_UP)
        shares[int(line.id)] = share
        allocated += share
        if line_total > largest_total:
            largest_total = line_total
            largest_id = int(line.id)
    residual = promo_total - allocated
    if residual and largest_id is not None:
        shares[largest_id] = shares[largest_id] + residual
    return shares


class PosRmaService:
    @staticmethod
    def resolve_sale_id(user, *, sale_id=None, sale_number=None) -> int | None:
        """Resolve a sale id from an explicit id or receipt number, scoped."""
        sale = None
        try:
            parsed_id = int(sale_id) if sale_id else None
        except (TypeError, ValueError):
            parsed_id = None
        if parsed_id:
            sale = tenant_query(Sale, user=user).filter(Sale.id == parsed_id).first()
        elif sale_number and str(sale_number).strip():
            query = tenant_query(Sale, user=user).filter(Sale.sale_number == str(sale_number).strip())
            scoped_branch_id = branch_scope_id_for(user)
            if scoped_branch_id is not None:
                query = query.filter(Sale.branch_id == scoped_branch_id)
            sale = query.first()
        return sale.id if sale is not None else None

    @staticmethod
    def lookup_receipt(user, number: str):
        """Exact sale_number lookup for the POS returns screen.

        Returns a serialization dict, or None when the receipt is not found
        in the caller's tenant/branch scope (the route maps that to 404, so
        cross-tenant probing is indistinguishable from a missing receipt).
        """
        number = (number or "").strip()
        if not number:
            raise ValueError("رقم الإيصال مطلوب.")

        query = tenant_query(Sale, user=user).filter(Sale.sale_number == number)
        scoped_branch_id = branch_scope_id_for(user)
        if scoped_branch_id is not None:
            query = query.filter(Sale.branch_id == scoped_branch_id)
        sale = query.first()
        if sale is None:
            return None

        tenant_id = int(sale.tenant_id)
        returned_map = _returned_quantities(sale.id, tenant_id)
        promo_shares = _promo_allocations(sale)

        lines = []
        for line in sale.lines or []:
            sold = Decimal(str(line.quantity or 0))
            returned = returned_map.get(int(line.id), Decimal("0"))
            returnable = sold - returned
            if returnable < 0:
                returnable = Decimal("0")
            product = line.product
            lines.append(
                {
                    "sale_line_id": line.id,
                    "product_id": line.product_id,
                    "product_name": getattr(product, "name", None),
                    "sku": getattr(product, "sku", None),
                    "barcode": getattr(product, "barcode", None),
                    "quantity_sold": float(sold),
                    "quantity_returned": float(returned),
                    "quantity_returnable": float(returnable),
                    "unit_price": float(line.unit_price or 0),
                    "discount_percent": float(line.discount_percent or 0),
                    "line_total": float(line.line_total or 0),
                    "promo_discount_share": float(promo_shares.get(int(line.id), Decimal("0"))),
                }
            )

        customer = sale.customer
        promo_total = sale.__dict__.get("promotion_discount_amount")
        return {
            "sale_id": sale.id,
            "sale_number": sale.sale_number,
            "sale_date": sale.sale_date.isoformat() if isinstance(sale.sale_date, datetime) else None,
            "status": sale.status,
            "payment_status": sale.payment_status,
            "customer_id": sale.customer_id,
            "customer_name": getattr(customer, "name", None),
            "currency": sale.currency,
            "exchange_rate": float(sale.exchange_rate or 1),
            "subtotal": float(sale.subtotal or 0),
            "discount_amount": float(sale.discount_amount or 0),
            "promotion_discount_amount": float(promo_total or 0),
            "shipping_cost": float(sale.shipping_cost or 0),
            "tax_rate": float(sale.tax_rate or 0),
            "tax_amount": float(sale.tax_amount or 0),
            "total_amount": float(sale.total_amount or 0),
            "lines": lines,
        }

    @staticmethod
    def stock_breakdown(user, *, product_id: int | None = None, barcode: str | None = None):
        """Per-warehouse on-hand breakdown for one product (single aggregate)."""
        from models import Product

        product = None
        if product_id:
            product = tenant_query(Product, user=user).filter(Product.id == int(product_id)).first()
        elif barcode:
            code = barcode.strip()
            product = (
                tenant_query(Product, user=user)
                .filter(db.or_(Product.barcode == code, Product.sku == code))
                .first()
            )
        if product is None:
            return None

        warehouses = [w for w in get_accessible_warehouses(user) if w.is_active]
        stock_map = get_warehouse_stock_map(
            product_ids=[product.id],
            warehouse_ids=[w.id for w in warehouses],
        )
        breakdown = []
        for warehouse in warehouses:
            qty = stock_map.get((product.id, warehouse.id), Decimal("0"))
            branch = getattr(warehouse, "branch", None)
            breakdown.append(
                {
                    "warehouse_id": warehouse.id,
                    "warehouse_name": warehouse.name,
                    "warehouse_code": warehouse.code,
                    "branch_id": warehouse.branch_id,
                    "branch_name": getattr(branch, "name", None),
                    "on_hand": float(qty),
                }
            )
        return {
            "product_id": product.id,
            "product_name": product.name,
            "sku": product.sku,
            "barcode": product.barcode,
            "total_on_hand": float(sum(Decimal(str(row["on_hand"])) for row in breakdown)),
            "warehouses": breakdown,
        }

    @staticmethod
    def _create_cash_refund_payment(*, product_return, sale, session, user):
        """Outgoing drawer Payment settling the return credit in cash.

        GL: Dr customer credit / Cr branch cash, posted in the sale currency
        at the ORIGINAL sale exchange rate — the exact reverse of the return's
        customer-credit leg, so the customer account nets to zero and the
        drawer decrement equals ``product_return.amount_aed`` (base).
        """
        tenant_id = int(sale.tenant_id)
        refund_amount = _money(product_return.refund_amount)
        if refund_amount <= 0:
            raise ValueError("مبلغ الاسترداد النقدي يجب أن يكون أكبر من صفر.")

        payment_number = generate_number(
            "PAY",
            Payment,
            "payment_number",
            branch_id=session.branch_id,
            tenant_id=tenant_id,
        )
        payment = Payment(
            tenant_id=tenant_id,
            payment_number=payment_number,
            payment_type="refund",
            direction="outgoing",
            # Deliberately NOT linked to sale_id: recalculate_payment_status
            # sums every confirmed payment on the sale as money RECEIVED — a
            # refund is money paid OUT and is tracked via the return instead.
            sale_id=None,
            customer_id=sale.customer_id,
            amount=refund_amount,
            currency=product_return.currency,
            exchange_rate=product_return.exchange_rate,
            amount_aed=product_return.amount_aed,
            payment_method="cash",
            payment_confirmed=True,
            confirmation_date=datetime.now(),
            notes=f"استرداد نقدي للمرتجع {product_return.return_number} — فاتورة {sale.sale_number}",
            user_id=getattr(user, "id", None),
            branch_id=session.branch_id,
        )
        db.session.add(payment)
        db.session.flush()

        customer_account = GLService.get_customer_credit_account(
            sale.customer,
            branch_id=session.branch_id,
            tenant_id=tenant_id,
        )
        cash_code = resolve_pos_cash_account_code(tenant_id, session.branch_id)
        description = f"استرداد نقدي {payment.payment_number} — مرتجع {product_return.return_number}"
        GLService.ensure_core_accounts(tenant_id=tenant_id)
        post_or_fail(
            [
                {
                    "account": customer_account,
                    "concept_code": GLService.get_customer_credit_concept(sale.customer),
                    "debit": refund_amount,
                    "credit": 0,
                    "description": description,
                },
                {
                    "account": cash_code,
                    "concept_code": "CASH",
                    "debit": 0,
                    "credit": refund_amount,
                    "description": description,
                },
            ],
            description=description,
            reference_type=GLRef.PAYMENT,
            reference_id=payment.id,
            currency=product_return.currency,
            exchange_rate=product_return.exchange_rate,
            branch_id=session.branch_id,
            user_id=getattr(user, "id", None),
            tenant_id=tenant_id,
        )

        # The return created customer credit; the cash hand-out consumes it.
        if sale.customer:
            sale.customer.adjust_balance(-Decimal(str(product_return.amount_aed or 0)))
        return payment

    @staticmethod
    def create_pos_return(*, user, session, shift, sale_id, return_lines, refund_method, notes=None):
        """Create a POS return (+ optional cash refund) inside the caller's transaction."""
        if refund_method not in REFUND_METHODS:
            raise ValueError("طريقة الاسترداد يجب أن تكون credit أو cash.")

        product_return = ReturnService.create_return(
            sale_id=sale_id,
            return_lines_data=return_lines,
            user=user,
            notes=notes,
        )

        refund_payment = None
        if refund_method == REFUND_METHOD_CASH:
            sale = product_return.sale
            refund_payment = PosRmaService._create_cash_refund_payment(
                product_return=product_return,
                sale=sale,
                session=session,
                user=user,
            )
            refund_base = _money(product_return.amount_aed)
            session.total_cash_refunds = Decimal(str(session.total_cash_refunds or 0)) + refund_base
            if shift is not None:
                shift.total_cash_refunds = Decimal(str(getattr(shift, "total_cash_refunds", None) or 0)) + refund_base
            db.session.add(session)
            if shift is not None:
                db.session.add(shift)
            # The cash settlement consumed the credit the return created;
            # refresh the sale's derived payment status accordingly.
            if hasattr(sale, "recalculate_payment_status"):
                sale.recalculate_payment_status()

        db.session.flush()
        return product_return, refund_payment

    @staticmethod
    def user_can_return_beyond_own_sales(user) -> bool:
        """True when the user may process returns for any seller's sale.

        Fail-closed ``is True`` checks so dynamic mock attributes never
        silently grant the privilege.
        """
        checker = getattr(user, "has_permission", None)
        return (getattr(user, "is_owner", None) is True) or (
            callable(checker) and checker(PermissionEnum.POS_RETURN) is True
        )
