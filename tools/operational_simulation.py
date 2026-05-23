import os
import random
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP


def _d(value) -> Decimal:
    return Decimal(str(value))


def _rand_phone(prefix: str, n: int) -> str:
    return f"{prefix}{n:06d}"


def _ensure_customer(db, Customer, tenant_id: int, name: str, customer_type: str, n: int):
    customer = Customer.query.filter_by(name=name).first()
    if customer:
        if not customer.customer_type:
            customer.customer_type = customer_type
        customer.customer_type = customer_type
        if getattr(customer, "tenant_id", None) is None:
            customer.tenant_id = tenant_id
        customer.is_active = True
        return customer

    customer = Customer(
        tenant_id=tenant_id,
        name=name,
        name_ar=name,
        customer_type=customer_type,
        phone=_rand_phone("05", n),
        email=f"{customer_type}{n}@example.com",
        address="",
        tax_number="",
        preferred_currency="AED",
        notes="",
        is_active=True,
    )
    db.session.add(customer)
    db.session.flush()
    return customer


def _ensure_supplier(db, Supplier, tenant_id: int, name: str, n: int):
    supplier = Supplier.query.filter_by(name=name).first()
    if supplier:
        if getattr(supplier, "tenant_id", None) is None:
            supplier.tenant_id = tenant_id
        supplier.is_active = True
        return supplier
    supplier = Supplier(
        tenant_id=tenant_id,
        name=name,
        name_ar=name,
        phone=_rand_phone("06", n),
        email=f"supplier{n}@example.com",
        address="",
        is_active=True,
    )
    db.session.add(supplier)
    db.session.flush()
    return supplier


def _ensure_category(db, ProductCategory, tenant_id: int, name: str):
    cat = ProductCategory.query.filter_by(name=name).first()
    if cat:
        cat.is_active = True
        if getattr(cat, "tenant_id", None) is None:
            cat.tenant_id = tenant_id
        return cat
    cat = ProductCategory(tenant_id=tenant_id, name=name, name_ar=name, description="", is_active=True)
    db.session.add(cat)
    db.session.flush()
    return cat


def _ensure_product(db, Product, tenant_id: int, cat, idx: int):
    name = f"منتج-{idx:03d}"
    product = Product.query.filter_by(name=name).first()
    if product:
        product.is_active = True
        if getattr(product, "tenant_id", None) is None:
            product.tenant_id = tenant_id
        if product.category_id is None:
            product.category_id = cat.id
        if product.regular_price is None or _d(product.regular_price) <= 0:
            product.regular_price = _d(100 + (idx % 10) * 10)
        if product.cost_price is None or _d(product.cost_price) <= 0:
            product.cost_price = (_d(product.regular_price) * _d("0.65")).quantize(_d("0.001"), rounding=ROUND_HALF_UP)
        return product

    sku = f"SKU-{100000 + idx}"
    barcode = f"BAR-{200000 + idx}"
    part = f"PN-{300000 + idx}"
    regular = _d(100 + (idx % 10) * 10).quantize(_d("0.001"), rounding=ROUND_HALF_UP)
    cost = (regular * _d("0.65")).quantize(_d("0.001"), rounding=ROUND_HALF_UP)
    product = Product(
        tenant_id=tenant_id,
        name=name,
        name_ar=name,
        commercial_name=name,
        sku=sku,
        part_number=part,
        barcode=barcode,
        country_of_origin="UAE",
        category_id=cat.id,
        regular_price=regular,
        cost_price=cost,
        current_stock=_d("0"),
        min_stock_alert=_d("5"),
        is_active=True,
    )
    db.session.add(product)
    db.session.flush()
    return product


def _ensure_expense_category(db, ExpenseCategory, name: str, gl_code: str):
    cat = ExpenseCategory.query.filter_by(name=name).first()
    if cat:
        cat.is_active = True
        cat.gl_account_code = cat.gl_account_code or gl_code
        return cat
    cat = ExpenseCategory(name=name, name_ar=name, gl_account_code=gl_code, is_active=True)
    db.session.add(cat)
    db.session.flush()
    return cat


def main():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if base_dir not in sys.path:
        sys.path.insert(0, base_dir)

    os.environ.setdefault("APP_ENV", "development")
    os.environ.setdefault("DEBUG", "1")
    os.environ.setdefault("SKIP_SYSTEM_INTEGRITY", "1")

    from app import create_app
    from extensions import db
    from models import (
        Branch,
        Cheque,
        Customer,
        Expense,
        ExpenseCategory,
        Product,
        ProductCategory,
        ProductPartner,
        Supplier,
        Tenant,
        User,
        Warehouse,
    )
    from services.gl_service import GLService
    from services.purchase_service import PurchaseService
    from services.sale_service import SaleService
    from utils.helpers import generate_number
    from utils.branching import get_branch_stock_map

    random.seed(20260523)

    app = create_app()
    with app.app_context():
        GLService.ensure_core_accounts()
        tenant = Tenant.get_current()
        tenant_id = int(tenant.id)

        branches = Branch.query.filter_by(is_active=True).order_by(Branch.is_main.desc(), Branch.id.asc()).all()
        if not branches:
            raise RuntimeError("No branches found")

        for b in branches:
            if getattr(b, "tenant_id", None) is None:
                b.tenant_id = tenant_id

        warehouses = Warehouse.query.filter_by(is_active=True).order_by(Warehouse.is_main.desc(), Warehouse.id.asc()).all()
        if not warehouses:
            raise RuntimeError("No warehouses found")

        for wh in warehouses:
            if getattr(wh, "tenant_id", None) is None:
                wh.tenant_id = tenant_id

        operator_user = (
            User.query.filter(User.username.like("seller_%")).order_by(User.id.asc()).first()
            or User.query.filter(User.username.like("manager_%")).order_by(User.id.asc()).first()
            or User.query.filter_by(is_active=True, is_owner=False).order_by(User.id.asc()).first()
        )
        if not operator_user:
            raise RuntimeError("No active users found")
        if getattr(operator_user, "tenant_id", None) is None:
            operator_user.tenant_id = tenant_id

        db.session.commit()

        partners = []
        merchants = []
        regulars = []
        for i in range(1, 11):
            partners.append(_ensure_customer(db, Customer, tenant_id, f"شريك-{i:02d}", "partner", 7000 + i))
        for i in range(1, 6):
            merchants.append(_ensure_customer(db, Customer, tenant_id, f"تاجر-{i:02d}", "merchant", 8000 + i))
        for i in range(1, 26):
            regulars.append(_ensure_customer(db, Customer, tenant_id, f"عميل-{i:02d}", "regular", 9000 + i))

        suppliers = []
        for i in range(1, 6):
            suppliers.append(_ensure_supplier(db, Supplier, tenant_id, f"مورد-{i:02d}", 6000 + i))

        cats = [
            _ensure_category(db, ProductCategory, tenant_id, "قطع محرك"),
            _ensure_category(db, ProductCategory, tenant_id, "كهرباء"),
            _ensure_category(db, ProductCategory, tenant_id, "سوائل"),
            _ensure_category(db, ProductCategory, tenant_id, "هيكل"),
        ]

        products = []
        for i in range(1, 31):
            products.append(_ensure_product(db, Product, tenant_id, cats[i % len(cats)], i))

        db.session.commit()

        ProductPartner.query.delete()
        db.session.commit()

        for p in products:
            chosen = random.sample(partners, k=random.randint(1, 3))
            remaining = Decimal("100.00")
            rows = []
            for idx, partner in enumerate(chosen):
                if idx == len(chosen) - 1:
                    pct = min(remaining, Decimal(str(random.randint(5, 20))))
                else:
                    pct = Decimal(str(random.randint(5, 20)))
                if pct <= 0:
                    continue
                if pct > remaining:
                    pct = remaining
                remaining -= pct
                rows.append((partner.id, pct))

            for partner_id, pct in rows:
                db.session.add(
                    ProductPartner(
                        product_id=p.id,
                        partner_customer_id=partner_id,
                        percentage=pct,
                    )
                )

        db.session.commit()

        for wh in warehouses:
            wh_user = (
                User.query.filter_by(is_active=True, branch_id=wh.branch_id)
                .filter(User.username.like("seller_%"))
                .order_by(User.id.asc())
                .first()
                or operator_user
            )
            if getattr(wh_user, "tenant_id", None) is None:
                wh_user.tenant_id = tenant_id
            supplier = random.choice(suppliers)
            lines = []
            for prod in random.sample(products, k=min(10, len(products))):
                qty = Decimal(str(random.randint(10, 50)))
                unit_cost = (_d(prod.cost_price or 0) or _d("1")).quantize(_d("0.001"), rounding=ROUND_HALF_UP)
                lines.append(
                    {
                        "product_id": prod.id,
                        "quantity": qty,
                        "unit_cost": unit_cost,
                        "discount_percent": 0,
                    }
                )
            PurchaseService.create_purchase(
                user=wh_user,
                supplier_data={"supplier_id": supplier.id, "supplier_name": supplier.name},
                lines_data=lines,
                warehouse_id=wh.id,
                currency="AED",
                notes="purchase seed",
            )
        db.session.commit()

        exp_cats = [
            _ensure_expense_category(db, ExpenseCategory, "إيجار", "6200"),
            _ensure_expense_category(db, ExpenseCategory, "رواتب", "6100"),
            _ensure_expense_category(db, ExpenseCategory, "كهرباء/ماء", "6200"),
        ]
        db.session.commit()

        def _postable_expense_account(code: str) -> str:
            from models import GLAccount
            acc = GLAccount.query.filter_by(code=code).first()
            if not acc:
                return "6990"
            if getattr(acc, "is_header", False):
                return "6990"
            return code

        for b in branches:
            for i in range(1, 7):
                cat = random.choice(exp_cats)
                amount = Decimal(str(random.randint(200, 1200))).quantize(_d("0.001"), rounding=ROUND_HALF_UP)
                exp = Expense(
                    expense_number=generate_number("E", Expense, "expense_number", branch_id=b.id),
                    category_id=cat.id,
                    description=f"{cat.name} - فرع {b.code}",
                    description_ar=f"{cat.name} - فرع {b.code}",
                    amount=amount,
                    currency="AED",
                    exchange_rate=Decimal("1.0"),
                    amount_aed=amount,
                    expense_date=datetime.now(timezone.utc) - timedelta(days=random.randint(0, 20)),
                    payment_method=random.choice(["cash", "bank_transfer"]),
                    reference_number="",
                    supplier_name="",
                    notes="expense seed",
                    status="confirmed",
                    is_active=True,
                    user_id=operator_user.id,
                    branch_id=b.id,
                )
                db.session.add(exp)
                db.session.flush()
                debit_account = _postable_expense_account(cat.gl_account_code or "6200")
                credit_account = "1110" if exp.payment_method == "cash" else "1120"
                GLService.post_entry(
                    lines=[
                        {"account": debit_account, "debit": exp.amount_aed, "credit": 0, "description": exp.description},
                        {"account": credit_account, "debit": 0, "credit": exp.amount_aed, "description": exp.expense_number},
                    ],
                    description=f"Expense {exp.expense_number}",
                    reference_type="expense",
                    reference_id=exp.id,
                    branch_id=exp.branch_id,
                )
        db.session.commit()

        for wh in warehouses:
            branch_id = wh.branch_id
            branch_sellers = User.query.filter_by(is_active=True, branch_id=branch_id).filter(User.username.like("seller_%")).all()
            seller = branch_sellers[0] if branch_sellers else operator_user
            if getattr(seller, "tenant_id", None) is None:
                seller.tenant_id = tenant_id
            stock_map = get_branch_stock_map(product_ids=[p.id for p in products], warehouse_ids=[wh.id])
            available_products = [p for p in products if _d(stock_map.get(p.id, 0)) > Decimal("0")]
            if not available_products:
                continue

            for _ in range(12):
                customer = random.choice(regulars + merchants + partners)
                lines = []
                chosen = random.sample(available_products, k=min(random.randint(1, 4), len(available_products)))
                for prod in chosen:
                    avail = _d(stock_map.get(prod.id, 0))
                    max_qty = int(avail) if avail > 0 else 0
                    if max_qty <= 0:
                        continue
                    qty = Decimal(str(random.randint(1, min(5, max_qty))))
                    unit_price = _d(prod.regular_price or 0)
                    lines.append(
                        {
                            "product": prod,
                            "quantity": qty,
                            "unit_price": unit_price,
                            "discount_percent": 0,
                        }
                    )
                    stock_map[prod.id] = avail - qty
                if not lines:
                    continue
                try:
                    SaleService.create_sale(
                        customer=customer,
                        seller=seller,
                        lines_data=lines,
                        warehouse_id=wh.id,
                        currency="AED",
                        notes="sale seed",
                        payment_data={"amount": 0, "currency": "AED", "exchange_rate": 1.0, "method": "cash"},
                    )
                except Exception:
                    db.session.rollback()
        db.session.commit()

        for b in branches:
            outgoing_partner = random.choice(partners)
            incoming_customer = random.choice(regulars)
            base_num = f"{b.code}-{datetime.now().strftime('%y%m%d')}-{random.randint(100,999)}"

            ch_out = Cheque(
                cheque_number=f"CH-OUT-{base_num}",
                cheque_bank_number=f"BNK-{random.randint(100000,999999)}",
                cheque_type="outgoing",
                bank_name="Local Bank",
                amount=Decimal(str(random.randint(300, 1500))),
                currency="AED",
                exchange_rate=Decimal("1.0"),
                issue_date=datetime.now().date(),
                due_date=(datetime.now() + timedelta(days=7)).date(),
                status="pending",
                payee_name=outgoing_partner.name,
                customer_id=outgoing_partner.id,
                branch_id=b.id,
                user_id=operator_user.id,
                is_active=True,
            )
            ch_out.calculate_amount_aed()
            db.session.add(ch_out)
            db.session.flush()
            ch_out.issue_cheque()
            ch_out.deposit_cheque()
            ch_out.clear_cheque()

            ch_in = Cheque(
                cheque_number=f"CH-IN-{base_num}",
                cheque_bank_number=f"BNK-{random.randint(100000,999999)}",
                cheque_type="incoming",
                bank_name="Local Bank",
                amount=Decimal(str(random.randint(500, 2500))),
                currency="AED",
                exchange_rate=Decimal("1.0"),
                issue_date=datetime.now().date(),
                due_date=(datetime.now() + timedelta(days=10)).date(),
                status="pending",
                drawer_name=incoming_customer.name,
                customer_id=incoming_customer.id,
                branch_id=b.id,
                user_id=operator_user.id,
                is_active=True,
            )
            ch_in.calculate_amount_aed()
            db.session.add(ch_in)
            db.session.flush()
            ch_in.receive_cheque()
            ch_in.deposit_cheque()
            ch_in.clear_cheque()

        db.session.commit()

        print("OPS_SIM_OK")
        print(f"PARTNERS={len(partners)} MERCHANTS={len(merchants)} CUSTOMERS={len(regulars)}")
        print(f"PRODUCTS={len(products)} SUPPLIERS={len(suppliers)}")
        print(f"WAREHOUSES={len(warehouses)} BRANCHES={len(branches)}")


if __name__ == "__main__":
    main()
