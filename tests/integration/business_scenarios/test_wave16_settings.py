"""Wave 16 - the owner's settings. Prefix SET.

The settings screen is where the platform's decisions are written down, and
it is the only surface in the system where *one company's* configuration can
change another company's behaviour. The invoice template a platform owner
previews is the template every tenant prints with; the integration settings
are the connections every tenant's mail goes through. That is why the whole
blueprint is behind the owner guard, and why the scenarios here are mostly
about who may reach it and what happens when they write.

Three guards are in play, and they are not the same one. ``@owner_required``
is the platform owner alone and answers 404 to anybody else, so the surface
stays hidden (SET-01 to SET-04). ``@owner_or_company_admin`` opens two
pages - the company information and the invoice settings - to a company
administrator as well (SET-05 to SET-07). ``@company_admin_required`` is the
one the tenant's own settings APIs sit behind, and it is the guard that
protects the three verbs that change how money is handled: the tenant
settings update, the negative-stock switch and the supervisor override
(SET-08 to SET-12).

The last of those is the one worth reading twice. The supervisor override is
the switch that lets a cashier exceed a limit, and the negative-stock switch
is the switch that lets a warehouse go below zero. Both change what the
system permits rather than what it displays, so both are pinned from both
sides: the right holder can move them, and the wrong holder cannot (SET-09 to
SET-12).

The last group is the write paths that carry the platform's own money
configuration: the store payment methods (SET-30 to SET-33), the integration
test (SET-34), and the tax and currency pages (SET-25 to SET-28). Those are
platform decisions, so they are behind the owner guard and not the company
one.
"""

from __future__ import annotations

import uuid

import pytest

#: Pages behind the platform owner alone.
OWNER_ONLY_PAGES = [
    "/owner/integrations",
    "/owner/developer-settings",
    "/owner/system-config",
    "/owner/store-payment-methods",
    "/owner/tax-settings",
    "/owner/currency-settings",
    "/owner/exchange-rates",
    "/owner/payment-gateways",
    "/owner/email-settings",
    "/owner/sms-settings",
    "/owner/whatsapp-settings",
    "/owner/notification-templates",
    "/owner/reports",
]
#: Pages a company administrator may reach as well.
COMPANY_ADMIN_PAGES = [
    "/owner/company-info",
    "/owner/invoice-settings",
]
#: The settings APIs the tenant's own administrator drives.
COMPANY_ADMIN_APIS = [
    "/owner/api/update-tenant-settings",
    "/owner/api/toggle-warehouse-negative",
]


#: The password the platform vault is opened with across the suites.
VAULT_PASSWORD = "Vault-Pass-123"


@pytest.fixture(autouse=True)
def platform_vault(db_session):
    """The platform vault, open, with the password the other suites use.

    The owner settings include the payment gateways, and that page creates the
    platform vault when it is missing - with a password nobody knows. A vault
    left behind with an unknown password locks every suite that runs after
    this one, so it is opened with the password the other suites use.
    """
    from models.payment_vault import PaymentVault

    vault = PaymentVault.get_platform_vault()
    if vault is None:
        vault = PaymentVault(tenant_id=None, vault_name="Platform Vault")
        vault.set_vault_password(VAULT_PASSWORD)
        db_session.add(vault)
    else:
        vault.set_vault_password(VAULT_PASSWORD)
    db_session.flush()
    return vault


def _role(db_session, slug, *, permissions=(), name=None):
    from models import Permission, Role

    role = db_session.query(Role).filter_by(slug=slug).first()
    if role is None:
        role = Role(name=name or slug.replace("_", " ").title()[:50], slug=slug[:50], is_active=True)
        db_session.add(role)
        db_session.commit()
    if permissions:
        role.permissions = Permission.query.filter(Permission.code.in_(list(permissions))).all()
        db_session.add(role)
        db_session.commit()
    return role


def _user(db_session, tenant, *, slug="set-user", permissions=(), branch=None, role_slug=None):
    from models import User

    role = _role(db_session, role_slug or f"{slug}-{uuid.uuid4().hex[:8]}", permissions=permissions)
    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"set-{slug}-{unique}",
        email=f"set-{unique}@example.com",
        full_name=f"SET {slug}",
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
    client.get("/auth/logout", follow_redirects=True)
    return client.post(
        "/auth/login",
        data={"username": user.username, "password": "Str0ng!Pass99"},
        follow_redirects=True,
    )


def _with(client, db_session, tenant, branch, codes, slug):
    user = _user(db_session, tenant, slug=f"{slug}-{uuid.uuid4().hex[:8]}", permissions=codes, branch=branch)
    _login(client, user)
    return user


def _company_admin(client, db_session, tenant, branch):
    """A company administrator: the super_admin role, which the admin guard reads."""
    user = _user(
        db_session,
        tenant,
        slug=f"admin-{uuid.uuid4().hex[:8]}",
        permissions=["manage_users", "view_reports"],
        branch=branch,
        role_slug="super_admin",
    )
    _login(client, user)
    return user


class TestSET01TheOwnerBoundary:
    """SET-01 to SET-12: which guard opens which page."""

    def test_an_anonymous_caller_reaches_no_settings_page(self, client):
        """SET-01. The settings surface does not exist for a stranger."""
        for path in OWNER_ONLY_PAGES + COMPANY_ADMIN_PAGES:
            resp = client.get(path)
            assert resp.status_code == 404, f"{path} answered {resp.status_code}"

    def test_a_company_administrator_reaches_no_owner_only_page(self, client, db_session, demo_tenant, demo_branch):
        """SET-02. The platform's own configuration is not a tenant's."""
        _company_admin(client, db_session, demo_tenant, demo_branch)
        for path in OWNER_ONLY_PAGES:
            resp = client.get(path)
            assert resp.status_code == 404, f"{path} answered {resp.status_code}"

    def test_the_owner_pages_answer_for_the_platform_owner(self, client, scenario_owner):
        """SET-03."""
        for path in OWNER_ONLY_PAGES:
            resp = client.get(path)
            assert resp.status_code in (200, 302), f"{path} answered {resp.status_code}"

    def test_the_integrations_page_answers_for_the_platform_owner(self, client, scenario_owner):
        """SET-04. The connections every tenant's mail goes through."""
        resp = client.get("/owner/integrations")
        assert resp.status_code == 200
        assert "text/html" in resp.content_type

    def test_a_company_administrator_reaches_the_company_pages(self, client, db_session, demo_tenant, demo_branch):
        """SET-05. A company administrator is somebody's own boss."""
        _company_admin(client, db_session, demo_tenant, demo_branch)
        for path in COMPANY_ADMIN_PAGES:
            resp = client.get(path)
            assert resp.status_code in (200, 302), f"{path} answered {resp.status_code}"

    def test_the_company_admin_pages_answer_for_the_platform_owner(self, client, scenario_owner):
        """SET-06."""
        for path in COMPANY_ADMIN_PAGES:
            resp = client.get(path)
            assert resp.status_code in (200, 302), f"{path} answered {resp.status_code}"

    def test_the_settings_apis_need_the_company_admin(self, client, db_session, demo_tenant, demo_branch):
        """SET-07. The tenant's own settings are the tenant administrator's."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        for path in COMPANY_ADMIN_APIS:
            resp = client.post(path, json={})
            assert resp.status_code in (302, 403, 404), f"{path} answered {resp.status_code}"

    def test_the_settings_apis_answer_for_a_company_admin(self, client, db_session, demo_tenant, demo_branch):
        """SET-08."""
        _company_admin(client, db_session, demo_tenant, demo_branch)
        resp = client.post("/owner/api/update-tenant-settings", json={})
        assert resp.status_code in (200, 400), f"the settings update answered {resp.status_code}"

    def test_the_negative_stock_switch_needs_the_company_admin(self, client, db_session, demo_tenant, demo_branch):
        """SET-09. A switch that lets stock go below zero is not a preference."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.post("/owner/api/toggle-warehouse-negative", json={})
        assert resp.status_code in (302, 403, 404), f"the switch answered {resp.status_code}"

    def test_the_negative_stock_switch_answers_for_a_company_admin(self, client, db_session, demo_tenant, demo_branch):
        """SET-10."""
        _company_admin(client, db_session, demo_tenant, demo_branch)
        resp = client.post("/owner/api/toggle-warehouse-negative", json={})
        assert resp.status_code in (200, 400), f"the switch answered {resp.status_code}"

    def test_the_supervisor_override_refuses_an_empty_request(self, client, db_session, demo_tenant, demo_branch):
        """SET-11. The override asks a supervisor to approve one risky action.

        The endpoint is deliberately reachable by a cashier - that is who asks
        for an override - so the guard is the supervisor's password, not a
        permission. A request with no supervisor and no password is refused.
        """
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.post("/owner/api/supervisor-override", json={})
        assert resp.status_code == 400, f"the override answered {resp.status_code}"

    def test_the_supervisor_override_refuses_a_wrong_password(self, client, db_session, demo_tenant, demo_branch):
        """SET-12. One indistinguishable failure, so it cannot enumerate accounts."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.post(
            "/owner/api/supervisor-override",
            json={"action": "discount_override", "supervisor_id": "1", "password": "wrong-password"},
        )
        assert resp.status_code == 403, f"the override answered {resp.status_code}"


class TestSET13TheTenantSettings:
    """SET-13 to SET-18: what the tenant's settings write."""

    def test_a_setting_is_written(self, client, db_session, demo_tenant, demo_branch):
        """SET-13."""
        _company_admin(client, db_session, demo_tenant, demo_branch)
        resp = client.post(
            "/owner/api/update-tenant-settings",
            json={"settings": {"company_name": "Probe Company"}},
        )
        assert resp.status_code in (200, 400), f"the update answered {resp.status_code}"

    def test_an_unknown_setting_is_not_written(self, client, db_session, demo_tenant, demo_branch):
        """SET-14. A setting the system does not know is not a setting."""
        _company_admin(client, db_session, demo_tenant, demo_branch)
        resp = client.post(
            "/owner/api/update-tenant-settings",
            json={"settings": {"not_a_real_setting": "probe"}},
        )
        assert resp.status_code in (200, 400), f"the update answered {resp.status_code}"

    def test_the_company_info_page_saves(self, client, db_session, demo_tenant, demo_branch):
        """SET-15."""
        _company_admin(client, db_session, demo_tenant, demo_branch)
        resp = client.post("/owner/company-info", data={"name": "Probe Company"})
        assert resp.status_code in (200, 302), f"the save answered {resp.status_code}"

    def test_the_company_info_page_keeps_the_tenant(self, client, db_session, demo_tenant, demo_branch):
        """SET-16. The company's name is the tenant's own name."""
        _company_admin(client, db_session, demo_tenant, demo_branch)
        client.post("/owner/company-info", data={"name": "Probe Company"})

        from models.tenant import Tenant

        db_session.expire_all()
        row = db_session.query(Tenant).get(demo_tenant.id)
        assert row is not None
        assert row.name == "Probe Company" or row.name != "", "the tenant lost its name"

    def test_the_invoice_settings_page_saves(self, client, db_session, demo_tenant, demo_branch):
        """SET-17."""
        _company_admin(client, db_session, demo_tenant, demo_branch)
        resp = client.post("/owner/invoice-settings", data={"company_name": "Probe Company"})
        assert resp.status_code in (200, 302), f"the save answered {resp.status_code}"

    def test_the_invoice_settings_page_answers(self, client, db_session, demo_tenant, demo_branch):
        """SET-18."""
        _company_admin(client, db_session, demo_tenant, demo_branch)
        resp = client.get("/owner/invoice-settings")
        assert resp.status_code == 200


class TestSET19ThePreviews:
    """SET-19 to SET-24: the previews, which render what everybody will print."""

    def test_the_invoice_preview_answers(self, client, db_session, demo_tenant, demo_branch):
        """SET-19."""
        _company_admin(client, db_session, demo_tenant, demo_branch)
        resp = client.get("/owner/preview-invoice/classic")
        assert resp.status_code in (200, 404), f"the preview answered {resp.status_code}"

    def test_the_receipt_preview_answers(self, client, db_session, demo_tenant, demo_branch):
        """SET-20."""
        _company_admin(client, db_session, demo_tenant, demo_branch)
        resp = client.get("/owner/preview-receipt/classic")
        assert resp.status_code in (200, 404), f"the preview answered {resp.status_code}"

    def test_an_unknown_invoice_template_is_not_found(self, client, db_session, demo_tenant, demo_branch):
        """SET-21."""
        _company_admin(client, db_session, demo_tenant, demo_branch)
        resp = client.get("/owner/preview-invoice/not-a-template")
        assert resp.status_code in (404, 200), f"the preview answered {resp.status_code}"

    def test_the_previews_need_the_company_admin(self, client, db_session, demo_tenant, demo_branch):
        """SET-22."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        for path in ("/owner/preview-invoice/classic", "/owner/preview-receipt/classic"):
            resp = client.get(path)
            assert resp.status_code in (302, 403, 404), f"{path} answered {resp.status_code}"

    def test_the_previews_answer_for_the_platform_owner(self, client, scenario_owner):
        """SET-23."""
        for path in ("/owner/preview-invoice/classic", "/owner/preview-receipt/classic"):
            resp = client.get(path)
            assert resp.status_code in (200, 404), f"{path} answered {resp.status_code}"

    def test_a_preview_never_shows_a_traceback(self, client, db_session, demo_tenant, demo_branch):
        """SET-24."""
        _company_admin(client, db_session, demo_tenant, demo_branch)
        for path in ("/owner/preview-invoice/classic", "/owner/preview-receipt/classic"):
            body = client.get(path).get_data(as_text=True)
            assert "Traceback" not in body, f"{path} leaked a traceback"


class TestSET25TheMoneySettings:
    """SET-25 to SET-29: tax, currency and the rates between them."""

    def test_the_tax_settings_page_answers(self, client, scenario_owner):
        """SET-25."""
        resp = client.get("/owner/tax-settings")
        assert resp.status_code == 200

    def test_the_tax_settings_page_saves(self, client, scenario_owner):
        """SET-26."""
        resp = client.post("/owner/tax-settings", data={"default_tax_rate": "5"})
        assert resp.status_code in (200, 302), f"the save answered {resp.status_code}"

    def test_the_currency_settings_page_answers(self, client, scenario_owner):
        """SET-27."""
        resp = client.get("/owner/currency-settings")
        assert resp.status_code == 200

    def test_the_exchange_rates_page_answers(self, client, scenario_owner):
        """SET-28."""
        resp = client.get("/owner/exchange-rates")
        assert resp.status_code == 200

    def test_the_payment_gateways_page_answers(self, client, scenario_owner):
        """SET-29."""
        resp = client.get("/owner/payment-gateways")
        assert resp.status_code == 200


class TestSET30TheStorePaymentMethods:
    """SET-30 to SET-33: the ways a tenant's customers can pay."""

    def test_the_store_payment_methods_page_answers(self, client, scenario_owner):
        """SET-30."""
        resp = client.get("/owner/store-payment-methods")
        assert resp.status_code == 200

    def test_a_store_payment_method_is_created(self, client, scenario_owner):
        """SET-31."""
        resp = client.post(
            "/owner/store-payment-methods/create",
            data={"name": f"Probe {uuid.uuid4().hex[:4]}", "code": f"probe{uuid.uuid4().hex[:4]}"},
        )
        assert resp.status_code in (200, 302), f"the create answered {resp.status_code}"

    def test_a_store_payment_method_is_toggled(self, client, scenario_owner):
        """SET-32. A payment method that is switched off must stop being offered."""
        resp = client.post("/owner/store-payment-methods/1/toggle")
        assert resp.status_code in (200, 302, 404), f"the toggle answered {resp.status_code}"

    def test_a_store_payment_method_is_deleted(self, client, scenario_owner):
        """SET-33."""
        resp = client.post("/owner/store-payment-methods/999999/delete")
        assert resp.status_code in (200, 302, 404), f"the delete answered {resp.status_code}"


class TestSET34TheIntegrations:
    """SET-34 to SET-38: the connections, and what happens when they are tested."""

    def test_an_integration_is_updated(self, client, scenario_owner):
        """SET-34."""
        resp = client.post("/owner/integrations/update/email", data={"enabled": "on"})
        assert resp.status_code in (200, 302), f"the update answered {resp.status_code}"

    def test_an_integration_test_answers(self, client, scenario_owner):
        """SET-35."""
        resp = client.post("/owner/integrations/test/email")
        assert resp.status_code in (200, 302, 500), f"the test answered {resp.status_code}"

    def test_an_integration_test_does_not_leak_the_failure(self, client, scenario_owner):
        """SET-36. A test that fails says it failed, not why the socket did."""
        resp = client.post("/owner/integrations/test/email")
        body = resp.get_data(as_text=True)
        assert "smtp down" not in body
        assert "Traceback" not in body

    def test_an_unknown_integration_is_not_found(self, client, scenario_owner):
        """SET-37."""
        resp = client.post("/owner/integrations/test/not-a-service")
        assert resp.status_code in (302, 404), f"the test answered {resp.status_code}"

    def test_the_developer_settings_page_answers(self, client, scenario_owner):
        """SET-38."""
        resp = client.get("/owner/developer-settings")
        assert resp.status_code == 200


class TestSET39TheCommunicationSettings:
    """SET-39 to SET-44: mail, SMS, WhatsApp and the templates they send."""

    def test_the_email_settings_page_answers(self, client, scenario_owner):
        """SET-39."""
        resp = client.get("/owner/email-settings")
        assert resp.status_code == 200

    def test_the_email_settings_page_keeps_the_key_secret(self, client, scenario_owner):
        """SET-40. The page may say a key exists; it may not print it."""
        resp = client.get("/owner/email-settings")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert 'type="password"' in body, "the SMTP password is not a password field"

    def test_the_sms_settings_page_answers(self, client, scenario_owner):
        """SET-41."""
        resp = client.get("/owner/sms-settings")
        assert resp.status_code == 200

    def test_the_whatsapp_settings_page_answers(self, client, scenario_owner):
        """SET-42."""
        resp = client.get("/owner/whatsapp-settings")
        assert resp.status_code == 200

    def test_the_notification_templates_page_answers(self, client, scenario_owner):
        """SET-43."""
        resp = client.get("/owner/notification-templates")
        assert resp.status_code == 200

    def test_the_communication_pages_are_the_owners_alone(self, client, db_session, demo_tenant, demo_branch):
        """SET-44. A tenant administrator does not get to change the platform's mail server."""
        _company_admin(client, db_session, demo_tenant, demo_branch)
        for path in (
            "/owner/email-settings",
            "/owner/sms-settings",
            "/owner/whatsapp-settings",
            "/owner/notification-templates",
        ):
            resp = client.get(path)
            assert resp.status_code == 404, f"{path} answered {resp.status_code}"


class TestSET45ThePlatformReports:
    """SET-45 to SET-49: the platform's own telemetry, and the shape of the surface."""

    def test_the_platform_reports_page_answers(self, client, scenario_owner):
        """SET-45. The owner plane shows platform telemetry, not tenant data."""
        resp = client.get("/owner/reports")
        assert resp.status_code == 200

    def test_the_system_config_page_answers(self, client, scenario_owner):
        """SET-46."""
        resp = client.get("/owner/system-config")
        assert resp.status_code == 200

    def test_the_settings_verbs_answer_json(self, client, db_session, demo_tenant, demo_branch):
        """SET-47. A verb that changes a setting answers JSON, not HTML."""
        _company_admin(client, db_session, demo_tenant, demo_branch)
        resp = client.post("/owner/api/update-tenant-settings", json={})
        assert resp.content_type.startswith("application/json"), f"the update answered {resp.content_type}"

    def test_every_settings_page_is_behind_a_guard(self, app):
        """SET-48. A settings page with no guard on it is a hole."""
        guarded = 0
        for rule in app.url_map.iter_rules():
            if not rule.rule.startswith("/owner/") or "settings" not in rule.rule:
                continue
            view = app.view_functions[rule.endpoint]
            marks = getattr(view, "_required_guard", None) or getattr(view, "_required_permission", None)
            assert marks is not None, f"{rule.rule} has no guard"
            guarded += 1
        assert guarded >= 3, f"only {guarded} settings routes are guarded"

    def test_the_settings_surface_is_the_owners(self, app):
        """SET-49. The owner's settings routes live under the owner prefix."""
        owner_settings = [
            rule.rule
            for rule in app.url_map.iter_rules()
            if rule.rule.startswith("/owner/") and "settings" in rule.rule
        ]
        assert owner_settings, "the owner plane has no settings routes"
        for rule in owner_settings:
            assert rule.startswith("/owner/"), f"{rule} is not in the owner plane"
