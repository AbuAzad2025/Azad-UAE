"""
Integration tests: Ledger manual journal entry routes.
"""

import uuid


class TestLedgerManualEntry:
    def test_ledger_journal_entry_creates_balanced_gl(self, app, db_session, client):
        from models import Tenant, Branch, User, Role, Permission
        from services.gl_service import GLService
        from services.gl_helpers import get_account

        tid = str(uuid.uuid4())[:8]
        tenant = Tenant(
            name=f"Test {tid}",
            name_ar=f"Test {tid}",
            slug=f"test-ledger-{tid}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(tenant)
        db_session.flush()

        branch = Branch(tenant_id=tenant.id, name=f"Main {tid}", code=f"BR{tid[:4]}")
        db_session.add(branch)
        db_session.flush()

        GLService.ensure_core_accounts(tenant_id=tenant.id)
        db_session.commit()

        cogs = get_account("5100", tenant.id)
        sales = get_account("4100", tenant.id)
        assert cogs is not None
        assert sales is not None

        perm = Permission.query.filter_by(code="manage_ledger").first()
        if perm is None:
            perm = Permission(
                code="manage_ledger",
                name="Manage Ledger",
                name_ar="إدارة دفتر الأستاذ",
                category="finance",
            )
            db_session.add(perm)
            db_session.flush()

        role = Role(name=f"Acc {tid}", slug=f"acc-{tid}", is_active=True)
        role.permissions.append(perm)
        db_session.add(role)
        db_session.flush()

        user = User(
            username=f"acctest-{tid}",
            email=f"acctest-{tid}@test.com",
            full_name="Accountant",
            tenant_id=tenant.id,
            role_id=role.id,
            branch_id=branch.id,
            is_active=True,
            is_owner=False,
        )
        user.set_password("pass123")
        db_session.add(user)
        db_session.commit()

        with client:
            resp = client.post(
                "/auth/login",
                data={
                    "username": user.username,
                    "password": "pass123",
                },
                follow_redirects=True,
            )
            assert resp.status_code == 200

            resp = client.post(
                "/ledger/manual-entry",
                data={
                    "description": "Test manual entry",
                    "entry_date": "2026-06-23",
                    "branch_id": str(branch.id),
                    "line_0_account": "5100",
                    "line_0_debit": "200",
                    "line_0_credit": "0",
                    "line_0_description": "COGS test",
                    "line_1_account": "4100",
                    "line_1_debit": "0",
                    "line_1_credit": "200",
                    "line_1_description": "Sales test",
                },
                follow_redirects=False,
            )
            assert resp.status_code == 302, f"Expected redirect, got {resp.status_code}"

        from models import GLJournalEntry

        entry = GLJournalEntry.query.filter_by(description="Test manual entry").first()
        assert entry is not None, "Journal entry was not created"
        assert entry.is_balanced(), (
            f"Entry is not balanced: debit={entry.total_debit} credit={entry.total_credit}"
        )
        assert entry.entry_type == "manual"

    def test_ledger_unauthorized_user_cannot_post(self, app, db_session):
        """User without manage_ledger permission gets 403."""
        from models import Tenant, Branch, User, Role
        import uuid

        tid = str(uuid.uuid4())[:8]
        tenant = Tenant(
            name=f"Unauth {tid}",
            name_ar=f"Unauth {tid}",
            slug=f"unauth-{tid}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(tenant)
        db_session.flush()
        branch = Branch(tenant_id=tenant.id, name=f"Main {tid}", code=f"BR{tid[:4]}")
        db_session.add(branch)
        db_session.flush()
        role = Role(name=f"Restricted {tid}", slug=f"restricted-{tid}", is_active=True)
        db_session.add(role)
        db_session.flush()
        u = User(
            username=f"no-perm-{tid}",
            email=f"noperm-{tid}@test.com",
            tenant_id=tenant.id,
            role_id=role.id,
            branch_id=branch.id,
            is_active=True,
        )
        u.set_password("password123")
        db_session.add(u)
        db_session.commit()
        with app.test_client() as client:
            client.post(
                "/auth/login",
                data={"username": f"no-perm-{tid}", "password": "password123"},
                follow_redirects=True,
            )
            resp = client.post(
                "/ledger/manual-entry",
                data={
                    "description": "Hack attempt",
                    "entry_date": "2026-06-23",
                    "line_0_account": "5100",
                    "line_0_debit": "100",
                    "line_0_credit": "0",
                },
            )
            assert resp.status_code == 403
