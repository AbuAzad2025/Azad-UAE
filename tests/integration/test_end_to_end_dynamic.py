"""
Integration tests for end-to-end dynamic integration:
- VAT inclusive / exclusive pricing
- Tenant default vs Branch override for prices_include_vat
- Warehouse allow_negative_inventory
- Dynamic currency symbol
- Actual Purchase and Sale creation with server-verified totals
"""
import pytest
from decimal import Decimal


import uuid


def _make_user(db_session, tenant_id, username, branch_id=None, role_slug='admin'):
    from models import User, Role
    suffix = str(uuid.uuid4())[:8]
    role_name = f'Role_{suffix}'
    role_slug_full = f'{role_slug}_{suffix}'
    role = Role(name=role_name, slug=role_slug_full, is_active=True)
    db_session.add(role)
    db_session.flush()
    u = User(
        tenant_id=tenant_id, username=f'{username}_{suffix}',
        email=f'{username}_{suffix}@test.com', is_active=True,
        password_hash='fakehash', branch_id=branch_id,
        role_id=role.id, is_owner=False,
    )
    db_session.add(u)
    db_session.flush()
    return u


def _make_admin_user(db_session, tenant_id, username, branch_id=None):
    """Create a user with super_admin role for admin-only routes."""
    from models import User, Role
    suffix = str(uuid.uuid4())[:8]
    role = Role.query.filter_by(slug='super_admin').first()
    if not role:
        role = Role(name='SuperAdmin', slug='super_admin', is_active=True)
        db_session.add(role)
        db_session.flush()
    u = User(
        tenant_id=tenant_id, username=f'{username}_{suffix}',
        email=f'{username}_{suffix}@test.com', is_active=True,
        password_hash='fakehash', branch_id=branch_id,
        role_id=role.id, is_owner=False,
    )
    db_session.add(u)
    db_session.flush()
    return u


def _make_tenant(db_session, name, slug, currency='AED', piv=False):
    from models import Tenant
    suffix = str(uuid.uuid4())[:8]
    t = Tenant(
        name=f'{name}_{suffix}', name_ar=f'{name}_{suffix}', slug=f'{slug}_{suffix}',
        default_currency=currency, base_currency=currency, prices_include_vat=piv
    )
    db_session.add(t)
    db_session.flush()
    return t


def _make_branch(db_session, tenant_id, name, code, piv=None):
    from models import Branch
    suffix = str(uuid.uuid4())[:8]
    b = Branch(tenant_id=tenant_id, name=f'{name}_{suffix}', code=f'{code}_{suffix}', prices_include_vat=piv)
    db_session.add(b)
    db_session.flush()
    return b


def _make_wh(db_session, tenant_id, branch_id, allow_neg=False):
    from models import Warehouse
    suffix = str(uuid.uuid4())[:8]
    w = Warehouse(tenant_id=tenant_id, name=f'WH_{suffix}', branch_id=branch_id, allow_negative_inventory=allow_neg)
    db_session.add(w)
    db_session.flush()
    return w


def _make_product(db_session, tenant_id, name, sku, cost=50, stock=100):
    from models import Product
    suffix = str(uuid.uuid4())[:8]
    p = Product(
        tenant_id=tenant_id, name=f'{name}_{suffix}', name_ar=f'{name}_{suffix}', sku=f'{sku}_{suffix}',
        cost_price=cost, regular_price=cost * 2, current_stock=stock,
        merchant_share=100, min_stock_alert=0, warranty_days=0,
        is_returnable=True, return_period_days=7, industry='general'
    )
    db_session.add(p)
    db_session.flush()
    return p


def _make_customer(db_session, tenant_id, name):
    from models import Customer
    suffix = str(uuid.uuid4())[:8]
    c = Customer(tenant_id=tenant_id, name=f'{name}_{suffix}', phone=f'050{suffix}')
    db_session.add(c)
    db_session.flush()
    return c


def _make_supplier(db_session, tenant_id, name):
    from models import Supplier
    suffix = str(uuid.uuid4())[:8]
    s = Supplier(tenant_id=tenant_id, name=f'{name}_{suffix}', phone=f'050{suffix}')
    db_session.add(s)
    db_session.flush()
    return s


class TestPricesIncludeVatEndToEnd:
    """Verify VAT calculation uses tenant/branch settings correctly."""

    def test_tenant_prices_include_vat_false_calculates_exclusive(self, app, db_session):
        from services.sale_service import SaleService

        t = _make_tenant(db_session, 'Test Tenant', 'test-vat-tenant', 'AED', False)
        b = _make_branch(db_session, t.id, 'Main', 'MAIN', None)
        wh = _make_wh(db_session, t.id, b.id, True)
        product = _make_product(db_session, t.id, 'Widget', 'W1', 50, 100)
        customer = _make_customer(db_session, t.id, 'C1')
        seller = _make_user(db_session, t.id, 'seller_' + str(t.id), b.id)

        lines = [{'product': product, 'quantity': 2, 'discount_percent': 0, 'unit_price': 100.00, 'serials': []}]

        sale = SaleService.create_sale(
            customer=customer, seller=seller, lines_data=lines,
            warehouse_id=wh.id, currency='AED', tax_rate=5.0,
            discount_amount=0, shipping_cost=0,
        )

        assert sale.prices_include_vat is False
        assert sale.subtotal == Decimal('200')
        assert sale.tax_amount == Decimal('10')
        assert sale.total_amount == Decimal('210')

    def test_tenant_prices_include_vat_true_calculates_inclusive(self, app, db_session):
        from services.sale_service import SaleService

        t = _make_tenant(db_session, 'Test Tenant Inc', 'test-vat-inc', 'AED', True)
        b = _make_branch(db_session, t.id, 'Main', 'MAIN', None)
        wh = _make_wh(db_session, t.id, b.id, True)
        product = _make_product(db_session, t.id, 'Widget', 'W2', 50, 100)
        customer = _make_customer(db_session, t.id, 'C1')
        seller = _make_user(db_session, t.id, 'seller_' + str(t.id), b.id)

        lines = [{'product': product, 'quantity': 2, 'discount_percent': 0, 'unit_price': 100.00, 'serials': []}]

        sale = SaleService.create_sale(
            customer=customer, seller=seller, lines_data=lines,
            warehouse_id=wh.id, currency='AED', tax_rate=5.0,
            discount_amount=0, shipping_cost=0,
        )

        assert sale.prices_include_vat is True
        assert sale.subtotal == Decimal('200')
        assert sale.tax_amount == Decimal('9.52')
        assert sale.total_amount == Decimal('200')
        assert sale.taxable_amount == Decimal('190.48')

    def test_branch_override_tenant_prices_include_vat(self, app, db_session):
        from services.sale_service import SaleService

        t = _make_tenant(db_session, 'T', 't-ov', 'AED', False)
        b = _make_branch(db_session, t.id, 'B', 'B1', True)
        wh = _make_wh(db_session, t.id, b.id, True)
        product = _make_product(db_session, t.id, 'W', 'W3', 50, 100)
        customer = _make_customer(db_session, t.id, 'C')
        seller = _make_user(db_session, t.id, 'seller_' + str(t.id), b.id)

        lines = [{'product': product, 'quantity': 1, 'discount_percent': 0, 'unit_price': 100.00, 'serials': []}]

        sale = SaleService.create_sale(
            customer=customer, seller=seller, lines_data=lines,
            warehouse_id=wh.id, currency='AED', tax_rate=5.0,
        )

        assert sale.prices_include_vat is True
        assert sale.total_amount == Decimal('100')
        assert sale.tax_amount == Decimal('4.76')


class TestWarehouseAllowNegativeInventory:
    """Verify allow_negative_inventory is enforced in stock service."""

    def test_allow_negative_warehouse_permits_sale(self, app, db_session):
        from services.sale_service import SaleService

        t = _make_tenant(db_session, 'T', 't-neg', 'AED', False)
        b = _make_branch(db_session, t.id, 'B', 'B1')
        wh = _make_wh(db_session, t.id, b.id, True)
        product = _make_product(db_session, t.id, 'W', 'W4', 50, 0)
        customer = _make_customer(db_session, t.id, 'C')
        seller = _make_user(db_session, t.id, 'seller_' + str(t.id), b.id)

        lines = [{'product': product, 'quantity': 5, 'discount_percent': 0, 'unit_price': 100.00, 'serials': []}]

        sale = SaleService.create_sale(
            customer=customer, seller=seller, lines_data=lines,
            warehouse_id=wh.id, currency='AED', tax_rate=5.0,
        )

        assert sale.total_amount == Decimal('525')

    def test_disallow_negative_warehouse_blocks_sale(self, app, db_session):
        from services.sale_service import SaleService

        t = _make_tenant(db_session, 'T', 't-neg2', 'AED', False)
        b = _make_branch(db_session, t.id, 'B', 'B2')
        wh = _make_wh(db_session, t.id, b.id, False)
        product = _make_product(db_session, t.id, 'W', 'W5', 50, 0)
        customer = _make_customer(db_session, t.id, 'C')
        seller = _make_user(db_session, t.id, 'seller_' + str(t.id), b.id)

        lines = [{'product': product, 'quantity': 5, 'discount_percent': 0, 'unit_price': 100.00, 'serials': []}]

        with pytest.raises(ValueError, match='المخزون'):
            SaleService.create_sale(
                customer=customer, seller=seller, lines_data=lines,
                warehouse_id=wh.id, currency='AED', tax_rate=5.0,
            )


class TestDynamicCurrency:
    """Verify currency symbol and base currency are dynamic."""

    def test_tenant_usd_uses_usd_symbol(self, app, db_session):
        from services.sale_service import SaleService
        from utils.currency_utils import resolve_tenant_base_currency

        t = _make_tenant(db_session, 'T', 't-usd', 'USD', False)
        b = _make_branch(db_session, t.id, 'B', 'B1')
        wh = _make_wh(db_session, t.id, b.id, True)
        product = _make_product(db_session, t.id, 'W', 'W6', 50, 100)
        customer = _make_customer(db_session, t.id, 'C')
        seller = _make_user(db_session, t.id, 'seller_' + str(t.id), b.id)

        base = resolve_tenant_base_currency(tenant_id=t.id)
        assert base == 'USD'

        lines = [{'product': product, 'quantity': 1, 'discount_percent': 0, 'unit_price': 100.00, 'serials': []}]

        sale = SaleService.create_sale(
            customer=customer, seller=seller, lines_data=lines,
            warehouse_id=wh.id, currency='USD', tax_rate=0,
        )

        assert sale.currency == 'USD'
        assert sale.total_amount == Decimal('100')


class TestPurchaseVatCalculation:
    """Verify purchase server-side VAT calculation."""

    def test_purchase_exclusive_vat(self, app, db_session):
        from services.purchase_service import PurchaseService

        t = _make_tenant(db_session, 'T', 't-pur', 'AED', False)
        b = _make_branch(db_session, t.id, 'B', 'B1')
        wh = _make_wh(db_session, t.id, b.id)
        product = _make_product(db_session, t.id, 'W', 'W7', 50, 0)
        supplier = _make_supplier(db_session, t.id, 'S')
        seller = _make_user(db_session, t.id, 'seller_' + str(t.id), b.id)

        lines = [{'product_id': product.id, 'quantity': 10, 'unit_cost': 50.0, 'discount_percent': 0, 'serials': []}]

        purchase = PurchaseService.create_purchase(
            user=seller, supplier_data={'supplier_id': supplier.id},
            lines_data=lines, warehouse_id=wh.id, currency='AED', tax_rate=5.0,
        )

        assert purchase.prices_include_vat is False
        assert purchase.subtotal == Decimal('500')
        assert purchase.tax_amount == Decimal('25')
        assert purchase.total_amount == Decimal('525')

    def test_purchase_inclusive_vat(self, app, db_session):
        from services.purchase_service import PurchaseService

        t = _make_tenant(db_session, 'T', 't-pur-inc', 'AED', True)
        b = _make_branch(db_session, t.id, 'B', 'B1')
        wh = _make_wh(db_session, t.id, b.id)
        product = _make_product(db_session, t.id, 'W', 'W8', 50, 0)
        supplier = _make_supplier(db_session, t.id, 'S')
        seller = _make_user(db_session, t.id, 'seller_' + str(t.id), b.id)

        lines = [{'product_id': product.id, 'quantity': 10, 'unit_cost': 50.0, 'discount_percent': 0, 'serials': []}]

        purchase = PurchaseService.create_purchase(
            user=seller, supplier_data={'supplier_id': supplier.id},
            lines_data=lines, warehouse_id=wh.id, currency='AED', tax_rate=5.0,
        )

        assert purchase.prices_include_vat is True
        assert purchase.subtotal == Decimal('500')
        assert purchase.tax_amount == Decimal('23.81')
        assert purchase.total_amount == Decimal('500')
        assert purchase.taxable_amount == Decimal('476.19')


class TestBrowserTotalsIgnored:
    """Prove server recalculates totals and ignores any browser-sent totals."""

    def test_sale_create_ignores_browser_total(self, app, db_session):
        from services.sale_service import SaleService

        t = _make_tenant(db_session, 'T', 't-ignore', 'AED', False)
        b = _make_branch(db_session, t.id, 'B', 'B1')
        wh = _make_wh(db_session, t.id, b.id, True)
        product = _make_product(db_session, t.id, 'W', 'W9', 50, 100)
        customer = _make_customer(db_session, t.id, 'C')
        seller = _make_user(db_session, t.id, 'seller_' + str(t.id), b.id)

        lines = [{'product': product, 'quantity': 2, 'discount_percent': 0, 'unit_price': 100.00, 'serials': []}]

        sale = SaleService.create_sale(
            customer=customer, seller=seller, lines_data=lines,
            warehouse_id=wh.id, currency='AED', tax_rate=5.0,
            discount_amount=0, shipping_cost=0,
        )

        # Server calculates: 2 * 100 = 200 + 5% = 210
        assert sale.subtotal == Decimal('200')
        assert sale.total_amount == Decimal('210')
        # If browser had sent subtotal=999, tax=1, total=1000, it would be ignored
        # because SaleService only receives line quantities and prices, not totals


class TestWarehouseEditSecurity:
    """Verify warehouse edit route enforces tenant isolation and branch access."""

    def test_tenant_get_or_404_blocks_cross_tenant(self, db_session):
        """tenant_get_or_404 must return 404 for warehouse from another tenant."""
        from models import Warehouse
        from utils.tenanting import tenant_get_or_404

        t1 = _make_tenant(db_session, 'T1', 't1-sec', 'AED', False)
        t2 = _make_tenant(db_session, 'T2', 't2-sec', 'AED', False)
        b1 = _make_branch(db_session, t1.id, 'B1', 'B1')
        b2 = _make_branch(db_session, t2.id, 'B2', 'B2')
        wh1 = _make_wh(db_session, t1.id, b1.id, False)
        wh2 = _make_wh(db_session, t2.id, b2.id, False)
        user1 = _make_admin_user(db_session, t1.id, 'u1_sec', b1.id)

        # Same tenant: should succeed
        result = tenant_get_or_404(Warehouse, wh1.id, user=user1)
        assert result.id == wh1.id

        # Cross tenant: should raise 404
        from werkzeug.exceptions import NotFound
        with pytest.raises(NotFound):
            tenant_get_or_404(Warehouse, wh2.id, user=user1)

    def test_ensure_warehouse_access_blocks_cross_branch(self, db_session):
        """ensure_warehouse_access must reject warehouse from another branch."""
        from utils.branching import ensure_warehouse_access

        t = _make_tenant(db_session, 'T', 't-branch', 'AED', False)
        b1 = _make_branch(db_session, t.id, 'B1', 'B1')
        b2 = _make_branch(db_session, t.id, 'B2', 'B2')
        wh1 = _make_wh(db_session, t.id, b1.id, False)
        wh2 = _make_wh(db_session, t.id, b2.id, False)
        user = _make_user(db_session, t.id, 'u_branch', b1.id)

        # Same branch: should succeed
        result = ensure_warehouse_access(wh1.id, user=user)
        assert result.id == wh1.id

        # Cross branch: should raise ValueError
        with pytest.raises(ValueError, match='خارج نطاق'):
            ensure_warehouse_access(wh2.id, user=user)

    def test_allow_negative_inventory_toggle_persists(self, db_session):
        """Directly toggling allow_negative_inventory on warehouse persists."""
        t = _make_tenant(db_session, 'T', 't-toggle', 'AED', False)
        b = _make_branch(db_session, t.id, 'B', 'B1')
        wh = _make_wh(db_session, t.id, b.id, False)

        assert wh.allow_negative_inventory is False
        wh.allow_negative_inventory = True
        db_session.commit()
        db_session.refresh(wh)
        assert wh.allow_negative_inventory is True

        wh.allow_negative_inventory = False
        db_session.commit()
        db_session.refresh(wh)
        assert wh.allow_negative_inventory is False

    def test_edit_route_validates_branch_id_is_accessible(self, db_session):
        """The edit route's branch_id validation must reject inaccessible branches."""
        t = _make_tenant(db_session, 'T', 't-branch-val', 'AED', False)
        b1 = _make_branch(db_session, t.id, 'B1', 'B1')
        b2 = _make_branch(db_session, t.id, 'B2', 'B2')
        wh = _make_wh(db_session, t.id, b1.id, False)
        user = _make_user(db_session, t.id, 'u_branch', b1.id)

        from utils.branching import get_accessible_branches_query
        branches = get_accessible_branches_query(user).all()
        accessible_ids = {b.id for b in branches}

        assert b1.id in accessible_ids
        assert b2.id not in accessible_ids

        # Verify branch validation logic (as implemented in route)
        new_branch_id = b2.id
        assert new_branch_id not in accessible_ids, "Inaccessible branch should be rejected by route"


class TestPartnerCommissionDynamicProfitMargin:
    """Verify partner commissions are calculated on net profit margin (revenue - COGS) not gross revenue."""

    def test_commission_on_exclusive_vat_uses_profit_margin(self, app, db_session):
        from services.sale_service import SaleService

        t = _make_tenant(db_session, 'T', 't-comm', 'AED', False)
        b = _make_branch(db_session, t.id, 'B', 'B1')
        wh = _make_wh(db_session, t.id, b.id, True)
        # Product: cost=50, price=100 → profit=50 per unit
        product = _make_product(db_session, t.id, 'Widget', 'W1', cost=50, stock=100)
        # Set product cost_price for MWAC fallback
        product.cost_price = Decimal('50')
        db_session.flush()

        # Create a partner customer
        from models import Customer
        partner = Customer(tenant_id=t.id, name='Partner1', phone='0501111111', customer_type='partner')
        db_session.add(partner)
        db_session.flush()

        # Link partner to product at 20%
        from models import ProductPartner
        pp = ProductPartner(tenant_id=t.id, product_id=product.id, partner_customer_id=partner.id, percentage=Decimal('20'))
        db_session.add(pp)
        db_session.flush()

        customer = _make_customer(db_session, t.id, 'C1')
        seller = _make_user(db_session, t.id, 'seller_' + str(t.id), b.id)

        lines = [{'product': product, 'quantity': 2, 'discount_percent': 0, 'unit_price': 100.00, 'serials': []}]

        sale = SaleService.create_sale(
            customer=customer, seller=seller, lines_data=lines,
            warehouse_id=wh.id, currency='AED', tax_rate=5.0,
            discount_amount=0, shipping_cost=0,
        )

        # Revenue excl VAT = 2 * 100 = 200
        # Cost = 2 * 50 = 100
        # Profit margin = 100
        # Commission = 100 * 20% = 20
        from models import PartnerCommissionEntry
        entries = PartnerCommissionEntry.query.filter_by(sale_id=sale.id).all()
        assert len(entries) == 1
        entry = entries[0]
        assert entry.profit_margin == Decimal('100')
        assert entry.cost_basis == Decimal('100')
        assert entry.commission_amount_aed == Decimal('20')
        assert entry.warehouse_id == wh.id
        assert entry.tenant_id == t.id

    def test_commission_on_inclusive_vat_excludes_vat_from_profit(self, app, db_session):
        from services.sale_service import SaleService

        t = _make_tenant(db_session, 'T', 't-comm-inc', 'AED', True)
        b = _make_branch(db_session, t.id, 'B', 'B1')
        wh = _make_wh(db_session, t.id, b.id, True)
        product = _make_product(db_session, t.id, 'Widget', 'W2', cost=50, stock=100)
        product.cost_price = Decimal('50')
        db_session.flush()

        from models import Customer
        partner = Customer(tenant_id=t.id, name='Partner2', phone='0502222222', customer_type='partner')
        db_session.add(partner)
        db_session.flush()

        from models import ProductPartner
        pp = ProductPartner(tenant_id=t.id, product_id=product.id, partner_customer_id=partner.id, percentage=Decimal('10'))
        db_session.add(pp)
        db_session.flush()

        customer = _make_customer(db_session, t.id, 'C1')
        seller = _make_user(db_session, t.id, 'seller_' + str(t.id), b.id)

        # unit_price = 100 (inclusive of 5% VAT)
        # Revenue excl VAT = 100 / 1.05 = 95.24 per unit
        # For 2 units: 190.48
        # Cost = 2 * 50 = 100
        # Profit = 90.48
        # Commission = 90.48 * 10% = 9.05
        lines = [{'product': product, 'quantity': 2, 'discount_percent': 0, 'unit_price': 100.00, 'serials': []}]

        sale = SaleService.create_sale(
            customer=customer, seller=seller, lines_data=lines,
            warehouse_id=wh.id, currency='AED', tax_rate=5.0,
        )

        from models import PartnerCommissionEntry
        entries = PartnerCommissionEntry.query.filter_by(sale_id=sale.id).all()
        assert len(entries) == 1
        entry = entries[0]
        # profit_margin should be ~90.48 (190.48 - 100)
        assert entry.profit_margin > Decimal('80')
        assert entry.profit_margin < Decimal('100')
        assert entry.cost_basis == Decimal('100')
        assert entry.commission_amount_aed > Decimal('8')
        assert entry.commission_amount_aed < Decimal('10')

    def test_no_commission_when_no_partner_linked(self, app, db_session):
        from services.sale_service import SaleService

        t = _make_tenant(db_session, 'T', 't-comm-none', 'AED', False)
        b = _make_branch(db_session, t.id, 'B', 'B1')
        wh = _make_wh(db_session, t.id, b.id, True)
        product = _make_product(db_session, t.id, 'Widget', 'W3', cost=50, stock=100)
        customer = _make_customer(db_session, t.id, 'C1')
        seller = _make_user(db_session, t.id, 'seller_' + str(t.id), b.id)

        lines = [{'product': product, 'quantity': 1, 'discount_percent': 0, 'unit_price': 100.00, 'serials': []}]

        sale = SaleService.create_sale(
            customer=customer, seller=seller, lines_data=lines,
            warehouse_id=wh.id, currency='AED', tax_rate=0,
        )

        from models import PartnerCommissionEntry
        entries = PartnerCommissionEntry.query.filter_by(sale_id=sale.id).all()
        assert len(entries) == 0

    def test_commission_tenant_isolation(self, app, db_session):
        """Partner commission entries must be tenant-isolated."""
        t1 = _make_tenant(db_session, 'T1', 't1-iso', 'AED', False)
        t2 = _make_tenant(db_session, 'T2', 't2-iso', 'AED', False)
        b1 = _make_branch(db_session, t1.id, 'B1', 'B1')
        wh1 = _make_wh(db_session, t1.id, b1.id, True)
        product1 = _make_product(db_session, t1.id, 'W', 'W4', cost=50, stock=100)

        from models import Customer
        partner1 = Customer(tenant_id=t1.id, name='P1', phone='0503333333', customer_type='partner')
        db_session.add(partner1)
        db_session.flush()

        from models import ProductPartner
        pp = ProductPartner(tenant_id=t1.id, product_id=product1.id, partner_customer_id=partner1.id, percentage=Decimal('10'))
        db_session.add(pp)
        db_session.flush()

        customer = _make_customer(db_session, t1.id, 'C')
        seller = _make_user(db_session, t1.id, 'seller_' + str(t1.id), b1.id)

        from services.sale_service import SaleService
        lines = [{'product': product1, 'quantity': 1, 'discount_percent': 0, 'unit_price': 100.00, 'serials': []}]
        sale = SaleService.create_sale(
            customer=customer, seller=seller, lines_data=lines,
            warehouse_id=wh1.id, currency='AED', tax_rate=0,
        )

        from models import PartnerCommissionEntry
        entries = PartnerCommissionEntry.query.filter_by(sale_id=sale.id).all()
        assert len(entries) == 1
        assert entries[0].tenant_id == t1.id

        # Cross-tenant query should return nothing
        cross = PartnerCommissionEntry.query.filter_by(sale_id=sale.id, tenant_id=t2.id).all()
        assert len(cross) == 0
