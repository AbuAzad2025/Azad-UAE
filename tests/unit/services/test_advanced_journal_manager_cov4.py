"""Coverage-4 for services/advanced_journal_manager.py — state-machine arcs.

Targets (production lines):
- _transition illegal-transition ValueError (43-47); reversed flag (49-50);
  posted flags validated_at/updated_at (51-54).
- validate_entry wrong-status guard (79-80); balance-error capture (84-88);
  explicit_account_allowed bypass arc (92); error vs validated branches
  (98-104); commit True/False flush arc (114-115).
- create_entry_with_validation unbalanced fast-fail (126-129) + header
  rejection arc (141-142) + draft-status assignment (154-156).
- update_entry wrong-status (182-183) + unbalanced-after-update (187-190)
  + commit True/False flush arcs (206-210).
- post_entry wrong-status (233-236).
- reverse_entry_advanced already-reversed (256-257) + wrong-status (258-259).
- delete_entry posted/reversed guard (325-328) + linked-reversal guard
  (329-330).
- get_entry_history missing-entry arc (375-377).
- _log_audit user_id-None early return (396-397).
- Helper methods: get_balance_status minor/major (445-453),
  can_be_modified/can_be_reversed/can_be_deleted (455-465).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from services.advanced_journal_manager import (
    AdvancedJournalEntryManager,
    add_helper_methods,
)


def _ns_entry(**kwargs):
    base = {
        "status": "draft",
        "is_reversed": False,
        "is_posted": False,
        "validated_at": None,
        "updated_at": None,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


class TestTransition:
    def test_illegal_transition_raises(self):
        entry = _ns_entry(status="posted")
        with pytest.raises(ValueError, match="Illegal journal status transition"):
            AdvancedJournalEntryManager._transition(entry, "draft")

    def test_reversed_sets_flag(self):
        entry = _ns_entry(status="posted")
        AdvancedJournalEntryManager._transition(entry, "reversed")
        assert entry.status == "reversed"
        assert entry.is_reversed is True

    def test_posted_sets_flags_and_timestamps(self):
        entry = _ns_entry(status="validated")
        AdvancedJournalEntryManager._transition(entry, "posted")
        assert entry.is_posted is True
        assert entry.validated_at is not None
        assert entry.updated_at is not None

    def test_posted_keeps_existing_validated_at(self):
        stamp = datetime(2026, 1, 1, tzinfo=UTC)
        entry = _ns_entry(status="validated", validated_at=stamp)
        AdvancedJournalEntryManager._transition(entry, "posted")
        assert entry.validated_at is stamp

    def test_terminal_state_has_no_transitions(self):
        entry = _ns_entry(status="cancelled")
        with pytest.raises(ValueError, match="none"):
            AdvancedJournalEntryManager._transition(entry, "posted")


class TestValidateEntryGuards:
    def test_wrong_status_raises(self, mocker):
        mocker.patch.object(
            AdvancedJournalEntryManager, "_entry_or_404",
            return_value=_ns_entry(status="posted"),
        )
        with pytest.raises(ValueError, match="Cannot validate entry"):
            AdvancedJournalEntryManager.validate_entry(1, validated_by=1)

    def test_balance_error_sets_error_status(self, mocker):
        line = SimpleNamespace(debit=Decimal("10"), credit=Decimal("0"), account=None)
        entry = MagicMock(status="draft", lines=[line], currency="AED", id=1)
        entry.to_dict.return_value = {"id": 1}
        mocker.patch.object(
            AdvancedJournalEntryManager, "_entry_or_404", return_value=entry
        )
        mocker.patch.object(AdvancedJournalEntryManager, "_log_audit")
        mocker.patch("services.gl_posting.assert_balanced_lines", side_effect=ValueError("nope"))
        out = AdvancedJournalEntryManager.validate_entry(1, validated_by=2, commit=True)
        assert out.status == "error"
        assert out.validation_errors is not None

    def test_explicit_account_allowed_bypasses_header(self, mocker):
        account = SimpleNamespace(is_header=True, full_name="HDR Parent")
        line = SimpleNamespace(
            debit=Decimal("5"), credit=Decimal("5"), account=account,
            explicit_account_allowed=True,
        )
        entry = MagicMock(status="draft", lines=[line, line], currency="AED", id=2)
        entry.to_dict.return_value = {"id": 2}
        mocker.patch.object(
            AdvancedJournalEntryManager, "_entry_or_404", return_value=entry
        )
        mocker.patch.object(AdvancedJournalEntryManager, "_log_audit")
        mocker.patch("services.gl_posting.assert_balanced_lines")
        out = AdvancedJournalEntryManager.validate_entry(2, validated_by=2, commit=False)
        assert out.status == "validated"
        assert out.validation_errors is None

    def test_header_without_flag_is_error(self, mocker):
        account = SimpleNamespace(is_header=True, full_name="HDR Parent")
        line = SimpleNamespace(
            debit=Decimal("5"), credit=Decimal("0"), account=account,
            explicit_account_allowed=False,
        )
        other = SimpleNamespace(debit=Decimal("0"), credit=Decimal("5"), account=None)
        entry = MagicMock(status="error", lines=[line, other], currency="AED", id=3)
        entry.to_dict.return_value = {"id": 3}
        mocker.patch.object(
            AdvancedJournalEntryManager, "_entry_or_404", return_value=entry
        )
        mocker.patch.object(AdvancedJournalEntryManager, "_log_audit")
        mocker.patch("services.gl_posting.assert_balanced_lines")
        out = AdvancedJournalEntryManager.validate_entry(3, validated_by=2, commit=False)
        assert out.status == "error"
        assert "Header account used" in out.validation_errors


class TestCreateUpdatePostGuards:
    def test_create_unbalanced_raises(self):
        with pytest.raises(ValueError, match="غير متوازن"):
            AdvancedJournalEntryManager.create_entry_with_validation(
                description="bad",
                lines=[{"debit": 10, "credit": 0}, {"debit": 0, "credit": 1}],
            )

    def test_create_header_account_raises(self, mocker, app):
        with app.app_context():
            account = SimpleNamespace(is_header=True, full_name="HDR X")
            mocker.patch(
                "utils.gl_tenant.get_gl_account_by_code", return_value=account
            )
            with pytest.raises(ValueError, match="الرئيسي"):
                AdvancedJournalEntryManager.create_entry_with_validation(
                    description="hdr",
                    lines=[
                        {"account_code": "1000", "debit": 5, "credit": 0},
                        {"account_code": "4000", "debit": 0, "credit": 5},
                    ],
                    tenant_id=1,
                )

    def test_create_sets_draft_and_audit(self, mocker, app):
        with app.app_context():
            mocker.patch("utils.gl_tenant.get_gl_account_by_code", return_value=None)
            fake = MagicMock(id=7)
            fake.to_dict.return_value = {"id": 7}
            mocker.patch(
                "services.gl_service.GLService.create_manual_entry", return_value=fake
            )
            audit = mocker.patch.object(AdvancedJournalEntryManager, "_log_audit")
            out = AdvancedJournalEntryManager.create_entry_with_validation(
                description="ok",
                lines=[
                    {"account_code": "1000", "debit": 5, "credit": 0},
                    {"account_code": "4000", "debit": 0, "credit": 5},
                ],
                tenant_id=1,
                created_by=3,
            )
            assert out.status == "draft"
            assert out.is_posted is False
            assert audit.called

    def test_update_wrong_status_raises(self, mocker):
        mocker.patch.object(
            AdvancedJournalEntryManager, "_entry_or_404",
            return_value=_ns_entry(status="posted"),
        )
        with pytest.raises(ValueError, match="لا يمكن تعديل"):
            AdvancedJournalEntryManager.update_entry(1, {"description": "x"}, updated_by=1)

    def test_update_unbalanced_raises(self, mocker):
        mocker.patch.object(
            AdvancedJournalEntryManager, "_entry_or_404",
            return_value=_ns_entry(status="draft"),
        )
        with pytest.raises(ValueError, match="غير متوازن بعد التحديث"):
            AdvancedJournalEntryManager.update_entry(
                1,
                {"lines": [{"debit": 3, "credit": 0}]},
                updated_by=1,
            )

    def test_update_ok_both_commit_modes(self, mocker):
        for commit in (True, False):
            entry = MagicMock(status="draft")
            entry.to_dict.side_effect = [{"id": 1}, {"id": 1, "description": "n"}]
            mocker.patch.object(
                AdvancedJournalEntryManager, "_entry_or_404", return_value=entry
            )
            mocker.patch.object(AdvancedJournalEntryManager, "_log_audit")
            out = AdvancedJournalEntryManager.update_entry(
                1, {"description": "n"}, updated_by=1, commit=commit
            )
            assert out.description == "n"

    def test_post_wrong_status_raises(self, mocker):
        mocker.patch.object(
            AdvancedJournalEntryManager, "_entry_or_404",
            return_value=_ns_entry(status="draft"),
        )
        with pytest.raises(ValueError, match="must be validated"):
            AdvancedJournalEntryManager.post_entry(1, posted_by=1)


class TestReverseDeleteHistoryAudit:
    def test_reverse_already_reversed_raises(self, mocker):
        mocker.patch.object(
            AdvancedJournalEntryManager, "_entry_or_404",
            return_value=_ns_entry(status="reversed"),
        )
        with pytest.raises(ValueError, match="معكوس"):
            AdvancedJournalEntryManager.reverse_entry_advanced(1, reversed_by=1, reason="x")

    def test_reverse_wrong_status_raises(self, mocker):
        mocker.patch.object(
            AdvancedJournalEntryManager, "_entry_or_404",
            return_value=_ns_entry(status="draft"),
        )
        with pytest.raises(ValueError, match="لا يمكن عكس"):
            AdvancedJournalEntryManager.reverse_entry_advanced(1, reversed_by=1, reason="x")

    def test_delete_posted_raises(self, mocker):
        mocker.patch.object(
            AdvancedJournalEntryManager, "_entry_or_404",
            return_value=_ns_entry(status="posted", reversed_entry_id=None),
        )
        with pytest.raises(ValueError, match="Cannot delete entry"):
            AdvancedJournalEntryManager.delete_entry(1, deleted_by=1, reason="x")

    def test_delete_reversed_raises(self, mocker):
        mocker.patch.object(
            AdvancedJournalEntryManager, "_entry_or_404",
            return_value=_ns_entry(status="reversed", reversed_entry_id=None),
        )
        with pytest.raises(ValueError, match="Cannot delete entry"):
            AdvancedJournalEntryManager.delete_entry(1, deleted_by=1, reason="x")

    def test_delete_with_linked_reversal_raises(self, mocker):
        mocker.patch.object(
            AdvancedJournalEntryManager, "_entry_or_404",
            return_value=_ns_entry(status="draft", reversed_entry_id=9),
        )
        with pytest.raises(ValueError, match="قيود عكسية"):
            AdvancedJournalEntryManager.delete_entry(1, deleted_by=1, reason="x")

    def test_get_history_missing_returns_empty(self, mocker):
        mocker.patch("utils.gl_tenant.gl_entry_query",
                      return_value=MagicMock(filter_by=MagicMock(
                          return_value=MagicMock(first=MagicMock(return_value=None)))))
        assert AdvancedJournalEntryManager.get_entry_history(999, tenant_id=1) == []

    def test_log_audit_none_user_returns_early(self, mocker):
        add = mocker.patch("services.advanced_journal_manager.db.session.add")
        AdvancedJournalEntryManager._log_audit(1, "post", {"a": 1}, {"a": 2}, "r", None)
        assert not add.called


class TestHelperMethods:
    def test_balance_status_branches(self):
        from models.gl import GLJournalEntry

        add_helper_methods()
        assert GLJournalEntry.get_balance_status(SimpleNamespace(total_debit=100, total_credit=100)) == "balanced"
        assert GLJournalEntry.get_balance_status(SimpleNamespace(total_debit=100, total_credit=105)) == "minor_imbalance"
        assert GLJournalEntry.get_balance_status(SimpleNamespace(total_debit=100, total_credit=200)) == "major_imbalance"

    def test_state_predicates(self):
        from models.gl import GLJournalEntry

        add_helper_methods()
        assert GLJournalEntry.can_be_modified(SimpleNamespace(status="draft")) is True
        assert GLJournalEntry.can_be_modified(SimpleNamespace(status="posted")) is False
        assert GLJournalEntry.can_be_reversed(
            SimpleNamespace(status="posted", is_reversed=False)) is True
        assert GLJournalEntry.can_be_reversed(
            SimpleNamespace(status="draft", is_reversed=False)) is False
        assert GLJournalEntry.can_be_deleted(
            SimpleNamespace(status="draft", reversed_entry_id=None)) is True
        assert GLJournalEntry.can_be_deleted(
            SimpleNamespace(status="draft", reversed_entry_id=5)) is False
