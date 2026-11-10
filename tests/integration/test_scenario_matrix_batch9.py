"""Scenario matrix batch 9 — integration extras: scope, returns, lifecycle, unified."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from models import Partner, ProductReturn, ProductReturnLine, Sale, SaleLine
from services.partner_service import PartnerService

JAN = (date(2026, 1, 1), date(2026, 1, 31))
FEB = (date(2026, 2, 1), date(2026, 2, 28))


def _mk_sale(db_session, tenant, warehouse, user, customer, product, number, *, qty, price, cost, amount):
    sale = Sale(
        tenant_id=tenant.id, sale_number=number, customer_id=customer.id, seller_id=user.id,
        branch_id=warehouse.branch_id, warehouse_id=warehouse.id,
        sale_date=datetime(2026, 1, 10, tzinfo=UTC), status="confirmed",
        subtotal=amount, total_amount=amount, amount=amount, amount_aed=amount,
        tax_amount=Decimal("0"), currency="AED",
    )
    db_session.add(sale)
    db_session.flush()
    line = SaleLine(
        tenant_id=tenant.id, sale_id=sale.id, product_id=product.id, quantity=Decimal(str(qty)),
        unit_price=Decimal(str(price)), line_total=amount, cost_price=Decimal(str(cost)),
    )
    db_session.add(line)
    db_session.flush()
    return sale, line


class TestScopeExtraGrid:
    @pytest.mark.parametrize(
        "qty,price,cost",
        [(1, 150, 100), (3, 70, 60), (4, 55, 40), (6, 90, 80), (9, 25, 24), (2, 500, 400)],
    )
    def test_scope_grid_b(self, db_session, sample_tenant, sample_warehouse, sample_user,
                          sample_customer, sample_product, qty, price, cost):
        amount = Decimal(str(qty)) * Decimal(str(price))
        _mk_sale(db_session, sample_tenant, sample_warehouse, sample_user, sample_customer,
                 sample_product, f"B9-{qty}-{price}-{cost}", qty=qty, price=price, cost=cost, amount=amount)
        pnl = PartnerService.calculate_scope_profit(sample_tenant.id, *JAN, "company")
        assert Decimal(str(pnl["revenue"])) == amount
        assert Decimal(str(pnl["net_profit"])) == amount - Decimal(str(qty)) * Decimal(str(cost))


class TestReturnsExtraGrid:
    @pytest.mark.parametrize("ret", [1, 2, 3])
    def test_partial_returns_grid(self, db_session, sample_tenant, sample_warehouse, sample_user,
                                 sample_customer, sample_product, ret):
        sale, line = _mk_sale(db_session, sample_tenant, sample_warehouse, sample_user, sample_customer,
                              sample_product, f"R9-{ret}", qty=4, price=100, cost=50, amount=Decimal("400"))
        r = ProductReturn(
            tenant_id=sample_tenant.id, return_number=f"R9-{ret}-R", sale_id=sale.id,
            customer_id=sample_customer.id, branch_id=sale.branch_id,
            return_date=datetime(2026, 2, 10, tzinfo=UTC), status="approved",
            total_amount=Decimal("100"), refund_amount=Decimal("100"), amount_aed=Decimal("100"),
            currency="AED",
        )
        db_session.add(r)
        db_session.flush()
        db_session.add(
            ProductReturnLine(
                tenant_id=sample_tenant.id, return_id=r.id, sale_line_id=line.id,
                product_id=sample_product.id, quantity=Decimal(str(ret)),
                unit_price=Decimal("100"), line_total=Decimal("100"),
            )
        )
        db_session.flush()
        expected_rev = -Decimal(str(ret)) * Decimal("100")
        expected_cogs = -Decimal(str(ret)) * Decimal("50")
        assert PartnerService.get_scope_revenue(sample_tenant.id, *FEB, "company") == expected_rev
        assert PartnerService.get_scope_cogs(sample_tenant.id, *FEB, "company") == expected_cogs


class TestLifecycleVariants:
    @pytest.mark.parametrize("share", ["25", "50", "75", "100"])
    def test_approve_variants(self, db_session, sample_tenant, sample_warehouse, sample_user,
                              sample_customer, sample_product, share):
        _mk_sale(db_session, sample_tenant, sample_warehouse, sample_user, sample_customer,
                 sample_product, f"LC-{share}", qty=2, price=100, cost=50, amount=Decimal("200"))
        partner = Partner(
            tenant_id=sample_tenant.id, name=f"P{share}", scope_type="company",
            share_percentage=Decimal(share), start_date=date(2026, 1, 1),
        )
        db_session.add(partner)
        db_session.flush()
        PartnerService.create_distributions(sample_tenant.id, *JAN)
        from models import PartnerProfitDistribution

        dist = (
            db_session.query(PartnerProfitDistribution)
            .filter_by(tenant_id=sample_tenant.id, partner_id=partner.id)
            .first()
        )
        expected = (Decimal("100") * Decimal(share) / Decimal("100")).quantize(Decimal("0.001"))
        assert Decimal(str(dist.net_due)) == expected
        assert PartnerService.approve_distribution(dist.id, sample_user.id, tenant_id=sample_tenant.id) is True
        db_session.flush()
        db_session.refresh(partner)
        assert Decimal(str(partner.current_balance)) == expected
