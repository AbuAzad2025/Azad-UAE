"""Template coverage for the admin/ledger (GeneralLedger) pages.

These 12 templates (``admin/ledger/*.html``) are owner-only routes under
``routes/admin_ledger.py``. The base smoke suite drives a *tenant* user
(``auth_client``) so every admin route answered 302/403 and the templates were
never rendered -> 4 of them (accounts, add_account, edit_account,
view_journal, plus the report/dashboard pages in a real-data state) were
uncovered.

THIS MODULE: logs in as the platform owner with an active tenant selected (the
``owner_records`` pattern) and renders every template with **real, committed**
records so context data is fully populated and zero Jinja variables resolve to
``None``.

WHY COMMITTED DATA: ``tests/conftest.py::db_session`` wraps fixture writes in a
savepoint (``session.begin_nested()``). ``commit()`` only releases that
savepoint, so fixture-created records stay invisible to the test client's
request sessions. ``committed_ledger_data`` therefore seeds a real Tenant +
GLAccount + GLJournalEntry (+ lines) through ``atomic_transaction`` in a fresh
app context -- a real DB commit every request session can see, with the FK from
``gl_accounts.tenant_id -> tenants.id`` satisfied.

WHY AN ACTIVE TENANT IS SET: the platform owner with ``active_tenant_id``
cleared runs in "all companies" mode, but ``GLService.get_all_account_balances``
calls ``resolve_tenant_id`` which -- when no active tenant is resolved -- counts
active tenants and raises ``ValueError`` if more than one exists. Pinning
``active_tenant_id`` to the committed tenant short-circuits that logic and keeps
the report routes deterministic.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest


@pytest.fixture(scope="module")
def committed_ledger_data(app):
    """Committed Ledger Tenant + 2 active GLAccounts + 1 posted journal entry.

    Runs in a *fresh* app context so ``atomic_transaction`` performs a real DB
    commit without touching the ``db_session`` fixture's savepoint. Because the
    commit happens outside any request context the ORM write guard is skipped,
    so the committed ``tenant_id`` values are preserved. The committed Tenant row
    also satisfies the ``gl_accounts.tenant_id -> tenants.id`` foreign key.
    """
    import uuid

    from extensions import db
    from models import GLAccount, GLJournalEntry, GLJournalLine, Tenant
    from utils.db_safety import atomic_transaction

    unique = uuid.uuid4().hex[:8]

    with app.app_context():
        with atomic_transaction("ledger_tenant_seed"):
            tenant = Tenant(
                name="Ledger Test Company",
                name_ar="شركة تجربة المحاسبة",
                slug=f"ledger-test-{unique}",
                email=f"ledger-{unique}@example.com",
                phone_1="0500000000",
                country="AE",
                subscription_plan="basic",
                default_currency="AED",
                base_currency="AED",
                is_active=True,
                is_suspended=False,
                suspension_reason=None,
            )
            db.session.add(tenant)
            db.session.flush()
            tenant_id = tenant.id

        with atomic_transaction("ledger_account_seed"):
            acct_asset = GLAccount(
                tenant_id=tenant_id,
                code="1110",
                name="Cash",
                name_ar="نقداً",
                type="asset",
                sub_type="cash",
                currency="AED",
                is_active=True,
                is_header=False,
                level=0,
            )
            acct_revenue = GLAccount(
                tenant_id=tenant_id,
                code="4100",
                name="Sales Revenue",
                name_ar="إيراد المبيعات",
                type="revenue",
                sub_type="revenue_operating",
                currency="AED",
                is_active=True,
                is_header=False,
                level=0,
            )
            db.session.add_all([acct_asset, acct_revenue])
            db.session.flush()
            asset_id = acct_asset.id
            revenue_id = acct_revenue.id

        with atomic_transaction("ledger_journal_seed"):
            entry = GLJournalEntry(
                tenant_id=tenant_id,
                entry_number=f"GL-LEDGER-{unique}",
                entry_date=datetime.now(UTC),
                description="Admin ledger coverage fixture entry",
                reference_type="manual",
                entry_type="manual",
                currency="AED",
                exchange_rate=Decimal("1"),
                total_debit=Decimal("100.000"),
                total_credit=Decimal("100.000"),
                status="posted",
                is_posted=True,
            )
            db.session.add(entry)
            db.session.flush()
            entry_id = entry.id

            db.session.add_all(
                [
                    GLJournalLine(
                        tenant_id=tenant_id,
                        entry_id=entry_id,
                        account_id=asset_id,
                        description="Debit line",
                        debit=Decimal("100.000"),
                        credit=Decimal("0.000"),
                        amount_aed=Decimal("100.000"),
                    ),
                    GLJournalLine(
                        tenant_id=tenant_id,
                        entry_id=entry_id,
                        account_id=revenue_id,
                        description="Credit line",
                        debit=Decimal("0.000"),
                        credit=Decimal("100.000"),
                        amount_aed=Decimal("-100.000"),
                    ),
                ]
            )
            db.session.flush()

    return {
        "tenant_id": tenant_id,
        "asset_id": asset_id,
        "revenue_id": revenue_id,
        "entry_id": entry_id,
    }


@pytest.fixture
def admin_owner_client(owner_client, committed_ledger_data):
    """Platform owner with an active tenant selected (see module docstring).

    Mirrors ``owner_records``: the platform owner picks a tenant to operate
    against so ``resolve_tenant_id`` and the GL helpers resolve it directly
    instead of falling into the multi-tenant auto-pick branch.
    """
    from utils.tenanting import ACTIVE_TENANT_SESSION_KEY

    with owner_client.session_transaction() as sess:
        sess[ACTIVE_TENANT_SESSION_KEY] = committed_ledger_data["tenant_id"]
    return owner_client


@pytest.fixture
def rendered_templates():
    """Capture the names of templates rendered during a request/test.

    Uses Flask's ``template_rendered`` signal (the same signal
    ``tests/conftest._on_template_rendered`` listens to) to assert the exact
    template was rendered, not just that the route returned 200.
    """
    from flask import template_rendered

    captured: list[str] = []

    def _record(sender, template, context=None, **extra):
        name = getattr(template, "name", None)
        if name:
            captured.append(name)

    template_rendered.connect(_record)
    try:
        yield captured
    finally:
        template_rendered.disconnect(_record)


EXPECTED_TEMPLATES = {
    "/admin/ledger/": "admin/ledger/dashboard.html",
    "/admin/ledger/accounts": "admin/ledger/accounts.html",
    "/admin/ledger/accounts/add": "admin/ledger/add_account.html",
    "/admin/ledger/accounts/{asset_id}/edit": "admin/ledger/edit_account.html",
    "/admin/ledger/vaults": "admin/ledger/vaults.html",
    "/admin/ledger/journals": "admin/ledger/journals.html",
    "/admin/ledger/journals/{entry_id}/view": "admin/ledger/view_journal.html",
    "/admin/ledger/reports": "admin/ledger/reports.html",
    "/admin/ledger/reports/trial-balance": "admin/ledger/trial_balance.html",
    "/admin/ledger/reports/balance-sheet": "admin/ledger/balance_sheet.html",
    "/admin/ledger/reports/income-statement": "admin/ledger/income_statement.html",
    "/admin/ledger/settings": "admin/ledger/settings.html",
}


class TestAdminLedgerTemplates:
    """Renders every admin/ledger GET route as the platform owner with data."""

    @pytest.fixture(autouse=True)
    def _data(self, admin_owner_client, committed_ledger_data):
        self.client = admin_owner_client
        self.data = committed_ledger_data

    @pytest.mark.parametrize(
        "path",
        [
            "/",
            "/accounts",
            "/accounts/add",
            "/vaults",
            "/journals",
            "/reports",
            "/reports/trial-balance",
            "/reports/balance-sheet",
            "/reports/income-statement",
            "/settings",
        ],
    )
    def test_list_and_report_routes_render(self, path, rendered_templates):
        resp = self.client.get(f"/admin/ledger{path}", follow_redirects=True)
        expected = EXPECTED_TEMPLATES[f"/admin/ledger{path}"]
        assert resp.status_code == 200, f"{path} -> {resp.status_code}"
        assert expected in rendered_templates, f"{path} did not render {expected}; rendered={rendered_templates}"

    def test_edit_account_renders(self, rendered_templates):
        path = f"/admin/ledger/accounts/{self.data['asset_id']}/edit"
        resp = self.client.get(path, follow_redirects=True)
        assert resp.status_code == 200, f"edit_account -> {resp.status_code}"
        assert "admin/ledger/edit_account.html" in rendered_templates

    def test_view_journal_renders(self, rendered_templates):
        path = f"/admin/ledger/journals/{self.data['entry_id']}/view"
        resp = self.client.get(path, follow_redirects=True)
        assert resp.status_code == 200, f"view_journal -> {resp.status_code}"
        assert "admin/ledger/view_journal.html" in rendered_templates
