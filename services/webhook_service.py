"""
Webhook Service - خدمة Webhooks
معالجة webhooks من بوابات الدفع
"""
from datetime import datetime, timezone
from extensions import db
from models import Donation, PackagePurchase, PaymentLog
from services.notification_service import NotificationService
import hmac
import hashlib
import logging
import json

logger = logging.getLogger(__name__)


class WebhookService:
    """خدمة معالجة Webhooks"""
    
    @staticmethod
    def verify_nowpayments_signature(payload, signature, ipn_secret):
        """
        التحقق من توقيع NOWPayments
        
        Args:
            payload (bytes): محتوى الـ webhook
            signature (str): التوقيع من header
            ipn_secret (str): IPN Secret
        
        Returns:
            bool: صحة التوقيع
        """
        if not ipn_secret:
            logger.warning('NOWPayments IPN secret not configured')
            return False
        
        # حساب التوقيع المتوقع
        expected_signature = hmac.new(
            ipn_secret.encode('utf-8'),
            payload,
            hashlib.sha512
        ).hexdigest()
        
        return hmac.compare_digest(expected_signature, signature)
    
    @staticmethod
    def process_nowpayments_webhook(data):
        """
        معالجة webhook من NOWPayments
        
        Args:
            data (dict): بيانات الـ webhook
        
        Returns:
            dict: نتيجة المعالجة
        """
        try:
            payment_id = data.get('payment_id')
            payment_status = data.get('payment_status')
            order_id = data.get('order_id', '')
            
            logger.info(f'📨 NOWPayments webhook received: {payment_id} - {payment_status}')
            
            # تحديد نوع العملية (شراء أو تبرع)
            if order_id.startswith('PURCHASE_'):
                return WebhookService._process_purchase_webhook(data)
            elif order_id.startswith('DONATION_'):
                return WebhookService._process_donation_webhook(data)
            else:
                logger.warning(f'Unknown order type: {order_id}')
                return {'success': False, 'error': 'Unknown order type'}
        
        except Exception as e:
            logger.error(f'❌ Webhook processing error: {str(e)}')
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def _process_purchase_webhook(data):
        """معالجة webhook للمشتريات"""
        payment_status = data.get('payment_status')
        payment_id = data.get('payment_id')
        
        # البحث عن الشراء
        purchase = PackagePurchase.query.filter_by(transaction_id=payment_id).first()
        
        if not purchase:
            logger.warning(f'Purchase not found for payment_id: {payment_id}')
            return {'success': False, 'error': 'Purchase not found'}
        
        # تحديث الحالة
        if payment_status == 'finished':
            purchase.payment_status = 'completed'
            purchase.activation_status = 'activated'
            purchase.activation_date = datetime.now(timezone.utc)
            
            # إرسال إشعار
            NotificationService.notify_purchase_activated(
                purchase.package.name_ar if purchase.package else 'N/A',
                purchase.customer_name
            )
            
            logger.info(f'✅ Purchase {purchase.id} completed and activated')
            
        elif payment_status == 'failed' or payment_status == 'expired':
            purchase.payment_status = 'failed'
            logger.warning(f'❌ Purchase {purchase.id} failed')
        
        db.session.commit()
        
        return {'success': True, 'message': f'Purchase updated to {payment_status}'}
    
    @staticmethod
    def _process_donation_webhook(data):
        """معالجة webhook للتبرعات"""
        payment_status = data.get('payment_status')
        payment_id = data.get('payment_id')
        
        # البحث عن التبرع
        donation = Donation.query.filter_by(transaction_hash=payment_id).first()
        
        if not donation:
            logger.warning(f'Donation not found for payment_id: {payment_id}')
            return {'success': False, 'error': 'Donation not found'}
        
        # تحديث الحالة
        if payment_status == 'finished':
            donation.status = 'completed'
            donation.completed_at = datetime.now(timezone.utc)
            
            # إرسال إشعار
            NotificationService.notify_payment_received(
                float(donation.amount_usd),
                donation.donor_name or 'مجهول',
                donation.payment_method
            )
            
            logger.info(f'✅ Donation {donation.id} completed')
            
        elif payment_status == 'failed' or payment_status == 'expired':
            donation.status = 'failed'
            logger.warning(f'❌ Donation {donation.id} failed')
        
        db.session.commit()
        
        return {'success': True, 'message': f'Donation updated to {payment_status}'}
    
    @staticmethod
    def verify_stripe_signature(payload, signature, webhook_secret):
        """
        التحقق من توقيع Stripe
        
        Args:
            payload (bytes): محتوى الـ webhook
            signature (str): التوقيع من header
            webhook_secret (str): Webhook Secret
        
        Returns:
            bool: صحة التوقيع
        """
        if not webhook_secret:
            logger.warning('Stripe webhook secret not configured')
            return False
        
        # استخدام مكتبة Stripe للتحقق
        # (يتطلب تثبيت stripe: pip install stripe)
        try:
            import stripe
            stripe.Webhook.construct_event(
                payload, signature, webhook_secret
            )
            return True
        except Exception as e:
            logger.error(f'Stripe signature verification failed: {str(e)}')
            return False
    
    @staticmethod
    def process_stripe_webhook(data):
        """
        معالجة webhook من Stripe
        
        Args:
            data (dict): بيانات الـ webhook
        
        Returns:
            dict: نتيجة المعالجة
        """
        try:
            event_type = data.get('type')
            event_data = data.get('data', {}).get('object', {})
            
            logger.info(f'📨 Stripe webhook received: {event_type}')
            
            if event_type == 'payment_intent.succeeded':
                return WebhookService._process_stripe_payment_success(event_data)
            elif event_type == 'payment_intent.payment_failed':
                return WebhookService._process_stripe_payment_failed(event_data)
            else:
                logger.info(f'Unhandled Stripe event: {event_type}')
                return {'success': True, 'message': 'Event acknowledged'}
        
        except Exception as e:
            logger.error(f'❌ Stripe webhook processing error: {str(e)}')
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def _process_stripe_payment_success(payment_intent):
        """معالجة دفعة ناجحة من Stripe"""
        # استخراج البيانات
        amount = payment_intent.get('amount') / 100  # من cents إلى dollars
        customer_email = payment_intent.get('receipt_email')
        
        logger.info(f'✅ Stripe payment succeeded: ${amount} from {customer_email}')
        
        # إرسال إشعار
        NotificationService.notify_payment_received(
            amount,
            customer_email or 'Unknown',
            'Stripe'
        )
        
        return {'success': True, 'message': 'Payment processed'}
    
    @staticmethod
    def _process_stripe_payment_failed(payment_intent):
        """معالجة دفعة فاشلة من Stripe"""
        customer_email = payment_intent.get('receipt_email')
        error_message = payment_intent.get('last_payment_error', {}).get('message', 'Unknown error')
        
        logger.warning(f'❌ Stripe payment failed for {customer_email}: {error_message}')
        
        # إرسال تنبيه
        NotificationService.notify_security_alert(
            'فشل دفعة Stripe',
            f'فشلت دفعة من {customer_email}: {error_message}'
        )
        
        return {'success': True, 'message': 'Payment failure processed'}

