"""Treasury service — liquidity position, check buckets, reconciliation."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest


class TestLiquidityPosition:
    """get_liquidity_position — cashbox vs GL fallback."""

    def test_cashbox_balances_summed_by_kind(self, mocker):
        box = MagicMock(
            id=1,
            code="CASH-01",
            name_ar="صندوق",
            name_en="Cash",
            box_type="cash",
            current_balance=Decimal("5000"),
            currency="AED",
            branch_id=2,
        )
        mock_q = MagicMock()
        mock_q.filter_by.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.all.return_value = [box]
        mocker.patch(
            "models.CashBox.query",
            new_callable=mocker.PropertyMock,
            return_value=mock_q,
        )

        from services.treasury_service import TreasuryService

        result = TreasuryService.get_liquidity_position(tenant_id=1, branch_id=2)
        assert result["total_balance"] == pytest.approx(5000.0)
        assert result["accounts"][0]["kind"] == "cash"
        assert result["kind_summary"]["cash"]["count"] == 1

    def test_gl_fallback_when_no_cashboxes(self, mocker):
        cb_q = MagicMock()
        cb_q.filter_by.return_value = cb_q
        cb_q.filter.return_value = cb_q
        cb_q.order_by.return_value = cb_q
        cb_q.all.return_value = []
        mocker.patch(
            "models.CashBox.query",
            new_callable=mocker.PropertyMock,
            return_value=cb_q,
        )

        acc = MagicMock(
            id=10,
            code="1100",
            liquidity_kind="bank",
            name_ar="بنك",
            name_en="Bank",
            currency="AED",
        )
        acc.get_balance.return_value = Decimal("12000")
        gl_q = MagicMock()
        gl_q.filter.return_value = gl_q
        gl_q.order_by.return_value = gl_q
        gl_q.all.return_value = [acc]
        mocker.patch(
            "models.GLAccount.query",
            new_callable=mocker.PropertyMock,
            return_value=gl_q,
        )

        from services.treasury_service import TreasuryService

        result = TreasuryService.get_liquidity_position(tenant_id=1)
        assert result["accounts"][0]["source"] == "gl_account"
        assert result["total_balance"] == pytest.approx(12000.0)

    def test_normalizes_bank_account_box_type(self, mocker):
        box = MagicMock(
            id=2,
            code="BNK",
            name_ar=None,
            name_en="Main",
            box_type="bank_account",
            current_balance=100,
            currency="AED",
            branch_id=None,
        )
        mock_q = MagicMock()
        mock_q.filter_by.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.all.return_value = [box]
        mocker.patch(
            "models.CashBox.query",
            new_callable=mocker.PropertyMock,
            return_value=mock_q,
        )

        from services.treasury_service import TreasuryService

        result = TreasuryService.get_liquidity_position(1)
        assert result["accounts"][0]["kind"] == "bank"


class TestChequeMaturity:
    """get_check_maturity — bucket boundaries and incoming/outgoing split."""

    def test_buckets_incoming_cheques(self, mocker):
        today = date.today()
        overdue = MagicMock(
            id=1,
            cheque_type="incoming",
            amount_aed=Decimal("1000"),
            due_date=today - timedelta(days=5),
            cheque_number="C1",
            cheque_bank_number=None,
            bank_name="B",
            drawer_name="D",
            payee_name="P",
            status="pending",
            cheque_type_ar="وارد",
        )
        soon = MagicMock(
            id=2,
            cheque_type="incoming",
            amount_aed=Decimal("500"),
            due_date=today + timedelta(days=3),
            cheque_number="C2",
            cheque_bank_number=None,
            bank_name="B",
            drawer_name="D",
            payee_name="P",
            status="pending",
            cheque_type_ar="وارد",
        )
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.all.return_value = [overdue, soon]
        mocker.patch(
            "models.Cheque.query",
            new_callable=mocker.PropertyMock,
            return_value=mock_q,
        )

        from services.treasury_service import TreasuryService

        result = TreasuryService.get_cheque_maturity(tenant_id=1)
        inc = result["incoming"]["buckets"]
        assert inc["overdue"]["count"] == 1
        assert inc["0_7_days"]["count"] == 1
        assert result["incoming"]["total_count"] == 2


class TestDashboard:
    """build_dashboard / get_bank_reconciliation_status."""

    def test_build_dashboard_aggregates_sections(self, mocker):
        mocker.patch(
            "services.treasury_service.TreasuryService.get_liquidity_position",
            return_value={"total_balance": 1.0, "accounts": []},
        )
        mocker.patch(
            "services.treasury_service.TreasuryService.get_cheque_maturity",
            return_value={"incoming": {}, "outgoing": {}, "today": "2025-06-01"},
        )
        mocker.patch(
            "services.treasury_service.TreasuryService.get_bank_reconciliation_status",
            return_value=[],
        )

        from services.treasury_service import TreasuryService

        dash = TreasuryService.build_dashboard(1, branch_id=3)
        assert "liquidity" in dash
        assert "generated_at" in dash

    def test_reconciliation_list_shape(self, mocker):
        rec = MagicMock(
            id=1,
            reconciliation_number="REC-1",
            period_start=date(2025, 1, 1),
            period_end=date(2025, 1, 31),
            closing_balance_per_books=100,
            closing_balance_per_bank=99,
            difference=1,
            status="open",
            status_ar="مفتوح",
            created_at=None,
        )
        rec.bank_account = MagicMock(code="1200", name_ar="بنك")
        mock_q = MagicMock()
        mock_q.join.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.all.return_value = [rec]
        mocker.patch(
            "models.BankReconciliation.query",
            new_callable=mocker.PropertyMock,
            return_value=mock_q,
        )

        from services.treasury_service import TreasuryService

        rows = TreasuryService.get_bank_reconciliation_status(1)
        assert rows[0]["difference"] == pytest.approx(1.0)
