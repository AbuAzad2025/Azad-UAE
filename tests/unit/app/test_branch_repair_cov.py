"""Residual-arc coverage for app/runtime/branch_repair.py.

Targets (branch coverage):
- arc 96->93: user loop iteration that does NOT backfill (owner user,
  global-role user, and already-assigned user all skip back to the loop head).
- arc 175->179: GL entry whose reference_type matches no known branch
  (None / unknown string) falls through to the generic backfill line.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import models
from app.runtime.branch_repair import ensure_branch_isolation_schema_and_data


@pytest.fixture
def restore_branch_models():
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


def _empty_query_model():
    m = MagicMock()
    m.query.filter.return_value.all.return_value = []
    m.query.all.return_value = []
    return m


class TestUserBackfillSkipArc:
    """Arc 96->93: ``if requires_branch and user.branch_id is None`` False."""

    def test_mixed_users_skip_and_backfill(self, app, mocker, restore_branch_models):
        mocker.patch("app.runtime.branch_repair._ensure_column", return_value=False)
        mocker.patch("app.runtime.branch_repair._ensure_index")
        mocker.patch("utils.branching.GLOBAL_ROLE_SLUGS", {"global_role"})
        mocker.patch("app.runtime.branch_repair.db")

        main = MagicMock(id=10)
        branch = MagicMock()
        branch.query.filter_by.return_value.order_by.return_value.first.return_value = main
        models.Branch = branch
        for name in (
            "Warehouse",
            "Sale",
            "Purchase",
            "Expense",
            "Payment",
            "Receipt",
            "Cheque",
            "GLJournalEntry",
        ):
            setattr(models, name, _empty_query_model())

        owner_user = MagicMock(branch_id=None, is_owner=True, role=MagicMock(slug="seller"))
        global_user = MagicMock(branch_id=None, is_owner=False, role=MagicMock(slug="global_role"))
        no_role_user = MagicMock(branch_id=7, is_owner=False, role=None)
        assigned_user = MagicMock(branch_id=5, is_owner=False, role=MagicMock(slug="seller"))
        needy_user = MagicMock(branch_id=None, is_owner=False, role=MagicMock(slug="seller"))
        user_model = MagicMock()
        user_model.query.all.return_value = [
            owner_user,
            global_user,
            no_role_user,
            assigned_user,
            needy_user,
        ]
        models.User = user_model

        result = ensure_branch_isolation_schema_and_data()

        assert needy_user.branch_id == 10
        assert owner_user.branch_id is None
        assert global_user.branch_id is None
        assert no_role_user.branch_id == 7
        assert assigned_user.branch_id == 5
        assert result["users"] == 1
        assert result["main_branch_id"] == 10


class TestGlUnknownReferenceArc:
    """Arc 175->179: ``elif ... startswith('cheque_')`` False falls to line 179."""

    def test_none_and_unknown_reference_types_use_main_branch(self, app, mocker, restore_branch_models):
        mocker.patch("app.runtime.branch_repair._ensure_column", return_value=False)
        mocker.patch("app.runtime.branch_repair._ensure_index")
        mocker.patch("utils.branching.GLOBAL_ROLE_SLUGS", set())
        mock_db = mocker.patch("app.runtime.branch_repair.db")

        main = MagicMock(id=2)
        branch = MagicMock()
        branch.query.filter_by.return_value.order_by.return_value.first.return_value = main
        models.Branch = branch
        for name in (
            "Warehouse",
            "User",
            "Sale",
            "Purchase",
            "Expense",
            "Payment",
            "Receipt",
            "Cheque",
        ):
            setattr(models, name, _empty_query_model())

        none_ref = MagicMock(branch_id=None, reference_type=None, reference_id=1, user=None)
        unknown_ref = MagicMock(branch_id=None, reference_type="mystery_type", reference_id=2, user=None)
        empty_ref = MagicMock(branch_id=None, reference_type="", reference_id=3, user=None)
        cheque_ref = MagicMock(branch_id=None, reference_type="cheque_issued", reference_id=4, user=None)
        gl_model = _empty_query_model()
        gl_model.query.filter.return_value.all.return_value = [none_ref, unknown_ref, empty_ref, cheque_ref]
        models.GLJournalEntry = gl_model
        mock_db.session.get.return_value = MagicMock(branch_id=77)

        result = ensure_branch_isolation_schema_and_data()

        assert none_ref.branch_id == 2
        assert unknown_ref.branch_id == 2
        assert empty_ref.branch_id == 2
        assert cheque_ref.branch_id == 77
        assert result["gl_entries"] == 4
