"""Wave 8 debt - the expense category's account validation, branch by branch.

``test_wave8_budget_expenses.py`` proved expenses are gated by a single
``manage_expenses`` code and walked create/archive/restore. ``_validate_gl_account_code``
was exercised for its happy path and not for its refusals.

That is the wrong way round, because every branch in it exists to stop the same
class of defect: an expense posted to an account that is not an expense account.
The entry still balances. Dr and Cr agree to the fils. And it is completely
wrong - the expense has been capitalised into receivables, or written off
against a liability, and the trial balance still adds up while every ratio on
top of it is nonsense.

So each branch gets its own scenario, and the refusal is asserted as a refusal
rather than as "not a 200":

- the code does not exist,
- the account is a header (a total, not something you can post to),
- the account is inactive,
- the code is on the explicit restricted list,
- the code is in a balance-sheet class (1-4) that is not on that list,
- a real expense code is accepted,
- and no code at all is accepted, because a category is allowed to be posted to
  the default expense account.

The last two matter as much as the refusals. A validator that rejects
everything is as broken as one that accepts everything, and only the accepting
cases prove the refusals are discriminating rather than blanket.
"""

from __future__ import annotations

import uuid


def _user(db_session, tenant, *, slug="expense-categorist", permissions=("manage_expenses",), branch=None):
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
        username=f"expc-{slug}-{unique}",
        email=f"expc-{unique}@example.com",
        full_name=f"EXP {slug}",
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


def _categories(db_session, tenant):
    """Provision the tenant's chart through the production path."""
    from services.gl_service import GLService

    GLService.ensure_core_accounts(tenant_id=tenant.id)
    db_session.expire_all()


def _account(db_session, tenant, code):
    from models import GLAccount

    return db_session.query(GLAccount).filter_by(tenant_id=tenant.id, code=str(code)).first()


def _post(client, db_session, tenant, branch, code):
    """Create a category over the JSON branch of the route and return the response."""
    user = _user(db_session, tenant, branch=branch)
    _login(client, user)
    payload = {
        "name": f"Cat-{uuid.uuid4().hex[:6]}",
        "name_ar": "فئة",
    }
    if code is not None:
        payload["gl_account_code"] = code
    return client.post("/expenses/categories/create", json=payload, follow_redirects=False)


def _count(db_session, tenant):
    from models import ExpenseCategory

    return db_session.query(ExpenseCategory).filter_by(tenant_id=tenant.id).count()


class TestEXP37CategoryAccountValidation:
    """EXP-37 to EXP-43: every branch of _validate_gl_account_code."""

    def test_an_account_that_does_not_exist_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """EXP-37. A code with no account behind it cannot be posted to."""
        _categories(db_session, sample_tenant)
        before = _count(db_session, sample_tenant)

        resp = _post(client, db_session, sample_tenant, sample_branch, "8888")
        assert resp.status_code == 400, f"an unknown account code answered {resp.status_code}, expected a refusal"
        db_session.expire_all()
        assert _count(db_session, sample_tenant) == before, "a category was stored against a nonexistent account"

    def test_a_header_account_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """EXP-38. A header is a total, not a place to post.

        Posting a line into a header account double-counts: the header already
        aggregates its children, so a posting there is counted once as a leaf
        and again in the total above it. The entry still balances, which is
        exactly why nothing else would catch it.
        """
        from models import GLAccount

        _categories(db_session, sample_tenant)
        header = (
            db_session.query(GLAccount)
            .filter_by(tenant_id=sample_tenant.id, is_header=True)
            .order_by(GLAccount.code)
            .first()
        )
        assert header is not None, "this tenant's chart has no header account to test against"

        before = _count(db_session, sample_tenant)
        resp = _post(client, db_session, sample_tenant, sample_branch, header.code)
        assert resp.status_code == 400, f"header account {header.code} answered {resp.status_code}, expected a refusal"
        db_session.expire_all()
        assert _count(db_session, sample_tenant) == before, f"a category was stored against the header {header.code}"

    def test_an_inactive_account_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """EXP-39. A retired account is not a place to put new money.

        Deprecating an account says the code is finished. Accepting new expenses
        against it would strand entries on an account the chart no longer
        presents, where they are neither reported nor cleaned up.
        """
        _categories(db_session, sample_tenant)
        account = _account(db_session, sample_tenant, "6500")
        assert account is not None, "the tenant chart has no 6500 to deactivate"
        account.is_active = False
        db_session.commit()

        before = _count(db_session, sample_tenant)
        resp = _post(client, db_session, sample_tenant, sample_branch, "6500")
        assert resp.status_code == 400, f"an inactive account answered {resp.status_code}, expected a refusal"
        db_session.expire_all()
        assert _count(db_session, sample_tenant) == before, "a category was stored against a retired account"

    def test_an_explicitly_restricted_code_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """EXP-40. The named list is refused by name, before the class rule.

        1130 is receivables. It is a 1-code, so the class rule in EXP-41 would
        catch it too - but the explicit list is checked first and gives the
        operator a message naming the account and the reason, instead of the
        generic "must be 5xxx or 6xxx". The list exists to make the refusal
        legible for the codes most likely to be reached for by mistake.
        """
        _categories(db_session, sample_tenant)
        before = _count(db_session, sample_tenant)

        resp = _post(client, db_session, sample_tenant, sample_branch, "1130")
        assert resp.status_code == 400, f"restricted code 1130 answered {resp.status_code}, expected a refusal"
        db_session.expire_all()
        assert _count(db_session, sample_tenant) == before, "a category was stored against restricted code 1130"

    def test_a_balance_sheet_class_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """EXP-41. A 1-4 code is refused on its class, not by name.

        The restricted list is explicit; this is the general rule behind it. An
        expense that debits an asset is an expense the company has not had - it
        is stock or a prepayment wearing an expense's clothes, and every
        margin computed from the ledger would be wrong while the trial balance
        still balanced.
        """
        from models import GLAccount

        _categories(db_session, sample_tenant)
        restricted = ("1130", "1150", "1160", "2110", "2120", "2140", "3130", "3350")
        code = "1499"
        assert code not in restricted and code[0] in "1234", "the fixture code must be an unlisted balance-sheet code"

        # Built here rather than looked up: the seeded chart happens to contain no
        # postable 1-4 code outside the restricted list, so searching for one
        # would either find nothing or quietly select a listed account and turn
        # this scenario into a second copy of EXP-40.
        existing = db_session.query(GLAccount).filter_by(tenant_id=sample_tenant.id, code=code).first()
        if existing is None:
            existing = GLAccount(
                tenant_id=sample_tenant.id,
                code=code,
                name=f"Scenario prepaid {code}",
                type="asset",
                is_header=False,
                is_active=True,
                level=1,
            )
            db_session.add(existing)
            db_session.commit()
        db_session.expire_all()
        balance_sheet = db_session.query(GLAccount).filter_by(tenant_id=sample_tenant.id, code=code).first()
        assert balance_sheet is not None, f"the fixture account {code} was not stored"

        before = _count(db_session, sample_tenant)
        resp = _post(client, db_session, sample_tenant, sample_branch, balance_sheet.code)
        assert resp.status_code == 400, (
            f"balance-sheet account {balance_sheet.code} answered {resp.status_code}, expected a refusal"
        )
        db_session.expire_all()
        assert _count(db_session, sample_tenant) == before, (
            f"a category was stored against balance-sheet account {balance_sheet.code}"
        )

    def test_a_real_expense_account_is_accepted(self, client, db_session, sample_tenant, sample_branch):
        """EXP-42. The validator discriminates.

        A validator that refuses everything would pass EXP-37 to EXP-41
        perfectly while making the feature unusable. 6500 is the chart's own
        miscellaneous expense account and must be accepted.
        """
        from models import ExpenseCategory

        _categories(db_session, sample_tenant)
        resp = _post(client, db_session, sample_tenant, sample_branch, "6500")
        assert resp.status_code == 200, f"a valid expense account answered {resp.status_code}, expected acceptance"
        db_session.expire_all()

        body = resp.get_json()
        assert body is not None and "data" in body, f"the accepted category answered without data: {body}"

        created = body["data"]["category"]
        row = db_session.query(ExpenseCategory).filter_by(id=created["id"]).first()
        assert row is not None, f"category {created['id']} was reported created but is not stored"
        assert row.gl_account_code == "6500", f"the category stored {row.gl_account_code!r}, not 6500"

    def test_a_category_with_no_account_is_accepted(self, client, db_session, sample_tenant, sample_branch):
        """EXP-43. No code is a decision, not an omission.

        ``_validate_gl_account_code`` returns True immediately for a falsy code,
        and ``_build_expense_gl_lines`` then falls back to 6500. So a category
        may legitimately have no account of its own - it is not that validation
        was skipped, it is that the default was chosen deliberately.
        """
        from models import ExpenseCategory

        _categories(db_session, sample_tenant)
        resp = _post(client, db_session, sample_tenant, sample_branch, None)
        assert resp.status_code == 200, f"a category with no account answered {resp.status_code}, expected acceptance"
        db_session.expire_all()

        body = resp.get_json()
        assert body is not None and "data" in body, f"the accepted category answered without data: {body}"
        row = db_session.query(ExpenseCategory).filter_by(id=body["data"]["category"]["id"]).first()
        assert row is not None, "the category without an account was reported created but is not stored"
        assert not row.gl_account_code, f"the category stored {row.gl_account_code!r}, expected none"
