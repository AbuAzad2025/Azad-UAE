"""
Integration test: Tenant isolation — cross-tenant access must be blocked.
"""

import uuid


class TestTenantIsolation:
    def test_cross_tenant_access_is_blocked(self, app, db_session):
        from models import Tenant, Customer
        from utils.tenanting import tenant_query, get_active_tenant_id
        from flask_login import login_user, logout_user
        from models import User, Role, Branch

        # --- Setup Tenant A ---
        ta_id = str(uuid.uuid4())[:8]
        tenant_a = Tenant(
            name=f"TenantA {ta_id}",
            name_ar=f"TenantA {ta_id}",
            slug=f"tenant-a-{ta_id}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(tenant_a)
        db_session.flush()

        role_a = Role(name=f"UserA {ta_id}", slug=f"usera-{ta_id}", is_active=True)
        db_session.add(role_a)
        db_session.flush()

        branch_a = Branch(tenant_id=tenant_a.id, name=f"BrA {ta_id}", code=f"BA{ta_id[:4]}")
        db_session.add(branch_a)
        db_session.flush()

        user_a = User(
            tenant_id=tenant_a.id,
            username=f"user_a_{ta_id}",
            email=f"a_{ta_id}@test.com",
            is_active=True,
            password_hash="fakehash",
            branch_id=branch_a.id,
            role_id=role_a.id,
        )
        db_session.add(user_a)
        db_session.flush()

        customer_a = Customer(tenant_id=tenant_a.id, name=f"CustA {ta_id}", phone=f"050{ta_id}")
        db_session.add(customer_a)
        db_session.flush()

        # --- Setup Tenant B ---
        tb_id = str(uuid.uuid4())[:8]
        tenant_b = Tenant(
            name=f"TenantB {tb_id}",
            name_ar=f"TenantB {tb_id}",
            slug=f"tenant-b-{tb_id}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(tenant_b)
        db_session.flush()

        role_b = Role(name=f"UserB {tb_id}", slug=f"userb-{tb_id}", is_active=True)
        db_session.add(role_b)
        db_session.flush()

        branch_b = Branch(tenant_id=tenant_b.id, name=f"BrB {tb_id}", code=f"BB{tb_id[:4]}")
        db_session.add(branch_b)
        db_session.flush()

        user_b = User(
            tenant_id=tenant_b.id,
            username=f"user_b_{tb_id}",
            email=f"b_{tb_id}@test.com",
            is_active=True,
            password_hash="fakehash",
            branch_id=branch_b.id,
            role_id=role_b.id,
        )
        db_session.add(user_b)
        db_session.flush()

        customer_b = Customer(tenant_id=tenant_b.id, name=f"CustB {tb_id}", phone=f"050{tb_id}")
        db_session.add(customer_b)
        db_session.flush()

        # --- Test 1: Unscoped query returns all customers ---
        all_customers = Customer.query.all()
        assert len(all_customers) >= 2
        all_ids = {c.id for c in all_customers}
        assert customer_a.id in all_ids
        assert customer_b.id in all_ids

        # --- Test 2: tenant_query filters to Tenant A only ---
        with app.test_request_context():
            login_user(user_a, remember=False)

            tid = get_active_tenant_id()
            assert tid == tenant_a.id

            scoped = tenant_query(Customer).all()
            scoped_ids = {c.id for c in scoped}
            assert customer_a.id in scoped_ids, "Tenant A's own customer missing from scoped query"
            assert customer_b.id not in scoped_ids, "Tenant B's customer leaked into Tenant A's scoped query"

        with app.test_request_context():
            login_user(user_b, remember=False)

            tid = get_active_tenant_id()
            assert tid == tenant_b.id

            scoped = tenant_query(Customer).all()
            scoped_ids = {c.id for c in scoped}
            assert customer_b.id in scoped_ids, "Tenant B's own customer missing from scoped query"
            assert customer_a.id not in scoped_ids, "Tenant A's customer leaked into Tenant B's scoped query"

        # --- Test 3: Without authentication, tenant_query returns all (no tenant filter) ---
        with app.test_request_context():
            logout_user()

            tid = get_active_tenant_id()
            assert tid is None, f"Expected no active tenant, got {tid}"

            # No tenant = no filter; query returns all customers
            all_after = tenant_query(Customer).all()
            assert len(all_after) >= 2
            all_after_ids = {c.id for c in all_after}
            assert customer_a.id in all_after_ids
            assert customer_b.id in all_after_ids
