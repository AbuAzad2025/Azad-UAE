"""Store coupon validation and application."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from extensions import db
from models.store_coupon import StoreCoupon


class StoreCouponService:
    @staticmethod
    def list_for_tenant(tenant_id: int, *, active_only=False):
        q = StoreCoupon.query.filter_by(tenant_id=int(tenant_id))
        if active_only:
            q = q.filter_by(is_active=True)
        return q.order_by(StoreCoupon.created_at.desc()).all()

    @staticmethod
    def get_by_code(tenant_id: int, code: str) -> StoreCoupon | None:
        normalized = StoreCoupon.normalize_code(code)
        if not normalized:
            return None
        return StoreCoupon.query.filter_by(tenant_id=int(tenant_id), code=normalized).first()

    @staticmethod
    def validate_for_checkout(tenant_id: int, code: str, subtotal: Decimal) -> tuple[Decimal, StoreCoupon]:
        coupon = StoreCouponService.get_by_code(tenant_id, code)
        if not coupon:
            raise ValueError('كود الخصم غير صالح.')
        if not coupon.is_valid_now():
            raise ValueError('كود الخصم منتهٍ أو غير نشط.')

        subtotal = Decimal(str(subtotal or 0))
        min_order = Decimal(str(coupon.min_order_amount or 0))
        if min_order > 0 and subtotal < min_order:
            raise ValueError(f'الحد الأدنى للطلب لتطبيق الكوبون: {min_order}')

        discount = Decimal('0')
        if coupon.discount_percent and Decimal(str(coupon.discount_percent)) > 0:
            discount = (subtotal * (Decimal(str(coupon.discount_percent)) / Decimal('100'))).quantize(
                Decimal('0.001'), rounding=ROUND_HALF_UP
            )
        elif coupon.discount_amount and Decimal(str(coupon.discount_amount)) > 0:
            discount = Decimal(str(coupon.discount_amount))

        if discount <= Decimal('0'):
            raise ValueError('كوبون غير صالح — لا يوجد خصم.')
        if discount > subtotal:
            discount = subtotal
        return discount, coupon

    @staticmethod
    def create_coupon(tenant_id: int, data: dict) -> StoreCoupon:
        code = StoreCoupon.normalize_code(data.get('code'))
        if len(code) < 3:
            raise ValueError('رمز الكوبون قصير جداً.')
        if StoreCouponService.get_by_code(tenant_id, code):
            raise ValueError('الكود مستخدم مسبقاً.')

        pct = data.get('discount_percent')
        amt = data.get('discount_amount')
        if not pct and not amt:
            raise ValueError('حدد نسبة أو مبلغ خصم.')

        coupon = StoreCoupon(
            tenant_id=int(tenant_id),
            code=code,
            description=(data.get('description') or '').strip() or None,
            discount_percent=Decimal(str(pct)) if pct else None,
            discount_amount=Decimal(str(amt)) if amt else None,
            min_order_amount=Decimal(str(data['min_order_amount'])) if data.get('min_order_amount') else None,
            max_uses=int(data['max_uses']) if data.get('max_uses') else None,
            is_active=bool(data.get('is_active', True)),
        )
        db.session.add(coupon)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        return coupon

    @staticmethod
    def update_coupon(coupon_id: int, tenant_id: int, data: dict) -> StoreCoupon:
        coupon = StoreCoupon.query.filter_by(id=int(coupon_id), tenant_id=int(tenant_id)).first()
        if not coupon:
            raise ValueError('الكوبون غير موجود.')
        if data.get('description') is not None:
            coupon.description = (data.get('description') or '').strip() or None
        if data.get('discount_percent') is not None:
            coupon.discount_percent = Decimal(str(data['discount_percent'])) if data['discount_percent'] else None
        if data.get('discount_amount') is not None:
            coupon.discount_amount = Decimal(str(data['discount_amount'])) if data['discount_amount'] else None
        if 'min_order_amount' in data:
            coupon.min_order_amount = Decimal(str(data['min_order_amount'])) if data.get('min_order_amount') else None
        if 'max_uses' in data:
            coupon.max_uses = int(data['max_uses']) if data.get('max_uses') else None
        if 'is_active' in data:
            coupon.is_active = bool(data.get('is_active'))
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        return coupon

    @staticmethod
    def mark_used(coupon: StoreCoupon):
        coupon.used_count = int(coupon.used_count or 0) + 1
        db.session.flush()

    @staticmethod
    def release_use(coupon_code: str, tenant_id: int):
        coupon = StoreCouponService.get_by_code(tenant_id, coupon_code)
        if coupon and int(coupon.used_count or 0) > 0:
            coupon.used_count = int(coupon.used_count) - 1
            db.session.flush()
