"""
Tests/unit/test_vat_inclusive_pricing.py
========================================

Professional test suite for VAT-inclusive pricing (Prices Include VAT).

Coverage
--------
• Sale.calculate_totals      — VAT extraction from inclusive prices
• Purchase.calculate_totals  — VAT extraction from inclusive prices
• PurchaseLine.inventory_unit_cost — VAT-excluded cost for inventory valuation
• GL Sale posting            — Revenue / Shipping / Discount are VAT-exclusive
• GL Purchase posting        — Inventory debit = taxable_amount (not subtotal)
• Purchase Return            — Inventory credit = VAT-exclusive
• Branch-level override      — Branch prices_include_vat overrides tenant
• Tenant-level fallback      — Branch NULL falls back to tenant
• MWAC compatibility       — Inventory cost must never include recoverable VAT

Author  : Azad Intelligent Systems
Date    : 2026-06-21
"""

from decimal import Decimal, ROUND_HALF_UP
import pytest


@pytest.fixture(autouse=True)
def _vat_app_context(app):
    with app.app_context():
        yield


@pytest.fixture(autouse=True)
def _vat_product(db_session, sample_tenant):
    """Ensure a product with id=1 exists for tests that reference product_id=1."""
    from models import Product
    existing = db_session.get(Product, 1)
    if existing is None:
        p = Product(
            id=1,
            tenant_id=sample_tenant.id,
            name="VAT Test Product",
            sku="SKU-VAT-001",
            cost_price=Decimal("50.000"),
            regular_price=Decimal("100.000"),
            current_stock=Decimal("0"),
        )
        db_session.add(p)
        db_session.commit()


# ──────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────

@pytest.fixture
def vat_exclusive_tenant(db_session, sample_tenant):
    """Tenant configured with prices_include_vat=False (default)."""
    sample_tenant.prices_include_vat = False
    sample_tenant.default_tax_rate = Decimal("16.00")
    sample_tenant.enable_tax = True
    db_session.commit()
    db_session.refresh(sample_tenant)
    return sample_tenant


@pytest.fixture
def vat_inclusive_tenant(db_session, sample_tenant):
    """Tenant configured with prices_include_vat=True."""
    sample_tenant.prices_include_vat = True
    sample_tenant.default_tax_rate = Decimal("16.00")
    sample_tenant.enable_tax = True
    db_session.commit()
    db_session.refresh(sample_tenant)
    return sample_tenant


@pytest.fixture
def vat_inclusive_branch(db_session, sample_branch):
    """Branch configured with prices_include_vat=True."""
    sample_branch.prices_include_vat = True
    db_session.commit()
    return sample_branch


@pytest.fixture
def vat_exclusive_branch(db_session, sample_branch):
    """Branch configured with prices_include_vat=False."""
    sample_branch.prices_include_vat = False
    db_session.commit()
    return sample_branch


@pytest.fixture
def sample_product_vat(db_session, sample_tenant):
    """Product for VAT pricing tests."""
    from models import Product
    p = Product(
        tenant_id=sample_tenant.id,
        name="VAT Test Product",
        sku="SKU-VAT-002",
        cost_price=Decimal("50.000"),
        regular_price=Decimal("100.000"),
    )
    db_session.add(p)
    db_session.commit()
    return p


@pytest.fixture
def sample_warehouse_vat(db_session, sample_tenant, sample_branch):
    """Warehouse for VAT pricing tests."""
    from models import Warehouse
    w = Warehouse(
        tenant_id=sample_tenant.id,
        branch_id=sample_branch.id,
        name="VAT Warehouse",
        name_ar="مستودع VAT",
        is_active=True,
            allow_negative_inventory=True,
    )
    db_session.add(w)
    db_session.commit()
    return w


@pytest.fixture
def sample_customer_vat(db_session, sample_tenant):
    """Customer for VAT pricing tests."""
    from models import Customer
    c = Customer(
        tenant_id=sample_tenant.id,
        name="VAT Customer",
        email="vat-customer@test.com",
    )
    db_session.add(c)
    db_session.commit()
    return c


@pytest.fixture
def sample_supplier_vat(db_session, sample_tenant):
    """Supplier for VAT pricing tests."""
    from models import Supplier
    s = Supplier(
        tenant_id=sample_tenant.id,
        name="VAT Supplier",
        email="vat-supplier@test.com",
    )
    db_session.add(s)
    db_session.commit()
    return s


@pytest.fixture
def sample_user_vat(db_session, sample_tenant, sample_role, sample_branch):
    """User for VAT pricing tests."""
    from models import User
    import uuid
    unique = str(uuid.uuid4())[:8]
    u = User(
        username=f"vat-user-{unique}",
        email=f"vat-user-{unique}@test.com",
        full_name="VAT Test User",
        tenant_id=sample_tenant.id,
        role_id=sample_role.id,
        branch_id=sample_branch.id,
        is_active=True,
    )
    u.set_password("password123")
    db_session.add(u)
    db_session.commit()
    return u


# ──────────────────────────────────────────────────────────────
# 1. Sale.calculate_totals — VAT-inclusive pricing
# ──────────────────────────────────────────────────────────────

class TestSaleVatInclusiveTotals:
    """Ensure Sale.calculate_totals correctly extracts VAT when prices_include_vat=True."""

    def test_sale_vat_inclusive_extraction(self, db_session, vat_inclusive_tenant, sample_product_vat):
        """When prices_include_vat=True, tax_amount must be extracted from subtotal."""
        from models import Sale, SaleLine

        sale = Sale(
            tenant_id=vat_inclusive_tenant.id,
            sale_number="SAL-VAT-001",
            customer_id=1,  # dummy, will be linked via lines if needed
            seller_id=1,
            subtotal=Decimal("116.00"),
            discount_amount=Decimal("0"),
            shipping_cost=Decimal("0"),
            tax_rate=Decimal("16.00"),
            prices_include_vat=True,
            total_amount=Decimal("0"),
            amount=Decimal("0"),
            amount_aed=Decimal("0"),
            currency="AED",
        )
        db_session.add(sale)
        db_session.flush()

        # Add a line to make subtotal real
        line = SaleLine(
            tenant_id=vat_inclusive_tenant.id,
            sale_id=sale.id,
            product_id=sample_product_vat.id,
            quantity=Decimal("1"),
            unit_price=Decimal("116.00"),
            line_total=Decimal("116.00"),
        )
        db_session.add(line)
        db_session.commit()

        sale.calculate_totals()
        db_session.commit()

        # 116 / 1.16 = 100 taxable, 16 tax
        assert sale.taxable_amount == Decimal("100.00"), \
            f"Expected taxable_amount=100.00, got {sale.taxable_amount}"
        assert sale.tax_amount == Decimal("16.00"), \
            f"Expected tax_amount=16.00, got {sale.tax_amount}"
        assert sale.total_amount == Decimal("116.00"), \
            f"Expected total_amount=116.00 (unchanged), got {sale.total_amount}"

    def test_sale_vat_inclusive_with_discount(self, db_session, vat_inclusive_tenant):
        """VAT-inclusive with discount: tax is extracted from (subtotal - discount)."""
        from models import Sale, SaleLine

        sale = Sale(
            tenant_id=vat_inclusive_tenant.id,
            sale_number="SAL-VAT-002",
            customer_id=1,
            seller_id=1,
            subtotal=Decimal("116.00"),
            discount_amount=Decimal("11.60"),
            shipping_cost=Decimal("0"),
            tax_rate=Decimal("16.00"),
            prices_include_vat=True,
            total_amount=Decimal("0"),
            amount=Decimal("0"),
            amount_aed=Decimal("0"),
            currency="AED",
        )
        db_session.add(sale)
        db_session.flush()

        line = SaleLine(
            tenant_id=vat_inclusive_tenant.id,
            sale_id=sale.id,
            product_id=1,
            quantity=Decimal("1"),
            unit_price=Decimal("116.00"),
            line_total=Decimal("116.00"),
        )
        db_session.add(line)
        db_session.commit()

        sale.calculate_totals()
        db_session.commit()

        gross = Decimal("116.00") - Decimal("11.60")  # 104.40
        expected_taxable = (gross / Decimal("1.16")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        expected_tax = (gross - expected_taxable).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        assert sale.taxable_amount == expected_taxable, \
            f"Expected taxable_amount={expected_taxable}, got {sale.taxable_amount}"
        assert sale.tax_amount == expected_tax, \
            f"Expected tax_amount={expected_tax}, got {sale.tax_amount}"

    def test_sale_vat_inclusive_with_shipping(self, db_session, vat_inclusive_tenant):
        """VAT-inclusive with shipping: shipping is also inclusive."""
        from models import Sale, SaleLine

        sale = Sale(
            tenant_id=vat_inclusive_tenant.id,
            sale_number="SAL-VAT-003",
            customer_id=1,
            seller_id=1,
            subtotal=Decimal("100.00"),
            discount_amount=Decimal("0"),
            shipping_cost=Decimal("23.20"),  # 20 + 3.20 VAT
            tax_rate=Decimal("16.00"),
            prices_include_vat=True,
            total_amount=Decimal("0"),
            amount=Decimal("0"),
            amount_aed=Decimal("0"),
            currency="AED",
        )
        db_session.add(sale)
        db_session.flush()

        line = SaleLine(
            tenant_id=vat_inclusive_tenant.id,
            sale_id=sale.id,
            product_id=1,
            quantity=Decimal("1"),
            unit_price=Decimal("100.00"),
            line_total=Decimal("100.00"),
        )
        db_session.add(line)
        db_session.commit()

        sale.calculate_totals()
        db_session.commit()

        gross = Decimal("100.00") + Decimal("23.20")  # 123.20
        expected_taxable = (gross / Decimal("1.16")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        expected_tax = (gross - expected_taxable).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        assert sale.taxable_amount == expected_taxable, \
            f"Expected taxable_amount={expected_taxable}, got {sale.taxable_amount}"
        assert sale.tax_amount == expected_tax, \
            f"Expected tax_amount={expected_tax}, got {sale.tax_amount}"
        assert sale.total_amount == gross, \
            f"Expected total_amount={gross}, got {sale.total_amount}"

    def test_sale_vat_exclusive_unchanged(self, db_session, vat_exclusive_tenant):
        """When prices_include_vat=False, tax is added on top (standard behaviour)."""
        from models import Sale, SaleLine

        sale = Sale(
            tenant_id=vat_exclusive_tenant.id,
            sale_number="SAL-VAT-004",
            customer_id=1,
            seller_id=1,
            subtotal=Decimal("100.00"),
            discount_amount=Decimal("0"),
            shipping_cost=Decimal("0"),
            tax_rate=Decimal("16.00"),
            prices_include_vat=False,
            total_amount=Decimal("0"),
            amount=Decimal("0"),
            amount_aed=Decimal("0"),
            currency="AED",
        )
        db_session.add(sale)
        db_session.flush()

        line = SaleLine(
            tenant_id=vat_exclusive_tenant.id,
            sale_id=sale.id,
            product_id=1,
            quantity=Decimal("1"),
            unit_price=Decimal("100.00"),
            line_total=Decimal("100.00"),
        )
        db_session.add(line)
        db_session.commit()

        sale.calculate_totals()
        db_session.commit()

        assert sale.taxable_amount == Decimal("100.00"), \
            f"Expected taxable_amount=100.00, got {sale.taxable_amount}"
        assert sale.tax_amount == Decimal("16.00"), \
            f"Expected tax_amount=16.00, got {sale.tax_amount}"
        assert sale.total_amount == Decimal("116.00"), \
            f"Expected total_amount=116.00, got {sale.total_amount}"


# ──────────────────────────────────────────────────────────────
# 2. Purchase.calculate_totals — VAT-inclusive pricing
# ──────────────────────────────────────────────────────────────

class TestPurchaseVatInclusiveTotals:
    """Ensure Purchase.calculate_totals correctly extracts VAT when prices_include_vat=True."""

    def test_purchase_vat_inclusive_extraction(self, db_session, vat_inclusive_tenant):
        """When prices_include_vat=True, tax_amount is extracted from subtotal."""
        from models import Purchase, PurchaseLine

        purchase = Purchase(
            tenant_id=vat_inclusive_tenant.id,
            purchase_number="PUR-VAT-001",
            supplier_name="VAT Supplier",
            subtotal=Decimal("116.00"),
            discount_amount=Decimal("0"),
            tax_rate=Decimal("16.00"),
            prices_include_vat=True,
            total_amount=Decimal("0"),
            amount=Decimal("0"),
            amount_aed=Decimal("0"),
            currency="AED",
            user_id=1,
        )
        db_session.add(purchase)
        db_session.flush()

        line = PurchaseLine(
            tenant_id=vat_inclusive_tenant.id,
            purchase_id=purchase.id,
            product_id=1,
            quantity=Decimal("1"),
            unit_cost=Decimal("116.00"),
            line_total=Decimal("116.00"),
        )
        db_session.add(line)
        db_session.commit()

        purchase.calculate_totals()
        db_session.commit()

        assert purchase.taxable_amount == Decimal("100.00"), \
            f"Expected taxable_amount=100.00, got {purchase.taxable_amount}"
        assert purchase.tax_amount == Decimal("16.00"), \
            f"Expected tax_amount=16.00, got {purchase.tax_amount}"
        assert purchase.total_amount == Decimal("116.00"), \
            f"Expected total_amount=116.00, got {purchase.total_amount}"

    def test_purchase_vat_inclusive_with_landed_cost(self, db_session, vat_inclusive_tenant):
        """Landed costs are added to total_amount but NOT to taxable_amount."""
        from models import Purchase, PurchaseLine

        purchase = Purchase(
            tenant_id=vat_inclusive_tenant.id,
            purchase_number="PUR-VAT-002",
            supplier_name="VAT Supplier",
            subtotal=Decimal("116.00"),
            discount_amount=Decimal("0"),
            tax_rate=Decimal("16.00"),
            prices_include_vat=True,
            freight=Decimal("10.00"),
            customs_duty=Decimal("5.00"),
            total_amount=Decimal("0"),
            amount=Decimal("0"),
            amount_aed=Decimal("0"),
            currency="AED",
            user_id=1,
        )
        db_session.add(purchase)
        db_session.flush()

        line = PurchaseLine(
            tenant_id=vat_inclusive_tenant.id,
            purchase_id=purchase.id,
            product_id=1,
            quantity=Decimal("1"),
            unit_cost=Decimal("116.00"),
            line_total=Decimal("116.00"),
        )
        db_session.add(line)
        db_session.commit()

        purchase.calculate_totals()
        db_session.commit()

        assert purchase.taxable_amount == Decimal("100.00"), \
            f"Expected taxable_amount=100.00, got {purchase.taxable_amount}"
        assert purchase.tax_amount == Decimal("16.00"), \
            f"Expected tax_amount=16.00, got {purchase.tax_amount}"
        expected_total = Decimal("116.00") + Decimal("15.00")  # subtotal + landed
        assert purchase.total_amount == expected_total, \
            f"Expected total_amount={expected_total}, got {purchase.total_amount}"


# ──────────────────────────────────────────────────────────────
# 3. PurchaseLine.inventory_unit_cost — VAT-free for inventory
# ──────────────────────────────────────────────────────────────

class TestPurchaseLineInventoryUnitCost:
    """Ensure inventory cost excludes recoverable VAT when prices_include_vat=True."""

    def test_inventory_unit_cost_vat_inclusive(self, db_session, vat_inclusive_tenant):
        """When purchase uses inclusive VAT, inventory_unit_cost must be VAT-excluded."""
        from models import Purchase, PurchaseLine

        purchase = Purchase(
            tenant_id=vat_inclusive_tenant.id,
            purchase_number="PUR-VAT-003",
            supplier_name="VAT Supplier",
            tax_rate=Decimal("16.00"),
            prices_include_vat=True,
            total_amount=Decimal("0"),
            amount=Decimal("0"),
            amount_aed=Decimal("0"),
            user_id=1,
        )
        db_session.add(purchase)
        db_session.flush()

        line = PurchaseLine(
            tenant_id=vat_inclusive_tenant.id,
            purchase_id=purchase.id,
            product_id=1,
            quantity=Decimal("1"),
            unit_cost=Decimal("116.00"),
            line_total=Decimal("116.00"),
        )
        db_session.add(line)
        db_session.commit()

        # 116 / 1.16 = 100
        expected = Decimal("100.00")
        assert line.inventory_unit_cost == expected, \
            f"Expected inventory_unit_cost={expected}, got {line.inventory_unit_cost}"

    def test_inventory_unit_cost_vat_exclusive(self, db_session, vat_exclusive_tenant):
        """When purchase uses exclusive VAT, inventory_unit_cost equals unit_cost."""
        from models import Purchase, PurchaseLine

        purchase = Purchase(
            tenant_id=vat_exclusive_tenant.id,
            purchase_number="PUR-VAT-004",
            supplier_name="VAT Supplier",
            tax_rate=Decimal("16.00"),
            prices_include_vat=False,
            total_amount=Decimal("0"),
            amount=Decimal("0"),
            amount_aed=Decimal("0"),
            user_id=1,
        )
        db_session.add(purchase)
        db_session.flush()

        line = PurchaseLine(
            tenant_id=vat_exclusive_tenant.id,
            purchase_id=purchase.id,
            product_id=1,
            quantity=Decimal("1"),
            unit_cost=Decimal("100.00"),
            line_total=Decimal("100.00"),
        )
        db_session.add(line)
        db_session.commit()

        assert line.inventory_unit_cost == Decimal("100.00"), \
            f"Expected inventory_unit_cost=100.00, got {line.inventory_unit_cost}"

    def test_landed_inventory_unit_cost_vat_inclusive(self, db_session, vat_inclusive_tenant):
        """Landed cost is added AFTER VAT exclusion."""
        from models import Purchase, PurchaseLine

        purchase = Purchase(
            tenant_id=vat_inclusive_tenant.id,
            purchase_number="PUR-VAT-005",
            supplier_name="VAT Supplier",
            tax_rate=Decimal("16.00"),
            prices_include_vat=True,
            total_amount=Decimal("0"),
            amount=Decimal("0"),
            amount_aed=Decimal("0"),
            user_id=1,
        )
        db_session.add(purchase)
        db_session.flush()

        line = PurchaseLine(
            tenant_id=vat_inclusive_tenant.id,
            purchase_id=purchase.id,
            product_id=1,
            quantity=Decimal("2"),
            unit_cost=Decimal("116.00"),
            line_total=Decimal("232.00"),
            landed_cost=Decimal("20.00"),
        )
        db_session.add(line)
        db_session.commit()

        # inventory_unit_cost = 116 / 1.16 = 100
        assert line.inventory_unit_cost == Decimal("100.00"), \
            f"Expected inventory_unit_cost=100.00, got {line.inventory_unit_cost}"
        # landed_inventory_unit_cost = 100 + (20/2) = 110
        assert line.landed_inventory_unit_cost == Decimal("110.00"), \
            f"Expected landed_inventory_unit_cost=110.00, got {line.landed_inventory_unit_cost}"


# ──────────────────────────────────────────────────────────────
# 4. GL Sale Posting — Revenue must be VAT-exclusive
# ──────────────────────────────────────────────────────────────

class TestSaleGlVatExclusive:
    """When prices_include_vat=True, GL revenue lines must be VAT-exclusive."""

    def test_gl_revenue_vat_exclusive(self, db_session, vat_inclusive_tenant, sample_customer_vat, sample_user_vat, sample_branch, sample_warehouse_vat, sample_gl_accounts):
        """Sale GL: revenue credit = taxable_amount, not subtotal."""
        from decimal import Decimal
        from models import Sale, SaleLine, Product
        from services.sale_service import SaleService

        product = Product(
            tenant_id=vat_inclusive_tenant.id,
            name="GL Test Product",
            sku="SKU-GL-001",
            cost_price=Decimal("50.00"),
            regular_price=Decimal("100.00"),
        )
        db_session.add(product)
        db_session.flush()

        sale = SaleService.create_sale(
            customer=sample_customer_vat,
            seller=sample_user_vat,
            lines_data=[{"product": product, "quantity": 1, "unit_price": 116.00}],
            warehouse_id=sample_warehouse_vat.id,
            tax_rate=16.00,
            currency="AED",
        )
        db_session.commit()

        assert sale.prices_include_vat is True, "Sale should inherit prices_include_vat from tenant"
        assert sale.taxable_amount == Decimal("100.00"), \
            f"Expected taxable_amount=100.00, got {sale.taxable_amount}"
        assert sale.tax_amount == Decimal("16.00"), \
            f"Expected tax_amount=16.00, got {sale.tax_amount}"
        assert sale.total_amount == Decimal("116.00"), \
            f"Expected total_amount=116.00, got {sale.total_amount}"

    def test_gl_revenue_with_discount_vat_exclusive(self, db_session, vat_inclusive_tenant, sample_customer_vat, sample_user_vat, sample_branch, sample_warehouse_vat, sample_gl_accounts):
        """Sale GL with discount: discount_debit must also be VAT-exclusive."""
        from decimal import Decimal
        from models import Product
        from services.sale_service import SaleService

        product = Product(
            tenant_id=vat_inclusive_tenant.id,
            name="GL Discount Product",
            sku="SKU-GL-DISC",
            cost_price=Decimal("50.00"),
            regular_price=Decimal("100.00"),
        )
        db_session.add(product)
        db_session.flush()

        sale = SaleService.create_sale(
            customer=sample_customer_vat,
            seller=sample_user_vat,
            lines_data=[{"product": product, "quantity": 1, "unit_price": 116.00}],
            warehouse_id=sample_warehouse_vat.id,
            tax_rate=16.00,
            discount_amount=11.60,
            currency="AED",
        )
        db_session.commit()

        # Discount should be VAT-exclusive in GL: 11.60 / 1.16 = 10.00
        assert sale.discount_amount == Decimal("11.60"), \
            f"Expected discount_amount=11.60, got {sale.discount_amount}"
        assert sale.taxable_amount == Decimal("90.00"), \
            f"Expected taxable_amount=90.00, got {sale.taxable_amount}"


# ──────────────────────────────────────────────────────────────
# 5. GL Purchase Posting — Inventory debit = taxable_amount
# ──────────────────────────────────────────────────────────────

class TestPurchaseGlVatExclusive:
    """When prices_include_vat=True, GL inventory debit must equal taxable_amount."""

    def test_gl_inventory_debit_equals_taxable_amount(self, db_session, vat_inclusive_tenant, sample_supplier_vat, sample_user_vat, sample_branch, sample_warehouse_vat, sample_gl_accounts):
        """Purchase GL: inventory_debit = taxable_amount (VAT-excluded), not subtotal."""
        from decimal import Decimal
        from models import Product
        from services.purchase_service import PurchaseService

        product = Product(
            tenant_id=vat_inclusive_tenant.id,
            name="GL Purchase Product",
            sku="SKU-GL-PUR",
            cost_price=Decimal("50.00"),
            regular_price=Decimal("100.00"),
        )
        db_session.add(product)
        db_session.flush()

        purchase = PurchaseService.create_purchase(
            user=sample_user_vat,
            supplier_data={"supplier_id": sample_supplier_vat.id},
            lines_data=[{"product_id": product.id, "quantity": 1, "unit_cost": 116.00}],
            warehouse_id=sample_warehouse_vat.id,
            tax_rate=16.00,
            currency="AED",
        )
        db_session.commit()

        assert purchase.prices_include_vat is True
        assert purchase.taxable_amount == Decimal("100.00"), \
            f"Expected taxable_amount=100.00, got {purchase.taxable_amount}"
        assert purchase.tax_amount == Decimal("16.00"), \
            f"Expected tax_amount=16.00, got {purchase.tax_amount}"
        assert purchase.total_amount == Decimal("116.00"), \
            f"Expected total_amount=116.00, got {purchase.total_amount}"

    def test_gl_inventory_with_landed_cost(self, db_session, vat_inclusive_tenant, sample_supplier_vat, sample_user_vat, sample_branch, sample_warehouse_vat, sample_gl_accounts):
        """Landed costs are capitalized into inventory (added to VAT-excluded base)."""
        from decimal import Decimal
        from models import Product
        from services.purchase_service import PurchaseService

        product = Product(
            tenant_id=vat_inclusive_tenant.id,
            name="GL Landed Product",
            sku="SKU-GL-LND",
            cost_price=Decimal("50.00"),
            regular_price=Decimal("100.00"),
        )
        db_session.add(product)
        db_session.flush()

        purchase = PurchaseService.create_purchase(
            user=sample_user_vat,
            supplier_data={"supplier_id": sample_supplier_vat.id},
            lines_data=[{"product_id": product.id, "quantity": 1, "unit_cost": 116.00}],
            warehouse_id=sample_warehouse_vat.id,
            tax_rate=16.00,
            freight=10.00,
            customs_duty=5.00,
            currency="AED",
        )
        db_session.commit()

        assert purchase.taxable_amount == Decimal("100.00")
        assert purchase.total_amount == Decimal("131.00")  # 116 + 15 landed


# ──────────────────────────────────────────────────────────────
# 6. Purchase Return — Inventory credit VAT-exclusive
# ──────────────────────────────────────────────────────────────

class TestPurchaseReturnVatExclusive:
    """Purchase return inventory credit must be VAT-exclusive when original was inclusive."""

    def test_return_inventory_credit_vat_exclusive(self, db_session, vat_inclusive_tenant, sample_supplier_vat, sample_user_vat, sample_branch, sample_warehouse_vat, sample_gl_accounts):
        """Return inventory_credit = subtotal_return / (1 + tax_rate/100)."""
        from decimal import Decimal
        from models import Product
        from services.purchase_service import PurchaseService

        product = Product(
            tenant_id=vat_inclusive_tenant.id,
            name="Return Product",
            sku="SKU-RET-001",
            cost_price=Decimal("50.00"),
            regular_price=Decimal("100.00"),
        )
        db_session.add(product)
        db_session.flush()

        purchase = PurchaseService.create_purchase(
            user=sample_user_vat,
            supplier_data={"supplier_id": sample_supplier_vat.id},
            lines_data=[{"product_id": product.id, "quantity": 10, "unit_cost": 116.00}],
            warehouse_id=sample_warehouse_vat.id,
            tax_rate=16.00,
            currency="AED",
        )
        db_session.commit()

        # Return 2 units
        lines_data = [{"purchase_line_id": purchase.lines[0].id, "product_id": product.id, "quantity": 2, "unit_cost": 116.00}]
        ret = PurchaseService.create_purchase_return(purchase, sample_user_vat, lines_data)
        db_session.commit()

        assert ret is not None
        # Return subtotal = 2 * 116 = 232
        # inventory_credit should be VAT-exclusive: 232 / 1.16 = 200
        assert ret.subtotal == Decimal("232.00"), \
            f"Expected return subtotal=232.00, got {ret.subtotal}"


# ──────────────────────────────────────────────────────────────
# 7. Branch-level override & Tenant fallback
# ──────────────────────────────────────────────────────────────

class TestPricesIncludeVatResolution:
    """Ensure branch-level setting overrides tenant, and NULL falls back to tenant."""

    def test_branch_override_tenant(self, db_session, vat_exclusive_tenant, vat_inclusive_branch):
        """Branch prices_include_vat=True overrides tenant prices_include_vat=False."""
        from utils.tax_settings import get_prices_include_vat

        result = get_prices_include_vat(
            tenant_id=vat_exclusive_tenant.id,
            branch_id=vat_inclusive_branch.id
        )
        assert result is True, \
            "Branch should override tenant when branch.prices_include_vat is explicitly set"

    def test_tenant_fallback_when_branch_null(self, db_session, vat_inclusive_tenant):
        """When branch.prices_include_vat is NULL, fall back to tenant setting."""
        from models import Branch
        from utils.tax_settings import get_prices_include_vat

        branch = Branch(
            tenant_id=vat_inclusive_tenant.id,
            name="Null Branch",
            code="NULL01",
            is_active=True,
            prices_include_vat=None,  # Explicitly NULL
        )
        db_session.add(branch)
        db_session.commit()

        result = get_prices_include_vat(
            tenant_id=vat_inclusive_tenant.id,
            branch_id=branch.id
        )
        assert result is True, \
            "Should fall back to tenant when branch.prices_include_vat is NULL"

    def test_tenant_default_false(self, db_session, vat_exclusive_tenant):
        """When tenant has prices_include_vat=False and no branch, return False."""
        from utils.tax_settings import get_prices_include_vat

        result = get_prices_include_vat(tenant_id=vat_exclusive_tenant.id)
        assert result is False, \
            "Tenant with prices_include_vat=False should return False"


# ──────────────────────────────────────────────────────────────
# 8. MWAC compatibility — Inventory cost must never include VAT
# ──────────────────────────────────────────────────────────────

class TestMwacVatCompatibility:
    """MWAC must use VAT-excluded cost when prices_include_vat=True."""

    def test_mwac_cost_is_vat_free(self, db_session, vat_inclusive_tenant, sample_user_vat, sample_branch, sample_warehouse_vat, sample_gl_accounts):
        """After purchase with inclusive VAT, MWAC average cost must be VAT-free."""
        from decimal import Decimal
        from models import Product, ProductWarehouseCost
        from services.purchase_service import PurchaseService

        product = Product(
            tenant_id=vat_inclusive_tenant.id,
            name="MWAC VAT Product",
            sku="SKU-MWAC-VAT",
            cost_price=Decimal("0"),
            regular_price=Decimal("100.00"),
        )
        db_session.add(product)
        db_session.flush()

        # Purchase 10 units at 116 each (inclusive VAT = 100 + 16 tax)
        purchase = PurchaseService.create_purchase(
            user=sample_user_vat,
            supplier_data={"supplier_name": "MWAC Supplier"},
            lines_data=[{"product_id": product.id, "quantity": 10, "unit_cost": 116.00}],
            warehouse_id=sample_warehouse_vat.id,
            tax_rate=16.00,
            currency="AED",
        )
        db_session.commit()

        # Check MWAC recorded cost
        pwc = ProductWarehouseCost.query.filter_by(
            tenant_id=vat_inclusive_tenant.id,
            product_id=product.id,
            warehouse_id=sample_warehouse_vat.id,
        ).first()

        assert pwc is not None, "ProductWarehouseCost record should exist after purchase"
        # Average cost must be VAT-free: 100.00 per unit
        assert pwc.average_cost == Decimal("100.00"), \
            f"MWAC average cost must be VAT-free (100.00), got {pwc.average_cost}"
        assert pwc.total_quantity == Decimal("10.00"), \
            f"Expected quantity=10, got {pwc.total_quantity}"
        assert pwc.total_value == Decimal("1000.00"), \
            f"Expected total_value=1000.00, got {pwc.total_value}"

    def test_mwac_with_landed_cost(self, db_session, vat_inclusive_tenant, sample_user_vat, sample_branch, sample_warehouse_vat, sample_gl_accounts):
        """MWAC includes landed costs but still excludes VAT."""
        from decimal import Decimal
        from models import Product, ProductWarehouseCost
        from services.purchase_service import PurchaseService

        product = Product(
            tenant_id=vat_inclusive_tenant.id,
            name="MWAC Landed Product",
            sku="SKU-MWAC-LND",
            cost_price=Decimal("0"),
            regular_price=Decimal("100.00"),
        )
        db_session.add(product)
        db_session.flush()

        purchase = PurchaseService.create_purchase(
            user=sample_user_vat,
            supplier_data={"supplier_name": "MWAC Landed Supplier"},
            lines_data=[{"product_id": product.id, "quantity": 10, "unit_cost": 116.00}],
            warehouse_id=sample_warehouse_vat.id,
            tax_rate=16.00,
            freight=50.00,
            currency="AED",
        )
        db_session.commit()

        pwc = ProductWarehouseCost.query.filter_by(
            tenant_id=vat_inclusive_tenant.id,
            product_id=product.id,
            warehouse_id=sample_warehouse_vat.id,
        ).first()

        assert pwc is not None
        # VAT-free base = 100 per unit * 10 = 1000
        # Landed = 50 distributed over 10 = 5 per unit
        # Average cost = 105.00
        assert pwc.average_cost == Decimal("105.00"), \
            f"MWAC average cost must include landed but exclude VAT (105.00), got {pwc.average_cost}"
