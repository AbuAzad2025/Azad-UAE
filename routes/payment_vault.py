"""
Payment Vault Routes - مسارات الخزينة السرية
مسارات محمية بكلمة مرور منفصلة للدفع والتبرعات
"""

from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, session
from flask_login import login_required, current_user
from extensions import db, limiter, csrf
from models import PaymentVault, PaymentTransaction, PaymentLog, Donation, CardPayment, Package, PackagePurchase
from services.nowpayments_service import NOWPaymentsService
from services.logging_core import LoggingCore
from utils.decorators import owner_only
import secrets
import string
import logging
import re
import os
from urllib.parse import urlparse

payment_vault_bp = Blueprint('payment_vault', __name__, url_prefix='/payment-vault')
logger = logging.getLogger(__name__)

_DEV_VAULT_ORIGINS = frozenset({
    'http://localhost:5000',
    'http://127.0.0.1:5000',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
})


def _get_azad_platform_vault():
    """Return the Azad/platform vault controlled by the global owner."""
    return PaymentVault.get_platform_vault()


def _get_vault_for_current_tenant():
    """Backward-compatible helper name for owner vault routes."""
    return _get_azad_platform_vault()


def _is_production_env() -> bool:
    app_env = (os.environ.get('APP_ENV') or 'production').strip().lower()
    debug = (os.environ.get('DEBUG') or '').strip().lower() in ('1', 'true', 'yes', 'y')
    return app_env == 'production' and not debug


def _is_duplicate_webhook(provider: str, event_id: str | None) -> bool:
    """Idempotent webhook deduplication via cache (24h TTL)."""
    if not event_id:
        return False
    try:
        from extensions import cache
        key = f'webhook:{provider}:{event_id}'
        if cache.get(key):
            logger.warning('%s webhook replay blocked: %s', provider, event_id)
            return True
        cache.set(key, '1', timeout=86400)
    except Exception:
        logger.exception('Webhook dedup cache error for %s %s', provider, event_id)
    return False


def _payment_vault_trusted_origins() -> frozenset[str]:
    from flask import current_app

    configured = current_app.config.get('PAYMENT_VAULT_TRUSTED_ORIGINS') or []
    origins = {str(o).strip().rstrip('/') for o in configured if o}
    if origins:
        return frozenset(origins)

    if _is_production_env():
        base = (current_app.config.get('BASE_URL') or '').strip().rstrip('/')
        return frozenset({base}) if base else frozenset()

    return _DEV_VAULT_ORIGINS


def _origin_from_referer(referer: str) -> str | None:
    try:
        parsed = urlparse(referer)
        if parsed.scheme and parsed.netloc:
            return f'{parsed.scheme}://{parsed.netloc}'.rstrip('/')
    except Exception:
        return None
    return None


def _validate_public_api_origin():
    """Reject cross-site POSTs; require Origin/Referer in trusted allowlist."""
    trusted = _payment_vault_trusted_origins()
    if not trusted:
        logger.warning('Payment vault public API rejected: trusted origins not configured')
        return jsonify({'success': False, 'error': 'Origin policy not configured'}), 503

    origin = (request.headers.get('Origin') or '').strip().rstrip('/')
    referer = (request.headers.get('Referer') or '').strip()

    if origin:
        if origin not in trusted:
            logger.warning('Payment vault public API rejected: origin=%s', origin)
            return jsonify({'success': False, 'error': 'Origin غير مسموح'}), 403
        return None

    if referer:
        ref_origin = _origin_from_referer(referer)
        if ref_origin and ref_origin in trusted:
            return None
        logger.warning('Payment vault public API rejected: referer=%s', referer[:120])
        return jsonify({'success': False, 'error': 'Referer غير مسموح'}), 403

    return jsonify({'success': False, 'error': 'Origin أو Referer مطلوب'}), 403


@payment_vault_bp.before_request
def _protect_owner_vault_pages():
    path = request.path or ''
    if path.startswith('/payment-vault/api/') or path.startswith('/payment-vault/webhook/'):
        return None

    if not current_user.is_authenticated:
        flash('الرجاء تسجيل الدخول أولاً', 'warning')
        return redirect(url_for('auth.login'))

    if not current_user.is_owner:
        flash('❌ غير مصرح - الخزينة السرية للمالك فقط!', 'danger')
        return redirect(url_for('main.dashboard'))

    from utils.security_helpers import enforce_owner_ip_if_needed
    enforce_owner_ip_if_needed()

    return None


@payment_vault_bp.route('/')
@owner_only
def index():
    """الصفحة الرئيسية للخزينة السرية"""
    return render_template('payment_vault/index.html')


@payment_vault_bp.route('/unlock', methods=['GET', 'POST'])
@owner_only
@limiter.limit("5 per minute")
def unlock_vault():
    """فتح الخزينة السرية"""
    if request.method == 'POST':
        password = request.form.get('vault_password', '').strip()
        
        if not password:
            flash('❌ يرجى إدخال كلمة مرور الخزينة', 'danger')
            return render_template('payment_vault/unlock.html')
        
        # البحث عن الخزينة أو إنشاؤها
        vault = _get_vault_for_current_tenant()
        if not vault:
            # إنشاء خزينة جديدة
            vault = PaymentVault()
            vault.tenant_id = None
            vault.set_vault_password(password)  # كلمة المرور الأولى
            vault.nowpayments_api_key = ""
            vault.nowpayments_ipn_secret = ""
            vault.bitcoin_address = ""
            vault.is_locked = False
            db.session.add(vault)
            db.session.commit()
            
            # تسجيل العملية
            PaymentLog.log_action(
                vault_id=vault.id,
                action='vault_created',
                description='تم إنشاء الخزينة السرية',
                level='info',
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )
            
            flash('✅ تم إنشاء الخزينة السرية بنجاح!', 'success')
            return redirect(url_for('payment_vault.dashboard'))
        
        # محاولة فتح الخزينة
        if vault.unlock_vault(password):
            # تسجيل العملية
            PaymentLog.log_action(
                vault_id=vault.id,
                action='vault_unlocked',
                description='تم فتح الخزينة السرية',
                level='info',
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )
            
            flash('✅ تم فتح الخزينة السرية بنجاح!', 'success')
            return redirect(url_for('payment_vault.dashboard'))
        else:
            # تسجيل المحاولة الفاشلة
            PaymentLog.log_action(
                vault_id=vault.id,
                action='vault_unlock_failed',
                description='محاولة فتح فاشلة - كلمة مرور خاطئة',
                level='warning',
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )
            
            if vault.is_locked_out():
                flash('❌ تم قفل الخزينة بسبب المحاولات الفاشلة المتكررة!', 'danger')
            else:
                flash('❌ كلمة مرور الخزينة غير صحيحة!', 'danger')
            
            return render_template('payment_vault/unlock.html')
    
    return render_template('payment_vault/unlock.html')


@payment_vault_bp.route('/dashboard')
@owner_only
def dashboard():
    """لوحة تحكم الخزينة السرية"""
    # التحقق من وجود الخزينة
    vault = _get_vault_for_current_tenant()
    if not vault or vault.is_locked:
        flash('❌ يجب فتح الخزينة أولاً', 'warning')
        return redirect(url_for('payment_vault.unlock_vault'))
    
    # جلب التحليلات المتقدمة
    from services.analytics_service import AnalyticsService
    from services.notification_service import SecurityService

    tid = None

    # الإحصائيات الأساسية (مُفلترة بـ tenant_id)
    purchases = Donation.query.filter_by(tenant_id=tid, transaction_type='purchase').all()
    donations = Donation.query.filter_by(tenant_id=tid, transaction_type='donation').all()
    
    stats = {
        'total_purchases': len(purchases),
        'total_donations': len(donations),
        'total_revenue': sum(float(p.amount_usd or 0) for p in purchases + donations if p.status == 'completed'),
        'pending_count': sum(1 for p in purchases + donations if p.status == 'pending')
    }
    
    # إحصائيات اليوم
    daily_stats = AnalyticsService.get_daily_stats()
    stats.update(daily_stats)
    
    # حالة الأمان
    security_status = SecurityService.get_security_status()
    
    # آخر العمليات (مُفلترة بـ tenant_id)
    recent_purchases = Donation.query.filter_by(tenant_id=tid, transaction_type='purchase').order_by(Donation.created_at.desc()).limit(5).all()
    recent_donations = Donation.query.filter_by(tenant_id=tid, transaction_type='donation').order_by(Donation.created_at.desc()).limit(5).all()
    
    # بيانات الرسم البياني (شهرياً)
    revenue_data = AnalyticsService.get_revenue_by_period(months=6)
    monthly_labels = revenue_data['labels']
    monthly_purchases = revenue_data['purchases']
    monthly_donations = revenue_data['donations']
    
    # إحصائيات طرق الدفع
    payment_methods_stats = AnalyticsService.get_payment_method_stats()
    
    # تحليل سلوك العملاء
    customer_behavior = AnalyticsService.get_customer_behavior()
    
    # أداء الباقات
    package_performance = AnalyticsService.get_package_performance()
    
    return render_template('payment_vault/dashboard.html',
                         vault=vault,
                         stats=stats,
                         security_status=security_status,
                         recent_purchases=recent_purchases,
                         recent_donations=recent_donations,
                         monthly_labels=monthly_labels,
                         monthly_purchases=monthly_purchases,
                         monthly_donations=monthly_donations,
                         payment_methods_stats=payment_methods_stats,
                         customer_behavior=customer_behavior,
                         package_performance=package_performance)


# تم نقل route /purchases إلى view_purchases في نهاية الملف


@payment_vault_bp.route('/settings', methods=['GET', 'POST'])
@owner_only
def settings():
    """إعدادات الخزينة السرية"""
    vault = _get_vault_for_current_tenant()
    if not vault or not vault.is_vault_accessible():
        flash('❌ الخزينة مقفلة، يرجى إدخال كلمة المرور', 'warning')
        return redirect(url_for('payment_vault.unlock_vault'))
    
    if request.method == 'POST':
        def _as_float(value, default):
            try:
                if value is None:
                    return float(default)
                s = str(value).strip()
                if s == "":
                    return float(default)
                return float(s)
            except Exception:
                return float(default)

        def _as_int(value, default):
            try:
                if value is None:
                    return int(default)
                s = str(value).strip()
                if s == "":
                    return int(default)
                return int(s)
            except Exception:
                return int(default)

        # تحديث إعدادات الدفع - Crypto
        vault.nowpayments_api_key = request.form.get('nowpayments_api_key', vault.nowpayments_api_key)
        vault.nowpayments_ipn_secret = request.form.get('nowpayments_ipn_secret', vault.nowpayments_ipn_secret)
        vault.bitcoin_address = request.form.get('bitcoin_address', vault.bitcoin_address)
        vault.ethereum_address = request.form.get('ethereum_address', vault.ethereum_address)
        vault.usdt_address = request.form.get('usdt_address', vault.usdt_address)
        
        # تحديث إعدادات PayPal
        vault.paypal_business_email = request.form.get('paypal_business_email', vault.paypal_business_email)
        vault.paypal_client_id = request.form.get('paypal_client_id', vault.paypal_client_id)
        vault.paypal_client_secret = request.form.get('paypal_client_secret', vault.paypal_client_secret)
        vault.paypal_mode = request.form.get('paypal_mode', vault.paypal_mode)
        
        # تحديث معلومات البنك
        vault.bank_name = request.form.get('bank_name', vault.bank_name)
        vault.bank_account_name = request.form.get('bank_account_name', vault.bank_account_name)
        vault.bank_account_number = request.form.get('bank_account_number', vault.bank_account_number)
        vault.bank_iban = request.form.get('bank_iban', vault.bank_iban)
        vault.bank_swift_code = request.form.get('bank_swift_code', vault.bank_swift_code)
        vault.bank_branch = request.form.get('bank_branch', vault.bank_branch)
        vault.bank_country = request.form.get('bank_country', vault.bank_country)
        vault.bank_currency = request.form.get('bank_currency', vault.bank_currency)
        
        # تحديث إعدادات Stripe
        vault.stripe_publishable_key = request.form.get('stripe_publishable_key', vault.stripe_publishable_key)
        vault.stripe_secret_key = request.form.get('stripe_secret_key', vault.stripe_secret_key)
        vault.stripe_webhook_secret = request.form.get('stripe_webhook_secret', vault.stripe_webhook_secret)
        
        # تحديث حدود الدفع
        vault.min_donation_amount = _as_float(request.form.get('min_donation_amount'), vault.min_donation_amount)
        vault.max_donation_amount = _as_float(request.form.get('max_donation_amount'), vault.max_donation_amount)
        vault.daily_limit = _as_float(request.form.get('daily_limit'), vault.daily_limit)

        vault.donations_enabled = bool(request.form.get('donations_enabled'))
        vault.donation_page_enabled = bool(request.form.get('donation_page_enabled'))
        vault.donation_title_ar = request.form.get('donation_title_ar') or vault.donation_title_ar
        vault.donation_title_en = request.form.get('donation_title_en') or vault.donation_title_en
        vault.donation_intro_ar = request.form.get('donation_intro_ar') or vault.donation_intro_ar
        vault.donation_intro_en = request.form.get('donation_intro_en') or vault.donation_intro_en
        vault.donation_debit_account = (request.form.get('donation_debit_account') or '1120').strip()
        vault.donation_credit_account = (request.form.get('donation_credit_account') or '4200').strip()
        
        # تحديث إعدادات الأمان
        vault.require_2fa = bool(request.form.get('require_2fa'))
        vault.auto_lock_minutes = _as_int(request.form.get('auto_lock_minutes'), vault.auto_lock_minutes)
        vault.max_failed_attempts = _as_int(request.form.get('max_failed_attempts'), vault.max_failed_attempts)
        
        vault.updated_at = datetime.utcnow()
        db.session.commit()
        
        # تسجيل العملية
        PaymentLog.log_action(
            vault_id=vault.id,
            action='settings_updated',
            description='تم تحديث إعدادات الخزينة',
            level='info',
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        flash('✅ تم تحديث إعدادات الخزينة بنجاح!', 'success')
        return redirect(url_for('payment_vault.settings'))
    
    return render_template('payment_vault/settings.html', vault=vault)




@payment_vault_bp.route('/donations')
@owner_only
def donations():
    """عرض التبرعات"""
    vault = _get_vault_for_current_tenant()
    if not vault or vault.is_locked:
        flash('❌ يجب فتح الخزينة أولاً', 'warning')
        return redirect(url_for('payment_vault.unlock_vault'))
    
    # الفلاتر
    status_filter = request.args.get('status', '')
    crypto_filter = request.args.get('crypto', '')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search_query = request.args.get('search', '')
    
    # Query (مُفلترة بـ tenant_id)
    tid = None
    query = Donation.query.filter_by(tenant_id=tid, transaction_type='donation')

    if status_filter:
        query = query.filter_by(status=status_filter)
    if crypto_filter:
        query = query.filter_by(crypto_type=crypto_filter)
    if search_query:
        query = query.filter(
            db.or_(
                Donation.donor_name.ilike(f'%{search_query}%'),
                Donation.donor_email.ilike(f'%{search_query}%')
            )
        )
    
    pagination = query.order_by(Donation.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    donations = pagination.items

    total_donations = pagination.total
    completed_count = query.filter(Donation.status == 'completed').count()
    pending_count = query.filter(Donation.status == 'pending').count()
    total_amount = float(
        query.with_entities(db.func.coalesce(db.func.sum(Donation.amount_usd), 0)).scalar() or 0
    )
    
    return render_template('payment_vault/donations.html',
                         donations=donations,
                         pagination=pagination,
                         total_donations=total_donations,
                         completed_count=completed_count,
                         pending_count=pending_count,
                         total_amount=total_amount)


@payment_vault_bp.route('/packages-management')
@owner_only
def packages_management():
    """إدارة الباقات من الخزينة"""
    vault = _get_vault_for_current_tenant()
    if not vault or vault.is_locked:
        flash('❌ يجب فتح الخزينة أولاً', 'warning')
        return redirect(url_for('payment_vault.unlock_vault'))
    
    # جلب جميع الباقات
    packages = Package.query.order_by(Package.sort_order.asc()).all()
    
    # إحصائيات الباقات من جدول الشراء الجديد
    basic_purchases = PackagePurchase.query.join(Package).filter(Package.slug == 'basic').count()
    pro_purchases = PackagePurchase.query.join(Package).filter(Package.slug == 'professional').count()
    ent_purchases = PackagePurchase.query.join(Package).filter(Package.slug == 'enterprise').count()
    
    package_stats = [basic_purchases, pro_purchases, ent_purchases]
    
    return render_template('payment_vault/packages.html',
                         packages=packages,
                         package_stats=package_stats)


@payment_vault_bp.route('/package/create', methods=['POST'])
@owner_only
def create_package():
    """إنشاء باقة جديدة من لوحة الخزينة."""
    vault = _get_vault_for_current_tenant()
    if not vault or vault.is_locked:
        flash('❌ يجب فتح الخزينة أولاً', 'warning')
        return redirect(url_for('payment_vault.unlock_vault'))

    def _slugify(value):
        value = re.sub(r'[^a-zA-Z0-9\\s_-]+', '', (value or '').strip().lower())
        value = re.sub(r'[-\\s]+', '-', value).strip('-')
        return value or f'package-{secrets.token_hex(3)}'

    def _as_float(value, default=0):
        try:
            return float(str(value).strip() or default)
        except Exception:
            return float(default)

    def _as_int(value, default=0):
        try:
            return int(str(value).strip() or default)
        except Exception:
            return int(default)

    try:
        name_ar = (request.form.get('name_ar') or '').strip()
        name_en = (request.form.get('name_en') or '').strip()
        slug = _slugify(request.form.get('slug') or name_en or name_ar)

        if not name_ar or not name_en:
            flash('❌ اسم الباقة بالعربية والإنجليزية مطلوبان', 'danger')
            return redirect(url_for('payment_vault.packages_management'))

        existing = Package.query.filter_by(slug=slug).first()
        if existing:
            flash('❌ هذا الرابط المختصر مستخدم بالفعل لباقـة أخرى', 'danger')
            return redirect(url_for('payment_vault.packages_management'))

        features_text = (request.form.get('features') or '').strip()
        package = Package(
            name_ar=name_ar,
            name_en=name_en,
            slug=slug,
            icon=(request.form.get('icon') or '📦').strip() or '📦',
            price=_as_float(request.form.get('price'), 0),
            description_ar=(request.form.get('description_ar') or '').strip() or None,
            description_en=(request.form.get('description_en') or '').strip() or None,
            features=[line.strip() for line in features_text.splitlines() if line.strip()],
            is_active=request.form.get('is_active') == 'on',
            is_featured=request.form.get('is_featured') == 'on',
            badge_text=(request.form.get('badge_text') or '').strip() or None,
            sort_order=_as_int(request.form.get('sort_order'), 0),
            support_duration_months=_as_int(request.form.get('support_duration_months'), 3),
            max_users=_as_int(request.form.get('max_users'), 1),
            max_branches=_as_int(request.form.get('max_branches'), 1),
        )

        db.session.add(package)
        db.session.commit()

        LoggingCore.log_audit(
            action='create',
            table_name='packages',
            record_id=package.id,
            changes={'package': package.name_ar, 'slug': package.slug}
        )

        flash('✅ تم إنشاء الباقة بنجاح', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'❌ خطأ أثناء إنشاء الباقة: {str(e)}', 'danger')

    return redirect(url_for('payment_vault.packages_management'))


@payment_vault_bp.route('/package/<int:package_id>/edit', methods=['GET', 'POST'])
@owner_only
def edit_package(package_id):
    """تعديل باقة"""
    vault = _get_vault_for_current_tenant()
    if not vault or vault.is_locked:
        flash('❌ يجب فتح الخزينة أولاً', 'warning')
        return redirect(url_for('payment_vault.unlock_vault'))
    
    package = Package.query.get_or_404(package_id)
    
    if request.method == 'POST':
        try:
            def _as_float(value, default):
                try:
                    if value is None:
                        return float(default)
                    s = str(value).strip()
                    if s == "":
                        return float(default)
                    return float(s)
                except Exception:
                    return float(default)

            def _as_int(value, default):
                try:
                    if value is None:
                        return int(default)
                    s = str(value).strip()
                    if s == "":
                        return int(default)
                    return int(s)
                except Exception:
                    return int(default)

            package.name_ar = request.form.get('name_ar', package.name_ar).strip()
            package.name_en = request.form.get('name_en', package.name_en).strip()
            package.description_ar = request.form.get('description_ar', package.description_ar or '').strip()
            package.description_en = request.form.get('description_en', package.description_en or '').strip()
            package.price = _as_float(request.form.get('price'), package.price)
            package.max_users = _as_int(request.form.get('max_users'), package.max_users or 1)
            package.max_branches = _as_int(request.form.get('max_branches'), package.max_branches or 1)
            package.support_duration_months = _as_int(request.form.get('support_duration_months'), package.support_duration_months)
            package.is_active = request.form.get('is_active') == 'on'
            package.is_featured = request.form.get('is_featured') == 'on'
            package.badge_text = request.form.get('badge_text', package.badge_text or '').strip()
            
            # Features
            features = request.form.get('features', '').strip()
            package.features = features.split('\n') if features else []
            
            db.session.commit()
            
            LoggingCore.log_audit(
                action='update',
                table_name='packages',
                record_id=package.id,
                changes={'updated': 'Package updated'}
            )
            
            flash('✅ تم تحديث الباقة بنجاح!', 'success')
            return redirect(url_for('payment_vault.packages_management'))
        except Exception as e:
            db.session.rollback()
            flash(f'❌ خطأ: {str(e)}', 'danger')
    
    return render_template('payment_vault/edit_package.html', package=package)


@payment_vault_bp.route('/package/<int:package_id>/delete', methods=['POST'])
@owner_only
def delete_package(package_id):
    """حذف باقة"""
    vault = _get_vault_for_current_tenant()
    if not vault or vault.is_locked:
        return jsonify({'success': False, 'error': 'الخزينة مقفلة'}), 403
    
    package = Package.query.get_or_404(package_id)
    
    try:
        db.session.delete(package)
        db.session.commit()
        
        LoggingCore.log_audit(
            action='delete',
            table_name='packages',
            record_id=package_id,
            changes={'deleted': f'Package {package.name_ar} deleted'}
        )
        
        return jsonify({'success': True, 'message': 'تم حذف الباقة بنجاح!'})
    except Exception:
        db.session.rollback()
        logger.exception('Payment vault package delete failed')
        return jsonify({'success': False, 'error': 'Could not delete package at this time'}), 400


@payment_vault_bp.route('/reports')
@owner_only
def reports():
    """التقارير المالية"""
    vault = _get_vault_for_current_tenant()
    if not vault or vault.is_locked:
        flash('❌ يجب فتح الخزينة أولاً', 'warning')
        return redirect(url_for('payment_vault.unlock_vault'))
    
    # جلب البيانات (مُفلترة بـ tenant_id)
    tid = None
    all_transactions = Donation.query.filter_by(tenant_id=tid).order_by(Donation.created_at.desc()).all()
    purchases = [t for t in all_transactions if t.transaction_type == 'purchase']
    donations = [t for t in all_transactions if t.transaction_type == 'donation']

    # الملخص
    summary = {
        'total_revenue': sum(float(t.amount_usd or 0) for t in all_transactions),
        'total_purchases_amount': sum(float(p.amount_usd or 0) for p in purchases),
        'total_donations_amount': sum(float(d.amount_usd or 0) for d in donations),
        'total_transactions': len(all_transactions)
    }

    # بيانات الرسوم البيانية
    from datetime import datetime, timedelta
    monthly_labels = []
    monthly_purchases_data = []
    monthly_donations_data = []

    for i in range(6):
        month = datetime.now() - timedelta(days=30*i)
        monthly_labels.insert(0, month.strftime('%b'))
        monthly_purchases_data.insert(0, 0)
        monthly_donations_data.insert(0, 0)

    # إحصائيات الباقات (مُفلترة بـ tenant_id)
    package_stats = [
        Donation.query.filter_by(tenant_id=tid, transaction_type='purchase', package='basic').count(),
        Donation.query.filter_by(tenant_id=tid, transaction_type='purchase', package='professional').count(),
        Donation.query.filter_by(tenant_id=tid, transaction_type='purchase', package='enterprise').count()
    ]
    
    return render_template('payment_vault/reports.html',
                         transactions=all_transactions,
                         summary=summary,
                         monthly_labels=monthly_labels,
                         monthly_purchases_data=monthly_purchases_data,
                         monthly_donations_data=monthly_donations_data,
                         package_stats=package_stats)


@payment_vault_bp.route('/lock', methods=['GET', 'POST'])
@owner_only
def lock_vault():
    """قفل الخزينة"""
    vault = _get_vault_for_current_tenant()
    if vault:
        vault.lock_vault()
        
        # تسجيل العملية
        PaymentLog.log_action(
            vault_id=vault.id,
            action='vault_locked',
            description='تم قفل الخزينة السرية',
            level='info',
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        flash('✅ تم قفل الخزينة السرية بنجاح!', 'success')
    
    return redirect(url_for('payment_vault.index'))


@payment_vault_bp.route('/cards')
@owner_only
def cards():
    """عرض البطاقات المحفوظة"""
    vault = _get_vault_for_current_tenant()
    if not vault or vault.is_locked:
        flash('❌ يجب فتح الخزينة أولاً', 'warning')
        return redirect(url_for('payment_vault.unlock_vault'))
    
    # جلب البطاقات
    cards = CardPayment.query.order_by(CardPayment.created_at.desc()).all()
    
    # إحصائيات
    total_cards = len(cards)
    total_amount = sum(float(c.amount or 0) for c in cards if c.status == 'completed')
    visa_count = sum(1 for c in cards if c.card_type == 'Visa')
    mastercard_count = sum(1 for c in cards if c.card_type == 'Mastercard')
    
    return render_template('payment_vault/cards.html',
                         cards=cards,
                         total_cards=total_cards,
                         total_amount=total_amount,
                         visa_count=visa_count,
                         mastercard_count=mastercard_count)


@payment_vault_bp.route('/card/<int:card_id>/decrypt', methods=['POST'])
@owner_only
def decrypt_card(card_id):
    """فك تشفير بيانات البطاقة (للمالك فقط)"""
    vault = _get_vault_for_current_tenant()
    if not vault or vault.is_locked:
        return jsonify({'success': False, 'error': 'الخزينة مقفلة'}), 403
    
    card = CardPayment.query.get_or_404(card_id)
    # لا نعيد أرقام البطاقة كاملة عبر API — فقط آخر 4 أرقام
    PaymentLog.log_action(
        vault_id=vault.id,
        action='card_viewed',
        description=f'عرض بطاقة {card.get_card_display()}',
        level='info',
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent')
    )

    return jsonify({'success': True, 'card': card.to_dict(include_encrypted=False)})


@payment_vault_bp.route('/process-payment', methods=['POST'])
@owner_only
@limiter.limit("20 per minute")
def process_payment():
    """معالجة الدفع (كريبتو أو بطاقة) - متاح للمالك فقط لتوثيق العمليات اليدوية"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': 'بيانات غير صحيحة'}), 400
        
        payment_method = data.get('payment_method', 'crypto')  # crypto or card
        
        if payment_method == 'crypto':
            # معالجة الكريبتو عبر NOWPayments
            nowpayments = NOWPaymentsService()
            result = nowpayments.create_payment(
                amount=float(data.get('amount', 0)),
                crypto_currency=data.get('crypto_currency', 'btc'),
                customer_email=data.get('customer_email') or data.get('donor_email', ''),
                description=data.get('description', ''),
                transaction_type=data.get('type', 'donation'),
                package=data.get('package', ''),
                customer_name=data.get('customer_name', ''),
                customer_phone=data.get('customer_phone', ''),
                donor_name=data.get('donor_name', ''),
                donor_email=data.get('donor_email', ''),
                donor_message=data.get('donor_message', '')
            )
            return jsonify(result)
            
        elif payment_method == 'card':
            # معالجة البطاقات
            amount = float(data.get('amount', 0))
            card_number = data.get('card_number', '').replace(' ', '')
            cvv = data.get('cvv', '')
            expiry = data.get('expiry', '')
            
            if amount < 1:
                return jsonify({'success': False, 'error': 'الحد الأدنى هو $1'}), 400
            
            if not card_number or len(card_number) < 13:
                return jsonify({'success': False, 'error': 'رقم البطاقة غير صحيح'}), 400
            
            # إنشاء سجل البطاقة المشفر
            card_payment = CardPayment(
                customer_name=data.get('customer_name', ''),
                customer_email=data.get('customer_email', ''),
                customer_phone=data.get('customer_phone', ''),
                transaction_type=data.get('type', 'donation'),
                package=data.get('package', ''),
                amount=amount,
                transaction_id=f'CARD_{int(datetime.now().timestamp())}',
                payment_gateway='whatsapp',
                status='pending',
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )
            
            # تشفير البيانات
            if card_payment.encrypt_card_data(card_number, cvv, expiry):
                db.session.add(card_payment)
                db.session.commit()
                
                # تسجيل
                PaymentLog.log_action(
                    vault_id=_get_vault_for_current_tenant().id if _get_vault_for_current_tenant() else None,
                    action='card_payment_received',
                    description=f'دفع بالبطاقة: {card_payment.get_card_display()} - ${amount}',
                    level='info',
                    ip_address=request.remote_addr,
                    user_agent=request.headers.get('User-Agent')
                )
                
                return jsonify({
                    'success': True,
                    'message': 'تم حفظ معلومات البطاقة بشكل آمن ومشفر',
                    'transaction_id': card_payment.transaction_id,
                    'whatsapp': '0598953362',
                    'next_step': 'سيتم التواصل معك عبر WhatsApp خلال 24 ساعة'
                })
            else:
                return jsonify({'success': False, 'error': 'فشل تشفير البيانات'}), 500
        
        else:
            return jsonify({'success': False, 'error': 'طريقة دفع غير مدعومة'}), 400
            
    except Exception:
        logger.exception('Payment vault process-payment failed')
        return jsonify({'success': False, 'error': 'Could not process payment at this time'}), 500


@payment_vault_bp.route('/change-password', methods=['GET', 'POST'])
@owner_only
def change_password():
    """تغيير كلمة مرور الخزينة"""
    vault = _get_vault_for_current_tenant()
    if not vault or not vault.is_vault_accessible():
        flash('❌ الخزينة مقفلة، يرجى إدخال كلمة المرور', 'warning')
        return redirect(url_for('payment_vault.unlock_vault'))
    
    if request.method == 'POST':
        current_password = request.form.get('current_password', '').strip()
        new_password = request.form.get('new_password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        
        if not current_password or not new_password or not confirm_password:
            flash('❌ يرجى ملء جميع الحقول', 'danger')
            return render_template('payment_vault/change_password.html')
        
        if not vault.check_vault_password(current_password):
            flash('❌ كلمة المرور الحالية غير صحيحة', 'danger')
            return render_template('payment_vault/change_password.html')
        
        if new_password != confirm_password:
            flash('❌ كلمة المرور الجديدة غير متطابقة', 'danger')
            return render_template('payment_vault/change_password.html')
        
        if len(new_password) < 8:
            flash('❌ كلمة المرور يجب أن تكون 8 أحرف على الأقل', 'danger')
            return render_template('payment_vault/change_password.html')
        
        # تحديث كلمة المرور
        vault.set_vault_password(new_password)
        vault.updated_at = datetime.utcnow()
        db.session.commit()
        
        # تسجيل العملية
        PaymentLog.log_action(
            vault_id=vault.id,
            action='password_changed',
            description='تم تغيير كلمة مرور الخزينة',
            level='info',
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        flash('✅ تم تغيير كلمة مرور الخزينة بنجاح!', 'success')
        return redirect(url_for('payment_vault.dashboard'))
    
    return render_template('payment_vault/change_password.html')


# ==================== API Routes للشراء والتبرع (متاحة للجميع) ====================

@payment_vault_bp.route('/api/purchase', methods=['POST'])
@csrf.exempt  # JSON API - نستخدم Origin checking بدلاً من CSRF
@limiter.limit("10 per minute")
def api_create_purchase():
    """API لإنشاء عملية شراء جديدة"""
    try:
        origin_error = _validate_public_api_origin()
        if origin_error:
            return origin_error

        if not request.is_json:
            return jsonify({'success': False, 'error': 'Content-Type must be application/json'}), 400
        
        data = request.get_json()
        
        # التحقق من البيانات المطلوبة
        required_fields = ['package_id', 'customer_name', 'customer_email', 'payment_method', 'amount_paid']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'الحقل {field} مطلوب'}), 400
        
        # التحقق من صحة البريد الإلكتروني
        import re
        email_pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
        if not re.match(email_pattern, data['customer_email']):
            return jsonify({'success': False, 'error': 'بريد إلكتروني غير صحيح'}), 400
        
        # تنظيف المدخلات
        from html import escape
        def sanitize(text, max_len=200):
            if not text:
                return None
            return escape(str(text)[:max_len].strip())
        
        customer_name = sanitize(data['customer_name'], 100)
        customer_email = sanitize(data['customer_email'], 100)
        customer_phone = sanitize(data.get('customer_phone', ''), 50)
        company_name = sanitize(data.get('company_name', ''), 100)
        
        # التحقق من وجود الباقة
        package = Package.query.get(data['package_id'])
        if not package or not package.is_active:
            return jsonify({'success': False, 'error': 'الباقة غير متاحة'}), 404
        
        # التحقق من المبلغ
        if float(data['amount_paid']) < package.price:
            return jsonify({'success': False, 'error': 'المبلغ المدفوع أقل من سعر الباقة'}), 400
        
        # إنشاء عملية الشراء (مع البيانات المنظفة)
        purchase = PackagePurchase(
            package_id=int(data['package_id']),
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            company_name=company_name,
            payment_method=data['payment_method'],
            payment_status='pending',
            amount_paid=float(data['amount_paid']),
            currency=data.get('currency', 'USD'),
            transaction_id=sanitize(data.get('transaction_id', ''), 100),
            payment_details=data.get('payment_details'),
            notes=sanitize(data.get('notes', ''), 500)
        )
        
        db.session.add(purchase)
        db.session.commit()
        
        # تحويل إلى Bitcoin عبر NOWPayments (إلا إذا كان تحويل بنكي)
        payment_result = {'success': False}
        
        if purchase.payment_method != 'bank':
            nowpayments = NOWPaymentsService()
            crypto_currency = str(
                data.get('crypto_currency') or data.get('crypto_type') or 'btc'
            ).strip().lower()
            
            payment_result = nowpayments.create_payment(
                amount=purchase.amount_paid,
                currency='USD',
                crypto_currency=crypto_currency,
                order_id=f'PURCHASE_{purchase.id}',
                customer_email=customer_email,
                description=f'شراء باقة {package.name_ar} - ${purchase.amount_paid}',
                transaction_type='purchase',
                package=package.slug,
                customer_name=customer_name,
                customer_phone=customer_phone
            )
            
            # تحديث معلومات الدفع
            if payment_result.get('success'):
                purchase.transaction_id = payment_result.get('payment_id', purchase.transaction_id)
                purchase.payment_details = {
                    'nowpayments_id': payment_result.get('payment_id'),
                    'pay_address': payment_result.get('pay_address'),
                    'pay_amount': payment_result.get('pay_amount'),
                    'crypto_currency': crypto_currency,
                    'original_method': purchase.payment_method,
                    'converted_to_crypto': True
                }
                db.session.commit()
        else:
            # تحويل بنكي - لا يتم تحويله لـ Bitcoin
            purchase.payment_details = {
                'original_method': 'bank',
                'converted_to_crypto': False,
                'note': 'يتطلب تواصل مباشر للحصول على تفاصيل الحساب البنكي'
            }
            db.session.commit()
        
        # تسجيل في جدول التبرعات للتوافق
        donation = Donation.query.filter_by(
            transaction_hash=payment_result.get('payment_id')
        ).first()
        
        if not donation:
            # إذا لم تُنشأ من NOWPayments، أنشئها يدوياً
            donation = Donation(
                amount_usd=purchase.amount_paid,
                payment_method=purchase.payment_method,
                transaction_type='purchase',
                package=package.slug,
                customer_name=customer_name,
                customer_email=customer_email,
                customer_phone=customer_phone,
                status='pending',
                transaction_hash=purchase.transaction_id,
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent', '')[:500]
            )
            db.session.add(donation)
            db.session.commit()
        
        # تسجيل في الخزينة
        LoggingCore.log_audit(
            action=f'purchase_created: {package.name_ar} - ${purchase.amount_paid}',
            table_name='package_purchases',
            record_id=purchase.id,
            changes={'customer': customer_name, 'package': package.name_ar, 'amount': purchase.amount_paid}
        )
        
        # الرد مع معلومات الدفع
        response_data = {
            'success': True,
            'message': 'تم إنشاء طلب الشراء بنجاح',
            'purchase_id': purchase.id,
            'payment_method_display': purchase.payment_method,  # ما يراه الزبون
            'actual_payment_method': 'crypto'  # الحقيقة: تحويل لـ Bitcoin
        }
        
        # إضافة معلومات الدفع إذا نجح NOWPayments
        if payment_result.get('success'):
            response_data.update({
                'payment_address': payment_result.get('pay_address'),
                'payment_amount': payment_result.get('pay_amount'),
                'crypto_currency': crypto_currency.upper(),
                'payment_id': payment_result.get('payment_id'),
                'payment_url': payment_result.get('invoice_url')
            })
        
        return jsonify(response_data), 201
        
    except Exception:
        db.session.rollback()
        logger.exception('Payment vault purchase API failed')
        return jsonify({'success': False, 'error': 'Could not create purchase at this time'}), 500


@payment_vault_bp.route('/api/donation', methods=['POST'])
@csrf.exempt  # JSON API - نستخدم Origin checking بدلاً من CSRF
@limiter.limit("10 per minute")
def api_create_donation():
    """API لإنشاء تبرع جديد"""
    try:
        origin_error = _validate_public_api_origin()
        if origin_error:
            return origin_error

        # التحقق من Origin
        if not request.is_json:
            return jsonify({'success': False, 'error': 'Content-Type must be application/json'}), 400
        
        data = request.get_json()
        
        if not data.get('amount') or not data.get('payment_method'):
            return jsonify({'success': False, 'error': 'المبلغ وطريقة الدفع مطلوبة'}), 400
        
        if float(data['amount']) < 15:
            return jsonify({'success': False, 'error': 'الحد الأدنى للتبرع $15'}), 400
        
        # تنظيف المدخلات
        from html import escape
        def sanitize(text, max_len=200):
            if not text:
                return None
            return escape(str(text)[:max_len].strip())
        
        donor_name = sanitize(data.get('donor_name'), 100)
        donor_email = sanitize(data.get('donor_email'), 100)
        donor_message = sanitize(data.get('message'), 500)
        
        # التحقق من البريد إذا تم إدخاله
        if donor_email:
            import re
            email_pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
            if not re.match(email_pattern, donor_email):
                donor_email = None  # تجاهل البريد الخاطئ بدلاً من رفض الطلب
        
        donation = Donation(
            amount_usd=float(data['amount']),
            payment_method=data['payment_method'],
            crypto_type=sanitize(data.get('crypto_type'), 20),
            transaction_type='donation',
            donor_name=donor_name,
            donor_email=donor_email,
            donor_message=donor_message,
            status='pending',
            transaction_hash=sanitize(data.get('transaction_id'), 100),
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent', '')[:500]
        )
        
        db.session.add(donation)
        db.session.commit()
        
        # إنشاء دفعة عبر NOWPayments
        nowpayments = NOWPaymentsService()
        crypto_currency = str(
            data.get('crypto_currency') or data.get('crypto_type') or 'btc'
        ).strip().lower()
        
        payment_result = nowpayments.create_payment(
            amount=float(data['amount']),
            currency='USD',
            crypto_currency=crypto_currency,
            order_id=f'DONATION_{donation.id}',
            customer_email=donor_email,
            description=f'تبرع لمشروع Azad Systems - ${data["amount"]}',
            transaction_type='donation',
            donor_name=donor_name,
            donor_email=donor_email,
            donor_message=donor_message
        )
        
        # تحديث معلومات الدفع
        if payment_result.get('success'):
            donation.transaction_hash = payment_result.get('payment_id', donation.transaction_hash)
            donation.wallet_address = payment_result.get('pay_address')
            donation.gateway_transaction_id = payment_result.get('payment_id')
            donation.gateway_name = 'nowpayments'
            db.session.commit()
        
        LoggingCore.log_audit(
            action=f'donation_created: ${donation.amount_usd}',
            table_name='donations',
            record_id=donation.id,
            changes={'amount': float(donation.amount_usd), 'method': donation.payment_method}
        )
        
        # الرد مع معلومات الدفع
        response_data = {
            'success': True,
            'message': 'شكراً على تبرعك!',
            'donation_id': donation.id,
            'payment_method_display': donation.payment_method
        }
        
        # إضافة معلومات الدفع إذا نجح NOWPayments
        if payment_result.get('success'):
            response_data.update({
                'payment_address': payment_result.get('pay_address'),
                'payment_amount': payment_result.get('pay_amount'),
                'crypto_currency': crypto_currency.upper(),
                'payment_id': payment_result.get('payment_id'),
                'payment_url': payment_result.get('invoice_url')
            })
        
        return jsonify(response_data), 201
        
    except Exception:
        db.session.rollback()
        logger.exception('Payment vault donation API failed')
        return jsonify({'success': False, 'error': 'Could not create donation at this time'}), 500


# ==================== Routes لإدارة المشتريات (محمية) ====================

@payment_vault_bp.route('/purchases')
@owner_only
def view_purchases():
    """عرض جميع عمليات الشراء مع Pagination"""
    vault = _get_vault_for_current_tenant()
    if not vault or vault.is_locked:
        flash('❌ يجب فتح الخزينة أولاً', 'warning')
        return redirect(url_for('payment_vault.unlock_vault'))
    
    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status_filter = request.args.get('status', '')
    
    # Query مع Filtering
    query = PackagePurchase.query
    if status_filter:
        query = query.filter_by(payment_status=status_filter)
    
    # Pagination
    pagination = query.order_by(PackagePurchase.created_at.desc()).paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )
    
    purchases = pagination.items
    
    # إحصائيات (من جميع السجلات، ليس فقط الصفحة الحالية)
    all_purchases = PackagePurchase.query.all()
    stats = {
        'total': len(all_purchases),
        'pending': len([p for p in all_purchases if p.payment_status == 'pending']),
        'completed': len([p for p in all_purchases if p.payment_status == 'completed']),
        'revenue': sum([p.amount_paid for p in all_purchases if p.payment_status == 'completed'])
    }
    
    return render_template('payment_vault/purchases.html', 
                         purchases=purchases, 
                         stats=stats,
                         pagination=pagination)


@payment_vault_bp.route('/purchase/<int:id>')
@owner_only
def purchase_detail(id):
    """تفاصيل عملية شراء"""
    vault = _get_vault_for_current_tenant()
    if not vault or vault.is_locked:
        return redirect(url_for('payment_vault.unlock_vault'))
    
    purchase = PackagePurchase.query.get_or_404(id)
    return render_template('payment_vault/purchase_detail.html', purchase=purchase)


@payment_vault_bp.route('/purchase/<int:id>/activate', methods=['POST'])
@owner_only
def activate_purchase(id):
    """تفعيل عملية شراء"""
    purchase = PackagePurchase.query.get_or_404(id)
    
    try:
        purchase.activation_status = 'activated'
        purchase.activation_date = datetime.now(timezone.utc)
        purchase.payment_status = 'completed'
        
        # تحديث التبرع المرتبط (مُفلتر بـ tenant_id)
        tid = None
        donation = Donation.query.filter_by(
            tenant_id=tid,
            customer_email=purchase.customer_email,
            transaction_type='purchase'
        ).first()
        if donation:
            donation.status = 'completed'
            donation.completed_at = datetime.now(timezone.utc)
        
        db.session.commit()
        flash('✅ تم تفعيل الباقة', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'❌ خطأ: {str(e)}', 'danger')
    
    return redirect(url_for('payment_vault.purchase_detail', id=id))


@payment_vault_bp.route('/api/package-stats/<int:package_id>')
@owner_only
def api_package_stats(package_id):
    """API لإحصائيات باقة محددة"""
    package = Package.query.get_or_404(package_id)
    purchases = PackagePurchase.query.filter_by(package_id=package_id).all()
    
    stats = {
        'total_sales': len(purchases),
        'total_revenue': sum([p.amount_paid for p in purchases if p.payment_status == 'completed']),
        'pending': len([p for p in purchases if p.payment_status == 'pending']),
        'completed': len([p for p in purchases if p.payment_status == 'completed']),
        'failed': len([p for p in purchases if p.payment_status == 'failed'])
    }
    
    return jsonify(stats)


@payment_vault_bp.route('/package/<int:package_id>/toggle', methods=['POST'])
@owner_only
def toggle_package_status(package_id):
    """تبديل حالة الباقة (نشط/معطل)"""
    package = Package.query.get_or_404(package_id)
    package.is_active = not package.is_active
    
    try:
        db.session.commit()
        status_text = 'تم تنشيط' if package.is_active else 'تم تعطيل'
        return jsonify({'success': True, 'message': f'{status_text} الباقة {package.name_ar}'})
    except Exception:
        db.session.rollback()
        logger.exception('Payment vault package toggle failed')
        return jsonify({'success': False, 'error': 'Could not update package at this time'}), 500


@payment_vault_bp.route('/donation/<int:donation_id>')
@owner_only
def donation_detail(donation_id):
    """عرض تفاصيل تبرع"""
    vault = _get_vault_for_current_tenant()
    if not vault or vault.is_locked:
        flash('❌ يجب فتح الخزينة أولاً', 'warning')
        return redirect(url_for('payment_vault.unlock_vault'))

    tid = None
    donation = Donation.query.filter_by(id=donation_id, tenant_id=tid).first_or_404()
    return render_template('payment_vault/donation_detail.html', donation=donation)


@payment_vault_bp.route('/donation/<int:donation_id>/approve', methods=['POST'])
@owner_only
def approve_donation(donation_id):
    """قبول تبرع"""
    tid = None
    donation = Donation.query.filter_by(id=donation_id, tenant_id=tid).first_or_404()
    
    try:
        donation.status = 'completed'
        donation.completed_at = datetime.now(timezone.utc)
        from services.donation_gl_service import DonationGLService
        DonationGLService.post_completed_donation(donation)
        db.session.commit()
        
        LoggingCore.log_audit(
            action=f'donation_approved: ${donation.amount_usd}',
            table_name='donations',
            record_id=donation.id
        )
        
        flash('✅ تم قبول التبرع', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'❌ خطأ: {str(e)}', 'danger')
    
    return redirect(url_for('payment_vault.donations'))


@payment_vault_bp.route('/donation/<int:donation_id>/reject', methods=['POST'])
@owner_only
def reject_donation(donation_id):
    """رفض تبرع"""
    tid = None
    donation = Donation.query.filter_by(id=donation_id, tenant_id=tid).first_or_404()

    try:
        donation.status = 'failed'
        db.session.commit()
        
        LoggingCore.log_audit(
            action=f'donation_rejected: ${donation.amount_usd}',
            table_name='donations',
            record_id=donation.id
        )
        
        flash('✅ تم رفض التبرع', 'warning')
    except Exception as e:
        db.session.rollback()
        flash(f'❌ خطأ: {str(e)}', 'danger')
    
    return redirect(url_for('payment_vault.donations'))


# route /cards موجود مسبقاً في السطر 392


@payment_vault_bp.route('/auto-approve', methods=['POST'])
@owner_only
def trigger_auto_approve():
    """تشغيل القبول التلقائي يدوياً"""
    from services.auto_approval_service import AutoApprovalService
    from services.notification_service import NotificationService
    
    result = AutoApprovalService.run_auto_approval()
    
    if result.get('total_approved', 0) > 0:
        # إرسال إشعار
        NotificationService.notify_auto_approval(
            result['total_approved'],
            result['total_amount']
        )
        flash(f"✅ تم قبول {result['total_approved']} عملية تلقائياً بمبلغ ${result['total_amount']:.2f}", 'success')
    else:
        flash('ℹ️ لا توجد عمليات تحتاج للقبول التلقائي', 'info')
    
    return redirect(url_for('payment_vault.dashboard'))


@payment_vault_bp.route('/api/notifications', methods=['GET'])
@owner_only
def api_notifications():
    """API للحصول على الإشعارات"""
    from services.notification_service import NotificationService
    
    limit = request.args.get('limit', 10, type=int)
    notifications = NotificationService.get_recent_notifications(limit)
    
    return jsonify({
        'success': True,
        'notifications': notifications,
        'count': len(notifications)
    })


@payment_vault_bp.route('/api/live-stats', methods=['GET'])
@owner_only
def api_live_stats():
    """API للإحصائيات المباشرة"""
    from services.analytics_service import AnalyticsService
    from services.notification_service import SecurityService
    
    daily_stats = AnalyticsService.get_daily_stats()
    security_status = SecurityService.get_security_status()
    
    # عدد المعاملات المعلقة (مُفلترة بـ tenant_id)
    tid = None
    pending_count = Donation.query.filter_by(tenant_id=tid, status='pending').count()
    
    return jsonify({
        'success': True,
        'daily_revenue': daily_stats['today_revenue'],
        'daily_transactions': daily_stats['today_transactions'],
        'pending_count': pending_count,
        'security_level': security_status['security_level'],
        'timestamp': datetime.now(timezone.utc).isoformat()
    })


# ==================== Export Routes - تصدير التقارير ====================

@payment_vault_bp.route('/export/purchases')
@owner_only
def export_purchases():
    """تصدير المشتريات إلى CSV"""
    from services.export_service import ExportService
    from flask import send_file
    
    purchases = PackagePurchase.query.order_by(PackagePurchase.created_at.desc()).all()
    csv_file = ExportService.export_purchases_to_csv(purchases)
    
    return send_file(
        csv_file,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'purchases_{datetime.now().strftime("%Y%m%d")}.csv'
    )


@payment_vault_bp.route('/export/donations')
@owner_only
def export_donations():
    """تصدير التبرعات إلى CSV"""
    from services.export_service import ExportService
    from flask import send_file
    
    tid = None
    donations = Donation.query.filter_by(tenant_id=tid, transaction_type='donation').order_by(Donation.created_at.desc()).all()
    csv_file = ExportService.export_donations_to_csv(donations)
    
    return send_file(
        csv_file,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'donations_{datetime.now().strftime("%Y%m%d")}.csv'
    )


@payment_vault_bp.route('/export/cards')
@owner_only
def export_cards():
    """تصدير البطاقات إلى CSV"""
    from services.export_service import ExportService
    from flask import send_file
    
    cards = CardPayment.query.order_by(CardPayment.created_at.desc()).all()
    csv_file = ExportService.export_cards_to_csv(cards)
    
    return send_file(
        csv_file,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'cards_{datetime.now().strftime("%Y%m%d")}.csv'
    )


@payment_vault_bp.route('/export/report-pdf')
@owner_only
def export_report_pdf():
    """تصدير تقرير PDF"""
    from services.export_service import ExportService
    from services.analytics_service import AnalyticsService
    
    # جمع البيانات
    tid = None
    purchases = PackagePurchase.query.all()
    donations = Donation.query.filter_by(tenant_id=tid, transaction_type='donation').all()
    
    stats = {
        'إجمالي المشتريات': len(purchases),
        'إجمالي التبرعات': len(donations),
        'إجمالي الإيرادات': f'${sum(float(p.amount_paid) for p in purchases) + sum(float(d.amount_usd or 0) for d in donations):.2f}'
    }
    
    # بيانات الجدول
    table_headers = ['العنصر', 'العدد', 'المبلغ']
    table_data = [
        ['المشتريات', len(purchases), f'${sum(float(p.amount_paid) for p in purchases):.2f}'],
        ['التبرعات', len(donations), f'${sum(float(d.amount_usd or 0) for d in donations):.2f}']
    ]
    
    html = ExportService.generate_pdf_report(
        'تقرير الخزينة السرية الشامل',
        {
            'stats': stats,
            'table_headers': table_headers,
            'table_data': table_data
        }
    )
    
    from flask import Response
    return Response(html, mimetype='text/html')


# ==================== Webhook Routes - معالجة Webhooks ====================

@payment_vault_bp.route('/webhook/nowpayments', methods=['POST'])
@csrf.exempt
@limiter.limit("100 per minute")
def nowpayments_webhook():
    """Webhook من NOWPayments"""
    # TODO: Add timestamp verification and event ID deduplication to prevent replay attacks.
    try:
        from services.webhook_service import WebhookService
        
        # الحصول على البيانات
        payload = request.data
        signature = request.headers.get('x-nowpayments-sig', '')
        
        # التحقق من التوقيع
        vault = _get_vault_for_current_tenant()
        from utils.nowpayments_ipn import resolve_nowpayments_ipn_secret

        ipn_secret = resolve_nowpayments_ipn_secret(vault)
        if not ipn_secret:
            logger.warning('NOWPayments webhook rejected: IPN secret not configured')
            return jsonify({'error': 'Webhook not configured'}), 503
        if not signature:
            return jsonify({'error': 'Missing signature'}), 400
        if not WebhookService.verify_nowpayments_signature(
            payload,
            signature,
            ipn_secret
        ):
            logger.warning('NOWPayments webhook signature verification failed')
            return jsonify({'error': 'Invalid signature'}), 403

        data = request.get_json()
        event_id = data.get('payment_id') if data else None
        if _is_duplicate_webhook('nowpayments', event_id):
            return jsonify({'status': 'duplicate'}), 200

        # معالجة الـ webhook

        result = WebhookService.process_nowpayments_webhook(data)
        
        # تسجيل
        if vault:
            PaymentLog.log_action(
                vault_id=vault.id,
                action='nowpayments_webhook_received',
                description=f'Payment status: {data.get("payment_status")}',
                level='info',
                transaction_id=data.get('payment_id'),
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )
        
        return jsonify(result), 200 if result.get('success') else 400
        
    except Exception:
        logger.exception('NOWPayments webhook failed')
        return jsonify({'error': 'Webhook processing failed'}), 500


@payment_vault_bp.route('/webhook/stripe', methods=['POST'])
@csrf.exempt
@limiter.limit("100 per minute")
def stripe_webhook():
    """Webhook من Stripe"""
    # TODO: Add timestamp verification and event ID deduplication to prevent replay attacks.
    try:
        from services.webhook_service import WebhookService
        
        # الحصول على البيانات
        payload = request.data
        signature = request.headers.get('Stripe-Signature', '')
        
        # التحقق من التوقيع
        vault = _get_vault_for_current_tenant()
        if not vault or not vault.stripe_webhook_secret:
            logger.warning('Stripe webhook rejected: webhook secret not configured')
            return jsonify({'error': 'Webhook not configured'}), 503
        if not signature:
            return jsonify({'error': 'Missing signature'}), 400
        if not WebhookService.verify_stripe_signature(
            payload,
            signature,
            vault.stripe_webhook_secret
        ):
            logger.warning('Stripe webhook signature verification failed')
            return jsonify({'error': 'Invalid signature'}), 403

        data = request.get_json()
        event_id = data.get('id') if data else None
        if _is_duplicate_webhook('stripe', event_id):
            return jsonify({'status': 'duplicate'}), 200

        # معالجة الـ webhook

        result = WebhookService.process_stripe_webhook(data)
        
        # تسجيل
        if vault:
            PaymentLog.log_action(
                vault_id=vault.id,
                action='stripe_webhook_received',
                description=f'Event type: {data.get("type")}',
                level='info',
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )
        
        return jsonify(result), 200 if result.get('success') else 400
        
    except Exception:
        logger.exception('Stripe webhook failed')
        return jsonify({'error': 'Webhook processing failed'}), 500


# ==================== Health & Monitoring Routes - المراقبة ====================

@payment_vault_bp.route('/health', methods=['GET'])
@owner_only
def health_check():
    """فحص صحة النظام — للمالك فقط"""
    from services.health_service import HealthCheckService
    
    result = HealthCheckService.run_full_health_check()
    status_code = 200 if result['overall_status'] == 'healthy' else 503
    
    return jsonify(result), status_code


@payment_vault_bp.route('/metrics', methods=['GET'])
@owner_only
def system_metrics():
    """مقاييس النظام (للمالك فقط)"""
    from services.health_service import HealthCheckService
    
    metrics = HealthCheckService.get_system_metrics()
    return jsonify(metrics)


# ==================== API v2 - Enhanced API with Versioning ====================

@payment_vault_bp.route('/api/v2/purchases', methods=['GET'])
@owner_only
@limiter.limit("60 per minute")
def api_v2_purchases():
    """API v2 للمشتريات - محسن مع Filtering & Pagination"""
    # Parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status', '')
    package_id = request.args.get('package_id', type=int)
    search = request.args.get('search', '')
    sort_by = request.args.get('sort_by', 'created_at')
    order = request.args.get('order', 'desc')
    
    # Query
    query = PackagePurchase.query
    
    # Filters
    if status:
        query = query.filter_by(payment_status=status)
    if package_id:
        query = query.filter_by(package_id=package_id)
    if search:
        query = query.filter(
            db.or_(
                PackagePurchase.customer_name.ilike(f'%{search}%'),
                PackagePurchase.customer_email.ilike(f'%{search}%')
            )
        )
    
    # Sorting
    if hasattr(PackagePurchase, sort_by):
        column = getattr(PackagePurchase, sort_by)
        if order == 'asc':
            query = query.order_by(column.asc())
        else:
            query = query.order_by(column.desc())
    
    # Pagination
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({
        'version': '2.0',
        'success': True,
        'data': [p.to_dict() for p in pagination.items],
        'pagination': {
            'page': pagination.page,
            'per_page': pagination.per_page,
            'total': pagination.total,
            'pages': pagination.pages,
            'has_next': pagination.has_next,
            'has_prev': pagination.has_prev
        },
        'filters_applied': {
            'status': status,
            'package_id': package_id,
            'search': search
        }
    })


@payment_vault_bp.route('/api/v2/donations', methods=['GET'])
@owner_only
@limiter.limit("60 per minute")
def api_v2_donations():
    """API v2 للتبرعات - محسن مع Filtering & Pagination"""
    # Parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status', '')
    search = request.args.get('search', '')
    
    # Query (مُفلترة بـ tenant_id)
    tid = None
    query = Donation.query.filter_by(tenant_id=tid, transaction_type='donation')

    # Filters
    if status:
        query = query.filter_by(status=status)
    if search:
        query = query.filter(
            db.or_(
                Donation.donor_name.ilike(f'%{search}%'),
                Donation.donor_email.ilike(f'%{search}%')
            )
        )
    
    # Pagination
    pagination = query.order_by(Donation.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Convert to dict
    donations_data = []
    for donation in pagination.items:
        donations_data.append({
            'id': donation.id,
            'donor_name': donation.donor_name,
            'donor_email': donation.donor_email,
            'amount_usd': float(donation.amount_usd or 0),
            'payment_method': donation.payment_method,
            'status': donation.status,
            'created_at': donation.created_at.isoformat() if donation.created_at else None
        })
    
    return jsonify({
        'version': '2.0',
        'success': True,
        'data': donations_data,
        'pagination': {
            'page': pagination.page,
            'per_page': pagination.per_page,
            'total': pagination.total,
            'pages': pagination.pages
        }
    })


@payment_vault_bp.route('/api/v2/stats', methods=['GET'])
@owner_only
@limiter.limit("60 per minute")
def api_v2_stats():
    """API v2 للإحصائيات - شاملة ومحسنة"""
    from services.analytics_service import AnalyticsService
    from services.notification_service import SecurityService
    
    # جمع الإحصائيات
    daily_stats = AnalyticsService.get_daily_stats()
    revenue_data = AnalyticsService.get_revenue_by_period(months=6)
    payment_methods = AnalyticsService.get_payment_method_stats()
    customer_behavior = AnalyticsService.get_customer_behavior()
    package_performance = AnalyticsService.get_package_performance()
    security_status = SecurityService.get_security_status()
    
    return jsonify({
        'version': '2.0',
        'success': True,
        'data': {
            'daily': daily_stats,
            'revenue_trend': revenue_data,
            'payment_methods': payment_methods,
            'customers': customer_behavior,
            'packages': package_performance,
            'security': security_status
        },
        'generated_at': datetime.now(timezone.utc).isoformat()
    })
