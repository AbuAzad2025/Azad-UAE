"""Targeted regressions for the GL authority / posting remediation batch."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from werkzeug.exceptions import NotFound

from services.advanced_journal_manager import AdvancedJournalEntryManager
from services.gl_account_resolver import GLMappingError
from services.gl_posting import GlPostingError, post_or_fail
from utils.field_validators import FieldValidationError, validate_gl_line_sides


class TestTypedPostingFailures:
    def test_mapping_error_is_not_collapsed(self):
        lines = [{"account": "1110", "debit": 1, "credit": 0}, {"account": "4100", "debit": 0, "credit": 1}]
        failure = GLMappingError(tenant_id=1, concept_code="AR", branch_id=None, issue="no mapping")
        with (
            patch("services.gl_service.GLService.create_journal_entry", return_value=MagicMock(tenant_id=1)),
            patch(
                "services.advanced_journal_manager.AdvancedJournalEntryManager.validate_entry",
                side_effect=failure,
            ),
            pytest.raises(GLMappingError) as caught,
        ):
            post_or_fail(lines, description="x", tenant_id=1)
        assert caught.value is failure

    def test_unexpected_error_is_wrapped(self):
        lines = [{"account": "1110", "debit": 1, "credit": 0}, {"account": "4100", "debit": 0, "credit": 1}]
        with (
            patch("services.gl_service.GLService.create_journal_entry", side_effect=RuntimeError("boom")),
            pytest.raises(GlPostingError, match="boom"),
        ):
            post_or_fail(lines, description="x", tenant_id=1)


class TestLineSideValidation:
    @pytest.mark.parametrize(
        "debit,credit",
        [(Decimal("-50"), Decimal("100")), (Decimal("50"), Decimal("-100"))],
    )
    def test_negative_side_rejected(self, debit, credit):
        with pytest.raises(FieldValidationError, match="سالب"):
            validate_gl_line_sides(debit, credit)

    def test_positive_opposite_sides_accepted(self):
        validate_gl_line_sides(Decimal("50"), Decimal("0"))


class TestJournalLookupTenantBinding:
    def test_foreign_entry_not_found(self):
        entry = MagicMock()
        entry.tenant_id = 2
        q = MagicMock()
        q.filter_by.return_value.first.return_value = entry
        with (
            patch("utils.gl_tenant.gl_entry_query", return_value=q),
            pytest.raises(NotFound),
        ):
            AdvancedJournalEntryManager._entry_or_404(entry.id, tenant_id=1)


class TestModelDefaults:
    def test_journal_entry_defaults_to_draft_not_posted(self, db_session, sample_tenant):
        from models.gl import GLJournalEntry

        entry = GLJournalEntry(
            tenant_id=sample_tenant.id,
            entry_number="JE-TEST-NEW",
            total_debit=Decimal("0"),
            total_credit=Decimal("0"),
        )
        db_session.add(entry)
        db_session.flush()
        assert entry.is_posted is False

    def test_schema_declares_nonnegative_checks(self):
        from models.gl import GLJournalEntry, GLJournalLine

        entry_checks = {c.name for c in GLJournalEntry.__table_args__ if getattr(c, "name", None)}
        line_checks = {c.name for c in GLJournalLine.__table_args__ if getattr(c, "name", None)}
        assert "ck_gl_journal_entries_total_debit_nonneg" in entry_checks
        assert "ck_gl_journal_entries_total_credit_nonneg" in entry_checks
        assert "ck_gl_journal_lines_debit_nonneg" in line_checks
        assert "ck_gl_journal_lines_credit_nonneg" in line_checks
