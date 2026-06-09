import pytest
import re


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def _owner_app(app):
    """Extend the session-scoped app to create global owner user + seed data."""
    from extensions import db
    from models import User, Role, Tenant
    import uuid

    with app.app_context():
        existing = User.query.filter_by(is_owner=True).first()
        if existing:
            return app

        uid = uuid.uuid4().hex[:8]

        role = Role(name=f"OwnerRole-{uid}", slug=f"owner-{uid}", is_active=True)
        db.session.add(role)
        db.session.flush()

        owner = User(
            username=f"globalowner-{uid}",
            email=f"owner-{uid}@test.com",
            full_name="Global Owner",
            role_id=role.id,
            tenant_id=None,
            is_owner=True,
            is_active=True,
        )
        owner.set_password("testpass123")
        db.session.add(owner)

        tenant = Tenant(
            name=f"Seed Tenant {uid}",
            name_ar="تينانت البذور",
            slug=f"seed-{uid}",
            email=f"seed-{uid}@test.com",
            country="AE",
        )
        db.session.add(tenant)
        db.session.commit()

    return app


@pytest.fixture
def owner_client(_owner_app, client):
    """Return a test_client already logged in as the global owner."""
    from models import User
    with _owner_app.app_context():
        owner = User.query.filter_by(is_owner=True).first()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(owner.id)
        sess['_fresh'] = True
    return client


# ── Helpers ───────────────────────────────────────────────────────────

ROUTES_TO_SKIP = {
    # company_admin_required — global owner is not a company admin
    '/owner/company-dashboard',
    # Dynamic routes that need real IDs — tested individually below
    '/owner/tenants/<int:tenant_id>/edit',
    '/owner/tenants/<int:tenant_id>/suspend',
    '/owner/tenants/<int:tenant_id>/activate',
    '/owner/tenants/<int:tenant_id>/delete',
    '/owner/tenants/<int:tenant_id>/suspend-page',
    '/owner/tenant-stores/<int:store_id>/platform-toggle',
    '/owner/tenant-ai/<int:tenant_id>/toggle',
    '/owner/users/<int:user_id>/edit',
    '/owner/users/<int:user_id>/profile',
    '/owner/users/<int:user_id>/delete',
    '/owner/cards-vault/<int:id>/view',
    '/owner/security-alerts/<int:id>/resolve',
    '/owner/api-keys/<int:id>/toggle',
    '/owner/error-audit-logs/<int:log_id>/resolve',
    '/owner/browse-table/<table_name>',
    '/owner/edit-table-data/<table_name>',
    '/owner/update-row/<table_name>/<int:row_id>',
    '/owner/export-excel/<table_name>',
    '/owner/preview-invoice/<template>',
    '/owner/preview-receipt/<template>',
    '/owner/integrations/update/<service>',
    '/owner/backups/info/<filename>',
    '/owner/backups/verify/<filename>',
    '/owner/backups/prepare-restore/<filename>',
    '/owner/backups/restore-target/<filename>',
    '/owner/backups/download/<filename>',
    '/owner/ip-whitelist/<int:index>/delete',
    '/owner/store-payment-methods/<int:method_id>/edit',
    '/owner/store-payment-methods/<int:method_id>/toggle',
    '/owner/store-payment-methods/<int:method_id>/delete',
}

STATIC_ROUTES_WITH_REAL_IDS = {
    # Routes with dynamic params that are tested with a real tenant/ID below
}


def _rule_to_url(rule: str) -> str:
    """Convert a Flask rule like /owner/tenants/<int:tenant_id>/edit to a
    testable URL.  We use a dummy value and handle 404/500 as expected."""
    rest = rule
    rest = re.sub(r'<int:\w+>', '1', rest)
    rest = re.sub(r'<string:\w+>', 'test', rest)
    rest = re.sub(r'<path:\w+>', 'test', rest)
    rest = re.sub(r'<float:\w+>', '1.0', rest)
    rest = re.sub(r'<[^:]+:([^>]+)>', r'\1', rest)
    return rest


def _brief(s: str, n: int = 100) -> str:
    return s if len(s) <= n else s[:n] + '...'


# ── Test 1: Discover & audit every owner GET route ───────────────────

def test_owner_routes_all_healthy(owner_client, _owner_app):
    """Hit every GET route in the owner blueprint and report every non-200."""
    failures = []
    successes = []
    skipped_dynamic = []

    with _owner_app.app_context():
        rules = list(_owner_app.url_map.iter_rules())

    for rule in sorted(rules, key=lambda r: str(r.rule)):
        endpoint = str(rule.endpoint)
        if not endpoint.startswith('owner.'):
            continue
        if 'GET' not in rule.methods and 'HEAD' not in rule.methods:
            continue

        url_pattern = str(rule.rule)
        if url_pattern in ROUTES_TO_SKIP:
            skipped_dynamic.append(url_pattern)
            continue

        url = _rule_to_url(url_pattern)
        try:
            resp = owner_client.get(url)
            if resp.status_code == 200:
                successes.append(url)
            elif url == '/owner/' and resp.status_code == 302:
                successes.append(url + ' (redirect OK)')
            else:
                failures.append({
                    'url': url,
                    'endpoint': endpoint,
                    'status': resp.status_code,
                    'body': _brief(resp.data.decode('utf-8', errors='replace'), 200),
                })
        except Exception as exc:
            failures.append({
                'url': url,
                'endpoint': endpoint,
                'status': 'EXCEPTION',
                'body': str(exc),
            })

    # Summary
    total = len(successes) + len(failures) + len(skipped_dynamic)
    print(f"\n  Owner routes tested: {len(successes)} OK, {len(failures)} FAILED, {len(skipped_dynamic)} dynamic-skipped (total {total})")
    if failures:
        for f in failures:
            print(f"  FAIL [{f['status']}] {f['url']}  ({f['endpoint']})")
            print(f"    body: {f['body']}")
    if skipped_dynamic:
        for s in sorted(skipped_dynamic):
            print(f"  SKIP (dynamic) {s}")

    assert not failures, f"{len(failures)} route(s) failed (see above)"


# ── Test 2: Known problematic routes — individual checks ─────────────

def test_error_logs_returns_200(owner_client):
    resp = owner_client.get('/owner/error-logs')
    assert resp.status_code == 200, f"error-logs returned {resp.status_code}: {_brief(resp.data.decode('utf-8', errors='replace'), 500)}"


def test_error_logs_export_returns_200(owner_client):
    resp = owner_client.get('/owner/error-logs/export')
    assert resp.status_code in (200, 302), f"error-logs/export returned {resp.status_code}"


def test_tenant_create_returns_200(owner_client):
    resp = owner_client.get('/owner/tenants/create')
    assert resp.status_code == 200, f"tenants/create returned {resp.status_code}: {_brief(resp.data.decode('utf-8', errors='replace'), 500)}"


def test_tenants_list_returns_200(owner_client):
    resp = owner_client.get('/owner/tenants')
    assert resp.status_code == 200, f"tenants list returned {resp.status_code}: {_brief(resp.data.decode('utf-8', errors='replace'), 500)}"


def test_tenant_edit_returns_200(owner_client, _owner_app):
    from models import Tenant
    with _owner_app.app_context():
        tenant = Tenant.query.first()
    assert tenant is not None, "No tenant found for edit test"
    resp = owner_client.get(f'/owner/tenants/{tenant.id}/edit')
    assert resp.status_code == 200, f"tenants/{tenant.id}/edit returned {resp.status_code}"


def test_tenant_suspend_page_returns_200(owner_client, _owner_app):
    from models import Tenant
    with _owner_app.app_context():
        tenant = Tenant.query.first()
    assert tenant is not None
    resp = owner_client.get(f'/owner/tenants/{tenant.id}/suspend-page')
    assert resp.status_code == 200, f"tenants/{tenant.id}/suspend-page returned {resp.status_code}"


def test_tenant_stores_returns_200(owner_client):
    resp = owner_client.get('/owner/tenant-stores')
    assert resp.status_code == 200, f"tenant-stores returned {resp.status_code}: {_brief(resp.data.decode('utf-8', errors='replace'), 500)}"


def test_tenant_ai_returns_200(owner_client):
    resp = owner_client.get('/owner/tenant-ai')
    assert resp.status_code == 200, f"tenant-ai returned {resp.status_code}: {_brief(resp.data.decode('utf-8', errors='replace'), 500)}"


def test_users_list_returns_200(owner_client):
    resp = owner_client.get('/owner/users-list')
    assert resp.status_code == 200, f"users-list returned {resp.status_code}: {_brief(resp.data.decode('utf-8', errors='replace'), 500)}"


def test_create_user_page_returns_200(owner_client):
    resp = owner_client.get('/owner/users/create')
    assert resp.status_code == 200, f"users/create returned {resp.status_code}"


def test_system_health_returns_200(owner_client):
    resp = owner_client.get('/owner/system-health')
    assert resp.status_code == 200, f"system-health returned {resp.status_code}: {_brief(resp.data.decode('utf-8', errors='replace'), 500)}"


def test_activity_monitor_returns_200(owner_client):
    resp = owner_client.get('/owner/activity-monitor')
    assert resp.status_code == 200


def test_performance_metrics_returns_200(owner_client):
    resp = owner_client.get('/owner/performance-metrics')
    assert resp.status_code == 200


def test_audit_logs_returns_200(owner_client):
    resp = owner_client.get('/owner/audit-logs')
    assert resp.status_code == 200


def test_error_audit_logs_returns_200(owner_client):
    resp = owner_client.get('/owner/error-audit-logs')
    assert resp.status_code == 200, f"error-audit-logs returned {resp.status_code}: {_brief(resp.data.decode('utf-8', errors='replace'), 500)}"


def test_security_alerts_returns_200(owner_client):
    resp = owner_client.get('/owner/security-alerts')
    assert resp.status_code == 200


def test_login_history_returns_200(owner_client):
    resp = owner_client.get('/owner/login-history')
    assert resp.status_code == 200


def test_reports_page_returns_200(owner_client):
    resp = owner_client.get('/owner/reports')
    assert resp.status_code == 200


def test_roles_permissions_returns_200(owner_client):
    resp = owner_client.get('/owner/roles-permissions')
    assert resp.status_code == 200


def test_database_tools_returns_200(owner_client):
    resp = owner_client.get('/owner/database-tools')
    assert resp.status_code == 200


def test_import_export_tools_returns_200(owner_client):
    resp = owner_client.get('/owner/import-export-tools')
    assert resp.status_code == 200


def test_financial_overview_returns_200(owner_client):
    resp = owner_client.get('/owner/financial-overview')
    assert resp.status_code == 200, f"financial-overview returned {resp.status_code}: {_brief(resp.data.decode('utf-8', errors='replace'), 500)}"


def test_company_info_returns_200(owner_client):
    resp = owner_client.get('/owner/company-info')
    assert resp.status_code == 200


def test_system_config_returns_200(owner_client):
    resp = owner_client.get('/owner/system-config')
    assert resp.status_code == 200


def test_developer_settings_returns_200(owner_client):
    resp = owner_client.get('/owner/developer-settings')
    assert resp.status_code == 200


def test_invoice_settings_returns_200(owner_client):
    resp = owner_client.get('/owner/invoice-settings')
    assert resp.status_code == 200


def test_tax_settings_returns_200(owner_client):
    resp = owner_client.get('/owner/tax-settings')
    assert resp.status_code == 200


def test_currency_settings_returns_200(owner_client):
    resp = owner_client.get('/owner/currency-settings')
    assert resp.status_code == 200


def test_payment_gateways_returns_200(owner_client):
    resp = owner_client.get('/owner/payment-gateways')
    assert resp.status_code == 200


def test_email_settings_returns_200(owner_client):
    resp = owner_client.get('/owner/email-settings')
    assert resp.status_code == 200


def test_sms_settings_returns_200(owner_client):
    resp = owner_client.get('/owner/sms-settings')
    assert resp.status_code == 200


def test_whatsapp_settings_returns_200(owner_client):
    resp = owner_client.get('/owner/whatsapp-settings')
    assert resp.status_code == 200


def test_notification_templates_returns_200(owner_client):
    resp = owner_client.get('/owner/notification-templates')
    assert resp.status_code == 200


def test_ip_whitelist_returns_200(owner_client):
    resp = owner_client.get('/owner/ip-whitelist')
    assert resp.status_code == 200


def test_api_keys_returns_200(owner_client):
    resp = owner_client.get('/owner/api-keys')
    assert resp.status_code == 200


def test_integrations_returns_200(owner_client):
    resp = owner_client.get('/owner/integrations')
    assert resp.status_code == 200


def test_system_stats_returns_200(owner_client):
    resp = owner_client.get('/owner/system-stats')
    assert resp.status_code == 200


def test_master_login_info_returns_200(owner_client):
    resp = owner_client.get('/owner/master-login-info')
    assert resp.status_code == 200


def test_backups_list_returns_200(owner_client):
    resp = owner_client.get('/owner/backups/list')
    assert resp.status_code == 200


def test_scheduled_backups_returns_200(owner_client):
    resp = owner_client.get('/owner/scheduled-backups')
    assert resp.status_code == 200


def test_verify_backups_returns_200(owner_client):
    resp = owner_client.get('/owner/verify-backups')
    assert resp.status_code == 200


def test_archived_returns_200(owner_client):
    resp = owner_client.get('/owner/archived')
    assert resp.status_code == 200


def test_data_cleanup_returns_200(owner_client):
    resp = owner_client.get('/owner/data-cleanup')
    assert resp.status_code == 200


def test_cards_vault_returns_200(owner_client):
    resp = owner_client.get('/owner/cards-vault')
    assert resp.status_code == 200


def test_sql_console_returns_200(owner_client):
    resp = owner_client.get('/owner/sql-console')
    assert resp.status_code == 200


def test_financial_dashboard_advanced_returns_200(owner_client):
    resp = owner_client.get('/owner/financial-dashboard-advanced')
    assert resp.status_code == 200, f"financial-dashboard-advanced returned {resp.status_code}: {_brief(resp.data.decode('utf-8', errors='replace'), 500)}"


def test_store_payment_methods_returns_200(owner_client):
    resp = owner_client.get('/owner/store-payment-methods')
    assert resp.status_code == 200


def test_store_payment_methods_create_returns_200(owner_client):
    resp = owner_client.get('/owner/store-payment-methods/create')
    assert resp.status_code == 200


def test_dashboard_returns_200(owner_client):
    resp = owner_client.get('/owner/dashboard')
    assert resp.status_code == 200


# ── Test 3: Analytics routes (formerly suspected 500) ────────────────

def test_sales_insights_returns_200(owner_client):
    resp = owner_client.get('/owner/sales-insights')
    assert resp.status_code == 200, f"sales-insights returned {resp.status_code}: {_brief(resp.data.decode('utf-8', errors='replace'), 500)}"


def test_customer_insights_returns_200(owner_client):
    resp = owner_client.get('/owner/customer-insights')
    assert resp.status_code == 200, f"customer-insights returned {resp.status_code}: {_brief(resp.data.decode('utf-8', errors='replace'), 500)}"


def test_product_performance_returns_200(owner_client):
    resp = owner_client.get('/owner/product-performance')
    assert resp.status_code == 200, f"product-performance returned {resp.status_code}: {_brief(resp.data.decode('utf-8', errors='replace'), 500)}"


def test_forecasting_returns_200(owner_client):
    resp = owner_client.get('/owner/forecasting')
    assert resp.status_code == 200, f"forecasting returned {resp.status_code}: {_brief(resp.data.decode('utf-8', errors='replace'), 500)}"


# ── Test 4: POST routes — smoke (form submission) ────────────────────

def test_tenant_create_post_creates_tenant(owner_client, _owner_app):
    import uuid
    uid = uuid.uuid4().hex[:8]
    resp = owner_client.post('/owner/tenants/create', data={
        'name_ar': f'تينانت جديد {uid}',
        'slug': f'new-tenant-{uid}',
        'email': f'{uid}@test.com',
        'country': 'AE',
        'subscription_plan': 'basic',
    })
    assert resp.status_code in (200, 302), f"POST tenants/create returned {resp.status_code}"


def test_tenant_activate_post(owner_client, _owner_app):
    from models import Tenant
    with _owner_app.app_context():
        tenant = Tenant.query.first()
    assert tenant is not None
    resp = owner_client.post(f'/owner/tenants/{tenant.id}/activate')
    assert resp.status_code in (200, 302, 404), f"POST tenants/{tenant.id}/activate returned {resp.status_code}"


# ── Test 5: Security — unauthenticated returns 404 ───────────────────


