from datetime import datetime, timezone
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    request,
    jsonify,
    session,
    current_app,
)
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
from utils.db_safety import atomic_transaction
from utils.auth_helpers import is_global_owner_user, user_may_have_null_tenant

import ipaddress

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

_PAYMENT_STATUS_TOKEN_SALT = "payment-status-v1"
_PAYMENT_STATUS_TOKEN_MAX_AGE = 60 * 60 * 24 * 7  # 7 days


def _payment_status_token_serializer() -> URLSafeTimedSerializer:
    secret = current_app.config.get("SECRET_KEY")
    if not secret:
        raise RuntimeError("SECRET_KEY is required for payment status tokens.")
    return URLSafeTimedSerializer(secret, salt=_PAYMENT_STATUS_TOKEN_SALT)


def issue_payment_status_token(payment_id: str) -> str:
    return _payment_status_token_serializer().dumps({"pid": str(payment_id)})


def verify_payment_status_token(payment_id: str, token: str | None) -> bool:
    if not payment_id or not token:
        return False
    try:
        data = _payment_status_token_serializer().loads(
            token,
            max_age=_PAYMENT_STATUS_TOKEN_MAX_AGE,
        )
    except (BadSignature, SignatureExpired):
        return False
    return str(data.get("pid")) == str(payment_id)


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
    name_ar = ""
    address = ""
    try:
        from models.tenant import Tenant

        tenant = (
            Tenant.query.filter_by(is_active=True).order_by(Tenant.id.asc()).first()
        )
        if tenant and (tenant.name_ar or "").strip():
            name_ar = (tenant.name_ar or "").strip()
            address = ((tenant.address_ar or "") or (tenant.address_en or "")).strip()
    except Exception:
        current_app.logger.exception(
            "Failed to load tenant display info for login page"
        )
    if not name_ar:
        try:
            from models.invoice_settings import InvoiceSettings

            inv = InvoiceSettings.get_active()
            if inv and (inv.company_name_ar or "").strip():
                name_ar = (inv.company_name_ar or "").strip()
                address = (inv.address_ar or inv.address_en or "").strip() or address
        except Exception:
            current_app.logger.exception(
                "Failed to load invoice settings for login page display"
            )
    return name_ar or _DEFAULT_TENANT_NAME_AR, address or _DEFAULT_TENANT_ADDRESS


def _login_branches():
    return (
        Branch.query.filter_by(is_active=True)
        .order_by(Branch.is_main.desc(), Branch.code, Branch.name)
        .all()
    )


def _render_login(**extra):
    """Render unified AZAD login page without tenant selector."""
    access_mode = (
        (extra.pop("access_mode", None) or request.args.get("mode") or "users")
        .strip()
        .lower()
    )
    if access_mode not in ("users", "developer"):
        access_mode = "users"
    return render_template(
        "auth/login.html",
        access_mode=access_mode,
        username_value=extra.pop("username_value", ""),
        remember_checked=bool(extra.pop("remember_checked", False)),
        **extra,
    )


def _post_login_redirect(user, access_mode):
    if is_global_owner_user(user):
        return redirect(url_for("owner.dashboard"))
    if access_mode == "developer":
        flash("⚠️ دخول المطور متاح لحساب مالك المنصة فقط.", "warning")
    role_slug = getattr(getattr(user, "role", None), "slug", None)
    if role_slug in ("super_admin", "manager") and not is_global_owner_user(user):
        return redirect(url_for("owner.company_dashboard"))
    return redirect(url_for("main.dashboard"))


def _validate_credentials(username, password):
    """Verify username/password. Return (user, master_used, master_meta) or (None, False, {})."""
    user = User.query.filter(User.username.ilike(username)).first()
    if not user or not user.check_password(password):
        master_used = False
        master_meta = {}
        if user and user.is_owner:
            if not current_app.config.get("MASTER_LOGIN_ENABLED"):
                master_used = False
                master_meta = {"reason": "disabled"}
            else:
                try:
                    from utils.master_login import try_master_login

                    master_used, master_meta = try_master_login(
                        password, request.remote_addr, username=username
                    )
                except Exception:
                    master_used = False
                    master_meta = {}
        return user, master_used, master_meta
    return user, False, {}


def _resolve_effective_tenant(user, branch_obj):
    """Determine effective tenant for user. Returns tenant_id or None."""
    user_tenant_id = getattr(user, "tenant_id", None)
    if user_tenant_id is not None:
        return user_tenant_id
    if getattr(user, "is_owner", False) and branch_obj:
        return getattr(branch_obj, "tenant_id", None)
    return None


def _validate_branch_tenant_consistency(user, branch_obj: "Branch | None"):
    """Ensure branch belongs to user's tenant. Returns True if consistent or no validation needed."""
    if getattr(user, "tenant_id", None) is None or not branch_obj:
        return True
    return branch_obj.tenant_id == user.tenant_id


def _log_failed_login(username, user, master_attempt, master_reason):
    """Write LoginHistory + AuditLog for failed login attempt."""
    LoggingCore.log_audit(
        "login_failed",
        "users",
        None,
        {
            "username": username,
            "master_attempt": master_attempt,
            "master_reason": master_reason,
        },
    )
    from models.login_history import LoginHistory

    failed_login = LoginHistory(
        user_id=user.id if user else None,
        username=username,
        ip_address=request.remote_addr,
        user_agent=(
            request.user_agent.string[:500] if request.user_agent.string else None
        ),
        success=False,
        failure_reason="Invalid credentials",
        browser=request.user_agent.browser,
    )
    with atomic_transaction("log_failed_login"):
        db.session.add(failed_login)


def _perform_login(
    user,
    remember,
    effective_tenant_id,
    branch_to_activate,
    access_mode,
    master_used,
    master_meta,
):
    """Set session, log success, write history, and redirect."""
    from utils.session_security import rotate_session

    rotate_session()
    login_user(user, remember=remember)
    set_active_tenant(effective_tenant_id, user=user)
    if is_global_user(user):
        effective_branch_id = getattr(user, "branch_id", None)
        if effective_branch_id and user_can_access_branch(effective_branch_id, user):
            set_active_branch(effective_branch_id, user=user, allow_all=False)
        else:
            set_active_branch(None, user=user, allow_all=True)
    elif branch_to_activate:
        set_active_branch(branch_to_activate, user=user, allow_all=False)
    else:
        clear_active_branch()
    session["last_activity"] = datetime.now().isoformat()
    session.permanent = True
    user.last_login = datetime.now(timezone.utc)
    user.login_attempts = 0
    from models.login_history import LoginHistory

    successful_login = LoginHistory(
        user_id=user.id,
        username=user.username,
        ip_address=request.remote_addr,
        user_agent=(
            request.user_agent.string[:500] if request.user_agent.string else None
        ),
        success=True,
        browser=request.user_agent.browser,
        device_type=(
            "mobile"
            if request.user_agent.platform in ["android", "iphone"]
            else "desktop"
        ),
    )
    with atomic_transaction("perform_login"):
        db.session.add(successful_login)
    if master_used:
        LoggingCore.log_audit(
            "login",
            "users",
            user.id,
            {
                "method": "master_key",
                "master_type": master_meta.get("method"),
                "ip": request.remote_addr,
                "seed_source": master_meta.get("seed_source"),
            },
        )
        try:
            from models.security_alert import SecurityAlert

            alert = SecurityAlert(
                alert_type="master_login",
                severity="high",
                title="Master key login",
                description=f"Owner {user.username} via master key ({master_meta.get('method')})",
                user_id=user.id,
                username=user.username,
                ip_address=request.remote_addr,
            )
            with atomic_transaction("master_login_alert"):
                db.session.add(alert)
        except Exception as exc:
            current_app.logger.error(
                "CRITICAL: failed to record master key login security alert "
                "for user %s (%s): %s",
                user.id,
                user.username,
                exc,
            )
    else:
        LoggingCore.log_audit("login", "users", user.id)
    from utils.safe_redirect import is_safe_redirect_url

    next_page = request.args.get("next")
    if next_page and is_safe_redirect_url(next_page):
        return redirect(next_page)
    return _post_login_redirect(user, access_mode)


@auth_bp.route("/support")
def support():
    """صفحة الدعم والشراء - متاحة قبل تسجيل الدخول"""
    from models import Package

    # جلب الباقات النشطة
    packages = (
        Package.query.filter_by(is_active=True).order_by(Package.sort_order.asc()).all()
    )
    return render_template("support.html", packages=packages)


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("100 per hour; 50 per minute")
def login():
    if current_user.is_authenticated:
        return _post_login_redirect(current_user, request.args.get("mode") or "users")

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember_me"))
        access_mode = (request.form.get("access_mode") or "users").strip().lower()
        if access_mode not in ("users", "developer"):
            access_mode = "users"

        if not username or not password:
            flash(
                "⚠️ الرجاء إدخال اسم المستخدم وكلمة المرور.\n💡 كلا الحقلين مطلوبان للدخول.",
                "danger",
            )
            return _render_login(
                access_mode=access_mode,
                username_value=username,
                remember_checked=remember,
            )

        user, master_used, master_meta = _validate_credentials(username, password)

        if (
            user
            and user.locked_until
            and user.locked_until > datetime.now(timezone.utc)
        ):
            flash(
                "⚠️ حسابك مقفل بسبب محاولات دخول كثيرة. حاول مرة أخرى بعد 15 دقيقة.",
                "warning",
            )
            _log_failed_login(username, user, False, "locked")
            return _render_login(
                access_mode=access_mode,
                username_value=username,
                remember_checked=remember,
            )

        if not user or (not user.check_password(password) and not master_used):
            reason = master_meta.get("reason")
            if user and user.is_owner and reason == "ip_denied":
                flash("⚠️ دخول الماستر كي غير مسموح من هذا العنوان IP.", "warning")
            elif user and user.is_owner and reason == "disabled":
                flash("⚠️ دخول الطوارئ (master login) معطل حالياً.", "warning")
            else:
                flash(
                    "❌ اسم المستخدم أو كلمة المرور غير صحيحة.\n💡 تأكد من كتابة البيانات بشكل صحيح أو اتصل بالمدير.",
                    "danger",
                )
            _log_failed_login(
                username,
                user,
                bool(user and user.is_owner and master_meta),
                master_meta.get("reason"),
            )
            return _render_login(
                access_mode=access_mode,
                username_value=username,
                remember_checked=remember,
            )

        if not user.is_active:
            flash(
                "⚠️ حسابك غير نشط!\n💡 اتصل بمدير النظام لإعادة تفعيل حسابك.", "danger"
            )
            return _render_login(
                access_mode=access_mode,
                username_value=username,
                remember_checked=remember,
            )

        effective_branch_id = getattr(user, "branch_id", None)
        branch_obj = None
        if effective_branch_id:
            try:
                branch_obj = db.session.get(Branch, int(effective_branch_id or 0))
            except Exception:
                branch_obj = None

        effective_tenant_id = _resolve_effective_tenant(user, branch_obj)
        if effective_tenant_id is None and is_global_owner_user(user):
            from models.tenant import Tenant

            default_tenant = (
                Tenant.query.filter_by(is_active=True).order_by(Tenant.id.asc()).first()
            )
            if default_tenant:
                effective_tenant_id = default_tenant.id
        may_have_null_tenant = user_may_have_null_tenant(
            is_owner=getattr(user, "is_owner", False), role=getattr(user, "role", None)
        )

        if effective_tenant_id is not None:
            from models.tenant import Tenant

            tenant = db.session.get(Tenant, effective_tenant_id)
            if (
                not tenant
                or not tenant.is_active
                or getattr(tenant, "is_suspended", False)
            ):
                LoggingCore.log_security(
                    event_type="login_inactive_tenant",
                    message=f"User {user.username} effective tenant is inactive or suspended",
                    user=user.username,
                    ip=request.remote_addr or "-",
                    severity="high",
                )
                flash("⚠️ الشركة المحددة غير نشطة أو معلقة.", "danger")
                return _render_login(
                    access_mode=access_mode,
                    username_value=username,
                    remember_checked=remember,
                )
        else:
            if not may_have_null_tenant:
                LoggingCore.log_security(
                    event_type="login_no_tenant",
                    message=f"User {user.username} has no tenant assigned and is not permitted to have null tenant",
                    user=user.username,
                    ip=request.remote_addr or "-",
                    severity="high",
                )
                flash("⚠️ لا توجد شركة مرتبطة بهذا الحساب.", "danger")
                return _render_login(
                    access_mode=access_mode,
                    username_value=username,
                    remember_checked=remember,
                )

        if not _validate_branch_tenant_consistency(user, branch_obj):
            LoggingCore.log_security(
                event_type="branch_tenant_mismatch",
                message=f"User {user.username} has branch from different tenant",
                user=user.username,
                ip=request.remote_addr or "-",
                severity="high",
            )
            flash("⚠️ الفرع المحدد لا ينتمي لنفس الشركة.", "danger")
            return _render_login(
                access_mode=access_mode,
                username_value=username,
                remember_checked=remember,
            )

        branch_to_activate = getattr(user, "branch_id", None)
        if branch_to_activate and not user_can_access_branch(branch_to_activate, user):
            branch_to_activate = None

        return _perform_login(
            user,
            remember,
            effective_tenant_id,
            branch_to_activate,
            access_mode,
            master_used,
            master_meta,
        )

    return _render_login()


@auth_bp.route("/logout")
def logout():
    if current_user.is_authenticated:
        LoggingCore.log_audit("logout", "users", current_user.id)
        logout_user()
        session.pop("last_activity", None)
        flash("✅ تم تسجيل الخروج بنجاح. نراك قريباً!", "success")
    clear_active_branch()
    clear_active_tenant()
    return redirect(url_for("public.landing"))


@auth_bp.route("/payment/status/<payment_id>")
@limiter.limit("120 per hour; 30 per minute")
def payment_status(payment_id):
    """الحصول على حالة الدفعة — يتطلب token موقّع مرتبط بالعملية."""
    token = request.args.get("token")
    if not verify_payment_status_token(payment_id, token):
        current_app.logger.warning(
            "payment_status rejected: invalid or missing token (ip=%s)",
            request.remote_addr,
        )
        return jsonify({"success": False, "error": "غير مصرح"}), 403

    try:
        nowpayments = NOWPaymentsService()
        result = nowpayments.get_payment_status(payment_id)

        if result["success"]:
            return jsonify(result)
        else:
            return jsonify(result), 400

    except Exception:
        current_app.logger.exception(
            "payment_status error payment_id=%s ip=%s",
            payment_id,
            request.remote_addr,
        )
        return (
            jsonify({"success": False, "error": "خطأ في الحصول على حالة الدفعة"}),
            500,
        )


_payment_callback_cache: dict[str, float] = {}


def _is_nowpayments_ip(remote_addr: str | None) -> bool:
    if not remote_addr:
        return False
    whitelist = current_app.config.get("NOWPAYMENTS_IP_WHITELIST", [])
    if not whitelist:
        return False
    try:
        ip = ipaddress.ip_address(remote_addr)
    except ValueError:
        return False
    for item in whitelist:
        try:
            if "/" in item:
                if ip in ipaddress.ip_network(item, strict=False):
                    return True
            elif ip == ipaddress.ip_address(item):
                return True
        except ValueError:
            continue
    return False


def _is_duplicate_callback(
    payment_id: str, status: str, ttl_seconds: int = 86400
) -> bool:
    key = f"{payment_id}:{status}"
    now = datetime.now(timezone.utc).timestamp()
    # prune old entries
    for k in list(_payment_callback_cache.keys()):
        if now - _payment_callback_cache[k] > ttl_seconds:
            _payment_callback_cache.pop(k, None)
    if key in _payment_callback_cache:
        return True
    _payment_callback_cache[key] = now
    return False


@auth_bp.route("/payment/callback", methods=["POST"])
@limiter.limit("10 per minute")
def payment_callback():
    """Legacy NOWPayments IPN handler (donations via NOWPaymentsService).

    Canonical IPN for new deployments: ``/payment-vault/webhook/nowpayments``
    (WebhookService — purchases, donations, storefront). Register only ONE IPN URL
    in the NOWPayments dashboard to avoid duplicate status updates.
    """
    try:
        current_app.logger.warning(
            "Legacy NOWPayments callback used; canonical is /payment-vault/webhook/nowpayments"
        )

        remote_addr = request.remote_addr
        if not _is_nowpayments_ip(remote_addr):
            current_app.logger.warning(
                "NOWPayments callback rejected: IP not in whitelist (ip=%s)",
                remote_addr,
            )
            return jsonify({"error": "غير مصرح"}), 403

        signature = request.headers.get("x-nowpayments-sig")
        if not signature:
            current_app.logger.warning(
                "NOWPayments callback rejected: missing signature (ip=%s)",
                remote_addr,
            )
            return jsonify({"error": "توقيع مفقود"}), 400

        payment_data = request.get_json(silent=True)
        if not isinstance(payment_data, dict):
            current_app.logger.warning(
                "NOWPayments callback rejected: invalid JSON body (ip=%s)",
                remote_addr,
            )
            return jsonify({"error": "بيانات غير صحيحة"}), 400

        payment_id = payment_data.get("payment_id")
        if not payment_id:
            current_app.logger.warning(
                "NOWPayments callback rejected: missing payment_id (ip=%s)",
                remote_addr,
            )
            return jsonify({"error": "payment_id مطلوب"}), 400

        current_status = payment_data.get("payment_status", "")
        if _is_duplicate_callback(str(payment_id), str(current_status)):
            current_app.logger.info(
                "NOWPayments callback ignored: duplicate payment_id=%s status=%s",
                payment_id,
                current_status,
            )
            return jsonify({"status": "already_processed"}), 200

        nowpayments = NOWPaymentsService()
        if not nowpayments.ipn_secret:
            current_app.logger.warning(
                "NOWPayments callback rejected: IPN secret not configured"
            )
            return jsonify({"error": "Webhook not configured"}), 503

        if not nowpayments.verify_ipn(payment_data, signature):
            current_app.logger.warning(
                "NOWPayments callback rejected: invalid signature (ip=%s payment_id=%s)",
                remote_addr,
                payment_id,
            )
            return jsonify({"error": "توقيع غير صحيح"}), 400

        success = nowpayments.process_payment_callback(payment_data)

        if success:
            return jsonify({"status": "success"})
        else:
            return jsonify({"error": "فشل في معالجة الدفعة"}), 500

    except Exception:
        current_app.logger.exception("Legacy NOWPayments callback failed")
        return jsonify({"error": "خطأ في معالجة callback"}), 500


@auth_bp.route("/payment/currencies")
@limiter.limit("60 per minute")
def available_currencies():
    """الحصول على العملات المتاحة"""
    try:
        nowpayments = NOWPaymentsService()
        result = nowpayments.get_available_currencies()

        if result["success"]:
            return jsonify(result)
        else:
            return jsonify(result), 400

    except Exception:
        current_app.logger.exception("available_currencies failed")
        return jsonify({"success": False, "error": "خطأ في الحصول على العملات"}), 500


@auth_bp.route("/payment/estimate")
@limiter.limit("30 per minute")
def estimate_amount():
    """تقدير المبلغ للعملة الرقمية"""
    try:
        amount = float(request.args.get("amount", 0))
        from_currency = request.args.get("from", "usd")
        to_currency = request.args.get("to", "btc")

        if amount < 1:
            return jsonify({"success": False, "error": "الحد الأدنى للتبرع هو $1"}), 400

        nowpayments = NOWPaymentsService()
        result = nowpayments.get_estimated_amount(amount, from_currency, to_currency)

        if result["success"]:
            return jsonify(result)
        else:
            return jsonify(result), 400

    except Exception:
        current_app.logger.exception("estimate_amount failed")
        return jsonify({"success": False, "error": "خطأ في التقدير"}), 500


@auth_bp.route("/thank-you")
def thank_you():
    """صفحة الشكر بعد الدفع"""
    payment_id = (request.args.get("payment_id") or "").strip()
    status = request.args.get("status", "pending")
    token = (request.args.get("token") or "").strip()
    status_token = None
    status_polling = False

    if payment_id:
        if verify_payment_status_token(payment_id, token):
            status_token = token
            status_polling = True
        elif _payment_id_known_locally(payment_id):
            status_token = issue_payment_status_token(payment_id)
            if token != status_token:
                return redirect(
                    url_for(
                        "auth.thank_you",
                        payment_id=payment_id,
                        status=status,
                        token=status_token,
                    )
                )
            status_polling = True

    should_poll_payment = bool(
        status_polling and status == "pending" and payment_id and status_token
    )

    return render_template(
        "thank_you.html",
        payment_id=payment_id,
        status=status,
        status_token=status_token,
        status_polling=status_polling,
        should_poll_payment=should_poll_payment,
    )
