"""Store coupon validation and application."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from extensions import db
from utils.db_safety import atomic_transaction
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
        code = StoreCoupon.normalize_code(data.get('code') or '')
        if len(code) < 3:
            raise ValueError('رمز الكوبون قصير جداً.')
        if StoreCouponService.get_by_code(tenant_id, code):
            raise ValueError('الكود مستخدم مسبقاً.')

        pct = data.get('discount_percent')
        amt = data.get('discount_amount')
        pct_provided = pct is not None
        amt_provided = amt is not None
        if pct_provided and amt_provided:
            raise ValueError('حدد نسبة أو مبلغ خصم، لا كلاهما.')
        if not pct_provided and not amt_provided:
            raise ValueError('حدد نسبة أو مبلغ خصم.')
        if pct_provided:
            pct_decimal = Decimal(str(pct))
            if pct_decimal <= Decimal('0') or pct_decimal > Decimal('100'):
                raise ValueError('نسبة الخصم يجب أن تكون بين 0.01 و 100.')
        if amt_provided:
            amt_decimal = Decimal(str(amt))
            if amt_decimal <= Decimal('0'):
                raise ValueError('مبلغ الخصم يجب أن يكون أكبر من صفر.')

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
        db.session.flush()

        return coupon

    @staticmethod
    def update_coupon(coupon_id: int, tenant_id: int, data: dict) -> StoreCoupon:
        coupon = StoreCoupon.query.filter_by(id=int(coupon_id), tenant_id=int(tenant_id)).first()
        if not coupon:
            raise ValueError('الكوبون غير موجود.')
        if data.get('description') is not None:
            coupon.description = (data.get('description') or '').strip() or None

        pct_provided = 'discount_percent' in data
        amt_provided = 'discount_amount' in data
        if pct_provided and amt_provided:
            raise ValueError('حدد نسبة أو مبلغ خصم، لا كلاهما.')
        if pct_provided:
            pct_raw = data['discount_percent']
            if pct_raw is not None:
                pct_decimal = Decimal(str(pct_raw))
                if pct_decimal <= Decimal('0') or pct_decimal > Decimal('100'):
                    raise ValueError('نسبة الخصم يجب أن تكون بين 0.01 و 100.')
                if coupon.discount_amount is not None:
                    raise ValueError('لا يمكن تعيين نسبة خصم عندما يكون هناك مبلغ خصم موجود.')
                coupon.discount_percent = pct_decimal
            else:
                coupon.discount_percent = None
        if amt_provided:
            amt_raw = data['discount_amount']
            if amt_raw is not None:
                amt_decimal = Decimal(str(amt_raw))
                if amt_decimal <= Decimal('0'):
                    raise ValueError('مبلغ الخصم يجب أن يكون أكبر من صفر.')
                if coupon.discount_percent is not None:
                    raise ValueError('لا يمكن تعيين مبلغ خصم عندما تكون هناك نسبة خصم موجودة.')
                coupon.discount_amount = amt_decimal
            else:
                coupon.discount_amount = None
        if 'min_order_amount' in data:
            coupon.min_order_amount = Decimal(str(data['min_order_amount'])) if data.get('min_order_amount') else None
        if 'max_uses' in data:
            coupon.max_uses = int(data['max_uses']) if data.get('max_uses') else None
        if 'is_active' in data:
            coupon.is_active = bool(data.get('is_active'))
        db.session.flush()

        return coupon

    @staticmethod
    def mark_used(coupon: StoreCoupon):
        result = db.session.query(StoreCoupon).filter(
            StoreCoupon.id == coupon.id,
            db.or_(
                StoreCoupon.max_uses.is_(None),
                StoreCoupon.used_count < StoreCoupon.max_uses
            )
        ).update(
            {StoreCoupon.used_count: StoreCoupon.used_count + 1},
            synchronize_session=False
        )
        if result == 0:
            raise ValueError('كود الخصم تجاوز الحد الأقصى للاستخدام.')
        db.session.flush()

    @staticmethod
    def release_use(coupon_code: str, tenant_id: int):
        coupon = StoreCouponService.get_by_code(tenant_id, coupon_code)
        if coupon and int(coupon.used_count or 0) > 0:
            coupon.used_count = int(coupon.used_count) - 1
            db.session.flush()
