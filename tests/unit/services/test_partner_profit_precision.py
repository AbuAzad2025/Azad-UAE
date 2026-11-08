"""Partner profit precision — per-scope shares, fixed prorate, accrual sync,
commission reversal on returns and discount re-basing."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from services.partner_service import PartnerService


def _partner(**kwargs):
    p = MagicMock()
    defaults = {
        "id": 1,
        "tenant_id": 1,
        "is_active": True,
        "scope_type": "company",
        "scope_id": None,
        "share_percentage": Decimal("50"),
        "expense_share_percentage": Decimal("0"),
        "loss_share_percentage": Decimal("0"),
        "fixed_monthly_amount": Decimal("0"),
        "min_profit_threshold": Decimal("0"),
        "current_balance": Decimal("0"),
        "total_profit_received": Decimal("0"),
        "total_loss_borne": Decimal("0"),
        "total_withdrawals": Decimal("0"),
        "total_additional_investment": Decimal("0"),
    }
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(p, k, v)
    return p


class TestMonthsInPeriod:
    def test_single_month(self):
        assert PartnerService._months_in_period(date(2026, 1, 1), date(2026, 1, 31)) == 1

    def test_quarter(self):
        assert PartnerService._months_in_period(date(2026, 1, 1), date(2026, 3, 31)) == 3

    def test_year_boundary(self):
        assert PartnerService._months_in_period(date(2025, 12, 15), date(2026, 2, 10)) == 3

    def test_reversed_period(self):
        assert PartnerService._months_in_period(date(2026, 3, 31), date(2026, 1, 1)) == 1


class TestPerScopeValidation:
    def _run(self, mocker, partners):
        P = mocker.patch("models.Partner")
        P.query.filter_by.return_value.all.return_value = partners
        D = mocker.patch("models.PartnerProfitDistribution")
        D.query.filter_by.return_value.first.return_value = None
        D.return_value = MagicMock(id=99)
        mocker.patch.object(
            PartnerService,
            "calculate_scope_profit",
            return_value={
                "revenue": 1000.0,
                "cogs": 200.0,
                "expenses": 0.0,
                "gross_profit": 800.0,
                "net_profit": 800.0,
            },
        )
        mocker.patch("services.partner_service.db")

    def test_company_and_branch_100_each_allowed(self, mocker):
        partners = [
            _partner(id=1, scope_type="company", scope_id=None, share_percentage=Decimal("100")),
            _partner(id=2, scope_type="branch", scope_id=5, share_percentage=Decimal("100")),
        ]
        self._run(mocker, partners)
        ids = PartnerService.create_distributions(1, date(2026, 1, 1), date(2026, 1, 31))
        assert len(ids) == 2

    def test_same_scope_over_100_rejected(self, mocker):
        partners = [
            _partner(id=1, scope_type="company", share_percentage=Decimal("60")),
            _partner(id=2, scope_type="company", share_percentage=Decimal("50")),
        ]
        P = mocker.patch("models.Partner")
        P.query.filter_by.return_value.all.return_value = partners
        with pytest.raises(ValueError, match="يتجاوز 100%"):
            PartnerService.create_distributions(1, date(2026, 1, 1), date(2026, 1, 31))

    def test_fixed_amount_prorated_by_period_months(self, mocker):
        partner = _partner(
            share_percentage=Decimal("0"),
            fixed_monthly_amount=Decimal("100"),
        )
        P = mocker.patch("models.Partner")
        P.query.filter_by.return_value.all.return_value = [partner]
        D = mocker.patch("models.PartnerProfitDistribution")
        D.query.filter_by.return_value.first.return_value = None
        dist = MagicMock(id=7)
        D.return_value = dist
        mocker.patch.object(
            PartnerService,
            "calculate_scope_profit",
            return_value={
                "revenue": 0.0,
                "cogs": 0.0,
                "expenses": 0.0,
                "gross_profit": 0.0,
                "net_profit": 0.0,
            },
        )
        mocker.patch("services.partner_service.db")
        PartnerService.create_distributions(1, date(2026, 1, 1), date(2026, 3, 31))
        fixed_arg = D.call_args.kwargs["fixed_amount"]
        assert fixed_arg == Decimal("300")


class TestApproveAccrual:
    def test_positive_net_accrues_expense_and_partner_liability(self, mocker):
        dist = MagicMock(
            status="draft",
            tenant_id=1,
            net_due=100.0,
            partner_id=1,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            id=5,
        )
        partner = _partner(current_balance=Decimal("0"))
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.get.side_effect = [dist, partner]
        mocker.patch("models.PartnerTransaction", return_value=MagicMock(amount=100.0))
        mocker.patch("utils.tax_settings._resolve_main_branch", return_value=1)
        mocker.patch(
            "services.gl_service.GLService.get_account_code_for_concept",
            return_value="2150",
        )
        post = mocker.patch("services.gl_posting.post_or_fail")
        assert PartnerService.approve_distribution(5, 9, tenant_id=1) is True
        args, kwargs = post.call_args
        lines = args[0] if args else kwargs.get("lines")
        debits = [ln for ln in lines if ln.get("debit")]
        credits = [ln for ln in lines if ln.get("credit")]
        assert debits[0]["concept_code"] == "COMMISSION_EXPENSE"
        assert credits[0]["concept_code"] == "PARTNER_CURRENT_ACCOUNT"
        assert partner.current_balance == Decimal("100")


class TestPaySync:
    def test_pay_reduces_balance_and_writes_withdrawal(self, mocker):
        dist = MagicMock(status="approved", tenant_id=1, net_due=200.0, id=7)
        partner = _partner(current_balance=Decimal("200"))
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.get.side_effect = [dist, partner]
        mocker.patch("utils.tax_settings._resolve_main_branch", return_value=1)
        mocker.patch(
            "services.gl_service.GLService.get_account_code_for_concept",
            return_value="2150",
        )
        mocker.patch(
            "services.gl_service.GLService.get_default_liquidity_account",
            return_value="1120",
        )
        mocker.patch("services.gl_posting.post_or_fail")
        mocker.patch("models.PartnerTransaction")
        assert PartnerService.pay_distribution(7, tenant_id=1) is True
        assert partner.current_balance == Decimal("0")
        assert partner.total_withdrawals == Decimal("200")

    def test_pay_loss_has_no_cash_leg(self, mocker):
        dist = MagicMock(status="approved", tenant_id=1, net_due=-50.0, id=8)
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.get.return_value = dist
        post = mocker.patch("services.gl_posting.post_or_fail")
        assert PartnerService.pay_distribution(8, tenant_id=1) is True
        post.assert_not_called()
        assert dist.status == "paid"


class TestCommissionReversal:
    def test_partial_return_reverses_same_ratio(self, mocker):
        entry = MagicMock(commission_amount_aed=Decimal("10"))
        E = mocker.patch("services.return_service.PartnerCommissionEntry")
        E.query.filter_by.return_value.all.return_value = [entry]
        sale_line = MagicMock(id=11, quantity=Decimal("4"))
        from services.return_service import ReturnService

        assert ReturnService._commission_reversal_total(sale_line, Decimal("1"), tenant_id=1) == Decimal("2.500")

    def test_zero_quantity_no_reversal(self, mocker):
        mocker.patch("services.return_service.PartnerCommissionEntry")
        sale_line = MagicMock(id=11, quantity=Decimal("4"))
        from services.return_service import ReturnService

        assert ReturnService._commission_reversal_total(sale_line, Decimal("0"), tenant_id=1) == Decimal("0")


class TestCancelGuard:
    def test_cancel_refused_when_returns_exist(self, mocker):
        from services.sale_service import SaleService

        sale = MagicMock(status="confirmed", id=1, tenant_id=1)
        PR = mocker.patch("models.ProductReturn")
        PR.query.filter_by.return_value.filter.return_value.count.return_value = 1
        with pytest.raises(ValueError, match="مرتجعات"):
            SaleService.cancel_sale(sale)


class TestScopeCommissions:
    def test_scope_commissions_net_of_returns(self, mocker):
        gross_q = MagicMock()
        gross_q.scalar.return_value = Decimal("100")
        gross_q.join.return_value.filter.return_value = gross_q
        ret_q = MagicMock()
        ret_q.all.return_value = [(Decimal("1"), Decimal("4"), Decimal("10"))]
        ret_q.join.return_value.join.return_value.join.return_value.filter.return_value = ret_q
        mocker.patch("services.partner_service.db.session.query", side_effect=[gross_q, ret_q])
        assert PartnerService.get_scope_commissions(1, date(2026, 1, 1), date(2026, 1, 31)) == Decimal("97.500")

    def test_calculate_scope_profit_deducts_commissions(self, mocker):
        mocker.patch.object(PartnerService, "get_scope_revenue", return_value=Decimal("1000"))
        mocker.patch.object(PartnerService, "get_scope_cogs", return_value=Decimal("400"))
        mocker.patch.object(PartnerService, "get_scope_expenses", return_value=Decimal("100"))
        mocker.patch.object(PartnerService, "get_scope_commissions", return_value=Decimal("50"))
        pnl = PartnerService.calculate_scope_profit(1, date(2026, 1, 1), date(2026, 1, 31))
        assert pnl["commissions"] == 50.0
        assert pnl["net_profit"] == 450.0


class TestUnifiedStatement:
    def test_unified_combines_both_roles(self, mocker):
        partner = _partner(current_balance=Decimal("25"))
        partner.name = "Dual Role"
        dist = MagicMock(
            id=1,
            share_amount=Decimal("100"),
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            scope_type="company",
            net_profit=Decimal("500"),
            net_due=Decimal("100"),
            status="approved",
        )
        customer = MagicMock(id=9, name="Dual Role", customer_type="partner")
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.get.return_value = partner
        mock_db.session.query.return_value.filter.return_value.scalar.return_value = Decimal("40")
        D = mocker.patch("models.PartnerProfitDistribution")
        D.query.filter_by.return_value.order_by.return_value.all.return_value = [dist]
        C = mocker.patch("models.Customer")
        C.query.filter_by.return_value.all.return_value = [customer]
        mocker.patch("models.PartnerCommissionEntry")
        out = PartnerService.get_unified_statement(1, 1)
        assert out["company_total"] == 100.0
        assert out["product_commissions_total"] == 40.0
        assert out["combined_total"] == 140.0


class TestDiscountRebase:
    def test_invoice_discount_reduces_commission(self):
        from services.sale_service import SaleService

        entry = MagicMock(base_amount_aed=Decimal("100"), commission_amount_aed=Decimal("20"))
        entry.base_amount_aed = Decimal("100")
        entry.commission_amount_aed = Decimal("20")
        entry.profit_margin = Decimal("100")
        context = [(entry, Decimal("500"), Decimal("100"), Decimal("20"), Decimal("100"))]
        SaleService._apply_invoice_discount_to_commissions(
            context,
            subtotal=Decimal("500"),
            total_discount=Decimal("50"),
            exchange_rate=Decimal("1"),
            currency="AED",
            tenant_id=1,
        )
        # Line takes the whole discount: base 100-50=50, commission 10.
        assert entry.base_amount_aed == Decimal("50")
        assert entry.commission_amount_aed == Decimal("10")
        assert entry.profit_margin == Decimal("50")
