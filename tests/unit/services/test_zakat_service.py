"""Zakat service — 2.5% of the net-working-capital base, idempotent per FY."""

from decimal import Decimal

import pytest

from models import GLAccount, GLJournalEntry, GLJournalLine
from services.zakat_service import ZakatService


def _post_nwc(db_session, tenant, branch, *, assets=Decimal("10000"), liabilities=Decimal("4000")):
    from utils.tenanting import without_tenant_scope

    with without_tenant_scope():
        cash = GLAccount.query.filter_by(tenant_id=tenant.id, code="1111").first()
        ap = GLAccount.query.filter_by(tenant_id=tenant.id, code="2111").first()
        suspense = GLAccount.query.filter_by(tenant_id=tenant.id, code="2999").first()
        entry = GLJournalEntry(
            tenant_id=tenant.id,
            branch_id=branch.id,
            entry_number="ZAK-TEST-1",
            description="NWC setup",
            reference_type="Manual",
            reference_id=1,
            status="posted",
            total_debit=assets,
            total_credit=assets,
        )
        db_session.add(entry)
        db_session.flush()
        db_session.add(
            GLJournalLine(
                tenant_id=tenant.id, entry_id=entry.id, account_id=cash.id, debit=assets, credit=0, amount_aed=assets
            )
        )
        db_session.add(
            GLJournalLine(
                tenant_id=tenant.id,
                entry_id=entry.id,
                account_id=ap.id,
                debit=0,
                credit=liabilities,
                amount_aed=-liabilities,
            )
        )
        db_session.add(
            GLJournalLine(
                tenant_id=tenant.id,
                entry_id=entry.id,
                account_id=suspense.id,
                debit=0,
                credit=assets - liabilities,
                amount_aed=-(assets - liabilities),
            )
        )
        db_session.flush()
    return entry


class TestZakatService:
    def test_estimate_returns_zero_when_base_is_zero(self, db_session, sample_tenant, sample_branch):
        tenant = sample_tenant
        tenant.enable_zakat = True
        db_session.commit()
        est = ZakatService.estimate(tenant.id, fiscal_year=2026)
        assert est["zakat_base"] == Decimal("0.000")
        assert est["zakat"] == Decimal("0.000")

    def test_estimate_computes_nwc_base(self, db_session, sample_tenant, sample_branch):
        tenant = sample_tenant
        tenant.enable_zakat = True
        db_session.commit()
        _post_nwc(db_session, tenant, sample_branch, assets=Decimal("10000"), liabilities=Decimal("4000"))
        est = ZakatService.estimate(tenant.id, fiscal_year=2026)
        assert est["current_assets"] == Decimal("10000")
        assert est["current_liabilities"] == Decimal("4000")
        assert est["zakat_base"] == Decimal("6000.000")
        assert est["zakat"] == Decimal("150.000")

    def test_accrue_disabled_raises(self, db_session, sample_tenant, sample_branch):
        tenant = sample_tenant
        tenant.enable_zakat = False
        db_session.commit()
        with pytest.raises(ValueError, match="enable_zakat"):
            ZakatService.accrue(tenant.id, 2026, branch_id=sample_branch.id, user_id=1)

    def test_accrue_idempotent(self, db_session, sample_tenant, sample_branch):
        tenant = sample_tenant
        tenant.enable_zakat = True
        db_session.commit()
        _post_nwc(db_session, tenant, sample_branch)
        first = ZakatService.accrue(tenant.id, 2026, branch_id=sample_branch.id, user_id=1)
        assert first["already_accrued"] is False
        assert first["zakat"] == Decimal("150.000")
        second = ZakatService.accrue(tenant.id, 2026, branch_id=sample_branch.id, user_id=1)
        assert second["already_accrued"] is True
        assert second["zakat"] is None

    def test_accrue_zero_base_posts_nothing(self, db_session, sample_tenant, sample_branch):
        tenant = sample_tenant
        tenant.enable_zakat = True
        db_session.commit()
        result = ZakatService.accrue(tenant.id, 2026, branch_id=sample_branch.id, user_id=1)
        assert result["already_accrued"] is False
        assert result["zakat"] == Decimal("0.000")
        assert result["entry"] is None
