"""Online payment gateway for store checkout (NOWPayments)."""
from __future__ import annotations

import requests
from decimal import Decimal

from flask import current_app

from extensions import db
from models.payment_vault import PaymentVault
from utils.nowpayments_ipn import get_nowpayments_ipn_url


class StoreOnlinePaymentService:
    ORDER_PREFIX = 'STORE_'

    @staticmethod
    def is_configured() -> bool:
        vault = PaymentVault.query.first()
        if not vault:
            return False
        key = (getattr(vault, 'nowpayments_api_key', None) or '').strip()
        return bool(key)

    @staticmethod
    def _api_key() -> str:
        vault = PaymentVault.query.first()
        key = (getattr(vault, 'nowpayments_api_key', None) or '').strip() if vault else ''
        if not key:
            key = (current_app.config.get('NOWPAYMENTS_API_KEY') or '').strip()
        if not key:
            raise ValueError('بوابة الدفع غير مهيأة على المنصة.')
        return key

    @staticmethod
    def create_payment_for_sale(sale, store, *, customer_email: str = None, crypto_currency: str = 'btc'):
        amount = float(Decimal(str(sale.total_amount or 0)))
        if amount < 1:
            raise ValueError('الحد الأدنى للدفع الإلكتروني 1 USD/AED equivalent.')

        currency = (sale.currency or 'AED').lower()
        order_id = f'{StoreOnlinePaymentService.ORDER_PREFIX}{sale.id}_{store.tenant_id}'
        ipn_url = get_nowpayments_ipn_url()

        payload = {
            'price_amount': amount,
            'price_currency': currency,
            'pay_currency': (crypto_currency or 'btc').lower(),
            'order_id': order_id,
            'order_description': f'Store order {sale.sale_number} — {store.title}',
            'ipn_callback_url': ipn_url,
        }
        if customer_email:
            payload['customer_email'] = customer_email

        headers = {
            'x-api-key': StoreOnlinePaymentService._api_key(),
            'Content-Type': 'application/json',
        }
        response = requests.post(
            'https://api.nowpayments.io/v1/payment',
            json=payload,
            headers=headers,
            timeout=30,
        )
        if response.status_code not in (200, 201):
            raise ValueError(f'فشل إنشاء الدفع: {response.text[:200]}')

        data = response.json()
        payment_id = data.get('payment_id')
        payment_url = data.get('invoice_url') or data.get('payment_url')
        if not payment_url:
            raise ValueError('لم يُرجَع رابط الدفع من البوابة.')

        sale.checkout_gateway_ref = str(payment_id)
        sale.checkout_payment_method = sale.checkout_payment_method or 'online_pay'
        db.session.commit()

        return {
            'payment_id': payment_id,
            'payment_url': payment_url,
            'order_id': order_id,
        }

    @staticmethod
    def parse_store_order_id(order_id: str) -> tuple[int, int] | None:
        if not order_id or not order_id.startswith(StoreOnlinePaymentService.ORDER_PREFIX):
            return None
        try:
            rest = order_id[len(StoreOnlinePaymentService.ORDER_PREFIX):]
            sale_id_str, tenant_id_str = rest.split('_', 1)
            return int(sale_id_str), int(tenant_id_str)
        except (TypeError, ValueError):
            return None
