"""
Health Check Service - خدمة فحص صحة النظام
مراقبة صحة النظام والخدمات المختلفة
"""
from datetime import datetime, timezone
from extensions import db
from models import PaymentVault
import logging
import psutil
import os

logger = logging.getLogger(__name__)


class HealthCheckService:
    """خدمة فحص صحة النظام"""
    
    @staticmethod
    def check_database():
        """فحص الاتصال بقاعدة البيانات"""
        try:
            db.session.execute(db.text('SELECT 1'))
            return {
                'status': 'healthy',
                'message': 'Database connection OK'
            }
        except Exception as e:
            logger.error(f'Database health check failed: {str(e)}')
            return {
                'status': 'unhealthy',
                'message': f'Database error: {str(e)}'
            }
    
    @staticmethod
    def check_nowpayments():
        """فحص تكوين NOWPayments"""
        try:
            vault = PaymentVault.get_platform_vault()
            if not vault:
                return {
                    'status': 'warning',
                    'message': 'Payment vault not initialized'
                }
            
            if vault.nowpayments_api_key and vault.bitcoin_address:
                return {
                    'status': 'healthy',
                    'message': 'NOWPayments configured'
                }
            else:
                return {
                    'status': 'warning',
                    'message': 'NOWPayments not fully configured'
                }
        except Exception as e:
            logger.error(f'NOWPayments health check failed: {str(e)}')
            return {
                'status': 'unhealthy',
                'message': f'Error: {str(e)}'
            }
    
    @staticmethod
    def check_encryption():
        """فحص نظام التشفير"""
        try:
            # التحقق من إمكانية التشفير
            from werkzeug.security import generate_password_hash
            test_hash = generate_password_hash('test')
            
            if test_hash:
                return {
                    'status': 'healthy',
                    'message': 'Encryption system OK'
                }
            else:
                return {
                    'status': 'unhealthy',
                    'message': 'Encryption test failed'
                }
        except Exception as e:
            logger.error(f'Encryption health check failed: {str(e)}')
            return {
                'status': 'unhealthy',
                'message': f'Error: {str(e)}'
            }
    
    @staticmethod
    def check_system_resources():
        """فحص موارد النظام"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            status = 'healthy'
            warnings = []
            
            if cpu_percent > 90:
                status = 'warning'
                warnings.append(f'High CPU usage: {cpu_percent}%')
            
            if memory.percent > 90:
                status = 'warning'
                warnings.append(f'High memory usage: {memory.percent}%')
            
            if disk.percent > 90:
                status = 'warning'
                warnings.append(f'Low disk space: {disk.percent}% used')
            
            return {
                'status': status,
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'disk_percent': disk.percent,
                'warnings': warnings if warnings else None
            }
        except Exception as e:
            logger.error(f'System resources check failed: {str(e)}')
            return {
                'status': 'unknown',
                'message': f'Error: {str(e)}'
            }
    
    @staticmethod
    def get_system_metrics():
        """الحصول على مقاييس النظام"""
        try:
            from models import Donation, PackagePurchase, CardPayment
            
            # إحصائيات قاعدة البيانات
            total_donations = Donation.query.count()
            total_purchases = PackagePurchase.query.count()
            total_cards = CardPayment.query.count()
            
            # معلومات النظام
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            
            return {
                'database': {
                    'total_donations': total_donations,
                    'total_purchases': total_purchases,
                    'total_cards': total_cards
                },
                'process': {
                    'memory_mb': round(memory_info.rss / 1024 / 1024, 2),
                    'cpu_percent': process.cpu_percent(interval=0.1),
                    'threads': process.num_threads(),
                    'uptime_seconds': int((datetime.now() - datetime.fromtimestamp(process.create_time())).total_seconds())
                },
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            logger.error(f'Failed to get system metrics: {str(e)}')
            return {'error': str(e)}
    
    @staticmethod
    def run_full_health_check():
        """تشغيل فحص صحة شامل"""
        checks = {
            'database': HealthCheckService.check_database(),
            'nowpayments': HealthCheckService.check_nowpayments(),
            'encryption': HealthCheckService.check_encryption(),
            'system': HealthCheckService.check_system_resources()
        }
        
        # تحديد الحالة العامة
        statuses = [check['status'] for check in checks.values()]
        
        if 'unhealthy' in statuses:
            overall_status = 'unhealthy'
        elif 'warning' in statuses:
            overall_status = 'warning'
        else:
            overall_status = 'healthy'
        
        return {
            'overall_status': overall_status,
            'checks': checks,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

