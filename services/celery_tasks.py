from celery import Celery
from flask import current_app
import os


celery = Celery(
    'garage_tasks',
    broker=os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0'),
    backend=os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
)

celery.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Dubai',
    enable_utc=True,
)


@celery.task
def generate_monthly_report(month: int, year: int):
    from app import create_app
    from services.report_service import ReportService
    
    app = create_app()
    with app.app_context():
        report = ReportService.generate_monthly_report(month, year)
        return {'success': True, 'report_id': report.id if report else None}


@celery.task
def send_invoice_email(sale_id: int):
    from app import create_app
    from models import Sale
    from flask_mail import Message
    from extensions import mail
    
    app = create_app()
    with app.app_context():
        sale = Sale.query.get(sale_id)
        if sale and sale.customer and sale.customer.email:
            msg = Message(
                subject=f'فاتورة رقم {sale.sale_number}',
                recipients=[sale.customer.email],
                body=f'تجدون في المرفق فاتورتكم رقم {sale.sale_number}'
            )
            mail.send(msg)
            return {'success': True}
        return {'success': False}


@celery.task
def auto_backup_database():
    from app import create_app
    from services.backup_service import BackupService
    
    app = create_app()
    with app.app_context():
        backup = BackupService.auto_backup_daily()
        return {'success': bool(backup), 'backup': backup}


@celery.task
def update_exchange_rates():
    from app import create_app
    from services.currency_service import CurrencyService
    
    app = create_app()
    with app.app_context():
        result = CurrencyService.update_all_rates()
        return result


@celery.task
def train_neural_models():
    from app import create_app
    from ai_knowledge.neural_engine import get_neural_engine
    
    app = create_app()
    with app.app_context():
        neural = get_neural_engine()
        results = neural.train_all_models()
        return results


@celery.task
def send_payment_reminders():
    from app import create_app
    from models import Customer
    from services.whatsapp_service import WhatsAppService
    from decimal import Decimal
    
    app = create_app()
    with app.app_context():
        customers = Customer.query.filter_by(is_active=True).all()
        sent = 0
        
        for customer in customers:
            balance = customer.get_balance_aed()
            if balance > Decimal('1000') and customer.phone:
                result = WhatsAppService.send_payment_reminder(
                    customer.phone,
                    customer.name,
                    float(balance)
                )
                if result.get('success'):
                    sent += 1
        
        return {'sent': sent, 'total_checked': len(customers)}


@celery.task
def cleanup_old_cache():
    from extensions import cache
    
    try:
        cache.clear()
        return {'success': True, 'message': 'Cache cleared'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

