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


class TestScopeCommissionsBranches:
    def _chain(self, scalar=None, rows=None):
        q = MagicMock()
        q.scalar = MagicMock(return_value=scalar)
        q.filter.return_value = q
        q.join.return_value = q
        q.all = MagicMock(return_value=rows or [])
        return q

    def test_scope_commissions_branch_and_warehouse(self, mocker):
        for scope, scope_id in (("branch", 5), ("warehouse", 9)):
            query = self._chain(scalar=Decimal("100"))
            mocker.patch("services.partner_service.db.session.query", return_value=query)
            assert PartnerService.get_scope_commissions(
                1, date(2026, 1, 1), date(2026, 1, 31), scope, scope_id
            ) == Decimal("100")

    def test_expenses_filter_by_warehouse(self, mocker):
        q = MagicMock()
        q.filter.return_value.filter.return_value.scalar.return_value = Decimal("25")
        mocker.patch("services.partner_service.db.session.query", return_value=q)
        assert PartnerService.get_scope_expenses(1, date(2026, 1, 1), date(2026, 1, 31), "warehouse", 9) == Decimal(
            "25"
        )

    def test_return_reversal_skips_invalid_rows_and_clamps(self, mocker):
        query = self._chain(
            scalar=Decimal("100"),
            rows=[
                (1, Decimal("0"), Decimal("0"), Decimal("10")),
                (2, Decimal("1"), Decimal("0"), Decimal("10")),
                (3, Decimal("8"), Decimal("4"), Decimal("10")),
            ],
        )
        mocker.patch("services.partner_service.db.session.query", return_value=query)
        assert PartnerService.get_scope_commissions(1, date(2026, 1, 1), date(2026, 1, 31)) == Decimal("90")

    def test_return_in_later_period_can_make_commissions_negative(self, mocker):
        query = self._chain(scalar=Decimal("0"), rows=[(1, Decimal("1"), Decimal("2"), Decimal("10"))])
        mocker.patch("services.partner_service.db.session.query", return_value=query)
        assert PartnerService.get_scope_commissions(1, date(2026, 2, 1), date(2026, 2, 28), "warehouse", 9) == Decimal(
            "-5.000"
        )

    def test_commission_reversal_rounds_each_return_line(self, mocker):
        query = self._chain(
            scalar=Decimal("0"),
            rows=[
                (1, Decimal("1"), Decimal("2"), Decimal("0.001")),
                (2, Decimal("1"), Decimal("2"), Decimal("0.001")),
            ],
        )
        mocker.patch("services.partner_service.db.session.query", return_value=query)
        assert PartnerService.get_scope_commissions(1, date(2026, 2, 1), date(2026, 2, 28)) == Decimal("-0.002")


class TestApproveBranches:
    def test_below_threshold_keeps_zero_share(self, mocker):
        partner = _partner(share_percentage=Decimal("40"), min_profit_threshold=Decimal("900"))
        P = mocker.patch("models.Partner")
        P.query.filter_by.return_value.all.return_value = [partner]
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
                "commissions": 0.0,
                "gross_profit": 800.0,
                "net_profit": 800.0,
            },
        )
        mocker.patch("services.partner_service.db")
        PartnerService.create_distributions(1, date(2026, 1, 1), date(2026, 1, 31))
        assert D.call_args.kwargs["share_amount"] == Decimal("0")

    def test_approve_without_partner_row_still_accrues(self, mocker):
        dist = MagicMock(
            status="draft",
            tenant_id=1,
            net_due=100.0,
            partner_id=999,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            id=5,
        )
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.get.side_effect = [dist, None]
        mocker.patch("models.PartnerTransaction", return_value=MagicMock(amount=100.0))
        mocker.patch("utils.tax_settings._resolve_main_branch", return_value=1)
        mocker.patch("services.gl_service.GLService.get_account_code_for_concept", return_value="2150")
        post = mocker.patch("services.gl_posting.post_or_fail")
        assert PartnerService.approve_distribution(5, 9, tenant_id=1) is True
        post.assert_called_once()

    def test_approve_branch_resolution_failure_falls_back_to_none(self, mocker):
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
        mocker.patch("utils.tax_settings._resolve_main_branch", side_effect=RuntimeError("no branch"))
        mocker.patch("services.gl_service.GLService.get_account_code_for_concept", return_value="2150")
        post = mocker.patch("services.gl_posting.post_or_fail")
        assert PartnerService.approve_distribution(5, 9, tenant_id=1) is True
        _, kwargs = post.call_args
        assert kwargs.get("branch_id") is None


class TestLinkUnlink:
    def test_link_missing_rows(self, mocker):
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.get.side_effect = [None, None]
        assert PartnerService.link_product_partner(1, 1, tenant_id=1) is False

    def test_link_wrong_tenant(self, mocker):
        partner = _partner(tenant_id=2)
        customer = MagicMock(tenant_id=2, customer_type="partner")
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.get.side_effect = [partner, customer]
        assert PartnerService.link_product_partner(1, 1, tenant_id=1) is False

    def test_link_foreign_customer_and_wrong_type(self, mocker):
        partner = _partner(tenant_id=1)
        foreign = MagicMock(tenant_id=2, customer_type="partner")
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.get.side_effect = [partner, foreign]
        assert PartnerService.link_product_partner(1, 1, tenant_id=1) is False
        regular = MagicMock(tenant_id=1, customer_type="regular")
        mock_db.session.get.side_effect = [partner, regular]
        assert PartnerService.link_product_partner(1, 1, tenant_id=1) is False

    def test_link_success_sets_partner_id(self, mocker):
        partner = _partner(id=3, tenant_id=1)
        customer = MagicMock(tenant_id=1, customer_type="partner")
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.get.side_effect = [partner, customer]
        assert PartnerService.link_product_partner(3, 9, tenant_id=1) is True
        assert customer.partner_id == 3

    def test_link_flush_failure_raises(self, mocker):
        partner = _partner(tenant_id=1)
        customer = MagicMock(tenant_id=1, customer_type="merchant")
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.get.side_effect = [partner, customer]
        mock_db.session.flush.side_effect = RuntimeError("db")
        with pytest.raises(RuntimeError):
            PartnerService.link_product_partner(1, 1, tenant_id=1)

    def test_unlink_missing_and_wrong_tenant(self, mocker):
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.get.return_value = None
        assert PartnerService.unlink_product_partner(1, partner_id=5, tenant_id=1) is False
        customer = MagicMock(tenant_id=2)
        mock_db.session.get.return_value = customer
        assert PartnerService.unlink_product_partner(1, partner_id=5, tenant_id=1) is False

    def test_unlink_releases(self, mocker):
        customer = MagicMock(tenant_id=1, partner_id=5)
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.get.return_value = customer
        assert PartnerService.unlink_product_partner(1, partner_id=5, tenant_id=1) is True
        assert customer.partner_id is None

    def test_unlink_refuses_another_partner(self, mocker):
        customer = MagicMock(tenant_id=1, partner_id=5)
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.get.return_value = customer
        assert PartnerService.unlink_product_partner(1, partner_id=6, tenant_id=1) is False
        assert customer.partner_id == 5
        mock_db.session.flush.assert_not_called()


class TestFlushFailures:
    def test_create_flush_failure_raises(self, mocker):
        partner = _partner(loss_share_percentage=Decimal("50"))
        P = mocker.patch("models.Partner")
        P.query.filter_by.return_value.all.return_value = [partner]
        D = mocker.patch("models.PartnerProfitDistribution")
        D.query.filter_by.return_value.first.return_value = None
        D.return_value = MagicMock(id=1)
        mocker.patch.object(
            PartnerService,
            "calculate_scope_profit",
            return_value={
                "revenue": 0.0,
                "cogs": 0.0,
                "expenses": 0.0,
                "commissions": 0.0,
                "gross_profit": 0.0,
                "net_profit": -1000.0,
            },
        )
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.flush.side_effect = [None, RuntimeError("fail")]
        with pytest.raises(RuntimeError):
            PartnerService.create_distributions(1, date(2026, 1, 1), date(2026, 1, 31))

    def test_pay_without_partner_row_still_marks_paid(self, mocker):
        dist = MagicMock(status="approved", tenant_id=1, net_due=200.0, id=7, partner_id=999)
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.get.side_effect = [dist, None]
        mocker.patch("utils.tax_settings._resolve_main_branch", return_value=1)
        mocker.patch("services.gl_service.GLService.get_account_code_for_concept", return_value="2150")
        mocker.patch("services.gl_service.GLService.get_default_liquidity_account", return_value="1120")
        mocker.patch("services.gl_posting.post_or_fail")
        assert PartnerService.pay_distribution(7, tenant_id=1) is True

    def test_add_transaction_flush_failure(self, mocker):
        partner = _partner(current_balance=Decimal("0"))
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.get.return_value = partner
        mocker.patch("utils.currency_utils.get_system_default_currency", return_value="AED")
        mocker.patch("models.PartnerTransaction", return_value=MagicMock(id=1))
        mocker.patch("services.gl_posting.post_or_fail")
        mock_db.session.flush.side_effect = [None, RuntimeError("fail")]
        with pytest.raises(RuntimeError):
            PartnerService.add_transaction(1, "adjustment", Decimal("10"))

    def test_unlink_flush_failure(self, mocker):
        customer = MagicMock(tenant_id=1, partner_id=5)
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.get.return_value = customer
        mock_db.session.flush.side_effect = RuntimeError("db")
        with pytest.raises(RuntimeError):
            PartnerService.unlink_product_partner(1, partner_id=5, tenant_id=1)


class TestUnifiedGuards:
    def test_missing_partner(self, mocker):
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.get.return_value = None
        assert PartnerService.get_unified_statement(1, 1) == {}

    def test_wrong_tenant(self, mocker):
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.get.return_value = _partner(tenant_id=2)
        assert PartnerService.get_unified_statement(1, 1) == {}

    def test_no_linked_customers(self, mocker):
        partner = _partner(current_balance=Decimal("15"))
        mock_db = mocker.patch("services.partner_service.db")
        mock_db.session.get.return_value = partner
        D = mocker.patch("models.PartnerProfitDistribution")
        D.query.filter_by.return_value.order_by.return_value.all.return_value = []
        C = mocker.patch("models.Customer")
        C.query.filter_by.return_value.all.return_value = []
        mocker.patch("models.PartnerCommissionEntry")
        out = PartnerService.get_unified_statement(1, 1)
        assert out["product_commissions_total"] == 0.0
        assert out["combined_total"] == 0.0


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
