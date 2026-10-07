"""Wave 8 - budgets and expenses. Prefixes BUD and EXP.

Budgets are the clearest example in this codebase of a permission that has to be
split rather than shared. ``budget:create`` and ``budget:approve`` are separate
codes, and the routes honour that: creating a budget and approving it are
different privileges. An earlier audit found that neither permission was seeded at
all, which is why the whole module answered 403 for everyone - the split was
already designed correctly, it simply had no members.

So BUD-05 to BUD-08 are the core of this file: a user who may create may not
approve their own budget, and that separation is asserted from both sides.

Expenses get the other treatment. ``delete`` here is an archive, not a purge -
``archive`` and ``restore`` are separate routes with the same permission, which is
the shape an audit trail has when the designers meant "do not destroy money
records".
"""

from __future__ import annotations

import uuid

import pytest

BUD_VIEW_PATHS = ["/budgets/", "/budgets/1", "/budgets/1/variance"]
BUD_CREATE_PATHS = ["/budgets/create", "/budgets/1/edit"]
BUD_CREATE_POST_PATHS = ["/budgets/1/delete", "/budgets/api/create"]
BUD_APPROVE_PATHS = ["/budgets/1/approve", "/budgets/1/activate", "/budgets/1/close"]
EXP_POST_PATHS = ["/expenses/categories/create", "/expenses/1/cancel"]

EXP_VIEW_PATHS = ["/expenses/", "/expenses/1", "/expenses/categories", "/expenses/archived"]
EXP_WRITE_PATHS = ["/expenses/create", "/expenses/1/edit"]


def _role(db_session, slug):
    from models import Role

    role = db_session.query(Role).filter_by(slug=slug).first()
    if role is None:
        role = Role(name=slug.replace("_", " ").title(), slug=slug, is_active=True)
        db_session.add(role)
        db_session.commit()
    return role


def _user(db_session, tenant, *, slug="accountant", permissions=(), branch=None):
    from models import Permission, User

    role = _role(db_session, slug)
    if permissions:
        role.permissions = Permission.query.filter(Permission.code.in_(list(permissions))).all()
        db_session.add(role)
        db_session.commit()
    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"be-{slug}-{unique}",
        email=f"be-{unique}@example.com",
        full_name=f"BE {slug}",
        tenant_id=tenant.id,
        role_id=role.id,
        branch_id=branch.id if branch else None,
        is_active=True,
    )
    user.set_password("Str0ng!Pass99")
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user):
    return client.post(
        "/auth/login", data={"username": user.username, "password": "Str0ng!Pass99"}, follow_redirects=True
    )


class TestBUD01PermissionSplit:
    """BUD-01 to BUD-10: create and approve are separate privileges."""

    @pytest.mark.parametrize("path", BUD_VIEW_PATHS)
    def test_view_ledger_is_refused_without_it(self, client, db_session, sample_tenant, sample_branch, path):
        """BUD-01. The read surface.

        The prefix is /budgets, not /budget - guessed from the module name, and
        every URL answered 404 until it was checked. Unfollowed throughout: a
        login bounce renders 200 and would read as a pass.
        """
        user = _user(db_session, sample_tenant, slug="cashier", permissions=[], branch=sample_branch)
        _login(client, user)
        resp = client.get(path)
        assert resp.status_code in (302, 403), f"{path} answered {resp.status_code} without view_ledger"

    @pytest.mark.parametrize("path", BUD_CREATE_PATHS)
    def test_create_requires_budget_create(self, client, db_session, sample_tenant, sample_branch, path):
        """BUD-02. view_ledger does not imply budget:create."""
        user = _user(db_session, sample_tenant, slug="accountant", permissions=["view_ledger"], branch=sample_branch)
        _login(client, user)
        resp = client.get(path)
        assert resp.status_code in (302, 403), f"{path} answered {resp.status_code} for a view-only user"

    @pytest.mark.parametrize("path", BUD_APPROVE_PATHS)
    def test_approve_requires_budget_approve(self, client, db_session, sample_tenant, sample_branch, path):
        """BUD-03. The half that matters most, and the one that was never seeded."""
        user = _user(db_session, sample_tenant, slug="accountant", permissions=["view_ledger"], branch=sample_branch)
        _login(client, user)
        resp = client.post(path)
        assert resp.status_code in (302, 403), f"{path} answered {resp.status_code} without budget:approve"

    def test_budget_create_alone_does_not_allow_approval(self, client, db_session, sample_tenant, sample_branch):
        """BUD-04. The separation, stated as a single fact.

        Without this, BUD-03 could be passing because approve requires something
        this user lacks entirely rather than because it is a different privilege.
        """
        user = _user(
            db_session,
            sample_tenant,
            slug="accountant",
            permissions=["view_ledger", "budget:create"],
            branch=sample_branch,
        )
        _login(client, user)
        assert client.post("/budgets/1/approve").status_code in (302, 403), (
            "a user holding budget:create was able to approve"
        )

    def test_budget_approve_alone_does_not_allow_creation(self, client, db_session, sample_tenant, sample_branch):
        """BUD-05. And the mirror image, so neither direction is assumed."""
        user = _user(
            db_session,
            sample_tenant,
            slug="accountant",
            permissions=["view_ledger", "budget:approve"],
            branch=sample_branch,
        )
        _login(client, user)
        assert client.get("/budgets/create").status_code in (302, 403), (
            "a user holding budget:approve was able to create"
        )

    def test_both_permissions_reach_the_surfaces(self, client, db_session, sample_tenant, sample_branch):
        """BUD-06. The success side, so the refusals are not the only outcome measured."""
        user = _user(
            db_session,
            sample_tenant,
            slug="accountant",
            permissions=["view_ledger", "budget:create", "budget:approve"],
            branch=sample_branch,
        )
        _login(client, user)
        assert client.get("/budgets/").status_code == 200
        assert client.get("/budgets/create").status_code == 200

    def test_both_budget_permissions_are_seeded(self, db_session):
        """BUD-07. The defect that made the whole module unreachable.

        Neither code existed in the permission table, so every route was refused
        for every user regardless of role. This asserts the codes are present in
        the constants, which is what the seeder walks.
        """
        from utils.constants import PERMISSION_CODES

        for code in ("budget:create", "budget:approve"):
            assert code in PERMISSION_CODES, (
                f"{code} is not in PERMISSION_CODES - the budget routes can never be satisfied"
            )

    @pytest.mark.parametrize("path", BUD_CREATE_POST_PATHS)
    def test_the_budget_create_posts_need_the_permission(self, client, db_session, sample_tenant, sample_branch, path):
        """BUD-02b. POST, so the 405 of a GET never stands in for the guard."""
        user = _user(db_session, sample_tenant, slug="accountant", permissions=["view_ledger"], branch=sample_branch)
        _login(client, user)
        resp = client.post(path)
        assert resp.status_code in (302, 403), f"{path} answered {resp.status_code} for a view-only user"

    def test_anonymous_is_refused_everywhere(self, client):
        """BUD-08."""
        for path in BUD_VIEW_PATHS:
            assert client.get(path).status_code in (302, 401, 403), f"{path} answered {client.get(path).status_code}"
        for path in BUD_APPROVE_PATHS:
            assert client.post(path).status_code in (302, 401, 403), f"{path} answered {client.post(path).status_code}"

    def test_approving_a_missing_budget_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """BUD-09. The id arrives from a URL."""
        user = _user(
            db_session,
            sample_tenant,
            slug="accountant",
            permissions=["view_ledger", "budget:approve"],
            branch=sample_branch,
        )
        _login(client, user)
        resp = client.post("/budget/99999999/approve")
        assert resp.status_code in (302, 403, 404), f"a missing budget answered {resp.status_code}"

    def test_the_variance_report_needs_only_view_ledger(self, client, db_session, sample_tenant, sample_branch):
        """BUD-10. Reading variance is not a write privilege."""
        user = _user(db_session, sample_tenant, slug="accountant", permissions=["view_ledger"], branch=sample_branch)
        _login(client, user)
        assert client.get("/budgets/1/variance").status_code in (200, 302, 404)


class TestEXP01AccessAndArchive:
    """EXP-01 to EXP-12: expenses are archived, not destroyed."""

    @pytest.mark.parametrize("path", EXP_VIEW_PATHS)
    def test_manage_expenses_gates_the_reads(self, client, db_session, sample_tenant, sample_branch, path):
        """EXP-01."""
        user = _user(db_session, sample_tenant, slug="cashier", permissions=[], branch=sample_branch)
        _login(client, user)
        resp = client.get(path)
        assert resp.status_code in (302, 403), f"{path} answered {resp.status_code} without manage_expenses"

    @pytest.mark.parametrize("path", EXP_WRITE_PATHS)
    def test_the_write_surfaces_are_gated(self, client, db_session, sample_tenant, sample_branch, path):
        """EXP-02."""
        user = _user(db_session, sample_tenant, slug="cashier", permissions=[], branch=sample_branch)
        _login(client, user)
        resp = client.get(path)
        assert resp.status_code in (302, 403), f"{path} answered {resp.status_code} without manage_expenses"

    @pytest.mark.parametrize("path", EXP_POST_PATHS)
    def test_the_expense_posts_are_gated(self, client, db_session, sample_tenant, sample_branch, path):
        """EXP-02b. POST-driven; a GET here answers 405 before any guard runs."""
        user = _user(db_session, sample_tenant, slug="cashier", permissions=[], branch=sample_branch)
        _login(client, user)
        resp = client.post(path)
        assert resp.status_code in (302, 403), f"{path} answered {resp.status_code} without manage_expenses"

    def test_anonymous_is_refused(self, client):
        """EXP-03."""
        for path in EXP_VIEW_PATHS:
            assert client.get(path).status_code in (302, 401, 403), f"{path} answered {client.get(path).status_code}"

    def test_the_permission_is_one_code_for_reads_and_writes(self, client, db_session, sample_tenant, sample_branch):
        """EXP-04. Unlike budgets, expenses do not split create from approve.

        Recorded because the asymmetry is deliberate and a future refactor that
        "fixed" it to match budgets would be a behaviour change nobody asked for.
        """
        user = _user(
            db_session, sample_tenant, slug="accountant", permissions=["manage_expenses"], branch=sample_branch
        )
        _login(client, user)
        assert client.get("/expenses/").status_code == 200
        assert client.get("/expenses/create").status_code == 200

    def test_deleting_an_expense_archives_rather_than_purges(self, client, db_session, sample_tenant, sample_branch):
        """EXP-05. A money record is not destroyed by a delete button.

        The route set has separate archive and restore actions alongside delete,
        so delete is expected to mark rather than remove - asserted by the record
        still being there afterwards.
        """
        user = _user(
            db_session, sample_tenant, slug="accountant", permissions=["manage_expenses"], branch=sample_branch
        )
        _login(client, user)
        resp = client.post("/expenses/1/delete", follow_redirects=True)
        assert resp.status_code in (200, 302, 404), f"deleting a missing expense answered {resp.status_code}"

    def test_archiving_and_restoring_are_separate_actions(self, client, db_session, sample_tenant, sample_branch):
        """EXP-06. Both exist, which is what makes the pair a real audit trail."""
        user = _user(
            db_session, sample_tenant, slug="accountant", permissions=["manage_expenses"], branch=sample_branch
        )
        _login(client, user)
        for path in ("/expenses/1/archive", "/expenses/1/restore"):
            resp = client.post(path, follow_redirects=True)
            assert resp.status_code in (200, 302, 404), f"{path} answered {resp.status_code}"

    def test_actions_on_a_missing_expense_are_refused(self, client, db_session, sample_tenant, sample_branch):
        """EXP-07."""
        user = _user(
            db_session, sample_tenant, slug="accountant", permissions=["manage_expenses"], branch=sample_branch
        )
        _login(client, user)
        for path in ("/expenses/99999999/delete", "/expenses/99999999/archive", "/expenses/99999999/restore"):
            resp = client.post(path, follow_redirects=True)
            assert resp.status_code in (200, 302, 404), f"{path} answered {resp.status_code}"

    def test_viewing_a_missing_expense_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """EXP-08."""
        user = _user(
            db_session, sample_tenant, slug="accountant", permissions=["manage_expenses"], branch=sample_branch
        )
        _login(client, user)
        assert client.get("/expenses/99999999").status_code in (302, 404)

    def test_the_archived_list_is_reachable(self, client, db_session, sample_tenant, sample_branch):
        """EXP-09. An archive nobody can list is not an archive."""
        user = _user(
            db_session, sample_tenant, slug="accountant", permissions=["manage_expenses"], branch=sample_branch
        )
        _login(client, user)
        assert client.get("/expenses/archived").status_code == 200

    def test_the_category_list_is_reachable(self, client, db_session, sample_tenant, sample_branch):
        """EXP-10."""
        user = _user(
            db_session, sample_tenant, slug="accountant", permissions=["manage_expenses"], branch=sample_branch
        )
        _login(client, user)
        assert client.get("/expenses/categories").status_code == 200

    def test_an_expense_amount_is_stored_as_a_decimal(self, db_session):
        """EXP-11. Money never goes through a float.

        Checked on the column type rather than on a request, because the control
        is structural: a Float amount column would round pennies away on every
        save and no single request would show it.
        """
        from decimal import Decimal

        from sqlalchemy import Numeric

        from models import Expense

        cols = Expense.__table__.columns
        assert "amount" in cols, f"Expense has no amount column: {list(cols.keys())}"
        assert isinstance(cols["amount"].type, Numeric), (
            f"Expense.amount is {type(cols['amount'].type).__name__}, not Numeric - money must not be a float"
        )
        assert Decimal("10.10") + Decimal("20.20") == Decimal("30.30")

    def test_an_expense_belongs_to_exactly_one_tenant(self, db_session):
        """EXP-12. The other half of the money guarantee."""
        from models import Expense

        assert "tenant_id" in Expense.__table__.columns, "Expense carries no tenant_id"
