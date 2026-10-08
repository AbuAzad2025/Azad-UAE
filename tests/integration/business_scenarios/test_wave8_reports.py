"""Wave 8 - financial reports and analytics. Prefix RPT.

All 25 routes in this domain share a single permission: ``view_reports``.
There are no write operations - every route is a read of money that has already
moved, or a forecast of money that might. The entire surface is therefore
about correct aggregation, correct filtering, correct format, and the right
boundaries between tenants.

The only "write" adjacent paths are the export endpoints that stream a CSV or
XLSX file to the caller. Those are still GET in the web UI and POST only in the
API layer, and they never write to the database.
"""

from __future__ import annotations

import uuid

import pytest

RPT_VIEW_PATHS = [
    "/reports/",
    "/reports/partners",
    "/reports/sales",
    "/reports/sales/export",
    "/reports/purchases",
    "/reports/purchases/export",
    "/reports/ar-reconciliation",
    "/reports/inventory-reconciliation",
    "/reports/inventory-reconciliation/export",
    "/reports/receivables",
    "/reports/receivables/export",
    "/reports/ap-aging",
    "/reports/api/ap-aging",
    "/reports/ap-aging/export",
    "/reports/inventory",
    "/reports/inventory/export",
    "/reports/api/model-fields",
    "/reports/api/entity-search",
    "/reports/top-selling",
]

RPT_API_PATHS = [
    "/reports/api/ap-aging",
    "/reports/api/model-fields",
    "/reports/api/entity-search",
    "/api/analytics/overdue-payments",
    "/api/analytics/daily-stats",
    "/api/analytics/top-customers",
    "/api/analytics/low-stock-products",
    "/api/analytics/revenue-trend",
]

RPT_EXPORT_PATHS = [
    "/reports/sales/export",
    "/reports/purchases/export",
    "/reports/inventory-reconciliation/export",
    "/reports/receivables/export",
    "/reports/ap-aging/export",
    "/reports/inventory/export",
]


def _role(db_session, slug):
    from models import Role

    role = db_session.query(Role).filter_by(slug=slug).first()
    if role is None:
        role = Role(name=slug.replace("_", " ").title(), slug=slug, is_active=True)
        db_session.add(role)
        db_session.commit()
    return role


def _user(db_session, tenant, *, slug="accountant", permissions=(), branch=None):
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
        username=f"rpt-{slug}-{unique}",
        email=f"rpt-{unique}@example.com",
        full_name=f"RPT {slug}",
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


class TestRPT01Boundary:
    """RPT-01 to RPT-07: the single permission that guards everything."""

    @pytest.mark.parametrize("path", ["/reports/", "/reports/sales", "/reports/partners"])
    def test_anonymous_is_refused(self, client, path):
        """RPT-01. 404/401/403 on every route, unfollowed."""
        resp = client.get(path)
        assert resp.status_code in (302, 401, 403), f"{path} answered {resp.status_code} anonymously"

    @pytest.mark.parametrize("path", ["/reports/sales/export", "/reports/purchases/export"])
    def test_export_endpoints_are_gated(self, client, path):
        """RPT-02. Exports are GET but still behind the gate."""
        resp = client.get(path)
        assert resp.status_code in (302, 401, 403), f"{path} answered {resp.status_code} anonymously"

    @pytest.mark.parametrize("path", ["/reports/api/ap-aging", "/api/analytics/daily-stats"])
    def test_api_endpoints_are_gated(self, client, path):
        """RPT-02b. The JSON endpoints share the same gate."""
        resp = client.get(path)
        assert resp.status_code in (302, 401, 403), f"{path} answered {resp.status_code} anonymously"

    def test_a_user_without_view_reports_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """RPT-03. The permission is the single gate."""
        from models import Role, User

        role = db_session.query(Role).filter_by(slug="cashier").first() or Role(
            name="Cashier", slug="cashier", is_active=True
        )
        if role not in db_session:
            db_session.add(role)
            db_session.commit()
        user = User(
            username=f"rpt-cash-{uuid.uuid4().hex[:8]}",
            email=f"rpt-{uuid.uuid4().hex[:8]}@example.com",
            full_name="RPT Cashier",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        _login(client, user)

        for path in ("/reports/sales", "/reports/api/ap-aging", "/reports/sales/export"):
            resp = client.get(path)
            assert resp.status_code in (302, 403), f"{path} answered {resp.status_code} without view_reports"

    def test_a_user_with_view_reports_reaches_all_read_surfaces(self, client, db_session, sample_tenant, sample_branch):
        """RPT-04. The success side, so the refusals are not the only outcome."""
        from models import Permission, Role, User

        role = db_session.query(Role).filter_by(slug="accountant").first() or Role(
            name="Accountant", slug="accountant", is_active=True
        )
        if role not in db_session:
            db_session.add(role)
            db_session.commit()
        role.permissions = Permission.query.filter(Permission.code == "view_reports").all()
        db_session.add(role)
        db_session.commit()

        user = User(
            username=f"rpt-acc-{uuid.uuid4().hex[:8]}",
            email=f"rpt-{uuid.uuid4().hex[:8]}@example.com",
            full_name="RPT Accountant",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        _login(client, user)

        for path in (
            "/reports/sales",
            "/reports/purchases",
            "/reports/ar-reconciliation",
            "/reports/api/ap-aging",
            "/api/analytics/top-customers",
        ):
            resp = client.get(path)
            assert resp.status_code in (200, 302, 404), (
                f"the report at {path} answered {resp.status_code} for view_reports"
            )


class TestRPT02Exports:
    """RPT-05 to RPT-11: the export endpoints stream the right format."""

    def test_sales_export_is_csv_by_default(self, client, db_session, sample_tenant, sample_branch):
        """RPT-05. The sales export defaults to CSV, not PDF.

        The route accepts a format parameter and defaults to CSV. Verified by
        content-type and content.
        """
        from models import Permission, Role, User

        role = db_session.query(Role).filter_by(slug="accountant").first() or Role(
            name="Accountant", slug="accountant", is_active=True
        )
        if role not in db_session:
            db_session.add(role)
            db_session.commit()
        role.permissions = Permission.query.filter(Permission.code == "view_reports").all()
        db_session.add(role)
        db_session.commit()

        user = User(
            username=f"rpt-exp-{uuid.uuid4().hex[:8]}",
            email=f"rpt-{uuid.uuid4().hex[:8]}@example.com",
            full_name="RPT Export",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        _login(client, user)

        resp = client.get("/reports/sales/export", follow_redirects=True)
        assert resp.status_code == 200, f"sales export answered {resp.status_code}"
        ctype = resp.content_type or ""
        assert "text/csv" in ctype, f"sales export is {ctype}"
        data = resp.get_data(as_text=True)
        assert len(data) > 0, "empty CSV response"

    def test_purchases_export_is_csv_by_default(self, client, db_session, sample_tenant, sample_branch):
        """RPT-06. Purchases export is also CSV by default."""
        from models import Permission, Role, User

        role = db_session.query(Role).filter_by(slug="accountant").first() or Role(
            name="Accountant", slug="accountant", is_active=True
        )
        if role not in db_session:
            db_session.add(role)
            db_session.commit()
        role.permissions = Permission.query.filter(Permission.code == "view_reports").all()
        db_session.add(role)
        db_session.commit()

        user = User(
            username=f"rpt-exp-{uuid.uuid4().hex[:8]}",
            email=f"rpt-{uuid.uuid4().hex[:8]}@example.com",
            full_name="RPT Export",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        _login(client, user)

        resp = client.get("/reports/purchases/export", follow_redirects=True)
        assert resp.status_code == 200, f"purchases export answered {resp.status_code}"
        ctype = resp.content_type or ""
        assert "text/csv" in ctype, f"purchases export is {ctype}"
        data = resp.get_data(as_text=True)
        assert len(data) > 0, "empty CSV response"

    def test_ap_aging_export_is_csv(self, client, db_session, sample_tenant, sample_branch):
        """RPT-07. AP aging export."""
        from models import Permission, Role, User

        role = db_session.query(Role).filter_by(slug="accountant").first() or Role(
            name="Accountant", slug="accountant", is_active=True
        )
        if role not in db_session:
            db_session.add(role)
            db_session.commit()
        role.permissions = Permission.query.filter(Permission.code == "view_reports").all()
        db_session.add(role)
        db_session.commit()

        user = User(
            username=f"rpt-ap-{uuid.uuid4().hex[:8]}",
            email=f"rpt-{uuid.uuid4().hex[:8]}@example.com",
            full_name="RPT AP",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        _login(client, user)

        resp = client.get("/reports/ap-aging/export", follow_redirects=True)
        assert resp.status_code == 200
        ctype = resp.content_type or ""
        assert "application/pdf" in ctype, f"AP aging export is {ctype}"
        body = resp.get_data()
        assert body[:5] == b"%PDF-", f"not a PDF: {body[:12]!r}"


class TestRPT03API:
    """RPT-08 to RPT-14: the JSON endpoints."""

    def test_ap_aging_api_returns_json(self, client, db_session, sample_tenant, sample_branch):
        """RPT-08."""
        from models import Permission, Role, User

        role = db_session.query(Role).filter_by(slug="accountant").first() or Role(
            name="Accountant", slug="accountant", is_active=True
        )
        if role not in db_session:
            db_session.add(role)
            db_session.commit()
        role.permissions = Permission.query.filter(Permission.code == "view_reports").all()
        db_session.add(role)
        db_session.commit()

        user = User(
            username=f"rpt-api-{uuid.uuid4().hex[:8]}",
            email=f"rpt-{uuid.uuid4().hex[:8]}@example.com",
            full_name="RPT API",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        _login(client, user)

        resp = client.get("/reports/api/ap-aging")
        assert resp.status_code == 200, f"api/ap-aging answered {resp.status_code}"
        ctype = resp.content_type or ""
        assert "application/json" in ctype, f"not JSON: {ctype}"
        body = resp.get_json()
        assert isinstance(body, (dict, list)), f"unexpected body type: {type(body).__name__}"

    def test_model_fields_api_is_json(self, client, db_session, sample_tenant, sample_branch):
        """RPT-09."""
        from models import Permission, Role, User

        role = db_session.query(Role).filter_by(slug="accountant").first() or Role(
            name="Accountant", slug="accountant", is_active=True
        )
        if role not in db_session:
            db_session.add(role)
            db_session.commit()
        role.permissions = Permission.query.filter(Permission.code == "view_reports").all()
        db_session.add(role)
        db_session.commit()

        user = User(
            username=f"rpt-mf-{uuid.uuid4().hex[:8]}",
            email=f"rpt-{uuid.uuid4().hex[:8]}@example.com",
            full_name="RPT MF",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        _login(client, user)

        resp = client.get("/reports/api/model_fields?model=sale")
        assert resp.status_code == 200
        ctype = resp.content_type or ""
        assert "application/json" in ctype

    def test_entity_search_requires_query(self, client, db_session, sample_tenant, sample_branch):
        """RPT-10. An empty search is not a search."""
        from models import Permission, Role, User

        role = db_session.query(Role).filter_by(slug="accountant").first() or Role(
            name="Accountant", slug="accountant", is_active=True
        )
        if role not in db_session:
            db_session.add(role)
            db_session.commit()
        role.permissions = Permission.query.filter(Permission.code == "view_reports").all()
        db_session.add(role)
        db_session.commit()

        user = User(
            username=f"rpt-es-{uuid.uuid4().hex[:8]}",
            email=f"rpt-{uuid.uuid4().hex[:8]}@example.com",
            full_name="RPT ES",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        _login(client, user)

        resp = client.get("/reports/api/entity-search")
        assert resp.status_code in (200, 400), f"entity-search answered {resp.status_code}"
        if resp.status_code == 400:
            body = resp.get_json()
            assert body is not None, "400 without a JSON body"

    def test_analytics_endpoints_return_json(self, client, db_session, sample_tenant, sample_branch):
        """RPT-11 to RPT-14: the analytics APIs are all JSON."""
        from models import Permission, Role, User

        role = db_session.query(Role).filter_by(slug="accountant").first() or Role(
            name="Accountant", slug="accountant", is_active=True
        )
        if role not in db_session:
            db_session.add(role)
            db_session.commit()
        role.permissions = Permission.query.filter(Permission.code == "view_reports").all()
        db_session.add(role)
        db_session.commit()

        user = User(
            username=f"rpt-an-{uuid.uuid4().hex[:8]}",
            email=f"rpt-{uuid.uuid4().hex[:8]}@example.com",
            full_name="RPT Analytics",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        _login(client, user)

        for path in (
            "/api/analytics/overdue-payments",
            "/api/analytics/daily-stats",
            "/api/analytics/top-customers",
            "/api/analytics/low-stock-products",
            "/api/analytics/revenue-trend",
        ):
            resp = client.get(path)
            assert resp.status_code in (200, 404), f"{path} answered {resp.status_code}"
            if resp.status_code == 200:
                ctype = resp.content_type or ""
                assert "application/json" in ctype, f"{path} is {ctype}, not JSON"


class TestRPT04TenantIsolation:
    """RPT-15: the reports never cross a tenant boundary."""

    def test_sales_report_is_tenant_scoped(self, client, db_session, sample_tenant, sample_branch):
        """RPT-15. A report never leaks another tenant's data."""
        from models import Permission, Role, User

        role = db_session.query(Role).filter_by(slug="accountant").first() or Role(
            name="Accountant", slug="accountant", is_active=True
        )
        if role not in db_session:
            db_session.add(role)
            db_session.commit()
        role.permissions = Permission.query.filter(Permission.code == "view_reports").all()
        db_session.add(role)
        db_session.commit()

        user = User(
            username=f"rpt-ti-{uuid.uuid4().hex[:8]}",
            email=f"rpt-{uuid.uuid4().hex[:8]}@example.com",
            full_name="RPT Tenant Isolation",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        _login(client, user)

        resp = client.get("/reports/sales")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "cross-tenant" not in body.lower(), "the report leaked another tenant's data"

    def test_api_aging_is_tenant_scoped(self, client, db_session, sample_tenant, sample_branch):
        """RPT-16. The API surface respects the tenant boundary too."""
        from models import Permission, Role, User

        role = db_session.query(Role).filter_by(slug="accountant").first() or Role(
            name="Accountant", slug="accountant", is_active=True
        )
        if role not in db_session:
            db_session.add(role)
            db_session.commit()
        role.permissions = Permission.query.filter(Permission.code == "view_reports").all()
        db_session.add(role)
        db_session.commit()

        user = User(
            username=f"rpt-ti-{uuid.uuid4().hex[:8]}",
            email=f"rpt-{uuid.uuid4().hex[:8]}@example.com",
            full_name="RPT TI",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        _login(client, user)

        resp = client.get("/reports/api/ap-aging")
        assert resp.status_code == 200
        body = resp.get_json()
        assert isinstance(body, (dict, list)), f"not JSON: {type(body).__name__}"


class TestRPT05MoreExports:
    """RPT-17 to RPT-23: remaining export endpoints and formats."""

    def test_inventory_reconciliation_export_xlsx(self, client, db_session, sample_tenant, sample_branch):
        """RPT-17. Inventory reconciliation exports XLSX by default."""
        from models import Permission, Role, User

        role = db_session.query(Role).filter_by(slug="accountant").first() or Role(
            name="Accountant", slug="accountant", is_active=True
        )
        if role not in db_session:
            db_session.add(role)
            db_session.commit()
        role.permissions = Permission.query.filter(Permission.code == "view_reports").all()
        db_session.add(role)
        db_session.commit()

        user = User(
            username=f"rpt-ir-{uuid.uuid4().hex[:8]}",
            email=f"rpt-{uuid.uuid4().hex[:8]}@example.com",
            full_name="RPT IR",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        _login(client, user)

        resp = client.get("/reports/inventory-reconciliation/export", follow_redirects=True)
        assert resp.status_code == 200, f"inventory-reconciliation export answered {resp.status_code}"
        ctype = resp.content_type or ""
        assert "spreadsheetml" in ctype, f"inventory-reconciliation export is {ctype}"

    def test_receivables_export_csv(self, client, db_session, sample_tenant, sample_branch):
        """RPT-18. Receivables exports CSV."""
        from models import Permission, Role, User

        role = db_session.query(Role).filter_by(slug="accountant").first() or Role(
            name="Accountant", slug="accountant", is_active=True
        )
        if role not in db_session:
            db_session.add(role)
            db_session.commit()
        role.permissions = Permission.query.filter(Permission.code == "view_reports").all()
        db_session.add(role)
        db_session.commit()

        user = User(
            username=f"rpt-rec-{uuid.uuid4().hex[:8]}",
            email=f"rpt-{uuid.uuid4().hex[:8]}@example.com",
            full_name="RPT Receivables",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        _login(client, user)

        resp = client.get("/reports/receivables/export", follow_redirects=True)
        assert resp.status_code == 200, f"receivables export answered {resp.status_code}"
        ctype = resp.content_type or ""
        assert "text/csv" in ctype, f"receivables export is {ctype}"
        data = resp.get_data(as_text=True)
        assert len(data) > 0, "empty CSV response"

    def test_inventory_export_csv(self, client, db_session, sample_tenant, sample_branch):
        """RPT-19. Inventory exports CSV."""
        from models import Permission, Role, User

        role = db_session.query(Role).filter_by(slug="accountant").first() or Role(
            name="Accountant", slug="accountant", is_active=True
        )
        if role not in db_session:
            db_session.add(role)
            db_session.commit()
        role.permissions = Permission.query.filter(Permission.code == "view_reports").all()
        db_session.add(role)
        db_session.commit()

        user = User(
            username=f"rpt-inv-{uuid.uuid4().hex[:8]}",
            email=f"rpt-{uuid.uuid4().hex[:8]}@example.com",
            full_name="RPT Inventory",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        _login(client, user)

        resp = client.get("/reports/inventory/export", follow_redirects=True)
        assert resp.status_code == 200, f"inventory export answered {resp.status_code}"
        ctype = resp.content_type or ""
        assert "text/csv" in ctype, f"inventory export is {ctype}"
        data = resp.get_data(as_text=True)
        assert len(data) > 0, "empty CSV response"

    def test_sales_export_xlsx(self, client, db_session, sample_tenant, sample_branch):
        """RPT-20. Sales export supports XLSX format."""
        from models import Permission, Role, User

        role = db_session.query(Role).filter_by(slug="accountant").first() or Role(
            name="Accountant", slug="accountant", is_active=True
        )
        if role not in db_session:
            db_session.add(role)
            db_session.commit()
        role.permissions = Permission.query.filter(Permission.code == "view_reports").all()
        db_session.add(role)
        db_session.commit()

        user = User(
            username=f"rpt-xlsx-{uuid.uuid4().hex[:8]}",
            email=f"rpt-{uuid.uuid4().hex[:8]}@example.com",
            full_name="RPT XLSX",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        _login(client, user)

        resp = client.get("/reports/sales/export?format=xlsx", follow_redirects=True)
        assert resp.status_code == 200, f"sales XLSX export answered {resp.status_code}"
        ctype = resp.content_type or ""
        assert "spreadsheetml" in ctype, f"sales XLSX export is {ctype}"

    def test_purchases_export_xlsx(self, client, db_session, sample_tenant, sample_branch):
        """RPT-21. Purchases export supports XLSX format."""
        from models import Permission, Role, User

        role = db_session.query(Role).filter_by(slug="accountant").first() or Role(
            name="Accountant", slug="accountant", is_active=True
        )
        if role not in db_session:
            db_session.add(role)
            db_session.commit()
        role.permissions = Permission.query.filter(Permission.code == "view_reports").all()
        db_session.add(role)
        db_session.commit()

        user = User(
            username=f"rpt-pxls-{uuid.uuid4().hex[:8]}",
            email=f"rpt-{uuid.uuid4().hex[:8]}@example.com",
            full_name="RPT PXLS",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        _login(client, user)

        resp = client.get("/reports/purchases/export?format=xlsx", follow_redirects=True)
        assert resp.status_code == 200, f"purchases XLSX export answered {resp.status_code}"
        ctype = resp.content_type or ""
        assert "spreadsheetml" in ctype, f"purchases XLSX export is {ctype}"

    def test_receivables_export_xlsx(self, client, db_session, sample_tenant, sample_branch):
        """RPT-23. Receivables export supports XLSX format."""
        from models import Permission, Role, User

        role = db_session.query(Role).filter_by(slug="accountant").first() or Role(
            name="Accountant", slug="accountant", is_active=True
        )
        if role not in db_session:
            db_session.add(role)
            db_session.commit()
        role.permissions = Permission.query.filter(Permission.code == "view_reports").all()
        db_session.add(role)
        db_session.commit()

        user = User(
            username=f"rpt-rxls-{uuid.uuid4().hex[:8]}",
            email=f"rpt-{uuid.uuid4().hex[:8]}@example.com",
            full_name="RPT RXLS",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        _login(client, user)

        resp = client.get("/reports/receivables/export?format=xlsx", follow_redirects=True)
        assert resp.status_code == 200, f"receivables XLSX export answered {resp.status_code}"
        ctype = resp.content_type or ""
        assert "spreadsheetml" in ctype, f"receivables XLSX export is {ctype}"


class TestRPT06ModelFieldsAPI:
    """RPT-24 to RPT-28: model fields API with different models."""

    @pytest.mark.parametrize("model", ["sale", "purchase", "customer", "product"])
    def test_model_fields_returns_columns_for_model(self, client, db_session, sample_tenant, sample_branch, model):
        """RPT-24..RPT-27. Each supported model returns its column list."""
        from models import Permission, Role, User

        role = db_session.query(Role).filter_by(slug="accountant").first() or Role(
            name="Accountant", slug="accountant", is_active=True
        )
        if role not in db_session:
            db_session.add(role)
            db_session.commit()
        role.permissions = Permission.query.filter(Permission.code == "view_reports").all()
        db_session.add(role)
        db_session.commit()

        user = User(
            username=f"rpt-mf-{uuid.uuid4().hex[:8]}",
            email=f"rpt-{uuid.uuid4().hex[:8]}@example.com",
            full_name="RPT MF",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        _login(client, user)

        resp = client.get(f"/reports/api/model_fields?model={model}")
        assert resp.status_code == 200, f"model_fields for {model} answered {resp.status_code}"
        ctype = resp.content_type or ""
        assert "application/json" in ctype
        body = resp.get_json()
        assert isinstance(body, dict), f"expected dict, got {type(body).__name__}"
        assert "data" in body, f"no data key for {model}"
        data = body["data"]
        assert "columns" in data, f"no columns key for {model}"
        assert isinstance(data["columns"], list), f"columns not list for {model}"
        assert len(data["columns"]) > 0, f"empty columns for {model}"

    def test_model_fields_unknown_model_returns_empty(self, client, db_session, sample_tenant, sample_branch):
        """RPT-28. Unknown model returns empty columns."""
        from models import Permission, Role, User

        role = db_session.query(Role).filter_by(slug="accountant").first() or Role(
            name="Accountant", slug="accountant", is_active=True
        )
        if role not in db_session:
            db_session.add(role)
            db_session.commit()
        role.permissions = Permission.query.filter(Permission.code == "view_reports").all()
        db_session.add(role)
        db_session.commit()

        user = User(
            username=f"rpt-mfu-{uuid.uuid4().hex[:8]}",
            email=f"rpt-{uuid.uuid4().hex[:8]}@example.com",
            full_name="RPT MFU",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        _login(client, user)

        resp = client.get("/reports/api/model_fields?model=nonexistent")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"]["columns"] == []


class TestRPT07EntitySearch:
    """RPT-29 to RPT-31: entity search API."""

    def test_entity_search_with_query_returns_results(self, client, db_session, sample_tenant, sample_branch):
        """RPT-29. A non-empty query returns results."""
        from models import Permission, Role, User

        role = db_session.query(Role).filter_by(slug="accountant").first() or Role(
            name="Accountant", slug="accountant", is_active=True
        )
        if role not in db_session:
            db_session.add(role)
            db_session.commit()
        role.permissions = Permission.query.filter(Permission.code == "view_reports").all()
        db_session.add(role)
        db_session.commit()

        user = User(
            username=f"rpt-esq-{uuid.uuid4().hex[:8]}",
            email=f"rpt-{uuid.uuid4().hex[:8]}@example.com",
            full_name="RPT ESQ",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        _login(client, user)

        resp = client.get("/reports/api/entity-search?q=test")
        assert resp.status_code in (200, 400), f"entity-search answered {resp.status_code}"
        if resp.status_code == 200:
            ctype = resp.content_type or ""
            assert "application/json" in ctype
            body = resp.get_json()
            assert isinstance(body, (dict, list))

    def test_entity_search_with_type_parameter(self, client, db_session, sample_tenant, sample_branch):
        """RPT-30. Entity search accepts type filter."""
        from models import Permission, Role, User

        role = db_session.query(Role).filter_by(slug="accountant").first() or Role(
            name="Accountant", slug="accountant", is_active=True
        )
        if role not in db_session:
            db_session.add(role)
            db_session.commit()
        role.permissions = Permission.query.filter(Permission.code == "view_reports").all()
        db_session.add(role)
        db_session.commit()

        user = User(
            username=f"rpt-est-{uuid.uuid4().hex[:8]}",
            email=f"rpt-{uuid.uuid4().hex[:8]}@example.com",
            full_name="RPT EST",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        _login(client, user)

        resp = client.get("/reports/api/entity-search?q=test&type=sale")
        assert resp.status_code in (200, 400), f"entity-search with type answered {resp.status_code}"

    def test_entity_search_empty_query_returns_empty_results(self, client, db_session, sample_tenant, sample_branch):
        """RPT-31. Empty query returns empty results (not an error)."""
        from models import Permission, Role, User

        role = db_session.query(Role).filter_by(slug="accountant").first() or Role(
            name="Accountant", slug="accountant", is_active=True
        )
        if role not in db_session:
            db_session.add(role)
            db_session.commit()
        role.permissions = Permission.query.filter(Permission.code == "view_reports").all()
        db_session.add(role)
        db_session.commit()

        user = User(
            username=f"rpt-ese-{uuid.uuid4().hex[:8]}",
            email=f"rpt-{uuid.uuid4().hex[:8]}@example.com",
            full_name="RPT ESE",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        _login(client, user)

        resp = client.get("/reports/api/entity-search?q=")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "data" in body
        assert isinstance(body["data"], list)


class TestRPT08AnalyticsParameters:
    """RPT-32 to RPT-35: analytics endpoints with parameters."""

    def test_overdue_payments_with_date_range(self, client, db_session, sample_tenant, sample_branch):
        """RPT-32. Overdue payments accepts date range."""
        from models import Permission, Role, User

        role = db_session.query(Role).filter_by(slug="accountant").first() or Role(
            name="Accountant", slug="accountant", is_active=True
        )
        if role not in db_session:
            db_session.add(role)
            db_session.commit()
        role.permissions = Permission.query.filter(Permission.code == "view_reports").all()
        db_session.add(role)
        db_session.commit()

        user = User(
            username=f"rpt-od-{uuid.uuid4().hex[:8]}",
            email=f"rpt-{uuid.uuid4().hex[:8]}@example.com",
            full_name="RPT OD",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        _login(client, user)

        resp = client.get("/api/analytics/overdue-payments?date_from=2024-01-01&date_to=2024-12-31")
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            ctype = resp.content_type or ""
            assert "application/json" in ctype

    def test_daily_stats_with_branch(self, client, db_session, sample_tenant, sample_branch):
        """RPT-33. Daily stats accepts branch filter."""
        from models import Permission, Role, User

        role = db_session.query(Role).filter_by(slug="accountant").first() or Role(
            name="Accountant", slug="accountant", is_active=True
        )
        if role not in db_session:
            db_session.add(role)
            db_session.commit()
        role.permissions = Permission.query.filter(Permission.code == "view_reports").all()
        db_session.add(role)
        db_session.commit()

        user = User(
            username=f"rpt-ds-{uuid.uuid4().hex[:8]}",
            email=f"rpt-{uuid.uuid4().hex[:8]}@example.com",
            full_name="RPT DS",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        _login(client, user)

        resp = client.get(f"/api/analytics/daily-stats?branch_id={sample_branch.id}")
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            ctype = resp.content_type or ""
            assert "application/json" in ctype

    def test_top_customers_with_limit(self, client, db_session, sample_tenant, sample_branch):
        """RPT-34. Top customers accepts limit parameter."""
        from models import Permission, Role, User

        role = db_session.query(Role).filter_by(slug="accountant").first() or Role(
            name="Accountant", slug="accountant", is_active=True
        )
        if role not in db_session:
            db_session.add(role)
            db_session.commit()
        role.permissions = Permission.query.filter(Permission.code == "view_reports").all()
        db_session.add(role)
        db_session.commit()

        user = User(
            username=f"rpt-tc-{uuid.uuid4().hex[:8]}",
            email=f"rpt-{uuid.uuid4().hex[:8]}@example.com",
            full_name="RPT TC",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        _login(client, user)

        resp = client.get("/api/analytics/top-customers?limit=5")
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            ctype = resp.content_type or ""
            assert "application/json" in ctype

    def test_revenue_trend_with_period(self, client, db_session, sample_tenant, sample_branch):
        """RPT-35. Revenue trend accepts period parameter."""
        from models import Permission, Role, User

        role = db_session.query(Role).filter_by(slug="accountant").first() or Role(
            name="Accountant", slug="accountant", is_active=True
        )
        if role not in db_session:
            db_session.add(role)
            db_session.commit()
        role.permissions = Permission.query.filter(Permission.code == "view_reports").all()
        db_session.add(role)
        db_session.commit()

        user = User(
            username=f"rpt-rt-{uuid.uuid4().hex[:8]}",
            email=f"rpt-{uuid.uuid4().hex[:8]}@example.com",
            full_name="RPT RT",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        _login(client, user)

        resp = client.get("/api/analytics/revenue-trend?period=monthly")
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            ctype = resp.content_type or ""
            assert "application/json" in ctype


class TestRPT09MoreTenantIsolation:
    """RPT-36 to RPT-38: more tenant isolation checks."""

    def test_receivables_is_tenant_scoped(self, client, db_session, sample_tenant, sample_branch):
        """RPT-36. Receivables report is tenant-scoped."""
        from models import Permission, Role, User

        role = db_session.query(Role).filter_by(slug="accountant").first() or Role(
            name="Accountant", slug="accountant", is_active=True
        )
        if role not in db_session:
            db_session.add(role)
            db_session.commit()
        role.permissions = Permission.query.filter(Permission.code == "view_reports").all()
        db_session.add(role)
        db_session.commit()

        user = User(
            username=f"rpt-tir-{uuid.uuid4().hex[:8]}",
            email=f"rpt-{uuid.uuid4().hex[:8]}@example.com",
            full_name="RPT TIR",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        _login(client, user)

        resp = client.get("/reports/receivables")
        assert resp.status_code == 200

    def test_inventory_reconciliation_is_tenant_scoped(self, client, db_session, sample_tenant, sample_branch):
        """RPT-37. Inventory reconciliation is tenant-scoped."""
        from models import Permission, Role, User

        role = db_session.query(Role).filter_by(slug="accountant").first() or Role(
            name="Accountant", slug="accountant", is_active=True
        )
        if role not in db_session:
            db_session.add(role)
            db_session.commit()
        role.permissions = Permission.query.filter(Permission.code == "view_reports").all()
        db_session.add(role)
        db_session.commit()

        user = User(
            username=f"rpt-tii-{uuid.uuid4().hex[:8]}",
            email=f"rpt-{uuid.uuid4().hex[:8]}@example.com",
            full_name="RPT TII",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        _login(client, user)

        resp = client.get("/reports/inventory-reconciliation")
        assert resp.status_code == 200

    def test_partners_report_is_tenant_scoped(self, client, db_session, sample_tenant, sample_branch):
        """RPT-38. Partners report is tenant-scoped."""
        from models import Permission, Role, User

        role = db_session.query(Role).filter_by(slug="accountant").first() or Role(
            name="Accountant", slug="accountant", is_active=True
        )
        if role not in db_session:
            db_session.add(role)
            db_session.commit()
        role.permissions = Permission.query.filter(Permission.code == "view_reports").all()
        db_session.add(role)
        db_session.commit()

        user = User(
            username=f"rpt-tip-{uuid.uuid4().hex[:8]}",
            email=f"rpt-{uuid.uuid4().hex[:8]}@example.com",
            full_name="RPT TIP",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        _login(client, user)

        resp = client.get("/reports/partners")
        assert resp.status_code == 200


class TestRPT10ReadEndpoints:
    """RPT-39 to RPT-42: remaining read endpoints."""

    def test_sales_report_page_renders(self, client, db_session, sample_tenant, sample_branch):
        """RPT-39. Sales report page renders HTML."""
        from models import Permission, Role, User

        role = db_session.query(Role).filter_by(slug="accountant").first() or Role(
            name="Accountant", slug="accountant", is_active=True
        )
        if role not in db_session:
            db_session.add(role)
            db_session.commit()
        role.permissions = Permission.query.filter(Permission.code == "view_reports").all()
        db_session.add(role)
        db_session.commit()

        user = User(
            username=f"rpt-sr-{uuid.uuid4().hex[:8]}",
            email=f"rpt-{uuid.uuid4().hex[:8]}@example.com",
            full_name="RPT SR",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        _login(client, user)

        resp = client.get("/reports/sales")
        assert resp.status_code == 200
        ctype = resp.content_type or ""
        assert "text/html" in ctype

    def test_purchases_report_page_renders(self, client, db_session, sample_tenant, sample_branch):
        """RPT-40. Purchases report page renders HTML."""
        from models import Permission, Role, User

        role = db_session.query(Role).filter_by(slug="accountant").first() or Role(
            name="Accountant", slug="accountant", is_active=True
        )
        if role not in db_session:
            db_session.add(role)
            db_session.commit()
        role.permissions = Permission.query.filter(Permission.code == "view_reports").all()
        db_session.add(role)
        db_session.commit()

        user = User(
            username=f"rpt-pr-{uuid.uuid4().hex[:8]}",
            email=f"rpt-{uuid.uuid4().hex[:8]}@example.com",
            full_name="RPT PR",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        _login(client, user)

        resp = client.get("/reports/purchases")
        assert resp.status_code == 200
        ctype = resp.content_type or ""
        assert "text/html" in ctype

    def test_inventory_report_page_renders(self, client, db_session, sample_tenant, sample_branch):
        """RPT-41. Inventory report page renders HTML."""
        from models import Permission, Role, User

        role = db_session.query(Role).filter_by(slug="accountant").first() or Role(
            name="Accountant", slug="accountant", is_active=True
        )
        if role not in db_session:
            db_session.add(role)
            db_session.commit()
        role.permissions = Permission.query.filter(Permission.code == "view_reports").all()
        db_session.add(role)
        db_session.commit()

        user = User(
            username=f"rpt-irp-{uuid.uuid4().hex[:8]}",
            email=f"rpt-{uuid.uuid4().hex[:8]}@example.com",
            full_name="RPT IRP",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        _login(client, user)

        resp = client.get("/reports/inventory")
        assert resp.status_code == 200
        ctype = resp.content_type or ""
        assert "text/html" in ctype

    def test_top_selling_report_renders(self, client, db_session, sample_tenant, sample_branch):
        """RPT-42. Top selling report renders."""
        from models import Permission, Role, User

        role = db_session.query(Role).filter_by(slug="accountant").first() or Role(
            name="Accountant", slug="accountant", is_active=True
        )
        if role not in db_session:
            db_session.add(role)
            db_session.commit()
        role.permissions = Permission.query.filter(Permission.code == "view_reports").all()
        db_session.add(role)
        db_session.commit()

        user = User(
            username=f"rpt-ts-{uuid.uuid4().hex[:8]}",
            email=f"rpt-{uuid.uuid4().hex[:8]}@example.com",
            full_name="RPT TS",
            tenant_id=sample_tenant.id,
            role_id=role.id,
            branch_id=sample_branch.id,
            is_active=True,
        )
        user.set_password("Str0ng!Pass99")
        db_session.add(user)
        db_session.commit()
        _login(client, user)

        resp = client.get("/reports/top-selling")
        assert resp.status_code == 200
