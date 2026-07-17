from __future__ import annotations

from datetime import datetime, timedelta, timezone

from models.store_coupon import StoreCoupon


class TestStoreCouponValidation:
    def test_normalize_code_uppercase(self):
        assert StoreCoupon.normalize_code("  save10 ") == "SAVE10"

    def test_is_valid_now_active(self):
        coupon = StoreCoupon(tenant_id=1, code="OK", is_active=True)
        assert coupon.is_valid_now() is True

    def test_is_valid_now_inactive(self):
        coupon = StoreCoupon(tenant_id=1, code="OFF", is_active=False)
        assert coupon.is_valid_now() is False

    def test_is_valid_now_future_valid_from(self):
        coupon = StoreCoupon(
            tenant_id=1,
            code="FUTURE",
            is_active=True,
            valid_from=datetime.now(timezone.utc) + timedelta(days=1),
        )
        assert coupon.is_valid_now() is False

    def test_is_valid_now_expired(self):
        coupon = StoreCoupon(
            tenant_id=1,
            code="OLD",
            is_active=True,
            valid_until=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        assert coupon.is_valid_now() is False

    def test_is_valid_now_max_uses_reached(self):
        coupon = StoreCoupon(
            tenant_id=1,
            code="MAXED",
            is_active=True,
            max_uses=5,
            used_count=5,
        )
        assert coupon.is_valid_now() is False
