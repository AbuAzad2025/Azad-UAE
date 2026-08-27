"""branch_repair skip-path: no active tenant → skipped_no_tenant result."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import models
from app.runtime.branch_repair import ensure_branch_isolation_schema_and_data


@pytest.fixture
def restore_models():
    names = [
        "Branch",
        "Warehouse",
        "User",
        "Sale",
        "Purchase",
        "Expense",
        "Payment",
        "Receipt",
        "Cheque",
        "GLJournalEntry",
        "Tenant",
    ]
    saved = {n: getattr(models, n) for n in names}
    yield
    for n, v in saved.items():
        setattr(models, n, v)


def test_no_active_tenant_returns_skipped(app, mocker, restore_models):
    mocker.patch("app.runtime.branch_repair._ensure_column", return_value=False)
    mocker.patch("app.runtime.branch_repair._ensure_index")

    Branch = MagicMock()
    Branch.query.filter_by.return_value.order_by.return_value.first.return_value = None
    models.Branch = Branch

    TenantQ = MagicMock()
    TenantQ.query.filter_by.return_value.order_by.return_value.first.return_value = None
    models.Tenant = TenantQ

    result = ensure_branch_isolation_schema_and_data()
    assert result["skipped_no_tenant"] is True
    assert result["main_branch_id"] is None
    assert result["users"] == 0
    assert result["sales"] == 0
