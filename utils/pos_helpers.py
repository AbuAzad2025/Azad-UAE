"""POS catalog, customer resolution, checkout line helpers, and session management."""
from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone

from extensions import db
from models import Customer, PosSession, Product
from services.stock_service import StockService
from utils.branching import get_accessible_warehouse_ids, get_branch_stock_map, get_active_branch_id
from utils.helpers import generate_number
from utils.tenanting import get_active_tenant_id, tenant_query

POS_WALKIN_MARKER = "[POS-WALKIN]"
POS_QA_MARKER = "[POS-QA]"


def get_pos_walkin_customer(tenant_id: int | None = None) -> Customer:
    """Tenant-scoped walk-in / quick-sale customer (stable, not QA junk)."""
    tid = tenant_id or get_active_tenant_id()
    if not tid:
        raise ValueError("لا توجد شركة نشطة.")

    existing = (
        tenant_query(Customer)
        .filter(Customer.is_active == True)
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
        base = base.filter(Product.is_active == True)
    if category_id:
        base = base.filter(Product.category_id == category_id)

    products = []
    if q:
        exact = base.filter(
            db.or_(
                db.func.lower(Product.barcode) == q.lower(),
                db.func.lower(Product.sku) == q.lower(),
            )
        ).limit(5).all()
        if exact:
            products = exact
        else:
            products = (
                _product_search_filters(base, q)
                .order_by(Product.name)
                .limit(per_page)
                .all()
            )
    else:
        products = base.order_by(Product.name).limit(per_page).all()

    wh_ids = _warehouse_ids_for_stock(warehouse_id, user)
    stock_map = (
        get_branch_stock_map(product_ids=[p.id for p in products], warehouse_ids=wh_ids)
        if wh_ids and products
        else {}
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
        base = base.filter(Product.is_active == True)

    product = base.filter(
        db.or_(
            db.func.lower(Product.barcode) == code.lower(),
            db.func.lower(Product.sku) == code.lower(),
        )
    ).first()
    if not product:
        return None, {}

    wh_ids = _warehouse_ids_for_stock(warehouse_id, user)
    stock_map = (
        get_branch_stock_map(product_ids=[product.id], warehouse_ids=wh_ids)
        if wh_ids
        else {}
    )
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
        product_id = int(row.get("product_id"))
        qty = Decimal(str(row.get("quantity")))
        if qty <= 0:
            raise ValueError("الكمية يجب أن تكون أكبر من صفر.")
        discount_percent = Decimal(str(row.get("discount_percent", 0) or 0))
        if discount_percent < 0 or discount_percent > 100:
            raise ValueError("نسبة الخصم يجب أن تكون بين 0 و 100.")
        unit_price = row.get("unit_price", None)
        if unit_price is not None and str(unit_price).strip() != "":
            unit_price = Decimal(str(unit_price))
        else:
            unit_price = None

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


def get_active_session(user=None, branch_id: int = None) -> PosSession | None:
    tenant_id = get_active_tenant_id(user)
    if not tenant_id:
        return None
    branch_id = branch_id or get_active_branch_id(user)
    return PosSession.query.filter(
        PosSession.tenant_id == int(tenant_id),
        PosSession.branch_id == int(branch_id) if branch_id else True,
        PosSession.user_id == user.id if user else True,
        PosSession.status == 'open',
    ).order_by(PosSession.id.desc()).first()


def require_active_session(user=None, branch_id: int = None) -> PosSession:
    session = get_active_session(user, branch_id)
    if not session:
        raise ValueError("لا توجد جلسة كاشير مفتوحة. يرجى فتح جلسة أولاً.")
    return session


def create_pos_session(user, branch_id: int, opening_balance: Decimal = Decimal('0'), notes: str = None) -> PosSession:
    tenant_id = get_active_tenant_id(user)
    if not tenant_id:
        raise ValueError("لا توجد شركة نشطة.")
    number = generate_number(
        prefix='POS-SES',
        model=PosSession,
        field_name='session_number',
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
        status='open',
    )
    db.session.add(session)
    db.session.flush()
    return session


def close_pos_session(session: PosSession, closing_cash: Decimal, notes: str = None):
    from models import Payment, Sale

    tenant_id = session.tenant_id
    sales_in_session = Sale.query.filter(
        Sale.tenant_id == int(tenant_id),
        Sale.seller_id == session.user_id,
        Sale.branch_id == session.branch_id,
        Sale.sale_date >= session.opened_at,
        db.or_(
            Sale.sale_date <= (session.closed_at or datetime.now(timezone.utc)),
            Sale.sale_date == None,
        ),
    ).all()

    total = Decimal('0')
    cash_total = Decimal('0')
    card_total = Decimal('0')
    for sale in sales_in_session:
        total += Decimal(str(sale.total_amount or 0))
        for payment in sale.payments:
            method = getattr(payment, 'payment_method', '')
            amt = Decimal(str(payment.amount or 0))
            if method == 'cash':
                cash_total += amt
            elif method in ('card', 'bank_transfer', 'e_wallet'):
                card_total += amt

    session.total_sales = total
    session.total_cash_sales = cash_total
    session.total_card_sales = card_total
    session.close(closing_cash, notes)
    db.session.flush()
    return session
