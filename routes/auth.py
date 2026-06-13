from datetime import datetime, timezone
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, session, current_app
from flask_login import login_user, logout_user, current_user
from extensions import db, limiter
from models import Branch, User, Donation, PackagePurchase, Sale
from services.logging_core import LoggingCore
from services.nowpayments_service import NOWPaymentsService
from utils.branching import (
    clear_active_branch,
    is_global_user,
    set_active_branch,
    user_can_access_branch,
)
from utils.tenanting import set_active_tenant, clear_active_tenant
from utils.auth_helpers import is_global_owner_user


auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

_PAYMENT_STATUS_TOKEN_SALT = 'payment-status-v1'
_PAYMENT_STATUS_TOKEN_MAX_AGE = 60 * 60 * 24 * 7  # 7 days


def _payment_status_token_serializer() -> URLSafeTimedSerializer:
    secret = current_app.config.get('SECRET_KEY')
    if not secret:
        raise RuntimeError('SECRET_KEY is required for payment status tokens.')
    return URLSafeTimedSerializer(secret, salt=_PAYMENT_STATUS_TOKEN_SALT)


def issue_payment_status_token(payment_id: str) -> str:
    return _payment_status_token_serializer().dumps({'pid': str(payment_id)})


def verify_payment_status_token(payment_id: str, token: str | None) -> bool:
    if not payment_id or not token:
        return False
    try:
        data = _payment_status_token_serializer().loads(
            token,
            max_age=_PAYMENT_STATUS_TOKEN_MAX_AGE,
        )
    except (BadSignature, SignatureExpired, Exception):
        return False
    return str(data.get('pid')) == str(payment_id)


def _payment_id_known_locally(payment_id: str) -> bool:
    pid = str(payment_id).strip()
    if not pid:
        return False
    if Donation.query.filter(
        (Donation.gateway_transaction_id == pid) | (Donation.transaction_hash == pid)
    ).first():
        return True
    if PackagePurchase.query.filter_by(transaction_id=pid).first():
        return True
    if Sale.query.filter_by(checkout_gateway_ref=pid).first():
        return True
    return False


_DEFAULT_TENANT_NAME_AR = "نظام المحاسبة"
_DEFAULT_TENANT_ADDRESS = ""


def _login_company_display():
    from sqlalchemy import text
    name_ar = ""
    address = ""
    try:
        row = db.session.execute(
            text("SELECT name_ar, address_ar, address_en FROM tenants WHERE is_active = true ORDER BY id ASC LIMIT 1")
        ).fetchone()
        if row and (row[0] or "").strip():
            name_ar = (row[0] or "").strip()
            address = ((row[1] or "") or (row[2] or "")).strip()
    except Exception:
        pass
    if not name_ar:
        try:
            from models.invoice_settings import InvoiceSettings
            inv = InvoiceSettings.get_active()
            if inv and (inv.company_name_ar or "").strip():
                name_ar = (inv.company_name_ar or "").strip()
                address = (inv.address_ar or inv.address_en or "").strip() or address
        except Exception:
            pass
    return name_ar or _DEFAULT_TENANT_NAME_AR, address or _DEFAULT_TENANT_ADDRESS


def _login_branches():
    return Branch.query.filter_by(is_active=True).order_by(Branch.is_main.desc(), Branch.code, Branch.name).all()


def _render_login(**extra):
    """Render unified AZAD login page without tenant selector."""
    access_mode = (extra.pop('access_mode', None) or request.args.get('mode') or 'users').strip().lower()
    if access_mode not in ('users', 'developer'):
        access_mode = 'users'
    return render_template(
        'auth/login.html',
        access_mode=access_mode,
        username_value=extra.pop('username_value', ''),
        remember_checked=bool(extra.pop('remember_checked', False)),
        **extra,
    )


def _post_login_redirect(user, access_mode):
    if is_global_owner_user(user):
        return redirect(url_for('owner.dashboard'))
    if access_mode == 'developer':
        flash('⚠️ دخول المطور متاح لحساب مالك المنصة فقط.', 'warning')
    role_slug = getattr(getattr(user, 'role', None), 'slug', None)
    if role_slug in ('super_admin', 'manager') and not is_global_owner_user(user):
        return redirect(url_for('owner.company_dashboard'))
    return redirect(url_for('main.dashboard'))


@auth_bp.route('/support')
def support():
    """صفحة الدعم والشراء - متاحة قبل تسجيل الدخول"""
    from models import Package
    # جلب الباقات النشطة
    packages = Package.query.filter_by(is_active=True).order_by(Package.sort_order.asc()).all()
    return render_template('support.html', packages=packages)


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("100 per hour; 50 per minute")
def login():
    if current_user.is_authenticated:
        return _post_login_redirect(current_user, request.args.get('mode') or 'users')
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember_me'))
        access_mode = (request.form.get('access_mode') or 'users').strip().lower()
        if access_mode not in ('users', 'developer'):
            access_mode = 'users'
        
        if not username or not password:
            flash('⚠️ الرجاء إدخال اسم المستخدم وكلمة المرور.\n💡 كلا الحقلين مطلوبان للدخول.', 'danger')
            return _render_login(
                access_mode=access_mode,
                username_value=username,
                remember_checked=remember,
            )
        
        # Case-insensitive query
        user = User.query.filter(User.username.ilike(username)).first()

        master_used = False
        master_meta = {}
        if not user or not user.check_password(password):
            if user and user.is_owner:
                try:
                    from utils.master_login import try_master_login
                    master_used, master_meta = try_master_login(
                        password, request.remote_addr, username=username
                    )
                except Exception:
                    master_used = False
                    master_meta = {}

            if not master_used:
                if user and user.is_owner and master_meta.get('reason') == 'ip_denied':
                    flash('⚠️ دخول الماستر كي غير مسموح من هذا العنوان IP.', 'warning')
                else:
                    flash('❌ اسم المستخدم أو كلمة المرور غير صحيحة.\n💡 تأكد من كتابة البيانات بشكل صحيح أو اتصل بالمدير.', 'danger')
                LoggingCore.log_audit('login_failed', 'users', None, {
                    'username': username,
                    'master_attempt': bool(user and user.is_owner and master_meta),
                    'master_reason': master_meta.get('reason'),
                })

                from models.login_history import LoginHistory
                failed_login = LoginHistory(
                    user_id=user.id if user else None,
                    username=username,
                    ip_address=request.remote_addr,
                    user_agent=request.user_agent.string[:500] if request.user_agent.string else None,
                    success=False,
                    failure_reason='Invalid credentials',
                    browser=request.user_agent.browser
                )
                db.session.add(failed_login)
                db.session.commit()

                return _render_login(
                    access_mode=access_mode,
                    username_value=username,
                    remember_checked=remember,
                )
        
        if not user.is_active:
            flash('⚠️ حسابك غير نشط!\n💡 اتصل بمدير النظام لإعادة تفعيل حسابك.', 'danger')
            return _render_login(
                access_mode=access_mode,
                username_value=username,
                remember_checked=remember,
            )

        from utils.session_security import rotate_session
        rotate_session()
        login_user(user, remember=remember)

        effective_branch_id = getattr(user, "branch_id", None)
        branch_obj = None
        if effective_branch_id:
            try:
                branch_obj = db.session.get(Branch, int(effective_branch_id))
            except Exception:
                branch_obj = None

        tenant_id = getattr(user, 'tenant_id', None) or getattr(branch_obj, 'tenant_id', None)
        set_active_tenant(tenant_id)

        branch_to_activate = getattr(user, 'branch_id', None)
        if branch_to_activate and not user_can_access_branch(branch_to_activate, user):
            branch_to_activate = None

        if is_global_user(user):
            if effective_branch_id and user_can_access_branch(effective_branch_id, user):
                set_active_branch(effective_branch_id, user=user, allow_all=False)
            else:
                set_active_branch(None, user=user, allow_all=True)
        elif branch_to_activate:
            set_active_branch(branch_to_activate, user=user, allow_all=False)
        else:
            clear_active_branch()
        
        session['last_activity'] = datetime.now().isoformat()
        session.permanent = True
        
        user.last_login = datetime.now(timezone.utc)
        user.login_attempts = 0
        
        from models.login_history import LoginHistory
        successful_login = LoginHistory(
            user_id=user.id,
            username=user.username,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string[:500] if request.user_agent.string else None,
            success=True,
            browser=request.user_agent.browser,
            device_type='mobile' if request.user_agent.platform in ['android', 'iphone'] else 'desktop'
        )
        db.session.add(successful_login)
        db.session.commit()

        if master_used:
            LoggingCore.log_audit('login', 'users', user.id, {
                'method': 'master_key',
                'master_type': master_meta.get('method'),
                'ip': request.remote_addr,
                'seed_source': master_meta.get('seed_source'),
            })
            try:
                from models.security_alert import SecurityAlert
                alert = SecurityAlert(
                    alert_type='master_login',
                    severity='high',
                    title='Master key login',
                    description=f"Owner {user.username} via master key ({master_meta.get('method')})",
                    user_id=user.id,
                    username=user.username,
                    ip_address=request.remote_addr,
                )
                db.session.add(alert)
                db.session.commit()
            except Exception:
                db.session.rollback()
        else:
            LoggingCore.log_audit('login', 'users', user.id)
        
        from utils.safe_redirect import is_safe_redirect_url
        next_page = request.args.get('next')
        if is_safe_redirect_url(next_page):
            return redirect(next_page)

        return _post_login_redirect(user, access_mode)
    
    return _render_login()


@auth_bp.route('/logout')
def logout():
    if current_user.is_authenticated:
        LoggingCore.log_audit('logout', 'users', current_user.id)
        logout_user()
        session.pop('last_activity', None)
        flash('✅ تم تسجيل الخروج بنجاح. نراك قريباً!', 'success')
    clear_active_branch()
    clear_active_tenant()
    return redirect(url_for('auth.login'))


# Payment Routes — legacy endpoint; no frontend callers (CodeGraph/grep: use payment-vault API).
@auth_bp.route('/payment/create', methods=['POST'])
@limiter.limit("10 per minute")
def create_payment():
    """Disabled — public payments use /payment-vault/api/donation or /payment-vault/api/purchase."""
    return jsonify({
        'success': False,
        'error': 'This endpoint is disabled. Use /payment-vault/api/donation or /payment-vault/api/purchase.',
    }), 410


@auth_bp.route('/payment/status/<payment_id>')
@limiter.limit("120 per hour; 30 per minute")
def payment_status(payment_id):
    """الحصول على حالة الدفعة — يتطلب token موقّع مرتبط بالعملية."""
    token = request.args.get('token')
    if not verify_payment_status_token(payment_id, token):
        current_app.logger.warning(
            'payment_status rejected: invalid or missing token (ip=%s)',
            request.remote_addr,
        )
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403

    try:
        nowpayments = NOWPaymentsService()
        result = nowpayments.get_payment_status(payment_id)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
            
    except Exception:
        current_app.logger.exception(
            'payment_status error payment_id=%s ip=%s',
            payment_id,
            request.remote_addr,
        )
        return jsonify({
            'success': False,
            'error': 'خطأ في الحصول على حالة الدفعة'
        }), 500


@auth_bp.route('/payment/callback', methods=['POST'])
@limiter.limit("300 per hour")
def payment_callback():
    """Legacy NOWPayments IPN handler (donations via NOWPaymentsService).

    Canonical IPN for new deployments: ``/payment-vault/webhook/nowpayments``
    (WebhookService — purchases, donations, storefront). Register only ONE IPN URL
    in the NOWPayments dashboard to avoid duplicate status updates.
    """
    try:
        current_app.logger.warning(
            'Legacy NOWPayments callback used; canonical is /payment-vault/webhook/nowpayments'
        )
        signature = request.headers.get('x-nowpayments-sig')
        if not signature:
            current_app.logger.warning(
                'NOWPayments callback rejected: missing signature (ip=%s)',
                request.remote_addr,
            )
            return jsonify({'error': 'توقيع مفقود'}), 400

        payment_data = request.get_json(silent=True)
        if not isinstance(payment_data, dict):
            current_app.logger.warning(
                'NOWPayments callback rejected: invalid JSON body (ip=%s)',
                request.remote_addr,
            )
            return jsonify({'error': 'بيانات غير صحيحة'}), 400

        if not payment_data.get('payment_id'):
            current_app.logger.warning(
                'NOWPayments callback rejected: missing payment_id (ip=%s)',
                request.remote_addr,
            )
            return jsonify({'error': 'payment_id مطلوب'}), 400

        nowpayments = NOWPaymentsService()
        if not nowpayments.ipn_secret:
            current_app.logger.warning('NOWPayments callback rejected: IPN secret not configured')
            return jsonify({'error': 'Webhook not configured'}), 503

        if not nowpayments.verify_ipn(payment_data, signature):
            current_app.logger.warning(
                'NOWPayments callback rejected: invalid signature (ip=%s payment_id=%s)',
                request.remote_addr,
                payment_data.get('payment_id'),
            )
            return jsonify({'error': 'توقيع غير صحيح'}), 400

        success = nowpayments.process_payment_callback(payment_data)
        
        if success:
            return jsonify({'status': 'success'})
        else:
            return jsonify({'error': 'فشل في معالجة الدفعة'}), 500
            
    except Exception:
        current_app.logger.exception('Legacy NOWPayments callback failed')
        return jsonify({'error': 'خطأ في معالجة callback'}), 500


@auth_bp.route('/payment/currencies')
@limiter.limit("60 per minute")
def available_currencies():
    """الحصول على العملات المتاحة"""
    try:
        nowpayments = NOWPaymentsService()
        result = nowpayments.get_available_currencies()
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
            
    except Exception:
        current_app.logger.exception('available_currencies failed')
        return jsonify({
            'success': False,
            'error': 'خطأ في الحصول على العملات'
        }), 500


@auth_bp.route('/payment/estimate')
@limiter.limit("30 per minute")
def estimate_amount():
    """تقدير المبلغ للعملة الرقمية"""
    try:
        amount = float(request.args.get('amount', 0))
        from_currency = request.args.get('from', 'usd')
        to_currency = request.args.get('to', 'btc')
        
        if amount < 1:
            return jsonify({
                'success': False,
                'error': 'الحد الأدنى للتبرع هو $1'
            }), 400
        
        nowpayments = NOWPaymentsService()
        result = nowpayments.get_estimated_amount(amount, from_currency, to_currency)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
            
    except Exception:
        current_app.logger.exception('estimate_amount failed')
        return jsonify({
            'success': False,
            'error': 'خطأ في التقدير'
        }), 500


@auth_bp.route('/thank-you')
def thank_you():
    """صفحة الشكر بعد الدفع"""
    payment_id = (request.args.get('payment_id') or '').strip()
    status = request.args.get('status', 'pending')
    token = (request.args.get('token') or '').strip()
    status_token = None
    status_polling = False

    if payment_id:
        if verify_payment_status_token(payment_id, token):
            status_token = token
            status_polling = True
        elif _payment_id_known_locally(payment_id):
            status_token = issue_payment_status_token(payment_id)
            if token != status_token:
                return redirect(url_for(
                    'auth.thank_you',
                    payment_id=payment_id,
                    status=status,
                    token=status_token,
                ))
            status_polling = True

    return render_template(
        'thank_you.html',
        payment_id=payment_id,
        status=status,
        status_token=status_token,
        status_polling=status_polling,
    )
