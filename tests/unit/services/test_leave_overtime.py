"""Leave balance and overtime service tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from extensions import db
from models import LeaveType
from services.hr_service import LeaveBalanceService, OvertimeService


def _make_leave_type(tenant_id, name="Annual Leave", days=30, carry_forward=5):
    lt = LeaveType(
        tenant_id=tenant_id,
        name=name,
        name_ar=name,
        days_per_year=days,
        is_active=True,
        carry_forward_days=carry_forward,
        max_carry_forward=carry_forward,
    )
    db.session.add(lt)
    db.session.flush()
    return lt


class TestLeaveBalanceService:
    def test_get_or_create_creates(self, db_session, sample_tenant, sample_user):
        lt = _make_leave_type(sample_tenant.id, "Annual Leave", 30)
        balance = LeaveBalanceService.get_or_create_balance(sample_user.id, lt.id, 2026, tenant_id=sample_tenant.id)
        assert balance.id is not None
        assert balance.entitled_days == Decimal("30")
        assert balance.remaining_days == Decimal("30")

    def test_get_or_create_reuses(self, db_session, sample_tenant, sample_user):
        lt = _make_leave_type(sample_tenant.id, "Sick Leave", 15)
        b1 = LeaveBalanceService.get_or_create_balance(sample_user.id, lt.id, 2026, tenant_id=sample_tenant.id)
        b2 = LeaveBalanceService.get_or_create_balance(sample_user.id, lt.id, 2026, tenant_id=sample_tenant.id)
        assert b1.id == b2.id

    def test_accrue_leave(self, db_session, sample_tenant, sample_user):
        lt = _make_leave_type(sample_tenant.id, "Annual", 30)
        balance = LeaveBalanceService.accrue_leave(
            sample_user.id, lt.id, 2026, Decimal("5"), tenant_id=sample_tenant.id
        )
        assert balance.taken_days == Decimal("5")
        assert balance.remaining_days == Decimal("25")

    def test_carry_forward(self, db_session, sample_tenant, sample_user):
        lt = _make_leave_type(sample_tenant.id, "Annual", 30, carry_forward=5)
        old = LeaveBalanceService.get_or_create_balance(sample_user.id, lt.id, 2025, tenant_id=sample_tenant.id)
        old.taken_days = Decimal("10")
        old.recalculate()
        db_session.flush()
        assert old.remaining_days == Decimal("20")

        new_balance = LeaveBalanceService.carry_forward_leave(sample_user.id, lt.id, 2025, tenant_id=sample_tenant.id)
        assert new_balance is not None
        assert new_balance.year == 2026
        assert new_balance.carried_forward == Decimal("5")

    def test_list_balances(self, db_session, sample_tenant, sample_user):
        lt = _make_leave_type(sample_tenant.id, "Annual", 30)
        LeaveBalanceService.get_or_create_balance(sample_user.id, lt.id, 2026, tenant_id=sample_tenant.id)
        balances = LeaveBalanceService.list_balances(sample_user.id, 2026, tenant_id=sample_tenant.id)
        assert len(balances) >= 1


class TestOvertimeService:
    def test_create_entry(self, db_session, sample_tenant, sample_user):
        data = {
            "user_id": str(sample_user.id),
            "overtime_date": date(2026, 8, 15),
            "hours": "4",
            "rate_multiplier": "1.25",
            "overtime_type": "standard",
        }
        entry = OvertimeService.create_entry(data, sample_user)
        assert entry.id is not None
        assert entry.status == "pending"
        assert entry.hours == Decimal("4")

    def test_approve_entry(self, db_session, sample_tenant, sample_user):
        data = {
            "user_id": str(sample_user.id),
            "overtime_date": date(2026, 8, 16),
            "hours": "2",
            "overtime_type": "weekend",
        }
        entry = OvertimeService.create_entry(data, sample_user)
        OvertimeService.approve_entry(entry, sample_user)
        assert entry.status == "approved"
        assert entry.approved_by == sample_user.id

    def test_reject_entry(self, db_session, sample_tenant, sample_user):
        data = {
            "user_id": str(sample_user.id),
            "overtime_date": date(2026, 8, 17),
            "hours": "3",
            "overtime_type": "holiday",
        }
        entry = OvertimeService.create_entry(data, sample_user)
        OvertimeService.reject_entry(entry, sample_user, reason="Not needed")
        assert entry.status == "rejected"
        assert entry.rejected_reason == "Not needed"

    def test_approve_non_pending_raises(self, db_session, sample_tenant, sample_user):
        data = {
            "user_id": str(sample_user.id),
            "overtime_date": date(2026, 8, 18),
            "hours": "5",
        }
        entry = OvertimeService.create_entry(data, sample_user)
        OvertimeService.approve_entry(entry, sample_user)
        with pytest.raises(ValueError):
            OvertimeService.approve_entry(entry, sample_user)

    def test_total_hours_value(self, db_session, sample_tenant, sample_user):
        data = {
            "user_id": str(sample_user.id),
            "overtime_date": date(2026, 8, 19),
            "hours": "4",
            "rate_multiplier": "1.5",
        }
        entry = OvertimeService.create_entry(data, sample_user)
        assert entry.total_hours_value == Decimal("4") * Decimal("1.5")
