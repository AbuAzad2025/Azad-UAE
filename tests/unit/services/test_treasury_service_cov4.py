"""Cov4: treasury_service — cashbox/GL fallback/buckets/recon/dashboard arcs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from services.treasury_service import TreasuryService


def test_liquidity_gl_fallback_empty_and_with_accounts(db_session, sample_tenant):
    out = TreasuryService.get_liquidity_position(sample_tenant.id)
    assert out["account_count"] == 0
    assert out["total_balance"] == 0.0
    from services.gl_service import GLService

    GLService.ensure_core_accounts(tenant_id=sample_tenant.id)
    out = TreasuryService.get_liquidity_position(sample_tenant.id)
    assert out["account_count"] > 0
    assert set(out["kind_summary"]) <= set(TreasuryService.LIQUIDITY_KINDS)
    out_b = TreasuryService.get_liquidity_position(sample_tenant.id, branch_id=999999)
    assert out_b["account_count"] == 0


def test_liquidity_cashbox_primary(db_session, sample_tenant, sample_branch):
    from models import CashBox

    box = CashBox(tenant_id=sample_tenant.id, branch_id=sample_branch.id,
                  code="CB-COV4", name_ar="صندوق", box_type="bank_account",
                  current_balance=Decimal("123.5"), currency="AED", is_active=True)
    db_session.add(box)
    box2 = CashBox(tenant_id=sample_tenant.id, branch_id=sample_branch.id,
                   code="CB-COV4-2", name_ar="بوابة", name_en="Gateway box", box_type="payment_gateway",
                   current_balance=Decimal("10"), is_active=True)
    db_session.add(box2)
    box3 = CashBox(tenant_id=sample_tenant.id, branch_id=sample_branch.id,
                   code="CB-COV4-3", name_ar="شيكات", box_type="cheque_under_collection",
                   current_balance=Decimal("7"), is_active=True)
    db_session.add(box3)
    db_session.flush()
    out = TreasuryService.get_liquidity_position(sample_tenant.id)
    kinds = {a["code"]: a["kind"] for a in out["accounts"]}
    assert kinds["CB-COV4"] == "bank"
    assert kinds["CB-COV4-2"] == "gateway"
    assert kinds["CB-COV4-3"] == "in_transit"
    assert out["total_balance"] >= 140.5
    out_b = TreasuryService.get_liquidity_position(sample_tenant.id, branch_id=sample_branch.id)
    assert out_b["account_count"] >= 3


def test_cheque_maturity_buckets(db_session, sample_tenant, incoming_cheque, outgoing_cheque,
                                 sample_branch):
    incoming_cheque.due_date = datetime.now(UTC).date() - timedelta(days=3)  # overdue
    incoming_cheque.status = "pending"
    incoming_cheque.is_active = True
    outgoing_cheque.due_date = datetime.now(UTC).date() + timedelta(days=5)  # 0-7
    outgoing_cheque.status = "deposited"
    outgoing_cheque.is_active = True
    outgoing_cheque.branch_id = sample_branch.id
    db_session.flush()
    out = TreasuryService.get_cheque_maturity(sample_tenant.id)
    assert out["incoming"]["buckets"]["overdue"]["count"] >= 1
    assert out["outgoing"]["buckets"]["0_7_days"]["count"] >= 1
    assert out["incoming"]["total_count"] >= 1
    out_b = TreasuryService.get_cheque_maturity(sample_tenant.id, branch_id=sample_branch.id)
    assert out_b["outgoing"]["total_count"] >= 1
    # cheque without due date -> meta 0 branch
    incoming_cheque.due_date = None
    db_session.flush()
    out2 = TreasuryService.get_cheque_maturity(sample_tenant.id)
    assert out2["incoming"]["buckets"]["0_7_days"]["count"] >= 1


def test_recon_status_and_dashboard(db_session, sample_tenant):
    assert TreasuryService.get_bank_reconciliation_status(sample_tenant.id) == []
    dash = TreasuryService.build_dashboard(sample_tenant.id)
    assert set(dash) == {"liquidity", "cheques", "reconciliations", "generated_at"}
