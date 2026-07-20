"""
Integration tests: Sales routes — real business logic via POST /sales/create.
"""

import uuid
from decimal import Decimal

from models import StockMovement


def _add_initial_stock(db_session, product_id, warehouse_id, tenant_id, quantity):
    """Create an initial StockMovement so stock queries return the expected quantity."""
    sm = StockMovement(
        product_id=product_id,
        warehouse_id=warehouse_id,
        tenant_id=tenant_id,
        movement_type="adjustment",
        quantity=quantity,
        notes="Initial test stock",
    )
    db_session.add(sm)


class TestSalesCreate:
    def test_create_invoice_creates_gl_and_reduces_stock(self, app, db_session, client):
        from models import (
            Tenant,
            Branch,
            User,
            Role,
            Customer,
            Product,
            Warehouse,
            ProductWarehouseStock,
        )
        from services.gl_service import GLService
        from models.gl import GLJournalEntry

        tid = str(uuid.uuid4())[:8]
        tenant = Tenant(
            name=f"ST {tid}",
            name_ar=f"ST {tid}",
            slug=f"sales-test-{tid}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(tenant)
        db_session.flush()

        branch = Branch(tenant_id=tenant.id, name=f"Main {tid}", code=f"BR{tid[:4]}")
        db_session.add(branch)
        db_session.flush()

        warehouse = Warehouse(
            tenant_id=tenant.id,
            name=f"WH {tid}",
            code=f"WH{tid[:4]}",
            branch_id=branch.id,
            is_active=True,
            allow_negative_inventory=False,
        )
        db_session.add(warehouse)
        db_session.flush()

        role = Role(name=f"Admin {tid}", slug=f"admin-{tid}", is_active=True)
        db_session.add(role)
        db_session.flush()

        user = User(
            username=f"seller-{tid}",
            email=f"seller-{tid}@t.com",
            full_name="Seller",
            role_id=role.id,
            tenant_id=tenant.id,
            branch_id=branch.id,
            is_active=True,
            is_owner=True,
        )
        user.set_password("x")
        db_session.add(user)
        db_session.flush()

        customer = Customer(tenant_id=tenant.id, name=f"Cust {tid}", phone=f"050{tid}")
        db_session.add(customer)
        db_session.flush()

        product = Product(
            name=f"Widget {tid}",
            sku=f"WID-{tid}",
            tenant_id=tenant.id,
            cost_price=Decimal("50"),
            regular_price=Decimal("100"),
            current_stock=Decimal("100"),
            is_active=True,
        )
        db_session.add(product)
        db_session.flush()

        stock = ProductWarehouseStock(
            tenant_id=tenant.id,
            product_id=product.id,
            warehouse_id=warehouse.id,
            quantity=Decimal("100"),
        )
        db_session.add(stock)
        _add_initial_stock(db_session, product.id, warehouse.id, tenant.id, Decimal("100"))
        db_session.commit()

        GLService.ensure_core_accounts(tenant_id=tenant.id)
        db_session.commit()

        with client:
            resp = client.post(
                "/auth/login",
                data={
                    "username": user.username,
                    "password": "x",
                },
                follow_redirects=True,
            )
            assert resp.status_code == 200

            resp = client.post(
                "/sales/create",
                data={
                    "customer_id": str(customer.id),
                    "line_count": "1",
                    "lines[0][product_id]": str(product.id),
                    "lines[0][quantity]": "5",
                    "lines[0][unit_price]": "100",
                    "lines[0][discount_percent]": "0",
                    "currency": "AED",
                    "warehouse_id": str(warehouse.id),
                },
                follow_redirects=False,
            )

        assert resp.status_code == 302, f"Expected redirect, got {resp.status_code}"

        from models import Sale

        sale = Sale.query.filter_by(tenant_id=tenant.id).first()
        assert sale is not None, "Sale was not created"
        assert sale.total_amount == Decimal("500")
        assert sale.paid_amount == Decimal("0")

        gl_entries = GLJournalEntry.query.filter(
            GLJournalEntry.reference_type.in_(["Sale", "SaleCOGS"]),
            GLJournalEntry.reference_id == sale.id,
        ).all()
        assert len(gl_entries) >= 2
        total_debit = sum((e.total_debit or 0) for e in gl_entries)
        total_credit = sum((e.total_credit or 0) for e in gl_entries)
        assert total_debit == total_credit, f"GL unbalanced: debit={total_debit} credit={total_credit}"

        stock_after = ProductWarehouseStock.query.filter_by(product_id=product.id, warehouse_id=warehouse.id).first()
        assert stock_after.quantity == Decimal("95"), f"Expected 95, got {stock_after.quantity}"

    def test_create_invoice_with_tax_calculates_vat_correctly(self, app, db_session, client):
        from models import (
            Tenant,
            Branch,
            User,
            Role,
            Customer,
            Product,
            Warehouse,
            ProductWarehouseStock,
        )
        from services.gl_service import GLService
        from decimal import Decimal

        tid = str(uuid.uuid4())[:8]
        tenant = Tenant(
            name=f"TAX {tid}",
            name_ar=f"TAX {tid}",
            slug=f"tax-test-{tid}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(tenant)
        db_session.flush()

        branch = Branch(tenant_id=tenant.id, name=f"Main {tid}", code=f"BR{tid[:4]}")
        db_session.add(branch)
        db_session.flush()

        warehouse = Warehouse(
            tenant_id=tenant.id,
            name=f"WH {tid}",
            code=f"WH{tid[:4]}",
            branch_id=branch.id,
            is_active=True,
        )
        db_session.add(warehouse)
        db_session.flush()

        role = Role(name=f"Admin {tid}", slug=f"admin-{tid}", is_active=True)
        db_session.add(role)
        db_session.flush()

        user = User(
            username=f"seller2-{tid}",
            email=f"seller2-{tid}@t.com",
            full_name="Seller",
            role_id=role.id,
            tenant_id=tenant.id,
            branch_id=branch.id,
            is_active=True,
            is_owner=True,
        )
        user.set_password("x")
        db_session.add(user)
        db_session.flush()

        customer = Customer(tenant_id=tenant.id, name=f"TaxCust {tid}", phone=f"051{tid}")
        db_session.add(customer)
        db_session.flush()

        product = Product(
            name=f"TaxWidget {tid}",
            sku=f"TW-{tid}",
            tenant_id=tenant.id,
            cost_price=Decimal("50"),
            regular_price=Decimal("100"),
            current_stock=Decimal("50"),
            is_active=True,
        )
        db_session.add(product)
        db_session.flush()

        stock = ProductWarehouseStock(
            tenant_id=tenant.id,
            product_id=product.id,
            warehouse_id=warehouse.id,
            quantity=Decimal("50"),
        )
        db_session.add(stock)
        _add_initial_stock(db_session, product.id, warehouse.id, tenant.id, Decimal("50"))
        db_session.commit()

        GLService.ensure_core_accounts(tenant_id=tenant.id)
        db_session.commit()

        with client:
            resp = client.post(
                "/auth/login",
                data={
                    "username": user.username,
                    "password": "x",
                },
                follow_redirects=True,
            )
            assert resp.status_code == 200

            resp = client.post(
                "/sales/create",
                data={
                    "customer_id": str(customer.id),
                    "line_count": "1",
                    "lines[0][product_id]": str(product.id),
                    "lines[0][quantity]": "2",
                    "lines[0][unit_price]": "100",
                    "lines[0][discount_percent]": "0",
                    "currency": "AED",
                    "warehouse_id": str(warehouse.id),
                    "tax_rate": "5",
                },
                follow_redirects=False,
            )

        assert resp.status_code == 302, f"Expected redirect, got {resp.status_code}"

        from models import Sale

        sale = Sale.query.filter_by(tenant_id=tenant.id).first()
        assert sale is not None
        assert sale.subtotal == Decimal("200"), f"subtotal={sale.subtotal}"
        assert sale.tax_rate == Decimal("5")
        assert sale.tax_amount == Decimal("10"), f"tax_amount={sale.tax_amount}"
        assert sale.total_amount == Decimal("210"), f"total={sale.total_amount}"
