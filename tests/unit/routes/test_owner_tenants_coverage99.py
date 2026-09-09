"""Coverage-99 boost for routes/owner/tenants.py (13 endpoints)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def to_client(app_factory, bypass_owner_auth):
    from routes.owner import owner_bp

    app = app_factory(owner_bp)
    return app.test_client()


def _tenant(tid=2):
    t = MagicMock()
    t.id = tid
    t.name = "Acme"
    t.name_ar = "أكمي"
    t.name_en = "Acme"
    t.slug = "acme"
    t.is_active = True
    t.is_suspended = False
    t.tenant_id = tid
    t.max_users = 5
    t.max_products = 1000
    t.max_customers = 500
    t.max_suppliers = 200
    t.max_branches = 3
    t.max_warehouses = 2
    t.max_storage_mb = 1024
    t.max_invoices_per_month = 1000
    t.max_sales_per_month = 5000
    t.data_retention_days = 365
    t.default_currency = "AED"
    t.business_type = "general"
    t.phone_1 = ""
    t.phone_2 = ""
    t.email = ""
    t.address_ar = ""
    t.enable_pos_promotions = None
    t.enable_pos_multi_tender = None
    t.enable_pos_returns = None
    t.enable_pos_shifts = None
    t.enable_ai = False
    t.ai_external_sharing_enabled = False
    t.subscription_end = None
    t.subscription_plan = None
    t.subscription_plan_duration = None
    t.is_trial = False
    return t


class TestStoresAndAi:
    def test_tenant_stores(self, to_client):
        store = MagicMock(is_enabled=True, platform_disabled=False)
        tenant = _tenant()
        with (
            patch(
                "services.owner_ops_service.OwnerOpsService.tenant_stores_with_tenants",
                return_value=[(store, tenant)],
            ),
            patch(
                "services.store_service.StoreService.is_store_publicly_available",
                return_value=True,
            ),
            patch(
                "services.store_service.StoreService.stores_globally_enabled",
                return_value=True,
            ),
            patch("routes.owner.tenants.render_template", return_value="ok"),
        ):
            assert to_client.get("/owner/tenant-stores").status_code == 200

    def test_tenant_ai(self, to_client):
        t = _tenant()
        with (
            patch(
                "services.owner_ops_service.OwnerOpsService.active_ai_tenants",
                return_value=[t],
            ),
            patch("routes.owner.tenants.get_tenant_ai_level", return_value="execute"),
            patch("routes.owner.tenants.render_template", return_value="ok"),
        ):
            assert to_client.get("/owner/tenant-ai").status_code == 200

    def test_ai_toggle_missing(self, to_client):
        with patch("services.owner_ops_service.OwnerOpsService.get_tenant", return_value=None):
            assert to_client.post("/owner/tenant-ai/9/toggle").status_code in (200, 302)

    def test_ai_toggle_enable_invalid_level(self, to_client):
        t = _tenant()
        with (
            patch("services.owner_ops_service.OwnerOpsService.get_tenant", return_value=t),
            patch("routes.owner.tenants.get_tenant_ai_level", return_value="execute"),
            patch("routes.owner.tenants.set_tenant_ai_level", return_value="execute"),
            patch("routes.owner.tenants.db.session"),
            patch("routes.owner.tenants.LoggingCore"),
        ):
            resp = to_client.post(
                "/owner/tenant-ai/2/toggle",
                data={
                    "enable_ai": "1",
                    "ai_access_level": "ultra",
                    "ai_external_sharing_enabled": ["0", "1"],
                },
            )
        assert resp.status_code in (200, 302)

    def test_ai_toggle_disable_error(self, to_client):
        t = _tenant()
        with (
            patch("services.owner_ops_service.OwnerOpsService.get_tenant", return_value=t),
            patch("routes.owner.tenants.get_tenant_ai_level", return_value="execute"),
            patch("routes.owner.tenants.set_tenant_ai_level", side_effect=RuntimeError("x")),
            patch("routes.owner.tenants.db.session"),
        ):
            resp = to_client.post("/owner/tenant-ai/2/toggle", data={})
        assert resp.status_code in (200, 302)

    def test_store_toggle_missing(self, to_client):
        with patch("services.owner_ops_service.OwnerOpsService.get_tenant_store", return_value=None):
            assert to_client.post("/owner/tenant-stores/9/platform-toggle").status_code in (
                200,
                302,
            )

    def test_store_toggle_lock_unlock(self, to_client):
        store = MagicMock(id=3)
        with (
            patch(
                "services.owner_ops_service.OwnerOpsService.get_tenant_store",
                return_value=store,
            ),
            patch(
                "services.store_service.StoreService.set_platform_disabled",
                return_value=None,
            ),
            patch("routes.owner.tenants.LoggingCore"),
        ):
            assert to_client.post(
                "/owner/tenant-stores/3/platform-toggle", data={"platform_disabled": "1"}
            ).status_code in (200, 302)
            assert to_client.post("/owner/tenant-stores/3/platform-toggle", data={}).status_code in (200, 302)

    def test_store_toggle_error(self, to_client):
        store = MagicMock(id=3)
        with (
            patch(
                "services.owner_ops_service.OwnerOpsService.get_tenant_store",
                return_value=store,
            ),
            patch(
                "services.store_service.StoreService.set_platform_disabled",
                side_effect=RuntimeError("x"),
            ),
        ):
            assert to_client.post(
                "/owner/tenant-stores/3/platform-toggle", data={"platform_disabled": "1"}
            ).status_code in (200, 302)


class TestListAndCreate:
    def test_tenants_list(self, to_client):
        with (
            patch(
                "services.tenant_service.TenantService.get_tenants_list_context",
                return_value={
                    "tenants": [],
                    "user_counts": {},
                    "branch_counts": {},
                    "store_counts": {},
                },
            ),
            patch("routes.owner.tenants.render_template", return_value="ok"),
        ):
            assert to_client.get("/owner/tenants").status_code == 200

    def test_create_get(self, to_client):
        with (
            patch(
                "services.owner_ops_service.OwnerOpsService.active_packages_sorted",
                return_value=[],
            ),
            patch("routes.owner.tenants.render_template", return_value="form"),
        ):
            assert to_client.get("/owner/tenants/create").status_code == 200

    def _post_create(self, client, data):
        with (
            patch(
                "services.owner_ops_service.OwnerOpsService.active_packages_sorted",
                return_value=[],
            ),
            patch(
                "services.owner_ops_service.OwnerOpsService.find_tenant_by_slug",
                return_value=None,
            ),
            patch("routes.owner.tenants.Tenant") as tcls,
            patch("routes.owner.tenants.db.session"),
            patch("models.ensure_default_pos_order_types", return_value=None),
            patch("services.gl_service.GLService.ensure_core_accounts", return_value=None),
            patch("services.gl_service.GLService.ensure_gl_mappings", return_value=None),
        ):
            tcls.return_value = MagicMock(id=11)
            return client.post("/owner/tenants/create", data=data)

    def test_create_missing_fields(self, to_client):
        assert self._post_create(to_client, {}).status_code in (200, 302, 303)

    def test_create_missing_currency(self, to_client):
        resp = self._post_create(to_client, {"name_ar": "شركة", "slug": "co1", "default_currency": ""})
        assert resp.status_code in (200, 302, 303)

    def test_create_duplicate_slug(self, to_client):
        with (
            patch(
                "services.owner_ops_service.OwnerOpsService.active_packages_sorted",
                return_value=[],
            ),
            patch(
                "services.owner_ops_service.OwnerOpsService.find_tenant_by_slug",
                return_value=MagicMock(),
            ),
        ):
            resp = to_client.post(
                "/owner/tenants/create",
                data={"name_ar": "شركة", "slug": "dup", "default_currency": "AED"},
            )
        assert resp.status_code in (200, 302, 303)

    def test_create_success_plain(self, to_client):
        resp = self._post_create(
            to_client,
            {"name_ar": "شركة", "slug": "co2", "default_currency": "aed", "max_users": "bad"},
        )
        assert resp.status_code in (200, 302, 303)

    def test_create_with_package_and_end(self, to_client):
        from services.saas_provisioning_service import SaaSProvisioningService

        with (
            patch(
                "services.owner_ops_service.OwnerOpsService.active_packages_sorted",
                return_value=[],
            ),
            patch(
                "services.owner_ops_service.OwnerOpsService.find_tenant_by_slug",
                return_value=None,
            ),
            patch("routes.owner.tenants.Tenant") as tcls,
            patch("routes.owner.tenants.db.session"),
            patch("models.ensure_default_pos_order_types", return_value=None),
            patch("services.gl_service.GLService.ensure_core_accounts", return_value=None),
            patch("services.gl_service.GLService.ensure_gl_mappings", return_value=None),
            patch.object(SaaSProvisioningService, "activate_purchased_package", return_value=None),
        ):
            tcls.return_value = MagicMock(id=12)
            resp = to_client.post(
                "/owner/tenants/create",
                data={
                    "name_ar": "شركة",
                    "slug": "co3",
                    "default_currency": "AED",
                    "package_id": "7",
                    "subscription_plan_duration": "weird",
                    "subscription_end": "2030-01-01",
                    "enable_pos_promotions": "1",
                    "enable_pos_multi_tender": "0",
                },
            )
        assert resp.status_code in (200, 302, 303)

    def test_create_with_package_valid_duration_no_end(self, to_client):
        from services.saas_provisioning_service import SaaSProvisioningService

        with (
            patch(
                "services.owner_ops_service.OwnerOpsService.active_packages_sorted",
                return_value=[],
            ),
            patch(
                "services.owner_ops_service.OwnerOpsService.find_tenant_by_slug",
                return_value=None,
            ),
            patch("routes.owner.tenants.Tenant") as tcls,
            patch("routes.owner.tenants.db.session"),
            patch("models.ensure_default_pos_order_types", return_value=None),
            patch("services.gl_service.GLService.ensure_core_accounts", return_value=None),
            patch("services.gl_service.GLService.ensure_gl_mappings", return_value=None),
            patch.object(SaaSProvisioningService, "activate_purchased_package", return_value=None),
        ):
            tcls.return_value = MagicMock(id=13)
            resp = to_client.post(
                "/owner/tenants/create",
                data={
                    "name_ar": "شركة",
                    "slug": "co4",
                    "default_currency": "AED",
                    "package_id": "7",
                    "subscription_plan_duration": "annual",
                },
            )
        assert resp.status_code in (200, 302, 303)

    def test_create_exception(self, to_client):
        with (
            patch(
                "services.owner_ops_service.OwnerOpsService.active_packages_sorted",
                return_value=[],
            ),
            patch(
                "services.owner_ops_service.OwnerOpsService.find_tenant_by_slug",
                side_effect=RuntimeError("x"),
            ),
            patch("routes.owner.tenants.render_template", return_value="form"),
        ):
            assert (
                to_client.post(
                    "/owner/tenants/create",
                    data={"name_ar": "شركة", "slug": "co9", "default_currency": "AED"},
                ).status_code
                == 200
            )


class TestSuspendActivateDelete:
    def test_suspend_main_protected(self, to_client):
        with patch(
            "services.owner_ops_service.OwnerOpsService.get_tenant_or_404",
            return_value=_tenant(1),
        ):
            assert to_client.post("/owner/tenants/1/suspend").status_code in (200, 302)

    def test_suspend_ok_and_error(self, to_client):
        with (
            patch(
                "services.owner_ops_service.OwnerOpsService.get_tenant_or_404",
                return_value=_tenant(2),
            ),
            patch("routes.owner.tenants.db.session"),
        ):
            assert to_client.post("/owner/tenants/2/suspend", data={"reason": "r"}).status_code in (
                200,
                302,
            )
        with (
            patch(
                "services.owner_ops_service.OwnerOpsService.get_tenant_or_404",
                return_value=_tenant(2),
            ),
            patch("routes.owner.tenants.db.session.commit", side_effect=RuntimeError("x")),
        ):
            assert to_client.post("/owner/tenants/2/suspend").status_code in (200, 302)

    def test_activate_ok_and_error(self, to_client):
        with (
            patch(
                "services.owner_ops_service.OwnerOpsService.get_tenant_or_404",
                return_value=_tenant(2),
            ),
            patch("routes.owner.tenants.db.session"),
        ):
            assert to_client.post("/owner/tenants/2/activate").status_code in (200, 302)
        with (
            patch(
                "services.owner_ops_service.OwnerOpsService.get_tenant_or_404",
                return_value=_tenant(2),
            ),
            patch("routes.owner.tenants.db.session.commit", side_effect=RuntimeError("x")),
        ):
            assert to_client.post("/owner/tenants/2/activate").status_code in (200, 302)

    def test_delete_protected_users_error(self, to_client):
        with patch(
            "services.owner_ops_service.OwnerOpsService.get_tenant_or_404",
            return_value=_tenant(1),
        ):
            assert to_client.post("/owner/tenants/1/delete").status_code in (200, 302)
        with (
            patch(
                "services.owner_ops_service.OwnerOpsService.get_tenant_or_404",
                return_value=_tenant(2),
            ),
            patch(
                "services.owner_ops_service.OwnerOpsService.count_tenant_active_users",
                return_value=3,
            ),
        ):
            assert to_client.post("/owner/tenants/2/delete").status_code in (200, 302)
        with (
            patch(
                "services.owner_ops_service.OwnerOpsService.get_tenant_or_404",
                return_value=_tenant(2),
            ),
            patch(
                "services.owner_ops_service.OwnerOpsService.count_tenant_active_users",
                return_value=0,
            ),
            patch("routes.owner.tenants.db.session.commit", side_effect=RuntimeError("x")),
        ):
            assert to_client.post("/owner/tenants/2/delete").status_code in (200, 302)

    def test_delete_ok(self, to_client):
        with (
            patch(
                "services.owner_ops_service.OwnerOpsService.get_tenant_or_404",
                return_value=_tenant(2),
            ),
            patch(
                "services.owner_ops_service.OwnerOpsService.count_tenant_active_users",
                return_value=0,
            ),
            patch("routes.owner.tenants.db.session"),
        ):
            assert to_client.post("/owner/tenants/2/delete").status_code in (200, 302)


class TestEdit:
    def test_edit_get(self, to_client):
        with (
            patch(
                "services.owner_ops_service.OwnerOpsService.get_tenant_or_404",
                return_value=_tenant(2),
            ),
            patch("routes.owner.tenants.render_template", return_value="form"),
        ):
            assert to_client.get("/owner/tenants/2/edit").status_code == 200

    def test_edit_post_tristate_variants(self, to_client):
        with (
            patch(
                "services.owner_ops_service.OwnerOpsService.get_tenant_or_404",
                return_value=_tenant(2),
            ),
            patch("routes.owner.tenants.db.session"),
            patch("routes.owner.tenants.render_template", return_value="form"),
        ):
            resp = to_client.post(
                "/owner/tenants/2/edit",
                data={
                    "name_ar": "محدث",
                    "max_users": "bad",
                    "enable_pos_promotions": "1",
                    "enable_pos_multi_tender": "0",
                },
            )
        assert resp.status_code in (200, 302, 303)

    def test_edit_post_error(self, to_client):
        with (
            patch(
                "services.owner_ops_service.OwnerOpsService.get_tenant_or_404",
                return_value=_tenant(2),
            ),
            patch("routes.owner.tenants.db.session.commit", side_effect=RuntimeError("x")),
            patch("routes.owner.tenants.render_template", return_value="form"),
        ):
            assert to_client.post("/owner/tenants/2/edit", data={"name_ar": "x"}).status_code in (
                200,
                302,
            )


class TestToggleApi:
    def test_not_json(self, to_client):
        assert (
            to_client.post("/owner/api/tenant/2/toggle-status", data="x", content_type="text/plain").status_code == 400
        )

    def test_missing_and_main(self, to_client):
        with patch("services.owner_ops_service.OwnerOpsService.get_tenant", return_value=None):
            assert to_client.post("/owner/api/tenant/9/toggle-status", json={}).status_code == 404
        # Owner has full control: tenant id=1 is toggleable like any other.
        with (
            patch("services.owner_ops_service.OwnerOpsService.get_tenant", return_value=_tenant(1)),
            patch("routes.owner.tenants.db.session"),
        ):
            assert to_client.post("/owner/api/tenant/1/toggle-status", json={}).status_code == 200

    def test_toggle_off_on_and_error(self, to_client):
        with (
            patch(
                "services.owner_ops_service.OwnerOpsService.get_tenant",
                return_value=_tenant(2),
            ),
            patch("routes.owner.tenants.db.session"),
        ):
            assert to_client.post("/owner/api/tenant/2/toggle-status", json={}).status_code == 200
        t = _tenant(2)
        t.is_active = False
        with (
            patch("services.owner_ops_service.OwnerOpsService.get_tenant", return_value=t),
            patch("routes.owner.tenants.db.session"),
        ):
            assert to_client.post("/owner/api/tenant/2/toggle-status", json={}).status_code == 200
        with (
            patch(
                "services.owner_ops_service.OwnerOpsService.get_tenant",
                return_value=_tenant(2),
            ),
            patch("routes.owner.tenants.db.session.commit", side_effect=RuntimeError("x")),
        ):
            assert to_client.post("/owner/api/tenant/2/toggle-status", json={}).status_code == 500


class TestUpdatePackageApi:
    def test_not_json_missing_field_value(self, to_client):
        assert (
            to_client.post("/owner/api/tenant/2/update-package", data="x", content_type="text/plain").status_code == 400
        )
        with patch("services.owner_ops_service.OwnerOpsService.get_tenant", return_value=None):
            assert to_client.post("/owner/api/tenant/2/update-package", json={}).status_code == 404
        with patch("services.owner_ops_service.OwnerOpsService.get_tenant", return_value=_tenant(2)):
            assert (
                to_client.post("/owner/api/tenant/2/update-package", json={"field": "nope", "value": 1}).status_code
                == 400
            )
            assert (
                to_client.post(
                    "/owner/api/tenant/2/update-package",
                    json={"field": "max_users", "value": "abc"},
                ).status_code
                == 400
            )

    def test_update_ok_and_error(self, to_client):
        with (
            patch(
                "services.owner_ops_service.OwnerOpsService.get_tenant",
                return_value=_tenant(2),
            ),
            patch("routes.owner.tenants.db.session"),
        ):
            assert (
                to_client.post(
                    "/owner/api/tenant/2/update-package",
                    json={"field": "max_users", "value": 9},
                ).status_code
                == 200
            )
        with (
            patch(
                "services.owner_ops_service.OwnerOpsService.get_tenant",
                return_value=_tenant(2),
            ),
            patch("routes.owner.tenants.db.session.commit", side_effect=RuntimeError("x")),
        ):
            assert (
                to_client.post(
                    "/owner/api/tenant/2/update-package",
                    json={"field": "max_users", "value": 9},
                ).status_code
                == 500
            )


class TestExtendSubscription:
    def test_form_bad_days(self, to_client):
        with patch(
            "services.owner_ops_service.OwnerOpsService.get_tenant_or_404",
            return_value=_tenant(2),
        ):
            assert to_client.post("/owner/tenants/2/extend-subscription", data={"days": "xx"}).status_code in (200, 302)

    def test_form_end_and_plan(self, to_client):
        from services.saas_provisioning_service import SaaSProvisioningService

        with (
            patch(
                "services.owner_ops_service.OwnerOpsService.get_tenant_or_404",
                return_value=_tenant(2),
            ),
            patch("routes.owner.tenants.db.session"),
            patch.object(SaaSProvisioningService, "apply_plan_with_template", return_value=None),
        ):
            assert to_client.post(
                "/owner/tenants/2/extend-subscription",
                data={"subscription_end": "2030-05-05", "subscription_plan": "pro"},
            ).status_code in (200, 302)
            assert to_client.post(
                "/owner/tenants/2/extend-subscription",
                data={"days": "30", "is_trial": "1"},
            ).status_code in (200, 302)

    def test_form_error(self, to_client):
        with (
            patch(
                "services.owner_ops_service.OwnerOpsService.get_tenant_or_404",
                return_value=_tenant(2),
            ),
            patch("routes.owner.tenants.db.session.commit", side_effect=RuntimeError("x")),
        ):
            assert to_client.post("/owner/tenants/2/extend-subscription", data={"days": "5"}).status_code in (200, 302)

    def test_form_zero_days_no_plan(self, to_client):
        with (
            patch(
                "services.owner_ops_service.OwnerOpsService.get_tenant_or_404",
                return_value=_tenant(2),
            ),
            patch("routes.owner.tenants.db.session"),
        ):
            assert to_client.post("/owner/tenants/2/extend-subscription", data={}).status_code in (
                200,
                302,
            )

    def test_api_variants(self, to_client):
        assert (
            to_client.post(
                "/owner/api/tenant/2/extend-subscription",
                data="x",
                content_type="text/plain",
            ).status_code
            == 400
        )
        with patch("services.owner_ops_service.OwnerOpsService.get_tenant", return_value=None):
            assert to_client.post("/owner/api/tenant/2/extend-subscription", json={}).status_code == 404
        with patch("services.owner_ops_service.OwnerOpsService.get_tenant", return_value=_tenant(2)):
            assert to_client.post("/owner/api/tenant/2/extend-subscription", json={"days": "xx"}).status_code == 400

    def test_api_ok_end_plan_error(self, to_client):
        from services.saas_provisioning_service import SaaSProvisioningService

        with (
            patch(
                "services.owner_ops_service.OwnerOpsService.get_tenant",
                return_value=_tenant(2),
            ),
            patch("routes.owner.tenants.db.session"),
            patch.object(SaaSProvisioningService, "apply_plan_with_template", return_value=None),
        ):
            assert (
                to_client.post(
                    "/owner/api/tenant/2/extend-subscription",
                    json={"subscription_end": "2031-01-01", "subscription_plan": "p"},
                ).status_code
                == 200
            )
            assert to_client.post("/owner/api/tenant/2/extend-subscription", json={"days": "10"}).status_code == 200
        with (
            patch(
                "services.owner_ops_service.OwnerOpsService.get_tenant",
                return_value=_tenant(2),
            ),
            patch("routes.owner.tenants.db.session"),
        ):
            assert to_client.post("/owner/api/tenant/2/extend-subscription", json={}).status_code == 200
        with (
            patch(
                "services.owner_ops_service.OwnerOpsService.get_tenant",
                return_value=_tenant(2),
            ),
            patch("routes.owner.tenants.db.session.commit", side_effect=RuntimeError("x")),
        ):
            assert to_client.post("/owner/api/tenant/2/extend-subscription", json={"days": "10"}).status_code == 500
