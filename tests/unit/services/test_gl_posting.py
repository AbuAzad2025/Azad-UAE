from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from services.gl_posting import (
    GlPostingError,
    UnbalancedJournalEntryError,
    assert_balanced_lines,
    post_or_fail,
)


class TestAssertBalancedLines:
    def test_balanced_aed(self):
        lines = [
            {"debit": Decimal("100"), "credit": Decimal("0")},
            {"debit": Decimal("0"), "credit": Decimal("100")},
        ]
        assert_balanced_lines(lines, currency="AED")

    def test_unbalanced_raises(self):
        lines = [
            {"debit": Decimal("100"), "credit": Decimal("0")},
            {"debit": Decimal("0"), "credit": Decimal("50")},
        ]
        with pytest.raises(UnbalancedJournalEntryError, match="غير متوازن"):
            assert_balanced_lines(lines, currency="AED")

    def test_jod_tolerance(self):
        lines = [
            {"debit": Decimal("1.000001"), "credit": Decimal("0")},
            {"debit": Decimal("0"), "credit": Decimal("1.000002")},
        ]
        assert_balanced_lines(lines, currency="JOD")

    def test_custom_tolerance(self):
        lines = [
            {"debit": Decimal("10"), "credit": Decimal("0")},
            {"debit": Decimal("0"), "credit": Decimal("10.0005")},
        ]
        assert_balanced_lines(lines, currency="USD", tolerance=Decimal("0.01"))


class TestPostOrFail:
    def test_empty_lines_raises(self):
        with pytest.raises(GlPostingError, match="بدون سطور قيد"):
            post_or_fail([], description="Empty", tenant_id=1)

    def test_currency_from_tenant(self, db_session, sample_tenant, mocker):
        mocker.patch("services.gl_posting.assert_period_open")
        mock_entry = MagicMock(id=1)
        mocker.patch(
            "services.gl_posting.GLService.create_journal_entry",
            return_value=mock_entry,
        )
        mocker.patch(
            "services.advanced_journal_manager.AdvancedJournalEntryManager.validate_entry",
            return_value=MagicMock(status="validated"),
        )
        mocker.patch(
            "services.advanced_journal_manager.AdvancedJournalEntryManager.post_entry",
            return_value=mock_entry,
        )
        lines = [
            {"account_code": "1000", "debit": Decimal("10"), "credit": Decimal("0")},
            {"account_code": "4000", "debit": Decimal("0"), "credit": Decimal("10")},
        ]
        post_or_fail(
            lines,
            description="Tenant currency",
            tenant_id=sample_tenant.id,
        )

    def test_currency_fallback_on_tenant_error(self, mocker):
        mocker.patch(
            "services.gl_posting.db.session.get",
            side_effect=AttributeError("no tenant"),
        )
        mocker.patch(
            "services.gl_posting.get_system_default_currency", return_value="AED"
        )
        mocker.patch("services.gl_posting.assert_period_open")
        mock_entry = MagicMock(id=2)
        create = mocker.patch(
            "services.gl_posting.GLService.create_journal_entry",
            return_value=mock_entry,
        )
        mocker.patch(
            "services.advanced_journal_manager.AdvancedJournalEntryManager.validate_entry",
            return_value=MagicMock(status="validated"),
        )
        mocker.patch(
            "services.advanced_journal_manager.AdvancedJournalEntryManager.post_entry",
            return_value=mock_entry,
        )
        lines = [
            {"account_code": "1000", "debit": Decimal("5"), "credit": Decimal("0")},
            {"account_code": "4000", "debit": Decimal("0"), "credit": Decimal("5")},
        ]
        post_or_fail(lines, description="Fallback currency", tenant_id=1)
        assert create.call_args.kwargs["currency"] == "AED"

    def test_wraps_gl_service_errors(self, mocker):
        mocker.patch("services.gl_posting.assert_period_open")
        mocker.patch(
            "services.gl_posting.GLService.create_journal_entry",
            side_effect=ValueError("period closed"),
        )
        lines = [
            {"account_code": "1000", "debit": Decimal("1"), "credit": Decimal("0")},
            {"account_code": "4000", "debit": Decimal("0"), "credit": Decimal("1")},
        ]
        with pytest.raises(GlPostingError, match="period closed"):
            post_or_fail(
                lines,
                description="Wrapped",
                tenant_id=1,
                date=datetime(2026, 1, 15, tzinfo=timezone.utc),
            )
