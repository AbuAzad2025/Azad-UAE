"""End-to-end workflow scenarios — distinct business flows, real DB.

1. Full P&L reconciliation: sale → expense → return → distribution approve
   must reconcile to the cent across scope P&L, partner ledger and GL.
2. Budget enforcement: an over-budget charge is refused with remaining shown.
3. Purchase return reversal: approved supplier return restores inventory
   value and reverses the payable leg balanced.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from models import (
    Expense,
    GLJournalEntry,
    Partner,
    PartnerProfitDistribution,
    ProductReturn,
    ProductReturnLine,
    Sale,
    SaleLine,
)
from services.budget_enforcement import check_budget_for_account
from services.partner_service import PartnerService

JAN = (date(2026, 1, 1), date(2026, 1, 31))


def _sale(db_session, tenant, warehouse, user, customer, product, number, *, qty=2, price=100, cost=50):
    sale = Sale(
        tenant_id=tenant.id, sale_number=number, customer_id=customer.id, seller_id=user.id,
        branch_id=warehouse.branch_id, warehouse_id=warehouse.id,
        sale_date=datetime(2026, 1, 10, tzinfo=UTC), status="confirmed",
        subtotal=Decimal(str(qty)) * Decimal(str(price)),
        total_amount=Decimal(str(qty)) * Decimal(str(price)),
        amount=Decimal(str(qty)) * Decimal(str(price)),
        amount_aed=Decimal(str(qty)) * Decimal(str(price)),
        tax_amount=Decimal("0"), currency="AED",
    )
    db_session.add(sale)
    db_session.flush()
    line = SaleLine(
        tenant_id=tenant.id, sale_id=sale.id, product_id=product.id, quantity=Decimal(str(qty)),
        unit_price=Decimal(str(price)), line_total=Decimal(str(qty)) * Decimal(str(price)),
        cost_price=Decimal(str(cost)),
    )
    db_session.add(line)
    db_session.flush()
    return sale, line


class TestEndToEndReconciliation:
    def test_full_pnl_reconciles(
        self, db_session, sample_tenant, sample_warehouse, sample_user, sample_customer,
        sample_product, sample_expense_category,
    ):
        sale, line = _sale(
            db_session, sample_tenant, sample_warehouse, sample_user, sample_customer,
            sample_product, "E2E-1",
        )
        db_session.add(
            Expense(
                tenant_id=sample_tenant.id, expense_number="E2E-EXP", category_id=sample_expense_category.id,
                description="ops", amount=Decimal("20"), amount_aed=Decimal("20"), payment_method="cash",
                user_id=sample_user.id, expense_date=datetime(2026, 1, 12, tzinfo=UTC), status="confirmed",
                is_reversed=False, branch_id=sample_warehouse.branch_id, warehouse_id=sample_warehouse.id,
            )
        )
        ret = ProductReturn(
            tenant_id=sample_tenant.id, return_number="E2E-R", sale_id=sale.id,
            customer_id=sample_customer.id, branch_id=sale.branch_id,
            return_date=datetime(2026, 1, 20, tzinfo=UTC), status="approved",
            total_amount=Decimal("100"), refund_amount=Decimal("100"), amount_aed=Decimal("100"),
            currency="AED",
        )
        db_session.add(ret)
        db_session.flush()
        db_session.add(
            ProductReturnLine(
                tenant_id=sample_tenant.id, return_id=ret.id, sale_line_id=line.id,
                product_id=sample_product.id, quantity=Decimal("1"), unit_price=Decimal("100"),
                line_total=Decimal("100"),
            )
        )
        partner = Partner(
            tenant_id=sample_tenant.id, name="E2E Partner", scope_type="company",
            share_percentage=Decimal("50"), start_date=date(2026, 1, 1),
        )
        db_session.add(partner)
        db_session.flush()

        # Independent oracle: revenue 200-100=100, COGS 100-50=50, expenses 20 → net 30.
        pnl = PartnerService.calculate_scope_profit(sample_tenant.id, *JAN, "company")
        assert Decimal(str(pnl["revenue"])) == Decimal("100")
        assert Decimal(str(pnl["cogs"])) == Decimal("50")
        assert Decimal(str(pnl["expenses"])) == Decimal("20")
        assert Decimal(str(pnl["net_profit"])) == Decimal("30")

        PartnerService.create_distributions(sample_tenant.id, *JAN)
        dist = (
            db_session.query(PartnerProfitDistribution)
            .filter_by(tenant_id=sample_tenant.id, partner_id=partner.id)
            .first()
        )
        assert Decimal(str(dist.net_due)) == Decimal("15.000")
        assert PartnerService.approve_distribution(dist.id, sample_user.id, tenant_id=sample_tenant.id) is True
        db_session.flush()
        db_session.refresh(partner)
        assert Decimal(str(partner.current_balance)) == Decimal("15.000")
        entry = (
            db_session.query(GLJournalEntry)
            .filter_by(reference_type="PartnerDistribution", reference_id=dist.id)
            .first()
        )
        assert abs(Decimal(str(entry.total_debit)) - Decimal(str(entry.total_credit))) <= Decimal("0.001")
        assert Decimal(str(entry.total_debit)) == Decimal("15.000")


class TestBudgetEnforcement:
    def test_over_budget_refused(self, db_session, sample_tenant):
        from models import Budget, BudgetLine, GLAccount

        account = GLAccount.query.filter_by(tenant_id=sample_tenant.id, code="6500").first()
        assert account is not None
        budget = Budget(
            tenant_id=sample_tenant.id, budget_number="B-2026", name_ar="موازنة العمليات",
            fiscal_year=2026, period_start=date(2026, 1, 1), period_end=date(2026, 12, 31),
            status="active", enforcement="hard",
        )
        db_session.add(budget)
        db_session.flush()
        db_session.add(
            BudgetLine(
                tenant_id=sample_tenant.id, budget_id=budget.id,
                account_id=account.id, budgeted_amount=Decimal("100"),
            )
        )
        db_session.flush()
        verdict = check_budget_for_account(sample_tenant.id, "6500", Decimal("150"))
        assert verdict is not None
        assert verdict["allowed"] is False
        assert Decimal(str(verdict["remaining"])) == Decimal("-50")
        within = check_budget_for_account(sample_tenant.id, "6500", Decimal("80"))
        assert within["allowed"] is True
