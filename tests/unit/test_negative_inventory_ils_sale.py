import pytest
from decimal import Decimal

from models import (
    Tenant,
    Branch,
    Warehouse,
    Product,
    Customer,
    User,
    Role,
    GLAccount,
    GLJournalEntry,
    GLJournalLine,
    ProductWarehouseStock,
    ProductWarehouseCost,
    Currency,
)
from services.sale_service import SaleService
from services.gl_service import GLService
from services.gl_tree_builder import GLTreeBuilder
from services.gl_accounting_setup import GLAccountingSetupService


@pytest.fixture
def ils_tenant(db_session):
    """Create a Palestinian tenant with ILS base currency."""
    import uuid

    unique = str(uuid.uuid4())[:8]
    tenant = Tenant(
        name=f"Palestine Tech Co {unique}",
        name_ar="شركة تك فلسطين",
        slug=f"palestine-tech-{unique}",
        email=f"test-{unique}@palestine.ps",
        phone_1="0599000000",
        country="PS",
        city="Ramallah",
        subscription_plan="basic",
        default_currency="ILS",
        base_currency="ILS",
        default_tax_rate=Decimal("16.00"),
        tax_number="123456789",
        is_active=True,
        enable_tax=True,
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


@pytest.fixture
def ils_branch(db_session, ils_tenant):
    """Create a branch for the Palestinian tenant."""
    branch = Branch(
        tenant_id=ils_tenant.id,
        name="Ramallah Main",
        code="RAM01",
        is_active=True,
        is_main=True,
    )
    db_session.add(branch)
    db_session.commit()
    return branch


@pytest.fixture
def negative_warehouse(db_session, ils_tenant, ils_branch):
    """Create a warehouse that allows negative inventory."""
    wh = Warehouse(
        tenant_id=ils_tenant.id,
        branch_id=ils_branch.id,
        name="POS Warehouse",
        name_ar="مستودع نقاط البيع",
        is_active=True,
        is_main=True,
        allow_negative_inventory=True,
    )
    db_session.add(wh)
    db_session.commit()
    return wh


@pytest.fixture
def ils_customer(db_session, ils_tenant):
    """Create a test customer."""
    cust = Customer(
        tenant_id=ils_tenant.id,
        name="Test Buyer",
        name_ar="مشتري تجريبي",
        email="buyer@test.ps",
        phone="0599111111",
        customer_type="retail",
        is_active=True,
    )
    db_session.add(cust)
    db_session.commit()
    return cust


@pytest.fixture
def ils_seller(db_session, ils_tenant, ils_branch):
    """Create a test seller user."""
    import uuid

    unique = str(uuid.uuid4())[:8]
    role = Role(
        name=f"Seller {unique}",
        slug=f"seller-{unique}",
        is_active=True,
    )
    db_session.add(role)
    db_session.commit()

    user = User(
        tenant_id=ils_tenant.id,
        branch_id=ils_branch.id,
        role_id=role.id,
        username=f"test_seller_{unique}",
        email=f"seller-{unique}@test.ps",
        full_name="Test Seller",
        is_active=True,
    )
    user.set_password("password123")
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def ils_product_zero_stock(db_session, ils_tenant, negative_warehouse):
    """Create a product with ZERO stock but a known cost_price (fallback)."""
    product = Product(
        tenant_id=ils_tenant.id,
        name="Test Product",
        name_ar="منتج تجريبي",
        sku="SKU-PS-001",
        cost_price=Decimal("50.00"),
        regular_price=Decimal("100.00"),
        current_stock=Decimal("0"),
        is_active=True,
    )
    db_session.add(product)
    db_session.commit()

    pws = ProductWarehouseStock.query.filter_by(
        tenant_id=ils_tenant.id,
        product_id=product.id,
        warehouse_id=negative_warehouse.id,
    ).first()
    if pws:
        db_session.delete(pws)
        db_session.commit()

    return product


@pytest.fixture
def ils_currency_setup(db_session, ils_tenant):
    """Ensure ILS currency exists."""
    c = Currency.query.filter_by(code="ILS").first()
    if not c:
        c = Currency(
            code="ILS",
            name="Israeli Shekel",
            name_ar="شيكل إسرائيلي",
            symbol="₪",
            is_base=True,
        )
        db_session.add(c)
        db_session.commit()
    return c


@pytest.fixture
def ils_coa(db_session, ils_tenant, ils_branch, negative_warehouse):
    """Build full GL chart for the tenant."""
    GLTreeBuilder.build(tenant_id=ils_tenant.id, cleanup_extra=False)
    GLAccountingSetupService.execute(tenant_id=ils_tenant.id, dry_run=False)
    tenant = db_session.get(Tenant, ils_tenant.id)
    tenant.enable_tax = True
    tenant.default_tax_rate = Decimal("16.00")
    db_session.commit()
    return ils_tenant


class TestNegativeInventoryILSSale:
    def test_sale_with_zero_stock_negative_inventory_allowed(
        self,
        app,
        db_session,
        ils_tenant,
        ils_branch,
        negative_warehouse,
        ils_customer,
        ils_seller,
        ils_product_zero_stock,
        ils_currency_setup,
        ils_coa,
    ):
        """
        Simulate: Sale of 1 unit at 100 ILS + 16% VAT when stock is zero
        and warehouse allows negative inventory.
        """
        with app.app_context():
            # Step 1: Pre-conditions
            assert ils_tenant.base_currency == "ILS"
            assert negative_warehouse.allow_negative_inventory is True
            assert ils_product_zero_stock.current_stock == 0

            gl_accounts = GLAccount.query.filter_by(tenant_id=ils_tenant.id).all()
            assert len(gl_accounts) > 50, "COA not built properly"

            ar_acct = GLAccount.query.filter_by(
                tenant_id=ils_tenant.id, code="1130"
            ).first()
            sales_acct = GLAccount.query.filter_by(
                tenant_id=ils_tenant.id, code="4100"
            ).first()
            cogs_acct = GLAccount.query.filter_by(
                tenant_id=ils_tenant.id, code="5100"
            ).first()
            inv_acct = GLAccount.query.filter_by(
                tenant_id=ils_tenant.id, code="1140"
            ).first()

            from utils.tax_settings import should_post_vat_gl

            tenant_row = db_session.get(Tenant, ils_tenant.id)
            tenant_row.enable_tax = True
            tenant_row.default_tax_rate = Decimal("16.00")
            db_session.commit()
            db_session.refresh(tenant_row)
            assert should_post_vat_gl(ils_tenant.id) is True

            vat_account_code = GLService.get_account_code_for_concept(
                "VAT_OUTPUT",
                branch_id=ils_branch.id,
                tenant_id=ils_tenant.id,
                fallback_key="tax_payable",
            )
            vat_acct = GLAccount.query.filter_by(
                tenant_id=ils_tenant.id, code=vat_account_code
            ).first()
            assert all([ar_acct, sales_acct, vat_acct, cogs_acct, inv_acct]), (
                "Key accounts missing"
            )

            # Step 2: Create the sale
            quantity = 1
            unit_price = Decimal("100.00")

            lines_data = [
                {
                    "product": ils_product_zero_stock,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "discount_percent": 0,
                }
            ]

            sale = SaleService.create_sale(
                customer=ils_customer,
                seller=ils_seller,
                lines_data=lines_data,
                warehouse_id=negative_warehouse.id,
                currency="ILS",
                tax_rate=Decimal("16"),
                defer_fulfillment=False,
            )

            assert sale is not None
            assert sale.sale_number is not None
            db_session.refresh(sale)

            # Step 3: Verify sale totals
            expected_subtotal = Decimal("100.00")
            expected_vat = Decimal("16.00")
            expected_total = Decimal("116.00")

            assert sale.subtotal == expected_subtotal
            assert sale.tax_amount == expected_vat
            assert sale.total_amount == expected_total
            assert should_post_vat_gl(sale.tenant_id) is True

            # Step 4: Verify stock went negative
            pws = ProductWarehouseStock.query.filter_by(
                tenant_id=ils_tenant.id,
                product_id=ils_product_zero_stock.id,
                warehouse_id=negative_warehouse.id,
            ).first()

            assert pws is not None
            assert pws.quantity < 0
            assert pws.quantity == -quantity

            # Step 5: Verify COGS > 0 (fallback cost used)
            pwc = ProductWarehouseCost.query.filter_by(
                tenant_id=ils_tenant.id,
                product_id=ils_product_zero_stock.id,
                warehouse_id=negative_warehouse.id,
            ).first()

            assert pwc is not None
            assert pwc.average_cost is not None
            assert pwc.average_cost > 0
            assert pwc.average_cost == Decimal("50.00")

            # Step 6: Verify GL entries (Revenue + VAT)
            entries = GLJournalEntry.query.filter_by(
                tenant_id=ils_tenant.id,
                reference_id=sale.id,
            ).all()

            assert len(entries) > 0, "No GL entries for sale"

            def _line_account_code(gl_line):
                acc = db_session.get(GLAccount, gl_line.account_id)
                return acc.code if acc else None

            # Separate revenue and COGS entries
            revenue_entry = None
            cogs_entry = None
            for entry in entries:
                lines = GLJournalLine.query.filter_by(entry_id=entry.id).all()
                for line in lines:
                    code = _line_account_code(line)
                    if code == "4100":
                        revenue_entry = entry
                    if code == "5100":
                        cogs_entry = entry

            assert revenue_entry is not None, "Revenue GL entry not found"

            rev_lines = GLJournalLine.query.filter_by(entry_id=revenue_entry.id).all()
            rev_debit = sum(l.debit for l in rev_lines if l.debit)
            rev_credit = sum(l.credit for l in rev_lines if l.credit)
            assert abs(rev_debit - rev_credit) < Decimal("0.01"), (
                f"Revenue entry NOT balanced: Dr={rev_debit} Cr={rev_credit}"
            )

            all_lines = []
            for entry in entries:
                all_lines.extend(GLJournalLine.query.filter_by(entry_id=entry.id).all())

            ar_line = [l for l in all_lines if _line_account_code(l) == "1130"]
            sales_line = [l for l in all_lines if _line_account_code(l) == "4100"]
            vat_line = [
                l for l in all_lines if _line_account_code(l) == vat_account_code
            ]

            assert len(ar_line) == 1, "AR line missing"
            assert len(sales_line) == 1, "Sales line missing"
            assert len(vat_line) == 1, "VAT line missing"

            # Amounts are in base currency (ILS), so exact match expected
            assert ar_line[0].debit == expected_total, (
                f"AR debit should be {expected_total}: got {ar_line[0].debit}"
            )
            assert sales_line[0].credit == expected_subtotal, (
                f"Sales credit should be {expected_subtotal}: got {sales_line[0].credit}"
            )
            assert vat_line[0].credit == expected_vat, (
                f"VAT credit should be {expected_vat}: got {vat_line[0].credit}"
            )

            # Step 7: Verify COGS entry
            assert cogs_entry is not None, "COGS GL entry not found"

            cogs_lines = GLJournalLine.query.filter_by(entry_id=cogs_entry.id).all()
            cogs_debit = sum(l.debit for l in cogs_lines if l.debit)
            cogs_credit = sum(l.credit for l in cogs_lines if l.credit)
            assert abs(cogs_debit - cogs_credit) < Decimal("0.01"), (
                f"COGS entry NOT balanced: Dr={cogs_debit} Cr={cogs_credit}"
            )

            cogs_dr = [l for l in cogs_lines if _line_account_code(l) == "5100"]
            inv_cr = [l for l in cogs_lines if _line_account_code(l) == "1140"]

            assert len(cogs_dr) == 1, "COGS debit line missing"
            assert cogs_dr[0].debit > 0, f"COGS should be > 0: got {cogs_dr[0].debit}"
            assert cogs_dr[0].debit == Decimal("50.00"), (
                f"COGS should be 50 (fallback cost): got {cogs_dr[0].debit}"
            )

            assert len(inv_cr) == 1, "Inventory credit line missing"
            assert inv_cr[0].credit == cogs_dr[0].debit, (
                "COGS and Inventory lines must match"
            )

            # Step 8: Verify sale line has cost_price captured
            sale_line = sale.lines[0]
            assert sale_line.cost_price is not None
            assert sale_line.cost_price > 0, (
                f"SaleLine.cost_price should be > 0: got {sale_line.cost_price}"
            )

            print(f"\r\n{'=' * 60}")
            print("TEST PASSED: Negative Inventory + ILS + VAT Sale")
            print(f"{'=' * 60}")
            print(f"Sale Number: {sale.sale_number}")
            print(f"Subtotal: {sale.subtotal} ILS")
            print(f"VAT: {sale.tax_amount} ILS")
            print(f"Total: {sale.total_amount} ILS")
            print(f"Stock: {pws.quantity} (negative, OK)")
            print(f"COGS: {cogs_dr[0].debit} (fallback cost, OK)")
            print(f"Revenue GL: Dr={rev_debit} Cr={rev_credit} (balanced)")
            print(f"COGS GL: Dr={cogs_debit} Cr={cogs_credit} (balanced)")
            print(f"{'=' * 60}")
