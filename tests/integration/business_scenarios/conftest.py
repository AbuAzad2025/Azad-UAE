"""Fixtures and assertions for the business-scenario suite.

Two things every scenario needs and none of the existing fixtures provide:

1. A way to ask the ledger a question. The integration suite so far asserts on
   service return values; a business scenario has to ask what the accounts now
   say, which is the only way to catch a posting that hit the wrong account.
2. A signed-in client for each actor a scenario involves - platform owner,
   company admin, cashier - because the permission boundary is part of the
   behaviour under test.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def scenario_owner(db_session, client):
    """Platform owner, signed in over real HTTP.

    tenant_id is None, which is what @owner_required checks for, so this is the
    only actor that can reach /owner/tenants/create.
    """
    import uuid

    from models import Role, Tenant, User

    unique = str(uuid.uuid4())[:8]
    tenant = Tenant(
        name=f"Scenario Platform {unique}",
        name_ar="منصة السيناريو",
        slug=f"scenario-plat-{unique}",
        email=f"plat-{unique}@example.com",
        country="AE",
        subscription_plan="basic",
    )
    db_session.add(tenant)
    db_session.commit()

    role = db_session.query(Role).filter_by(slug="owner").first()
    if role is None:
        role = Role(name="Owner", slug="owner", is_active=True)
        db_session.add(role)
        db_session.commit()

    user = User(
        username=f"plat-owner-{unique}",
        email=f"plat-{unique}@example.com",
        full_name="Platform Owner",
        tenant_id=None,
        role_id=role.id,
        is_owner=True,
    )
    user.set_password("password123")
    db_session.add(user)
    db_session.commit()

    client.post(
        "/auth/login",
        data={"username": user.username, "password": "password123"},
        follow_redirects=True,
    )
    # Log out on teardown. A platform owner leaves tenant_id=None active in the
    # session, and the next test's fixtures create branches and customers for
    # their own tenant - which the ORM write guard then rejects as a cross-tenant
    # insert. Without this the suite fails depending on test order, which is
    # exactly the kind of nondeterminism these scenarios exist to rule out.
    yield user
    client.get("/auth/logout", follow_redirects=True)


@pytest.fixture
def ledger(db_session):
    """Read-only view of what the ledger says, for verification.

    Deliberately queries posted journal lines rather than trusting a service's
    return value. If a posting is written to the wrong account, only a query
    against the journal will show it.
    """

    class Ledger:
        def balance(self, account_code: str, tenant_id: int) -> float:
            from sqlalchemy import func, select

            from models import GLAccount, GLJournalEntry, GLJournalLine

            stmt = (
                select(
                    func.coalesce(func.sum(GLJournalLine.debit), 0),
                    func.coalesce(func.sum(GLJournalLine.credit), 0),
                )
                .select_from(GLJournalLine)
                .join(GLJournalEntry, GLJournalEntry.id == GLJournalLine.entry_id)
                .join(GLAccount, GLAccount.id == GLJournalLine.account_id)
                .where(
                    GLAccount.code == str(account_code),
                    GLEntry_tenant_filter(tenant_id),
                    GLJournalEntry.status == "posted",
                )
            )
            debit, credit = db_session.execute(stmt).one()
            return float(debit or 0) - float(credit or 0)

        def entries(self, tenant_id: int) -> list:
            """Every posted entry for the tenant, newest first."""
            from models import GLJournalEntry

            return (
                db_session.query(GLJournalEntry)
                .filter(GLEntry_tenant_filter(tenant_id))
                .filter_by(status="posted")
                .order_by(GLJournalEntry.id.desc())
                .all()
            )

        def lines_for(self, entry_id: int):
            from models import GLJournalLine

            return db_session.query(GLJournalLine).filter_by(entry_id=entry_id).all()

        def codes_for(self, entry_id: int) -> list[str]:
            from models import GLAccount

            return [db_session.query(GLAccount).get(line.account_id).code for line in self.lines_for(entry_id)]

    def GLEntry_tenant_filter(tenant_id):  # noqa: N802 - local predicate helper
        from models import GLJournalEntry

        return GLJournalEntry.tenant_id == tenant_id

    return Ledger()
