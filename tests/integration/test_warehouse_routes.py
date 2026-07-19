"""
Integration tests: Warehouse routes — real business logic via POST /warehouse/add-stock.
"""

import uuid
from decimal import Decimal

from models import StockMovement


def _add_initial_stock(db_session, product_id, warehouse_id, tenant_id, quantity):
    sm = StockMovement(
        product_id=product_id,
        warehouse_id=warehouse_id,
        tenant_id=tenant_id,
        movement_type="adjustment",
        quantity=quantity,
        notes="Initial test stock",
    )
    db_session.add(sm)


class TestWarehouseAddStock:
    def test_add_stock_increases_stock_and_creates_gl(self, app, db_session, client):
        from models import (
            Tenant,
            Branch,
            User,
            Role,
            Product,
            Warehouse,
            ProductWarehouseStock,
        )
        from services.gl_service import GLService
        from models.gl import GLJournalEntry

        tid = str(uuid.uuid4())[:8]
        tenant = Tenant(
            name=f"WH {tid}",
            name_ar=f"WH {tid}",
            slug=f"wh-test-{tid}",
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
            username=f"whuser-{tid}",
            email=f"whuser-{tid}@t.com",
            full_name="WH User",
            role_id=role.id,
            tenant_id=tenant.id,
            branch_id=branch.id,
            is_active=True,
            is_owner=True,
        )
        user.set_password("x")
        db_session.add(user)
        db_session.flush()

        product = Product(
            name=f"Item {tid}",
            sku=f"ITM-{tid}",
            tenant_id=tenant.id,
            cost_price=Decimal("50"),
            regular_price=Decimal("100"),
            current_stock=Decimal("10"),
            is_active=True,
        )
        db_session.add(product)
        db_session.flush()

        stock = ProductWarehouseStock(
            tenant_id=tenant.id,
            product_id=product.id,
            warehouse_id=warehouse.id,
            quantity=Decimal("10"),
        )
        db_session.add(stock)
        _add_initial_stock(
            db_session, product.id, warehouse.id, tenant.id, Decimal("10")
        )
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
                f"/warehouse/add-stock/{product.id}",
                data={
                    "quantity": "5",
                    "warehouse_id": str(warehouse.id),
                    "notes": "Test add stock",
                },
                follow_redirects=False,
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data is not None, f"Expected JSON, got {resp.data}"
        assert data["success"] is True

        stock_after = ProductWarehouseStock.query.filter_by(
            product_id=product.id, warehouse_id=warehouse.id
        ).first()
        assert stock_after.quantity == Decimal("15"), (
            f"Expected 15, got {stock_after.quantity}"
        )

        movement = (
            StockMovement.query.filter_by(
                product_id=product.id,
                warehouse_id=warehouse.id,
                movement_type="adjustment",
            )
            .order_by(StockMovement.id.desc())
            .first()
        )
        assert movement is not None
        assert movement.quantity == Decimal("5")

        gl_entries = GLJournalEntry.query.filter(
            GLJournalEntry.reference_type == "StockAdjustment",
            GLJournalEntry.reference_id == movement.id,
        ).all()
        assert len(gl_entries) >= 1
        total_debit = sum((e.total_debit or 0) for e in gl_entries)
        total_credit = sum((e.total_credit or 0) for e in gl_entries)
        assert total_debit == total_credit, (
            f"GL unbalanced: debit={total_debit} credit={total_credit}"
        )
        assert total_debit == Decimal("250"), (
            f"Expected 250 (5 * 50), got {total_debit}"
        )

    def test_add_stock_calculates_gl_from_cost_price(self, app, db_session, client):
        from models import (
            Tenant,
            Branch,
            User,
            Role,
            Product,
            Warehouse,
            ProductWarehouseStock,
        )
        from services.gl_service import GLService
        from models.gl import GLJournalEntry, GLJournalLine

        tid = str(uuid.uuid4())[:8]
        tenant = Tenant(
            name=f"WH2 {tid}",
            name_ar=f"WH2 {tid}",
            slug=f"wh2-test-{tid}",
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
            name=f"WH2 {tid}",
            code=f"WH2{tid[:4]}",
            branch_id=branch.id,
            is_active=True,
        )
        db_session.add(warehouse)
        db_session.flush()

        role = Role(name=f"Admin {tid}", slug=f"admin-{tid}", is_active=True)
        db_session.add(role)
        db_session.flush()

        user = User(
            username=f"whuser2-{tid}",
            email=f"whuser2-{tid}@t.com",
            full_name="WH User",
            role_id=role.id,
            tenant_id=tenant.id,
            branch_id=branch.id,
            is_active=True,
            is_owner=True,
        )
        user.set_password("x")
        db_session.add(user)
        db_session.flush()

        product = Product(
            name=f"CostItem {tid}",
            sku=f"CST-{tid}",
            tenant_id=tenant.id,
            cost_price=Decimal("20"),
            regular_price=Decimal("80"),
            current_stock=Decimal("0"),
            is_active=True,
        )
        db_session.add(product)
        db_session.flush()

        stock = ProductWarehouseStock(
            tenant_id=tenant.id,
            product_id=product.id,
            warehouse_id=warehouse.id,
            quantity=Decimal("0"),
        )
        db_session.add(stock)
        _add_initial_stock(
            db_session, product.id, warehouse.id, tenant.id, Decimal("0")
        )
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
                f"/warehouse/add-stock/{product.id}",
                data={
                    "quantity": "10",
                    "warehouse_id": str(warehouse.id),
                },
                follow_redirects=False,
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert float(data["new_stock"]) == 10.0

        stock_after = ProductWarehouseStock.query.filter_by(
            product_id=product.id, warehouse_id=warehouse.id
        ).first()
        assert stock_after.quantity == Decimal("10")

        movement = (
            StockMovement.query.filter_by(
                product_id=product.id,
                warehouse_id=warehouse.id,
                movement_type="adjustment",
            )
            .order_by(StockMovement.id.desc())
            .first()
        )
        assert movement.quantity == Decimal("10")

        lines = (
            GLJournalLine.query.join(
                GLJournalEntry,
                GLJournalLine.entry_id == GLJournalEntry.id,
            )
            .filter(
                GLJournalEntry.reference_type == "StockAdjustment",
                GLJournalEntry.reference_id == movement.id,
            )
            .all()
        )
        assert len(lines) >= 2

        debit_lines = [line for line in lines if (line.debit or 0) > 0]
        credit_lines = [line for line in lines if (line.credit or 0) > 0]
        assert len(debit_lines) >= 1
        assert len(credit_lines) >= 1
        total_debit = sum((line.debit or 0) for line in lines)
        total_credit = sum((line.credit or 0) for line in lines)
        assert total_debit == total_credit
        assert total_debit == Decimal("200"), (
            f"Expected 200 (10 * 20), got {total_debit}"
        )


class TestWarehouseCreate:
    def test_create_warehouse_persists_and_lists(self, app, db_session, client):
        import uuid
        from models import Tenant, Branch, User, Role, Warehouse

        tid = str(uuid.uuid4())[:8]
        tenant = Tenant(
            name=f"WH Create {tid}",
            name_ar=f"WH Create {tid}",
            slug=f"wh-create-{tid}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(tenant)
        db_session.flush()

        branch = Branch(
            tenant_id=tenant.id, name=f"Main {tid}", code=f"BR{tid[:4]}", is_main=True
        )
        db_session.add(branch)
        db_session.flush()

        role = Role.query.filter_by(slug="super_admin").first()
        if role is None:
            role = Role(name=f"Admin {tid}", slug=f"super-admin-{tid}", is_active=True)
            db_session.add(role)
            db_session.flush()

        user = User(
            username=f"whadmin-{tid}",
            email=f"whadmin-{tid}@t.com",
            full_name="WH Admin",
            role_id=role.id,
            tenant_id=tenant.id,
            branch_id=branch.id,
            is_active=True,
            is_owner=True,
        )
        user.set_password("x")
        db_session.add(user)
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
                "/warehouse/create",
                data={
                    "name": f"Storage {tid}",
                    "location": "Dubai",
                    "branch_id": branch.id,
                },
                follow_redirects=False,
            )
            assert resp.status_code in (302, 303)

            created = Warehouse.query.filter_by(
                tenant_id=tenant.id, name=f"Storage {tid}"
            ).first()
            assert created is not None
            assert created.branch_id == branch.id
            assert created.is_active is True

            resp = client.get("/warehouse/list")
            assert resp.status_code == 200
            assert f"Storage {tid}".encode() in resp.data
