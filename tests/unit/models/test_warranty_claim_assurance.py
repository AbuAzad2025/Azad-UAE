"""WarrantyClaim model — remaining days and representation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _claim_stub(**kwargs):
    from models.warranty_claim import WarrantyClaim

    class Stub:
        sale_id = kwargs.get("sale_id", 10)
        claim_type = kwargs.get("claim_type", "repair")
        status = kwargs.get("status", "open")
        warranty_end_date = kwargs.get("warranty_end_date")

        remaining_days = WarrantyClaim.remaining_days
        __repr__ = WarrantyClaim.__repr__

    return Stub()


class TestWarrantyClaim:
    def test_repr(self):
        assert "S#10" in repr(_claim_stub())

    def test_remaining_days_zero_without_end(self):
        assert _claim_stub().remaining_days == 0

    def test_remaining_days_future(self):
        end = datetime.now(timezone.utc) + timedelta(days=15)
        assert _claim_stub(warranty_end_date=end).remaining_days >= 14

    def test_remaining_days_past_clamped(self):
        end = datetime.now(timezone.utc) - timedelta(days=3)
        assert _claim_stub(warranty_end_date=end).remaining_days == 0
