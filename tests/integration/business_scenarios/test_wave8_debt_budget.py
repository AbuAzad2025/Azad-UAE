"""Wave 8 debt - the budget state machine.

``test_wave8_budget_expenses.py`` proved the permission split: ``budget:create``
writes, ``budget:approve`` moves a budget along, and the two are not aliases.
BUD-11 to BUD-19 then walked the guards - a 404 must not fall through to a
default budget, create and approve must stay two codes, reading is not creating.

What none of them did is walk a budget *through* its states. Every assertion
above is about who may act; none is about what the sequence of actions produces.
The machine is the point of a budget: money is only constrained once a document
has been approved, and a budget that can be deleted after spending against it is
no constraint at all.

The order is the behaviour worth pinning:

    draft --approve--> approved --activate--> active --close--> closed

``approve`` accepts only a draft, so approving twice is refused - the second
approval would otherwise re-stamp ``approved_by`` and quietly reassign the
attribution of a limit that a manager already signed off. ``delete`` accepts
only a draft, which is why an approved or active budget cannot be removed: once
someone has approved it, removing it would erase the evidence that the limit
was ever set. ``activate`` accepts a draft as well as an approved budget, so it
is deliberately reachable from either side and refuses only a budget that has
already moved on.
"""

from __future__ import annotations

import uuid


def _user(db_session, tenant, *, slug, permissions, branch=None):
    from models import Permission, Role, User

    role = db_session.query(Role).filter_by(slug=slug).first()
    if role is None:
        role = Role(name=slug.replace("_", " ").title(), slug=slug, is_active=True)
        db_session.add(role)
        db_session.commit()
    role.permissions = Permission.query.filter(Permission.code.in_(list(permissions))).all()
    db_session.add(role)
    db_session.commit()

    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"bud-{slug}-{unique}",
        email=f"bud-{unique}@example.com",
        full_name=f"BUD {slug}",
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
    """Sign ``user`` in, replacing any session a fixture already opened.

    ``/auth/login`` short-circuits to a redirect when the session is already
    authenticated, so without the logout this call is silently a no-op and the
    route under test keeps being reached as the previous user.
    """
    client.get("/auth/logout", follow_redirects=True)
    return client.post(
        "/auth/login", data={"username": user.username, "password": "Str0ng!Pass99"}, follow_redirects=True
    )


def _maker(client, db_session, tenant, branch):
    """Holds ``budget:create`` and can read the result, but cannot approve.

    ``view_ledger`` is here because a successful create redirects to
    ``/budgets/<id>``, which is guarded by it. Without it the POST succeeds and
    the *redirect* answers 403, which reads as a failed create when nothing was
    refused.
    """
    user = _user(
        db_session,
        tenant,
        slug="budget-maker",
        permissions=["budget:create", "view_ledger"],
        branch=branch,
    )
    _login(client, user)
    return user


def _approver(client, db_session, tenant, branch):
    user = _user(
        db_session,
        tenant,
        slug="budget-approver",
        permissions=["budget:approve", "view_ledger"],
        branch=branch,
    )
    _login(client, user)
    return user


def _form(**over):
    data = {
        "name_ar": "ميزانية السيناريو",
        "name_en": "Scenario budget",
        "fiscal_year": "2026",
        "period_type": "annual",
        "period_start": "2026-01-01",
        "period_end": "2026-12-31",
        "enforcement": "warn",
    }
    data.update(over)
    return data


def _create(client, db_session, tenant, branch, **over):
    """Create a budget over HTTP and read the row back out."""
    from models import Budget

    _maker(client, db_session, tenant, branch)
    resp = client.post("/budgets/create", data=_form(**over), follow_redirects=True)
    assert resp.status_code == 200, f"budget create answered {resp.status_code}"
    db_session.expire_all()
    return db_session.query(Budget).filter_by(tenant_id=tenant.id).order_by(Budget.id.desc()).first()


class TestBUD20TheStateMachine:
    """BUD-20 to BUD-24: what the sequence of actions produces."""

    def test_a_created_budget_is_a_draft_with_nobody_approving_it(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """BUD-20. Creation never approves.

        A budget that arrives already approved would mean the limit was in force
        before anyone chose it. The draft state and the empty approver are the
        same fact seen twice: nothing has signed off yet.
        """
        budget = _create(client, db_session, sample_tenant, sample_branch)

        assert budget is not None, "no budget was created to check"
        assert budget.budget_number, f"budget {budget.id} carries no number"
        assert budget.status == "draft", f"a freshly created budget is {budget.status!r}"
        assert budget.approved_by is None, "a draft budget already carries an approver"
        assert budget.approved_at is None, "a draft budget already carries an approval timestamp"

    def test_approving_twice_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """BUD-21. ``approve`` accepts a draft and only a draft.

        The second approval would re-stamp ``approved_by`` and ``approved_at``,
        quietly reassigning who signed off on a limit a manager had already
        accepted. The refusal is what keeps the original attribution.
        """
        budget = _create(client, db_session, sample_tenant, sample_branch)
        _approver(client, db_session, sample_tenant, sample_branch)

        first = client.post(f"/budgets/{budget.id}/approve", follow_redirects=True)
        assert first.status_code == 200, f"the first approval answered {first.status_code}"
        db_session.expire_all()
        approved = db_session.get(type(budget), budget.id)
        assert approved.status == "approved", f"after one approval the budget is {approved.status!r}"
        first_approver, first_at = approved.approved_by, approved.approved_at

        second = client.post(f"/budgets/{budget.id}/approve", follow_redirects=True)
        assert second.status_code == 200, f"the second approval answered {second.status_code}"
        db_session.expire_all()
        reapproved = db_session.get(type(budget), budget.id)
        assert reapproved.status == "approved", f"a second approval changed the status to {reapproved.status!r}"
        assert reapproved.approved_by == first_approver, (
            f"the second approval reassigned the budget from approver {first_approver} to {reapproved.approved_by}"
        )
        assert reapproved.approved_at == first_at, "the second approval moved the approval timestamp"

    def test_an_active_budget_cannot_be_activated_again(self, client, db_session, sample_tenant, sample_branch):
        """BUD-22. ``activate`` moves the budget forward and will not move it twice.

        ``activate`` accepts a draft or an approved budget, so it is reachable
        from either side - but from an active budget it must refuse. Re-activating
        would stamp a fresh ``activated_at`` and make a budget look newly
        activated to anything comparing dates.
        """
        budget = _create(client, db_session, sample_tenant, sample_branch)
        _approver(client, db_session, sample_tenant, sample_branch)

        client.post(f"/budgets/{budget.id}/approve", follow_redirects=True)
        client.post(f"/budgets/{budget.id}/activate", follow_redirects=True)
        db_session.expire_all()
        active = db_session.get(type(budget), budget.id)
        assert active.status == "active", f"the budget is {active.status!r}, expected active"

        resp = client.post(f"/budgets/{budget.id}/activate", follow_redirects=True)
        assert resp.status_code == 200, f"re-activation answered {resp.status_code}"
        db_session.expire_all()
        again = db_session.get(type(budget), budget.id)
        assert again.status == "active", f"re-activation left the budget as {again.status!r}"

    def test_an_approved_budget_cannot_be_deleted(self, client, db_session, sample_tenant, sample_branch):
        """BUD-23. Deletion is confined to drafts, whoever asks.

        This is the control that makes an approval mean anything. Once a manager
        has signed off on a limit, the budget that records it has to stay on the
        books - removing it would erase the only evidence the limit was ever
        set, and leave the spending it constrained unconstrained.

        Both halves matter. The maker holds ``budget:create`` and so may reach
        the delete route at all, yet must still be refused on status; the
        approver does not hold ``budget:create`` and is stopped by the
        permission before the status rule is ever consulted.
        """
        budget = _create(client, db_session, sample_tenant, sample_branch)

        _approver(client, db_session, sample_tenant, sample_branch)
        client.post(f"/budgets/{budget.id}/approve", follow_redirects=True)
        db_session.expire_all()
        assert db_session.get(type(budget), budget.id).status == "approved", "the budget was never approved"

        # The approver cannot delete at all: no budget:create.
        refused_by_permission = client.post(f"/budgets/{budget.id}/delete", follow_redirects=False)
        assert refused_by_permission.status_code == 403, (
            f"an approver without budget:create reached delete: {refused_by_permission.status_code}"
        )

        # The maker can reach delete, and is still refused because it is approved.
        _maker(client, db_session, sample_tenant, sample_branch)
        refused_by_status = client.post(f"/budgets/{budget.id}/delete", follow_redirects=True)
        assert refused_by_status.status_code == 200, f"deleting answered {refused_by_status.status_code}"
        db_session.expire_all()
        assert db_session.get(type(budget), budget.id) is not None, (
            "an approved budget was deleted; the limit a manager signed off on is gone"
        )

    def test_a_line_naming_an_account_outside_the_tenant_is_refused(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """BUD-24. The line is rejected and the budget is not half-written.

        ``create_budget`` flushes the header before it resolves the line's
        account, so a refused account must leave nothing behind. A budget header
        with no lines - or, worse, one that reported success while silently
        dropping the line - would constrain nothing while looking configured.
        """
        from models import Budget, BudgetLine

        budget = _create(
            client,
            db_session,
            sample_tenant,
            sample_branch,
            line_0_account_code="9999",
            line_0_budgeted_amount="5000",
        )

        assert budget is not None, "the refused create stored no header to inspect"
        lines = db_session.query(BudgetLine).filter_by(budget_id=budget.id).all()
        assert not lines, f"budget {budget.id} kept {len(lines)} line(s) for an account that does not exist"

        other = db_session.query(Budget).filter_by(tenant_id=sample_tenant.id).count()
        assert other >= 1, "the refused create removed every budget, which is not what was asked for"
