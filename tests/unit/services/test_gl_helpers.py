from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from models import GLAccount, GLPeriod
from services.gl_helpers import (
    assert_period_open,
    get_account,
    next_entry_number,
    resolve_tenant_id,
)


def _mock_tenant_query(mocker, active_count, tenant_id=None):
    mock_tenant = MagicMock()
    mock_tenant.id = tenant_id or 1
    chain = mocker.patch("models.Tenant.query")
    filtered = chain.filter_by.return_value
    filtered.count.return_value = active_count
    filtered.first.return_value = mock_tenant if active_count == 1 else None
    return chain


@pytest.fixture
def gl_account(db_session, sample_tenant):
    acct = GLAccount(
        tenant_id=sample_tenant.id,
        code=f"1{uuid.uuid4().hex[:4]}",
        name="Cash",
        type="asset",
        is_active=True,
    )
    db_session.add(acct)
    db_session.flush()
    return acct


class TestResolveTenantId:
    def test_from_branch_id(self, db_session, sample_branch):
        tid = resolve_tenant_id(branch_id=sample_branch.id)
        assert tid == sample_branch.tenant_id

    def test_from_user_id(self, db_session, sample_user):
        tid = resolve_tenant_id(user_id=sample_user.id)
        assert tid == sample_user.tenant_id

    def test_from_active_tenant_context(self, mocker, sample_tenant):
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=sample_tenant.id)
        assert resolve_tenant_id() == sample_tenant.id

    def test_single_active_tenant_fallback(self, mocker, sample_tenant):
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=None)
        _mock_tenant_query(mocker, 1, sample_tenant.id)
        assert resolve_tenant_id() == sample_tenant.id

    def test_multiple_active_tenants_raises(self, mocker):
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=None)
        _mock_tenant_query(mocker, 2)
        with pytest.raises(ValueError, match="active tenants found"):
            resolve_tenant_id()

    def test_no_active_tenants_raises(self, mocker):
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=None)
        _mock_tenant_query(mocker, 0)
        with pytest.raises(ValueError, match="no active tenants"):
            resolve_tenant_id()

    def test_get_active_tenant_failure_logged(self, mocker, sample_tenant):
        mocker.patch(
            "utils.tenanting.get_active_tenant_id",
            side_effect=RuntimeError("session corrupt"),
        )
        mocker.patch(
            "services.logging_core.LoggingCore.log_error",
            side_effect=RuntimeError("log sink down"),
        )
        _mock_tenant_query(mocker, 1, sample_tenant.id)
        assert resolve_tenant_id() == sample_tenant.id

    def test_database_lookup_failure_raises(self, mocker):
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=None)
        chain = mocker.patch("models.Tenant.query")
        chain.filter_by.return_value.count.side_effect = RuntimeError("db down")
        with pytest.raises(RuntimeError, match="database lookup failed"):
            resolve_tenant_id()

    def test_unresolved_tenant_raises(self, mocker):
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=None)
        mock_t = MagicMock()
        mock_t.id = None
        chain = mocker.patch("models.Tenant.query")
        filtered = chain.filter_by.return_value
        filtered.count.return_value = 1
        filtered.first.return_value = mock_t
        with pytest.raises(ValueError, match="could not determine tenant_id"):
            resolve_tenant_id()

    def test_invalid_branch_returns_via_user(self, db_session, sample_user):
        tid = resolve_tenant_id(branch_id=999999, user_id=sample_user.id)
        assert tid == sample_user.tenant_id


class TestGetAccount:
    def test_with_tenant_id(self, gl_account, sample_tenant):
        found = get_account(gl_account.code, tenant_id=sample_tenant.id)
        assert found.id == gl_account.id

    def test_without_tenant_legacy_fallback(self, gl_account, mocker):
        mocker.patch("services.gl_helpers.resolve_tenant_id", return_value=gl_account.tenant_id)
        found = get_account(gl_account.code)
        assert found is not None

    def test_missing_account(self, sample_tenant):
        assert get_account("NONEXIST", tenant_id=sample_tenant.id) is None


def _mock_journal_query(mocker, latest_entry):
    mock_query = mocker.patch("services.gl_helpers.GLJournalEntry.query")
    end = mock_query.filter.return_value
    end.order_by.return_value.first.return_value = latest_entry
    end.filter.return_value.order_by.return_value.first.return_value = latest_entry
    return mock_query


class TestNextEntryNumber:
    def test_first_entry_of_year(self, mocker, sample_tenant):
        _mock_journal_query(mocker, None)
        num = next_entry_number(sample_tenant.id, entry_date=datetime(2026, 1, 1, tzinfo=timezone.utc))
        assert num == "JE-2026-0001"

    def test_increments_from_latest(self, mocker, sample_tenant):
        latest = MagicMock(entry_number="JE-2025-0005")
        _mock_journal_query(mocker, latest)
        num = next_entry_number(sample_tenant.id, entry_date=datetime(2025, 6, 15, tzinfo=timezone.utc))
        assert num == "JE-2025-0006"

    def test_unparseable_entry_number_defaults(self, mocker, sample_tenant):
        latest = MagicMock(entry_number="CORRUPT")
        _mock_journal_query(mocker, latest)
        num = next_entry_number(sample_tenant.id, entry_date=datetime(2025, 7, 1, tzinfo=timezone.utc))
        assert num == "JE-2025-0001"

    def test_unparseable_entry_logging_core_failure(self, mocker, sample_tenant):
        latest = MagicMock(entry_number="CORRUPT")
        _mock_journal_query(mocker, latest)
        mocker.patch(
            "services.logging_core.LoggingCore.log_error",
            side_effect=RuntimeError("log sink down"),
        )
        num = next_entry_number(sample_tenant.id, entry_date=datetime(2025, 7, 1, tzinfo=timezone.utc))
        assert num == "JE-2025-0001"

    def test_without_tenant_id(self, mocker):
        latest = MagicMock(entry_number="JE-2025-0010")
        _mock_journal_query(mocker, latest)
        num = next_entry_number(None, entry_date=datetime(2025, 8, 1, tzinfo=timezone.utc))
        assert num == "JE-2025-0011"


class TestAssertPeriodOpen:
    def test_open_period_passes(self, sample_tenant):
        assert_period_open(datetime(2025, 6, 15, tzinfo=timezone.utc), sample_tenant.id)

    def test_none_tenant_skips(self):
        assert_period_open(datetime(2025, 6, 15, tzinfo=timezone.utc), None)

    def test_closed_period_raises(self, db_session, sample_tenant):
        period = GLPeriod(
            tenant_id=sample_tenant.id,
            year=2025,
            month=6,
            is_closed=True,
        )
        db_session.add(period)
        db_session.flush()
        with pytest.raises(ValueError, match="2025-06"):
            assert_period_open(datetime(2025, 6, 15, tzinfo=timezone.utc), sample_tenant.id)
