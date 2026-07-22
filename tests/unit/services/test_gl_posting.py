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
        mocker.patch("services.gl_posting.get_system_default_currency", return_value="AED")
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


class TestGatewayBaseConversion:
    def _capture(self, mocker):
        mocker.patch("services.gl_posting.assert_period_open")
        mocker.patch("services.gl_posting.resolve_tenant_base_currency", return_value="AED")
        mock_entry = MagicMock(id=9)
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
        return create

    def test_foreign_lines_converted_to_base(self, mocker):
        create = self._capture(mocker)
        lines = [
            {"account_code": "5300", "debit": Decimal("100"), "credit": Decimal("0")},
            {"account_code": "1110", "debit": Decimal("0"), "credit": Decimal("100")},
        ]
        post_or_fail(
            lines,
            description="USD expense",
            currency="USD",
            exchange_rate="3.5",
            tenant_id=1,
        )
        stored = create.call_args.kwargs["lines"]
        assert stored[0]["debit"] == Decimal("350.000")
        assert stored[1]["credit"] == Decimal("350.000")
        assert stored[0]["original_debit"] == Decimal("100")
        assert stored[1]["original_credit"] == Decimal("100")

    def test_base_currency_fast_track_quantizes_only(self, mocker):
        create = self._capture(mocker)
        lines = [
            {"account_code": "5300", "debit": Decimal("100.0005"), "credit": Decimal("0")},
            {"account_code": "1110", "debit": Decimal("0"), "credit": Decimal("100.0005")},
        ]
        post_or_fail(
            lines,
            description="AED base",
            currency="AED",
            exchange_rate="3.5",
            tenant_id=1,
        )
        stored = create.call_args.kwargs["lines"]
        assert stored[0]["debit"] == Decimal("100.001")
        assert stored[1]["credit"] == Decimal("100.001")

    def test_rounding_plug_restores_exact_balance(self, mocker):
        create = self._capture(mocker)
        lines = [
            {"account_code": "5300", "debit": Decimal("10.0005"), "credit": Decimal("0")},
            {"account_code": "5001", "debit": Decimal("0"), "credit": Decimal("5.0003")},
            {"account_code": "5002", "debit": Decimal("0"), "credit": Decimal("5.0002")},
        ]
        post_or_fail(
            lines,
            description="Plug",
            currency="AED",
            tenant_id=1,
        )
        stored = create.call_args.kwargs["lines"]
        total_debit = sum(line["debit"] for line in stored)
        total_credit = sum(line["credit"] for line in stored)
        assert total_debit == total_credit
        assert stored[0]["debit"] == Decimal("10.000")

    def test_foreign_with_nonpositive_rate_raises(self, mocker):
        self._capture(mocker)
        lines = [
            {"account_code": "5300", "debit": Decimal("10"), "credit": Decimal("0")},
            {"account_code": "1110", "debit": Decimal("0"), "credit": Decimal("10")},
        ]
        with pytest.raises(GlPostingError, match="سعر صرف غير صالح"):
            post_or_fail(
                lines,
                description="Bad rate",
                currency="USD",
                exchange_rate=0,
                tenant_id=1,
            )

    def test_base_currency_with_rate_one_passes_through(self, mocker):
        create = self._capture(mocker)
        lines = [
            {"account_code": "5300", "debit": Decimal("42.5"), "credit": Decimal("0")},
            {"account_code": "1110", "debit": Decimal("0"), "credit": Decimal("42.5")},
        ]
        post_or_fail(
            lines,
            description="Base 1.0",
            currency="AED",
            exchange_rate="1.0",
            tenant_id=1,
        )
        stored = create.call_args.kwargs["lines"]
        assert stored[0]["debit"] == Decimal("42.500")
        assert stored[1]["credit"] == Decimal("42.500")
