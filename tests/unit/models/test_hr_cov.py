"""Coverage for models/hr.py repr and Arabic-label properties (lines 270, 315, 319-320, 324-325)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal


class TestLeaveBalanceRepr:
    def test_repr_includes_user_type_year(self):
        """Line 270: LeaveBalance.__repr__."""
        from models.hr import LeaveBalance

        balance = LeaveBalance(user_id=7, leave_type_id=3, year=2026)
        text = repr(balance)
        assert "7" in text
        assert "3" in text
        assert "2026" in text

    def test_recalculate_updates_remaining(self):
        from models.hr import LeaveBalance

        balance = LeaveBalance(user_id=7, leave_type_id=3, year=2026)
        balance.entitled_days = Decimal("21")
        balance.carried_forward = Decimal("2")
        balance.taken_days = Decimal("5")
        balance.pending_days = Decimal("1")
        balance.recalculate()
        assert balance.remaining_days == Decimal("17")


class TestOvertimeEntryRepr:
    def test_repr_includes_user_date_hours(self):
        """Line 315: OvertimeEntry.__repr__."""
        from models.hr import OvertimeEntry

        entry = OvertimeEntry(
            user_id=9,
            tenant_id=1,
            overtime_date=date(2026, 4, 2),
            hours=Decimal("2.50"),
        )
        text = repr(entry)
        assert "9" in text
        assert "2026-04-02" in text
        assert "2.50" in text


class TestOvertimeTypeAr:
    def test_known_types(self):
        """Lines 319-320: mapped overtime types."""
        from models.hr import OvertimeEntry

        assert OvertimeEntry(overtime_type="standard").overtime_type_ar == "إضافي عادي"
        assert OvertimeEntry(overtime_type="weekend").overtime_type_ar == "إضافي يوم إجازة"
        assert OvertimeEntry(overtime_type="holiday").overtime_type_ar == "إضافي عطلة رسمية"

    def test_unknown_type_falls_back(self):
        """Lines 319-320: unmapped type returns itself."""
        from models.hr import OvertimeEntry

        assert OvertimeEntry(overtime_type="night").overtime_type_ar == "night"


class TestOvertimeStatusAr:
    def test_known_statuses(self):
        """Lines 324-325: mapped statuses."""
        from models.hr import OvertimeEntry

        assert OvertimeEntry(status="pending").status_ar == "قيد المراجعة"
        assert OvertimeEntry(status="approved").status_ar == "تمت الموافقة"
        assert OvertimeEntry(status="rejected").status_ar == "مرفوض"

    def test_unknown_status_falls_back(self):
        """Lines 324-325: unmapped status returns itself."""
        from models.hr import OvertimeEntry

        assert OvertimeEntry(status="draft").status_ar == "draft"


class TestOvertimeTotalHoursValue:
    def test_total_hours_value_multiplies(self):
        from models.hr import OvertimeEntry

        entry = OvertimeEntry(hours=Decimal("2.50"), rate_multiplier=Decimal("1.5"))
        assert entry.total_hours_value == Decimal("3.750")
