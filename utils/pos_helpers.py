"""POS catalog, customer resolution, checkout line helpers, and session management."""

from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal, InvalidOperation

from extensions import db
from models import Customer, PosSession, Product
from services.stock_service import StockService
from utils.branching import (
    get_accessible_warehouse_ids,
    get_active_branch_id,
    get_branch_stock_map,
)
from utils.currency_utils import convert_and_quantize_aed
from utils.helpers import generate_number
from utils.tenanting import get_active_tenant_id, tenant_query

POS_WALKIN_MARKER = "[POS-WALKIN]"
POS_QA_MARKER = "[POS-QA]"

_AED_QUANTUM = Decimal("0.001")


def safe_decimal(value, default: Decimal = Decimal("0")) -> Decimal:
    """Best-effort Decimal coercion — never raises on legacy/odd values."""
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return default


# ─── Scale (weight-embedded) barcodes — GS1 variable-measure, prefix 20 ───

SCALE_BARCODE_PREFIX = "20"

_WEIGHT_UNITS = frozenset({"kg", "kilogram", "kilograms", "kilo", "كجم", "كغ", "كيلو", "كيلوغرام"})


def parse_scale_barcode(code) -> dict | None:
    """Parse a 13-digit weight-embedded scale barcode (prefix ``20``).

    Layout: ``20`` + 5-digit item code + 5-digit weight in grams + EAN-13
    check digit. Returns ``{"item_code", "weight_grams", "weight_kg"}`` or
    ``None`` when the code is not a structurally valid scale barcode.
    """
    raw = str(code or "").strip()
    if len(raw) != 13 or not raw.isdigit() or not raw.startswith(SCALE_BARCODE_PREFIX):
        return None
    body = [int(d) for d in raw[:12]]
    checksum = (10 - (sum(body[::2]) + 3 * sum(body[1::2])) % 10) % 10
    if checksum != int(raw[12]):
        return None
    grams = Decimal(raw[7:12])
    return {
        "item_code": raw[2:7],
        "weight_grams": grams,
        "weight_kg": (grams / Decimal("1000")).quantize(_AED_QUANTUM, rounding=ROUND_HALF_UP),
    }


def payment_amount_base(payment, tenant_id: int | None = None) -> Decimal:
    """Exact base-currency amount of a sale payment row.

    Converts via ``convert_and_quantize_aed`` using the payment's own
    currency/exchange_rate; legacy rows without currency fall back to the raw
    amount quantized to 0.001.
    """
    raw = safe_decimal(getattr(payment, "amount", 0))
    currency = getattr(payment, "currency", None)
    if not isinstance(currency, str) or not currency.strip():
        return raw.quantize(_AED_QUANTUM, rounding=ROUND_HALF_UP)
    rate = safe_decimal(getattr(payment, "exchange_rate", None), default=Decimal("1"))
    if rate <= 0:
        rate = Decimal("1")
    return convert_and_quantize_aed(raw, currency, rate, tenant_id=tenant_id)


def resolve_pos_cash_account_code(tenant_id: int, branch_id: int) -> str:
    """Postable branch cash account code (single source for POS GL cash legs)."""
    from services import gl_helpers
    from services.gl_service import GL_ACCOUNTS, GLService
    from services.gl_tree_builder import GLTreeBuilder

    GLService.ensure_core_accounts(tenant_id=tenant_id)
    cash_parent_code = GL_ACCOUNTS.get("cash", "1110")
    cash_acct_code = GLTreeBuilder._branch_account_code(cash_parent_code, branch_id)
    cash_account = gl_helpers.get_account(cash_acct_code, tenant_id=tenant_id)
    if cash_account is None or getattr(cash_account, "is_header", False):
        cash_acct_code = GLService.get_account_code_for_concept(
            "CASH",
            tenant_id=tenant_id,
            branch_id=branch_id,
            fallback_key="cash",
        )
    return cash_acct_code


def get_pos_walkin_customer(tenant_id: int | None = None) -> Customer:
    """Tenant-scoped walk-in / quick-sale customer (stable, not QA junk)."""
    tid = tenant_id or get_active_tenant_id()
    if not tid:
        raise ValueError("لا توجد شركة نشطة.")

    existing = (
        tenant_query(Customer)
        .filter(Customer.is_active)
        .filter(
            db.or_(
                Customer.notes.ilike(f"%{POS_WALKIN_MARKER}%"),
                Customer.name == "عميل نقدي (POS)",
            )
        )
        .order_by(Customer.id.asc())
        .first()
    )
    if existing:
        return existing

    customer = Customer(
        tenant_id=int(tid),
        name="عميل نقدي (POS)",
        name_ar="عميل نقدي (POS)",
        customer_type="regular",
        notes=f"{POS_WALKIN_MARKER} عميل افتراضي لنقطة البيع",
        is_active=True,
    )
    db.session.add(customer)
    db.session.flush()
    return customer


def _warehouse_ids_for_stock(warehouse_id: int | None, user=None) -> list[int]:
    if warehouse_id:
        return [int(warehouse_id)]
    return get_accessible_warehouse_ids(user)


def _product_search_filters(query, q: str):
    like = f"%{q}%"
    return query.filter(
        db.or_(
            Product.name.ilike(like),
            Product.name_ar.ilike(like),
            Product.commercial_name.ilike(like),
            Product.sku.ilike(like),
            Product.barcode.ilike(like),
        )
    )


def snapshot_pos_products(*, user=None, warehouse_id: int | None = None, limit: int = 5000):
    """Full active-product snapshot for the register's offline catalog."""
    base = StockService.get_visible_products_query(user).filter(Product.is_active).order_by(Product.id)
    products = base.limit(max(1, min(int(limit or 5000), 10000))).all()
    wh_ids = _warehouse_ids_for_stock(warehouse_id, user)
    stock_map = (
        get_branch_stock_map(product_ids=[p.id for p in products], warehouse_ids=wh_ids) if wh_ids and products else {}
    )
    return products, stock_map


def search_pos_products(
    q: str,
    *,
    user=None,
    warehouse_id: int | None = None,
    per_page: int = 20,
    include_inactive: bool = False,
    category_id: int | None = None,
):
    q = (q or "").strip()
    per_page = max(1, min(int(per_page or 20), 50))
    base = StockService.get_visible_products_query(user)
    if not include_inactive:
        base = base.filter(Product.is_active)
    if category_id:
        base = base.filter(Product.category_id == category_id)

    products = []
    if q:
        exact = (
            base.filter(
                db.or_(
                    db.func.lower(Product.barcode) == q.lower(),
                    db.func.lower(Product.sku) == q.lower(),
                )
            )
            .limit(5)
            .all()
        )
        products = exact or _product_search_filters(base, q).order_by(Product.name).limit(per_page).all()
    else:
        products = base.order_by(Product.name).limit(per_page).all()

    wh_ids = _warehouse_ids_for_stock(warehouse_id, user)
    stock_map = (
        get_branch_stock_map(product_ids=[p.id for p in products], warehouse_ids=wh_ids) if wh_ids and products else {}
    )
    return products, stock_map, wh_ids


def lookup_pos_product_exact(
    code: str,
    *,
    user=None,
    warehouse_id: int | None = None,
    include_inactive: bool = False,
):
    code = (code or "").strip()
    if not code:
        return None, {}

    base = StockService.get_visible_products_query(user)
    if not include_inactive:
        base = base.filter(Product.is_active)

    product = base.filter(
        db.or_(
            db.func.lower(Product.barcode) == code.lower(),
            db.func.lower(Product.sku) == code.lower(),
        )
    ).first()
    if not product:
        scale = parse_scale_barcode(code)
        if scale:
            item = scale["item_code"].lower()
            product = base.filter(
                db.or_(
                    db.func.lower(Product.barcode) == item,
                    db.func.lower(Product.sku) == item,
                    db.func.lower(Product.barcode) == f"{SCALE_BARCODE_PREFIX}{item}",
                )
            ).first()
    if not product:
        return None, {}

    wh_ids = _warehouse_ids_for_stock(warehouse_id, user)
    stock_map = get_branch_stock_map(product_ids=[product.id], warehouse_ids=wh_ids) if wh_ids else {}
    return product, stock_map


def serialize_pos_product(product: Product, stock_map: dict, *, warehouse_id: int | None = None):
    stock = float(stock_map.get(product.id, product.current_stock or 0))
    inactive = not product.is_active
    no_stock = stock <= 0
    label = product.name
    if product.sku:
        label = f"{label} ({product.sku})"
    return {
        "id": product.id,
        "name": product.name,
        "name_ar": product.name_ar or "",
        "sku": product.sku or "",
        "barcode": product.barcode or "",
        "price": float(product.regular_price or 0),
        "stock": stock,
        "unit": product.unit,
        "is_active": product.is_active,
        "is_inactive": inactive,
        "is_out_of_stock": no_stock,
        "is_weight_product": (product.unit or "").strip().lower() in _WEIGHT_UNITS,
        "has_serial_number": bool(getattr(product, "has_serial_number", False)),
        "warehouse_id": warehouse_id,
        "text": label,
    }


def merge_checkout_lines(raw_lines: list) -> list[dict]:
    """Merge duplicate product_id rows; sum quantities; keep last unit_price/discount."""
    merged: dict[int, dict] = {}
    order: list[int] = []
    for row in raw_lines:
        if not isinstance(row, dict):
            raise ValueError("بيانات السلة غير صالحة.")
        product_id = int(row.get("product_id") or 0)
        try:
            qty = Decimal(f"{row.get('quantity')}")
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError("الكمية يجب أن تكون أكبر من صفر.")
        if qty <= 0:
            raise ValueError("الكمية يجب أن تكون أكبر من صفر.")
        discount_percent = Decimal(str(row.get("discount_percent", 0) or 0))
        if discount_percent < 0 or discount_percent > 100:
            raise ValueError("نسبة الخصم يجب أن تكون بين 0 و 100.")
        unit_price = row.get("unit_price", None)
        unit_price = Decimal(str(unit_price)) if unit_price is not None and str(unit_price).strip() != "" else None

        if product_id not in merged:
            merged[product_id] = {
                "product_id": product_id,
                "quantity": qty,
                "discount_percent": discount_percent,
                "unit_price": unit_price,
            }
            order.append(product_id)
        else:
            merged[product_id]["quantity"] += qty
            merged[product_id]["discount_percent"] = discount_percent
            if unit_price is not None:
                merged[product_id]["unit_price"] = unit_price
    return [merged[pid] for pid in order]


def get_active_session(user=None, branch_id: int | None = None) -> PosSession | None:
    tenant_id = get_active_tenant_id(user)
    if not tenant_id:
        return None
    branch_id = branch_id or get_active_branch_id(user)
    return (
        PosSession.query.filter(
            PosSession.tenant_id == int(tenant_id),
            PosSession.branch_id == int(branch_id) if branch_id else True,
            PosSession.user_id == user.id if user else True,
            PosSession.status == PosSession.STATUS_OPEN,
        )
        .order_by(PosSession.id.desc())
        .first()
    )


def get_paused_session(user=None, branch_id: int | None = None) -> PosSession | None:
    tenant_id = get_active_tenant_id(user)
    if not tenant_id:
        return None
    branch_id = branch_id or get_active_branch_id(user)
    return (
        PosSession.query.filter(
            PosSession.tenant_id == int(tenant_id),
            PosSession.branch_id == int(branch_id) if branch_id else True,
            PosSession.user_id == user.id if user else True,
            PosSession.status == PosSession.STATUS_PAUSED,
        )
        .order_by(PosSession.id.desc())
        .first()
    )


def require_active_session(user=None, branch_id: int | None = None) -> PosSession:
    session = get_active_session(user, branch_id)
    if not session:
        raise ValueError("لا توجد جلسة كاشير مفتوحة. يرجى فتح جلسة أولاً.")
    return session


def create_pos_session(
    user,
    branch_id: int,
    opening_balance: Decimal = Decimal("0"),
    notes: str | None = None,
    terminal_id: str | None = None,
) -> PosSession:
    tenant_id = get_active_tenant_id(user)
    if not tenant_id:
        raise ValueError("لا توجد شركة نشطة.")
    number = generate_number(
        prefix="POS-SES",
        model=PosSession,
        field_name="session_number",
        branch_code=branch_id,
        tenant_id=int(tenant_id),
    )
    session = PosSession(
        tenant_id=int(tenant_id),
        branch_id=int(branch_id),
        user_id=user.id,
        session_number=number,
        opening_balance_cash=opening_balance,
        notes=notes,
        status=PosSession.STATUS_OPEN,
        terminal_id=(terminal_id or "").strip() or None,
    )
    db.session.add(session)
    db.session.flush()
    return session


def _accumulate_close_totals(session: PosSession, sales_in_session: list) -> tuple[Decimal, Decimal, Decimal]:
    """Recompute session totals from payment rows with per-payment conversion.

    Payment rows linked to a sale are capped at the invoice amount (any
    overpayment is booked as an unlinked customer prepayment), so the summed
    cash figure is the NET cash that stays in the drawer. The returned cash
    figure is grossed back up by the session's tracked ``total_change_given``
    so ``PosSession.close()`` can derive: expected = opening + gross tender −
    change + pay-ins − pay-outs.
    """
    tenant_id = session.tenant_id
    total = Decimal("0")
    cash_net = Decimal("0")
    card_total = Decimal("0")
    for sale in sales_in_session:
        total += safe_decimal(getattr(sale, "total_amount", 0))
        for payment in sale.payments:
            method = getattr(payment, "payment_method", "")
            amt = payment_amount_base(payment, tenant_id=tenant_id)
            if method == "cash":
                cash_net += amt
            elif method in ("card", "bank_transfer", "e_wallet"):
                card_total += amt
    change_given = safe_decimal(getattr(session, "total_change_given", 0))
    return total, cash_net + change_given, card_total


def _post_session_difference_gl(session: PosSession, closing_cash: Decimal):
    """Balanced Cash Over/Short journal for a closed session (session-level only)."""
    from services.gl_posting import post_or_fail
    from utils.gl_reference_types import GLRef

    tenant_id = session.tenant_id
    diff_aed = safe_decimal(session.difference)
    cash_acct_code = resolve_pos_cash_account_code(tenant_id, session.branch_id)
    from services.gl_service import GLService

    diff_acct_code = GLService.get_account_code_for_concept(
        "POS_CASH_DIFFERENCE",
        tenant_id=tenant_id,
        branch_id=session.branch_id,
        fallback_key="pos_cash_difference",
    )
    lines = []
    if diff_aed < 0:
        # Shortage: debit expense, credit cash
        lines.append(
            {
                "account": diff_acct_code,
                "concept_code": "POS_CASH_DIFFERENCE",
                "debit": abs(diff_aed),
                "credit": 0,
                "description": f"عجز كاشير POS — جلسة {session.session_number}",
            }
        )
        lines.append(
            {
                "account": cash_acct_code,
                "concept_code": "CASH",
                "debit": 0,
                "credit": abs(diff_aed),
                "description": f"تسوية عجز كاشير POS — جلسة {session.session_number}",
            }
        )
    else:
        # Overage: debit cash, credit income (credit to difference account)
        lines.append(
            {
                "account": cash_acct_code,
                "concept_code": "CASH",
                "debit": diff_aed,
                "credit": 0,
                "description": f"فائض كاشير POS — جلسة {session.session_number}",
            }
        )
        lines.append(
            {
                "account": diff_acct_code,
                "concept_code": "POS_CASH_DIFFERENCE",
                "debit": 0,
                "credit": diff_aed,
                "description": f"تسوية فائض كاشير POS — جلسة {session.session_number}",
            }
        )
    post_or_fail(
        lines,
        description=f"تسوية جلسة POS {session.session_number} — رصيد مغلق: {closing_cash} | متوقع: {session.expected_balance} | فرق: {diff_aed}",
        reference_type=GLRef.POS_CASH_DIFFERENCE,
        reference_id=session.id,
        date=session.closed_at,
        branch_id=session.branch_id,
        user_id=session.user_id,
        tenant_id=tenant_id,
    )


def close_pos_session(session: PosSession, closing_cash: Decimal, notes: str | None = None):
    from models import Sale

    sales_in_session = Sale.query.filter(
        Sale.tenant_id == int(session.tenant_id),
        Sale.pos_session_id == session.id,
    ).all()

    total, cash_total, card_total = _accumulate_close_totals(session, sales_in_session)
    session.total_sales = total
    session.total_cash_sales = cash_total
    session.total_card_sales = card_total
    session.close(closing_cash, notes)
    db.session.flush()

    # Post GL for shortage/overage if difference exists — session level ONLY.
    # Shift reconcile/close never posts (no double-posting).
    if session.difference != 0:
        _post_session_difference_gl(session, closing_cash)
    return session


# Banknote ladders per currency for POS fast-cash keys. The AED set is the
# fallback for any unlisted currency.
FAST_CASH_DENOMINATIONS: dict[str, tuple[int, ...]] = {
    "AED": (5, 10, 20, 50, 100, 200, 500, 1000),
    "ILS": (20, 50, 100, 200),
    "USD": (1, 5, 10, 20, 50, 100),
    "EUR": (5, 10, 20, 50, 100, 200, 500),
    "SAR": (5, 10, 20, 50, 100, 200, 500),
    "JOD": (1, 5, 10, 20, 50),
    "EGP": (5, 10, 20, 50, 100, 200),
    "KWD": (1, 5, 10, 20),
    "BHD": (1, 5, 10, 20),
    "QAR": (5, 10, 20, 50, 100, 200, 500),
    "OMR": (1, 5, 10, 20, 50),
    "GBP": (5, 10, 20, 50),
}
_FAST_CASH_DEFAULT = FAST_CASH_DENOMINATIONS["AED"]


def compute_fast_cash_options(total, currency: str | None = None, max_options: int = 7) -> list[dict]:
    """Quick-cash tender keys for a cart total — pure, Decimal-exact.

    Returns the exact amount first, then the smallest round-up multiples of
    each banknote denomination of *currency* (deduplicated), each with its
    precomputed change. All values are ``Decimal`` quantized to 0.001.
    """
    total_dec = Decimal(str(total or "0")).quantize(_AED_QUANTUM, rounding=ROUND_HALF_UP)
    if total_dec < 0:
        raise ValueError("الإجمالي لا يمكن أن يكون سالباً.")

    code = (currency or "").strip().upper()
    denominations = FAST_CASH_DENOMINATIONS.get(code, _FAST_CASH_DEFAULT)

    options: list[dict] = [{"amount": total_dec, "change": Decimal("0.000"), "is_exact": True}]
    seen = {total_dec}
    for note in denominations:
        note_dec = Decimal(note)
        units = (total_dec / note_dec).to_integral_value(rounding=ROUND_CEILING)
        amount = (units * note_dec).quantize(_AED_QUANTUM, rounding=ROUND_HALF_UP)
        if amount in seen:
            continue
        seen.add(amount)
        options.append(
            {
                "amount": amount,
                "change": (amount - total_dec).quantize(_AED_QUANTUM, rounding=ROUND_HALF_UP),
                "is_exact": False,
            }
        )
        if len(options) >= max_options:
            break
    return options


# ─── Customer-facing display (CFD) payload ───


def build_cfd_order_payload(sale, kds_status: str | None = None) -> dict:
    """Build the enriched customer-display payload for a completed sale.

    Includes per-line discounts, manual vs promotion discount split, and an
    exact VAT breakdown. Product rows carry no per-line VAT class in the
    schema, so the standard bucket holds the sale's taxable base when the sale
    is rated, otherwise the full base is reported as zero-rated; the exempt
    bucket is emitted explicitly (0) to keep the contract stable.
    """
    items = []
    for line in sale.lines:
        qty = safe_decimal(line.quantity)
        price = safe_decimal(line.unit_price)
        disc_pct = safe_decimal(line.discount_percent)
        line_total = safe_decimal(line.line_total)
        gross = (qty * price).quantize(_AED_QUANTUM, rounding=ROUND_HALF_UP)
        product = getattr(line, "product", None)
        name = "—"
        if product is not None:
            name = (product.name_ar or product.name or "—").strip() or "—"
        items.append(
            {
                "name": name,
                "quantity": float(qty),
                "unit_price": float(price),
                "discount_percent": float(disc_pct),
                "discount_amount": float(gross - line_total),
                "total": float(line_total),
            }
        )

    tax_rate = safe_decimal(sale.tax_rate)
    taxable = safe_decimal(sale.taxable_amount)
    tax_amount = safe_decimal(sale.tax_amount)
    if tax_rate > 0:
        standard = {"base": float(taxable), "rate": float(tax_rate), "tax": float(tax_amount)}
        zero_base = 0.0
    else:
        standard = {"base": 0.0, "rate": 0.0, "tax": 0.0}
        zero_base = float(taxable)

    total = safe_decimal(sale.total_amount)
    paid = safe_decimal(sale.paid_amount)
    return {
        "type": "order_update",
        "order_number": sale.sale_number,
        "items": items,
        "subtotal": float(safe_decimal(sale.subtotal)),
        "discount_amount": float(safe_decimal(sale.discount_amount)),
        "promotion_discount_amount": float(safe_decimal(sale.promotion_discount_amount)),
        "taxable_amount": float(taxable),
        "tax_breakdown": {
            "standard": standard,
            "zero_rated": {"base": zero_base, "tax": 0.0},
            "exempt": {"base": 0.0, "tax": 0.0},
        },
        "total": float(total),
        "paid_amount": float(paid),
        "change_due": float(max(Decimal("0"), paid - total)),
        "status": kds_status or "confirmed",
    }


def build_print_tickets(sale, printers) -> list[dict]:
    """Split a sale into per-printer ESC/POS content payloads.

    ``printers`` is an iterable of PosPrinter rows (any role). Returns a
    list of tickets::

        {"role": "customer"|"kitchen"|"warehouse",
         "printer_name": str,
         "connection_type": str,
         "printer": <hardware-agent printer payload>,
         "content": {"lines": [...], "cut": True}}

    Customer-role printers always receive the full receipt. Kitchen and
    warehouse printers receive only the sale lines whose product category
    passes ``printer.covers_category`` (empty category list = all lines).
    Printers with no matching lines are skipped.
    """

    def _money(value) -> str:
        return f"{safe_decimal(value):.3f}".rstrip("0").rstrip(".") or "0"

    def _qty(value) -> str:
        return _money(value)

    def _line_name(line) -> str:
        product = getattr(line, "product", None)
        if product is not None:
            return product.name_ar or product.name or f"#{line.product_id}"
        return f"#{line.product_id}"

    header = [
        {"text": sale.sale_number or "", "align": "center", "bold": True, "double": True},
        {"separator": True},
    ]
    full_lines = list(header)
    for line in sale.lines or []:
        name = _line_name(line)
        full_lines.append({"text": f"{_qty(line.quantity)} x {name}", "align": "left"})
        full_lines.append(
            {
                "text": f"   {_money(line.line_total)}",
                "align": "right",
            }
        )
    full_lines.append({"separator": True})
    full_lines.append({"text": f"TOTAL {_money(sale.total_amount)}", "align": "center", "bold": True})

    tickets = []
    for printer in printers or []:
        role = getattr(printer, "role", "customer")
        if role == "customer":
            content = {"lines": list(full_lines), "cut": True, "open_drawer": True}
        else:
            role_lines = list(header)
            matched = 0
            for line in sale.lines or []:
                product = getattr(line, "product", None)
                category_id = getattr(product, "category_id", None)
                if not printer.covers_category(category_id):
                    continue
                matched += 1
                role_lines.append(
                    {
                        "text": f"{_qty(line.quantity)} x {_line_name(line)}",
                        "align": "left",
                        "bold": True,
                    }
                )
            if matched == 0:
                continue
            content = {"lines": role_lines, "cut": True}
        tickets.append(
            {
                "role": role,
                "printer_name": printer.name,
                "connection_type": printer.connection_type,
                "printer": printer.agent_printer_payload(),
                "content": content,
            }
        )
    return tickets
