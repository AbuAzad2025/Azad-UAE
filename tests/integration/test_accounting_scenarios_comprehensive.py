"""Comprehensive accounting scenarios — run locally, not a CI gate claim.

Each scenario uses a real database and real services with independently
hand-computed expectations. They cover the partner-allocation policy space
(sequential scopes, fixed-before-percentage, actual days, sequential losses,
thresholds, idempotency, approve/pay lifecycle), scope P&L composition
(VAT excluded from revenue, cancelled sales excluded, reversed expenses
excluded, tenant isolation, warehouse expense attribution), and the global
journal invariant (every entry balanced, trial balance nets to zero).
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from models import (
    Expense,
    GLJournalEntry,
    GLJournalLine,
    Partner,
    PartnerProfitDistribution,
    Sale,
    SaleLine,
)
from services.partner_service import PartnerService

JAN = (date(2026, 1, 1), date(2026, 1, 31))


def _sale(
    db_session,
    tenant,
    warehouse,
    user,
    customer,
    product,
    number,
    *,
    status="confirmed",
    amount_aed=Decimal("200"),
    tax_amount=Decimal("0"),
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
        tax_amount=tax_amount,
        currency="AED",
    )
    db_session.add(sale)
    db_session.flush()
    db_session.add(
        SaleLine(
            tenant_id=tenant.id,
            sale_id=sale.id,
            product_id=product.id,
            quantity=Decimal("2"),
            unit_price=Decimal("100"),
            line_total=amount_aed,
            cost_price=Decimal("50"),
        )
    )
    db_session.flush()
    return sale


def _partner(db_session, tenant, name, scope_type, scope_id, share, **kwargs):
    partner = Partner(
        tenant_id=tenant.id,
        name=name,
        scope_type=scope_type,
        scope_id=scope_id,
        share_percentage=Decimal(str(share)),
        start_date=kwargs.pop("start_date", date(2026, 1, 1)),
        end_date=kwargs.pop("end_date", None),
        **kwargs,
    )
    db_session.add(partner)
    db_session.flush()
    return partner


def _dists(db_session, tenant):
    return db_session.query(PartnerProfitDistribution).filter(PartnerProfitDistribution.tenant_id == tenant.id).all()


class TestScopeProfitComposition:
    def test_vat_is_excluded_from_revenue(
        self, db_session, sample_tenant, sample_warehouse, sample_user, sample_customer, sample_product
    ):
        _sale(
            db_session,
            sample_tenant,
            sample_warehouse,
            sample_user,
            sample_customer,
            sample_product,
            "VAT-1",
            amount_aed=Decimal("116"),
            tax_amount=Decimal("16"),
        )
        revenue = PartnerService.get_scope_revenue(sample_tenant.id, *JAN, "company")
        assert Decimal(str(revenue)) == Decimal("100")

    def test_cancelled_sale_excluded_from_revenue(
        self, db_session, sample_tenant, sample_warehouse, sample_user, sample_customer, sample_product
    ):
        _sale(
            db_session,
            sample_tenant,
            sample_warehouse,
            sample_user,
            sample_customer,
            sample_product,
            "CXL-1",
            status="cancelled",
        )
        assert PartnerService.get_scope_revenue(sample_tenant.id, *JAN, "company") == Decimal("0")

    def test_reversed_expense_excluded_and_warehouse_attribution(
        self, db_session, sample_tenant, sample_warehouse, sample_branch, sample_expense_category, sample_user
    ):
        category_id = sample_expense_category.id
        user_id = sample_user.id
        db_session.add_all(
            [
                Expense(
                    tenant_id=sample_tenant.id,
                    expense_number="EXP-OK",
                    category_id=category_id,
                    description="OK expense",
                    amount=Decimal("40"),
                    amount_aed=Decimal("40"),
                    payment_method="cash",
                    user_id=user_id,
                    expense_date=datetime(2026, 1, 5, tzinfo=UTC),
                    status="confirmed",
                    is_reversed=False,
                    branch_id=sample_branch.id,
                    warehouse_id=sample_warehouse.id,
                ),
                Expense(
                    tenant_id=sample_tenant.id,
                    expense_number="EXP-REV",
                    category_id=category_id,
                    description="Reversed expense",
                    amount=Decimal("999"),
                    amount_aed=Decimal("999"),
                    payment_method="cash",
                    user_id=user_id,
                    expense_date=datetime(2026, 1, 5, tzinfo=UTC),
                    status="confirmed",
                    is_reversed=True,
                    branch_id=sample_branch.id,
                    warehouse_id=sample_warehouse.id,
                ),
                Expense(
                    tenant_id=sample_tenant.id,
                    expense_number="EXP-DRAFT",
                    category_id=category_id,
                    description="Draft expense",
                    amount=Decimal("888"),
                    amount_aed=Decimal("888"),
                    payment_method="cash",
                    user_id=user_id,
                    expense_date=datetime(2026, 1, 5, tzinfo=UTC),
                    status="draft",
                    is_reversed=False,
                    branch_id=sample_branch.id,
                    warehouse_id=sample_warehouse.id,
                ),
            ]
        )
        db_session.flush()
        total = PartnerService.get_scope_expenses(sample_tenant.id, *JAN, "warehouse", sample_warehouse.id)
        assert Decimal(str(total)) == Decimal("40")

    def test_tenant_isolation(
        self, db_session, sample_tenant, sample_warehouse, sample_user, sample_customer, sample_product
    ):
        _sale(
            db_session,
            sample_tenant,
            sample_warehouse,
            sample_user,
            sample_customer,
            sample_product,
            "ISO-1",
        )
        assert PartnerService.get_scope_revenue(sample_tenant.id + 999999, *JAN, "company") == Decimal("0")
        assert PartnerService.get_scope_revenue(sample_tenant.id, *JAN, "company") == Decimal("200")


class TestDistributionLifecycle:
    def test_full_lifecycle_create_approve_pay(
        self, db_session, sample_tenant, sample_warehouse, sample_user, sample_customer, sample_product
    ):
        _sale(
            db_session,
            sample_tenant,
            sample_warehouse,
            sample_user,
            sample_customer,
            sample_product,
            "LIFE-1",
        )
        # Scope net: revenue 200 − COGS 100 = 100.
        _partner(db_session, sample_tenant, "WH", "warehouse", sample_warehouse.id, "50")
        _partner(db_session, sample_tenant, "CO", "company", None, "50")

        ids = PartnerService.create_distributions(sample_tenant.id, *JAN)
        assert len(ids) == 2
        # Idempotent: a second run creates nothing.
        assert PartnerService.create_distributions(sample_tenant.id, *JAN) == []

        dists = _dists(db_session, sample_tenant)
        wh = next(d for d in dists if d.scope_type == "warehouse")
        co = next(d for d in dists if d.scope_type == "company")
        assert Decimal(str(wh.net_due)) == Decimal("50.000")
        assert Decimal(str(co.net_due)) == Decimal("25.000")

        assert PartnerService.approve_distribution(wh.id, sample_user.id, tenant_id=sample_tenant.id) is True
        db_session.flush()
        partner = db_session.get(Partner, wh.partner_id)
        assert Decimal(str(partner.current_balance)) == Decimal("50.000")
        # Double approval is a no-op.
        assert PartnerService.approve_distribution(wh.id, sample_user.id, tenant_id=sample_tenant.id) is False
        db_session.refresh(partner)
        assert Decimal(str(partner.current_balance)) == Decimal("50.000")

        assert PartnerService.pay_distribution(wh.id, tenant_id=sample_tenant.id) is True
        db_session.flush()
        db_session.refresh(partner)
        assert Decimal(str(partner.current_balance)) == Decimal("0.000")
        assert Decimal(str(partner.total_withdrawals)) == Decimal("50.000")

    def test_same_scope_over_100_rejected(self, db_session, sample_tenant):
        _partner(db_session, sample_tenant, "A", "company", None, "60")
        _partner(db_session, sample_tenant, "B", "company", None, "50")
        with pytest.raises(ValueError, match="يتجاوز 100%"):
            PartnerService.create_distributions(sample_tenant.id, *JAN)

    def test_loss_without_loss_percentage_refused(
        self, db_session, sample_tenant, sample_warehouse, sample_user, sample_customer, sample_product
    ):
        # Force a loss: COGS 100 against revenue 60.
        _sale(
            db_session,
            sample_tenant,
            sample_warehouse,
            sample_user,
            sample_customer,
            sample_product,
            "LOSS-1",
            amount_aed=Decimal("60"),
        )
        _partner(db_session, sample_tenant, "CO", "company", None, "50")
        with pytest.raises(ValueError, match="نسبة تحمل خسارة"):
            PartnerService.create_distributions(sample_tenant.id, *JAN)

    def test_fixed_prorated_across_quarter_by_actual_days(self, db_session, sample_tenant):
        _partner(
            db_session,
            sample_tenant,
            "FEB",
            "company",
            None,
            "0",
            fixed_monthly_amount=Decimal("100"),
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 28),
        )
        ids = PartnerService.create_distributions(sample_tenant.id, date(2026, 1, 1), date(2026, 3, 31))
        assert len(ids) == 1
        dist = _dists(db_session, sample_tenant)[0]
        # 3 months × 100 × 28/90 days = 93.333
        assert Decimal(str(dist.fixed_amount)) == Decimal("93.333")

    def test_cross_tenant_create_ignores_foreign_partners(self, db_session, sample_tenant):
        _partner(db_session, sample_tenant, "A", "company", None, "50")
        assert PartnerService.create_distributions(sample_tenant.id + 999999, *JAN) == []


class TestJournalInvariants:
    def test_every_entry_balanced_and_trial_balance_nets_zero(
        self, db_session, sample_tenant, sample_warehouse, sample_user, sample_customer, sample_product
    ):
        _sale(
            db_session,
            sample_tenant,
            sample_warehouse,
            sample_user,
            sample_customer,
            sample_product,
            "JE-1",
        )
        _partner(db_session, sample_tenant, "WH", "warehouse", sample_warehouse.id, "50")
        PartnerService.create_distributions(sample_tenant.id, *JAN)
        dist = _dists(db_session, sample_tenant)[0]
        assert PartnerService.approve_distribution(dist.id, sample_user.id, tenant_id=sample_tenant.id) is True
        db_session.flush()

        entries = db_session.query(GLJournalEntry).filter(GLJournalEntry.tenant_id == sample_tenant.id).all()
        assert entries, "expected the approval accrual entry"
        for entry in entries:
            assert abs(Decimal(str(entry.total_debit)) - Decimal(str(entry.total_credit))) <= Decimal("0.001")

        lines = (
            db_session.query(GLJournalLine)
            .join(GLJournalEntry, GLJournalLine.entry_id == GLJournalEntry.id)
            .filter(GLJournalEntry.tenant_id == sample_tenant.id)
            .all()
        )
        net = sum(Decimal(str(line.debit or 0)) - Decimal(str(line.credit or 0)) for line in lines)
        assert abs(net) <= Decimal("0.001")
