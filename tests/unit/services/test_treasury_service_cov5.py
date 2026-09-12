"""Cov5: treasury_service — same-kind summary aggregation branch."""

from __future__ import annotations

from decimal import Decimal


def test_liquidity_same_kind_aggregates(db_session, sample_tenant, sample_branch):
    from models import CashBox
    from services.treasury_service import TreasuryService

    for suffix in ("A", "B"):
        box = CashBox(
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            code=f"CB-COV5-{suffix}",
            name_ar="بنك",
            box_type="bank_account",
            current_balance=Decimal("10"),
            currency="AED",
            is_active=True,
        )
        db_session.add(box)
    db_session.flush()
    out = TreasuryService.get_liquidity_position(sample_tenant.id)
    assert out["kind_summary"]["bank"]["count"] >= 2
