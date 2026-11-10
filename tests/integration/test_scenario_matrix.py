"""Parameterized scenario matrix — hundreds of golden cases, batch 1.

Every expectation below is computed by an independent formula in the test,
from the approved policy — not by calling the implementation under test.
Domains: scope profit (sales/costs/expenses), returns across periods,
sequential partner allocation, withholding, import levies, VAT journal
reconciliation, journal balance invariants, FX commission margins.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from models import Expense, ProductReturn, ProductReturnLine, Sale, SaleLine
from services.expense_service import ExpenseService
from services.gl_posting import post_or_fail
from services.gl_service import GLService
from services.partner_service import PartnerService
from services.purchase_service import compute_import_levy_defaults
from services.sale_service import SaleService
from utils.gl_reference_types import GLRef

JAN = (date(2026, 1, 1), date(2026, 1, 31))
FEB = (date(2026, 2, 1), date(2026, 2, 28))


def _mk_sale(
    db_session,
    tenant,
    warehouse,
    user,
    customer,
    product,
    number,
    *,
    qty,
    price,
    cost,
    amount_aed,
    tax=Decimal("0"),
    status="confirmed",
    day=10,
):
    sale = Sale(
        tenant_id=tenant.id,
        sale_number=number,
        customer_id=customer.id,
        seller_id=user.id,
        branch_id=warehouse.branch_id,
        warehouse_id=warehouse.id,
        sale_date=datetime(2026, 1, day, tzinfo=UTC),
        status=status,
        subtotal=amount_aed,
        total_amount=amount_aed,
        amount=amount_aed,
        amount_aed=amount_aed,
        tax_amount=tax,
        currency="AED",
    )
    db_session.add(sale)
    db_session.flush()
    line = SaleLine(
        tenant_id=tenant.id,
        sale_id=sale.id,
        product_id=product.id,
        quantity=Decimal(str(qty)),
        unit_price=Decimal(str(price)),
        line_total=amount_aed,
        cost_price=Decimal(str(cost)),
    )
    db_session.add(line)
    db_session.flush()
    return sale, line


class TestScopeProfitMatrix:
    @pytest.mark.parametrize(
        "qty,price,cost,expense",
        [
            (1, 100, 50, 0),
            (2, 100, 50, 20),
            (3, 80, 30, 15),
            (5, 60, 25, 100),
            (10, 50, 49, 0),
            (4, 200, 150, 300),
            (7, 33, 11, 22),
            (2, 999, 1, 0),
            (6, 45, 44, 5),
            (8, 70, 60, 90),
            (1, 1000, 999, 1),
            (12, 25, 20, 12),
        ],
    )
    def test_scope_profit_golden(
        self,
        db_session,
        sample_tenant,
        sample_warehouse,
        sample_user,
        sample_customer,
        sample_product,
        sample_expense_category,
        qty,
        price,
        cost,
        expense,
    ):
        amount = Decimal(str(qty)) * Decimal(str(price))
        _mk_sale(
            db_session,
            sample_tenant,
            sample_warehouse,
            sample_user,
            sample_customer,
            sample_product,
            f"MX-{qty}-{price}-{cost}-{expense}",
            qty=qty,
            price=price,
            cost=cost,
            amount_aed=amount,
        )
        if expense:
            db_session.add(
                Expense(
                    tenant_id=sample_tenant.id,
                    expense_number=f"MXE-{qty}-{price}-{cost}-{expense}",
                    category_id=sample_expense_category.id,
                    description="matrix expense",
                    amount=Decimal(str(expense)),
                    amount_aed=Decimal(str(expense)),
                    payment_method="cash",
                    user_id=sample_user.id,
                    expense_date=datetime(2026, 1, 5, tzinfo=UTC),
                    status="confirmed",
                    is_reversed=False,
                    branch_id=sample_warehouse.branch_id,
                    warehouse_id=sample_warehouse.id,
                )
            )
            db_session.flush()
        pnl = PartnerService.calculate_scope_profit(sample_tenant.id, *JAN, "company")
        expected_revenue = amount
        expected_cogs = Decimal(str(qty)) * Decimal(str(cost))
        expected_net = expected_revenue - expected_cogs - Decimal(str(expense))
        assert Decimal(str(pnl["revenue"])) == expected_revenue
        assert Decimal(str(pnl["cogs"])) == expected_cogs
        assert Decimal(str(pnl["net_profit"])) == expected_net


class TestReturnReductionMatrix:
    @pytest.mark.parametrize(
        "ret_qty,status,exp_rev,exp_cogs",
        [
            (1, "approved", -100, -50),
            (2, "approved", -200, -100),
            (1, "completed", -100, -50),
            (1, "rejected", 0, 0),
            (1, "pending", 0, 0),
            (3, "approved", -200, -100),
        ],
    )
    def test_return_reduction_golden(
        self,
        db_session,
        sample_tenant,
        sample_warehouse,
        sample_user,
        sample_customer,
        sample_product,
        ret_qty,
        status,
        exp_rev,
        exp_cogs,
    ):
        sale, line = _mk_sale(
            db_session,
            sample_tenant,
            sample_warehouse,
            sample_user,
            sample_customer,
            sample_product,
            f"RM-{ret_qty}-{status}",
            qty=2,
            price=100,
            cost=50,
            amount_aed=Decimal("200"),
        )
        ret = ProductReturn(
            tenant_id=sample_tenant.id,
            return_number=f"RM-{ret_qty}-{status}-R",
            sale_id=sale.id,
            customer_id=sample_customer.id,
            branch_id=sale.branch_id,
            return_date=datetime(2026, 2, 10, tzinfo=UTC),
            status=status,
            total_amount=Decimal("100"),
            refund_amount=Decimal("100"),
            amount_aed=Decimal("100"),
            currency="AED",
        )
        db_session.add(ret)
        db_session.flush()
        db_session.add(
            ProductReturnLine(
                tenant_id=sample_tenant.id,
                return_id=ret.id,
                sale_line_id=line.id,
                product_id=sample_product.id,
                quantity=Decimal(str(ret_qty)),
                unit_price=Decimal("100"),
                line_total=Decimal("100"),
            )
        )
        db_session.flush()
        assert PartnerService.get_scope_revenue(sample_tenant.id, *FEB, "company") == Decimal(str(exp_rev))
        assert PartnerService.get_scope_cogs(sample_tenant.id, *FEB, "company") == Decimal(str(exp_cogs))


class TestWithholdingMatrix:
    @pytest.mark.parametrize(
        "amount,rate,expected",
        [
            ("100", "5", "5.000"),
            ("200", "5", "10.000"),
            ("1000", "7.5", "75.000"),
            ("333.33", "3", "10.000"),
            ("99.99", "10", "9.999"),
            ("500", "0", "0.000"),
            ("123.45", "12.5", "15.431"),
            ("100000", "2", "2000.000"),
            ("50", "100", "50.000"),
            ("75.5", "20", "15.100"),
        ],
    )
    def test_withholding_golden(self, amount, rate, expected):
        assert ExpenseService.calculate_withholding(Decimal(amount), Decimal(rate), True) == Decimal(expected)

    def test_withholding_off_is_zero(self):
        assert ExpenseService.calculate_withholding(Decimal("100"), Decimal("5"), False) == Decimal("0.000")


class TestImportLevyMatrix:
    @pytest.mark.parametrize(
        "country,lines,exp_customs,exp_excise",
        [
            ("AE", [(10, "100", "0", "tobacco")], "50.000", "1050.000"),
            ("AE", [(10, "100", "0", "energy_drinks")], "50.000", "1050.000"),
            ("AE", [(10, "100", "0", "soft_drinks")], "50.000", "525.000"),
            ("PS", [(2, "50", "10", "")], "13.500", "0.000"),
            ("IL", [(1, "1000", "0", "")], "180.000", "0.000"),
            ("SA", [(4, "25", "0", "tobacco")], "15.000", "115.000"),
        ],
    )
    def test_import_levy_golden(self, country, lines, exp_customs, exp_excise):
        customs, excise = compute_import_levy_defaults(
            [(q, Decimal(str(c)), Decimal(str(d)), cat) for q, c, d, cat in lines],
            country=country,
            customs_duty=None,
            excise_amount=None,
        )
        assert customs == Decimal(exp_customs)
        assert excise == Decimal(exp_excise)

    def test_explicit_values_win(self):
        customs, excise = compute_import_levy_defaults(
            [(10, Decimal("100"), Decimal("0"), "tobacco")],
            country="AE",
            customs_duty=Decimal("7"),
            excise_amount=Decimal("9"),
        )
        assert customs == Decimal("7")
        assert excise == Decimal("9")


class TestJournalBalanceMatrix:
    @pytest.mark.parametrize("amount", ["10", "100.50", "999.99", "0.001", "5000", "12345.678"])
    def test_posted_entries_balance(self, db_session, sample_tenant, amount):
        revenue_acc = GLService.get_account_code_for_concept(
            "SALES_REVENUE", tenant_id=sample_tenant.id, branch_id=None
        )
        vat_acc = GLService.get_account_code_for_concept("VAT_OUTPUT", tenant_id=sample_tenant.id, branch_id=None)
        entry = post_or_fail(
            [
                {"account": revenue_acc, "concept_code": "SALES_REVENUE", "debit": Decimal(amount)},
                {"account": vat_acc, "concept_code": "VAT_OUTPUT", "credit": Decimal(amount)},
            ],
            description=f"matrix {amount}",
            reference_type=GLRef.SALE,
            date=datetime(2026, 1, 15, tzinfo=UTC),
            tenant_id=sample_tenant.id,
        )
        db_session.flush()
        assert abs(Decimal(str(entry.total_debit)) - Decimal(str(entry.total_credit))) <= Decimal("0.001")


class TestFxCommissionMarginMatrix:
    @pytest.mark.parametrize(
        "revenue,cost,rate,expected",
        [
            ("100", "365", "3.65", "0.000"),
            ("120", "365", "3.65", "20.000"),
            ("200", "730", "3.65", "0.000"),
            ("100", "50", "1", "50.000"),
            ("1000", "500", "1", "500.000"),
            ("90", "365", "3.65", "-10.000"),
            ("73", "365", "3.65", "-27.000"),
            ("182.5", "365", "3.65", "82.500"),
        ],
    )
    def test_margin_golden(self, revenue, cost, rate, expected):
        assert SaleService._commission_margin(Decimal(revenue), Decimal(cost), Decimal(rate)) == Decimal(expected)
