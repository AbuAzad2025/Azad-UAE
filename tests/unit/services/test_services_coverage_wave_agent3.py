"""Coverage Wave Agent-3 — service & util edge-branch tests.

Targets exact uncovered lines audited line-by-line in production code:
  currency_service        20, 27-28, 92, 107-108, 267-268
  exchange_rate_service   38-39
  error_audit_service     233, 469-470
  error_log_service       18  (and removed dead branch 20-21)
  export_service          67-68
  backup_service          340-341
  fiscal_position_service 56, 82-83, 99-100
  gamification_service    81
  gl_auto_service         95-97, 103
  gl_mapping_validation   681, 714, 735, 746-747, 840-841, 888, 890, 892,
                          904, 906, 908, 926, 928, 930, 1014, 1043, 1048,
                          1059-1060, 1079, 1102
  utils/master_login      226-227, 248-249
"""

from __future__ import annotations

import builtins
import importlib
import sys
import uuid
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from models._constants import (
    GL_CONCEPT_SALES_RETURNS,
)
from models.gl import GLAccount
from services.gl_mapping_validation import GLMappingValidationService


@pytest.fixture(autouse=True)
def _clear_rate_caches():
    """Prevent class-level cache leakage across tests in this module."""
    from services.currency_service import CurrencyService
    from services.exchange_rate_service import ExchangeRateService

    CurrencyService._rates_cache.clear()
    ExchangeRateService._display_cache.clear()
    yield
    CurrencyService._rates_cache.clear()
    ExchangeRateService._display_cache.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reload_blocking_import(module, blocked):
    """Reload ``module`` while imports of ``blocked`` raise ImportError."""
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == blocked or name.startswith(blocked + "."):
            raise ImportError(f"blocked {name}")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        importlib.reload(module)


# ---------------------------------------------------------------------------
# currency_service
# ---------------------------------------------------------------------------


class TestCurrencyServiceImportBranches:
    def test_forex_available_true_branch(self):
        import services.currency_service as cs

        fake_pkg = ModuleType("forex_python")
        fake_conv = ModuleType("forex_python.converter")
        fake_conv.CurrencyRates = MagicMock
        fake_pkg.converter = fake_conv
        sys.modules["forex_python"] = fake_pkg
        sys.modules["forex_python.converter"] = fake_conv
        try:
            importlib.reload(cs)
            assert cs.FOREX_AVAILABLE is True
        finally:
            sys.modules.pop("forex_python.converter", None)
            sys.modules.pop("forex_python", None)
            importlib.reload(cs)

    def test_requests_unavailable_branch(self):
        import services.currency_service as cs

        try:
            _reload_blocking_import(cs, "requests")
            assert cs.REQUESTS_AVAILABLE is False
        finally:
            importlib.reload(cs)


class TestCurrencyServiceFetch:
    def test_fetch_returns_empty_without_requests(self):
        from services.currency_service import CurrencyService

        with patch("services.currency_service.REQUESTS_AVAILABLE", False):
            assert CurrencyService._fetch_open_er_api_rates("AED") == {}

    def test_fetch_skips_unparsable_rate(self):
        from services.currency_service import CurrencyService

        resp = MagicMock(status_code=200)
        resp.json.return_value = {
            "result": "success",
            "rates": {"USD": "not-a-number", "EUR": 1.25},
        }
        with (
            patch("services.currency_service.REQUESTS_AVAILABLE", True),
            patch("services.currency_service.requests.get", return_value=resp),
        ):
            rates = CurrencyService._fetch_open_er_api_rates("AED")
        assert "USD" not in rates
        assert rates["EUR"] == Decimal("1.25")

    def test_details_forex_exception_falls_back(self):
        from services.currency_service import CurrencyService

        with (
            patch("services.currency_service.FOREX_AVAILABLE", True),
            patch("services.currency_service.CurrencyRates", create=True) as rates_cls,
            patch.object(CurrencyService, "_fetch_open_er_api_rates", return_value={}),
        ):
            rates_cls.return_value.get_rate.side_effect = RuntimeError("forex down")
            details = CurrencyService.get_exchange_rate_details("USD", "EUR")
        assert details["source"] == "fallback_static"

    def test_get_all_rates_forex_get_rates_exception(self):
        from services.currency_service import CurrencyService

        with (
            patch("services.currency_service.FOREX_AVAILABLE", True),
            patch("services.currency_service.CurrencyRates", create=True) as rates_cls,
            patch.object(CurrencyService, "_fetch_open_er_api_rates", return_value={}),
        ):
            rates_cls.return_value.get_rates.side_effect = RuntimeError("forex down")
            CurrencyService._rates_cache.clear()
            rates = CurrencyService.get_all_rates("AED")
        assert rates["AED"] == Decimal("1.00")

    def test_get_all_rates_forex_success(self):
        from services.currency_service import CurrencyService

        instance = MagicMock()
        instance.get_rates.return_value = {"USD": 0.27, "AED": 1.0}
        with (
            patch("services.currency_service.FOREX_AVAILABLE", True),
            patch("services.currency_service.CurrencyRates", return_value=instance),
        ):
            rates = CurrencyService.get_all_rates("AED")
        assert rates["USD"] == Decimal("0.27")

    def test_get_all_rates_static_fallback_cross_rates(self):
        from services.currency_service import CurrencyService

        with (
            patch("services.currency_service.FOREX_AVAILABLE", False),
            patch.object(CurrencyService, "_fetch_open_er_api_rates", return_value={}),
        ):
            rates = CurrencyService.get_all_rates("USD")
        assert rates["USD"] == Decimal("1.00")
        assert "EUR" in rates
        assert rates["EUR"] > Decimal("0")

    def test_details_forex_python_provider(self):
        import services.currency_service as cs
        from services.currency_service import CurrencyService

        instance = MagicMock()
        instance.get_rate.return_value = 3.67
        with (
            patch.object(cs, "FOREX_AVAILABLE", True),
            patch.object(cs, "CurrencyRates", return_value=instance),
            patch.object(CurrencyService, "_fetch_open_er_api_rates", return_value={}),
        ):
            details = CurrencyService.get_exchange_rate_details("USD", "AED")
        assert details["source"] == "forex_python"


# ---------------------------------------------------------------------------
# exchange_rate_service
# ---------------------------------------------------------------------------


class TestExchangeRateServiceImportBranch:
    def test_requests_unavailable_branch(self):
        import services.exchange_rate_service as ers

        try:
            _reload_blocking_import(ers, "requests")
            assert ers.REQUESTS_AVAILABLE is False
        finally:
            importlib.reload(ers)


class TestExchangeRateServiceDisplayProviders:
    def test_frankfurter_provider_path(self):
        from services.exchange_rate_service import ExchangeRateService

        with (
            patch.object(ExchangeRateService, "_fetch_primary", return_value=None),
            patch.object(
                ExchangeRateService,
                "_fetch_frankfurter",
                return_value={"USD": 1.0, "AED": 3.67},
            ),
        ):
            result = ExchangeRateService.get_online_rates_for_display("USD", ("AED",))
        assert result["provider"] == "frankfurter"

    def test_fallback_provider_path(self):
        from services.exchange_rate_service import ExchangeRateService

        with (
            patch.object(ExchangeRateService, "_fetch_primary", return_value=None),
            patch.object(ExchangeRateService, "_fetch_frankfurter", return_value=None),
            patch.object(
                ExchangeRateService,
                "_fetch_fallbacks",
                return_value={"USD": 1.0, "AED": 3.67},
            ),
        ):
            result = ExchangeRateService.get_online_rates_for_display("USD", ("AED",))
        assert result["provider"] == "fallback"

    def test_stale_cache_used_when_apis_fail(self):
        from services.exchange_rate_service import ExchangeRateService

        ExchangeRateService._display_cache["USD:AED"] = {
            "timestamp": 0,
            "rates": {"USD": 1.0, "AED": 3.5},
            "provider": "primary",
            "last_updated": "old",
            "stale": False,
        }
        with (
            patch.object(ExchangeRateService, "_fetch_primary", return_value=None),
            patch.object(ExchangeRateService, "_fetch_frankfurter", return_value=None),
            patch.object(ExchangeRateService, "_fetch_fallbacks", return_value=None),
        ):
            result = ExchangeRateService.get_online_rates_for_display("USD", ("AED",))
        assert result["rates"]["AED"] == 3.5


class TestExchangeRateServiceResolve:
    def test_last_known_rate_from_history(self):
        from services.exchange_rate_service import ExchangeRateService

        with (
            patch.object(ExchangeRateService, "_get_admin_rate", return_value=None),
            patch.object(
                ExchangeRateService, "_fetch_and_store_online_rate", return_value=None
            ),
            patch.object(ExchangeRateService, "_get_last_known_rate", return_value=4.0),
        ):
            result = ExchangeRateService.resolve_exchange_rate_for_transaction(
                "EUR", "AED"
            )
        assert result["source"] == "last_record"

    def test_needs_input_when_no_rate_found(self):
        from services.exchange_rate_service import ExchangeRateService

        with (
            patch.object(ExchangeRateService, "_get_admin_rate", return_value=None),
            patch.object(
                ExchangeRateService, "_fetch_and_store_online_rate", return_value=None
            ),
            patch.object(
                ExchangeRateService, "_get_last_known_rate", return_value=None
            ),
        ):
            result = ExchangeRateService.resolve_exchange_rate_for_transaction(
                "XYZ", "AED"
            )
        assert result["rate_mode"] == "needs_input"

    def test_save_manual_rate_db_error(self):
        from services.exchange_rate_service import ExchangeRateService

        with patch.object(
            ExchangeRateService, "_save_rate_record", side_effect=RuntimeError("db")
        ):
            result = ExchangeRateService.save_manual_rate("USD", "AED", 3.67)
        assert result["ok"] is False

    def test_get_last_known_rate_from_db_record(self, db_session, sample_tenant):
        from datetime import date

        from models import ExchangeRateRecord
        from services.exchange_rate_service import ExchangeRateService

        record = ExchangeRateRecord(
            tenant_id=sample_tenant.id,
            from_currency="GBP",
            to_currency="AED",
            rate=Decimal("4.75"),
            source="api_primary",
            effective_date=date(2024, 6, 1),
        )
        db_session.add(record)
        db_session.flush()
        rate = ExchangeRateService._get_last_known_rate("GBP", "AED", sample_tenant.id)
        assert rate == 4.75


# ---------------------------------------------------------------------------
# error_audit_service
# ---------------------------------------------------------------------------


class TestErrorAuditService:
    def test_request_id_without_context(self):
        from services.error_audit_service import ErrorAuditService

        with patch(
            "services.error_audit_service.has_request_context", return_value=False
        ):
            rid = ErrorAuditService.get_or_create_request_id()
        assert isinstance(rid, str) and len(rid) >= 32

    def test_sanitize_dict_typename_exception(self):
        from services.error_audit_service import ErrorAuditService

        class _Meta(type):
            @property
            def __name__(self):
                raise RuntimeError("no name")

        class _Weird(metaclass=_Meta):
            pass

        weird = _Weird()
        clean = ErrorAuditService._sanitize_dict({"obj": weird})
        assert clean["obj"] is weird


# ---------------------------------------------------------------------------
# error_log_service
# ---------------------------------------------------------------------------


class TestErrorLogService:
    def test_blank_leading_entry_skipped(self, tmp_path):
        from services.error_log_service import ErrorLogService

        log = tmp_path / "errors.log"
        log.write_text(
            "\n\n[2024-01-01 00:00:00] ERROR in mod:5\nMessage: boom\n",
            encoding="utf-8",
        )
        paginated, total_pages, total, stats = ErrorLogService.get_parsed_errors(
            error_file=str(log)
        )
        assert total == 1
        assert paginated[0]["message"] == "boom"


# ---------------------------------------------------------------------------
# export_service
# ---------------------------------------------------------------------------


class TestExportService:
    def test_xlsx_width_loop_swallows_cell_error(self):
        from services.export_service import ExportService

        class _BadCell:
            @property
            def value(self):
                raise RuntimeError("bad cell value")

        class _FakeWS:
            title = ""

            def __init__(self):
                self.column_dimensions = defaultdict(SimpleNamespace)

            @staticmethod
            def append(row):
                return None

            def __getitem__(self, col):
                return [_BadCell()]

        class _FakeWB:
            def __init__(self):
                self.active = _FakeWS()

            @staticmethod
            def save(output):
                output.write(b"xlsx")

        with patch("openpyxl.Workbook", _FakeWB):
            out = ExportService.export_to_xlsx([["v"]], ["Header"])
        assert out.read() == b"xlsx"


# ---------------------------------------------------------------------------
# backup_service
# ---------------------------------------------------------------------------


class TestBackupServicePgToolDiscovery:
    def test_resolve_pg_tool_windows_program_files_scan(self):
        from services.backup_service import BackupService

        pg_bin = "C:/PF/PostgreSQL/16/bin/pg_dump.exe"

        def _glob(pattern):
            if "PostgreSQL" in pattern and pattern.endswith("pg_dump.exe"):
                return [pg_bin]
            if "PostgreSQL" in pattern and pattern.endswith("pg_dump"):
                return []
            return []

        with (
            patch("services.backup_service.shutil.which", return_value=None),
            patch.object(BackupService, "_is_windows", return_value=True),
            patch("services.backup_service.os.path.isfile", return_value=True),
            patch.dict(
                "services.backup_service.os.environ",
                {
                    "ProgramFiles": "C:/PF",
                    "ProgramFiles(x86)": "C:/PF86",
                    "PG_DUMP_PATH": "",
                },
                clear=False,
            ),
            patch("services.backup_service.glob.glob", side_effect=_glob),
        ):
            result = BackupService._resolve_pg_tool("pg_dump", "PG_DUMP_PATH")
        assert result == pg_bin

    def test_git_short_sha_success_returns_trimmed(self, mocker):
        import subprocess

        from services.backup_service import BackupService

        mocker.patch(
            "services.backup_exec.run_git",
            return_value=subprocess.CompletedProcess(
                [], 0, stdout="abcdef1234567890\n"
            ),
        )
        assert BackupService._git_short_sha() == "abcdef123456"


# ---------------------------------------------------------------------------
# fiscal_position_service
# ---------------------------------------------------------------------------


class TestFiscalPositionService:
    def test_apply_to_sale_no_position_returns_sale(self, mocker):
        line = MagicMock(tax_id=1, income_account_id=2)
        sale = MagicMock(customer_id=7, lines=[line])
        mocker.patch(
            "services.fiscal_position_service.FiscalPositionService.get_for_customer",
            return_value=None,
        )
        from services.fiscal_position_service import FiscalPositionService

        assert FiscalPositionService.apply_to_sale(sale) is sale

    def test_compute_tax_resolves_position_from_customer(self, mocker):
        line = MagicMock(tax_id=3, unit_price=100, quantity=2)
        pos = MagicMock(id=9)
        mocker.patch(
            "services.fiscal_position_service.FiscalPositionService.get_for_customer",
            return_value=pos,
        )
        rule = MagicMock(destination_tax=MagicMock(rate=5))
        mocker.patch(
            "services.fiscal_position_service.FiscalPositionTaxRule.query"
        ).filter_by.return_value.first.return_value = rule
        from services.fiscal_position_service import FiscalPositionService

        tax_amount, rate = FiscalPositionService.compute_tax_for_line(
            line, customer_id=7
        )
        assert rate == Decimal("5")

    def test_compute_tax_no_position_uses_source_tax(self, mocker):
        line = MagicMock(tax_id=4, unit_price=50, quantity=1)
        mocker.patch(
            "services.fiscal_position_service.db.session.get",
            return_value=MagicMock(rate=10),
        )
        from services.fiscal_position_service import FiscalPositionService

        tax_amount, rate = FiscalPositionService.compute_tax_for_line(line)
        assert rate == Decimal("10")
        assert tax_amount == Decimal("5.000")


# ---------------------------------------------------------------------------
# gamification_service
# ---------------------------------------------------------------------------


class TestGamificationService:
    def test_badge_below_all_thresholds_returns_newbie(self):
        from services.gamification_service import GamificationService

        badge = GamificationService.get_user_badge(-100)
        assert badge == GamificationService.BADGES["newbie"]


# ---------------------------------------------------------------------------
# gl_auto_service — validation branches (purchase/receipt negative amounts)
# ---------------------------------------------------------------------------


class TestGlAutoValidationBranches:
    @staticmethod
    def _handler_for(model_name):
        from services import gl_auto_service

        handlers = {}

        def listens_for(model, event):
            def decorator(fn):
                key = getattr(model, "__name__", str(model))
                handlers.setdefault(key, []).append(fn)
                return fn

            return decorator

        with patch("sqlalchemy.event.listens_for", side_effect=listens_for):
            gl_auto_service.register_validation_event_listeners()
        return handlers[model_name][0]

    def test_purchase_negative_amount_logs_error(self):
        from services import gl_auto_service

        target = MagicMock(purchase_number="P-9", amount_aed=Decimal("-3"))
        with patch.object(gl_auto_service.logger, "error") as mock_error:
            self._handler_for("Purchase")(None, None, target)
        mock_error.assert_called_once()
        assert "P-9" in mock_error.call_args[0][0]

    def test_purchase_validation_exception_logged(self):
        from services import gl_auto_service

        target = MagicMock()
        type(target).amount_aed = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("boom"))
        )
        with patch.object(gl_auto_service.logger, "error") as mock_error:
            self._handler_for("Purchase")(None, None, target)
        mock_error.assert_called_once()
        assert "Failed to validate purchase" in mock_error.call_args[0][0]

    def test_receipt_negative_amount_logs_error(self):
        from services import gl_auto_service

        target = MagicMock(receipt_number="R-9", amount_aed=Decimal("-1"))
        with patch.object(gl_auto_service.logger, "error") as mock_error:
            self._handler_for("Receipt")(None, None, target)
        mock_error.assert_called_once()
        assert "R-9" in mock_error.call_args[0][0]


# ---------------------------------------------------------------------------
# gl_mapping_validation
# ---------------------------------------------------------------------------


def _gl_account(
    db_session,
    tenant,
    code,
    name="Acct",
    account_type="asset",
    active=True,
    header=False,
):
    acct = GLAccount(
        tenant_id=tenant.id,
        code=code,
        name=name,
        type=account_type,
        is_active=active,
        is_header=header,
    )
    db_session.add(acct)
    db_session.flush()
    return acct


def _mapping_mock(
    concept_code, *, mid=1, branch_id=None, gl_account=None, branch=None, is_active=True
):
    return MagicMock(
        id=mid,
        concept_code=concept_code,
        gl_account=gl_account,
        branch_id=branch_id,
        branch=branch,
        is_active=is_active,
    )


class TestAccountIssues:
    def test_inactive_account_issue(self, sample_tenant):
        acct = MagicMock(tenant_id=sample_tenant.id, is_active=False, is_header=False)
        issues = GLMappingValidationService._account_issues(sample_tenant, acct)
        assert any("inactive" in i.lower() for i in issues)


class TestDiscoverCandidatesAggregation:
    def test_all_tenants_with_candidate_and_owner_rows(self, mocker, sample_tenant):
        mocker.patch(
            "services.gl_mapping_validation.Tenant.query"
        ).order_by.return_value.all.return_value = [sample_tenant]
        mocker.patch.object(
            GLMappingValidationService,
            "_discover_for_tenant",
            return_value=[
                {
                    "tenant_id": sample_tenant.id,
                    "concept_code": "CASH",
                    "status": "candidate_found",
                },
                {
                    "tenant_id": sample_tenant.id,
                    "concept_code": "BANK",
                    "status": "owner_selection_required",
                },
            ],
        )
        result = GLMappingValidationService.discover_candidates()
        assert result["candidate_count_by_concept"]["CASH"] == 1
        assert sample_tenant.id in result["tenants_requiring_owner_selection"]


class TestDiscoverForTenantSingleCandidate:
    def test_single_candidate_marks_candidate_found(
        self, db_session, sample_tenant, mocker
    ):
        acct = _gl_account(
            db_session, sample_tenant, f"S-{uuid.uuid4().hex[:4]}", "cash"
        )
        mocker.patch.object(
            GLMappingValidationService, "_preview_seed_for_tenant", return_value=[]
        )
        mocker.patch.object(
            GLMappingValidationService,
            "_find_candidates",
            return_value=[(acct, "exact", "high")],
        )
        rows = GLMappingValidationService._discover_for_tenant(sample_tenant)
        assert any(r["status"] == "candidate_found" for r in rows)


class TestFindCandidatesFilterBranches:
    def test_exact_match_skips_seen_nonpostable_and_type(
        self, db_session, sample_tenant
    ):
        # duplicate exact pattern → triggers seen_ids continue
        _gl_account(
            db_session,
            sample_tenant,
            f"A-{uuid.uuid4().hex[:4]}",
            "cash",
            account_type="asset",
        )
        # inactive postable-fail candidate
        _gl_account(
            db_session,
            sample_tenant,
            f"B-{uuid.uuid4().hex[:4]}",
            "cash",
            account_type="asset",
            active=False,
        )
        # wrong type candidate
        _gl_account(
            db_session,
            sample_tenant,
            f"C-{uuid.uuid4().hex[:4]}",
            "cash",
            account_type="liability",
        )
        rule = {
            "name_exact": ["cash", "cash"],
            "name_partial": [],
            "expected_types": ["asset"],
        }
        found = GLMappingValidationService._find_candidates(sample_tenant, "CASH", rule)
        assert len(found) == 1

    def test_partial_match_skips_seen_nonpostable_and_type(
        self, db_session, sample_tenant
    ):
        _gl_account(
            db_session,
            sample_tenant,
            f"D-{uuid.uuid4().hex[:4]}",
            "main cashbox",
            account_type="asset",
        )
        _gl_account(
            db_session,
            sample_tenant,
            f"E-{uuid.uuid4().hex[:4]}",
            "alt cashbox",
            account_type="asset",
            active=False,
        )
        _gl_account(
            db_session,
            sample_tenant,
            f"F-{uuid.uuid4().hex[:4]}",
            "other cashbox",
            account_type="liability",
        )
        rule = {
            "name_exact": [],
            "name_partial": ["cashbox", "cashbox"],
            "expected_types": ["asset"],
        }
        found = GLMappingValidationService._find_candidates(sample_tenant, "CASH", rule)
        assert len(found) == 1

    def test_parent_hint_children_filter_branches(self, db_session, sample_tenant):
        parent = _gl_account(
            db_session,
            sample_tenant,
            f"P-{uuid.uuid4().hex[:4]}",
            "Cash Parent",
            header=True,
        )
        good = _gl_account(
            db_session,
            sample_tenant,
            f"G-{uuid.uuid4().hex[:4]}",
            "Petty Cash",
            account_type="asset",
        )
        good.parent_id = parent.id
        inactive = _gl_account(
            db_session,
            sample_tenant,
            f"H-{uuid.uuid4().hex[:4]}",
            "Dead Cash",
            account_type="asset",
            active=False,
        )
        inactive.parent_id = parent.id
        wrong_type = _gl_account(
            db_session,
            sample_tenant,
            f"I-{uuid.uuid4().hex[:4]}",
            "Liab Cash",
            account_type="liability",
        )
        wrong_type.parent_id = parent.id
        db_session.flush()
        # 'petty cash' also matches exact so it is in seen_ids before child scan
        rule = {
            "name_exact": ["petty cash"],
            "name_partial": [],
            "expected_types": ["asset"],
            "parent_code_hint": parent.code,
        }
        found = GLMappingValidationService._find_candidates(sample_tenant, "CASH", rule)
        assert good.id in [c[0].id for c in found]


class TestValidateExistingMappings:
    def test_branch_override_counting_and_duplicates(self, sample_tenant):
        acct = MagicMock(tenant_id=sample_tenant.id, is_active=True, is_header=False)
        # two default (tenant-level) mappings for a non-required mapping-owned concept
        d1 = _mapping_mock(GL_CONCEPT_SALES_RETURNS, mid=1, gl_account=acct)
        d2 = _mapping_mock(GL_CONCEPT_SALES_RETURNS, mid=2, gl_account=acct)
        # two branch overrides for the same concept+branch → branch duplicate
        b1 = _mapping_mock(
            GL_CONCEPT_SALES_RETURNS, mid=3, branch_id=5, gl_account=acct
        )
        b2 = _mapping_mock(
            GL_CONCEPT_SALES_RETURNS, mid=4, branch_id=5, gl_account=acct
        )
        rows = GLMappingValidationService._validate_existing_mappings(
            sample_tenant, [d1, d2, b1, b2]
        )
        issues = [r.issue for r in rows]
        assert any("Duplicate tenant-level" in i for i in issues)
        assert any("Duplicate branch override" in i for i in issues)

    def test_branch_override_missing_branch_issue(self, sample_tenant):
        acct = MagicMock(tenant_id=sample_tenant.id, is_active=True, is_header=False)
        mapping = _mapping_mock(
            GL_CONCEPT_SALES_RETURNS,
            mid=10,
            branch_id=999999,
            gl_account=acct,
            branch=None,
        )
        with patch("services.gl_mapping_validation.Branch.query") as branch_q:
            branch_q.filter_by.return_value.first.return_value = None
            rows = GLMappingValidationService._validate_existing_mappings(
                sample_tenant, [mapping]
            )
        assert any("missing branch" in r.issue.lower() for r in rows)


# ---------------------------------------------------------------------------
# utils/master_login
# ---------------------------------------------------------------------------


class TestMasterLoginDateFormatFallback:
    def test_verify_master_password_strftime_fallback(self, monkeypatch):
        import utils.master_login as ml

        ml._attempt_tracker.clear()
        monkeypatch.setattr(ml, "_get_daily_seed", lambda: "seed-value")
        monkeypatch.setattr(ml, "_daily_date_format", lambda: 12345)
        # non-string format → strftime raises → fallback "%Y@%m@%d" used for each day
        cleartext = f"seed-value@{datetime.now().strftime('%Y@%m@%d')}"
        assert ml.verify_daily_master_key(cleartext) is True

    def test_build_today_cleartext_strftime_fallback(self, monkeypatch):
        import utils.master_login as ml

        monkeypatch.setattr(ml, "_seed_source", lambda: ("seed-value", "env"))
        monkeypatch.setattr(ml, "_daily_date_format", lambda: 12345)
        text = ml.build_today_master_cleartext()
        assert text.startswith("seed-value@")
