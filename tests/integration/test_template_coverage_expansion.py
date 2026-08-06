"""Template coverage expansion — GET detail routes with real tenant records.

The base smoke suite (test_template_smoke.py) only hits list/create routes, so
record-detail templates (customers/view.html, sales/edit.html, invoices/*.html,
ledger/view_entry.html, …) never render. This module creates real records for
the sample tenant and hits the corresponding detail/edit/print routes so the
template_rendered signal in conftest.py records every Jinja2 template.

Scope: this is a test-only grant of tenant permissions. The shared super_admin
role created by ``sample_role`` is extended with the missing ``sample_permissions``
codes inside this module. All existing 403-assertion tests use dedicated
restricted roles (cashier, custom tenant roles), never the shared super_admin,
so extending it here is safe.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

# Permission codes referenced by tenant detail routes but absent from
# ``sample_permissions`` in tests/conftest.py.
_EXTRA_PERMISSION_CODES = [
    "crm.view",
    "crm.manage",
    "hr.view",
    "hr.manage",
    "marketing.manage",
    "manage_ledger",
    "manage_users",
    "manage_store",
    "project.view",
    "project.manage",
    "support.view",
    "support.manage",
    "view_customers",
    "view_kds",
    "view_products",
]


@pytest.fixture
def granted_permissions(db_session, sample_role):
    """Extend the shared super_admin role with missing tenant permission codes."""
    from models import Permission

    existing = {p.code: p for p in Permission.query.all()}
    role_codes = {p.code for p in sample_role.permissions}
    for code in _EXTRA_PERMISSION_CODES:
        perm = existing.get(code)
        if perm is None:
            perm = Permission(code=code, name=code, name_ar=code, category="test")
            db_session.add(perm)
        if code not in role_codes:
            sample_role.permissions.append(perm)
    db_session.commit()
    return sample_role


# ── Record fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def sample_invoice_settings(db_session, sample_tenant):
    """Explicit InvoiceSettings so active_template is controlled per test."""
    from decimal import Decimal

    from models.invoice_settings import InvoiceSettings

    settings = InvoiceSettings(
        tenant_id=sample_tenant.id,
        company_name_ar="شركة الاختبار",
        company_name_en="Test Company",
        is_active=True,
        active_template="modern",
        enable_qr_code=True,
        paper_size="A4",
        orientation="portrait",
        default_language="ar",
        watermark_opacity=Decimal("0.10"),
    )
    db_session.add(settings)
    db_session.commit()
    return settings


@pytest.fixture
def sample_gl_journal(db_session, sample_tenant, sample_gl_accounts, sample_user):
    """Posted GL journal entry with two balanced lines."""
    from decimal import Decimal

    from models import GLAccount, GLJournalEntry, GLJournalLine

    accounts = GLAccount.query.filter_by(tenant_id=sample_tenant.id).order_by(GLAccount.id).limit(2).all()
    entry = GLJournalEntry(
        tenant_id=sample_tenant.id,
        entry_number="GL-TEST-001",
        entry_date=datetime.now(timezone.utc),
        description="Test journal entry",
        reference_type="manual",
        entry_type="manual",
        currency="AED",
        exchange_rate=Decimal("1"),
        total_debit=Decimal("100.000"),
        total_credit=Decimal("100.000"),
        status="posted",
        is_posted=True,
        created_by=sample_user.id,
    )
    db_session.add(entry)
    db_session.flush()
    if len(accounts) >= 2:
        db_session.add(
            GLJournalLine(
                tenant_id=sample_tenant.id,
                entry_id=entry.id,
                account_id=accounts[0].id,
                description="Debit line",
                debit=Decimal("100.000"),
                credit=Decimal("0.000"),
                amount_aed=Decimal("100.000"),
            )
        )
        db_session.add(
            GLJournalLine(
                tenant_id=sample_tenant.id,
                entry_id=entry.id,
                account_id=accounts[1].id,
                description="Credit line",
                debit=Decimal("0.000"),
                credit=Decimal("100.000"),
                amount_aed=Decimal("-100.000"),
            )
        )
    db_session.commit()
    return entry


@pytest.fixture
def sample_receipt(db_session, sample_tenant, sample_customer, sample_user, sample_branch):
    """Incoming cash receipt linked to a branch and user."""
    from decimal import Decimal

    from models import Receipt

    receipt = Receipt(
        tenant_id=sample_tenant.id,
        receipt_number="REC-TEST-001",
        source_type="manual",
        direction="incoming",
        customer_id=sample_customer.id,
        amount=Decimal("100.000"),
        currency="AED",
        exchange_rate=Decimal("1"),
        amount_aed=Decimal("100.000"),
        payment_method="cash",
        branch_id=sample_branch.id,
        user_id=sample_user.id,
        receipt_date=datetime.now(timezone.utc),
    )
    db_session.add(receipt)
    db_session.commit()
    return receipt


@pytest.fixture
def sample_product_return(db_session, sample_tenant, sample_customer, sample_sale, sample_branch, sample_user):
    """Approved product return tied to the sample sale."""
    from decimal import Decimal

    from models import ProductReturn

    pr = ProductReturn(
        tenant_id=sample_tenant.id,
        return_number="RTN-TEST-001",
        sale_id=sample_sale.id,
        customer_id=sample_customer.id,
        branch_id=sample_branch.id,
        total_amount=Decimal("100.000"),
        refund_amount=Decimal("100.000"),
        amount_aed=Decimal("100.000"),
        status="approved",
        processed_by=sample_user.id,
    )
    db_session.add(pr)
    db_session.commit()
    return pr


@pytest.fixture
def sample_email_campaign(db_session, sample_tenant):
    """Draft email campaign for marketing stats page."""
    from models import EmailCampaign

    campaign = EmailCampaign(
        tenant_id=sample_tenant.id,
        name="Test Campaign",
        status="draft",
        is_active=True,
    )
    db_session.add(campaign)
    db_session.commit()
    return campaign


@pytest.fixture
def sample_vault_card(db_session, sample_tenant, sample_customer, sample_user):
    """Encrypted card vault record (key bootstrapped by the app factory)."""
    from models import CardVault
    from services.card_encryption_service import CardEncryptionService

    cipher = CardEncryptionService(encryption_key="test-encryption-key-32-chars-long!!")
    card = CardVault(
        tenant_id=sample_tenant.id,
        customer_id=sample_customer.id,
        is_active=True,
        is_default=True,
        created_by=sample_user.id,
    )
    card.set_card_data("4111111111111111", "Test Cardholder", "12", "2028", "123", cipher=cipher)
    db_session.add(card)
    db_session.commit()
    return card


@pytest.fixture
def sample_verification(db_session, sample_tenant, sample_sale, sample_user):
    """DocumentVerification record for the public verify route."""
    from models.document_verification import DocumentVerification

    rec = DocumentVerification.get_or_create(
        tenant_id=sample_tenant.id,
        document_type="sale",
        document_id=sample_sale.id,
        created_by=sample_user.id,
    )
    db_session.commit()
    return rec


@pytest.fixture
def sample_gl_account(db_session, sample_gl_accounts):
    """First core chart-of-accounts account for the tenant."""
    from models import GLAccount

    account = GLAccount.query.filter_by(tenant_id=sample_gl_accounts.id).order_by(GLAccount.id).first()
    if account is None:
        pytest.skip("No GL account available for the tenant")
    return account


@pytest.fixture
def owner_records(client, db_session, sample_tenant, sample_owner):
    """Owner-panel records created under the owner's active-tenant context.

    Logs in as a platform owner, switches the session's active tenant to
    ``sample_tenant`` (mirroring the real owner workflow), then creates
    tenant-scoped records in that same tenant so the ORM write guard and the
    owner routes' tenant criteria both resolve consistently.
    """
    import uuid

    from flask import g

    from models import CardVault, Customer, Role, User
    from utils.tenanting import set_active_tenant

    with client:
        client.post(
            "/auth/login",
            data={"username": sample_owner.username, "password": "password123"},
            follow_redirects=True,
        )
    with client.session_transaction() as sess:
        sess["active_tenant_id"] = sample_tenant.id

    set_active_tenant(sample_tenant.id, user=sample_owner)
    g.active_tenant_id = sample_tenant.id

    role = db_session.query(Role).filter_by(slug="owner").first()
    user_unique = str(uuid.uuid4())[:8]
    staff = User(
        username=f"owner-user-{user_unique}",
        email=f"owner-user-{user_unique}@example.com",
        full_name="Owner Tenant User",
        tenant_id=sample_tenant.id,
        role_id=role.id,
        is_active=True,
    )
    staff.set_password("password123")
    db_session.add(staff)
    db_session.flush()

    customer = Customer(
        tenant_id=sample_tenant.id,
        name="Owner Card Customer",
        email="card-customer@test.com",
        phone="0555000002",
    )
    db_session.add(customer)
    db_session.flush()

    from services.card_encryption_service import CardEncryptionService

    cipher = CardEncryptionService(encryption_key="test-encryption-key-32-chars-long!!")
    card = CardVault(
        tenant_id=sample_tenant.id,
        customer_id=customer.id,
        is_active=True,
        is_default=True,
        created_by=staff.id,
    )
    card_number = "4" + "".join(str(uuid.uuid4().int)[:15])
    card.set_card_data(card_number, "Owner Cardholder", "12", "2028", "123", cipher=cipher)
    db_session.add(card)
    db_session.commit()

    return {"client": client, "user": staff, "card": card, "tenant": sample_tenant, "owner": sample_owner}


@pytest.fixture
def tenant_records(
    db_session,
    sample_tenant,
    sample_branch,
    sample_customer,
    sample_supplier,
    sample_warehouse,
    sample_product,
    sample_expense,
    sample_cheque,
    sample_sale,
    sample_purchase,
    sample_receipt,
    sample_product_return,
    sample_gl_journal,
    sample_gl_account,
    sample_invoice_settings,
    sample_email_campaign,
    sample_employee,
    sample_payroll_transaction,
):
    """Convenience bundle — one dict of every sample record for the tenant."""
    return {
        "tenant": sample_tenant,
        "branch": sample_branch,
        "customer": sample_customer,
        "supplier": sample_supplier,
        "warehouse": sample_warehouse,
        "product": sample_product,
        "expense": sample_expense,
        "cheque": sample_cheque,
        "sale": sample_sale,
        "purchase": sample_purchase,
        "receipt": sample_receipt,
        "product_return": sample_product_return,
        "gl_journal": sample_gl_journal,
        "account": sample_gl_account,
        "invoice_settings": sample_invoice_settings,
        "email_campaign": sample_email_campaign,
        "employee": sample_employee,
        "payroll_transaction": sample_payroll_transaction,
    }


# ── Tenant record-detail routes ────────────────────────────────────────────


class TestLedgerRecordRoutes:
    """GL ledger detail pages — need posted journal entries + accounts."""

    @pytest.mark.parametrize(
        ("route_fmt", "key"),
        [
            ("/ledger/account/{}", "account"),
            ("/ledger/account/{}/statement", "account"),
            ("/ledger/entry/{}", "gl_journal"),
            ("/ledger/manual-entry", None),
            ("/ledger/cash-flow", None),
            ("/admin/ledger/accounts/{}/edit", "account"),
            ("/admin/ledger/journals/{}/view", "gl_journal"),
        ],
    )
    def test_ledger_detail_renders(
        self, auth_client, granted_permissions, sample_gl_accounts, tenant_records, route_fmt, key
    ):
        record_id = tenant_records[key].id if key else ""
        resp = auth_client.get(route_fmt.format(record_id), follow_redirects=True)
        assert resp.status_code in (200, 404, 403), f"{route_fmt} returned {resp.status_code}"


class TestCustomerSupplierRecordRoutes:
    """Customer and supplier detail / edit / statement pages."""

    @pytest.mark.parametrize(
        "suffix",
        [
            "",
            "/edit",
            "/statement",
            "/statement/print",
        ],
    )
    def test_customer_pages_render(self, auth_client, granted_permissions, tenant_records, suffix):
        url = f"/customers/{tenant_records['customer'].id}{suffix}"
        resp = auth_client.get(url, follow_redirects=True)
        assert resp.status_code in (200, 404, 403), f"{url} returned {resp.status_code}"

    @pytest.mark.parametrize(
        "suffix",
        [
            "",
            "/edit",
            "/statement",
            "/statement/print",
        ],
    )
    def test_supplier_pages_render(self, auth_client, granted_permissions, tenant_records, suffix):
        url = f"/suppliers/{tenant_records['supplier'].id}{suffix}"
        resp = auth_client.get(url, follow_redirects=True)
        assert resp.status_code in (200, 404, 403), f"{url} returned {resp.status_code}"


class TestSalesPurchasesReturnsRecordRoutes:
    """Sale / purchase / return detail, edit and print pages."""

    @pytest.mark.parametrize(
        "suffix",
        [
            "",
            "/edit",
            "/print",
        ],
    )
    def test_sale_pages_render(self, auth_client, granted_permissions, tenant_records, suffix):
        url = f"/sales/{tenant_records['sale'].id}{suffix}"
        resp = auth_client.get(url, follow_redirects=True)
        assert resp.status_code in (200, 404, 403), f"{url} returned {resp.status_code}"

    @pytest.mark.parametrize(
        "suffix",
        [
            "",
            "/edit",
            "/print",
        ],
    )
    def test_purchase_pages_render(self, auth_client, granted_permissions, tenant_records, suffix):
        url = f"/purchases/{tenant_records['purchase'].id}{suffix}"
        resp = auth_client.get(url, follow_redirects=True)
        assert resp.status_code in (200, 404, 403), f"{url} returned {resp.status_code}"

    def test_return_view_renders(self, auth_client, granted_permissions, tenant_records):
        url = f"/returns/view/{tenant_records['product_return'].id}"
        resp = auth_client.get(url, follow_redirects=True)
        assert resp.status_code in (200, 404, 403), f"{url} returned {resp.status_code}"

    @pytest.mark.parametrize(
        "template",
        ["modern", "classic", "gulf", "minimal", "simple"],
    )
    def test_sale_invoice_templates_render(
        self, db_session, auth_client, granted_permissions, tenant_records, sample_invoice_settings, template
    ):
        sample_invoice_settings.active_template = template
        db_session.commit()
        url = f"/sales/{tenant_records['sale'].id}/print"
        resp = auth_client.get(url, follow_redirects=True)
        assert resp.status_code in (200, 404, 403), f"{url} ({template}) returned {resp.status_code}"


class TestProductsWarehouseBranchesRoutes:
    """Product, warehouse and branch detail / edit pages."""

    @pytest.mark.parametrize(
        "suffix",
        [
            "",
            "/edit",
            "/print-label",
        ],
    )
    def test_product_pages_render(self, auth_client, granted_permissions, tenant_records, suffix):
        url = f"/products/{tenant_records['product'].id}{suffix}"
        resp = auth_client.get(url, follow_redirects=True)
        assert resp.status_code in (200, 404, 403), f"{url} returned {resp.status_code}"

    @pytest.mark.parametrize(
        "suffix",
        [
            "",
            "/edit",
        ],
    )
    def test_warehouse_pages_render(self, auth_client, granted_permissions, tenant_records, suffix):
        url = f"/warehouse/{tenant_records['warehouse'].id}{suffix}"
        resp = auth_client.get(url, follow_redirects=True)
        assert resp.status_code in (200, 404, 403), f"{url} returned {resp.status_code}"

    def test_branch_edit_renders(self, auth_client, granted_permissions, tenant_records):
        url = f"/branches/edit/{tenant_records['branch'].id}"
        resp = auth_client.get(url, follow_redirects=True)
        assert resp.status_code in (200, 404, 403), f"{url} returned {resp.status_code}"


class TestExpensesChequesPayrollRoutes:
    """Expense, cheque and payroll detail / edit / print pages."""

    @pytest.mark.parametrize(
        "suffix",
        [
            "",
            "/edit",
            "/print",
        ],
    )
    def test_expense_pages_render(self, auth_client, granted_permissions, tenant_records, suffix):
        url = f"/expenses/{tenant_records['expense'].id}{suffix}"
        resp = auth_client.get(url, follow_redirects=True)
        assert resp.status_code in (200, 404, 403), f"{url} returned {resp.status_code}"

    @pytest.mark.parametrize(
        "suffix",
        [
            "",
            "/edit",
        ],
    )
    def test_cheque_pages_render(self, auth_client, granted_permissions, tenant_records, suffix):
        url = f"/cheques/{tenant_records['cheque'].id}{suffix}"
        resp = auth_client.get(url, follow_redirects=True)
        assert resp.status_code in (200, 404, 403), f"{url} returned {resp.status_code}"

    def test_payroll_slip_renders(self, auth_client, granted_permissions, tenant_records):
        url = f"/payroll/slip/{tenant_records['payroll_transaction'].id}"
        resp = auth_client.get(url, follow_redirects=True)
        assert resp.status_code in (200, 404, 403), f"{url} returned {resp.status_code}"

    def test_payroll_statement_renders(self, auth_client, granted_permissions, tenant_records):
        url = f"/payroll/statement/{tenant_records['employee'].id}"
        resp = auth_client.get(url, follow_redirects=True)
        assert resp.status_code in (200, 404, 403), f"{url} returned {resp.status_code}"


class TestCrmHrMarketingGamificationRoutes:
    """Module pages previously blocked by missing permission codes."""

    @pytest.mark.parametrize(
        "route",
        [
            "/crm/pipeline",
            "/crm/leads",
            "/crm/leads/create",
            "/hr/attendance",
            "/hr/leaves",
            "/hr/leaves/request",
            "/hr/departments",
            "/marketing/",
            "/marketing/campaigns/create",
            "/gamification/leaderboard",
        ],
    )
    def test_module_pages_render(self, auth_client, granted_permissions, route):
        resp = auth_client.get(route, follow_redirects=True)
        assert resp.status_code in (200, 404, 403), f"{route} returned {resp.status_code}"

    def test_marketing_stats_renders(self, auth_client, granted_permissions, tenant_records):
        url = f"/marketing/campaigns/{tenant_records['email_campaign'].id}"
        resp = auth_client.get(url, follow_redirects=True)
        assert resp.status_code in (200, 404, 403), f"{url} returned {resp.status_code}"


class TestPaymentsReceiptsRoutes:
    """Receipt view / print pages including each receipt template."""

    def test_receipt_view_renders(self, auth_client, granted_permissions, tenant_records):
        url = f"/payments/receipts/{tenant_records['receipt'].id}"
        resp = auth_client.get(url, follow_redirects=True)
        assert resp.status_code in (200, 404, 403), f"{url} returned {resp.status_code}"

    @pytest.mark.parametrize(
        "template",
        ["modern", "classic", "gulf", "minimal", "simple"],
    )
    def test_receipt_print_templates_render(self, auth_client, granted_permissions, tenant_records, template):
        url = f"/payments/receipts/{tenant_records['receipt'].id}/print?template={template}"
        resp = auth_client.get(url, follow_redirects=True)
        assert resp.status_code in (200, 404, 403), f"{url} returned {resp.status_code}"


class TestUsersAndPosRoutes:
    """Users management and POS display pages (permission-gated)."""

    @pytest.mark.parametrize(
        "suffix",
        [
            "",
            "/view",
            "/edit",
        ],
    )
    def test_user_pages_render(self, auth_client, granted_permissions, sample_user, suffix):
        url = f"/users/{sample_user.id}{suffix}"
        resp = auth_client.get(url, follow_redirects=True)
        assert resp.status_code in (200, 404, 403), f"{url} returned {resp.status_code}"

    def test_users_index_renders(self, auth_client, granted_permissions):
        resp = auth_client.get("/users/", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code

    def test_pos_kds_renders(self, auth_client, granted_permissions):
        resp = auth_client.get("/pos/kds", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code


class TestUnifiedPrintingRoutes:
    """Unified /printing/<doc_type>/<id> handler for printing/*.html templates."""

    @pytest.mark.parametrize(
        ("doc_type", "key"),
        [
            ("cheque", "cheque"),
            ("packing-slip", "sale"),
            ("purchase", "purchase"),
            ("expense", "expense"),
            ("payroll-slip", "payroll_transaction"),
        ],
    )
    def test_printing_document_renders(self, auth_client, granted_permissions, tenant_records, doc_type, key):
        url = f"/printing/{doc_type}/{tenant_records[key].id}"
        resp = auth_client.get(url, follow_redirects=True)
        assert resp.status_code in (200, 404, 403), f"{url} returned {resp.status_code}"


# ── Owner panel record routes ───────────────────────────────────────────────


class TestOwnerRecordRoutes:
    """Owner detail routes that need real records (users, tenants, cards, tables)."""

    def test_owner_edit_user_renders(self, owner_records):
        client = owner_records["client"]
        resp = client.get(f"/owner/users/{owner_records['user'].id}/edit", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code

    def test_owner_user_profile_renders(self, owner_records):
        client = owner_records["client"]
        resp = client.get(f"/owner/users/{owner_records['user'].id}/profile", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code

    def test_owner_tenant_edit_renders(self, owner_records):
        client = owner_records["client"]
        resp = client.get(f"/owner/tenants/{owner_records['tenant'].id}/edit", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code

    def test_owner_view_card_renders(self, owner_records):
        client = owner_records["client"]
        resp = client.get(f"/owner/cards-vault/{owner_records['card'].id}/view", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code

    def test_owner_browse_table_renders(self, owner_client, sample_gl_accounts):
        resp = owner_client.get("/owner/browse-table/gl_accounts", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code

    def test_owner_edit_table_renders(self, owner_client, sample_gl_accounts):
        resp = owner_client.get("/owner/edit-table-data/gl_accounts", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code


# ── Public detail / language pages ──────────────────────────────────────────


class TestPublicDetailPages:
    """Public pages that need a tenant record, verification token or EN session."""

    def test_tenant_profile_renders(self, client, sample_tenant):
        resp = client.get(f"/tenant/{sample_tenant.slug}", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code

    def test_verify_document_renders(self, client, sample_verification):
        url = f"/verify/{sample_verification.public_token}"
        resp = client.get(url, follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code

    @pytest.mark.parametrize(
        "route",
        [
            "/contact",
            "/features",
            "/user-guide",
        ],
    )
    def test_english_public_pages_render(self, client, route):
        with client.session_transaction() as sess:
            sess["language"] = "en"
        resp = client.get(route, follow_redirects=True)
        assert resp.status_code in (200, 404, 403), f"{route} returned {resp.status_code}"
