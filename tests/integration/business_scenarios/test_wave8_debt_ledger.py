"""Wave 8 debt part of Wave 8 - the admin ledger, reached by an admin.

``test_wave8_ledger.py`` and ``test_wave8_ledger_part2.py`` walk the tenant
ledger hard: three access guards, double-entry arithmetic, the closed-period
lock, reversal rules, tenant isolation, statements, period close. Sixty-one
scenarios, and every one of them asserts about *behaviour* or about the
``view_ledger``/``manage_ledger`` split on ``/ledger/*``.

The ``/admin/ledger`` blueprint was never entered. Sixteen routes, all behind
``@admin_required``, all asserting nothing beyond the fact that the guard
exists. That leaves the most consequential account management in the system
untested:

- the code/type agreement rule, ``validate_account_code_type`` - a code whose
  leading digit contradicts its declared class. An account typed ``expense``
  with code 1130 would make the trial balance sort receivables into expenses
  while every total still added up;
- the three refusals on delete - protected codes, accounts that have journal
  lines, and accounts that still have children. Each is a different reason and
  each is a different recovery;
- and the positive paths: adding a valid account, editing one, and deleting an
  account that has genuinely never been used.

That last one matters as much as the refusals. A delete guard that refused
everything would pass every scenario below while leaving no way to retire a
spare account, which is a real operational problem and the reason the guards
exist in the form they do.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest


def _admin(client, db_session, tenant, branch, *, slug="led-admin", permissions=("view_ledger", "manage_ledger")):
    """A user ``@admin_required`` accepts: role slug or name ``super_admin``.

    The permission list is irrelevant to that decorator, which is precisely why
    the two halves of this blueprint can disagree about who gets in - a user
    can be an admin with no ledger permissions at all, and that is the
    situation LED-64 pins.
    """
    from models import Permission, Role, User

    role = db_session.query(Role).filter_by(slug=slug).first()
    if role is None:
        role = Role(name=slug.replace("_", " ").title(), slug=slug, is_active=True)
        db_session.add(role)
        db_session.commit()
    if permissions:
        role.permissions = Permission.query.filter(Permission.code.in_(list(permissions))).all()
        db_session.add(role)
        db_session.commit()

    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"{slug}-{unique}",
        email=f"{slug}-{unique}@example.com",
        full_name=f"LED {slug}",
        tenant_id=tenant.id,
        role_id=role.id,
        branch_id=branch.id if branch else None,
        is_active=True,
    )
    user.set_password("Str0ng!Pass99")
    db_session.add(user)
    db_session.commit()

    client.get("/auth/logout", follow_redirects=True)
    client.post("/auth/login", data={"username": user.username, "password": "Str0ng!Pass99"}, follow_redirects=True)
    return user


def _super_admin(client, db_session, tenant, branch, *, permissions=()):
    from models import Permission, Role, User

    role = db_session.query(Role).filter_by(slug="super_admin").first()
    if role is None:
        role = Role(name="Super Admin", slug="super_admin", is_active=True)
        db_session.add(role)
        db_session.commit()
    if permissions:
        role.permissions = Permission.query.filter(Permission.code.in_(list(permissions))).all()
        db_session.add(role)
        db_session.commit()

    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"led-super-{unique}",
        email=f"led-super-{unique}@example.com",
        full_name="LED Super Admin",
        tenant_id=tenant.id,
        role_id=role.id,
        branch_id=branch.id if branch else None,
        is_active=True,
    )
    user.set_password("Str0ng!Pass99")
    db_session.add(user)
    db_session.commit()

    client.get("/auth/logout", follow_redirects=True)
    client.post("/auth/login", data={"username": user.username, "password": "Str0ng!Pass99"}, follow_redirects=True)
    return user


def _restore_permissions(db_session, role, original):
    """Put a shared role's permissions back after a test has borrowed it.

    ``super_admin`` is a singleton in practice - name and slug are both unique,
    and ``admin_required`` only accepts a holder of that name or slug - so a
    test that reshapes it reshapes it for every other test in the session. The
    failure that produces shows up hundreds of lines away as a 403 where a 500
    was expected, which is close to undebuggable from the symptom.
    """
    db_session.expire_all()
    role.permissions = list(original)
    db_session.add(role)
    db_session.commit()


def _chart(db_session, tenant):
    from models import GLAccount
    from services.gl_service import GLService

    found = (
        db_session.query(GLAccount)
        .filter_by(tenant_id=tenant.id, is_header=False, is_active=True)
        .order_by(GLAccount.code)
        .limit(2)
        .all()
    )
    if len(found) < 2:
        from utils.tenanting import without_tenant_scope

        with without_tenant_scope():
            GLService.ensure_core_accounts(tenant_id=tenant.id)
        db_session.expire_all()
        found = (
            db_session.query(GLAccount)
            .filter_by(tenant_id=tenant.id, is_header=False, is_active=True)
            .order_by(GLAccount.code)
            .limit(2)
            .all()
        )
    assert len(found) == 2, f"the tenant chart has {len(found)} postable accounts, need 2"
    return found


def _account(db_session, tenant, code):
    from models import GLAccount

    return db_session.query(GLAccount).filter_by(tenant_id=tenant.id, code=str(code)).first()


def _count(db_session, tenant):
    from models import GLAccount

    return db_session.query(GLAccount).filter_by(tenant_id=tenant.id).count()


class TestLED64TheAdminGuardIsNotThePermissionGuard:
    """LED-64: why these scenarios cannot reuse the ledger file's helpers."""

    def test_a_super_admin_with_no_ledger_permissions_is_still_an_admin(
        self, client, db_session, sample_tenant, sample_branch, request
    ):
        """LED-64. ``@admin_required`` and ``permission_required`` are different.

        ``admin_required`` accepts the ``super_admin`` role; it never looks at
        the permission table. So a super admin with an *empty* permission list
        reaches every ``/admin/ledger`` route and is refused every
        ``/ledger/*`` one. Getting this backwards in either direction would
        mean either a locked-out operator or a permission model that is not
        doing what the decorator's name suggests.
        """
        from models import Permission, Role, User

        role = db_session.query(Role).filter_by(slug="super_admin").first()
        if role is None:
            role = Role(name="Super Admin", slug="super_admin", is_active=True)
            db_session.add(role)
            db_session.commit()
        # Emptied, and restored before the test ends. This is the one row that
        # has to be named "super_admin" for admin_required to accept its holder,
        # so every admin in the suite shares it - and leaving it empty strips
        # the permissions from every sample_role built afterwards. The restore
        # is what keeps this scenario from failing unrelated tests far away.
        original = list(role.permissions)
        role.permissions = []
        db_session.add(role)
        db_session.commit()
        request.addfinalizer(lambda: _restore_permissions(db_session, role, original))

        unique = uuid.uuid4().hex[:8]
        user = User(
            username=f"led-bare-{unique}",
            email=f"led-bare-{unique}@example.com",
            full_name="LED Bare Admin",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()

        client.get("/auth/logout", follow_redirects=True)
        client.post("/auth/login", data={"username": user.username, "password": "Str0ng!Pass99"}, follow_redirects=True)

        held = Permission.query.filter(Permission.code.in_(["view_ledger"])).all()
        assert not any("view_ledger" in p.code for p in user.role.permissions), (
            "the fixture role was supposed to hold no ledger permissions"
        )
        assert held is not None

        admin_side = client.get("/admin/ledger/", follow_redirects=False)
        assert admin_side.status_code == 200, (
            f"a super admin holding no permissions was refused the admin ledger: {admin_side.status_code}"
        )

        tenant_side = client.get("/ledger/", follow_redirects=False)
        assert tenant_side.status_code == 403, (
            f"a user with no view_ledger permission reached the tenant ledger: {tenant_side.status_code}"
        )


class TestLED65AddingAnAccount:
    """LED-65 to LED-70: the add form's rules."""

    def _add(self, client, **over):
        data = {
            "code": "",
            "name": "Scenario account",
            "name_ar": "حساب",
            "type": "expense",
            "is_active": "on",
        }
        data.update(over)
        return client.post("/admin/ledger/accounts/add", data=data, follow_redirects=True)

    def test_a_code_whose_digit_contradicts_its_type_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """LED-65. The class and the code have to agree.

        ``validate_account_code_type`` requires the leading digit to match the
        declared class: 1 asset, 2 liability, 3 equity, 4 revenue, 5-6 expense.
        Storing an account typed ``expense`` under code 1130 would sort
        receivables into the expense section - and every total would still add
        up, because sorting is presentation, not arithmetic. This is the defect
        no balance assertion can see.
        """
        _chart(db_session, sample_tenant)
        _super_admin(client, db_session, sample_tenant, sample_branch)
        before = _count(db_session, sample_tenant)

        resp = self._add(client, code="1130", type="expense")
        assert resp.status_code == 200, f"a mismatched account add answered {resp.status_code}"

        db_session.expire_all()
        assert _count(db_session, sample_tenant) == before, (
            f"an account whose code contradicts its type was stored ({before} -> {_count(db_session, sample_tenant)})"
        )

    @pytest.mark.parametrize(
        ("leading", "account_type"),
        [
            ("1", "asset"),
            ("2", "liability"),
            ("3", "equity"),
            ("4", "revenue"),
            ("5", "expense"),
        ],
    )
    def test_every_matching_class_is_accepted(
        self, client, db_session, sample_tenant, sample_branch, leading, account_type
    ):
        """LED-66. The positive half, so LED-65 is discriminating.

        A validator that refused everything passes LED-65 perfectly. One
        account per class is added and each must land - and the code's leading
        digit is derived from the class under test, because an account whose
        digit does not match its type is precisely what LED-65 forbids.
        """
        from models import GLAccount

        _chart(db_session, sample_tenant)
        _super_admin(client, db_session, sample_tenant, sample_branch)
        code = f"{leading}{uuid.uuid4().int % 9000 + 1000}"

        resp = self._add(client, code=code, type=account_type)
        assert resp.status_code == 200, f"adding a {account_type} answered {resp.status_code}"

        db_session.expire_all()
        stored = db_session.query(GLAccount).filter_by(tenant_id=sample_tenant.id, code=code).first()
        assert stored is not None, f"the {account_type} account {code} was reported added but is not stored"
        assert stored.type == account_type, f"the account is stored as {stored.type!r}, not {account_type!r}"

    def test_a_duplicate_code_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """LED-67. Two accounts cannot share a code.

        The code is what every journal line and every report resolves an
        account by, so a duplicate makes an ambiguous reference that resolves
        to whichever row the database happened to return first.
        """
        from models import GLAccount

        _chart(db_session, sample_tenant)
        _super_admin(client, db_session, sample_tenant, sample_branch)
        existing = db_session.query(GLAccount).filter_by(tenant_id=sample_tenant.id).order_by(GLAccount.code).first()
        assert existing is not None, "the tenant chart is empty to test a duplicate against"
        before = _count(db_session, sample_tenant)

        resp = self._add(client, code=existing.code, type=existing.type)
        assert resp.status_code == 200, f"a duplicate code answered {resp.status_code}"

        db_session.expire_all()
        assert _count(db_session, sample_tenant) == before, (
            f"a duplicate code was stored ({before} -> {_count(db_session, sample_tenant)})"
        )

    def test_an_account_with_no_type_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """LED-68. Type is required, and is checked before the code rule.

        Without a type there is nothing to validate the leading digit *against*,
        so the form refuses rather than storing an account whose class is
        unknown.
        """
        _chart(db_session, sample_tenant)
        _super_admin(client, db_session, sample_tenant, sample_branch)
        before = _count(db_session, sample_tenant)

        resp = self._add(client, code="6540", type="")
        assert resp.status_code == 200, f"a type-less account add answered {resp.status_code}"

        db_session.expire_all()
        assert _count(db_session, sample_tenant) == before, "an account with no type was stored"

    def test_an_account_with_no_code_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """LED-69. A code is the account's identity; an empty one is not one."""
        _chart(db_session, sample_tenant)
        _super_admin(client, db_session, sample_tenant, sample_branch)
        before = _count(db_session, sample_tenant)

        resp = self._add(client, code="", type="expense")
        assert resp.status_code == 200, f"a code-less account add answered {resp.status_code}"

        db_session.expire_all()
        assert _count(db_session, sample_tenant) == before, "an account with no code was stored"

    def test_the_add_form_renders(self, client, db_session, sample_tenant, sample_branch):
        """LED-70. The page every refusal above re-renders."""
        _chart(db_session, sample_tenant)
        _super_admin(client, db_session, sample_tenant, sample_branch)

        resp = client.get("/admin/ledger/accounts/add", follow_redirects=False)
        assert resp.status_code == 200, f"the add-account form answered {resp.status_code}"


class TestLED71DeletingAnAccount:
    """LED-71 to LED-78: three refusals, one of them per reason."""

    def _unused_account(self, db_session, tenant):
        """A postable account with no journal lines and no children."""
        from models import GLAccount

        code = f"98{uuid.uuid4().int % 90 + 10}"
        account = GLAccount(
            tenant_id=tenant.id,
            code=code,
            name=f"Spare {code}",
            name_ar=f"احتياطي {code}",
            type="expense",
            is_header=False,
            is_active=True,
            level=1,
        )
        db_session.add(account)
        db_session.commit()
        return account

    def _used_account(self, db_session, tenant, branch):
        """A postable account that already carries a journal line."""
        from datetime import UTC, datetime

        from models import GLJournalEntry, GLJournalLine

        debit, credit = _chart(db_session, tenant)
        entry = GLJournalEntry(
            tenant_id=tenant.id,
            entry_date=datetime.now(UTC),
            entry_number=f"LEDX-{uuid.uuid4().hex[:10]}",
            entry_type="manual",
            branch_id=branch.id if branch is not None else None,
            description="LED delete guard",
            status="posted",
            is_posted=True,
        )
        db_session.add(entry)
        db_session.flush()
        db_session.add(
            GLJournalLine(
                entry_id=entry.id,
                tenant_id=tenant.id,
                account_id=debit.id,
                debit=Decimal("10.00"),
                credit=Decimal("0"),
                description="debit",
            )
        )
        db_session.commit()
        return debit

    def test_a_protected_account_cannot_be_deleted(self, client, db_session, sample_tenant, sample_branch):
        """LED-71. The core codes are frozen.

        ``PROTECTED_ACCOUNT_CODES`` exists because the posting engine resolves
        concepts to these codes by name. Deleting 1110 does not remove an
        account, it removes the target that every cash posting resolves to -
        and the failure surfaces later, in a transaction, as an error nobody
        can attribute back to here.
        """
        from models.gl_account_registry import PROTECTED_ACCOUNT_CODES

        _chart(db_session, sample_tenant)
        _super_admin(client, db_session, sample_tenant, sample_branch)

        protected = next(
            (
                a
                for a in (_account(db_session, sample_tenant, code) for code in PROTECTED_ACCOUNT_CODES)
                if a is not None
            ),
            None,
        )
        if protected is None:
            # Deliberately an assertion, not a skip. A skip here would leave this
            # scenario asserting nothing in exactly the environment where the
            # frozen-code guard matters most, and a scenario that can quietly
            # decide it has nothing to say is how a wave gets reported complete.
            pytest.fail(
                "none of PROTECTED_ACCOUNT_CODES exists in this tenant's chart, so the "
                "frozen-code delete guard cannot be exercised at all"
            )

        resp = client.post(f"/admin/ledger/accounts/{protected.id}/delete", follow_redirects=True)
        assert resp.status_code == 200, f"deleting a protected account answered {resp.status_code}"

        db_session.expire_all()
        assert db_session.get(type(protected), protected.id) is not None, (
            f"protected account {protected.code} was deleted"
        )

    def test_an_account_with_journal_lines_cannot_be_deleted(self, client, db_session, sample_tenant, sample_branch):
        """LED-72. A posted account is referenced by history.

        Deleting it would either cascade the history away - destroying the audit
        trail for every amount ever booked to it - or leave lines pointing at
        nothing. Neither is survivable, so it is refused.
        """
        account = self._used_account(db_session, sample_tenant, sample_branch)
        _super_admin(client, db_session, sample_tenant, sample_branch)
        account_id = account.id

        resp = client.post(f"/admin/ledger/accounts/{account_id}/delete", follow_redirects=True)
        assert resp.status_code == 200, f"deleting a used account answered {resp.status_code}"

        db_session.expire_all()
        from models import GLAccount

        assert db_session.get(GLAccount, account_id) is not None, (
            f"account {account.code}, which carries journal lines, was deleted"
        )

    def test_an_account_with_children_cannot_be_deleted(self, client, db_session, sample_tenant, sample_branch):
        """LED-73. A parent is the sum of its children.

        Deleting it would leave the children orphaned and the total they roll
        up into gone. The parent has to be emptied first.
        """
        from models import GLAccount

        _chart(db_session, sample_tenant)
        _super_admin(client, db_session, sample_tenant, sample_branch)

        parent = GLAccount(
            tenant_id=sample_tenant.id,
            code=f"97{uuid.uuid4().int % 90 + 10}",
            name="LED scenario parent",
            name_ar="حساب رئيسي",
            type="expense",
            is_header=True,
            is_active=True,
            level=1,
        )
        db_session.add(parent)
        db_session.commit()

        child = GLAccount(
            tenant_id=sample_tenant.id,
            code=f"96{uuid.uuid4().int % 90 + 10}",
            name="LED scenario child",
            name_ar="حساب فرعي",
            type="expense",
            is_header=False,
            is_active=True,
            level=2,
            parent_id=parent.id,
        )
        db_session.add(child)
        db_session.commit()
        parent_id = parent.id

        resp = client.post(f"/admin/ledger/accounts/{parent_id}/delete", follow_redirects=True)
        assert resp.status_code == 200, f"deleting a parent answered {resp.status_code}"

        db_session.expire_all()
        assert db_session.get(GLAccount, parent_id) is not None, "a parent account was deleted out from under its child"

    def test_an_unused_account_can_be_deleted(self, client, db_session, sample_tenant, sample_branch):
        """LED-74. And an account that has never been used can go.

        This is the positive half, and it is the reason the other three are
        worth having: a guard set that refuses everything leaves no way to
        retire the account someone created by mistake last quarter, so the
        chart fills with dead codes that nobody can remove.
        """
        from models import GLAccount

        _chart(db_session, sample_tenant)
        _super_admin(client, db_session, sample_tenant, sample_branch)
        account = self._unused_account(db_session, sample_tenant)
        account_id, code = account.id, account.code

        resp = client.post(f"/admin/ledger/accounts/{account_id}/delete", follow_redirects=True)
        assert resp.status_code == 200, f"deleting an unused account answered {resp.status_code}"

        db_session.expire_all()
        assert db_session.get(GLAccount, account_id) is None, (
            f"the unused account {code} survived; there is no way to retire a spare account"
        )

    def test_deleting_an_account_that_does_not_exist_is_handled(self, client, db_session, sample_tenant, sample_branch):
        """LED-75. A stale id 404s rather than deleting something else."""
        _chart(db_session, sample_tenant)
        _super_admin(client, db_session, sample_tenant, sample_branch)
        before = _count(db_session, sample_tenant)

        resp = client.post("/admin/ledger/accounts/99999999/delete", follow_redirects=False)
        assert resp.status_code in (404, 302), f"deleting a missing account answered {resp.status_code}"

        db_session.expire_all()
        after = _count(db_session, sample_tenant)
        assert after == before, f"deleting a missing account removed a row ({before} -> {after})"
