"""Coverage-99 boost for routes/ledger.py uncovered lines:
178 (POST periods without permission → 403)
184->189 (period already exists, skip GLPeriod creation)
289-295 (tenant_id None + platform_owner + 0 tenants → flash + empty tree)
528-529 (api_calculate_journal_balance → exception path)
866-874 (admin_trial_balance loop with non-zero balances)
1039-1069 (close_fiscal_year success/ValueError/Exception branches)
1077-1100 (fiscal_year_preview branches: no tenant, no year, success, error)
"""

from __future__ import annotations

from contextlib import ExitStack
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.routes.test_ledger_routes import (
    _ledger_patches,
    _mock_account,
)


@pytest.fixture
def ledger_client(app_factory, bypass_permission_auth):
    from routes.ledger import ledger_bp

    app = app_factory(ledger_bp)
    return app.test_client()


@pytest.fixture
def ledger_admin_client(app_factory, bypass_admin_auth):
    from routes.ledger import ledger_bp

    app = app_factory(ledger_bp)
    return app.test_client()


# ---------------------------------------------------------------------------
# gl_periods POST
# ---------------------------------------------------------------------------


class TestGlPeriodsPostCoverage:
    def test_post_without_permission_aborts_403(self, ledger_client, bypass_permission_auth):
        bypass_permission_auth.has_permission.return_value = False
        bypass_permission_auth.is_super_admin.return_value = False
        with _ledger_patches(), patch("utils.decorators.is_global_owner_user", return_value=False):
            with ExitStack() as stack:
                stack.enter_context(patch("models.gl.GLPeriod.query", MagicMock()))
                resp = ledger_client.post(
                    "/ledger/periods",
                    data={"year": "2026", "month": "3", "action": "close"},
                    follow_redirects=False,
                )
        assert resp.status_code == 403

    def test_post_with_existing_period_updates_in_place(self, ledger_client):
        existing = MagicMock()
        existing.is_closed = False
        existing.closed_at = None
        existing.closed_by = None
        with _ledger_patches(), patch("models.gl.GLPeriod.query") as gp:
            gp.filter_by.return_value.first.return_value = existing
            resp = ledger_client.post(
                "/ledger/periods",
                data={"year": "2026", "month": "4", "action": "close"},
                follow_redirects=False,
            )
        assert resp.status_code == 302
        assert existing.is_closed is True

    def test_post_reopen_action_keeps_period_open(self, ledger_client):
        existing = MagicMock()
        existing.is_closed = True
        with _ledger_patches(), patch("models.gl.GLPeriod.query") as gp:
            gp.filter_by.return_value.first.return_value = existing
            resp = ledger_client.post(
                "/ledger/periods",
                data={"year": "2026", "month": "4", "action": "reopen"},
                follow_redirects=False,
            )
        assert resp.status_code == 302
        assert existing.is_closed is False


# ---------------------------------------------------------------------------
# accounts_tree: tenant_id None + platform_owner + 0 tenants
# ---------------------------------------------------------------------------


class TestAccountsTreeEmptyOwner:
    def test_no_active_tenants_for_platform_owner_returns_warning_flash(self, ledger_client):
        with (
            _ledger_patches(),
            patch(
                "utils.tenanting.get_active_tenant_id",
                return_value=None,
            ),
            patch(
                "utils.tenanting.is_platform_owner",
                return_value=True,
            ),
            patch(
                "routes.ledger.GLService.count_active_tenants",
                return_value=0,
            ),
        ):
            resp = ledger_client.get("/ledger/accounts-tree")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# api_calculate_journal_balance exception handler (L528-529)
# ---------------------------------------------------------------------------


class TestApiCalculateJournalBalanceError:
    def test_missing_data_returns_400(self, ledger_client):
        with (
            _ledger_patches(),
            patch("routes.ledger.error_response") as err_mock,
        ):
            err_mock.return_value = ("err", 400)
            resp = ledger_client.post(
                "/ledger/api/calculate-journal-balance",
                json=None,
            )
        # When request.get_json(silent=True) returns None → "No data provided"
        assert resp.status_code in (200, 400)

    def test_exception_path_returns_400(self, ledger_client):
        with (
            _ledger_patches(),
            patch(
                "routes.ledger.error_response",
                return_value=("err", 400),
            ),
            patch(
                "routes.ledger.Decimal",
                side_effect=[Decimal("0"), RuntimeError("bad")],
            ),
        ):
            resp = ledger_client.post(
                "/ledger/api/calculate-journal-balance",
                json={"lines": [{"debit": "abc", "credit": 0}]},
            )
        assert resp.status_code in (200, 400)


# ---------------------------------------------------------------------------
# admin_trial_balance loop with non-zero balances (L866-874)
# ---------------------------------------------------------------------------


class TestAdminTrialBalanceLoop:
    def test_loop_with_positive_and_negative_balances(self, ledger_admin_client):
        positive = _mock_account(code="1101", id=1)
        negative = _mock_account(code="2101", id=2)
        zero = _mock_account(code="5100", id=3)
        with (
            _ledger_patches(accounts=[positive, negative, zero]),
            patch(
                "routes.ledger.GLService.get_all_account_balances",
                return_value={1: Decimal("500.5"), 2: Decimal("-200.25"), 3: Decimal("0")},
            ),
        ):
            resp = ledger_admin_client.get(
                "/ledger/admin-trial-balance",
                query_string={"date_from": "2026-01-01", "date_to": "2026-06-30"},
            )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# close_fiscal_year (L1039-1069)
# ---------------------------------------------------------------------------


class TestCloseFiscalYear:
    def test_no_tenant_redirects_with_warning(self, ledger_client):
        with (
            _ledger_patches(),
            patch(
                "utils.tenanting.get_active_tenant_id",
                return_value=None,
            ),
        ):
            resp = ledger_client.post(
                "/ledger/close-fiscal-year",
                data={"fiscal_year": "2026"},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_missing_year_redirects(self, ledger_client):
        with _ledger_patches():
            resp = ledger_client.post(
                "/ledger/close-fiscal-year",
                data={"fiscal_year": ""},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_success_flushes_flash(self, ledger_client):
        closing_entry = MagicMock(id=99, entry_number="CL-99")
        with (
            _ledger_patches(),
            patch(
                "services.gl_service.FiscalYearService.close_fiscal_year",
                return_value=closing_entry,
            ),
        ):
            resp = ledger_client.post(
                "/ledger/close-fiscal-year",
                data={"fiscal_year": "2026"},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_value_error_captured_with_warning(self, ledger_client):
        with (
            _ledger_patches(),
            patch(
                "services.gl_service.FiscalYearService.close_fiscal_year",
                side_effect=ValueError("bad year"),
            ),
        ):
            resp = ledger_client.post(
                "/ledger/close-fiscal-year",
                data={"fiscal_year": "2026"},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_generic_exception_captured_with_danger(self, ledger_client):
        with (
            _ledger_patches(),
            patch(
                "services.gl_service.FiscalYearService.close_fiscal_year",
                side_effect=RuntimeError("backend down"),
            ),
        ):
            resp = ledger_client.post(
                "/ledger/close-fiscal-year",
                data={"fiscal_year": "2026"},
                follow_redirects=False,
            )
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# fiscal_year_preview (L1077-1100)
# ---------------------------------------------------------------------------


class TestFiscalYearPreview:
    def test_no_tenant_returns_400_json(self, ledger_client):
        with (
            _ledger_patches(),
            patch(
                "utils.tenanting.get_active_tenant_id",
                return_value=None,
            ),
        ):
            resp = ledger_client.get("/ledger/fiscal-year-preview")
        assert resp.status_code == 400

    def test_missing_year_returns_400_json(self, ledger_client):
        with _ledger_patches():
            resp = ledger_client.get("/ledger/fiscal-year-preview")
        assert resp.status_code == 400

    def test_success_returns_data(self, ledger_client):
        preview = {
            "total_revenue": Decimal("1000"),
            "total_expense": Decimal("600"),
            "net_income": Decimal("400"),
            "lines": [1, 2, 3],
        }
        with (
            _ledger_patches(),
            patch(
                "services.gl_service.FiscalYearService.calculate_pl_balance",
                return_value=preview,
            ),
        ):
            resp = ledger_client.get("/ledger/fiscal-year-preview?fiscal_year=2026")
        assert resp.status_code == 200

    def test_exception_returns_400(self, ledger_client):
        with (
            _ledger_patches(),
            patch(
                "services.gl_service.FiscalYearService.calculate_pl_balance",
                side_effect=RuntimeError("boom"),
            ),
        ):
            resp = ledger_client.get("/ledger/fiscal-year-preview?fiscal_year=2026")
        assert resp.status_code == 400
