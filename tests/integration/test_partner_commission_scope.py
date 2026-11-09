"""Returns in a later period must reverse commissions only in their own scope."""

from datetime import UTC, date, datetime
from decimal import Decimal

from models import (
    Branch,
    Partner,
    PartnerCommissionEntry,
    PartnerProfitDistribution,
    ProductReturn,
    ProductReturnLine,
    Sale,
    SaleLine,
    Warehouse,
)
from services.partner_service import PartnerService


def test_commission_reversals_respect_warehouse_and_return_state(
    db_session, sample_tenant, sample_warehouse, sample_user, sample_customer, sample_product
):
    other_branch = Branch(tenant_id=sample_tenant.id, name="Other commission branch", code="COM-OTHER")
    db_session.add(other_branch)
    db_session.flush()
    other_warehouse = Warehouse(
        tenant_id=sample_tenant.id, branch_id=other_branch.id, name="Other commission warehouse"
    )
    db_session.add(other_warehouse)
    db_session.flush()
    for number, warehouse, commission in (
        ("A", sample_warehouse, Decimal("20")),
        ("B", other_warehouse, Decimal("30")),
    ):
        sale = Sale(
            tenant_id=sample_tenant.id,
            sale_number=f"COM-{number}",
            customer_id=sample_customer.id,
            seller_id=sample_user.id,
            branch_id=warehouse.branch_id,
            warehouse_id=warehouse.id,
            sale_date=datetime(2026, 1, 10, tzinfo=UTC),
            status="confirmed",
            subtotal=Decimal("100"),
            total_amount=Decimal("100"),
            amount=Decimal("100"),
            amount_aed=Decimal("100"),
            currency="AED",
        )
        db_session.add(sale)
        db_session.flush()
        line = SaleLine(
            tenant_id=sample_tenant.id,
            sale_id=sale.id,
            product_id=sample_product.id,
            quantity=Decimal("2"),
            unit_price=Decimal("50"),
            line_total=Decimal("100"),
        )
        db_session.add(line)
        db_session.flush()
        db_session.add(
            PartnerCommissionEntry(
                tenant_id=sample_tenant.id,
                sale_id=sale.id,
                sale_line_id=line.id,
                partner_customer_id=sample_customer.id,
                percentage=Decimal("20"),
                base_amount_aed=Decimal("100"),
                commission_amount_aed=commission,
            )
        )
        for state in ("approved", "pending"):
            returned = ProductReturn(
                tenant_id=sample_tenant.id,
                return_number=f"COM-{number}-{state}",
                sale_id=sale.id,
                customer_id=sample_customer.id,
                branch_id=warehouse.branch_id,
                return_date=datetime(2026, 2, 10, tzinfo=UTC),
                status=state,
                total_amount=Decimal("50"),
                refund_amount=Decimal("50"),
                amount_aed=Decimal("50"),
                currency="AED",
            )
            db_session.add(returned)
            db_session.flush()
            db_session.add(
                ProductReturnLine(
                    tenant_id=sample_tenant.id,
                    return_id=returned.id,
                    sale_line_id=line.id,
                    product_id=sample_product.id,
                    quantity=Decimal("1"),
                    unit_price=Decimal("50"),
                    line_total=Decimal("50"),
                )
            )
    db_session.flush()

    january = (date(2026, 1, 1), date(2026, 1, 31))
    february = (date(2026, 2, 1), date(2026, 2, 28))
    assert PartnerService.get_scope_commissions(
        sample_tenant.id, *january, "warehouse", sample_warehouse.id
    ) == Decimal("20")
    assert PartnerService.get_scope_commissions(
        sample_tenant.id, *february, "warehouse", sample_warehouse.id
    ) == Decimal("-10")
    assert PartnerService.get_scope_commissions(
        sample_tenant.id, *february, "warehouse", other_warehouse.id
    ) == Decimal("-15")
    assert PartnerService.get_scope_commissions(
        sample_tenant.id, *february, "branch", sample_warehouse.branch_id
    ) == Decimal("-10")
    assert PartnerService.get_scope_commissions(sample_tenant.id, *february, "branch", other_branch.id) == Decimal(
        "-15"
    )
    assert PartnerService.get_scope_commissions(sample_tenant.id, *february, "company") == Decimal("-25")
    assert PartnerService.get_scope_commissions(sample_tenant.id + 999999, *february, "company") == Decimal("0")


def test_unlink_requires_the_actual_partner_and_tenant(db_session, sample_tenant, sample_customer):
    first = Partner(tenant_id=sample_tenant.id, name="First company partner")
    second = Partner(tenant_id=sample_tenant.id, name="Second company partner")
    db_session.add_all([first, second])
    db_session.flush()
    sample_customer.customer_type = "partner"
    sample_customer.partner_id = first.id
    db_session.flush()

    assert not PartnerService.unlink_product_partner(
        sample_customer.id, partner_id=second.id, tenant_id=sample_tenant.id
    )
    assert not PartnerService.unlink_product_partner(
        sample_customer.id, partner_id=first.id, tenant_id=sample_tenant.id + 999999
    )
    db_session.refresh(sample_customer)
    assert sample_customer.partner_id == first.id
    assert PartnerService.unlink_product_partner(sample_customer.id, partner_id=first.id, tenant_id=sample_tenant.id)
    db_session.refresh(sample_customer)
    assert sample_customer.partner_id is None


def test_expenses_are_not_deducted_twice_from_partner_share(
    db_session, sample_tenant, sample_sale, sample_product, sample_expense
):
    now = datetime.now(UTC)
    sample_sale.sale_date = now
    sample_sale.status = "confirmed"
    sample_sale.amount_aed = Decimal("210")
    sample_sale.tax_amount = Decimal("10")
    sample_sale.exchange_rate = Decimal("1")
    sample_expense.expense_date = now
    sample_expense.amount = Decimal("20")
    sample_expense.amount_aed = Decimal("20")
    sample_expense.status = "confirmed"
    sample_expense.is_reversed = False
    line = SaleLine(
        tenant_id=sample_tenant.id,
        sale_id=sample_sale.id,
        product_id=sample_product.id,
        quantity=Decimal("2"),
        unit_price=Decimal("100"),
        line_total=Decimal("200"),
        cost_price=Decimal("50"),
    )
    partner = Partner(
        tenant_id=sample_tenant.id,
        name="Expense sharing partner",
        scope_type="company",
        share_percentage=Decimal("50"),
        expense_share_percentage=Decimal("20"),
        loss_share_percentage=Decimal("0"),
        fixed_monthly_amount=Decimal("0"),
    )
    db_session.add_all([line, partner])
    db_session.flush()

    ids = PartnerService.create_distributions(sample_tenant.id, now.date(), now.date())
    assert len(ids) == 1
    distribution = db_session.get(PartnerProfitDistribution, ids[0])
    assert distribution.total_revenue == Decimal("200.000")
    assert distribution.total_cogs == Decimal("100.000")
    assert distribution.total_expenses == Decimal("20.000")
    assert distribution.net_profit == Decimal("80.000")
    assert distribution.share_amount == Decimal("40.000")
    assert distribution.expense_share_amount == Decimal("0.000")
    assert distribution.net_due == Decimal("40.000")
