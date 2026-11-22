"""Final statement/branch coverage gaps for eight utils modules.

Every test here drives a real code path in the module under test. External
collaborators (the DB session, Flask globals, plan/tenant lookups) are patched at
the boundary; no production code is changed. The ZATCA material is generated
locally with a self-signed certificate and is never used against a real authority.
"""

from __future__ import annotations

import datetime
import logging
import os
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from flask import Flask
from werkzeug.exceptions import HTTPException

from utils import country_tax, decorators, error_messages, invoice_profile
from utils import query_profiler as qp
from utils import seed_manifest_probe as probe
from utils import tenanting as tn

# ─────────────────────────────────────────────────────────────────────────────
# utils/decorators.py
# ─────────────────────────────────────────────────────────────────────────────


class TestDecoratorsFinalGaps:
    @staticmethod
    def _user(**overrides):
        base = {
            "is_authenticated": True,
            "is_owner": False,
            "tenant_id": 7,
            "role": SimpleNamespace(slug="seller"),
        }
        base.update(overrides)
        return SimpleNamespace(**base)

    def test_finance_admin_redirects_anonymous(self, app):
        with app.test_request_context("/ledger/admin/"):
            with patch.object(decorators, "current_user", SimpleNamespace(is_authenticated=False)):
                response = decorators.finance_admin_required(lambda: "OK")()
        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]

    def test_finance_admin_allows_manager_role(self, app):
        user = self._user(role=SimpleNamespace(slug="manager"))
        with app.test_request_context("/ledger/admin/"):
            with (
                patch.object(decorators, "current_user", user),
                patch.object(decorators, "is_global_owner_user", return_value=False),
                patch.object(decorators, "is_admin_surface_user", return_value=False),
            ):
                assert decorators.finance_admin_required(lambda: "OK")() == "OK"

    def test_owner_or_company_admin_rejects_company_admin_without_tenant(self, app):
        user = self._user(role=SimpleNamespace(slug="manager"))
        user.is_super_admin = lambda: False
        with app.test_request_context("/company/"):
            with (
                patch.object(decorators, "current_user", user),
                patch.object(decorators, "is_global_owner_user", return_value=False),
                patch("utils.tenanting.get_active_tenant_id", return_value=None),
            ):
                with pytest.raises(HTTPException) as excinfo:
                    decorators.owner_or_company_admin(lambda: "OK")()
        assert excinfo.value.code == 403

    def test_require_subscription_feature_refuses_missing_tenant(self):
        with (
            patch("utils.tenanting.get_active_tenant_id", return_value=5),
            patch.object(decorators, "db") as mock_db,
        ):
            mock_db.session.get.return_value = None
            with pytest.raises(HTTPException) as excinfo:
                decorators.require_subscription_feature("ai")(lambda: "OK")()
        assert excinfo.value.code == 403

    def test_require_subscription_feature_null_non_pos_flag_is_disabled(self):
        tenant = SimpleNamespace(id=1, enable_ai=None)
        with (
            patch("utils.tenanting.get_active_tenant_id", return_value=1),
            patch.object(decorators, "db") as mock_db,
        ):
            mock_db.session.get.return_value = tenant
            with pytest.raises(HTTPException) as excinfo:
                decorators.require_subscription_feature("ai")(lambda: "OK")()
        assert excinfo.value.code == 403

    def test_require_subscription_feature_plan_gate(self):
        tenant = SimpleNamespace(id=1, subscription_plan="basic")
        with (
            patch("utils.tenanting.get_active_tenant_id", return_value=1),
            patch.object(decorators, "db") as mock_db,
        ):
            mock_db.session.get.return_value = tenant
            with patch.object(decorators, "plan_meets", return_value=False):
                with pytest.raises(HTTPException) as excinfo:
                    decorators.require_subscription_feature("pro")(lambda: "OK")()
            assert excinfo.value.code == 403

            with patch.object(decorators, "plan_meets", return_value=True):
                assert decorators.require_subscription_feature("enterprise")(lambda: "OK")() == "OK"

    def test_require_subscription_feature_unknown_feature_falls_through(self):
        tenant = SimpleNamespace(id=1)
        with (
            patch("utils.tenanting.get_active_tenant_id", return_value=1),
            patch.object(decorators, "db") as mock_db,
        ):
            mock_db.session.get.return_value = tenant
            assert decorators.require_subscription_feature("mystery")(lambda: "OK")() == "OK"

    def test_api_key_usage_tracking_failure_is_best_effort(self, app):
        api_key = SimpleNamespace(tenant_id=5, scope="write", last_used=None, usage_count=0)
        headers = {"X-API-Key": "the-key", "X-API-Secret": "the-secret"}
        with app.test_request_context("/api/sync", headers=headers):
            with (
                patch("utils.db_safety.atomic_transaction") as atomic,
                patch("utils.tenanting.get_tenant_status", return_value={"ok": True}),
                patch("extensions.db") as mock_db,
            ):
                atomic.return_value.__enter__.side_effect = RuntimeError("tracking unavailable")
                mock_db.session.query.return_value.filter_by.return_value.first.return_value = api_key
                guarded = decorators.api_key_required("write")(lambda: "OK")
                assert guarded() == "OK"


# ─────────────────────────────────────────────────────────────────────────────
# utils/query_profiler.py
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _profiler_clean_state():
    qp.reset()
    qp._LAST_SQL["select"] = 0
    qp._LAST_SQL["write"] = 0
    yield
    qp.reset()
    qp.disable_profiling()


def _teardown_hook(flask_app: Flask):
    qp._flush_on_teardown(flask_app)
    return flask_app.teardown_request_funcs[None][-1]


class TestQueryProfilerFinalGaps:
    def test_flag_from_env_and_public_enabled_probe(self):
        with patch.dict(os.environ, {"QUERY_PROFILE": "YES"}):
            assert qp._flag_from_env() is True
        with patch.dict(os.environ, {"QUERY_PROFILE": "off"}):
            assert qp._flag_from_env() is False
        qp.enable_profiling()
        assert qp.is_enabled() is True
        qp.disable_profiling()
        assert qp.is_enabled() is False

    def test_disabled_bump_is_a_no_op(self):
        qp.disable_profiling()
        qp._bump_request("select")
        assert qp._LAST_SQL == {"select": 0, "write": 0}

    def test_current_endpoint_without_request_context(self):
        with patch("flask.has_request_context", return_value=False):
            assert qp._current_endpoint() == "<no-request>"

    def test_after_request_hook_short_circuits_when_disabled(self):
        qp.disable_profiling()
        response = object()
        assert qp._record_current_request(response) is response
        assert qp._COUNTS == {}

    def test_after_request_hook_without_request_context_records_under_fallback(self):
        qp.enable_profiling()
        qp._LAST_SQL["select"] = 2
        response = object()
        with patch("flask.has_request_context", return_value=False):
            assert qp._record_current_request(response) is response
        assert qp._COUNTS["<no-request>"][1] == 2

    def test_after_request_hook_skips_an_already_recorded_request(self, app):
        qp.enable_profiling()
        with app.test_request_context("/dashboard"):
            from flask import g

            g._query_profiler_recorded = True
            response = object()
            assert qp._record_current_request(response) is response
        assert qp._COUNTS == {}

    def test_app_hooks_are_idempotent(self):
        flask_app = Flask(__name__)
        qp._attach_after_request(flask_app)
        qp._attach_after_request(flask_app)
        assert flask_app._query_profiler_hooked is True
        hook = _teardown_hook(flask_app)
        _teardown_hook(flask_app)
        assert hook is flask_app.teardown_request_funcs[None][-1]

    def test_teardown_returns_when_disabled_or_outside_request(self):
        flask_app = Flask(__name__)
        qp.enable_profiling()
        hook = _teardown_hook(flask_app)
        hook(None)  # no request context
        qp.disable_profiling()
        with flask_app.test_request_context("/"):
            hook(None)  # profiling disabled

    def test_teardown_records_a_request_that_never_reached_after_request(self):
        flask_app = Flask(__name__)
        hook = _teardown_hook(flask_app)
        qp.enable_profiling()
        with flask_app.test_request_context("/aborted"):
            from flask import g

            qp._LAST_SQL["select"] = 3
            hook(None)
            # The teardown stamps the flag first, so the after_request hook it
            # invokes sees an already-recorded request and returns immediately.
            assert g._query_profiler_recorded is True

    def test_teardown_with_no_sql_does_not_create_a_bucket(self):
        flask_app = Flask(__name__)
        hook = _teardown_hook(flask_app)
        qp.enable_profiling()
        with flask_app.test_request_context("/idle"):
            from flask import g

            hook(None)
            assert g._query_profiler_recorded is True
        assert qp._COUNTS == {}


# ─────────────────────────────────────────────────────────────────────────────
# utils/seed_manifest_probe.py
# ─────────────────────────────────────────────────────────────────────────────


class TestSeedManifestProbeFinalGaps:
    def test_pos_order_type_and_store_payment_method_probes(self, app):
        with app.app_context():
            assert isinstance(probe.count_pos_order_types(), int)
            assert isinstance(probe.count_store_payment_methods(), int)
            assert isinstance(probe.count_gl_mappings(), int)

    def test_min_gl_accounts_with_no_active_tenants(self):
        with patch.object(probe, "db") as mock_db:
            mock_db.session.query.return_value.filter.return_value.all.return_value = []
            assert probe.min_gl_accounts_for_active_tenant() == 0

    def test_missing_gl_mappings_probe_when_dynamic_mapping_is_off(self):
        with patch("services.gl_service.is_dynamic_gl_mapping_enabled", return_value=False):
            assert probe.count_tenants_missing_required_gl_mappings() == 0


# ─────────────────────────────────────────────────────────────────────────────
# utils/invoice_profile.py
# ─────────────────────────────────────────────────────────────────────────────


class TestInvoiceProfileFinalGaps:
    @staticmethod
    def _tenant():
        return SimpleNamespace(id=1, name="Demo", name_ar="عرض", name_en="Demo EN")

    def test_unknown_private_attribute_raises_and_tenant_property_returns_source(self):
        snapshot = invoice_profile.build_invoice_settings_snapshot(self._tenant())
        with pytest.raises(AttributeError):
            _ = snapshot._not_a_real_attribute
        assert snapshot.tenant is snapshot._tenant

    def test_source_settings_metadata_is_copied_onto_the_snapshot(self):
        source = SimpleNamespace(
            id=17,
            created_at="2026-01-01",
            updated_at="2026-02-01",
            updated_by=42,
            is_active=False,
        )
        snapshot = invoice_profile.build_invoice_settings_snapshot(self._tenant(), source_settings=source)
        assert snapshot.id == 17
        assert snapshot.created_at == "2026-01-01"
        assert snapshot.updated_at == "2026-02-01"
        assert snapshot.updated_by == 42
        assert snapshot.is_active is False

    def test_source_settings_without_optional_metadata_uses_defaults(self):
        snapshot = invoice_profile.build_invoice_settings_snapshot(self._tenant(), source_settings=SimpleNamespace())
        assert snapshot.is_active is True

    def test_allow_files_ignores_unknown_fields_and_blank_filenames(self):
        tenant = self._tenant()
        returned = invoice_profile.apply_snapshot_to_tenant(
            tenant,
            {},
            allow_files={"unknown_snapshot_field": "x.png", "logo_url": "", "stamp_url": "stamp.png"},
        )
        assert returned is tenant
        assert tenant.stamp_url == "stamp.png"
        assert not hasattr(tenant, "logo_url")

    def test_resolve_print_profile_without_tenant_id(self):
        assert invoice_profile.resolve_print_profile(None) is None


# ─────────────────────────────────────────────────────────────────────────────
# utils/tenanting.py
# ─────────────────────────────────────────────────────────────────────────────


class TestTenantingFinalGaps:
    def test_current_request_id_handles_unbound_and_non_request_proxies(self):
        def _explode():
            raise RuntimeError("no request context")

        with patch("flask.request", SimpleNamespace(_get_current_object=_explode)):
            assert tn._current_request_id() is None

        with patch("flask.request", SimpleNamespace(_get_current_object=lambda: SimpleNamespace())):
            assert tn._current_request_id() is None

        with patch("flask.request", SimpleNamespace(_get_current_object=lambda: None)):
            assert tn._current_request_id() is None

    def test_anonymous_fallback_swallows_g_context_failures(self):
        with (
            patch.object(tn, "_resolve_user", return_value=None),
            patch.object(tn, "g_active_tenant_is_current", side_effect=RuntimeError("stale context")),
        ):
            assert tn.get_active_tenant_id() is None

    def test_platform_owner_swallows_session_lookup_failures(self):
        user = SimpleNamespace(is_authenticated=True, is_owner=True, tenant_id=None)
        with (
            patch.object(tn, "g_active_tenant_is_current", return_value=True),
            patch.object(tn.session, "get", side_effect=RuntimeError("session unavailable")),
        ):
            assert tn.get_active_tenant_id(user) is None


# ─────────────────────────────────────────────────────────────────────────────
# utils/error_messages.py
# ─────────────────────────────────────────────────────────────────────────────


class TestErrorMessagesFinalGaps:
    def test_cheque_guidance_messages(self):
        assert "إيداع" in error_messages.ErrorMessages.cheque_bounce_requires_deposit()
        assert "الحقول" in error_messages.ErrorMessages.cheque_missing_fields(["amount", "bank"])
        assert "القيمة" in error_messages.ErrorMessages.cheque_invalid_value("amount", "number")

    def test_default_logger_falls_back_outside_app_context(self):
        class _NoAppContext:
            @property
            def logger(self):
                raise RuntimeError("Working outside of application context")

        with patch.object(error_messages, "current_app", _NoAppContext()):
            assert error_messages._default_logger() is logging.getLogger("utils.error_messages")


# ─────────────────────────────────────────────────────────────────────────────
# utils/country_tax.py
# ─────────────────────────────────────────────────────────────────────────────


class TestCountryTaxFinalGaps:
    def test_corporate_threshold_and_zakat_rate_accessors(self):
        assert country_tax.corporate_threshold_for_country("AE") == Decimal("375000")
        assert country_tax.corporate_threshold_for_country("XX") is None
        assert country_tax.zakat_rate_for_country("SA") == Decimal("2.5")
        assert country_tax.zakat_rate_for_country("AE") is None

    def test_corporate_tax_honours_explicit_tenant_threshold(self):
        result = country_tax.compute_corporate_tax(Decimal("500000"), "AE", tenant_threshold=Decimal("100000"))
        assert result["threshold"] == Decimal("100000")
        assert result["taxable"] == Decimal("400000")

    def test_zero_salary_has_no_social_insurance(self):
        result = country_tax.social_insurance_amount(0, "PS")
        assert result == {
            "employee": Decimal("0"),
            "employer": Decimal("0"),
            "ceiling": None,
            "floor": None,
            "eligible": False,
        }

    def test_zero_pensionable_salary_is_ineligible(self):
        result = country_tax.il_pension_amount(0)
        assert result == {
            "employee": Decimal("0"),
            "employer": Decimal("0"),
            "base": Decimal("0"),
            "eligible": False,
        }


# ─────────────────────────────────────────────────────────────────────────────
# utils/einvoice_phase2_document.py
# ─────────────────────────────────────────────────────────────────────────────


class TestEInvoicePhase2FinalGaps:
    @staticmethod
    def _csid_material():
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import NameOID

        key = ec.generate_private_key(ec.SECP256R1())
        now = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "local-phase2-gap-test")])
        certificate = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=365))
            .sign(key, hashes.SHA256())
        )
        private_pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
        certificate_pem = certificate.public_bytes(serialization.Encoding.PEM).decode()
        return private_pem, certificate_pem

    @staticmethod
    def _sale(*, subtotal, lines, buyer_tax_number):
        line = SimpleNamespace(
            unit_price=Decimal("1000"),
            line_total=Decimal("1000"),
            product=SimpleNamespace(name="Widget"),
            product_id=1,
            quantity=Decimal("1"),
            tax_category="standard",
        )
        return SimpleNamespace(
            id=42,
            sale_number="S-PH2-GAP",
            customer=SimpleNamespace(name="Buyer", tax_number=buyer_tax_number),
            sale_date=datetime.datetime(2026, 11, 9, 10, 0, 0, tzinfo=datetime.UTC),
            tax_rate=Decimal("15"),
            total_amount=Decimal("1150"),
            tax_amount=Decimal("150"),
            taxable_amount=Decimal("1000"),
            subtotal=subtotal,
            lines=lines if lines is not None else [line],
        )

    def _build(self, sale):
        from utils.einvoice_phase2_document import build_signed_invoice_xml

        private_pem, certificate_pem = self._csid_material()
        return build_signed_invoice_xml(
            sale,
            SimpleNamespace(
                id=1,
                name_en="Seller EN",
                name="Seller",
                name_ar="بائع",
                tax_number="300000000000003",
                address_en="Street 1",
                city="Riyadh",
            ),
            icv=7,
            previous_pih="",
            csid_private_key_pem=private_pem,
            csid_certificate_pem=certificate_pem,
        )

    def test_missing_issue_date_uses_midnight_utc(self):
        from utils.einvoice_phase2_document import _iso_date_time

        assert _iso_date_time(SimpleNamespace(sale_date=None)) == ("", "00:00:00Z")

    def test_buyer_with_tax_number_gets_a_party_tax_scheme(self):
        result = self._build(self._sale(subtotal=Decimal("1000"), lines=None, buyer_tax_number="1234567890"))
        assert "<cac:PartyTaxScheme>" in result["xml_payload"]
        assert "<cbc:CompanyID>1234567890</cbc:CompanyID>" in result["xml_payload"]

    def test_line_extension_is_summed_from_lines_when_subtotal_is_blank(self):
        result = self._build(self._sale(subtotal=Decimal("0"), lines=None, buyer_tax_number=""))
        assert ">1000.000</cbc:LineExtensionAmount>" in result["xml_payload"]

    def test_line_extension_with_no_lines_falls_back_to_zero(self):
        result = self._build(self._sale(subtotal=Decimal("0"), lines=[], buyer_tax_number=""))
        assert ">0.000</cbc:LineExtensionAmount>" in result["xml_payload"]
