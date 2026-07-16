"""Platform store payment methods — shared across all tenant storefronts."""
from __future__ import annotations

from extensions import db
from utils.db_safety import atomic_transaction
from models.store_payment_method import StorePaymentMethod

DEFAULT_METHODS = (
    {
        'code': 'cod',
        'name_ar': 'الدفع عند الاستلام',
        'name_en': 'Cash on Delivery',
        'description_ar': 'ادفع نقداً عند استلام طلبك.',
        'description_en': 'Pay in cash when your order arrives.',
        'icon': 'fas fa-hand-holding-usd',
        'is_enabled': True,
        'is_builtin': True,
        'sort_order': 10,
    },
    {
        'code': 'bank_transfer',
        'name_ar': 'تحويل بنكي',
        'name_en': 'Bank Transfer',
        'description_ar': 'حوّل المبلغ ثم أرفق رقم المرجع في الملاحظات.',
        'description_en': 'Transfer the amount and add the reference in notes.',
        'icon': 'fas fa-university',
        'is_enabled': False,
        'is_builtin': True,
        'sort_order': 20,
        'config': {'bank_name': '', 'iban': '', 'account_name': ''},
    },
    {
        'code': 'card',
        'name_ar': 'بطاقة (عند الاستلام أو عبر الرابط)',
        'name_en': 'Card (on delivery or link)',
        'description_ar': 'الدفع ببطاقة عند التسليم أو حسب تعليمات المتجر.',
        'description_en': 'Pay by card on delivery or as instructed by the store.',
        'icon': 'fas fa-credit-card',
        'is_enabled': False,
        'is_builtin': True,
        'sort_order': 30,
    },
    {
        'code': 'e_wallet',
        'name_ar': 'محفظة إلكترونية',
        'name_en': 'E-Wallet',
        'description_ar': 'Apple Pay، Google Pay، أو محافظ أخرى حسب إعداد المنصة.',
        'description_en': 'Apple Pay, Google Pay, or other wallets as configured.',
        'icon': 'fas fa-wallet',
        'is_enabled': False,
        'is_builtin': True,
        'sort_order': 40,
        'config': {'providers': ''},
    },
    {
        'code': 'online_pay',
        'name_ar': 'دفع إلكتروني (عملات رقمية)',
        'name_en': 'Online Pay (Crypto)',
        'description_ar': 'ادفع عبر بوابة NOWPayments — يُفعّل عند إعداد الخزينة.',
        'description_en': 'Pay via NOWPayments gateway when configured.',
        'icon': 'fas fa-bitcoin-sign',
        'is_enabled': False,
        'is_builtin': True,
        'sort_order': 50,
    },
)


class StorePaymentMethodService:
    @staticmethod
    def ensure_defaults():
        with atomic_transaction('ensure_payment_defaults'):
            for item in DEFAULT_METHODS:
                existing = StorePaymentMethod.query.filter_by(code=item['code']).first()
                if existing:
                    continue
                row = StorePaymentMethod(
                    code=item['code'],
                    name_ar=item['name_ar'],
                    name_en=item['name_en'],
                    description_ar=item.get('description_ar'),
                    description_en=item.get('description_en'),
                    icon=item.get('icon', 'fas fa-money-bill-wave'),
                    is_enabled=bool(item.get('is_enabled', False)),
                    is_builtin=bool(item.get('is_builtin', False)),
                    sort_order=int(item.get('sort_order', 100)),
                )
                cfg = item.get('config')
                if cfg:
                    row.set_config(cfg)
                db.session.add(row)

    @staticmethod
    def list_all(*, enabled_only=False):
        q = StorePaymentMethod.query
        if enabled_only:
            q = q.filter_by(is_enabled=True)
        return q.order_by(StorePaymentMethod.sort_order.asc(), StorePaymentMethod.id.asc()).all()

    @staticmethod
    def list_for_checkout(tenant_id=None):
        methods = StorePaymentMethodService.list_all(enabled_only=True)
        try:
            from services.store_online_payment_service import StoreOnlinePaymentService
            if not StoreOnlinePaymentService.is_configured(tenant_id):
                methods = [m for m in methods if m.code != 'online_pay']
        except Exception:
            methods = [m for m in methods if getattr(m, 'code', '') != 'online_pay']
        return methods

    @staticmethod
    def get_by_code(code: str) -> StorePaymentMethod | None:
        normalized = (code or '').strip().lower()
        if not normalized:
            return None
        return StorePaymentMethod.query.filter_by(code=normalized).first()

    @staticmethod
    def validate_for_checkout(code: str) -> StorePaymentMethod:
        method = StorePaymentMethodService.get_by_code(code)
        if not method or not method.is_enabled:
            raise ValueError('طريقة الدفع غير متاحة.')
        return method

    @staticmethod
    def toggle_enabled(method_id: int, enabled: bool) -> StorePaymentMethod:
        method = db.session.get(StorePaymentMethod, int(method_id))
        if not method:
            raise ValueError('طريقة الدفع غير موجودة.')
        with atomic_transaction('toggle_payment_method'):
            method.is_enabled = bool(enabled)
        return method

    @staticmethod
    def create_method(data: dict) -> StorePaymentMethod:
        code = StorePaymentMethod.normalize_code(data.get('code') or '')
        if StorePaymentMethod.query.filter_by(code=code).first():
            raise ValueError('رمز طريقة الدفع مستخدم مسبقاً.')

        name_ar = (data.get('name_ar') or '').strip()
        name_en = (data.get('name_en') or '').strip()
        if len(name_ar) < 2 and len(name_en) < 2:
            raise ValueError('الاسم بالعربية أو الإنجليزية مطلوب.')

        with atomic_transaction('create_payment_method'):
            method = StorePaymentMethod(
                code=code,
                name_ar=name_ar or name_en,
                name_en=name_en or name_ar,
                description_ar=(data.get('description_ar') or '').strip() or None,
                description_en=(data.get('description_en') or '').strip() or None,
                icon=(data.get('icon') or 'fas fa-money-bill-wave').strip(),
                is_enabled=bool(data.get('is_enabled')),
                is_builtin=False,
                sort_order=int(data.get('sort_order') or 100),
            )
            config = {}
            for key in ('bank_name', 'iban', 'account_name', 'providers', 'instructions'):
                val = (data.get(key) or '').strip()
                if val:
                    config[key] = val
            if config:
                method.set_config(config)
            db.session.add(method)

        return method

    @staticmethod
    def update_method(method_id: int, data: dict) -> StorePaymentMethod:
        method = db.session.get(StorePaymentMethod, int(method_id))
        if not method:
            raise ValueError('طريقة الدفع غير موجودة.')

        with atomic_transaction('update_payment_method'):
            name_ar = (data.get('name_ar') or '').strip()
            name_en = (data.get('name_en') or '').strip()
            if name_ar:
                method.name_ar = name_ar
            if name_en:
                method.name_en = name_en
            method.description_ar = (data.get('description_ar') or '').strip() or None
            method.description_en = (data.get('description_en') or '').strip() or None
            if data.get('icon'):
                method.icon = data['icon'].strip()
            method.is_enabled = bool(data.get('is_enabled'))
            method.sort_order = int(data.get('sort_order') or method.sort_order or 100)

            if not method.is_builtin and data.get('code'):
                new_code = StorePaymentMethod.normalize_code(data['code'])
                clash = StorePaymentMethod.query.filter(
                    StorePaymentMethod.code == new_code,
                    StorePaymentMethod.id != method.id,
                ).first()
                if clash:
                    raise ValueError('رمز طريقة الدفع مستخدم مسبقاً.')
                method.code = new_code

            cfg = method.get_config()
            for key in ('bank_name', 'iban', 'account_name', 'providers', 'instructions'):
                if key in data:
                    val = (data.get(key) or '').strip()
                    if val:
                        cfg[key] = val
                    elif key in cfg:
                        cfg.pop(key, None)
            method.set_config(cfg)

        return method

    @staticmethod
    def delete_method(method_id: int):
        method = db.session.get(StorePaymentMethod, int(method_id))
        if not method:
            raise ValueError('طريقة الدفع غير موجودة.')
        if method.is_builtin:
            raise ValueError('لا يمكن حذف طرق الدفع الأساسية — يمكن إيقافها فقط.')
        with atomic_transaction('delete_payment_method'):
            db.session.delete(method)

    @staticmethod
    def format_checkout_instructions(method: StorePaymentMethod, lang='ar') -> str:
        parts = []
        desc = method.display_description(lang)
        if desc:
            parts.append(desc)
        cfg = method.get_config()
        if method.code == 'bank_transfer':
            if cfg.get('bank_name'):
                parts.append(f"{cfg['bank_name']}")
            if cfg.get('iban'):
                parts.append(f"IBAN: {cfg['iban']}")
            if cfg.get('account_name'):
                parts.append(cfg['account_name'])
        elif cfg.get('instructions'):
            parts.append(cfg['instructions'])
        elif cfg.get('providers'):
            parts.append(cfg['providers'])
        return '\n'.join(parts)
