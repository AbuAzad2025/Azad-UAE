"""Checkout flow for public online store — online warehouse only."""
from __future__ import annotations

import re
from decimal import Decimal

from flask import current_app
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from extensions import db
from models import Customer, Product, Sale, User, Warehouse
from services.sale_service import SaleService
from utils.currency_utils import resolve_default_currency
from services.stock_service import StockService
from services.store_service import StoreService
from services.store_payment_method_service import StorePaymentMethodService


class StoreCheckoutService:
    ORDER_TOKEN_SALT = 'shop-order-v1'
    ORDER_TOKEN_MAX_AGE = 60 * 60 * 24 * 7  # 7 days
    _DEV_ONLY_TOKEN_SECRET = 'dev-only-shop-order-token-not-for-production'

    @staticmethod
    def _is_production() -> bool:
        if current_app.config.get('DEBUG'):
            return False
        app_env = (current_app.config.get('APP_ENV') or 'production').strip().lower()
        return app_env == 'production'

    @staticmethod
    def _order_token_secret() -> str:
        secret = current_app.config.get('SECRET_KEY')
        if secret:
            return secret
        if StoreCheckoutService._is_production():
            raise ValueError(
                'SECRET_KEY must be configured in production to sign shop order tokens.'
            )
        current_app.logger.warning(
            '[Dev] Using dev-only shop order token secret; set SECRET_KEY for production.'
        )
        return StoreCheckoutService._DEV_ONLY_TOKEN_SECRET

    @staticmethod
    def _serializer():
        return URLSafeTimedSerializer(
            StoreCheckoutService._order_token_secret(),
            salt=StoreCheckoutService.ORDER_TOKEN_SALT,
        )

    @staticmethod
    def make_order_token(sale_id: int, tenant_id: int) -> str:
        return StoreCheckoutService._serializer().dumps({'sale_id': int(sale_id), 'tenant_id': int(tenant_id)})

    @staticmethod
    def load_order_token(token: str) -> dict | None:
        try:
            data = StoreCheckoutService._serializer().loads(
                token,
                max_age=StoreCheckoutService.ORDER_TOKEN_MAX_AGE,
            )
            if not isinstance(data, dict):
                return None
            return data
        except (BadSignature, SignatureExpired):
            return None

    @staticmethod
    def normalize_phone(phone: str) -> str:
        digits = re.sub(r'\D', '', phone or '')
        if not digits:
            raise ValueError('رقم الهاتف مطلوب.')
        if len(digits) < 8:
            raise ValueError('رقم الهاتف غير صالح.')
        return digits

    @staticmethod
    def get_or_create_customer(tenant_id: int, name: str, phone: str, address: str = None, email: str = None) -> Customer:
        phone_norm = StoreCheckoutService.normalize_phone(phone)
        name = (name or '').strip()
        if len(name) < 2:
            raise ValueError('الاسم مطلوب.')

        customer = Customer.query.filter_by(tenant_id=int(tenant_id), phone=phone_norm).first()
        if customer:
            if name and customer.name != name:
                customer.name = name
            if address and not customer.address:
                customer.address = address
            if email and not customer.email:
                customer.email = email
            return customer

        customer = Customer(
            tenant_id=int(tenant_id),
            name=name,
            customer_type='regular',
            phone=phone_norm,
            address=address,
            email=email,
            is_active=True,
        )
        db.session.add(customer)
        db.session.flush()
        return customer

    @staticmethod
    def resolve_seller(tenant_id: int) -> User:
        seller = (
            User.query.filter_by(tenant_id=int(tenant_id), is_active=True, is_owner=True)
            .order_by(User.id.asc())
            .first()
        )
        if not seller:
            seller = (
                User.query.filter_by(tenant_id=int(tenant_id), is_active=True)
                .order_by(User.id.asc())
                .first()
            )
        if not seller:
            raise ValueError('لا يوجد مستخدم نظام لمعالجة الطلب.')
        return seller

    @staticmethod
    def build_lines_from_cart(tenant_id: int, cart: dict, online_warehouse_id: int) -> list:
        if not cart:
            raise ValueError('السلة فارغة.')

        lines = []
        stock_map = StoreService.online_stock_map(tenant_id, list(cart.keys()))

        for pid_raw, qty_raw in cart.items():
            try:
                product_id = int(pid_raw)
                qty = Decimal(str(qty_raw))
            except (TypeError, ValueError):
                continue
            if qty <= 0:
                continue

            product = Product.query.filter_by(id=product_id, tenant_id=int(tenant_id), is_active=True).first()
            if not product:
                raise ValueError('منتج في السلة غير متاح.')
            if product.has_serial_number:
                raise ValueError(f'المنتج "{product.name}" يتطلب متابعة عبر الهاتف.')

            available = stock_map.get(product_id, Decimal('0'))
            if qty > available:
                raise ValueError(f'الكمية المطلوبة من "{product.name}" تتجاوز المتوفر ({available}).')

            ok, msg = StockService.check_availability_in_warehouse(product_id, qty, online_warehouse_id)
            if not ok:
                raise ValueError(f'{product.name}: {msg}')

            lines.append({
                'product': product,
                'quantity': float(qty),
                'discount_percent': 0,
            })

        if not lines:
            raise ValueError('السلة فارغة.')
        return lines

    @staticmethod
    def create_web_order(
        store,
        cart: dict,
        customer_name: str,
        phone: str,
        address: str,
        notes: str = None,
        payment_method_code: str = None,
        shop_account=None,
        coupon_code: str = None,
        customer_email: str = None,
    ) -> Sale:
        tenant_id = int(store.tenant_id)
        online_wh = db.session.get(Warehouse, store.warehouse_id)
        if not online_wh or not online_wh.is_online:
            raise ValueError('مستودع المتجر غير مهيأ.')

        pay_method = StorePaymentMethodService.validate_for_checkout(payment_method_code or 'cod')

        lines_data = StoreCheckoutService.build_lines_from_cart(tenant_id, cart, online_wh.id)
        if shop_account and shop_account.customer_id:
            customer = db.session.get(Customer, shop_account.customer_id)
            if not customer:
                customer = StoreCheckoutService.get_or_create_customer(tenant_id, customer_name, phone, address, email=customer_email)
            else:
                if customer_name:
                    customer.name = customer_name
                if address:
                    customer.address = address
                if phone:
                    customer.phone = StoreCheckoutService.normalize_phone(phone)
                if customer_email and not customer.email:
                    customer.email = customer_email
        else:
            customer = StoreCheckoutService.get_or_create_customer(tenant_id, customer_name, phone, address, email=customer_email)
        seller = StoreCheckoutService.resolve_seller(tenant_id)

        delivery_block = (
            f"\n[متجر أونلاين]\nطريقة الدفع: {pay_method.name_ar}\nالعنوان: {address}\nالهاتف: {phone}"
        )
        if notes:
            delivery_block += f"\nملاحظات: {notes}"

        from models import Tenant
        from services.store_coupon_service import StoreCouponService
        from services.store_notification_service import StoreNotificationService

        tenant = db.session.get(Tenant, tenant_id)
        currency = resolve_default_currency(tenant)

        subtotal = Decimal('0')
        for line_data in lines_data:
            product = line_data['product']
            qty = Decimal(str(line_data['quantity']))
            price = product.get_price_for_customer(customer.customer_type)
            subtotal += qty * Decimal(str(price))

        discount_amount = Decimal('0')
        coupon_obj = None
        if coupon_code:
            discount_amount, coupon_obj = StoreCouponService.validate_for_checkout(
                tenant_id, coupon_code, subtotal
            )
            delivery_block += f"\nكوبون: {coupon_obj.code} (-{discount_amount})"

        sale = SaleService.create_sale(
            customer=customer,
            seller=seller,
            lines_data=lines_data,
            warehouse_id=online_wh.id,
            currency=currency,
            discount_amount=discount_amount,
            shipping_cost=0,
            tax_rate=0,
            notes=(notes or '') + delivery_block,
            payment_data=None,
            source='online_store',
            sale_status='pending',
            checkout_payment_method=pay_method.code,
            defer_fulfillment=True,
        )
        if coupon_obj:
            sale.coupon_code = coupon_obj.code
            StoreCouponService.mark_used(coupon_obj)
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                raise


        StoreNotificationService.notify_new_order(sale, store)
        return sale
