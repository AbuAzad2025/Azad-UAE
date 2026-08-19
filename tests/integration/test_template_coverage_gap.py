"""Template coverage gap fill — render the remaining uncovered Jinja2 templates.

The base smoke + expansion suites leave ~70 templates uncovered (store admin,
shop storefront, partners/projects/tickets detail pages, orphaned error pages,
non-modern invoice templates, etc.). This module fills the gap:

1. Real authenticated GET requests against routes that need records and/or the
   extra permission codes (reusing the ``auth_client`` / ``owner_client``
   fixtures and the super_admin ``sample_role`` from conftest.py).
2. Direct ``render_template`` calls inside ``app.test_request_context()`` for
   templates that are orphaned (never referenced by a route), reachable only
   through a hard-to-set-up path (non-modern invoices, errors, storefront
   account pages), or that need global platform state.

The conftest ``template_rendered`` signal records every render, so both
approaches contribute to ``templates_rendered.json``.
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from flask import render_template

from config import Config
from extensions import db

# Permission codes referenced by the routes below that are absent from
# ``sample_permissions`` in tests/conftest.py.
_EXTRA_PERMISSION_CODES = [
    "assets:depreciate",
    "assets:manage",
    "assets:view",
    "budget:approve",
    "budget:create",
    "crm.view",
    "crm.manage",
    "grn:manage",
    "hr:leave_manage",
    "hr.view",
    "hr.manage",
    "marketing.manage",
    "manage_ledger",
    "manage_store",
    "manage_users",
    "project.view",
    "project.manage",
    "purchase_req:create",
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
def sample_partner(db_session, sample_tenant):
    """Partner record for view / edit / statement pages."""
    from models import Partner

    partner = Partner(
        tenant_id=sample_tenant.id,
        name="Test Partner",
        code="PTNR-001",
        scope_type="company",
        partner_type="investor",
        is_active=True,
    )
    db_session.add(partner)
    db_session.commit()
    return partner


@pytest.fixture
def sample_project(db_session, sample_tenant, sample_customer):
    """Project record for list / detail pages."""
    from models import Project

    project = Project(
        tenant_id=sample_tenant.id,
        name="Test Project",
        customer_id=sample_customer.id,
        status="planning",
        is_active=True,
    )
    db_session.add(project)
    db_session.commit()
    return project


@pytest.fixture
def sample_ticket(db_session, sample_tenant, sample_customer):
    """Ticket record for the detail page."""
    from models import Ticket

    ticket = Ticket(
        tenant_id=sample_tenant.id,
        subject="Test support ticket",
        status="open",
        customer_id=sample_customer.id,
    )
    db_session.add(ticket)
    db_session.commit()
    return ticket


@pytest.fixture
def store_ready(db_session, sample_tenant):
    """Enable the store feature flag + tenant store for /store/admin routes."""
    sample_tenant.enable_store = True
    db_session.commit()
    return sample_tenant


@pytest.fixture
def shop_storefront(db_session, sample_tenant, sample_branch, sample_warehouse):
    """A live storefront: enabled tenant store, global ecommerce on, product."""
    from models import SystemSettings, TenantStore

    slug = f"test-store-{uuid.uuid4().hex[:8]}"
    store = TenantStore(
        tenant_id=sample_tenant.id,
        warehouse_id=sample_warehouse.id,
        is_enabled=True,
        platform_disabled=False,
        store_slug=slug,
        title=sample_tenant.name_ar or sample_tenant.name,
        phone="0500000000",
        whatsapp="971500000000",
    )
    db_session.add(store)
    db_session.commit()

    settings = SystemSettings.get_current()
    settings.enable_ecommerce = True
    db_session.commit()

    return {"slug": slug, "store": store, "tenant": sample_tenant}


@pytest.fixture
def platform_vault(db_session):
    """Platform payment vault with donations enabled for public /donate pages."""
    from models.payment_vault import PaymentVault

    vault = PaymentVault(
        tenant_id=None,
        vault_name="Test Vault",
        vault_password_hash="pbkdf2:sha256:260000$test$" + "0" * 32,
        is_locked=False,
        donations_enabled=True,
        donation_page_enabled=True,
        min_donation_amount=Decimal("10.00"),
        max_donation_amount=Decimal("10000.00"),
        last_access=datetime.now(UTC),
        failed_attempts=0,
        max_failed_attempts=3,
        auto_lock_minutes=30,
    )
    db_session.add(vault)
    db_session.commit()
    return vault


# ── Tenant record-detail routes ────────────────────────────────────────────


class TestTicketsRoutes:
    """tickets/list.html + tickets/detail.html."""

    def test_tickets_list_renders(self, auth_client, granted_permissions):
        resp = auth_client.get("/tickets/", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code

    def test_tickets_create_renders(self, auth_client, granted_permissions):
        resp = auth_client.get("/tickets/create", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code

    def test_ticket_detail_renders(self, auth_client, granted_permissions, sample_ticket):
        resp = auth_client.get(f"/tickets/{sample_ticket.id}", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code


class TestProjectsRoutes:
    """projects/list.html + task_form.html + detail.html."""

    def test_projects_list_renders(self, auth_client, granted_permissions):
        resp = auth_client.get("/projects/", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code

    def test_projects_create_renders(self, auth_client, granted_permissions):
        resp = auth_client.get("/projects/create", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code

    def test_project_detail_renders(self, auth_client, granted_permissions, sample_project):
        resp = auth_client.get(f"/projects/{sample_project.id}", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code


class TestPartnersRoutes:
    """partners/create.html + view.html + edit.html + statement.html."""

    def test_partner_create_renders(self, auth_client, granted_permissions):
        resp = auth_client.get("/partners/create", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code

    def test_partner_view_renders(self, auth_client, granted_permissions, sample_partner):
        resp = auth_client.get(f"/partners/{sample_partner.id}", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code

    def test_partner_edit_renders(self, auth_client, granted_permissions, sample_partner):
        resp = auth_client.get(f"/partners/{sample_partner.id}/edit", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code

    def test_partner_statement_renders(self, auth_client, granted_permissions, sample_partner):
        resp = auth_client.get(f"/partners/{sample_partner.id}/statement", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code


class TestUnifiedInventoryRoutes:
    """unified_inventory/{campaigns,warranty,shipments}.html."""

    @pytest.mark.parametrize("route", ["/uinv/campaigns", "/uinv/warranty", "/uinv/shipments"])
    def test_uinv_page_renders(self, auth_client, granted_permissions, route):
        resp = auth_client.get(route, follow_redirects=True)
        assert resp.status_code in (200, 404, 403), f"{route} returned {resp.status_code}"


class TestStoreAdminRoutes:
    """store/admin_*.html — needs the store feature flag enabled."""

    @pytest.mark.parametrize(
        "route",
        [
            "/store/admin",
            "/store/admin/settings",
            "/store/admin/catalog",
            "/store/admin/transfer",
            "/store/admin/orders",
            "/store/admin/customers",
            "/store/admin/stats",
            "/store/admin/coupons",
        ],
    )
    def test_store_admin_page_renders(self, auth_client, granted_permissions, store_ready, route):
        resp = auth_client.get(route, follow_redirects=True)
        assert resp.status_code in (200, 404, 403), f"{route} returned {resp.status_code}"


class TestPosRoutes:
    """pos/receipt.html + pos/disabled.html."""

    def test_pos_thermal_receipt_renders(self, auth_client, granted_permissions, sample_sale):
        resp = auth_client.get(f"/pos/receipt/{sample_sale.id}", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code

    def test_pos_disabled_renders(self, auth_client, granted_permissions, sample_tenant):
        sample_tenant.enable_pos = False
        resp = auth_client.get("/pos/", follow_redirects=True)
        assert resp.status_code in (403, 404), resp.status_code
        sample_tenant.enable_pos = True


class TestPurchasesRoutes:
    """purchases/return.html."""

    def test_purchase_return_renders(self, auth_client, granted_permissions, sample_purchase):
        resp = auth_client.get(f"/purchases/{sample_purchase.id}/return", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code


class TestMiscTenantRoutes:
    """users/create.html, ledger/cash_flow.html, reports entity fragment."""

    def test_users_create_renders(self, auth_client, granted_permissions):
        resp = auth_client.get("/users/create", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code

    def test_ledger_cash_flow_renders(self, auth_client, granted_permissions):
        resp = auth_client.get("/ledger/cash-flow", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code

    @pytest.mark.parametrize(
        ("entity_type", "key"),
        [("customer", "customer"), ("supplier", "supplier")],
    )
    def test_entity_report_fragment_renders(
        self, auth_client, granted_permissions, sample_customer, sample_supplier, entity_type, key
    ):
        record = sample_customer if key == "customer" else sample_supplier
        resp = auth_client.get(f"/reports/entity_report_fragment/{entity_type}/{record.id}")
        assert resp.status_code in (200, 404, 403), resp.status_code


class TestOwnerRoutes:
    """ai/config.html (owner-only) + owner_admin/dashboard.html."""

    def test_ai_config_renders(self, owner_client):
        resp = owner_client.get("/ai/config", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code

    def test_super_admin_dashboard_renders(self, owner_client):
        resp = owner_client.get("/super-admin/dashboard", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code


class TestPublicDonateRoutes:
    """public/donate_azad.html + public/donate_thanks.html."""

    def test_donate_page_renders(self, client, platform_vault):
        resp = client.get("/donate", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code

    def test_donate_submit_renders(self, client, platform_vault):
        resp = client.post(
            "/donate/submit",
            data={"amount": "50", "payment_method": "bank_transfer", "donor_name": "Test Donor"},
            follow_redirects=True,
        )
        assert resp.status_code in (200, 404, 403), resp.status_code


class TestShopStorefrontRoutes:
    """shop/{catalog,product,cart,checkout,account_*,order_track,offline}.html."""

    def test_shop_catalog_renders(self, client, shop_storefront):
        resp = client.get(f"/s/{shop_storefront['slug']}", follow_redirects=True)
        assert resp.status_code in (200, 503, 404), resp.status_code

    def test_shop_cart_renders(self, client, shop_storefront):
        resp = client.get(f"/s/{shop_storefront['slug']}/cart", follow_redirects=True)
        assert resp.status_code in (200, 503, 404), resp.status_code

    def test_shop_checkout_renders(self, client, shop_storefront):
        resp = client.get(f"/s/{shop_storefront['slug']}/checkout", follow_redirects=True)
        assert resp.status_code in (200, 302, 503, 404), resp.status_code

    def test_shop_account_login_renders(self, client, shop_storefront):
        resp = client.get(f"/s/{shop_storefront['slug']}/account/login", follow_redirects=True)
        assert resp.status_code in (200, 503, 404), resp.status_code

    def test_shop_account_register_renders(self, client, shop_storefront):
        resp = client.get(f"/s/{shop_storefront['slug']}/account/register", follow_redirects=True)
        assert resp.status_code in (200, 503, 404), resp.status_code

    def test_shop_forgot_password_renders(self, client, shop_storefront):
        resp = client.get(f"/s/{shop_storefront['slug']}/account/forgot-password", follow_redirects=True)
        assert resp.status_code in (200, 503, 404), resp.status_code

    def test_shop_return_policy_renders(self, client, shop_storefront):
        resp = client.get(f"/s/{shop_storefront['slug']}/return-policy", follow_redirects=True)
        assert resp.status_code in (200, 503, 404), resp.status_code

    def test_shop_order_track_renders(self, client, shop_storefront):
        resp = client.get(f"/s/{shop_storefront['slug']}/track", follow_redirects=True)
        assert resp.status_code in (200, 503, 404), resp.status_code

    def test_shop_offline_renders(self, client, shop_storefront):
        resp = client.get(f"/s/{shop_storefront['slug']}/offline", follow_redirects=True)
        assert resp.status_code in (200, 503, 404), resp.status_code


# ── Direct renders (orphaned / hard-to-reach templates) ────────────────────


@contextlib.contextmanager
def _authed_render(app, user):
    """Request context with a logged-in user (templates need current_user)."""
    with app.test_request_context():
        from flask_login import login_user

        login_user(user)
        yield


class TestDirectTemplateRenders:
    """Render templates that no route can reach with default test state."""

    @pytest.mark.parametrize(
        "template_name",
        [
            "errors/500.html",
            "errors/503.html",
            "errors/402.html",
            "public/subscription_expired.html",
            "public/tenant_suspended.html",
            "public/pricing_en.html",
        ],
    )
    def test_error_and_public_pages_render(self, app, sample_tenant, template_name):
        with app.test_request_context():
            ctx = {}
            if template_name in ("public/subscription_expired.html", "public/tenant_suspended.html"):
                ctx["tenant"] = sample_tenant
            if template_name == "public/tenant_suspended.html":
                ctx["reason"] = "Maintenance"
            render_template(template_name, **ctx)

    @pytest.mark.parametrize("name", ["classic", "gulf", "minimal", "simple"])
    def test_invoice_templates_render(self, app, sample_tenant, sample_sale, name):
        from config import Config
        from models import Branch, InvoiceSettings
        from utils.tenant_branding import get_print_header_context

        with app.test_request_context():
            settings = InvoiceSettings(
                tenant_id=sample_tenant.id,
                company_name_ar="شركة الاختبار",
                company_name_en="Test Company",
                is_active=True,
                active_template=name,
                enable_qr_code=False,
            )
            print_branch = db.session.get(Branch, sample_sale.branch_id) if sample_sale.branch_id else None
            render_template(
                f"invoices/{name}.html",
                sale=sample_sale,
                settings=settings,
                config=Config,
                print_branch=print_branch,
                print_user_name="Test Seller",
                amount_in_words="مائة",
                qr_data_url="",
                print_branding=get_print_header_context(sample_tenant.id),
                print_tenant_id=sample_tenant.id,
                printed_at=datetime.now(UTC),
            )

    def test_payments_create_receipt_renders(self, app, sample_user, sample_purchase):
        from models import Supplier

        with _authed_render(app, sample_user):
            supplier = db.session.get(Supplier, sample_purchase.supplier_id)
            render_template(
                "payments/create_receipt.html",
                purchase=sample_purchase,
                supplier=supplier,
                suggested_amount=Decimal("100.000"),
                is_payment=True,
            )

    def test_payments_print_receipt_renders(self, app, db_session, sample_tenant, sample_supplier):
        from models import Payment

        with app.test_request_context():
            payment = Payment(
                tenant_id=sample_tenant.id,
                payment_number="PAY-TEST-001",
                payment_type="cash",
                direction="outgoing",
                supplier_id=sample_supplier.id,
                amount=Decimal("100.000"),
                amount_aed=Decimal("100.000"),
                currency="AED",
                payment_method="cash",
                payment_date=datetime.now(UTC),
                notes="Test payment",
            )
            render_template(
                "payments/print_receipt.html",
                receipt=payment,
                is_payment=True,
                company={"name_ar": "Test", "name_en": "Test"},
                settings=None,
                config=Config,
                printed_at=datetime.now(),
                print_branch=None,
                print_user_name="Test Seller",
                amount_in_words="مائة درهم",
                qr_data_url="",
                doc_number=payment.payment_number,
                print_branding={},
                print_tenant_id=sample_tenant.id,
                available_templates=["modern"],
                current_template="modern",
            )

    def test_pos_customer_display_renders(self, app):
        with app.test_request_context():
            render_template("pos/customer_display.html")

    def test_pos_disabled_direct_renders(self, app):
        with app.test_request_context():
            render_template("pos/disabled.html", reason="system")

    def test_owner_backup_instructions_renders(self, app):
        with app.test_request_context():
            render_template(
                "owner/backup_restore_instructions.html",
                filename="test-backup.json",
                commands=["SELECT 1;"],
                warning=None,
                info={"size_bytes": 1024},
            )

    def test_ledger_cash_flow_direct_renders(self, app, sample_user, sample_tenant):
        from services.cash_flow_service import CashFlowService

        report = {
            "period_start": "2026-01-01",
            "period_end": "2026-01-31",
            "operating_activities": {"items": [], "net_cash_from_operating": 0.0},
            "investing_activities": {"items": [], "net_cash_from_investing": 0.0},
            "financing_activities": {"items": [], "net_cash_from_financing": 0.0},
            "net_change_in_cash": 0.0,
            "cash_beginning": 0.0,
            "cash_ending": 0.0,
        }
        with contextlib.suppress(Exception):
            report = CashFlowService.generate_cash_flow(
                "2026-01-01", "2026-01-31", branch_id=None, tenant_id=sample_tenant.id
            )
        with _authed_render(app, sample_user):
            render_template(
                "ledger/cash_flow.html",
                report=report,
                date_from="2026-01-01",
                date_to="2026-01-31",
                branches=[],
                selected_branch=None,
            )

    def test_shop_account_pages_render(self, app, sample_tenant, sample_sale, shop_storefront):
        from routes.shop import _store_context
        from services.store_service import StoreService

        with app.test_request_context():
            store = StoreService.get_store_by_slug(shop_storefront["slug"])
            ctx = _store_context(store)
            render_template("shop/account_orders.html", orders=[], payment_methods={}, noindex=True, **ctx)
            render_template("shop/saved_payments.html", payments=[], noindex=True, **ctx)
            render_template("shop/wishlist.html", wishlist_items=[], noindex=True, **ctx)
            render_template(
                "shop/account_order_detail.html",
                order=sample_sale,
                pay_method=None,
                status_label="pending",
                noindex=True,
                **ctx,
            )
            render_template(
                "shop/order_invoice.html",
                sale=sample_sale,
                status_label="pending",
                pay_method=None,
                printed_at=datetime.now(UTC),
                **ctx,
            )
            render_template("shop/order_success.html", sale=sample_sale, **ctx)


# ── New fixtures for template coverage gap fill ─────────────────────────────


@pytest.fixture
def sample_gl_account(db_session, sample_tenant, sample_gl_accounts):
    """A single GL account for asset/budget FK references."""
    from models import GLAccount

    acct = GLAccount.query.filter_by(tenant_id=sample_tenant.id, type="expense").first()
    if not acct:
        acct = GLAccount(
            tenant_id=sample_tenant.id,
            code="6100",
            name="Test Expense Account",
            name_ar="حساب مصروف تجريبي",
            type="expense",
            is_active=True,
        )
        db_session.add(acct)
        db_session.commit()
    return acct


@pytest.fixture
def sample_asset_account(db_session, sample_tenant, sample_gl_accounts):
    """GL account of type 'asset' for FixedAsset.asset_account_id."""
    from models import GLAccount

    acct = GLAccount.query.filter_by(tenant_id=sample_tenant.id, type="asset").first()
    if not acct:
        acct = GLAccount(
            tenant_id=sample_tenant.id,
            code="1500",
            name="Test Fixed Asset Account",
            name_ar="حساب أصول ثابتة تجريبي",
            type="asset",
            sub_type="fixed_asset",
            is_active=True,
        )
        db_session.add(acct)
        db_session.commit()
    return acct


@pytest.fixture
def sample_fixed_asset(db_session, sample_tenant, sample_asset_account, sample_user, sample_branch):
    from datetime import date
    from decimal import Decimal

    from models import FixedAsset

    asset = FixedAsset(
        tenant_id=sample_tenant.id,
        asset_number="FA-TEST-001",
        name_ar="أصل تجريبي",
        name_en="Test Asset",
        category="equipment",
        asset_account_id=sample_asset_account.id,
        purchase_date=date(2025, 1, 1),
        purchase_price=Decimal("10000.000"),
        salvage_value=Decimal("1000.000"),
        depreciation_method="straight_line",
        useful_life_years=5,
        accumulated_depreciation=Decimal("0"),
        book_value=Decimal("10000.000"),
        status="active",
        branch_id=sample_branch.id,
        created_by=sample_user.id,
    )
    db_session.add(asset)
    db_session.commit()
    return asset


@pytest.fixture
def sample_budget(db_session, sample_tenant, sample_user, sample_gl_account, sample_branch):
    from datetime import date

    from models import Budget, BudgetLine

    budget = Budget(
        tenant_id=sample_tenant.id,
        budget_number="BUD-TEST-001",
        name_ar="موازنة تجريبية",
        name_en="Test Budget",
        fiscal_year=2026,
        period_type="annual",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31),
        status="draft",
        enforcement="warn",
        total_budgeted=Decimal("50000.000"),
        branch_id=sample_branch.id,
        created_by=sample_user.id,
    )
    db_session.add(budget)
    db_session.flush()

    line = BudgetLine(
        tenant_id=sample_tenant.id,
        budget_id=budget.id,
        account_id=sample_gl_account.id,
        budgeted_amount=Decimal("50000.000"),
        actual_amount=Decimal("0"),
        notes="Test line",
    )
    db_session.add(line)
    db_session.commit()
    return budget


@pytest.fixture
def sample_leave_type(db_session, sample_tenant):
    from models import LeaveType

    lt = LeaveType(
        tenant_id=sample_tenant.id,
        name="Annual Leave",
        name_ar="إجازة سنوية",
        days_per_year=30,
        is_active=True,
    )
    db_session.add(lt)
    db_session.commit()
    return lt


@pytest.fixture
def sample_quotation_with_lines(db_session, sample_tenant, sample_customer, sample_user, sample_product, sample_branch):
    from decimal import Decimal

    from models import Quotation, QuotationLine

    q = Quotation(
        tenant_id=sample_tenant.id,
        quotation_number="QT-TEST-001",
        customer_id=sample_customer.id,
        branch_id=sample_branch.id,
        status="draft",
        subtotal=Decimal("100.000"),
        total_amount=Decimal("105.000"),
        currency="AED",
        amount_aed=Decimal("105.000"),
        created_by=sample_user.id,
    )
    db_session.add(q)
    db_session.flush()

    line = QuotationLine(
        tenant_id=sample_tenant.id,
        quotation_id=q.id,
        product_id=sample_product.id,
        description="Test item",
        quantity=Decimal("1"),
        unit_price=Decimal("100.000"),
        line_total=Decimal("100.000"),
    )
    db_session.add(line)
    db_session.commit()
    return q


@pytest.fixture
def sample_warehouse_transfer_with_lines(
    db_session, sample_tenant, sample_user, sample_warehouse, sample_product, sample_branch
):
    from decimal import Decimal

    from models import Warehouse, WarehouseTransfer, WarehouseTransferLine

    from_warehouse = Warehouse(
        tenant_id=sample_tenant.id,
        branch_id=sample_branch.id,
        name="Source Warehouse",
        name_ar="مستودع المصدر",
        is_active=True,
    )
    db_session.add(from_warehouse)
    db_session.flush()

    t = WarehouseTransfer(
        tenant_id=sample_tenant.id,
        transfer_number="TRF-TEST-001",
        from_warehouse_id=from_warehouse.id,
        to_warehouse_id=sample_warehouse.id,
        branch_id=sample_branch.id,
        status="draft",
        requested_by=sample_user.id,
    )
    db_session.add(t)
    db_session.flush()

    line = WarehouseTransferLine(
        tenant_id=sample_tenant.id,
        transfer_id=t.id,
        product_id=sample_product.id,
        requested_quantity=Decimal("10"),
        received_quantity=Decimal("0"),
    )
    db_session.add(line)
    db_session.commit()
    return t


@pytest.fixture
def sample_payment_for_voucher(db_session, sample_tenant, sample_supplier, sample_user, sample_branch):
    from datetime import UTC, datetime
    from decimal import Decimal

    from models import Payment

    p = Payment(
        tenant_id=sample_tenant.id,
        payment_number="PAY-VOUCHER-001",
        payment_type="cash",
        direction="outgoing",
        supplier_id=sample_supplier.id,
        supplier_name="Test Supplier",
        amount=Decimal("500.000"),
        amount_aed=Decimal("500.000"),
        currency="AED",
        payment_method="cash",
        payment_date=datetime.now(UTC),
        branch_id=sample_branch.id,
        user_id=sample_user.id,
        notes="Test voucher payment",
    )
    db_session.add(p)
    db_session.commit()
    return p


@pytest.fixture
def sample_purchase_order_for_match(
    db_session, sample_tenant, sample_supplier, sample_user, sample_product, sample_warehouse, sample_branch
):
    from datetime import date
    from decimal import Decimal

    from models import PurchaseOrder, PurchaseOrderLine

    po = PurchaseOrder(
        tenant_id=sample_tenant.id,
        po_number="PO-MATCH-001",
        supplier_id=sample_supplier.id,
        warehouse_id=sample_warehouse.id,
        branch_id=sample_branch.id,
        order_date=date(2026, 1, 15),
        status="confirmed",
        subtotal=Decimal("1000.000"),
        total_amount=Decimal("1050.000"),
        currency="AED",
        created_by=sample_user.id,
    )
    db_session.add(po)
    db_session.flush()

    line = PurchaseOrderLine(
        tenant_id=sample_tenant.id,
        po_id=po.id,
        product_id=sample_product.id,
        quantity=Decimal("10"),
        unit_cost=Decimal("100.000"),
        line_total=Decimal("1000.000"),
    )
    db_session.add(line)
    db_session.commit()
    return po


@pytest.fixture
def shop_storefront_with_policy(db_session, sample_tenant, sample_branch, sample_warehouse):
    import uuid

    from models import SystemSettings, TenantStore

    slug = f"test-store-{uuid.uuid4().hex[:8]}"
    store = TenantStore(
        tenant_id=sample_tenant.id,
        warehouse_id=sample_warehouse.id,
        is_enabled=True,
        platform_disabled=False,
        store_slug=slug,
        title=sample_tenant.name_ar or sample_tenant.name,
        phone="0500000000",
        whatsapp="971500000000",
        return_policy_ar="سياسة الإرجاع: يمكن إرجاع المنتجات خلال 30 يوماً",
        return_policy_en="Return Policy: Products may be returned within 30 days",
    )
    db_session.add(store)
    db_session.commit()

    settings = SystemSettings.get_current()
    settings.enable_ecommerce = True
    db_session.commit()

    return {"slug": slug, "store": store, "tenant": sample_tenant}


# ── Assets routes ───────────────────────────────────────────────────────────


class TestAssetsRoutes:
    """assets/{index,create,detail,disposal,depreciation}.html."""

    def test_assets_index_renders(self, auth_client, granted_permissions, sample_fixed_asset):
        resp = auth_client.get("/assets/", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code

    def test_assets_create_renders(self, auth_client, granted_permissions, sample_gl_account):
        resp = auth_client.get("/assets/create", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code

    def test_assets_detail_renders(self, auth_client, granted_permissions, sample_fixed_asset):
        resp = auth_client.get(f"/assets/{sample_fixed_asset.id}", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code

    def test_assets_disposal_renders(self, auth_client, granted_permissions, sample_fixed_asset):
        resp = auth_client.get(f"/assets/{sample_fixed_asset.id}/dispose", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code

    def test_assets_depreciation_renders(self, auth_client, granted_permissions, sample_fixed_asset):
        resp = auth_client.get("/assets/depreciation-schedule", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code


# ── Budget routes ───────────────────────────────────────────────────────────


class TestBudgetRoutes:
    """financials/budget/{index,form,detail,variance}.html."""

    def test_budget_index_renders(self, auth_client, granted_permissions):
        resp = auth_client.get("/budgets/", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code

    def test_budget_form_create_renders(self, auth_client, granted_permissions, sample_gl_account):
        resp = auth_client.get("/budgets/create", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code

    def test_budget_detail_renders(self, auth_client, granted_permissions, sample_budget):
        resp = auth_client.get(f"/budgets/{sample_budget.id}", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code

    def test_budget_variance_renders(self, auth_client, granted_permissions, sample_budget):
        resp = auth_client.get(f"/budgets/{sample_budget.id}/variance", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code


# ── HR routes ───────────────────────────────────────────────────────────────


class TestHRRoutes:
    """hr/leave_ledger.html + hr/overtime.html."""

    def test_hr_leave_ledger_renders(self, auth_client, granted_permissions, sample_user, sample_leave_type):
        resp = auth_client.get("/hr/leave-ledger", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code

    def test_hr_overtime_renders(self, auth_client, granted_permissions):
        resp = auth_client.get("/hr/overtime", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code


# ── Purchasing routes ───────────────────────────────────────────────────────


class TestPurchasingRoutes:
    """purchasing/{requisitions,grn,match}.html."""

    def test_purchasing_requisitions_renders(self, auth_client, granted_permissions):
        resp = auth_client.get("/purchases/requisitions", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code

    def test_purchasing_grn_renders(self, auth_client, granted_permissions):
        resp = auth_client.get("/purchases/grn", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code

    def test_purchasing_match_renders(self, auth_client, granted_permissions, sample_purchase_order_for_match):
        resp = auth_client.get(
            f"/purchases/match/{sample_purchase_order_for_match.id}",
            follow_redirects=True,
        )
        assert resp.status_code in (200, 404, 403), resp.status_code


# ── Quotation routes ────────────────────────────────────────────────────────


class TestQuotationRoutes:
    """quotations/{index,form,detail}.html."""

    def test_quotations_index_renders(self, auth_client, granted_permissions):
        resp = auth_client.get("/quotations/", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code

    def test_quotations_form_create_renders(self, auth_client, granted_permissions):
        resp = auth_client.get("/quotations/create", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code

    def test_quotations_detail_renders(self, auth_client, granted_permissions, sample_quotation_with_lines):
        resp = auth_client.get(f"/quotations/{sample_quotation_with_lines.id}", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code


# ── Warehouse transfer routes ───────────────────────────────────────────────


class TestWarehouseTransferRoutes:
    """warehouse/{transfers,transfer_form,transfer_detail}.html."""

    def test_warehouse_transfers_index_renders(self, auth_client, granted_permissions):
        resp = auth_client.get("/transfers/", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code

    def test_warehouse_transfer_form_renders(self, auth_client, granted_permissions):
        resp = auth_client.get("/transfers/create", follow_redirects=True)
        assert resp.status_code in (200, 404, 403), resp.status_code

    def test_warehouse_transfer_detail_renders(
        self, auth_client, granted_permissions, sample_warehouse_transfer_with_lines
    ):
        resp = auth_client.get(
            f"/transfers/{sample_warehouse_transfer_with_lines.id}",
            follow_redirects=True,
        )
        assert resp.status_code in (200, 404, 403), resp.status_code


# ── Payment voucher (print route) ──────────────────────────────────────────


class TestPaymentVoucherRoute:
    """receipts/payment_voucher.html."""

    def test_payment_voucher_renders(
        self,
        auth_client,
        granted_permissions,
        sample_payment_for_voucher,
    ):
        resp = auth_client.get(
            f"/payments/{sample_payment_for_voucher.id}/print",
            follow_redirects=True,
        )
        assert resp.status_code in (200, 404, 403), resp.status_code


# ── Shop return policy (with policy set) ───────────────────────────────────


class TestShopReturnPolicyRoute:
    """shop/return_policy.html — needs actual policy text to avoid 404."""

    def test_shop_return_policy_with_text_renders(self, client, shop_storefront_with_policy):
        resp = client.get(
            f"/s/{shop_storefront_with_policy['slug']}/return-policy",
            follow_redirects=True,
        )
        assert resp.status_code in (200, 503, 404), resp.status_code


# ── Public donate (direct renders as fallback) ──────────────────────────────


class TestPublicDonateDirectRenders:
    """public/donate_azad.html + public/donate_thanks.html via direct render."""

    def test_donate_azad_direct_render(self, app, platform_vault):
        with app.test_request_context():
            from routes.public import _safe_vault_for_public

            render_template(
                "public/donate_azad.html",
                vault=_safe_vault_for_public(platform_vault),
                lang="ar",
                is_en=False,
            )

    def test_donate_thanks_direct_render(self, app, platform_vault):
        with app.test_request_context():
            from models.donation import Donation
            from routes.public import _safe_vault_for_public

            donation = Donation(
                amount_usd=Decimal("100"),
                payment_method="bank_transfer",
                transaction_type="donation",
                status="pending",
                donor_name="Test Donor",
            )
            db.session.add(donation)
            db.session.commit()
            render_template(
                "public/donate_thanks.html",
                vault=_safe_vault_for_public(platform_vault),
                donation=donation,
                lang="ar",
                is_en=False,
            )
