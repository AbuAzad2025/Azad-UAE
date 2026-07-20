"""Unit tests for StoreCouponService."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from extensions import db
from models.store_coupon import StoreCoupon
from services.store_coupon_service import StoreCouponService


@pytest.fixture(autouse=True)
def _app_context(app):
    with app.app_context():
        yield


@pytest.fixture(autouse=True)
def _transaction_rollback(db_session):
    yield
    db_session.rollback()


def _coupon(db_session, tenant_id, **kwargs):
    code = kwargs.pop("code", f"CPN{uuid.uuid4().hex[:6].upper()}")
    row = StoreCoupon(
        tenant_id=tenant_id,
        code=code,
        discount_percent=kwargs.get("discount_percent"),
        discount_amount=kwargs.get("discount_amount"),
        min_order_amount=kwargs.get("min_order_amount"),
        max_uses=kwargs.get("max_uses"),
        used_count=kwargs.get("used_count", 0),
        is_active=kwargs.get("is_active", True),
        valid_from=kwargs.get("valid_from"),
        valid_until=kwargs.get("valid_until"),
    )
    db_session.add(row)
    db_session.flush()
    return row


class TestListAndGet:
    def test_list_all_and_active_only(self, db_session, sample_tenant):
        active = _coupon(db_session, sample_tenant.id)
        inactive = _coupon(db_session, sample_tenant.id, is_active=False)
        all_rows = StoreCouponService.list_for_tenant(sample_tenant.id)
        active_rows = StoreCouponService.list_for_tenant(sample_tenant.id, active_only=True)
        assert active.id in {r.id for r in all_rows}
        assert inactive.id in {r.id for r in all_rows}
        assert active.id in {r.id for r in active_rows}
        assert inactive.id not in {r.id for r in active_rows}

    def test_get_by_code(self, db_session, sample_tenant):
        _coupon(db_session, sample_tenant.id, code="SAVE10")
        assert StoreCouponService.get_by_code(sample_tenant.id, "  save10 ") is not None
        assert StoreCouponService.get_by_code(sample_tenant.id, "") is None


class TestValidateForCheckout:
    def test_invalid_code(self, sample_tenant):
        with pytest.raises(ValueError, match="غير صالح"):
            StoreCouponService.validate_for_checkout(sample_tenant.id, "NOPE", Decimal("100"))

    def test_inactive_coupon(self, db_session, sample_tenant):
        row = _coupon(db_session, sample_tenant.id, is_active=False)
        with pytest.raises(ValueError, match="منتهٍ"):
            StoreCouponService.validate_for_checkout(sample_tenant.id, row.code, Decimal("100"))

    def test_expired_coupon(self, db_session, sample_tenant):
        row = _coupon(
            db_session,
            sample_tenant.id,
            valid_until=datetime.now(timezone.utc) - timedelta(days=1),
        )
        with pytest.raises(ValueError, match="منتهٍ"):
            StoreCouponService.validate_for_checkout(sample_tenant.id, row.code, Decimal("100"))

    def test_min_order_not_met(self, db_session, sample_tenant):
        row = _coupon(
            db_session,
            sample_tenant.id,
            discount_amount=Decimal("5"),
            min_order_amount=Decimal("50"),
        )
        with pytest.raises(ValueError, match="الحد الأدنى"):
            StoreCouponService.validate_for_checkout(sample_tenant.id, row.code, Decimal("10"))

    def test_percent_discount(self, db_session, sample_tenant):
        row = _coupon(db_session, sample_tenant.id, discount_percent=Decimal("10"))
        discount, coupon = StoreCouponService.validate_for_checkout(sample_tenant.id, row.code, Decimal("100"))
        assert discount == Decimal("10.000")
        assert coupon.id == row.id

    def test_amount_discount(self, db_session, sample_tenant):
        row = _coupon(db_session, sample_tenant.id, discount_amount=Decimal("15"))
        discount, _ = StoreCouponService.validate_for_checkout(sample_tenant.id, row.code, Decimal("100"))
        assert discount == Decimal("15")

    def test_discount_capped_at_subtotal(self, db_session, sample_tenant):
        row = _coupon(db_session, sample_tenant.id, discount_amount=Decimal("50"))
        discount, _ = StoreCouponService.validate_for_checkout(sample_tenant.id, row.code, Decimal("20"))
        assert discount == Decimal("20")

    def test_zero_discount_raises(self, db_session, sample_tenant):
        row = _coupon(db_session, sample_tenant.id, discount_percent=Decimal("0"))
        with pytest.raises(ValueError, match="لا يوجد خصم"):
            StoreCouponService.validate_for_checkout(sample_tenant.id, row.code, Decimal("100"))


class TestCreateCoupon:
    def test_short_code(self, sample_tenant):
        with pytest.raises(ValueError, match="قصير"):
            StoreCouponService.create_coupon(sample_tenant.id, {"code": "AB", "discount_amount": 5})

    def test_duplicate_code(self, db_session, sample_tenant):
        row = _coupon(db_session, sample_tenant.id, code="DUP123")
        with pytest.raises(ValueError, match="مستخدم"):
            StoreCouponService.create_coupon(sample_tenant.id, {"code": row.code, "discount_amount": 5})

    def test_both_or_neither_discount(self, sample_tenant):
        with pytest.raises(ValueError, match="لا كلاهما"):
            StoreCouponService.create_coupon(
                sample_tenant.id,
                {
                    "code": "BOTH1",
                    "discount_percent": 10,
                    "discount_amount": 5,
                },
            )
        with pytest.raises(ValueError, match="نسبة أو مبلغ"):
            StoreCouponService.create_coupon(sample_tenant.id, {"code": "NONE1"})

    def test_invalid_percent_and_amount(self, sample_tenant):
        with pytest.raises(ValueError, match="نسبة الخصم"):
            StoreCouponService.create_coupon(
                sample_tenant.id,
                {
                    "code": "BADPCT",
                    "discount_percent": 101,
                },
            )
        with pytest.raises(ValueError, match="مبلغ الخصم"):
            StoreCouponService.create_coupon(
                sample_tenant.id,
                {
                    "code": "BADAMT",
                    "discount_amount": 0,
                },
            )

    def test_creates_percent_coupon(self, sample_tenant):
        coupon = StoreCouponService.create_coupon(
            sample_tenant.id,
            {
                "code": f"NEW{uuid.uuid4().hex[:4].upper()}",
                "discount_percent": 12.5,
                "min_order_amount": 25,
                "max_uses": 10,
                "description": " promo ",
            },
        )
        assert coupon.discount_percent == Decimal("12.5")
        assert coupon.min_order_amount == Decimal("25")
        assert coupon.description == "promo"

    def test_commit_failure(self, sample_tenant, mocker):
        mocker.patch.object(db.session, "flush", side_effect=RuntimeError("db"))
        with pytest.raises(RuntimeError, match="db"):
            StoreCouponService.create_coupon(
                sample_tenant.id,
                {
                    "code": f"FAIL{uuid.uuid4().hex[:4].upper()}",
                    "discount_amount": 5,
                },
            )


class TestUpdateCoupon:
    def test_not_found(self, sample_tenant):
        with pytest.raises(ValueError, match="غير موجود"):
            StoreCouponService.update_coupon(999999999, sample_tenant.id, {})

    def test_both_discount_types_raises(self, db_session, sample_tenant):
        row = _coupon(db_session, sample_tenant.id, discount_percent=Decimal("5"))
        with pytest.raises(ValueError, match="لا كلاهما"):
            StoreCouponService.update_coupon(
                row.id,
                sample_tenant.id,
                {
                    "discount_percent": 10,
                    "discount_amount": 5,
                },
            )

    def test_update_percent_and_clear_amount_path(self, db_session, sample_tenant):
        row = _coupon(db_session, sample_tenant.id, discount_amount=Decimal("5"))
        with pytest.raises(ValueError, match="نسبة خصم"):
            StoreCouponService.update_coupon(row.id, sample_tenant.id, {"discount_percent": 10})

    def test_update_amount_when_percent_exists(self, db_session, sample_tenant):
        row = _coupon(db_session, sample_tenant.id, discount_percent=Decimal("5"))
        with pytest.raises(ValueError, match="مبلغ خصم"):
            StoreCouponService.update_coupon(row.id, sample_tenant.id, {"discount_amount": 5})

    def test_updates_fields(self, db_session, sample_tenant):
        row = _coupon(db_session, sample_tenant.id, discount_amount=Decimal("5"))
        updated = StoreCouponService.update_coupon(
            row.id,
            sample_tenant.id,
            {
                "description": "updated",
                "discount_amount": 8,
                "min_order_amount": 30,
                "max_uses": 3,
                "is_active": False,
            },
        )
        assert updated.description == "updated"
        assert updated.discount_amount == Decimal("8")
        assert updated.is_active is False

    def test_clear_discount_fields(self, db_session, sample_tenant):
        row = _coupon(db_session, sample_tenant.id, discount_percent=Decimal("5"))
        updated = StoreCouponService.update_coupon(
            row.id,
            sample_tenant.id,
            {
                "discount_percent": None,
                "min_order_amount": None,
                "max_uses": None,
            },
        )
        assert updated.discount_percent is None
        assert updated.min_order_amount is None

    def test_update_percent_success(self, db_session, sample_tenant):
        row = _coupon(db_session, sample_tenant.id, discount_percent=Decimal("5"))
        updated = StoreCouponService.update_coupon(row.id, sample_tenant.id, {"discount_percent": 12})
        assert updated.discount_percent == Decimal("12")

    def test_clear_amount_discount(self, db_session, sample_tenant):
        row = _coupon(db_session, sample_tenant.id, discount_amount=Decimal("5"))
        updated = StoreCouponService.update_coupon(row.id, sample_tenant.id, {"discount_amount": None})
        assert updated.discount_amount is None

    def test_creates_amount_coupon(self, sample_tenant):
        coupon = StoreCouponService.create_coupon(
            sample_tenant.id,
            {
                "code": f"AMT{uuid.uuid4().hex[:4].upper()}",
                "discount_amount": 7,
            },
        )
        assert coupon.discount_amount == Decimal("7")

    def test_invalid_percent_on_update(self, db_session, sample_tenant):
        row = _coupon(db_session, sample_tenant.id, discount_percent=Decimal("5"))
        with pytest.raises(ValueError, match="نسبة الخصم"):
            StoreCouponService.update_coupon(row.id, sample_tenant.id, {"discount_percent": 0})

    def test_update_amount_success(self, db_session, sample_tenant):
        row = _coupon(db_session, sample_tenant.id, discount_amount=Decimal("5"))
        updated = StoreCouponService.update_coupon(row.id, sample_tenant.id, {"discount_amount": 9})
        assert updated.discount_amount == Decimal("9")

    def test_invalid_amount_on_update(self, db_session, sample_tenant):
        row = _coupon(db_session, sample_tenant.id, discount_amount=Decimal("5"))
        with pytest.raises(ValueError, match="مبلغ الخصم"):
            StoreCouponService.update_coupon(row.id, sample_tenant.id, {"discount_amount": 0})

    def test_commit_failure(self, db_session, sample_tenant, mocker):
        row = _coupon(db_session, sample_tenant.id, discount_amount=Decimal("5"))
        mocker.patch.object(db.session, "flush", side_effect=RuntimeError("upd"))
        with pytest.raises(RuntimeError, match="upd"):
            StoreCouponService.update_coupon(row.id, sample_tenant.id, {"description": "x"})


class TestMarkAndRelease:
    def test_mark_used_increments(self, db_session, sample_tenant):
        row = _coupon(
            db_session,
            sample_tenant.id,
            discount_amount=Decimal("5"),
            max_uses=2,
            used_count=0,
        )
        StoreCouponService.mark_used(row)
        db_session.refresh(row)
        assert row.used_count == 1

    def test_mark_used_at_limit_raises(self, db_session, sample_tenant):
        row = _coupon(
            db_session,
            sample_tenant.id,
            discount_amount=Decimal("5"),
            max_uses=1,
            used_count=1,
        )
        with pytest.raises(ValueError, match="الحد الأقصى"):
            StoreCouponService.mark_used(row)

    def test_release_use(self, db_session, sample_tenant):
        row = _coupon(db_session, sample_tenant.id, discount_amount=Decimal("5"), used_count=2)
        StoreCouponService.release_use(row.code, sample_tenant.id)
        db_session.refresh(row)
        assert row.used_count == 1

    def test_release_use_noop(self, db_session, sample_tenant):
        row = _coupon(db_session, sample_tenant.id, discount_amount=Decimal("5"), used_count=0)
        StoreCouponService.release_use(row.code, sample_tenant.id)
        db_session.refresh(row)
        assert row.used_count == 0
        StoreCouponService.release_use("MISSING", sample_tenant.id)
