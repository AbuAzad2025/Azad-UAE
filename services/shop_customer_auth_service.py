"""Storefront customer registration & session — per tenant."""
from __future__ import annotations

import re

from datetime import datetime, timezone

from flask import session

from extensions import db
from utils.db_safety import atomic_transaction
from models import Customer
from models.shop_customer_account import ShopCustomerAccount
from utils.currency_utils import resolve_default_currency


class ShopCustomerAuthService:
    SESSION_PREFIX = 'shop_account_'

    @staticmethod
    def session_key(tenant_id: int) -> str:
        return f'{ShopCustomerAuthService.SESSION_PREFIX}{int(tenant_id)}'

    @staticmethod
    def get_logged_in_account(tenant_id: int) -> ShopCustomerAccount | None:
        raw = session.get(ShopCustomerAuthService.session_key(tenant_id))
        if not raw:
            return None
        account = db.session.get(ShopCustomerAccount, int(raw or 0))
        if not account or not account.is_active or int(account.tenant_id or 0) != int(tenant_id):
            return None
        return account

    @staticmethod
    def login(session_obj, tenant_id: int, account: ShopCustomerAccount):
        session_obj[ShopCustomerAuthService.session_key(tenant_id)] = account.id
        session_obj.modified = True

    @staticmethod
    def logout(session_obj, tenant_id: int):
        session_obj.pop(ShopCustomerAuthService.session_key(tenant_id), None)
        session_obj.modified = True

    @staticmethod
    def normalize_email(email: str) -> str:
        email = (email or '').strip().lower()
        if not email or '@' not in email:
            raise ValueError('البريد الإلكتروني غير صالح.')
        return email

    @staticmethod
    def normalize_phone(phone: str) -> str:
        digits = re.sub(r'\D', '', phone or '')
        if len(digits) < 8:
            raise ValueError('رقم الهاتف غير صالح.')
        return digits

    @staticmethod
    def register(tenant_id: int, name: str, email: str, phone: str, password: str, address: str | None = None) -> ShopCustomerAccount:
        tenant_id = int(tenant_id)
        name = (name or '').strip()
        if len(name) < 2:
            raise ValueError('الاسم مطلوب.')
        email = ShopCustomerAuthService.normalize_email(email)
        phone_norm = ShopCustomerAuthService.normalize_phone(phone)
        if not password or len(password) < 6:
            raise ValueError('كلمة المرور 6 أحرف على الأقل.')

        existing = ShopCustomerAccount.query.filter_by(tenant_id=tenant_id, email=email).first()
        if existing:
            raise ValueError('هذا البريد مسجّل مسبقاً — سجّل الدخول.')

        customer = Customer.query.filter_by(tenant_id=tenant_id, phone=phone_norm).first()
        if not customer:
            customer = Customer(
                tenant_id=tenant_id,
                name=name,
                customer_type='regular',
                phone=phone_norm,
                email=email,
                address=address,
                is_active=True,
            )
            db.session.add(customer)
            db.session.flush()
        else:
            customer.name = name
            customer.email = email
            if address:
                customer.address = address

        account = ShopCustomerAccount(
            tenant_id=tenant_id,
            customer_id=customer.id,
            email=email,
            phone=phone_norm,
            name=name,
            address=address,
            is_active=True,
        )
        account.set_password(password)
        db.session.add(account)
        try:
            db.session.flush()
        except Exception:
            raise

        return account

    @staticmethod
    def authenticate(tenant_id: int, email: str, password: str) -> ShopCustomerAccount:
        email = ShopCustomerAuthService.normalize_email(email)
        account = ShopCustomerAccount.query.filter_by(tenant_id=int(tenant_id), email=email, is_active=True).first()
        if not account or not account.check_password(password):
            raise ValueError('بيانات الدخول غير صحيحة.')
        from datetime import datetime, timezone
        account.last_login_at = datetime.now(timezone.utc)
        try:
            db.session.flush()
        except Exception:
            raise

        return account

    @staticmethod
    def request_password_reset(tenant_id: int, email: str) -> ShopCustomerAccount | None:
        import secrets
        from datetime import timedelta

        email = ShopCustomerAuthService.normalize_email(email)
        account = ShopCustomerAccount.query.filter_by(
            tenant_id=int(tenant_id), email=email, is_active=True
        ).first()
        if not account:
            return None

        account.password_reset_token = secrets.token_urlsafe(32)
        account.password_reset_expires_at = datetime.now(timezone.utc) + timedelta(hours=2)
        try:
            db.session.flush()
        except Exception:
            raise

        return account

    @staticmethod
    def reset_password(tenant_id: int, token: str, new_password: str) -> ShopCustomerAccount:
        token = (token or '').strip()
        if not token:
            raise ValueError('رمز الاستعادة غير صالح.')
        if not new_password or len(new_password) < 6:
            raise ValueError('كلمة المرور 6 أحرف على الأقل.')

        account = ShopCustomerAccount.query.filter_by(
            tenant_id=int(tenant_id),
            password_reset_token=token,
            is_active=True,
        ).first()
        if not account:
            raise ValueError('رمز الاستعادة غير صالح أو منتهٍ.')
        expires = account.password_reset_expires_at
        if not expires or expires.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            raise ValueError('انتهت صلاحية رابط الاستعادة — اطلب رابطاً جديداً.')

        account.set_password(new_password)
        account.password_reset_token = None
        account.password_reset_expires_at = None
        try:
            db.session.flush()
        except Exception:
            raise

        return account

    @staticmethod
    def send_password_reset_email(account: ShopCustomerAccount, store, reset_url: str):
        from flask import current_app

        if not current_app.config.get('MAIL_USERNAME') or not current_app.config.get('MAIL_PASSWORD'):
            return False
        try:
            from flask_mail import Message
            from extensions import mail

            msg = Message(
                subject=f'استعادة كلمة المرور — {store.title or "المتجر"}',
                recipients=[account.email],
                body=(
                    f'مرحباً {account.name},\n\n'
                    f'لإعادة تعيين كلمة المرور اضغط الرابط:\n{reset_url}\n\n'
                    f'صلاحية الرابط: ساعتان.\n'
                ),
            )
            mail.send(msg)
            return True
        except Exception as exc:
            current_app.logger.warning('Shop password reset email failed: %s', exc)
            return False

    @staticmethod
    def whatsapp_order_url(store, product, lang='ar', quantity=1) -> str | None:
        wa = (store.whatsapp or store.phone or '').strip()
        digits = re.sub(r'\D', '', wa)
        if not digits:
            return None
        pname = product.get_display_name(lang)
        price = product.regular_price
        currency = resolve_default_currency(getattr(store, 'tenant', None))
        if lang == 'en':
            text = (
                f"Hello, I'd like to order from {store.title or 'your store'}:\n"
                f"Product: {pname}\nSKU: {product.sku or '-'}\nQty: {quantity}\nPrice: {price} {currency}"
            )
        else:
            text = (
                f"مرحباً، أريد طلباً من {store.title or 'متجركم'}:\n"
                f"المنتج: {pname}\nالرمز: {product.sku or '-'}\nالكمية: {quantity}\nالسعر: {price} {currency}"
            )
        from urllib.parse import quote
        return f'https://wa.me/{digits}?text={quote(text)}'
