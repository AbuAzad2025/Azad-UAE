"""
NOWPayments Integration Service
خدمة التكامل مع NOWPayments للدفع بالعملات الرقمية
"""

import requests
import json
import hashlib
import hmac
import time
from datetime import datetime
from decimal import Decimal
from flask import current_app
from extensions import db
from models import Donation
from utils.nowpayments_ipn import get_nowpayments_ipn_url


class NOWPaymentsService:
    """خدمة NOWPayments للدفع بالعملات الرقمية"""
    
    def __init__(self):
        self.api_key = current_app.config.get('NOWPAYMENTS_API_KEY')
        self.api_url = 'https://api.nowpayments.io/v1'
        self.ipn_secret = current_app.config.get('NOWPAYMENTS_IPN_SECRET')
        
    def create_payment(self, amount, currency='USD', crypto_currency='btc', 
                      order_id=None, customer_email=None, description=None,
                      transaction_type='donation', package=None, 
                      customer_name=None, customer_phone=None,
                      donor_name=None, donor_email=None, donor_message=None):
        """
        إنشاء دفعة جديدة
        
        Args:
            amount (float): المبلغ بالدولار
            currency (str): العملة الأساسية (USD)
            crypto_currency (str): العملة الرقمية المطلوبة
            order_id (str): معرف الطلب
            customer_email (str): إيميل العميل
            description (str): وصف الدفعة
            transaction_type (str): نوع المعاملة (purchase/donation)
            package (str): الباقة المشتراة
            customer_name (str): اسم العميل
            customer_phone (str): رقم الجوال
            
        Returns:
            dict: معلومات الدفعة
        """
        try:
            # التحقق من الحد الأدنى
            if amount < 1:
                return {
                    'success': False,
                    'error': 'الحد الأدنى للتبرع هو $1'
                }
            
            # إعداد البيانات
            data = {
                'price_amount': float(amount),
                'price_currency': currency.lower(),
                'pay_currency': crypto_currency.lower(),
                'order_description': description or f"تبرع لمشروع Azad Systems - ${amount}",
                'ipn_callback_url': get_nowpayments_ipn_url(),
            }
            if order_id:
                data['order_id'] = order_id
            
            # إضافة إيميل العميل إذا كان متوفراً
            if customer_email:
                data['customer_email'] = customer_email
            
            # إرسال الطلب
            headers = {
                'x-api-key': self.api_key,
                'Content-Type': 'application/json'
            }
            
            response = requests.post(
                f"{self.api_url}/payment",
                json=data,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 201:
                payment_data = response.json()
                
                # حفظ الدفعة في قاعدة البيانات
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
                    # معلومات المعاملة
                    transaction_type=transaction_type,
                    package=package,
                    # معلومات العميل/المتبرع
                    customer_name=customer_name if transaction_type == 'purchase' else donor_name,
                    customer_email=customer_email if transaction_type == 'purchase' else donor_email,
                    customer_phone=customer_phone,
                    # معلومات التبرع
                    donor_name=donor_name,
                    donor_email=donor_email,
                    donor_message=donor_message
                )
                
                db.session.add(donation)
                db.session.commit()
                
                return {
                    'success': True,
                    'payment_id': payment_data.get('payment_id'),
                    'payment_address': payment_data.get('pay_address'),
                    'payment_amount': payment_data.get('pay_amount'),
                    'payment_url': payment_data.get('payment_url'),
                    'order_id': payment_data.get('order_id'),
                    'expires_at': payment_data.get('expires_at')
                }
            else:
                error_data = response.json() if response.content else {}
                return {
                    'success': False,
                    'error': error_data.get('message', f'خطأ في API: {response.status_code}')
                }
                
        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'error': f'خطأ في الاتصال: {str(e)}'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'خطأ عام: {str(e)}'
            }
    
    def get_payment_status(self, payment_id):
        """
        الحصول على حالة الدفعة
        
        Args:
            payment_id (str): معرف الدفعة
            
        Returns:
            dict: حالة الدفعة
        """
        try:
            headers = {
                'x-api-key': self.api_key,
                'Content-Type': 'application/json'
            }
            
            response = requests.get(
                f"{self.api_url}/payment/{payment_id}",
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                return {
                    'success': True,
                    'data': response.json()
                }
            else:
                return {
                    'success': False,
                    'error': f'خطأ في الحصول على حالة الدفعة: {response.status_code}'
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': f'خطأ: {str(e)}'
            }
    
    def get_available_currencies(self):
        """
        الحصول على العملات المتاحة
        
        Returns:
            dict: قائمة العملات المتاحة
        """
        try:
            response = requests.get(
                f"{self.api_url}/currencies",
                timeout=30
            )
            
            if response.status_code == 200:
                return {
                    'success': True,
                    'currencies': response.json()
                }
            else:
                return {
                    'success': False,
                    'error': f'خطأ في الحصول على العملات: {response.status_code}'
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': f'خطأ: {str(e)}'
            }
    
    def get_estimated_amount(self, amount, from_currency='usd', to_currency='btc'):
        """
        الحصول على المبلغ المقدر للعملة الرقمية
        
        Args:
            amount (float): المبلغ بالدولار
            from_currency (str): العملة الأساسية
            to_currency (str): العملة الرقمية
            
        Returns:
            dict: المبلغ المقدر
        """
        try:
            params = {
                'amount': amount,
                'currency_from': from_currency,
                'currency_to': to_currency
            }
            
            response = requests.get(
                f"{self.api_url}/estimate",
                params=params,
                timeout=30
            )
            
            if response.status_code == 200:
                return {
                    'success': True,
                    'data': response.json()
                }
            else:
                return {
                    'success': False,
                    'error': f'خطأ في التقدير: {response.status_code}'
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': f'خطأ: {str(e)}'
            }
    
    def verify_ipn(self, request_data, signature):
        """
        التحقق من صحة IPN callback
        
        Args:
            request_data (dict): بيانات الطلب
            signature (str): التوقيع
            
        Returns:
            bool: صحة التوقيع
        """
        try:
            # إنشاء التوقيع المتوقع
            expected_signature = hmac.new(
                self.ipn_secret.encode('utf-8'),
                json.dumps(request_data, sort_keys=True).encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(signature, expected_signature)
            
        except Exception:
            return False
    
    def process_payment_callback(self, payment_data):
        """
        معالجة callback الدفع
        
        Args:
            payment_data (dict): بيانات الدفع
            
        Returns:
            bool: نجح المعالجة
        """
        try:
            payment_id = payment_data.get('payment_id')
            status = payment_data.get('payment_status')
            
            if not payment_id:
                return False
            
            donation = Donation.query.filter(
                db.or_(
                    Donation.transaction_hash == payment_id,
                    Donation.gateway_transaction_id == payment_id
                )
            ).first()
            
            if not donation:
                return False
            
            # تحديث حالة التبرع
            if status == 'finished':
                donation.status = 'completed'
                donation.completed_at = datetime.utcnow()
            elif status == 'failed':
                donation.status = 'failed'
            elif status == 'refunded':
                donation.status = 'refunded'
            
            db.session.commit()
            return True
            
        except Exception as e:
            current_app.logger.error(f"خطأ في معالجة callback: {str(e)}")
            return False
