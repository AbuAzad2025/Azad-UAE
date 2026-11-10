"""Real-DB golden scenario: sequential partner allocation reconciles to the sale.

A single confirmed sale (revenue 200 AED, COGS 100 AED → scope net 100 AED)
with a warehouse partner at 50% and a company partner at 50% must allocate
50 to the warehouse partner and 25 to the company partner — the warehouse
entitlement reduces the company pot instead of paying the same profit twice.
Approving the warehouse distribution must leave the GL entry balanced and the
partner ledger in sync.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from models import GLJournalEntry, Partner, Sale, SaleLine
from services.partner_service import PartnerService


def test_sequential_allocation_reconciles_to_scope_profit(
    db_session, sample_tenant, sample_warehouse, sample_user, sample_customer, sample_product
):
    sale = Sale(
        tenant_id=sample_tenant.id,
        sale_number="DIST-GOLD-1",
        customer_id=sample_customer.id,
        seller_id=sample_user.id,
        branch_id=sample_warehouse.branch_id,
        warehouse_id=sample_warehouse.id,
        sale_date=datetime(2026, 1, 10, tzinfo=UTC),
        status="confirmed",
        subtotal=Decimal("200"),
        total_amount=Decimal("200"),
        amount=Decimal("200"),
        amount_aed=Decimal("200"),
        tax_amount=Decimal("0"),
        currency="AED",
    )
    db_session.add(sale)
    db_session.flush()
    db_session.add(
        SaleLine(
            tenant_id=sample_tenant.id,
            sale_id=sale.id,
            product_id=sample_product.id,
            quantity=Decimal("2"),
            unit_price=Decimal("100"),
            line_total=Decimal("200"),
            cost_price=Decimal("50"),
        )
    )
    warehouse_partner = Partner(
        tenant_id=sample_tenant.id,
        name="Warehouse partner",
        scope_type="warehouse",
        scope_id=sample_warehouse.id,
        share_percentage=Decimal("50"),
        start_date=date(2026, 1, 1),
        end_date=None,
    )
    company_partner = Partner(
        tenant_id=sample_tenant.id,
        name="Company partner",
        scope_type="company",
        scope_id=None,
        share_percentage=Decimal("50"),
        start_date=date(2026, 1, 1),
        end_date=None,
    )
    db_session.add_all([warehouse_partner, company_partner])
    db_session.flush()

    # Independent oracle: revenue 200 − COGS (2 × 50) − expenses 0 − commissions 0.
    pnl = PartnerService.calculate_scope_profit(
        sample_tenant.id, date(2026, 1, 1), date(2026, 1, 31), "warehouse", sample_warehouse.id
    )
    assert Decimal(str(pnl["net_profit"])) == Decimal("100")

    ids = PartnerService.create_distributions(sample_tenant.id, date(2026, 1, 1), date(2026, 1, 31))
    assert len(ids) == 2
    db_session.flush()

    from models import PartnerProfitDistribution

    dists = (
        db_session.query(PartnerProfitDistribution)
        .filter(PartnerProfitDistribution.tenant_id == sample_tenant.id)
        .all()
    )
    by_partner = {d.partner_id: Decimal(str(d.net_due)) for d in dists}
    assert by_partner[warehouse_partner.id] == Decimal("50.000")
    assert by_partner[company_partner.id] == Decimal("25.000")

    warehouse_dist = next(d for d in dists if d.partner_id == warehouse_partner.id)
    assert PartnerService.approve_distribution(warehouse_dist.id, sample_user.id, tenant_id=sample_tenant.id) is True
    db_session.flush()
    db_session.refresh(warehouse_partner)
    assert Decimal(str(warehouse_partner.current_balance)) == Decimal("50.000")

    entry = (
        db_session.query(GLJournalEntry)
        .filter_by(reference_type="PartnerDistribution", reference_id=warehouse_dist.id)
        .order_by(GLJournalEntry.id.desc())
        .first()
    )
    assert entry is not None
    assert abs(Decimal(str(entry.total_debit)) - Decimal(str(entry.total_credit))) <= Decimal("0.001")
    assert Decimal(str(entry.total_debit)) == Decimal("50.000")
