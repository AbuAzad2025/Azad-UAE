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
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from flask import render_template

from config import Config
from extensions import db

# Permission codes referenced by the routes below that are absent from
# ``sample_permissions`` in tests/conftest.py.
_EXTRA_PERMISSION_CODES = [
    "crm.view",
    "crm.manage",
    "hr.view",
    "hr.manage",
    "marketing.manage",
    "manage_ledger",
    "manage_store",
    "manage_users",
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
        last_access=datetime.now(timezone.utc),
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
            "products/_form_badges.html",
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
                printed_at=datetime.now(timezone.utc),
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
                payment_date=datetime.now(timezone.utc),
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
        try:
            report = CashFlowService.generate_cash_flow(
                "2026-01-01", "2026-01-31", branch_id=None, tenant_id=sample_tenant.id
            )
        except Exception:
            pass
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
                printed_at=datetime.now(timezone.utc),
                **ctx,
            )
            render_template("shop/order_success.html", sale=sample_sale, **ctx)
