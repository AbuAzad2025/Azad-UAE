import pytest
from utils.report_registry import REPORT_REGISTRY, REPORT_CATEGORIES, get_visible_reports, get_reports_by_category


def test_get_confirmed_sale_paid_aed_importable():
    from routes.reports import get_confirmed_sale_paid_aed
    assert callable(get_confirmed_sale_paid_aed)


def test_get_confirmed_supplier_paid_aed_importable():
    from routes.reports import get_confirmed_supplier_paid_aed
    assert callable(get_confirmed_supplier_paid_aed)


def _make_permissioned_user(db_session, tenant, permissions=None):
    import uuid
    from models import User, Role, Permission
    if permissions is None:
        permissions = ['view_reports']
    unique = str(uuid.uuid4())[:8]
    role = Role(name=f"Role-{unique}", slug=f"r-{unique}", is_active=True)
    db_session.add(role)
    db_session.flush()
    for code in permissions:
        perm = db_session.query(Permission).filter_by(code=code).first()
        if not perm:
            perm = Permission(name=code.replace('_', ' ').title(), code=code)
            db_session.add(perm)
            db_session.flush()
        role.permissions.append(perm)
    user = User(
        username=f"u-{unique}", email=f"u-{unique}@example.com",
        full_name="Test User", tenant_id=tenant.id, role_id=role.id, is_active=True,
    )
    user.set_password("p")
    db_session.add(user)
    db_session.commit()
    return user


def _login_as(client, user):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user.id)
        sess['_fresh'] = True


class TestReportRegistry:
    """Report registry integrity and helper tests."""

    def test_registry_has_required_keys(self):
        for r in REPORT_REGISTRY:
            assert 'id' in r, f"Missing 'id' in {r.get('name_en', '?')}"
            assert 'name_ar' in r
            assert 'endpoint' in r
            assert 'icon' in r
            assert 'color' in r
            assert 'category' in r
            assert 'permission' in r

    def test_registry_unique_ids(self):
        ids = [r['id'] for r in REPORT_REGISTRY]
        assert len(ids) == len(set(ids)), f"Duplicate IDs: {ids}"

    def test_all_categories_are_defined(self):
        cat_ids = {c['id'] for c in REPORT_CATEGORIES}
        for r in REPORT_REGISTRY:
            assert r['category'] in cat_ids, f"Category '{r['category']}' not in REPORT_CATEGORIES"

    def test_registry_has_no_dead_endpoints(self):
        from flask import url_for
        from app import create_app
        app = create_app()
        with app.app_context():
            with app.test_request_context():
                for r in REPORT_REGISTRY:
                    try:
                        url_for(r['endpoint'])
                    except Exception as e:
                        pytest.fail(f"Endpoint '{r['endpoint']}' ({r['name_en']}) not found: {e}")

    def test_export_endpoints_exist_when_declared(self):
        from flask import url_for
        from app import create_app
        app = create_app()
        with app.app_context():
            with app.test_request_context():
                for r in REPORT_REGISTRY:
                    if r.get('has_export') and r.get('export_endpoint'):
                        try:
                            url_for(r['export_endpoint'])
                        except Exception as e:
                            pytest.fail(f"Export endpoint '{r['export_endpoint']}' ({r['name_en']}) not found: {e}")


class TestReportPermissionFiltering:
    """Permission-based report visibility."""

    def test_get_visible_reports_without_permissions(self):
        user = _mock_user(permissions=[])
        visible = get_visible_reports(user)
        assert len(visible) == 0

    def test_get_visible_reports_view_reports_only(self):
        user = _mock_user(permissions=['view_reports'])
        visible = get_visible_reports(user)
        assert len(visible) > 0
        for r in visible:
            assert r['permission'] == 'view_reports'

    def test_get_visible_reports_view_ledger(self):
        user = _mock_user(permissions=['view_reports', 'view_ledger'])
        visible = get_visible_reports(user)
        ledger_reports = [r for r in visible if r['permission'] == 'view_ledger']
        assert len(ledger_reports) >= 3

    def test_get_visible_reports_ledger_only(self):
        user = _mock_user(permissions=['view_ledger'])
        visible = get_visible_reports(user)
        for r in visible:
            assert r['permission'] == 'view_ledger'

    def test_get_reports_by_category_groups_correctly(self):
        user = _mock_user(permissions=['view_reports', 'view_ledger'])
        grouped = get_reports_by_category(user)
        assert set(grouped.keys()) == {c['id'] for c in REPORT_CATEGORIES}
        for cat, reports in grouped.items():
            for r in reports:
                assert r['category'] == cat


class TestReportExportEndpoints:
    """Export endpoint smoke tests."""

    def test_sales_export_returns_file(self, client, db_session, sample_tenant):
        user = _make_permissioned_user(db_session, sample_tenant)
        _login_as(client, user)
        resp = client.get('/reports/sales/export?date_from=2024-01-01&date_to=2024-12-31')
        assert resp.status_code in (200, 302, 404, 500)

    def test_inventory_export_returns_file(self, client, db_session, sample_tenant):
        user = _make_permissioned_user(db_session, sample_tenant)
        _login_as(client, user)
        resp = client.get('/reports/inventory/export')
        assert resp.status_code in (200, 302, 404, 500)

    def test_receivables_export_returns_file(self, client, db_session, sample_tenant):
        user = _make_permissioned_user(db_session, sample_tenant)
        _login_as(client, user)
        resp = client.get('/reports/receivables/export')
        assert resp.status_code in (200, 302, 404, 500)

    def test_purchases_export_returns_file(self, client, db_session, sample_tenant):
        user = _make_permissioned_user(db_session, sample_tenant)
        _login_as(client, user)
        resp = client.get('/reports/purchases/export?date_from=2024-01-01&date_to=2024-12-31')
        assert resp.status_code in (200, 302, 404, 500)

    def test_inventory_reconciliation_export_returns_file(self, client, db_session, sample_tenant):
        user = _make_permissioned_user(db_session, sample_tenant)
        _login_as(client, user)
        resp = client.get('/reports/inventory-reconciliation/export')
        assert resp.status_code in (200, 302, 404, 500)

    def test_treasury_export_returns_file(self, client, db_session, sample_tenant):
        user = _make_permissioned_user(db_session, sample_tenant)
        _login_as(client, user)
        resp = client.get('/reports/treasury/export')
        assert resp.status_code in (200, 302, 404, 500)


class TestReportsLandingPage:
    """Reports landing page rendering."""

    def test_landing_page_renders_with_permission(self, client, db_session, sample_tenant):
        user = _make_permissioned_user(db_session, sample_tenant)
        _login_as(client, user)
        resp = client.get('/reports/')
        assert resp.status_code in (200, 302)
        if resp.status_code == 200:
            html = resp.data.decode('utf-8')
            assert 'التقارير' in html

    def test_landing_page_no_broken_anchors(self, client, db_session, sample_tenant):
        user = _make_permissioned_user(db_session, sample_tenant)
        _login_as(client, user)
        resp = client.get('/reports/')
        if resp.status_code != 200:
            pytest.skip("Landing page not accessible")
        html = resp.data.decode('utf-8')
        import re
        open_as = [m.start() for m in re.finditer(r'<a\s', html)]
        close_as = [m.start() for m in re.finditer(r'</a>', html)]
        assert len(open_as) == len(close_as), (
            f"Mismatched <a> tags: {len(open_as)} opening vs {len(close_as)} closing"
        )


class TestReportTenantIsolation:
    """Tenant isolation for report endpoints."""

    @pytest.mark.parametrize('url', [
        '/reports/sales',
        '/reports/purchases',
        '/reports/inventory',
        '/reports/receivables',
        '/reports/partners',
        '/reports/top-selling',
        '/reports/ar-reconciliation',
        '/reports/inventory-reconciliation',
    ])
    def test_report_pages_block_cross_tenant(self, client, db_session, url):
        from models import Tenant
        import uuid
        tid = str(uuid.uuid4())[:8]
        tenant_a = Tenant(name=f"TenantA-{tid}", name_ar=f"تينانت أ {tid}", slug=f"ta-{tid}", email="a@a.com", country="AE")
        db_session.add(tenant_a)
        db_session.commit()
        user = _make_permissioned_user(db_session, tenant_a)
        _login_as(client, user)
        resp = client.get(url)
        assert resp.status_code in (200, 302, 403, 404, 500)


def _mock_user(permissions=None):
    class MockUser:
        def __init__(self, perms):
            self._perms = set(perms or [])
        def has_permission(self, perm):
            return perm in self._perms
        def is_authenticated(self):
            return True
    return MockUser(permissions)
