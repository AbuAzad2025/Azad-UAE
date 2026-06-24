"""NOWPayments integration for crypto donations and purchases."""

import hashlib
import hmac
import json
from datetime import datetime
from decimal import Decimal

import requests
from flask import current_app

from extensions import db
from models import Donation
from services.payments.nowpayments_provider import NowPaymentsProvider
from utils.nowpayments_ipn import get_nowpayments_ipn_url


class NOWPaymentsService:
    def __init__(self):
        self.provider = NowPaymentsProvider()
        self.api_key = self.provider.api_key
        self.api_url = self.provider.api_base
        self.ipn_secret = self.provider.ipn_secret

    def create_payment(
        self,
        amount,
        currency='USD',
        crypto_currency='btc',
        order_id=None,
        customer_email=None,
        description=None,
        transaction_type='donation',
        package=None,
        customer_name=None,
        customer_phone=None,
        donor_name=None,
        donor_email=None,
        donor_message=None,
    ):
        try:
            if amount < 1:
                return {
                    'success': False,
                    'error': 'الحد الأدنى للتبرع هو $1',
                }

            data = {
                'price_amount': float(amount),
                'price_currency': currency.lower(),
                'pay_currency': crypto_currency.lower(),
                'order_description': description or f"تبرع لمشروع Azad Systems - ${amount}",
                'ipn_callback_url': get_nowpayments_ipn_url(),
            }
            if order_id:
                data['order_id'] = order_id
            if customer_email:
                data['customer_email'] = customer_email

            headers = {
                'x-api-key': self.api_key,
                'Content-Type': 'application/json',
            }

            response = requests.post(
                f"{self.api_url}/payment",
                json=data,
                headers=headers,
                timeout=30,
            )

            if response.status_code == 201:
                payment_data = response.json()

                donation = Donation(
                    amount_usd=Decimal(str(amount)),
                    payment_method='crypto',
                    crypto_type=crypto_currency,
                    wallet_address=payment_data.get('pay_address'),
                    transaction_hash=payment_data.get('payment_id'),
                    status='pending',
                    gateway_name='nowpayments',
                    gateway_transaction_id=payment_data.get('payment_id'),
                    gateway_status='pending',
                    transaction_type=transaction_type,
                    package=package,
                    customer_name=customer_name if transaction_type == 'purchase' else donor_name,
                    customer_email=customer_email if transaction_type == 'purchase' else donor_email,
                    customer_phone=customer_phone,
                    donor_name=donor_name,
                    donor_email=donor_email,
                    donor_message=donor_message,
                )

                db.session.add(donation)
                try:
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                    raise

                return {
                    'success': True,
                    'payment_id': payment_data.get('payment_id'),
                    'payment_address': payment_data.get('pay_address'),
                    'payment_amount': payment_data.get('pay_amount'),
                    'payment_url': payment_data.get('payment_url'),
                    'order_id': payment_data.get('order_id'),
                    'expires_at': payment_data.get('expires_at'),
                }

            current_app.logger.warning(
                'NOWPayments create_payment failed: status=%s body=%s',
                response.status_code,
                response.text[:500],
            )
            return {
                'success': False,
                'error': 'تعذر إنشاء دفعة NOWPayments حالياً',
            }

        except requests.exceptions.RequestException:
            current_app.logger.exception('NOWPayments create_payment request failed')
            return {
                'success': False,
                'error': 'تعذر الاتصال بخدمة NOWPayments حالياً',
            }
        except Exception:
            current_app.logger.exception('NOWPayments create_payment failed')
            return {
                'success': False,
                'error': 'تعذر إنشاء دفعة NOWPayments حالياً',
            }

    def get_payment_status(self, payment_id):
        try:
            headers = {
                'x-api-key': self.api_key,
                'Content-Type': 'application/json',
            }

            response = requests.get(
                f"{self.api_url}/payment/{payment_id}",
                headers=headers,
                timeout=30,
            )

            if response.status_code == 200:
                return {
                    'success': True,
                    'data': response.json(),
                }

            current_app.logger.warning(
                'NOWPayments get_payment_status failed: status=%s',
                response.status_code,
            )
            return {
                'success': False,
                'error': 'تعذر جلب حالة الدفعة حالياً',
            }

        except Exception:
            current_app.logger.exception('NOWPayments get_payment_status failed')
            return {
                'success': False,
                'error': 'تعذر جلب حالة الدفعة حالياً',
            }

    def get_available_currencies(self):
        try:
            response = requests.get(
                f"{self.api_url}/currencies",
                timeout=30,
            )

            if response.status_code == 200:
                return {
                    'success': True,
                    'currencies': response.json(),
                }

            current_app.logger.warning(
                'NOWPayments get_available_currencies failed: status=%s',
                response.status_code,
            )
            return {
                'success': False,
                'error': 'تعذر جلب العملات المتاحة حالياً',
            }

        except Exception:
            current_app.logger.exception('NOWPayments get_available_currencies failed')
            return {
                'success': False,
                'error': 'تعذر جلب العملات المتاحة حالياً',
            }

    def get_estimated_amount(self, amount, from_currency='usd', to_currency='btc'):
        try:
            params = {
                'amount': amount,
                'currency_from': from_currency,
                'currency_to': to_currency,
            }

            response = requests.get(
                f"{self.api_url}/estimate",
                params=params,
                timeout=30,
            )

            if response.status_code == 200:
                return {
                    'success': True,
                    'data': response.json(),
                }

            current_app.logger.warning(
                'NOWPayments get_estimated_amount failed: status=%s',
                response.status_code,
            )
            return {
                'success': False,
                'error': 'تعذر تقدير المبلغ حالياً',
            }

        except Exception:
            current_app.logger.exception('NOWPayments get_estimated_amount failed')
            return {
                'success': False,
                'error': 'تعذر تقدير المبلغ حالياً',
            }

    def verify_ipn(self, request_data, signature):
        try:
            expected_signature = hmac.new(
                self.ipn_secret.encode('utf-8'),
                json.dumps(request_data, sort_keys=True).encode('utf-8'),
                hashlib.sha256,
            ).hexdigest()

            return hmac.compare_digest(signature, expected_signature)

        except Exception:
            return False

    def process_payment_callback(self, payment_data):
        try:
            payment_id = payment_data.get('payment_id')
            status = payment_data.get('payment_status')

            if not payment_id:
                return False

            donation = Donation.query.filter(
                db.or_(
                    Donation.transaction_hash == payment_id,
                    Donation.gateway_transaction_id == payment_id,
                )
            ).first()

            if not donation:
                return False

            if status == 'finished':
                donation.status = 'completed'
                donation.completed_at = datetime.utcnow()
            elif status == 'failed':
                donation.status = 'failed'
            elif status == 'refunded':
                donation.status = 'refunded'

            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                raise

            return True

        except Exception as e:
            current_app.logger.error(f"خطأ في معالجة callback: {str(e)}")
            return False
