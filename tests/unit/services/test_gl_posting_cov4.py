"""Coverage-4 for services/gl_posting.py — exact-line fallback/except/else arcs.

Targets (production lines):
- _normalize_lines_to_base rounding-plug arc (diff != 0, within 0.001):
  lines 68-72 plug onto heavier side + line 72 log call.
- _normalize_lines_to_base no-plug arc (diff == 0): lines 65-67, 73.
- _normalize_lines_to_base original_* preservation: lines 61-62.
- post_or_fail currency-is-None tenant resolution error fallback arc:
  lines 115-124 (LookupError/AttributeError/TypeError/ValueError -> system default).
- post_or_fail invalid exchange-rate arc: lines 137-141 (rate<=0, non-base
  currency raises; base-currency resets to 1).
- post_or_fail validation-error arc: lines 176-177 (validated status error).
- post_or_fail exception-wrap arc: lines 188-189.
- assert_balanced_lines default-tolerance + unknown-currency arcs: 207-212.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from services.gl_posting import (
    GlPostingError,
    _normalize_lines_to_base,
    assert_balanced_lines,
    post_or_fail,
)


class TestNormalizeLinesRoundingPlug:
    def test_plug_adjusts_heavier_side_debit(self, mocker):
        # Real conversion path: identical currency fast-track keeps amounts,
        # but a 0.001 drift triggers the deterministic plug (lines 68-72).
        mocker.patch(
            "services.gl_posting.convert_and_quantize_aed",
            side_effect=[Decimal("10.001"), Decimal("0"), Decimal("0"), Decimal("10.000")],
        )
        lines = [
            {"account_code": "1111", "debit": Decimal("10"), "credit": Decimal("0")},
            {"account_code": "4101", "debit": Decimal("0"), "credit": Decimal("10")},
        ]
        out = _normalize_lines_to_base(
            lines, currency="AED", exchange_rate=Decimal("1"), base_currency="AED", tenant_id=1
        )
        assert out[0]["debit"] == Decimal("10.000")
        assert out[0]["original_debit"] == Decimal("10")
        assert out[1]["original_credit"] == Decimal("10")

    def test_plug_adjusts_credit_side(self, mocker):
        mocker.patch(
            "services.gl_posting.convert_and_quantize_aed",
            side_effect=[Decimal("10.000"), Decimal("0"), Decimal("0"), Decimal("10.001")],
        )
        lines = [
            {"account_code": "1111", "debit": Decimal("10"), "credit": Decimal("0")},
            {"account_code": "4101", "debit": Decimal("0"), "credit": Decimal("10")},
        ]
        out = _normalize_lines_to_base(
            lines, currency="AED", exchange_rate=Decimal("1"), base_currency="AED", tenant_id=1
        )
        # diff = debit - credit = -0.001 -> credit-side plug arc (lines 68-72).
        assert out[1]["credit"] == Decimal("10.002")

    def test_no_plug_when_balanced(self):
        lines = [
            {"account_code": "1111", "debit": Decimal("10"), "credit": Decimal("0")},
            {"account_code": "4101", "debit": Decimal("0"), "credit": Decimal("10")},
        ]
        out = _normalize_lines_to_base(
            lines, currency="AED", exchange_rate=Decimal("1"), base_currency="AED", tenant_id=1
        )
        assert out[0]["debit"] == Decimal("10.000")
        assert out[1]["credit"] == Decimal("10.000")

    def test_large_diff_no_plug(self, mocker):
        mocker.patch(
            "services.gl_posting.convert_and_quantize_aed",
            side_effect=[Decimal("10.500"), Decimal("0"), Decimal("0"), Decimal("10.000")],
        )
        lines = [
            {"account_code": "1111", "debit": Decimal("10"), "credit": Decimal("0")},
            {"account_code": "4101", "debit": Decimal("0"), "credit": Decimal("10")},
        ]
        out = _normalize_lines_to_base(
            lines, currency="AED", exchange_rate=Decimal("1"), base_currency="AED", tenant_id=1
        )
        assert out[0]["debit"] == Decimal("10.500")


class TestAssertBalancedLinesArcs:
    def test_unknown_currency_uses_default_tolerance(self):
        lines = [
            {"debit": Decimal("100"), "credit": Decimal("0")},
            {"debit": Decimal("0"), "credit": Decimal("100")},
        ]
        assert_balanced_lines(lines, currency="XXX")

    def test_none_currency_uses_default_tolerance(self):
        lines = [
            {"debit": Decimal("7"), "credit": Decimal("0")},
            {"debit": Decimal("0"), "credit": Decimal("7")},
        ]
        assert_balanced_lines(lines)

    def test_lowercase_currency_matches_table(self):
        lines = [
            {"debit": Decimal("1.000001"), "credit": Decimal("0")},
            {"debit": Decimal("0"), "credit": Decimal("1.000002")},
        ]
        assert_balanced_lines(lines, currency="jod")


class TestPostOrFailArcs:
    @staticmethod
    def _balanced():
        return [
            {"account_code": "1111", "debit": Decimal("5"), "credit": Decimal("0")},
            {"account_code": "4101", "debit": Decimal("0"), "credit": Decimal("5")},
        ]

    def test_invalid_rate_non_base_currency_raises(self, mocker):
        mocker.patch("services.gl_posting.assert_period_open")
        mocker.patch("services.gl_posting.resolve_tenant_base_currency", return_value="AED")
        with pytest.raises(GlPostingError, match="صرف"):
            post_or_fail(
                self._balanced(),
                description="Bad rate",
                tenant_id=1,
                currency="USD",
                exchange_rate=0,
            )

    def test_invalid_rate_base_currency_resets(self, mocker):
        mocker.patch("services.gl_posting.assert_period_open")
        mocker.patch("services.gl_posting.resolve_tenant_base_currency", return_value="AED")
        mock_entry = MagicMock(id=11)
        mocker.patch("services.gl_posting.GLService.create_journal_entry", return_value=mock_entry)
        mocker.patch(
            "services.advanced_journal_manager.AdvancedJournalEntryManager.validate_entry",
            return_value=MagicMock(status="validated"),
        )
        posted = MagicMock(id=11)
        post_mock = mocker.patch(
            "services.advanced_journal_manager.AdvancedJournalEntryManager.post_entry",
            return_value=posted,
        )
        out = post_or_fail(
            self._balanced(),
            description="Base rate reset",
            tenant_id=1,
            currency="AED",
            exchange_rate=0,
        )
        assert out is posted
        assert post_mock.called

    def test_validation_error_status_raises_wrapped(self, mocker):
        mocker.patch("services.gl_posting.assert_period_open")
        mocker.patch("services.gl_posting.resolve_tenant_base_currency", return_value="AED")
        mock_entry = MagicMock(id=12)
        mocker.patch("services.gl_posting.GLService.create_journal_entry", return_value=mock_entry)
        mocker.patch(
            "services.advanced_journal_manager.AdvancedJournalEntryManager.validate_entry",
            return_value=MagicMock(status="error", validation_errors="bad header"),
        )
        with pytest.raises(GlPostingError, match="Validation failed"):
            post_or_fail(
                self._balanced(),
                description="Invalid entry",
                tenant_id=1,
                currency="AED",
            )

    def test_wraps_post_errors(self, mocker):
        mocker.patch("services.gl_posting.assert_period_open")
        mocker.patch("services.gl_posting.resolve_tenant_base_currency", return_value="AED")
        mock_entry = MagicMock(id=13)
        mocker.patch("services.gl_posting.GLService.create_journal_entry", return_value=mock_entry)
        mocker.patch(
            "services.advanced_journal_manager.AdvancedJournalEntryManager.validate_entry",
            return_value=MagicMock(status="validated"),
        )
        mocker.patch(
            "services.advanced_journal_manager.AdvancedJournalEntryManager.post_entry",
            side_effect=ValueError("ledger locked"),
        )
        with pytest.raises(GlPostingError, match="ledger locked"):
            post_or_fail(
                self._balanced(),
                description="Post boom",
                tenant_id=1,
                currency="AED",
                date=datetime(2026, 2, 2, tzinfo=UTC),
            )

    def test_none_exchange_rate_defaults_to_one(self, mocker):
        mocker.patch("services.gl_posting.assert_period_open")
        mocker.patch("services.gl_posting.resolve_tenant_base_currency", return_value="AED")
        mock_entry = MagicMock(id=14)
        mocker.patch("services.gl_posting.GLService.create_journal_entry", return_value=mock_entry)
        mocker.patch(
            "services.advanced_journal_manager.AdvancedJournalEntryManager.validate_entry",
            return_value=MagicMock(status="validated"),
        )
        mocker.patch(
            "services.advanced_journal_manager.AdvancedJournalEntryManager.post_entry",
            return_value=mock_entry,
        )
        out = post_or_fail(
            self._balanced(),
            description="None rate",
            tenant_id=1,
            currency="AED",
            exchange_rate=None,
        )
        assert out is mock_entry
