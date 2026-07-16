"""
Notification Service - خدمة الإشعارات
إرسال إشعارات فورية للمستخدمين
"""
from datetime import datetime, timezone
from extensions import db
from models import PaymentLog
import logging

logger = logging.getLogger(__name__)


class NotificationService:
    """خدمة الإشعارات"""
    
    # مخزن الإشعارات في الذاكرة (يمكن استخدام Redis للإنتاج)
    _notifications: list[dict] = []
    
    @staticmethod
    def send_notification(title, message, notification_type='info', data=None):
        """
        إرسال إشعار
        
        Args:
            title (str): عنوان الإشعار
            message (str): نص الإشعار
            notification_type (str): نوع الإشعار (info, success, warning, danger)
            data (dict): بيانات إضافية
        """
        notification = {
            'id': len(NotificationService._notifications) + 1,
            'title': title,
            'message': message,
            'type': notification_type,
            'data': data or {},
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'read': False
        }
        
        NotificationService._notifications.append(notification)
        logger.info(f'📨 Notification sent: {title} - {message}')
        
        return notification
    
    @staticmethod
    def get_recent_notifications(limit=10):
        """جلب آخر الإشعارات"""
        return NotificationService._notifications[-limit:]
    
    @staticmethod
    def mark_as_read(notification_id):
        """تعليم الإشعار كمقروء"""
        for notif in NotificationService._notifications:
            if notif['id'] == notification_id:
                notif['read'] = True
                break
    
    @staticmethod
    def notify_payment_received(amount, customer_name, payment_method):
        """إشعار باستلام دفعة"""
        return NotificationService.send_notification(
            title='💰 دفعة جديدة',
            message=f'تم استلام ${amount} من {customer_name} عبر {payment_method}',
            notification_type='success',
            data={'amount': amount, 'customer': customer_name}
        )
    
    @staticmethod
    def notify_security_alert(alert_type, details):
        """إشعار بتنبيه أمني"""
        return NotificationService.send_notification(
            title='🚨 تنبيه أمني',
            message=f'{alert_type}: {details}',
            notification_type='danger',
            data={'alert_type': alert_type, 'details': details}
        )
    
    @staticmethod
    def notify_purchase_activated(package_name, customer_name):
        """إشعار بتفعيل باقة"""
        return NotificationService.send_notification(
            title='✅ تفعيل باقة',
            message=f'تم تفعيل باقة {package_name} للعميل {customer_name}',
            notification_type='info',
            data={'package': package_name, 'customer': customer_name}
        )
    
    @staticmethod
    def notify_auto_approval(count, total_amount):
        """إشعار بالقبول التلقائي"""
        return NotificationService.send_notification(
            title='⚡ قبول تلقائي',
            message=f'تم قبول {count} عملية تلقائياً بمبلغ ${total_amount}',
            notification_type='success',
            data={'count': count, 'amount': total_amount}
        )


class SecurityService:
    """خدمة الأمان والتنبيهات"""
    
    # قائمة سوداء للـ IPs المشبوهة
    _blacklist: set = set()

    # سجل المحاولات الفاشلة
    _failed_attempts: dict = {}
    
    @staticmethod
    def detect_suspicious_activity(ip_address, user_agent, action):
        """
        كشف النشاط المشبوه
        
        Args:
            ip_address (str): عنوان IP
            user_agent (str): User Agent
            action (str): الإجراء المنفذ
        
        Returns:
            dict: نتيجة الفحص
        """
        # فحص القائمة السوداء
        if ip_address in SecurityService._blacklist:
            NotificationService.notify_security_alert(
                'IP محظور',
                f'محاولة وصول من IP محظور: {ip_address}'
            )
            return {'suspicious': True, 'reason': 'blacklisted_ip'}
        
        # فحص المحاولات الفاشلة
        if ip_address in SecurityService._failed_attempts:
            attempts = SecurityService._failed_attempts[ip_address]
            if attempts['count'] >= 5:
                SecurityService._blacklist.add(ip_address)
                NotificationService.notify_security_alert(
                    'IP محظور تلقائياً',
                    f'تم حظر IP {ip_address} بسبب محاولات فاشلة متكررة'
                )
                return {'suspicious': True, 'reason': 'too_many_failed_attempts'}
        
        # فحص User Agent المشبوه
        suspicious_agents = ['bot', 'crawler', 'scraper', 'scanner']
        if any(agent in user_agent.lower() for agent in suspicious_agents):
            NotificationService.notify_security_alert(
                'User Agent مشبوه',
                f'كشف user agent مشبوه: {user_agent[:100]}'
            )
            return {'suspicious': True, 'reason': 'suspicious_user_agent'}
        
        return {'suspicious': False}
    
    @staticmethod
    def log_failed_attempt(ip_address):
        """تسجيل محاولة فاشلة"""
        if ip_address not in SecurityService._failed_attempts:
            SecurityService._failed_attempts[ip_address] = {
                'count': 0,
                'first_attempt': datetime.now(timezone.utc),
                'last_attempt': None
            }
        
        SecurityService._failed_attempts[ip_address]['count'] += 1
        SecurityService._failed_attempts[ip_address]['last_attempt'] = datetime.now(timezone.utc)
    
    @staticmethod
    def reset_failed_attempts(ip_address):
        """إعادة تعيين المحاولات الفاشلة"""
        if ip_address in SecurityService._failed_attempts:
            del SecurityService._failed_attempts[ip_address]
    
    @staticmethod
    def get_security_status():
        """الحصول على حالة الأمان"""
        return {
            'blacklisted_ips': len(SecurityService._blacklist),
            'failed_attempts': len(SecurityService._failed_attempts),
            'total_failed_count': sum(
                data['count'] for data in SecurityService._failed_attempts.values()
            ),
            'security_level': SecurityService._calculate_security_level()
        }
    
    @staticmethod
    def _calculate_security_level():
        """حساب مستوى الأمان"""
        failed_count = len(SecurityService._failed_attempts)
        blacklisted = len(SecurityService._blacklist)
        
        if blacklisted > 10 or failed_count > 20:
            return 'low'
        elif blacklisted > 5 or failed_count > 10:
            return 'medium'
        else:
            return 'high'

