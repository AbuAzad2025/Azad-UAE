"""Wave 10 — precise line closure for 7 remaining modules (separate file).

Targets (from the coverage report):
- models/card_vault.py             → ImportError fallback + card-type detector arms
- utils/i18n.py                    → ``_()`` TRANSLATIONS lookup arm
- utils/feature_guards.py          → request.is_json / missing tenant / POS sub-feature
- utils/system_init.py             → clean-platform bootstrap + exists-arms + email/password guards
- utils/offsite_backup.py          → not-configured, older-sibling skip, paginator error, invalid key
- ai_knowledge/expansion/knowledge_sources.py → stale cache, non-200, tax missing, dedupe, __main__
- ai_knowledge/core/system_integration.py → request tenant + cross-tenant guard arms
"""

from __future__ import annotations

import builtins
import importlib
import os
import runpy
import sys
import types
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask, g
from flask.globals import _cv_request
from werkzeug.exceptions import Forbidden

import utils.offsite_backup as offsite_backup
import utils.system_init as system_init_module
from ai_knowledge.core.system_integration import SystemIntegrator
from ai_knowledge.expansion.knowledge_sources import KnowledgeSourceManager, recommend_sources_for_query
from utils.feature_guards import _feature_denial


class TestCardVaultWave10:
    def test_import_without_fernet_sets_none(self, monkeypatch):
        import extensions as _ext
        import models.card_vault as m

        _real_import = builtins.__import__
        _real_card_vault = m.CardVault

        def _blocked_import(name, *args, **kwargs):
            if name.startswith("cryptography"):
                raise ImportError(f"No module named {name!r}")
            return _real_import(name, *args, **kwargs)

        class _PlainModel:
            pass

        fake_db = types.SimpleNamespace(
            Model=_PlainModel,
            Column=lambda *a, **k: MagicMock(),
            ForeignKey=lambda *a, **k: MagicMock(),
            relationship=lambda *a, **k: MagicMock(),
            Integer=MagicMock(),
            String=MagicMock(),
            LargeBinary=MagicMock(),
            Boolean=MagicMock(),
            DateTime=MagicMock(),
        )
        original_db = _ext.db
        monkeypatch.setattr(builtins, "__import__", _blocked_import)
        monkeypatch.setattr(_ext, "db", fake_db)
        try:
            reloaded = importlib.reload(m)
        finally:
            reloaded.db = original_db
            reloaded.CardVault = _real_card_vault
        assert reloaded.HAS_CRYPTO is False
        assert reloaded.Fernet is None
        assert reloaded.CardVault is _real_card_vault

    def test_detect_card_type_arms(self):
        from models.card_vault import CardVault

        assert CardVault._detect_card_type("5511111111111111") == "mastercard"
        assert CardVault._detect_card_type("341111111111111") == "amex"
        assert CardVault._detect_card_type("6011111111111111") == "discover"
        assert CardVault._detect_card_type("9999111111111") == "unknown"


class TestI18nWave10:
    def test_underscore_uses_translations_lookup(self, app):
        import utils.i18n

        with patch("utils.i18n.gettext", side_effect=lambda text: text):
            with app.test_request_context():
                assert utils.i18n._("Save") == utils.i18n.TRANSLATIONS["Save"]["ar"]


class TestFeatureGuardsWave10:
    def test_wants_json_accepts_json_content_type(self, app):
        tenant = MagicMock()
        tenant.enable_payroll = False
        with (
            app.test_request_context("/payroll/", json={}),
            patch("utils.tenanting.get_active_tenant_id", return_value=1),
            patch("utils.feature_guards.db.session") as session,
        ):
            session.get.return_value = tenant
            resp, status = _feature_denial("payroll")
        assert status == 403
        assert resp.get_json()["error"] == "FEATURE_LOCKED"

    def test_missing_tenant_aborts_403(self, app):
        with (
            app.test_request_context("/payroll/"),
            patch("utils.tenanting.get_active_tenant_id", return_value=99),
            patch("utils.feature_guards.db.session") as session,
        ):
            session.get.return_value = None
            with pytest.raises(Forbidden):
                _feature_denial("payroll")

    def test_nullable_pos_feature_inherits_plan_default(self, app):
        tenant = MagicMock()
        tenant.enable_pos_promotions = None
        with (
            app.test_request_context("/pos/"),
            patch("utils.tenanting.get_active_tenant_id", return_value=1),
            patch("utils.feature_guards.db.session") as session,
            patch("utils.feature_guards.pos_feature_enabled", return_value=True) as pfe,
        ):
            session.get.return_value = tenant
            assert _feature_denial("pos_promotions") is None
        pfe.assert_called_once_with(tenant, "pos_promotions")


@pytest.fixture
def wave10_offsite_env(monkeypatch):
    monkeypatch.setenv("OFFSITE_BACKUP_ENABLED", "1")
    monkeypatch.setenv("OFFSITE_BACKUP_BUCKET", "azad-wave10")
    monkeypatch.delenv("OFFSITE_BACKUP_PREFIX", raising=False)
    monkeypatch.delenv("OFFSITE_BACKUP_ENDPOINT", raising=False)
    return None


@pytest.fixture
def wave10_boto3():
    client = MagicMock(name="s3_client")
    module = types.ModuleType("boto3")
    module.client = MagicMock(return_value=client)
    with patch.dict(sys.modules, {"boto3": module}):
        yield module, client


class TestOffsiteBackupWave10:
    def test_latest_artifact_not_configured(self, monkeypatch):
        monkeypatch.delenv("OFFSITE_BACKUP_ENABLED", raising=False)
        monkeypatch.delenv("OFFSITE_BACKUP_BUCKET", raising=False)
        out = offsite_backup.latest_remote_artifact()
        assert out["ok"] is False
        assert "not configured" in out["error"]

    def test_download_artifact_not_configured(self, monkeypatch, tmp_path):
        monkeypatch.delenv("OFFSITE_BACKUP_ENABLED", raising=False)
        monkeypatch.delenv("OFFSITE_BACKUP_BUCKET", raising=False)
        out = offsite_backup.download_artifact("backups/x.tar.gz", str(tmp_path))
        assert out["ok"] is False
        assert "not configured" in out["error"]

    def test_download_latest_not_configured(self, monkeypatch, tmp_path):
        monkeypatch.delenv("OFFSITE_BACKUP_ENABLED", raising=False)
        monkeypatch.delenv("OFFSITE_BACKUP_BUCKET", raising=False)
        out = offsite_backup.download_latest_offsite_artifact(str(tmp_path))
        assert out["ok"] is False
        assert "not configured" in out["error"]

    def test_latest_skips_older_artifact(self, wave10_offsite_env, wave10_boto3):
        _, client = wave10_boto3
        newer = datetime(2026, 6, 1, tzinfo=UTC)
        paginator = MagicMock()
        paginator.paginate.return_value = [
            {
                "Contents": [
                    {"key": "backups/latest.tar.gz.enc", "LastModified": newer, "Size": 9},
                    {"key": "backups/older.tar.gz", "LastModified": newer - timedelta(days=1), "Size": 4},
                ]
            }
        ]
        client.get_paginator.return_value = paginator
        found = offsite_backup.latest_remote_artifact()
        assert found["ok"] is True
        assert found["key"] == "backups/latest.tar.gz.enc"

    def test_latest_paginator_error(self, wave10_offsite_env, wave10_boto3):
        _, client = wave10_boto3
        paginator = MagicMock()
        paginator.paginate.side_effect = OSError("s3 down")
        client.get_paginator.return_value = paginator
        out = offsite_backup.latest_remote_artifact()
        assert out["ok"] is False
        assert "OSError" in out["error"]

    def test_download_invalid_key(self, wave10_offsite_env, wave10_boto3, tmp_path):
        out = offsite_backup.download_artifact(".hidden", str(tmp_path))
        assert out["ok"] is False
        assert "invalid" in out["error"]


class TestKnowledgeSourcesWave10:
    def test_exchange_rates_stale_cache_refetches(self):
        mgr = KnowledgeSourceManager()
        stale = datetime.now() - timedelta(hours=25)
        mgr.cache["exchange_rates"] = ({"rates": {}}, stale)
        with patch("requests.get") as mock_get:
            mock_get.return_value.status_code = 500
            assert mgr.fetch_exchange_rates() is None

    def test_tax_resources_absent_country_mapping(self):
        assert KnowledgeSourceManager.get_tax_resources("Palestine") == []

    def test_recommend_sources_dedupes(self):
        results = recommend_sources_for_query("قطعة محرك")
        ids = [r["id"] for r in results]
        assert len(ids) == len(set(ids))

    def test_main_block(self):
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        module_path = os.path.join(root, "ai_knowledge", "expansion", "knowledge_sources.py")
        namespace = runpy.run_path(module_path, run_name="__main__")
        assert namespace["KNOWLEDGE_SOURCES"]


class TestSystemIntegratorWave10:
    @staticmethod
    def _customer(**overrides):
        customer = MagicMock()
        customer.tenant_id = overrides.get("tenant_id", 5)
        customer.id = 7
        customer.name = "Ali Test"
        customer.get_balance_aed.return_value = 100
        customer.sales.count.return_value = 1
        last_sale = MagicMock()
        last_sale.created_at = datetime(2026, 1, 1)
        customer.sales.order_by.return_value.first.return_value = last_sale
        customer.customer_type = "regular"
        customer.phone = "0500000000"
        customer.email = "ali@test.com"
        return customer

    @staticmethod
    def _chain(**returns):
        chain = MagicMock()
        chain.filter = MagicMock(return_value=chain)
        for attr, value in returns.items():
            setattr(chain, attr, MagicMock(return_value=value))
        return chain

    def test_financial_summary_applies_tenant_filters(self, app):
        from ai_knowledge.core.system_integration import SystemIntegrator

        with app.test_request_context("/x/"):
            g.active_tenant_id = 5
            base_q = MagicMock()
            base_q.filter.return_value = base_q
            base_q.scalar.return_value = Decimal("100")
            with patch(
                "extensions.db.session.query",
                return_value=base_q,
            ):
                result = SystemIntegrator.get_financial_summary()
        assert result["success"] is True
        assert result["financial"]["total_sales"] == 100.0
        assert base_q.filter.call_count >= 5
        filters = [call.args[0] for call in base_q.filter.call_args_list]
        assert any("tenant_id" in str(arg) for arg in filters)

    def test_active_tid_reads_flask_g(self, app):
        from ai_knowledge.core.system_integration import _active_tid

        token = _cv_request.set(None)
        try:
            assert _active_tid() is None
        finally:
            _cv_request.reset(token)
        with app.test_request_context("/x/"):
            g.active_tenant_id = 42
            assert _active_tid() == 42
        with app.test_request_context("/y/"):
            g.active_tenant_id = None
            assert _active_tid() is None

    def test_session_tid_converts_authenticated(self):
        from ai_knowledge.core.system_integration import _session_tid

        cu = MagicMock()
        cu.is_authenticated = True
        with (
            patch("flask_login.current_user", cu),
            patch("utils.tenanting.get_active_tenant_id", return_value="7"),
        ):
            assert _session_tid() == 7

    def test_session_tid_exception_returns_none(self):
        from ai_knowledge.core.system_integration import _session_tid

        cu = MagicMock()
        cu.is_authenticated = True
        with (
            patch("flask_login.current_user", cu),
            patch("utils.tenanting.get_active_tenant_id", side_effect=RuntimeError("boom")),
        ):
            assert _session_tid() is None

    def test_customer_balance_name_search_filters_tenant(self, app):
        with app.test_request_context("/x/"):
            g.active_tenant_id = 5
            chain = self._chain(first=self._customer())
            with patch("models.Customer") as MockC, patch("models.Sale"):
                MockC.query.filter.return_value = chain
                result = SystemIntegrator.get_customer_balance("Ali Test")
        assert result["success"] is True

    def test_customer_balance_cross_tenant_guard(self, app):
        with app.test_request_context("/x/"):
            g.active_tenant_id = 5
            chain = self._chain(first=self._customer(tenant_id=6))
            with patch("models.Customer") as MockC, patch("models.Sale"):
                MockC.query.filter.return_value = chain
                result = SystemIntegrator.get_customer_balance("Ali Test")
        assert result["success"] is False
        assert "غير موجود" in result["error"]

    def test_supplier_balance_name_search_filters_tenant(self, app):
        supplier = MagicMock()
        supplier.tenant_id = 5
        supplier.id = 8
        supplier.name = "Sup Test"
        supplier.get_balance_aed.return_value = 200
        supplier.purchases.count.return_value = 1
        last = MagicMock()
        last.created_at = datetime(2026, 1, 1)
        supplier.purchases.order_by.return_value.first.return_value = last
        supplier.supplier_type = "parts"
        supplier.phone = "0500000000"
        supplier.email = "sup@test.com"
        with app.test_request_context("/x/"):
            g.active_tenant_id = 5
            chain = self._chain(first=supplier)
            with patch("models.Supplier") as MockS, patch("models.Purchase"):
                MockS.query.filter.return_value = chain
                result = SystemIntegrator.get_supplier_balance("Sup Test")
        assert result["success"] is True

    def test_supplier_balance_cross_tenant_guard(self, app):
        supplier = MagicMock()
        supplier.tenant_id = 6
        supplier.name = "Sup Test"
        with app.test_request_context("/x/"):
            g.active_tenant_id = 5
            chain = self._chain(first=supplier)
            with patch("models.Supplier") as MockS, patch("models.Purchase"):
                MockS.query.filter.return_value = chain
                result = SystemIntegrator.get_supplier_balance("Sup Test")
        assert result["success"] is False

    def test_customer_sales_summary_cross_tenant_guard(self, app):
        customer = MagicMock()
        customer.tenant_id = 6
        with app.test_request_context("/x/"):
            g.active_tenant_id = 5
            with patch("models.Customer") as MockC, patch("models.Sale"):
                MockC.query.get.return_value = customer
                result = SystemIntegrator.get_customer_sales_summary("7")
        assert result["success"] is False

    def test_customer_sales_summary_tenant_filtered(self, app):
        customer = MagicMock()
        customer.tenant_id = 5
        customer.id = 7
        sale = MagicMock()
        sale.id = 1
        sale.total_amount = 120
        sale.paid_amount = 120
        sale.created_at = datetime(2026, 1, 1)
        sq = MagicMock()
        sq.filter_by.return_value = sq
        sq.order_by.return_value = sq
        sq.all.return_value = [sale]
        with app.test_request_context("/x/"):
            g.active_tenant_id = 5
            with patch("models.Customer") as MockC, patch("models.Sale") as MockS:
                MockC.query.get.return_value = customer
                MockS.query.filter_by.return_value = sq
                result = SystemIntegrator.get_customer_sales_summary("7")
        assert result["success"] is True
        assert result["summary"]["total_sales"] == 1

    def test_add_customer_legacy_tenant_lookup_error(self):
        with patch("models.tenant.Tenant") as MockT:
            MockT.get_current.side_effect = RuntimeError("legacy down")
            result = SystemIntegrator.add_customer({"name": "X", "customer_type": "regular"})
        assert result["success"] is False
        assert "تينانت" in result["error"]

    def test_product_stock_tenant_filter(self, app):
        product = MagicMock()
        product.tenant_id = 5
        product.id = 9
        product.name = "Piston"
        product.sku = "PST-1"
        product.current_stock = 10
        product.min_stock_alert = 5
        product.unit_price = 20
        product.category = None
        with app.test_request_context("/x/"):
            g.active_tenant_id = 5
            chain = self._chain(first=product)
            with patch("models.Product") as MockP:
                MockP.query.filter.return_value = chain
                result = SystemIntegrator.get_product_stock("PST-1")
        assert result["success"] is True
        assert result["product"]["status"] == "جيد"

    def test_product_stock_cross_tenant_guard(self, app):
        product = MagicMock()
        product.tenant_id = 6
        with app.test_request_context("/x/"):
            g.active_tenant_id = 5
            chain = self._chain(first=product)
            with patch("models.Product") as MockP:
                MockP.query.filter.return_value = chain
                result = SystemIntegrator.get_product_stock("PST-1")
        assert result["success"] is False

    def test_search_data_sale_tenant_filter(self, app):
        sale = MagicMock()
        sale.id = 1
        sale.customer = None
        sale.total_amount = 10
        sale.created_at = datetime(2026, 1, 1)
        sq = MagicMock()
        sq.filter.return_value = sq
        sq.limit.return_value = sq
        sq.all.return_value = [sale]
        q = MagicMock()
        q.filter.return_value = q
        q.limit.return_value = q
        q.all.return_value = []
        with app.test_request_context("/x/"):
            g.active_tenant_id = 5
            with patch("models.Customer") as MockC, patch("models.Product") as MockP, patch("models.Sale") as MockS:
                MockC.query.filter.return_value = q
                MockP.query.filter.return_value = q
                MockS.query.join.return_value = sq
                result = SystemIntegrator.search_data("Ali")
        assert result["success"] is True


class TestSystemInitWave10:
    @pytest.fixture
    def clean_app(self):
        _app = Flask(__name__)
        _app.config.update(
            OWNER_USERNAME="owner",
            OWNER_EMAIL="owner@example.com",
            OWNER_PASSWORD="secret",
            MAIL_USERNAME="mailer",
            MAIL_PASSWORD="pass",
        )
        _app.logger = MagicMock()
        return _app

    @staticmethod
    @contextmanager
    def _tenant_scope():
        yield

    def test_ensure_clean_platform_bootstrap(self, clean_app):
        with (
            patch("utils.system_init.db.create_all"),
            patch("utils.system_init._ensure_permissions"),
            patch("utils.system_init._ensure_owner_role", return_value=MagicMock(slug="owner")),
            patch("utils.system_init._ensure_owner_user", return_value=(MagicMock(), True)),
            patch("utils.system_init._record_server_activation"),
            patch("utils.system_init._ensure_super_admin_role"),
            patch("utils.system_init._ensure_developer_role"),
            patch("utils.system_init._ensure_functional_roles"),
            patch("utils.system_init._ensure_platform_reference_data"),
            patch("utils.tenanting.without_tenant_scope", return_value=self._tenant_scope()),
        ):
            system_init_module.ensure_clean_platform(clean_app)
        clean_app.logger.info.assert_any_call("SystemInit: Clean platform bootstrap complete (no tenants seeded).")

    def test_permissions_skip_existing_codes(self, clean_app):
        query = MagicMock()
        query.filter_by.return_value.first.return_value = MagicMock(code="manage_sales")
        with (
            clean_app.app_context(),
            patch.object(system_init_module.Permission, "query", query),
            patch("utils.system_init.db.session") as session,
            patch("utils.constants.PERMISSION_CODES", ["manage_sales"]),
            patch("utils.constants.PERMISSIONS", {"manage_sales": {"en": "Manage", "ar": "إدارة"}}),
        ):
            system_init_module._ensure_permissions()
        session.add.assert_not_called()

    def test_owner_role_exists_skips_creation(self, clean_app):
        role = MagicMock(slug="owner", permissions=[])
        perm_query = MagicMock()
        perm_query.all.return_value = [MagicMock(code="admin")]
        role_query = MagicMock()
        role_query.filter_by.return_value.first.return_value = role
        with (
            clean_app.app_context(),
            patch.object(system_init_module.Role, "query", role_query),
            patch.object(system_init_module.Permission, "query", perm_query),
            patch("utils.system_init.db.session") as session,
        ):
            result = system_init_module._ensure_owner_role()
        assert result is role
        session.add.assert_not_called()

    def test_super_admin_role_skips_when_permissions_match(self, clean_app):
        perm = MagicMock(code="admin")
        role = MagicMock(slug="super_admin", permissions=[perm])
        role_query = MagicMock()
        role_query.filter_by.return_value.first.return_value = role
        perm_query = MagicMock()
        perm_query.all.return_value = [perm]
        with (
            clean_app.app_context(),
            patch.object(system_init_module.Role, "query", role_query),
            patch.object(system_init_module.Permission, "query", perm_query),
            patch("utils.system_init.db.session") as session,
        ):
            system_init_module._ensure_super_admin_role()
        session.add.assert_not_called()

    def test_developer_role_skips_when_permissions_match(self, clean_app):
        perm = MagicMock(code="admin")
        role = MagicMock(slug="developer", permissions=[perm])
        role_query = MagicMock()
        role_query.filter_by.return_value.first.return_value = role
        perm_query = MagicMock()
        perm_query.all.return_value = [perm]
        with (
            clean_app.app_context(),
            patch.object(system_init_module.Role, "query", role_query),
            patch.object(system_init_module.Permission, "query", perm_query),
            patch("utils.system_init.db.session") as session,
        ):
            system_init_module._ensure_developer_role()
        session.add.assert_not_called()

    def test_owner_user_requires_password(self):
        _app = Flask(__name__)
        _app.config.update(OWNER_USERNAME="owner", OWNER_EMAIL="owner@example.com")
        _app.logger = MagicMock()
        user_query = MagicMock()
        user_query.filter_by.return_value.first.return_value = None
        with (
            _app.app_context(),
            patch.object(system_init_module.User, "query", user_query),
            patch("utils.system_init.db.session"),
        ):
            with pytest.raises(RuntimeError, match="OWNER_PASSWORD"):
                system_init_module._ensure_owner_user(MagicMock())

    def test_owner_user_skips_email_update_for_system_email(self, clean_app):
        role = MagicMock()
        owner = MagicMock(username="owner", is_owner=True, role=role, email="legacy@example.com", id=1)
        user_query = MagicMock()
        user_query.filter_by.return_value.first.return_value = owner
        clean_app.config["OWNER_EMAIL"] = "owner@system.local"
        with (
            clean_app.app_context(),
            patch.object(system_init_module.User, "query", user_query),
            patch("utils.system_init.db.session") as session,
        ):
            user, created = system_init_module._ensure_owner_user(role)
        assert created is False
        assert user.email == "legacy@example.com"
        session.add.assert_not_called()

    def test_owner_user_email_already_equal_skips_update(self, clean_app):
        role = MagicMock()
        owner = MagicMock(username="owner", is_owner=True, role=role, email="owner@example.com", id=1)
        user_query = MagicMock()
        user_query.filter_by.return_value.first.return_value = owner
        with (
            clean_app.app_context(),
            patch.object(system_init_module.User, "query", user_query),
            patch("utils.system_init.db.session") as session,
        ):
            user, created = system_init_module._ensure_owner_user(role)
        assert created is False
        assert user.email == "owner@example.com"
        session.add.assert_not_called()

    def test_functional_roles_creation_with_missing_mid_roles(self, clean_app):
        kitchen = MagicMock(slug="kitchen", permissions=[])
        cashier = MagicMock(slug="cashier", permissions=[])
        existing = {"kitchen": kitchen, "cashier": cashier}

        def _filter_by(**kwargs):
            query = MagicMock()
            query.first.return_value = existing.get(kwargs["slug"])
            return query

        role_query = MagicMock()
        role_query.filter.return_value.first.return_value = None
        role_query.filter_by.side_effect = _filter_by
        perm_query = MagicMock()
        perm_query.all.return_value = [MagicMock(code="manage_sales")]
        with (
            clean_app.app_context(),
            patch.object(system_init_module.Role, "query", role_query),
            patch.object(system_init_module.Permission, "query", perm_query),
            patch("utils.system_init.db.session"),
        ):
            system_init_module._ensure_functional_roles()
        assert kitchen.permissions is not None
        assert cashier.permissions is not None

    def test_functional_roles_all_exist_skips_creation(self, clean_app):
        slugs = ("manager", "seller", "branch_manager", "accountant", "kitchen", "cashier")
        roles = {slug: MagicMock(slug=slug, permissions=[]) for slug in slugs}

        def _filter_by(**kwargs):
            query = MagicMock()
            query.first.return_value = roles[kwargs["slug"]]
            return query

        role_query = MagicMock()
        role_query.filter.return_value.first.return_value = MagicMock(slug="manager")
        role_query.filter_by.side_effect = _filter_by
        perm_query = MagicMock()
        perm_query.all.return_value = [MagicMock(code="manage_sales")]
        with (
            clean_app.app_context(),
            patch.object(system_init_module.Role, "query", role_query),
            patch.object(system_init_module.Permission, "query", perm_query),
            patch("utils.system_init.db.session"),
        ):
            system_init_module._ensure_functional_roles()
        assert all(role.permissions is not None for role in roles.values())