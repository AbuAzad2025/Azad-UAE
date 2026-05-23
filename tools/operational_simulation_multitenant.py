import os
import random
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP


def _d(value) -> Decimal:
    return Decimal(str(value))


def _q(v: Decimal) -> Decimal:
    return _d(v).quantize(_d("0.001"), rounding=ROUND_HALF_UP)


def _ensure_tenant(db, Tenant, slug: str, name_ar: str, default_currency: str):
    tenant = Tenant.query.filter_by(slug=slug).first()
    if tenant:
        tenant.is_active = True
        tenant.default_currency = default_currency
        tenant.name_ar = name_ar
        tenant.name = tenant.name or slug
        return tenant
    tenant = Tenant(
        name=slug,
        name_ar=name_ar,
        slug=slug,
        business_type="garage",
        default_currency=default_currency,
        is_active=True,
    )
    db.session.add(tenant)
    db.session.flush()
    return tenant


def _ensure_branch(db, Branch, tenant_id: int, code: str, name: str, is_main: bool):
    b = Branch.query.filter_by(code=code).first()
    if b:
        b.is_active = True
        b.is_main = bool(is_main)
        b.tenant_id = tenant_id
        b.name = name
        return b
    b = Branch(
        tenant_id=tenant_id,
        code=code,
        name=name,
        city="UAE",
        is_active=True,
        is_main=bool(is_main),
    )
    db.session.add(b)
    db.session.flush()
    return b


def _ensure_warehouse(db, Warehouse, tenant_id: int, branch_id: int, code: str, name: str, is_main: bool):
    wh = Warehouse.query.filter_by(code=code).first()
    if wh:
        wh.is_active = True
        wh.is_main = bool(is_main)
        wh.tenant_id = tenant_id
        wh.branch_id = branch_id
        wh.name = name
        wh.name_ar = name
        return wh
    wh = Warehouse(
        tenant_id=tenant_id,
        name=name,
        name_ar=name,
        code=code,
        branch_id=branch_id,
        is_active=True,
        is_main=bool(is_main),
    )
    db.session.add(wh)
    db.session.flush()
    return wh


def _ensure_user(db, User, Role, tenant_id: int, branch_id: int, username: str, email: str, role_slug: str):
    user = User.query.filter_by(username=username).first()
    role = Role.query.filter_by(slug=role_slug).first()
    if not role:
        raise RuntimeError(f"Role not found: {role_slug}")
    if user:
        user.is_active = True
        user.tenant_id = tenant_id
        user.branch_id = branch_id
        user.role_id = role.id
        if user.email != email:
            user.email = email
        return user
    user = User(
        username=username,
        email=email,
        role_id=role.id,
        tenant_id=tenant_id,
        branch_id=branch_id,
        is_owner=False,
        is_active=True,
        email_verified=True,
        full_name=username,
        full_name_ar=username,
    )
    user.set_password("123")
    db.session.add(user)
    db.session.flush()
    return user


def _ensure_customer(db, Customer, tenant_id: int, name: str, customer_type: str, preferred_currency: str, n: int):
    customer = Customer.query.filter_by(tenant_id=tenant_id, name=name).first()
    if customer:
        customer.is_active = True
        customer.customer_type = customer_type
        customer.preferred_currency = preferred_currency
        return customer
    customer = Customer(
        tenant_id=tenant_id,
        name=name,
        name_ar=name,
        customer_type=customer_type,
        phone=f"05{n:08d}",
        email=f"{tenant_id}-{customer_type}-{n}@example.com",
        address="",
        tax_number="",
        preferred_currency=preferred_currency,
        notes="",
        is_active=True,
    )
    db.session.add(customer)
    db.session.flush()
    return customer


def _ensure_supplier(db, Supplier, tenant_id: int, name: str, n: int):
    supplier = Supplier.query.filter_by(tenant_id=tenant_id, name=name).first()
    if supplier:
        supplier.is_active = True
        return supplier
    supplier = Supplier(
        tenant_id=tenant_id,
        name=name,
        name_ar=name,
        phone=f"06{n:08d}",
        email=f"{tenant_id}-supplier-{n}@example.com",
        address="",
        is_active=True,
    )
    db.session.add(supplier)
    db.session.flush()
    return supplier


def _ensure_category(db, ProductCategory, tenant_id: int, name: str):
    cat = ProductCategory.query.filter_by(tenant_id=tenant_id, name=name).first()
    if cat:
        cat.is_active = True
        return cat
    cat = ProductCategory(tenant_id=tenant_id, name=name, name_ar=name, description="", is_active=True)
    db.session.add(cat)
    db.session.flush()
    return cat


def _ensure_product(db, Product, tenant_id: int, cat, idx: int, prefix: str):
    name = f"{prefix}-منتج-{idx:03d}"
    sku = f"{prefix}-SKU-{100000 + idx}"
    barcode = f"{prefix}-BAR-{200000 + idx}"
    part = f"{prefix}-PN-{300000 + idx}"
    product = Product.query.filter_by(tenant_id=tenant_id, sku=sku).first()
    if product:
        product.is_active = True
        if product.category_id is None:
            product.category_id = cat.id
        if product.regular_price is None or _d(product.regular_price) <= 0:
            product.regular_price = _q(100 + (idx % 10) * 10)
        if product.cost_price is None or _d(product.cost_price) <= 0:
            product.cost_price = _q(_d(product.regular_price) * _d("0.65"))
        return product
    regular = _q(100 + (idx % 10) * 10)
    cost = _q(regular * _d("0.65"))
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


def _ensure_expense_category(db, ExpenseCategory, tenant_id: int, name: str, gl_code: str):
    cat = ExpenseCategory.query.filter_by(tenant_id=tenant_id, name=name).first()
    if cat:
        cat.is_active = True
        cat.gl_account_code = cat.gl_account_code or gl_code
        return cat
    cat = ExpenseCategory(tenant_id=tenant_id, name=name, name_ar=name, gl_account_code=gl_code, is_active=True)
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
        GLAccount,
        Product,
        ProductCategory,
        ProductPartner,
        Role,
        Supplier,
        Tenant,
        User,
        Warehouse,
    )
    from services.currency_service import CurrencyService
    from services.gl_service import GLService
    from services.payment_service import PaymentService
    from services.purchase_service import PurchaseService
    from services.sale_service import SaleService
    from utils.helpers import generate_number
    from utils.branching import get_branch_stock_map

    random.seed(20260523)

    app = create_app()
    with app.app_context():
        GLService.ensure_core_accounts()

        tenants_spec = [
            ("t-aed", "شركة AED", "AED"),
            ("t-usd", "شركة USD", "USD"),
            ("t-ils", "شركة ILS", "ILS"),
        ]

        tenants = []
        for slug, name_ar, currency in tenants_spec:
            tenants.append(_ensure_tenant(db, Tenant, slug, name_ar, currency))

        db.session.commit()

        created = {
            "tenants": 0,
            "branches": 0,
            "warehouses": 0,
            "users": 0,
            "customers": 0,
            "suppliers": 0,
            "products": 0,
            "sales": 0,
            "purchases": 0,
            "receipts": 0,
            "payments": 0,
            "expenses": 0,
            "cheques": 0,
        }

        for tenant in tenants:
            tenant_id = int(tenant.id)
            prefix = tenant.slug.upper()

            b1 = _ensure_branch(db, Branch, tenant_id, code=f"{prefix}-A", name=f"{tenant.name_ar} - فرع A", is_main=True)
            b2 = _ensure_branch(db, Branch, tenant_id, code=f"{prefix}-B", name=f"{tenant.name_ar} - فرع B", is_main=False)
            created["branches"] += 2

            wh1 = _ensure_warehouse(
                db, Warehouse, tenant_id, b1.id, code=f"WH-{prefix}-A", name=f"{tenant.name_ar} - مستودع A", is_main=True
            )
            wh2 = _ensure_warehouse(
                db, Warehouse, tenant_id, b2.id, code=f"WH-{prefix}-B", name=f"{tenant.name_ar} - مستودع B", is_main=False
            )
            created["warehouses"] += 2

            seller_a = _ensure_user(
                db,
                User,
                Role,
                tenant_id,
                b1.id,
                username=f"seller_{tenant_id}_a",
                email=f"seller_{tenant_id}_a@example.com",
                role_slug="seller",
            )
            seller_b = _ensure_user(
                db,
                User,
                Role,
                tenant_id,
                b2.id,
                username=f"seller_{tenant_id}_b",
                email=f"seller_{tenant_id}_b@example.com",
                role_slug="seller",
            )
            manager_a = _ensure_user(
                db,
                User,
                Role,
                tenant_id,
                b1.id,
                username=f"manager_{tenant_id}_a",
                email=f"manager_{tenant_id}_a@example.com",
                role_slug="manager",
            )
            manager_b = _ensure_user(
                db,
                User,
                Role,
                tenant_id,
                b2.id,
                username=f"manager_{tenant_id}_b",
                email=f"manager_{tenant_id}_b@example.com",
                role_slug="manager",
            )
            created["users"] += 4

            partners = []
            merchants = []
            regulars = []
            for i in range(1, 6):
                partners.append(
                    _ensure_customer(db, Customer, tenant_id, f"{prefix}-شريك-{i:02d}", "partner", tenant.default_currency, 7000 + i)
                )
            for i in range(1, 4):
                merchants.append(
                    _ensure_customer(db, Customer, tenant_id, f"{prefix}-تاجر-{i:02d}", "merchant", tenant.default_currency, 8000 + i)
                )
            for i in range(1, 16):
                regulars.append(
                    _ensure_customer(db, Customer, tenant_id, f"{prefix}-عميل-{i:02d}", "regular", tenant.default_currency, 9000 + i)
                )
            created["customers"] += len(partners) + len(merchants) + len(regulars)

            suppliers = []
            for i in range(1, 5):
                suppliers.append(_ensure_supplier(db, Supplier, tenant_id, f"{prefix}-مورد-{i:02d}", 6000 + i))
            created["suppliers"] += len(suppliers)

            cats = [
                _ensure_category(db, ProductCategory, tenant_id, f"{prefix}-قطع محرك"),
                _ensure_category(db, ProductCategory, tenant_id, f"{prefix}-كهرباء"),
                _ensure_category(db, ProductCategory, tenant_id, f"{prefix}-سوائل"),
                _ensure_category(db, ProductCategory, tenant_id, f"{prefix}-هيكل"),
            ]

            products = []
            for i in range(1, 26):
                products.append(_ensure_product(db, Product, tenant_id, cats[i % len(cats)], i, prefix))
            created["products"] += len(products)

            db.session.commit()

            ProductPartner.query.filter_by(tenant_id=tenant_id).delete()
            db.session.commit()

            for p in products:
                chosen = random.sample(partners, k=random.randint(1, min(3, len(partners))))
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
                            tenant_id=tenant_id,
                            product_id=p.id,
                            partner_customer_id=partner_id,
                            percentage=pct,
                        )
                    )
            db.session.commit()

            currency_choices = [tenant.default_currency, "AED", "USD", "ILS"]
            currency_choices = [c for c in currency_choices if c]

            for wh, buyer in ((wh1, manager_a), (wh2, manager_b)):
                supplier = random.choice(suppliers)
                currency = random.choice(currency_choices)
                lines = []
                for prod in random.sample(products, k=min(10, len(products))):
                    qty = Decimal(str(random.randint(10, 40)))
                    unit_cost_aed = (_d(prod.cost_price or 0) or _d("1")).quantize(_d("0.001"), rounding=ROUND_HALF_UP)
                    ex = CurrencyService.get_exchange_rate(currency, "AED", user_rate=None)
                    unit_cost = _q(unit_cost_aed / (ex or Decimal("1")))
                    lines.append({"product_id": prod.id, "quantity": qty, "unit_cost": unit_cost, "discount_percent": 0})
                PurchaseService.create_purchase(
                    user=buyer,
                    supplier_data={"supplier_id": supplier.id, "supplier_name": supplier.name},
                    lines_data=lines,
                    warehouse_id=wh.id,
                    currency=currency,
                    notes="purchase seed multi-tenant",
                )
                created["purchases"] += 1
            db.session.commit()

            exp_cats = [
                _ensure_expense_category(db, ExpenseCategory, tenant_id, f"{prefix}-إيجار", "6200"),
                _ensure_expense_category(db, ExpenseCategory, tenant_id, f"{prefix}-رواتب", "6100"),
                _ensure_expense_category(db, ExpenseCategory, tenant_id, f"{prefix}-كهرباء/ماء", "6300"),
            ]
            db.session.commit()

            def _postable_expense_account(code: str) -> str:
                acc = GLAccount.query.filter_by(code=code).first()
                if not acc:
                    return "6990"
                if getattr(acc, "is_header", False):
                    return "6990"
                return code

            for b in (b1, b2):
                b_user = manager_a if int(b.id) == int(b1.id) else manager_b
                for i in range(1, 5):
                    cat = random.choice(exp_cats)
                    currency = random.choice(currency_choices)
                    ex = CurrencyService.get_exchange_rate(currency, "AED", user_rate=None)
                    amount = _q(Decimal(str(random.randint(200, 1500))) / (ex or Decimal("1")))
                    amount_aed = _q(amount * (ex or Decimal("1")))
                    exp = Expense(
                        tenant_id=tenant_id,
                        expense_number=generate_number("E", Expense, "expense_number", branch_id=b.id),
                        category_id=cat.id,
                        description=f"{cat.name} - {b.code}",
                        description_ar=f"{cat.name} - {b.code}",
                        amount=amount,
                        currency=currency,
                        exchange_rate=ex,
                        amount_aed=amount_aed,
                        expense_date=datetime.now(timezone.utc) - timedelta(days=random.randint(0, 20)),
                        payment_method=random.choice(["cash", "bank_transfer"]),
                        reference_number="",
                        supplier_name="",
                        notes="expense seed multi-tenant",
                        status="confirmed",
                        is_active=True,
                        user_id=b_user.id,
                        branch_id=b.id,
                    )
                    db.session.add(exp)
                    db.session.flush()
                    debit_account = _postable_expense_account((cat.gl_account_code or "6990").strip())
                    credit_account = "1110" if exp.payment_method == "cash" else "1120"
                    GLService.post_entry(
                        lines=[
                            {"account": debit_account, "debit": exp.amount, "credit": 0, "description": exp.description},
                            {"account": credit_account, "debit": 0, "credit": exp.amount, "description": exp.expense_number},
                        ],
                        description=f"Expense {exp.expense_number}",
                        reference_type="expense",
                        reference_id=exp.id,
                        currency=exp.currency,
                        exchange_rate=exp.exchange_rate,
                        branch_id=exp.branch_id,
                    )
                    created["expenses"] += 1
            db.session.commit()

            for wh, seller in ((wh1, seller_a), (wh2, seller_b)):
                stock_map = get_branch_stock_map(product_ids=[p.id for p in products], warehouse_ids=[wh.id])
                available_products = [p for p in products if _d(stock_map.get(p.id, 0)) > Decimal("0")]
                if not available_products:
                    continue

                for _ in range(10):
                    customer = random.choice(regulars + merchants + partners)
                    currency = random.choice(currency_choices)
                    lines = []
                    chosen = random.sample(available_products, k=min(random.randint(1, 4), len(available_products)))
                    for prod in chosen:
                        avail = _d(stock_map.get(prod.id, 0))
                        max_qty = int(avail) if avail > 0 else 0
                        if max_qty <= 0:
                            continue
                        qty = Decimal(str(random.randint(1, min(5, max_qty))))
                        unit_price_aed = _d(prod.regular_price or 0)
                        ex = CurrencyService.get_exchange_rate(currency, "AED", user_rate=None)
                        unit_price = _q(unit_price_aed / (ex or Decimal("1")))
                        lines.append({"product": prod, "quantity": qty, "unit_price": unit_price, "discount_percent": 0})
                        stock_map[prod.id] = avail - qty
                    if not lines:
                        continue
                    pay_amount = Decimal("0")
                    if random.random() < 0.35:
                        pay_amount = _q(sum((_d(l["unit_price"]) * _d(l["quantity"]) for l in lines), Decimal("0")) * _d("0.4"))
                    try:
                        SaleService.create_sale(
                            customer=customer,
                            seller=seller,
                            lines_data=lines,
                            warehouse_id=wh.id,
                            currency=currency,
                            notes="sale seed multi-tenant",
                            payment_data={
                                "amount": pay_amount,
                                "payment_method": "cash",
                                "currency": currency,
                                "exchange_rate": CurrencyService.get_exchange_rate(currency, "AED", user_rate=None),
                            }
                            if pay_amount > 0
                            else {"amount": 0},
                        )
                        created["sales"] += 1
                    except Exception:
                        db.session.rollback()
                db.session.commit()

            def _unique_cheque_number(prefix: str, base: str) -> str:
                n = 0
                num = f"{prefix}{base}"
                while Cheque.query.filter_by(cheque_number=num).first():
                    n += 1
                    num = f"{prefix}{base}-{n}"
                return num

            for b in (b1, b2):
                b_user = manager_a if int(b.id) == int(b1.id) else manager_b
                outgoing_partner = random.choice(partners)
                incoming_customer = random.choice(regulars)
                base_num = f"{b.code}-{datetime.now().strftime('%y%m%d%H%M%S')}-{random.randint(1000,9999)}"

                fx_currency = random.choice([c for c in currency_choices if c != "AED"] or ["AED"])
                issue_ex = CurrencyService.get_exchange_rate(fx_currency, "AED", user_rate=None)
                clear_ex = _q(issue_ex * Decimal(str(random.choice([0.97, 1.03]))))

                ch_out = Cheque(
                    tenant_id=tenant_id,
                    cheque_number=_unique_cheque_number("CH-OUT-", base_num),
                    cheque_bank_number=f"BNK-{random.randint(100000,999999)}",
                    cheque_type="outgoing",
                    bank_name="Local Bank",
                    amount=_q(Decimal(str(random.randint(300, 1500))) / (issue_ex or Decimal("1"))),
                    currency=fx_currency,
                    exchange_rate=issue_ex,
                    issue_date=datetime.now().date(),
                    due_date=(datetime.now() + timedelta(days=7)).date(),
                    status="pending",
                    payee_name=outgoing_partner.name,
                    customer_id=outgoing_partner.id,
                    branch_id=b.id,
                    user_id=b_user.id,
                    is_active=True,
                )
                ch_out.calculate_amount_aed()
                db.session.add(ch_out)
                db.session.flush()
                ch_out.issue_cheque()
                ch_out.deposit_cheque()
                ch_out.clear_cheque(clearance_exchange_rate=clear_ex if fx_currency != "AED" else None)
                created["cheques"] += 1

                ch_in = Cheque(
                    tenant_id=tenant_id,
                    cheque_number=_unique_cheque_number("CH-IN-", base_num),
                    cheque_bank_number=f"BNK-{random.randint(100000,999999)}",
                    cheque_type="incoming",
                    bank_name="Local Bank",
                    amount=_q(Decimal(str(random.randint(500, 2500))) / (issue_ex or Decimal("1"))),
                    currency=fx_currency,
                    exchange_rate=issue_ex,
                    issue_date=datetime.now().date(),
                    due_date=(datetime.now() + timedelta(days=10)).date(),
                    status="pending",
                    drawer_name=incoming_customer.name,
                    customer_id=incoming_customer.id,
                    branch_id=b.id,
                    user_id=b_user.id,
                    is_active=True,
                )
                ch_in.calculate_amount_aed()
                db.session.add(ch_in)
                db.session.flush()
                ch_in.receive_cheque()
                ch_in.deposit_cheque()
                ch_in.clear_cheque(clearance_exchange_rate=clear_ex if fx_currency != "AED" else None)
                created["cheques"] += 1

                db.session.commit()

                if random.random() < 0.5:
                    receipt_data = {
                        "customer_id": incoming_customer.id,
                        "amount": float(_q(Decimal("200") / (issue_ex or Decimal("1")))),
                        "currency": fx_currency,
                        "payment_method": "cash",
                        "notes": "receipt seed multi-tenant",
                        "branch_id": b.id,
                    }
                    r = PaymentService.create_receipt(receipt_data)
                    created["receipts"] += 1
                    db.session.commit()

        print("OPS_SIM_MULTI_OK")
        for k in sorted(created.keys()):
            print(f"{k.upper()}={created[k]}")


if __name__ == "__main__":
    main()

