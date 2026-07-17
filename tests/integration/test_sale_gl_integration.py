"""
Integration test: Sale creates balanced GL entries and records stock movements.
"""

from decimal import Decimal
import uuid


class TestSaleGlIntegration:
    def test_sale_creates_balanced_gl_entries(self, app, db_session):
        from models import Tenant, Branch, Warehouse, Product, Customer, User, Role
        from models import GLJournalEntry, StockMovement
        from services.sale_service import SaleService
        from utils.gl_reference_types import GLRef

        tid = str(uuid.uuid4())[:8]
        tenant = Tenant(
            name=f"Test {tid}",
            name_ar=f"Test {tid}",
            slug=f"test-{tid}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(tenant)
        db_session.flush()

        branch = Branch(tenant_id=tenant.id, name=f"Main {tid}", code=f"BR{tid[:4]}")
        db_session.add(branch)
        db_session.flush()

        wh = Warehouse(
            tenant_id=tenant.id,
            name=f"WH {tid}",
            branch_id=branch.id,
            allow_negative_inventory=True,
        )
        db_session.add(wh)
        db_session.flush()

        role = Role(name=f"Seller {tid}", slug=f"seller-{tid}", is_active=True)
        db_session.add(role)
        db_session.flush()

        seller = User(
            tenant_id=tenant.id,
            username=f"seller_{tid}",
            email=f"seller_{tid}@test.com",
            is_active=True,
            password_hash="fakehash",
            branch_id=branch.id,
            role_id=role.id,
        )
        db_session.add(seller)
        db_session.flush()

        customer = Customer(tenant_id=tenant.id, name=f"Cust {tid}", phone=f"050{tid}")
        db_session.add(customer)
        db_session.flush()

        product = Product(
            tenant_id=tenant.id,
            name=f"Prod {tid}",
            name_ar=f"Prod {tid}",
            sku=f"SKU-{tid}",
            cost_price=Decimal("50"),
            regular_price=Decimal("100"),
            current_stock=Decimal("100"),
        )
        db_session.add(product)
        db_session.flush()

        lines = [
            {
                "product": product,
                "quantity": 2,
                "discount_percent": 0,
                "unit_price": 100.00,
                "serials": [],
            }
        ]

        sale = SaleService.create_sale(
            customer=customer,
            seller=seller,
            lines_data=lines,
            warehouse_id=wh.id,
            currency="AED",
            tax_rate=0,
            discount_amount=0,
            shipping_cost=0,
        )

        assert sale.subtotal == Decimal("200")
        assert sale.total_amount == Decimal("200")

        # --- Verify SALE GL entry exists and balances ---
        gl_entry = GLJournalEntry.query.filter_by(
            reference_type=GLRef.SALE,
            reference_id=sale.id,
            tenant_id=tenant.id,
        ).first()
        assert gl_entry is not None, "No SALE GL entry created"

        total_debit = sum(Decimal(str(l.debit or 0)) for l in gl_entry.lines)
        total_credit = sum(Decimal(str(l.credit or 0)) for l in gl_entry.lines)
        assert total_debit == total_credit, (
            f"SALE GL entry unbalanced: debit={total_debit}, credit={total_credit}"
        )

        # Sale of 2x100 = 200 → DR AR 200, CR Sales Revenue 200
        assert total_debit == Decimal("200")
        assert total_credit == Decimal("200")

        # --- Verify SALE_COGS GL entry exists and balances ---
        cogs_entry = GLJournalEntry.query.filter_by(
            reference_type=GLRef.SALE_COGS,
            reference_id=sale.id,
            tenant_id=tenant.id,
        ).first()
        assert cogs_entry is not None, "No SALE_COGS GL entry created"

        cogs_debit = sum(Decimal(str(l.debit or 0)) for l in cogs_entry.lines)
        cogs_credit = sum(Decimal(str(l.credit or 0)) for l in cogs_entry.lines)
        assert cogs_debit == cogs_credit, (
            f"COGS GL entry unbalanced: debit={cogs_debit}, credit={cogs_credit}"
        )

        # COGS = 2 units × 50 cost = 100 → DR COGS 100, CR Inventory 100
        assert cogs_debit == Decimal("100")
        assert cogs_credit == Decimal("100")

        # --- Verify stock was deducted ---
        movements = StockMovement.query.filter_by(
            product_id=product.id,
            movement_type="sale",
            reference_type=GLRef.SALE,
            reference_id=sale.id,
        ).all()
        assert len(movements) >= 1
        total_qty = sum(m.quantity for m in movements)
        assert total_qty == Decimal("-2"), (
            f"Stock movement expected -2, got {total_qty}"
        )
