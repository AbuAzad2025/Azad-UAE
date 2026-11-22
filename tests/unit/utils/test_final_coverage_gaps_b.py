"""Last-mile statement coverage for small gaps across ``utils/``.

Each test targets one or two defensive/error lines the main slices leave
behind. Everything is offline or uses the standard fixtures; no production
module is modified and nothing is committed.

The defensive "no certificate" guard in ``utils/zatca_crypto.py`` is driven
through a stubbed loader, since cryptography itself raises on such a PEM.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from sqlalchemy.exc import OperationalError

from utils import (
    backup_crypto,
    build_assets,
    cache_decorators,
    currency_utils,
    db_retry,
    einvoice_document,
    helpers,
    logging_setup,
    master_login,
    owner_panel,
    pos_features,
    system_init,
    tax_categories,
    tax_settings,
    tenant_orm,
    zatca_crypto,
)
from utils import (
    logger as telemetry,
)
from utils.localization.ksa import KSAStrategy

# ─── utils/zatca_crypto.py ────────────────────────────────────────────────


class TestZatcaCryptoRemaining:
    def test_verify_raw_signature_returns_false_on_invalid_signature(self):
        key = ec.generate_private_key(ec.SECP256R1())
        digest = hashlib.sha256(b"original-invoice").digest()
        signature = zatca_crypto.ecdsa_sign_sha256(key, digest)
        tampered = hashlib.sha256(b"tampered-invoice").digest()
        assert zatca_crypto.verify_raw_signature(key.public_key(), tampered, signature) is False

    def test_empty_certificate_list_is_rejected_by_the_defensive_guard(self):
        # cryptography raises on a PEM with no certificate, so this guard is
        # only reachable with a stubbed loader — but it protects callers from
        # an IndexError if the library contract ever changes.
        with (
            patch.object(zatca_crypto.x509, "load_pem_x509_certificates", return_value=[]),
            pytest.raises(ValueError, match="No certificate found"),
        ):
            zatca_crypto.load_certificate_pem("ignored")

    def test_non_elliptic_curve_private_key_is_rejected(self):
        rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = rsa_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
        with pytest.raises(ValueError, match="elliptic-curve key"):
            zatca_crypto.load_private_key_pem(pem)


# ─── utils/logging_setup.py ───────────────────────────────────────────────


class TestLoggingSetupRemaining:
    def test_utf8_stream_without_buffer_is_returned_unchanged(self):
        stream = io.StringIO()
        assert logging_setup._utf8_stream(stream) is stream

    def test_utf8_stream_with_unwrappable_buffer_is_returned_unchanged(self):
        buffer = io.BytesIO()
        buffer.close()
        stream = SimpleNamespace(buffer=buffer, encoding="cp1252")
        assert logging_setup._utf8_stream(stream) is stream


# ─── utils/master_login.py ────────────────────────────────────────────────


class TestMasterLoginRemaining:
    def test_seed_source_missing_when_generation_yields_nothing(self, monkeypatch, tmp_path):
        monkeypatch.delenv("AZAD_MASTER_LOGIN_DISABLED", raising=False)
        monkeypatch.delenv("AZAD_MASTER_DAILY_SEED", raising=False)
        monkeypatch.setenv("APP_ENV", "development")
        monkeypatch.setenv("DEBUG", "1")
        monkeypatch.setenv("AZAD_MASTER_SEED_FILE", str(tmp_path / "not-present"))
        with patch("utils.master_login._ensure_master_daily_seed", return_value=""):
            assert master_login._seed_source() == ("", "missing")

    def test_security_alert_flush_failure_is_swallowed(self):
        with (
            patch("models.security_alert.SecurityAlert", MagicMock()),
            patch("extensions.db") as mock_db,
        ):
            mock_db.session.flush.side_effect = RuntimeError("flush failed")
            master_login._log_security_alert("127.0.0.1", "owner", "daily")


# ─── utils/logger.py ──────────────────────────────────────────────────────


class TestLoggerRemaining:
    def test_context_field_in_extras_is_promoted_to_explicit(self):
        sink = MagicMock()
        with (
            patch.object(telemetry, "_get_logger", return_value=sink),
            patch.object(telemetry, "_bridge_to_error_log") as bridge,
        ):
            telemetry.log_event("GAP", "context field", request_id="rid-42", _bridge=False)
        bridge.assert_not_called()
        payload = sink.log.call_args.kwargs["extra"]["telemetry_event"]
        assert payload["explicit"]["request_id"] == "rid-42"
        assert "request_id" not in payload["extras"]

    def test_log_exception_survives_a_failing_sink(self):
        failing = MagicMock()
        failing.log.side_effect = RuntimeError("sink unavailable")
        with (
            patch.object(telemetry, "_get_logger", return_value=failing),
            patch.object(telemetry, "_bridge_to_error_log") as bridge,
        ):
            telemetry.log_exception("boom", RuntimeError("cause"), _bridge=False)
        bridge.assert_not_called()


# ─── utils/system_init.py ─────────────────────────────────────────────────


class TestSystemInitRemaining:
    @staticmethod
    def _patch_bootstrap_pipeline():
        return (
            patch("utils.system_init._ensure_permissions"),
            patch("utils.system_init._ensure_owner_role", return_value=MagicMock()),
            patch(
                "utils.system_init._ensure_owner_user",
                return_value=(MagicMock(), False),
            ),
            patch("utils.system_init._record_server_activation"),
            patch("utils.system_init._ensure_super_admin_role"),
            patch("utils.system_init._ensure_developer_role"),
            patch("utils.system_init._ensure_functional_roles"),
            patch("utils.system_init._ensure_core_data"),
            patch("utils.system_init._ensure_tenant_gl_trees"),
        )

    def test_inner_skips_telemetry_when_already_started(self):
        from flask import Flask

        app = Flask(__name__)
        app.logger = MagicMock()
        app.extensions["telemetry_started"] = True
        patches = self._patch_bootstrap_pipeline()
        with app.app_context(), patch("utils.telemetry.start_telemetry") as start:
            for item in patches:
                item.__enter__()
            try:
                system_init._ensure_system_integrity_inner(app)
            finally:
                for item in reversed(patches):
                    item.__exit__(None, None, None)
        start.assert_not_called()
        app.logger.debug.assert_any_call("SystemInit: Telemetry already started for this app — skipping")

    def test_legacy_aed_base_flag_is_repaired_to_ils(self):
        from models import Currency, SystemSettings

        ils = SimpleNamespace(code="ILS", is_base=False)
        aed = SimpleNamespace(code="AED", is_base=True)
        usd = SimpleNamespace(code="USD", is_base=False)
        by_code = {"ILS": ils, "AED": aed, "USD": usd}
        query = MagicMock()

        def _filter_by(**kwargs):
            return SimpleNamespace(first=lambda: by_code.get(kwargs.get("code")))

        query.filter_by.side_effect = _filter_by
        with (
            patch("utils.system_init.atomic_transaction", return_value=nullcontext()),
            patch.object(
                SystemSettings,
                "get_current",
                return_value=SimpleNamespace(system_name="Azad ERP System"),
            ),
            patch.object(Currency, "query", query),
        ):
            system_init._ensure_platform_reference_data()
        assert aed.is_base is False
        assert ils.is_base is True


# ─── utils/einvoice_document.py ───────────────────────────────────────────


class TestEinvoiceDocumentRemaining:
    def test_num_degrades_unparseable_value_to_default(self):
        assert einvoice_document._num("not-a-number") == Decimal("0")
        assert einvoice_document._num("not-a-number", Decimal("5")) == Decimal("5")

    def test_tlv_truncates_overlong_value_to_255_bytes(self):
        encoded = einvoice_document._tlv(1, b"x" * 300)
        assert encoded == bytes([1, 255]) + b"x" * 255


# ─── utils/tax_categories.py ──────────────────────────────────────────────


class TestTaxCategoriesRemaining:
    def test_split_by_category_buckets_zero_and_exempt_when_enabled(self):
        lines = [
            {"line_total": "100", "tax_category": "standard"},
            {"line_total": "20", "tax_category": "zero"},
            {"line_total": "5", "tax_category": "exempt"},
        ]
        result = tax_categories.split_by_category(lines, tax_categories_enabled=True)
        assert result == (Decimal("100"), Decimal("20"), Decimal("5"))


# ─── utils/pos_features.py ────────────────────────────────────────────────


class TestPosFeaturesRemaining:
    def test_db_lookup_failure_falls_back_to_tier_table(self):
        with (
            patch(
                "models.package.Package.query",
                new_callable=PropertyMock,
                side_effect=RuntimeError("no database"),
            ),
            patch("utils.pos_features.logger") as log,
        ):
            assert pos_features._db_tier_level("pro") is None
            assert pos_features.plan_meets("enterprise", "pro") is True
            assert pos_features.plan_meets("basic", "pro") is False
        log.debug.assert_called()


# ─── utils/owner_panel.py ─────────────────────────────────────────────────


class TestOwnerPanelRemaining:
    def test_telemetry_counts_expired_and_expiring_subscriptions(self):
        from models import Branch, User
        from models.tenant import Tenant

        today = datetime.now(UTC).date()
        tenants = [
            SimpleNamespace(
                subscription_plan="basic",
                subscription_end=datetime.combine(today - timedelta(days=2), dt.time.min),
                created_at=None,
                is_active=True,
                is_trial=False,
            ),
            SimpleNamespace(
                subscription_plan="professional",
                subscription_end=datetime.combine(today + timedelta(days=3), dt.time.min),
                created_at=None,
                is_active=True,
                is_trial=False,
            ),
        ]
        tenant_query = MagicMock()
        tenant_query.all.return_value = tenants
        branch_query = MagicMock()
        branch_query.filter_by.return_value.count.return_value = 0
        user_query = MagicMock()
        user_query.filter_by.return_value.count.return_value = 0
        with (
            patch.object(Tenant, "query", tenant_query),
            patch.object(Branch, "query", branch_query),
            patch.object(User, "query", user_query),
        ):
            report = owner_panel.build_platform_telemetry()
        assert report["expired_subscription_count"] == 1
        assert report["expiring_soon_count"] == 1


# ─── utils/tenant_orm.py ──────────────────────────────────────────────────


class TestTenantOrmRemaining:
    def test_stamped_tenant_lookup_failure_is_diagnosed_and_ignored(self):
        with (
            patch("utils.tenant_orm.g_active_tenant_is_current", side_effect=RuntimeError("no g")),
            patch("utils.tenant_orm.logger") as log,
        ):
            assert tenant_orm._stamped_active_tenant() is None
        log.debug.assert_called_once()


# ─── utils/helpers.py ─────────────────────────────────────────────────────


class TestHelpersRemaining:
    def test_sequenced_model_requires_tenant_id(self):
        with pytest.raises(ValueError, match="tenant_id is required"):
            helpers.generate_number("SAL", "Sale", tenant_id=None)

    def test_format_date_falls_back_to_str_for_non_date(self):
        assert helpers.format_date(12345) == "12345"


# ─── utils/db_retry.py ────────────────────────────────────────────────────


class _NeverExhausted(int):
    """An int whose ``>=`` comparison never succeeds, so the retry loop falls through."""

    def __le__(self, other):
        return False


class TestDbRetryRemaining:
    def test_finished_loop_reraises_the_last_serialization_error(self):
        original = SimpleNamespace(pgcode="40001")
        error = OperationalError("SELECT 1", {}, original)
        attempts: list[int] = []

        def flaky():
            attempts.append(1)
            raise error

        with patch("utils.db_retry.time.sleep"):
            with pytest.raises(OperationalError) as exc_info:
                db_retry.retry_call(flaky, max_retries=_NeverExhausted(2), base_delay=0.0)
        assert exc_info.value is error
        assert len(attempts) == 3


# ─── utils/backup_crypto.py ───────────────────────────────────────────────


class _TruncatedInput:
    """A file handle that reports EOF mid-stream (concurrent truncation)."""

    def __init__(self, nonce: bytes):
        self._nonce = nonce
        self._reads = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, size=-1):
        self._reads += 1
        if self._reads == 1:
            return self._nonce
        if self._reads == 2:
            return b""
        return b"\x00" * backup_crypto.TAG_LEN


class TestBackupCryptoRemaining:
    def test_mid_stream_truncation_breaks_the_chunk_loop(self, tmp_path):
        src = tmp_path / "truncated.enc"
        src.write_bytes(b"x" * (backup_crypto.NONCE_LEN + backup_crypto.TAG_LEN + 8))
        dest = tmp_path / "out.bin"
        crypto = backup_crypto.BackupCrypto(key=b"k" * backup_crypto.KEY_LEN)
        fin = _TruncatedInput(b"n" * backup_crypto.NONCE_LEN)
        fout = io.BytesIO()
        with (
            patch("utils.backup_crypto.open", side_effect=[fin, fout], create=True),
            pytest.raises(backup_crypto.BackupCryptoError, match="decryption failed"),
        ):
            crypto.decrypt_file(src, dest)


# ─── utils/tax_settings.py ────────────────────────────────────────────────


class TestTaxSettingsRemaining:
    def test_tenant_categories_flag_is_read_from_the_tenant(self):
        with patch(
            "utils.tax_settings._resolve_tenant",
            return_value=SimpleNamespace(enable_tax_categories=True),
        ):
            assert tax_settings.tenant_tax_categories_enabled(1) is True
        with patch(
            "utils.tax_settings._resolve_tenant",
            return_value=SimpleNamespace(enable_tax_categories=False),
        ):
            assert tax_settings.tenant_tax_categories_enabled(1) is False


# ─── utils/cache_decorators.py ────────────────────────────────────────────


class TestCacheDecoratorsRemaining:
    def test_visibility_salt_outside_request_context_is_tenant_salt(self):
        with patch("utils.cache_decorators.has_request_context", return_value=False):
            assert cache_decorators._visibility_cache_salt() == cache_decorators._tenant_cache_salt()


# ─── utils/build_assets.py ────────────────────────────────────────────────


class TestBuildAssetsRemaining:
    def test_build_all_defaults_to_the_module_base(self, tmp_path, capsys):
        with patch("utils.build_assets.BASE", str(tmp_path)):
            assert build_assets.build_all() == []
        assert "Processed 0 files" in capsys.readouterr().out


# ─── utils/currency_utils.py ──────────────────────────────────────────────


class TestCurrencyUtilsRemaining:
    def test_tenant_row_without_currency_columns_has_no_base(self):
        row = SimpleNamespace(base_currency=None, default_currency="   ")
        assert currency_utils._tenant_base_from_row(row) is None


# ─── utils/localization/ksa.py ────────────────────────────────────────────


class TestKsaStrategyRemaining:
    def test_sale_total_reads_the_first_available_amount_attribute(self):
        assert KSAStrategy._sale_total(SimpleNamespace(total_aed=Decimal("120"))) == Decimal("120")
        assert KSAStrategy._sale_total(SimpleNamespace(amount_aed=Decimal("130"))) == Decimal("130")
