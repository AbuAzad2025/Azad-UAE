"""
Webhook Service - خدمة Webhooks
معالجة webhooks من بوابات الدفع
"""
from datetime import datetime, timezone
from extensions import db
from models import Donation, PackagePurchase, PaymentLog
from services.notification_service import NotificationService
from sqlalchemy import or_
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
            elif order_id.startswith('STORE_'):
                return WebhookService._process_store_order_webhook(data)
            else:
                logger.warning(f'Unknown order type: {order_id}')
                return {'success': False, 'error': 'Unknown order type'}
        
        except Exception as e:
            logger.error(f'❌ Webhook processing error: {str(e)}')
            return {'success': False, 'error': 'Webhook processing failed'}
    
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

        if (
            payment_status == 'finished'
            and purchase.payment_status == 'completed'
            and purchase.activation_status == 'activated'
        ):
            return {'success': True, 'message': 'Purchase already activated (idempotent)'}

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
        donation = Donation.query.filter(
            or_(
                Donation.transaction_hash == payment_id,
                Donation.gateway_transaction_id == payment_id,
            )
        ).first()

        if not donation:
            logger.warning(f'Donation not found for payment_id: {payment_id}')
            return {'success': False, 'error': 'Donation not found'}

        if donation.status == 'completed' and payment_status == 'finished':
            return {'success': True, 'message': 'Donation already completed (idempotent)'}

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
    def _process_store_order_webhook(data):
        """Confirm online store order after gateway payment."""
        from models import Sale
        from services.store_online_payment_service import StoreOnlinePaymentService
        from services.store_order_service import StoreOrderService

        payment_status = data.get('payment_status')
        payment_id = str(data.get('payment_id', ''))
        order_id = data.get('order_id', '')

        parsed = StoreOnlinePaymentService.parse_store_order_id(order_id)
        if not parsed:
            return {'success': False, 'error': 'Invalid store order id'}

        sale_id, tenant_id = parsed
        sale = Sale.query.filter_by(
            id=sale_id,
            tenant_id=tenant_id,
            source='online_store',
        ).first()
        if not sale:
            return {'success': False, 'error': 'Store sale not found'}

        if payment_id and sale.checkout_gateway_ref and sale.checkout_gateway_ref != payment_id:
            logger.warning('Gateway ref mismatch for sale %s', sale.sale_number)

        if payment_status == 'finished' and sale.status == 'confirmed':
            from services.azad_platform_fee_service import AzadPlatformFeeService
            AzadPlatformFeeService.record_store_online_fee(
                sale,
                gateway_reference=payment_id or getattr(sale, 'checkout_gateway_ref', None),
            )
            db.session.commit()
            return {'success': True, 'message': 'Store order already confirmed (idempotent)'}

        if payment_status == 'finished':
            if sale.status != 'confirmed':
                try:
                    StoreOrderService.confirm_order(sale, mark_paid=True)
                except ValueError as exc:
                    logger.warning('Store order confirm skipped: %s', exc)
            logger.info('Store order %s paid via gateway', sale.sale_number)
        elif payment_status in ('failed', 'expired', 'refunded'):
            if sale.status == 'pending':
                StoreOrderService.cancel_order(sale)
            logger.warning('Store order %s payment %s', sale.sale_number, payment_status)

        return {'success': True, 'message': f'Store order updated to {payment_status}'}

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
            return {'success': False, 'error': 'Webhook processing failed'}
    
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

