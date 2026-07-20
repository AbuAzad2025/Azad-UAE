import werkzeug.exceptions


def _clean_db(db_session):
    """Remove stale test data from shared session-scoped database."""
    from extensions import db

    db.session.execute(
        db.text("TRUNCATE TABLE invoice_settings, login_history, users, roles, tenants RESTART IDENTITY CASCADE")
    )
    db.session.commit()
    db_session.expire_all()


class TestOwnerDashboardAccess:
    def test_owner_dashboard_returns_404_for_non_owner(self, client, db_session):
        _clean_db(db_session)
        import uuid
        from models import User, Role, Tenant

        uid = str(uuid.uuid4())[:8]
        tenant = Tenant(
            name=f"TestCo {uid}",
            name_ar=f"TestCo AR {uid}",
            slug=f"testco-{uid}",
            default_currency="AED",
        )
        db_session.add(tenant)
        db_session.commit()

        role = Role(name=f"Cashier {uid}", slug=f"cashier-{uid}")
        db_session.add(role)
        db_session.commit()

        user = User(
            username=f"cashier_user_{uid}",
            email=f"cashier_{uid}@test.com",
            full_name="Cashier User",
            role_id=role.id,
            tenant_id=tenant.id,
            is_owner=False,
            is_active=True,
        )
        user.set_password("password123")
        db_session.add(user)
        db_session.commit()

        with client:
            client.post(
                "/auth/login",
                data={
                    "username": f"cashier_user_{uid}",
                    "password": "password123",
                },
                follow_redirects=True,
            )

            try:
                resp = client.get("/owner/dashboard", follow_redirects=False)
            except werkzeug.exceptions.NotFound:
                pass
            else:
                assert resp.status_code == 404

    def test_owner_dashboard_renders_for_platform_owner(self, client, db_session):
        _clean_db(db_session)
        import uuid
        from models import User, Role, Tenant
        from models.invoice_settings import InvoiceSettings

        uid = str(uuid.uuid4())[:8]
        tenant = Tenant(
            name=f"PlatCo {uid}",
            name_ar=f"PlatCo AR {uid}",
            slug=f"platco-{uid}",
            default_currency="AED",
        )
        db_session.add(tenant)
        db_session.commit()

        role = Role(name=f"OwnerRole {uid}", slug=f"owner-{uid}")
        db_session.add(role)
        db_session.commit()

        owner = User(
            username=f"platform_owner_{uid}",
            email=f"owner_{uid}@test.com",
            full_name="Platform Owner",
            role_id=role.id,
            tenant_id=None,
            is_owner=True,
            is_active=True,
        )
        owner.set_password("password123")
        db_session.add(owner)
        db_session.commit()

        inv = InvoiceSettings(is_active=True, tenant_id=tenant.id)
        db_session.add(inv)
        db_session.commit()

        with client:
            client.post(
                "/auth/login",
                data={
                    "username": f"platform_owner_{uid}",
                    "password": "password123",
                },
                follow_redirects=True,
            )

            with client.session_transaction() as sess:
                sess["active_tenant_id"] = str(tenant.id)

            resp = client.get("/owner/dashboard", follow_redirects=False)
            assert resp.status_code == 200
