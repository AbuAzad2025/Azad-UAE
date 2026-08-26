"""
Payment Vault Routes - مسارات الخزينة السرية
مسارات محمية بكلمة مرور منفصلة للدفع والتبرعات
"""

import logging
import os
import re
import secrets
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from flask_babel import gettext
from flask_login import current_user

from extensions import csrf, db, limiter
from models import (
    CardPayment,
    Donation,
    Package,
    PackagePurchase,
    PaymentLog,
    PaymentVault,
)
from models.package import TENANT_FLAG_COLUMNS, TENANT_LIMIT_COLUMNS
from services.idempotency_service import (
    IdempotencyHashMismatchError,
    IdempotencyInFlightError,
    IdempotencyService,
    hash_request_payload,
)
from services.logging_core import LoggingCore
from services.nowpayments_service import NOWPaymentsService
from services.vault_query_service import VaultQueryService
from utils.api_response import error_response, paginated_response, success_response
from utils.db_safety import atomic_transaction
from utils.decorators import owner_only
from utils.tenanting import tenant_query

payment_vault_bp = Blueprint("payment_vault", __name__, url_prefix="/payment-vault")
logger = logging.getLogger(__name__)

_DEV_VAULT_ORIGINS = frozenset(
    {
        "http://localhost:5000",
        "http://127.0.0.1:5000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    }
)


def _get_azad_platform_vault():
    """Return the Azad/platform vault controlled by the global owner."""
    return PaymentVault.get_platform_vault()


def _get_vault_for_current_tenant():
    """Backward-compatible helper name for owner vault routes."""
    return _get_azad_platform_vault()


def _is_production_env() -> bool:
    app_env = (os.environ.get("APP_ENV") or "production").strip().lower()
    debug = (os.environ.get("DEBUG") or "").strip().lower() in ("1", "true", "yes", "y")
    return app_env == "production" and not debug


def _is_duplicate_webhook(provider: str, event_id: str | None) -> bool:
    """Idempotent webhook deduplication via cache (24h TTL)."""
    if not event_id:
        return False
    try:
        from extensions import cache

        key = f"webhook:{provider}:{event_id}"
        if cache.get(key):
            logger.warning("%s webhook replay blocked: %s", provider, event_id)
            return True
        cache.set(key, "1", timeout=86400)
    except Exception:
        logger.exception("Webhook dedup cache error for %s %s", provider, event_id)
    return False


def _payment_vault_trusted_origins() -> frozenset[str]:
    from flask import current_app

    configured = current_app.config.get("PAYMENT_VAULT_TRUSTED_ORIGINS") or []
    origins = {str(o).strip().rstrip("/") for o in configured if o}
    if origins:
        return frozenset(origins)

    if _is_production_env():
        base = (current_app.config.get("BASE_URL") or "").strip().rstrip("/")
        return frozenset({base}) if base else frozenset()

    return _DEV_VAULT_ORIGINS


def _origin_from_referer(referer: str) -> str | None:
    try:
        parsed = urlparse(referer)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    except (TypeError, ValueError):
        return None
    return None


def _validate_public_api_origin():
    """Reject cross-site POSTs; require Origin/Referer in trusted allowlist."""
    trusted = _payment_vault_trusted_origins()
    if not trusted:
        logger.warning("Payment vault public API rejected: trusted origins not configured")
        return error_response(message="Origin policy not configured", status_code=503)

    origin = (request.headers.get("Origin") or "").strip().rstrip("/")
    referer = (request.headers.get("Referer") or "").strip()

    if origin:
        if origin not in trusted:
            logger.warning("Payment vault public API rejected: origin=%s", origin)
            return error_response(message=gettext("Origin غير مسموح"), status_code=403)
        return None

    if referer:
        ref_origin = _origin_from_referer(referer)
        if ref_origin and ref_origin in trusted:
            return None
        logger.warning("Payment vault public API rejected: referer=%s", referer[:120])
        return error_response(message=gettext("Referer غير مسموح"), status_code=403)

    return error_response(message=gettext("Origin أو Referer مطلوب"), status_code=403)


# Replay protection — reject webhook payloads older than 5 minutes

_WEBHOOK_MAX_AGE = 300  # 5 minutes


def _reject_stale_webhook_timestamp(data: dict | None) -> tuple | None:
    """Reject webhook payloads whose ``timestamp`` (or ``created_at``) is
    older than ``_WEBHOOK_MAX_AGE`` seconds.

    Returns ``(jsonify_response, status_code)`` if stale, else ``None``
    (graceful degradation when no timestamp is present).
    """
    if not data:
        return None
    ts_str = data.get("timestamp") or data.get("created_at")
    if not ts_str:
        return None
    try:
        if isinstance(ts_str, (int, float)):
            ts = datetime.fromtimestamp(ts_str, tz=UTC)
        else:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        age = (datetime.now(UTC) - ts).total_seconds()
        if age > _WEBHOOK_MAX_AGE:
            logger.warning("Webhook replay blocked: age=%.0fs", age)
            return error_response(message="Stale webhook — timestamp too old", status_code=401)
        if age < 0:
            logger.warning("Webhook replay blocked: future timestamp")
            return error_response(message="Invalid timestamp", status_code=401)
    except (ValueError, TypeError, AttributeError):
        logger.exception("Webhook timestamp parse failed")
    return None


# Idempotency-key ledger for public API endpoints
#
# Uses the durable ``IdempotencyKey`` model instead of an in-process dict so
# replays are detected across workers and deployments. The ledger row lives
# inside the caller's ``atomic_transaction``; a failure rolls the in-progress
# row back so the key never stays poisoned.


VAULT_PURCHASE_ENDPOINT = "payment_vault.api_create_purchase"
VAULT_DONATION_ENDPOINT = "payment_vault.api_create_donation"


def _check_idempotency_key(
    endpoint: str | None = None,
    payload: dict | None = None,
) -> tuple | None:
    """Begin or replay an idempotent public-API execution.

    ``endpoint`` defaults to ``request.endpoint``; ``payload`` defaults to the
    current JSON body with any ``idempotency_key`` field stripped before hashing.

    Returns ``(jsonify_response, status_code)`` when the key is missing,
    in-flight, reused with a different payload, or a completed replay.
    Returns ``None`` for a fresh key, leaving a new in-progress ledger row on
    ``g.vault_idempotency_record`` for ``_save_idempotency_key`` to complete.
    """
    key = (request.headers.get("Idempotency-Key") or "").strip()
    if not key:
        return error_response(message=gettext("Idempotency-Key header is required"), status_code=400)

    endpoint = endpoint or request.endpoint
    if not endpoint:
        return error_response(message="Idempotency endpoint context missing", status_code=500)

    api_key = getattr(g, "vault_api_key", None)
    tenant_id = getattr(api_key, "tenant_id", None) or 0
    user_id = getattr(api_key, "created_by", None) or getattr(api_key, "user_id", None)

    if payload is None:
        payload = request.get_json(silent=True)
    request_hash = hash_request_payload({k: v for k, v in (payload or {}).items() if k != "idempotency_key"})

    try:
        record, stored = IdempotencyService.begin(
            tenant_id=int(tenant_id),
            endpoint=endpoint,
            key=key,
            user_id=user_id,
            request_hash=request_hash,
        )
    except IdempotencyInFlightError:
        return error_response(
            message=gettext("طلب مكرر قيد المعالجة حالياً. أعد المحاولة بعد لحظات."),
            status_code=409,
        )
    except IdempotencyHashMismatchError:
        return error_response(
            message=gettext("مفتاح عدم التكرار استُخدم مع بيانات مختلفة."),
            status_code=422,
        )

    if stored is not None:
        body, status = stored
        replay_data = {k: v for k, v in body.items() if k != "success"}
        return success_response(data=replay_data, meta={"idempotent_replay": True}, status_code=status)

    g.vault_idempotency_record = record
    return None


def _save_idempotency_key(response_data: dict, status_code: int) -> None:
    """Persist the final response on the in-progress ledger row."""
    record = getattr(g, "vault_idempotency_record", None)
    if record is not None:
        IdempotencyService.complete(record, response_data, status_code)


# API-key validation & scope enforcement

_API_KEY_SCOPES = frozenset({"read", "write"})


def _validate_api_key(*, required_scope: str = "write") -> tuple | None:
    """Check ``X-API-Key`` header and ensure it has the required scope.

    Returns ``None`` on success, or ``(jsonify, status)`` on failure.
    """
    raw_key = (request.headers.get("X-API-Key") or "").strip()
    if not raw_key:
        return error_response(message="API key is required", status_code=401)

    api_key = VaultQueryService.find_active_api_key(raw_key)
    if not api_key:
        return error_response(message="Invalid or inactive API key", status_code=403)

    scope = getattr(api_key, "scope", "write") or "write"
    if required_scope == "write" and scope == "read":
        return error_response(
            message="Read-only API key cannot perform this action",
            status_code=403,
        )

    # Make the validated key available to idempotency helpers.
    g.vault_api_key = api_key

    # Track usage
    try:
        with atomic_transaction("api_key_usage_tracking"):
            api_key.last_used = datetime.now(UTC)
            api_key.usage_count = (api_key.usage_count or 0) + 1
    except Exception:
        from flask import current_app

        current_app.logger.exception("Failed to track API key %s usage", api_key.id)

    return None


@payment_vault_bp.before_request
def _protect_owner_vault_pages():
    path = request.path or ""
    if path.startswith("/payment-vault/api/") or path.startswith("/payment-vault/webhook/"):
        return None

    if not current_user.is_authenticated:
        flash(gettext("الرجاء تسجيل الدخول أولاً"), "warning")
        return redirect(url_for("auth.login"))

    if not current_user.is_owner:
        flash(gettext("❌ غير مصرح - الخزينة السرية للمالك فقط!"), "danger")
        return redirect(url_for("main.dashboard"))

    from utils.security_helpers import enforce_owner_ip_if_needed

    enforce_owner_ip_if_needed()

    return None


@payment_vault_bp.route("/")
@owner_only
def index():
    """الصفحة الرئيسية للخزينة السرية"""
    return render_template("payment_vault/index.html")


@payment_vault_bp.route("/unlock", methods=["GET", "POST"])
@owner_only
@limiter.limit("5 per minute")
def unlock_vault():
    """فتح الخزينة السرية"""
    if request.method == "POST":
        password = request.form.get("vault_password", "").strip()

        if not password:
            flash(gettext("❌ يرجى إدخال كلمة مرور الخزينة"), "danger")
            return render_template("payment_vault/unlock.html")

        vault = _get_vault_for_current_tenant()
        if not vault:
            vault = PaymentVault()
            vault.tenant_id = None
            vault.set_vault_password(password)
            vault.nowpayments_api_key = ""
            vault.nowpayments_ipn_secret = ""
            vault.bitcoin_address = ""
            vault.is_locked = False
            with atomic_transaction("vault_creation"):
                db.session.add(vault)

            PaymentLog.log_action(
                vault_id=vault.id,
                action="vault_created",
                description=gettext("تم إنشاء الخزينة السرية"),
                level="info",
                ip_address=request.remote_addr,
                user_agent=request.headers.get("User-Agent"),
            )

            flash(gettext("✅ تم إنشاء الخزينة السرية بنجاح!"), "success")
            return redirect(url_for("payment_vault.dashboard"))

        if vault.unlock_vault(password):
            PaymentLog.log_action(
                vault_id=vault.id,
                action="vault_unlocked",
                description=gettext("تم فتح الخزينة السرية"),
                level="info",
                ip_address=request.remote_addr,
                user_agent=request.headers.get("User-Agent"),
            )

            flash(gettext("✅ تم فتح الخزينة السرية بنجاح!"), "success")
            return redirect(url_for("payment_vault.dashboard"))
        else:
            PaymentLog.log_action(
                vault_id=vault.id,
                action="vault_unlock_failed",
                description=gettext("محاولة فتح فاشلة - كلمة مرور خاطئة"),
                level="warning",
                ip_address=request.remote_addr,
                user_agent=request.headers.get("User-Agent"),
            )

            if vault.is_locked_out():
                flash(
                    gettext("❌ تم قفل الخزينة بسبب المحاولات الفاشلة المتكررة!"),
                    "danger",
                )
            else:
                flash(gettext("❌ كلمة مرور الخزينة غير صحيحة!"), "danger")

            return render_template("payment_vault/unlock.html")

    return render_template("payment_vault/unlock.html")


@payment_vault_bp.route("/dashboard")
@owner_only
def dashboard():
    """لوحة تحكم الخزينة السرية"""
    vault = _get_vault_for_current_tenant()
    if not vault or vault.is_locked:
        flash(gettext("❌ يجب فتح الخزينة أولاً"), "warning")
        return redirect(url_for("payment_vault.unlock_vault"))

    from services.analytics_service import AnalyticsService
    from services.notification_service import SecurityService

    tid = None

    purchases = VaultQueryService.list_platform_records(tid=tid, transaction_type="purchase")
    donation_list = VaultQueryService.list_platform_records(tid=tid, transaction_type="donation")

    stats = {
        "total_purchases": len(purchases),
        "total_donations": len(donation_list),
        "total_revenue": sum(float(p.amount_usd or 0) for p in purchases + donation_list if p.status == "completed"),
        "pending_count": sum(1 for p in purchases + donation_list if p.status == "pending"),
    }

    daily_stats = AnalyticsService.get_daily_stats()
    stats.update(daily_stats)

    security_status = SecurityService.get_security_status()

    recent_purchases = VaultQueryService.recent_platform_records(tid=tid, transaction_type="purchase", limit=5)
    recent_donations = VaultQueryService.recent_platform_records(tid=tid, transaction_type="donation", limit=5)

    revenue_data = AnalyticsService.get_revenue_by_period(months=6)
    monthly_labels = revenue_data["labels"]
    monthly_purchases = revenue_data["purchases"]
    monthly_donations = revenue_data["donations"]

    payment_methods_stats = AnalyticsService.get_payment_method_stats()

    customer_behavior = AnalyticsService.get_customer_behavior()

    package_performance = AnalyticsService.get_package_performance()

    chart_data = {
        "labels": monthly_labels,
        "datasets": [
            {
                "label": gettext("مشتريات"),
                "data": monthly_purchases,
                "borderColor": "rgba(102, 126, 234, 1)",
                "backgroundColor": "rgba(102, 126, 234, 0.2)",
                "fill": True,
            },
            {
                "label": gettext("تبرعات"),
                "data": monthly_donations,
                "borderColor": "rgba(40, 167, 69, 1)",
                "backgroundColor": "rgba(40, 167, 69, 0.2)",
                "fill": True,
            },
        ],
    }

    return render_template(
        "payment_vault/dashboard.html",
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
        package_performance=package_performance,
        chart_data=chart_data,
    )


@payment_vault_bp.route("/settings", methods=["GET", "POST"])
@owner_only
def settings():
    """إعدادات الخزينة السرية"""
    vault = _get_vault_for_current_tenant()
    if not vault or not vault.is_vault_accessible():
        flash(gettext("❌ الخزينة مقفلة، يرجى إدخال كلمة المرور"), "warning")
        return redirect(url_for("payment_vault.unlock_vault"))

    if request.method == "POST":

        def _as_float(value, default):
            try:
                if value is None:
                    return float(default)
                s = str(value).strip()
                if s == "":
                    return float(default)
                return float(s)
            except (TypeError, ValueError, AttributeError):
                return float(default)

        def _as_int(value, default):
            try:
                if value is None:
                    return int(default)
                s = str(value).strip()
                if s == "":
                    return int(default)
                return int(s)
            except (TypeError, ValueError, AttributeError):
                return int(default)

        vault.nowpayments_api_key = request.form.get("nowpayments_api_key", vault.nowpayments_api_key)
        vault.nowpayments_ipn_secret = request.form.get("nowpayments_ipn_secret", vault.nowpayments_ipn_secret)
        vault.bitcoin_address = request.form.get("bitcoin_address", vault.bitcoin_address)
        vault.ethereum_address = request.form.get("ethereum_address", vault.ethereum_address)
        vault.usdt_address = request.form.get("usdt_address", vault.usdt_address)

        vault.paypal_business_email = request.form.get("paypal_business_email", vault.paypal_business_email)
        vault.paypal_client_id = request.form.get("paypal_client_id", vault.paypal_client_id)
        vault.paypal_client_secret = request.form.get("paypal_client_secret", vault.paypal_client_secret)
        vault.paypal_mode = request.form.get("paypal_mode", vault.paypal_mode)

        vault.bank_name = request.form.get("bank_name", vault.bank_name)
        vault.bank_account_name = request.form.get("bank_account_name", vault.bank_account_name)
        vault.bank_account_number = request.form.get("bank_account_number", vault.bank_account_number)
        vault.bank_iban = request.form.get("bank_iban", vault.bank_iban)
        vault.bank_swift_code = request.form.get("bank_swift_code", vault.bank_swift_code)
        vault.bank_branch = request.form.get("bank_branch", vault.bank_branch)
        vault.bank_country = request.form.get("bank_country", vault.bank_country)
        vault.bank_currency = request.form.get("bank_currency", vault.bank_currency)

        vault.stripe_publishable_key = request.form.get("stripe_publishable_key", vault.stripe_publishable_key)
        vault.stripe_secret_key = request.form.get("stripe_secret_key", vault.stripe_secret_key)
        vault.stripe_webhook_secret = request.form.get("stripe_webhook_secret", vault.stripe_webhook_secret)

        vault.min_donation_amount = _as_float(request.form.get("min_donation_amount"), vault.min_donation_amount)
        vault.max_donation_amount = _as_float(request.form.get("max_donation_amount"), vault.max_donation_amount)
        vault.daily_limit = _as_float(request.form.get("daily_limit"), vault.daily_limit)

        vault.donations_enabled = bool(request.form.get("donations_enabled"))
        vault.donation_page_enabled = bool(request.form.get("donation_page_enabled"))
        vault.donation_title_ar = request.form.get("donation_title_ar") or vault.donation_title_ar
        vault.donation_title_en = request.form.get("donation_title_en") or vault.donation_title_en
        vault.donation_intro_ar = request.form.get("donation_intro_ar") or vault.donation_intro_ar
        vault.donation_intro_en = request.form.get("donation_intro_en") or vault.donation_intro_en
        vault.donation_debit_account = (request.form.get("donation_debit_account") or "1120").strip()
        vault.donation_credit_account = (request.form.get("donation_credit_account") or "4200").strip()

        vault.require_2fa = bool(request.form.get("require_2fa"))
        vault.auto_lock_minutes = _as_int(request.form.get("auto_lock_minutes"), vault.auto_lock_minutes)
        vault.max_failed_attempts = _as_int(request.form.get("max_failed_attempts"), vault.max_failed_attempts)

        vault.updated_at = datetime.now(UTC)

        with atomic_transaction("vault_settings_update"):
            PaymentLog.log_action(
                vault_id=vault.id,
                action="settings_updated",
                description=gettext("تم تحديث إعدادات الخزينة"),
                level="info",
                ip_address=request.remote_addr,
                user_agent=request.headers.get("User-Agent"),
            )

        flash(gettext("✅ تم تحديث إعدادات الخزينة بنجاح!"), "success")
        return redirect(url_for("payment_vault.settings"))

    return render_template("payment_vault/settings.html", vault=vault)


@payment_vault_bp.route("/donations")
@owner_only
def donations():
    """عرض التبرعات"""
    vault = _get_vault_for_current_tenant()
    if not vault or vault.is_locked:
        flash(gettext("❌ يجب فتح الخزينة أولاً"), "warning")
        return redirect(url_for("payment_vault.unlock_vault"))

    status_filter = request.args.get("status", "")
    crypto_filter = request.args.get("crypto", "")
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    search_query = request.args.get("search", "")

    tid = None
    pagination, completed_count, pending_count, total_amount = VaultQueryService.donations_overview(
        tid,
        status_filter,
        crypto_filter,
        search_query,
        page,
        per_page,
    )
    donation_list = pagination.items
    total_donations = pagination.total

    return render_template(
        "payment_vault/donations.html",
        donations=donation_list,
        pagination=pagination,
        total_donations=total_donations,
        completed_count=completed_count,
        pending_count=pending_count,
        total_amount=total_amount,
    )


@payment_vault_bp.route("/packages-management")
@owner_only
def packages_management():
    """إدارة الباقات من الخزينة"""
    vault = _get_vault_for_current_tenant()
    if not vault or vault.is_locked:
        flash(gettext("❌ يجب فتح الخزينة أولاً"), "warning")
        return redirect(url_for("payment_vault.unlock_vault"))

    packages = VaultQueryService.list_packages_ordered()

    package_stats = VaultQueryService.package_purchase_counts_by_slug(("basic", "professional", "enterprise"))

    return render_template("payment_vault/packages.html", packages=packages, package_stats=package_stats)


def _package_form_int(value, default=None):
    """Parse an integer package form field; blank/invalid → default. ``-1`` = unlimited."""
    try:
        s = str(value).strip()
        if not s:
            return default
        return int(s)
    except (TypeError, ValueError):
        return default


def _package_limits_flags_from_form(form, current=None):
    """Extract the 9 quantitative limits + 8 feature flags from a package form.

    On edit, ``current`` (the existing Package) supplies per-field fallbacks so
    a blank input keeps the stored value; on create, blanks fall back to None
    (unlimited where the column is nullable).
    """
    data = {}
    for col in TENANT_LIMIT_COLUMNS:
        fallback = getattr(current, col, None) if current is not None else None
        data[col] = _package_form_int(form.get(col), fallback)
    for col in TENANT_FLAG_COLUMNS:
        data[col] = form.get(col) == "on"
    return data


@payment_vault_bp.route("/package/create", methods=["POST"])
@owner_only
def create_package():
    """إنشاء باقة جديدة من لوحة الخزينة."""
    vault = _get_vault_for_current_tenant()
    if not vault or vault.is_locked:
        flash(gettext("❌ يجب فتح الخزينة أولاً"), "warning")
        return redirect(url_for("payment_vault.unlock_vault"))

    def _slugify(value):
        value = re.sub(r"[^a-zA-Z0-9\\s_-]+", "", (value or "").strip().lower())
        value = re.sub(r"[-\\s]+", "-", value).strip("-")
        return value or f"package-{secrets.token_hex(3)}"

    def _as_float(value, default=0):
        try:
            return float(str(value).strip() or default)
        except (TypeError, ValueError, AttributeError):
            return float(default)

    def _as_int(value, default=0):
        try:
            return int(str(value).strip() or default)
        except (TypeError, ValueError, AttributeError):
            return int(default)

    try:
        name_ar = (request.form.get("name_ar") or "").strip()
        name_en = (request.form.get("name_en") or "").strip()
        slug = _slugify(request.form.get("slug") or name_en or name_ar)

        if not name_ar or not name_en:
            flash(gettext("❌ اسم الباقة بالعربية والإنجليزية مطلوبان"), "danger")
            return redirect(url_for("payment_vault.packages_management"))

        existing = VaultQueryService.find_package_by_slug(slug)
        if existing:
            flash(gettext("❌ هذا الرابط المختصر مستخدم بالفعل لباقـة أخرى"), "danger")
            return redirect(url_for("payment_vault.packages_management"))

        features_text = (request.form.get("features") or "").strip()
        limits_flags = _package_limits_flags_from_form(request.form)
        # Preserve the historical create-form defaults (1/1) when left blank.
        if limits_flags["max_users"] is None:
            limits_flags["max_users"] = 1
        if limits_flags["max_branches"] is None:
            limits_flags["max_branches"] = 1
        package = Package(
            name_ar=name_ar,
            name_en=name_en,
            slug=slug,
            icon=(request.form.get("icon") or "📦").strip() or "📦",
            price=_as_float(request.form.get("price"), 0),
            description_ar=(request.form.get("description_ar") or "").strip() or None,
            description_en=(request.form.get("description_en") or "").strip() or None,
            features=[line.strip() for line in features_text.splitlines() if line.strip()],
            is_active=request.form.get("is_active") == "on",
            is_featured=request.form.get("is_featured") == "on",
            badge_text=(request.form.get("badge_text") or "").strip() or None,
            sort_order=_as_int(request.form.get("sort_order"), 0),
            support_duration_months=_as_int(request.form.get("support_duration_months"), 3),
            **limits_flags,
        )

        with atomic_transaction("package_creation"):
            db.session.add(package)

        LoggingCore.log_audit(
            action="create",
            table_name="packages",
            record_id=package.id,
            changes={"package": package.name_ar, "slug": package.slug},
        )

        flash(gettext("✅ تم إنشاء الباقة بنجاح"), "success")
    except Exception as e:
        logger.exception("Package creation failed")
        flash(gettext(f"❌ خطأ أثناء إنشاء الباقة: {str(e)}"), "danger")

    return redirect(url_for("payment_vault.packages_management"))


@payment_vault_bp.route("/package/<int:package_id>/edit", methods=["GET", "POST"])
@owner_only
def edit_package(package_id):
    """تعديل باقة"""
    vault = _get_vault_for_current_tenant()
    if not vault or vault.is_locked:
        flash(gettext("❌ يجب فتح الخزينة أولاً"), "warning")
        return redirect(url_for("payment_vault.unlock_vault"))

    package = VaultQueryService.get_package_or_404(package_id)

    if request.method == "POST":
        try:

            def _as_float(value, default):
                try:
                    if value is None:
                        return float(default)
                    s = str(value).strip()
                    if s == "":
                        return float(default)
                    return float(s)
                except (TypeError, ValueError, AttributeError):
                    return float(default)

            def _as_int(value, default):
                try:
                    if value is None:
                        return int(default)
                    s = str(value).strip()
                    if s == "":
                        return int(default)
                    return int(s)
                except (TypeError, ValueError, AttributeError):
                    return int(default)

            package.name_ar = request.form.get("name_ar", package.name_ar).strip()
            package.name_en = request.form.get("name_en", package.name_en).strip()
            package.description_ar = request.form.get("description_ar", package.description_ar or "").strip()
            package.description_en = request.form.get("description_en", package.description_en or "").strip()
            package.price = Decimal(str(_as_float(request.form.get("price"), package.price)))
            for col, value in _package_limits_flags_from_form(request.form, current=package).items():
                setattr(package, col, value)
            package.support_duration_months = _as_int(
                request.form.get("support_duration_months"),
                package.support_duration_months,
            )
            package.is_active = request.form.get("is_active") == "on"
            package.is_featured = request.form.get("is_featured") == "on"
            package.badge_text = request.form.get("badge_text", package.badge_text or "").strip()

            features = request.form.get("features", "").strip()
            package.features = features.split("\n") if features else []

            with atomic_transaction("package_update"):
                LoggingCore.log_audit(
                    action="update",
                    table_name="packages",
                    record_id=package.id,
                    changes={"updated": "Package updated"},
                )

            flash(gettext("✅ تم تحديث الباقة بنجاح!"), "success")
            return redirect(url_for("payment_vault.packages_management"))
        except Exception as e:
            logger.exception("Package update failed")
            flash(gettext(f"❌ خطأ: {str(e)}"), "danger")

    return render_template("payment_vault/edit_package.html", package=package)


@payment_vault_bp.route("/package/<int:package_id>/delete", methods=["POST"])
@owner_only
def delete_package(package_id):
    """حذف باقة"""
    vault = _get_vault_for_current_tenant()
    if not vault or vault.is_locked:
        return error_response(message=gettext("الخزينة مقفلة"), status_code=403)

    package = VaultQueryService.get_package_or_404(package_id)

    try:
        with atomic_transaction("package_deletion"):
            db.session.delete(package)
            LoggingCore.log_audit(
                action="delete",
                table_name="packages",
                record_id=package_id,
                changes={"deleted": f"Package {package.name_ar} deleted"},
            )

        return success_response(message=gettext("تم حذف الباقة بنجاح!"))
    except Exception:
        logger.exception("Payment vault package delete failed")
        return error_response(message="Could not delete package at this time", status_code=400)


@payment_vault_bp.route("/reports")
@owner_only
def reports():
    """التقارير المالية"""
    vault = _get_vault_for_current_tenant()
    if not vault or vault.is_locked:
        flash(gettext("❌ يجب فتح الخزينة أولاً"), "warning")
        return redirect(url_for("payment_vault.unlock_vault"))

    tid = None
    all_transactions = VaultQueryService.list_platform_records_desc(tid)
    purchases = [t for t in all_transactions if t.transaction_type == "purchase"]
    donations = [t for t in all_transactions if t.transaction_type == "donation"]

    summary = {
        "total_revenue": sum(float(t.amount_usd or 0) for t in all_transactions),
        "total_purchases_amount": sum(float(p.amount_usd or 0) for p in purchases),
        "total_donations_amount": sum(float(d.amount_usd or 0) for d in donations),
        "total_transactions": len(all_transactions),
    }

    now = datetime.now()
    month_keys = []
    for i in range(5, -1, -1):
        m = now.month - i
        y = now.year
        while m <= 0:
            m += 12
            y -= 1
        month_keys.append((y, m))

    start_of_window = datetime(month_keys[0][0], month_keys[0][1], 1)
    monthly_rows = VaultQueryService.donation_monthly_aggregates(tid, start_of_window)

    monthly_totals = {}
    for row in monthly_rows:
        monthly_totals[(int(row.y), int(row.m), row.transaction_type)] = float(row.total or 0)

    monthly_labels = []
    monthly_purchases_data = []
    monthly_donations_data = []
    for y, m in month_keys:
        monthly_labels.append(datetime(y, m, 1).strftime("%b"))
        monthly_purchases_data.append(round(monthly_totals.get((y, m, "purchase"), 0.0), 2))
        monthly_donations_data.append(round(monthly_totals.get((y, m, "donation"), 0.0), 2))

    package_stats = VaultQueryService.platform_package_purchase_counts(tid, ("basic", "professional", "enterprise"))

    return render_template(
        "payment_vault/reports.html",
        transactions=all_transactions,
        summary=summary,
        monthly_labels=monthly_labels,
        monthly_purchases_data=monthly_purchases_data,
        monthly_donations_data=monthly_donations_data,
        package_stats=package_stats,
    )


@payment_vault_bp.route("/lock", methods=["GET", "POST"])
@owner_only
def lock_vault():
    """قفل الخزينة"""
    vault = _get_vault_for_current_tenant()
    if vault:
        vault.lock_vault()

        PaymentLog.log_action(
            vault_id=vault.id,
            action="vault_locked",
            description=gettext("تم قفل الخزينة السرية"),
            level="info",
            ip_address=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
        )

        flash(gettext("✅ تم قفل الخزينة السرية بنجاح!"), "success")

    return redirect(url_for("payment_vault.index"))


@payment_vault_bp.route("/cards")
@owner_only
def cards():
    """عرض البطاقات المحفوظة"""
    vault = _get_vault_for_current_tenant()
    if not vault or vault.is_locked:
        flash(gettext("❌ يجب فتح الخزينة أولاً"), "warning")
        return redirect(url_for("payment_vault.unlock_vault"))

    card_list = VaultQueryService.list_cards()

    total_cards = len(card_list)
    total_amount = sum(float(c.amount or 0) for c in card_list if c.status == "completed")
    visa_count = sum(1 for c in card_list if c.card_type == "Visa")
    mastercard_count = sum(1 for c in card_list if c.card_type == "Mastercard")

    return render_template(
        "payment_vault/cards.html",
        cards=card_list,
        total_cards=total_cards,
        total_amount=total_amount,
        visa_count=visa_count,
        mastercard_count=mastercard_count,
    )


@payment_vault_bp.route("/card/<int:card_id>/decrypt", methods=["POST"])
@owner_only
def decrypt_card(card_id):
    """فك تشفير بيانات البطاقة (للمالك فقط)"""
    vault = _get_vault_for_current_tenant()
    if not vault or vault.is_locked:
        return error_response(message=gettext("الخزينة مقفلة"), status_code=403)

    card = VaultQueryService.get_card_or_404(card_id)
    PaymentLog.log_action(
        vault_id=vault.id,
        action="card_viewed",
        description=gettext(f"عرض بطاقة {card.get_card_display()}"),
        level="info",
        ip_address=request.remote_addr,
        user_agent=request.headers.get("User-Agent"),
    )

    from flask import current_app

    from services.card_encryption_service import CardEncryptionService

    cipher = CardEncryptionService(encryption_key=current_app.config.get("CARD_ENCRYPTION_KEY") or "")
    return success_response(data={"card": card.to_dict(cipher=cipher)})


@payment_vault_bp.route("/process-payment", methods=["POST"])
@owner_only
@limiter.limit("20 per minute")
def process_payment():
    """معالجة الدفع (كريبتو أو بطاقة) - متاح للمالك فقط لتوثيق العمليات اليدوية"""
    try:
        data = request.get_json(silent=True)

        if not data:
            return error_response(message=gettext("بيانات غير صحيحة"), status_code=400)

        payment_method = data.get("payment_method", "crypto")

        if payment_method == "crypto":
            try:
                amount = float(data.get("amount", 0))
            except (ValueError, TypeError):
                return error_response(message=gettext("المبلغ غير صحيح"), status_code=422)

            nowpayments = NOWPaymentsService()
            result = nowpayments.create_payment(
                amount=amount,
                crypto_currency=data.get("crypto_currency", "btc"),
                customer_email=data.get("customer_email") or data.get("donor_email", ""),
                description=data.get("description", ""),
                transaction_type=data.get("type", "donation"),
                package=data.get("package", ""),
                customer_name=data.get("customer_name", ""),
                customer_phone=data.get("customer_phone", ""),
                donor_name=data.get("donor_name", ""),
                donor_email=data.get("donor_email", ""),
                donor_message=data.get("donor_message", ""),
            )
            return success_response(data=result)

        elif payment_method == "card":
            try:
                amount = float(data.get("amount", 0))
            except (ValueError, TypeError):
                return error_response(message=gettext("المبلغ غير صحيح"), status_code=422)

            if amount < 1:
                return error_response(message=gettext("الحد الأدنى هو $1"), status_code=400)

            card_number = data.get("card_number", "").replace(" ", "")
            cvv = data.get("cvv", "")
            expiry = data.get("expiry", "")

            if not card_number or len(card_number) < 13:
                return error_response(message=gettext("رقم البطاقة غير صحيح"), status_code=400)

            card_payment = CardPayment(
                customer_name=data.get("customer_name", ""),
                customer_email=data.get("customer_email", ""),
                customer_phone=data.get("customer_phone", ""),
                transaction_type=data.get("type", "donation"),
                package=data.get("package", ""),
                amount=amount,
                transaction_id=f"CARD_{int(datetime.now().timestamp())}",
                payment_gateway="whatsapp",
                status="pending",
                ip_address=request.remote_addr,
                user_agent=request.headers.get("User-Agent"),
            )

            from flask import current_app

            from services.card_encryption_service import CardEncryptionService

            cipher = CardEncryptionService(encryption_key=current_app.config.get("CARD_ENCRYPTION_KEY") or "")
            if card_payment.encrypt_card_data(card_number, cvv, expiry, cipher=cipher):
                with atomic_transaction("card_payment_storage"):
                    db.session.add(card_payment)
                    PaymentLog.log_action(
                        vault_id=(_get_vault_for_current_tenant().id if _get_vault_for_current_tenant() else None),
                        action="card_payment_received",
                        description=gettext(f"دفع بالبطاقة: {card_payment.get_card_display()} - ${amount}"),
                        level="info",
                        ip_address=request.remote_addr,
                        user_agent=request.headers.get("User-Agent"),
                    )

                return success_response(
                    data={
                        "transaction_id": card_payment.transaction_id,
                        "whatsapp": "0598953362",
                        "next_step": gettext("سيتم التواصل معك عبر WhatsApp خلال 24 ساعة"),
                    },
                    message=gettext("تم حفظ معلومات البطاقة بشكل آمن ومشفر"),
                )
            else:
                return error_response(message=gettext("فشل تشفير البيانات"), status_code=500)

        else:
            return error_response(message=gettext("طريقة دفع غير مدعومة"), status_code=400)

    except Exception:
        logger.exception("Payment vault process-payment failed")
        return error_response(message="Could not process payment at this time", status_code=500)


@payment_vault_bp.route("/change-password", methods=["GET", "POST"])
@owner_only
def change_password():
    """تغيير كلمة مرور الخزينة"""
    vault = _get_vault_for_current_tenant()
    if not vault or not vault.is_vault_accessible():
        flash(gettext("❌ الخزينة مقفلة، يرجى إدخال كلمة المرور"), "warning")
        return redirect(url_for("payment_vault.unlock_vault"))

    if request.method == "POST":
        current_password = request.form.get("current_password", "").strip()
        new_password = request.form.get("new_password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()

        if not current_password or not new_password or not confirm_password:
            flash(gettext("❌ يرجى ملء جميع الحقول"), "danger")
            return render_template("payment_vault/change_password.html")

        if not vault.check_vault_password(current_password):
            flash(gettext("❌ كلمة المرور الحالية غير صحيحة"), "danger")
            return render_template("payment_vault/change_password.html")

        if new_password != confirm_password:
            flash(gettext("❌ كلمة المرور الجديدة غير متطابقة"), "danger")
            return render_template("payment_vault/change_password.html")

        if len(new_password) < 8:
            flash(gettext("❌ كلمة المرور يجب أن تكون 8 أحرف على الأقل"), "danger")
            return render_template("payment_vault/change_password.html")

        vault.set_vault_password(new_password)
        vault.updated_at = datetime.now(UTC)

        with atomic_transaction("vault_password_change"):
            PaymentLog.log_action(
                vault_id=vault.id,
                action="password_changed",
                description=gettext("تم تغيير كلمة مرور الخزينة"),
                level="info",
                ip_address=request.remote_addr,
                user_agent=request.headers.get("User-Agent"),
            )

        flash(gettext("✅ تم تغيير كلمة مرور الخزينة بنجاح!"), "success")
        return redirect(url_for("payment_vault.dashboard"))

    return render_template("payment_vault/change_password.html")


@payment_vault_bp.route("/api/purchase", methods=["POST"])
@csrf.exempt
@limiter.limit("10 per minute")
def api_create_purchase():
    """API لإنشاء عملية شراء جديدة"""
    try:
        origin_error = _validate_public_api_origin()
        if origin_error:
            return origin_error

        api_key_err = _validate_api_key(required_scope="write")
        if api_key_err:
            return api_key_err

        if not request.is_json:
            return error_response(message="Content-Type must be application/json", status_code=400)

        data = request.get_json(silent=True) or {}

        required_fields = [
            "package_id",
            "customer_name",
            "customer_email",
            "payment_method",
            "amount_paid",
        ]
        for field in required_fields:
            if not data.get(field):
                return error_response(message=gettext(f"الحقل {field} مطلوب"), status_code=400)

        import re

        email_pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
        if not re.match(email_pattern, data["customer_email"]):
            return error_response(message=gettext("بريد إلكتروني غير صحيح"), status_code=400)

        from html import escape

        def sanitize(text, max_len=200):
            if not text:
                return None
            return escape(str(text)[:max_len].strip())

        customer_name = sanitize(data["customer_name"], 100)
        customer_email = sanitize(data["customer_email"], 100)
        customer_phone = sanitize(data.get("customer_phone", ""), 50)
        company_name = sanitize(data.get("company_name", ""), 100)

        package = VaultQueryService.get_package_by_id(data["package_id"])
        if not package or not package.is_active:
            return error_response(message=gettext("الباقة غير متاحة"), status_code=404)

        try:
            amount_paid_value = Decimal(str(data["amount_paid"]))
        except (InvalidOperation, TypeError, ValueError):
            return error_response(message=gettext("المبلغ المدفوع غير صالح"), status_code=400)
        if amount_paid_value < Decimal(str(package.price or 0)):
            return error_response(
                message=gettext("المبلغ المدفوع أقل من سعر الباقة"),
                status_code=400,
            )

        with atomic_transaction("api_purchase"):
            idempotent = _check_idempotency_key(VAULT_PURCHASE_ENDPOINT, data)
            if idempotent:
                return idempotent

            purchase = PackagePurchase(
                package_id=int(data["package_id"]),
                customer_name=customer_name,
                customer_email=customer_email,
                customer_phone=customer_phone,
                company_name=company_name,
                payment_method=data["payment_method"],
                payment_status="pending",
                amount_paid=amount_paid_value,
                currency=data.get("currency", "USD"),
                transaction_id=sanitize(data.get("transaction_id", ""), 100),
                payment_details=data.get("payment_details"),
                notes=sanitize(data.get("notes", ""), 500),
            )
            db.session.add(purchase)

            payment_result = {"success": False}
            crypto_currency = None

            if purchase.payment_method != "bank":
                nowpayments = NOWPaymentsService()
                crypto_currency = str(data.get("crypto_currency") or data.get("crypto_type") or "btc").strip().lower()

                payment_result = nowpayments.create_payment(
                    amount=purchase.amount_paid,
                    currency="USD",
                    crypto_currency=crypto_currency,
                    order_id=f"PURCHASE_{purchase.id}",
                    customer_email=customer_email,
                    description=gettext(f"شراء باقة {package.name_ar} - ${purchase.amount_paid}"),
                    transaction_type="purchase",
                    package=package.slug,
                    customer_name=customer_name,
                    customer_phone=customer_phone,
                )

                if payment_result.get("success"):
                    purchase.transaction_id = payment_result.get("payment_id", purchase.transaction_id)
                    purchase.payment_details = {
                        "nowpayments_id": payment_result.get("payment_id"),
                        "pay_address": payment_result.get("pay_address"),
                        "pay_amount": payment_result.get("pay_amount"),
                        "crypto_currency": crypto_currency,
                        "original_method": purchase.payment_method,
                        "converted_to_crypto": True,
                    }
            else:
                purchase.payment_details = {
                    "original_method": "bank",
                    "converted_to_crypto": False,
                    "note": gettext("يتطلب تواصل مباشر للحصول على تفاصيل الحساب البنكي"),
                }

            donation = VaultQueryService.find_donation_by_transaction_hash(payment_result.get("payment_id"))

            if not donation:
                donation = Donation(
                    amount_usd=purchase.amount_paid,
                    payment_method=purchase.payment_method,
                    transaction_type="purchase",
                    package=package.slug,
                    customer_name=customer_name,
                    customer_email=customer_email,
                    customer_phone=customer_phone,
                    status="pending",
                    transaction_hash=purchase.transaction_id,
                    ip_address=request.remote_addr,
                    user_agent=request.headers.get("User-Agent", "")[:500],
                )
                db.session.add(donation)
                LoggingCore.log_audit(
                    action=f"purchase_created: {package.name_ar} - ${purchase.amount_paid}",
                    table_name="package_purchases",
                    record_id=purchase.id,
                    changes={
                        "customer": customer_name,
                        "package": package.name_ar,
                        "amount": purchase.amount_paid,
                    },
                )

            response_data = {
                "success": True,
                "message": gettext("تم إنشاء طلب الشراء بنجاح"),
                "purchase_id": purchase.id,
                "payment_method_display": purchase.payment_method,
                "actual_payment_method": "crypto",
            }

            if payment_result.get("success"):
                response_data.update(
                    {
                        "payment_address": payment_result.get("pay_address"),
                        "payment_amount": payment_result.get("pay_amount"),
                        "crypto_currency": (crypto_currency.upper() if crypto_currency else None),
                        "payment_id": payment_result.get("payment_id"),
                        "payment_url": payment_result.get("invoice_url"),
                    }
                )

            _save_idempotency_key(response_data, 201)
            return success_response(
                data={k: v for k, v in response_data.items() if k != "success"},
                message=response_data.get("message"),
                status_code=201,
            )

    except Exception:
        logger.exception("Payment vault purchase API failed")
        return error_response(message="Could not create purchase at this time", status_code=500)


@payment_vault_bp.route("/api/donation", methods=["POST"])
@csrf.exempt
@limiter.limit("10 per minute")
def api_create_donation():
    """API لإنشاء تبرع جديد"""
    try:
        origin_error = _validate_public_api_origin()
        if origin_error:
            return origin_error

        api_key_err = _validate_api_key(required_scope="write")
        if api_key_err:
            return api_key_err

        if not request.is_json:
            return error_response(message="Content-Type must be application/json", status_code=400)

        data = request.get_json(silent=True) or {}

        if not data.get("amount") or not data.get("payment_method"):
            return error_response(message=gettext("المبلغ وطريقة الدفع مطلوبة"), status_code=400)

        if float(data["amount"]) < 15:
            return error_response(message=gettext("الحد الأدنى للتبرع $15"), status_code=400)

        from html import escape

        def sanitize(text, max_len=200):
            if not text:
                return None
            return escape(str(text)[:max_len].strip())

        donor_name = sanitize(data.get("donor_name"), 100)
        donor_email = sanitize(data.get("donor_email"), 100)
        donor_message = sanitize(data.get("message"), 500)

        if donor_email:
            import re

            email_pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
            if not re.match(email_pattern, donor_email):
                donor_email = None

        with atomic_transaction("api_donation"):
            idempotent = _check_idempotency_key(VAULT_DONATION_ENDPOINT, data)
            if idempotent:
                return idempotent

            donation = Donation(
                amount_usd=float(data["amount"]),
                payment_method=data["payment_method"],
                crypto_type=sanitize(data.get("crypto_type"), 20),
                transaction_type="donation",
                donor_name=donor_name,
                donor_email=donor_email,
                donor_message=donor_message,
                status="pending",
                transaction_hash=sanitize(data.get("transaction_id"), 100),
                ip_address=request.remote_addr,
                user_agent=request.headers.get("User-Agent", "")[:500],
            )
            db.session.add(donation)

            nowpayments = NOWPaymentsService()
            crypto_currency = str(data.get("crypto_currency") or data.get("crypto_type") or "btc").strip().lower()

            payment_result = nowpayments.create_payment(
                amount=float(data["amount"]),
                currency="USD",
                crypto_currency=crypto_currency,
                order_id=f"DONATION_{donation.id}",
                customer_email=donor_email,
                description=gettext(f"تبرع لمشروع Azad Systems - ${data['amount']}"),
                transaction_type="donation",
                donor_name=donor_name,
                donor_email=donor_email,
                donor_message=donor_message,
            )

            if payment_result.get("success"):
                donation.transaction_hash = payment_result.get("payment_id", donation.transaction_hash)
                donation.wallet_address = payment_result.get("pay_address")
                donation.gateway_transaction_id = payment_result.get("payment_id")
                donation.gateway_name = "nowpayments"

            LoggingCore.log_audit(
                action=f"donation_created: ${donation.amount_usd}",
                table_name="donations",
                record_id=donation.id,
                changes={
                    "amount": float(donation.amount_usd),
                    "method": donation.payment_method,
                },
            )

            response_data = {
                "success": True,
                "message": gettext("شكراً على تبرعك!"),
                "donation_id": donation.id,
                "payment_method_display": donation.payment_method,
            }

            if payment_result.get("success"):
                response_data.update(
                    {
                        "payment_address": payment_result.get("pay_address"),
                        "payment_amount": payment_result.get("pay_amount"),
                        "crypto_currency": (crypto_currency.upper() if crypto_currency else None),
                        "payment_id": payment_result.get("payment_id"),
                        "payment_url": payment_result.get("invoice_url"),
                    }
                )

            _save_idempotency_key(response_data, 201)
            return success_response(
                data={k: v for k, v in response_data.items() if k != "success"},
                message=response_data.get("message"),
                status_code=201,
            )

    except Exception:
        logger.exception("Payment vault donation API failed")
        return error_response(message="Could not create donation at this time", status_code=500)


@payment_vault_bp.route("/purchases")
@owner_only
def view_purchases():
    """عرض جميع عمليات الشراء مع Pagination"""
    vault = _get_vault_for_current_tenant()
    if not vault or vault.is_locked:
        flash(gettext("❌ يجب فتح الخزينة أولاً"), "warning")
        return redirect(url_for("payment_vault.unlock_vault"))

    # Pagination
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    status_filter = request.args.get("status", "")

    # Pagination
    pagination = VaultQueryService.purchases_page(page, per_page, status_filter)

    purchases = pagination.items

    all_purchases = VaultQueryService.list_all_purchases()
    stats = {
        "total": len(all_purchases),
        "pending": len([p for p in all_purchases if p.payment_status == "pending"]),
        "completed": len([p for p in all_purchases if p.payment_status == "completed"]),
        "revenue": sum([p.amount_paid for p in all_purchases if p.payment_status == "completed"]),
    }

    return render_template(
        "payment_vault/purchases.html",
        purchases=purchases,
        stats=stats,
        pagination=pagination,
    )


@payment_vault_bp.route("/purchase/<int:id>")
@owner_only
def purchase_detail(**kwargs):
    """تفاصيل عملية شراء"""
    record_id = kwargs.pop("id")
    vault = _get_vault_for_current_tenant()
    if not vault or vault.is_locked:
        return redirect(url_for("payment_vault.unlock_vault"))

    purchase = VaultQueryService.get_purchase_or_404(record_id)
    return render_template("payment_vault/purchase_detail.html", purchase=purchase)


@payment_vault_bp.route("/purchase/<int:id>/send-email", methods=["POST"])
@owner_only
def send_email(id):
    """إرسال إيصال الشراء إلى البريد الإلكتروني للعميل"""
    vault = _get_vault_for_current_tenant()
    if not vault or vault.is_locked:
        return error_response(message=gettext("الخزينة مقفلة"), status_code=403)

    purchase = VaultQueryService.get_purchase_or_404(id)
    if not purchase.customer_email:
        return error_response(message=gettext("لا يوجد بريد إلكتروني للعميل"), status_code=400)

    try:
        from flask_mail import Message

        from extensions import mail

        package = purchase.package
        package_name = package.name_ar or package.name_en if package else None
        msg = Message(
            subject=gettext(f"إيصال شراء باقة #{purchase.id}"),
            recipients=[purchase.customer_email],
            body=gettext(
                f"مرحباً {purchase.customer_name or ''},\n"
                f"شكراً لشرائكم {package_name or 'الباقة'}.\n"
                f"المبلغ: {purchase.amount_paid} {purchase.currency}\n"
                f"حالة الدفع: {purchase.payment_status}"
            ),
        )
        mail.send(msg)
        return success_response()
    except Exception as exc:
        logger.error("Failed to send purchase receipt email: %s", exc)
        return error_response(message=gettext("فشل إرسال البريد"), status_code=500)


@payment_vault_bp.route("/purchase/<int:id>/activate", methods=["POST"])
@owner_only
def activate_purchase(**kwargs):
    """تفعيل عملية شراء"""
    record_id = kwargs.pop("id")
    purchase = VaultQueryService.get_purchase_or_404(record_id)

    try:
        purchase.activation_status = "activated"
        purchase.activation_date = datetime.now(UTC)
        purchase.payment_status = "completed"

        tid = None
        donation = VaultQueryService.find_purchase_donation_by_email(purchase.customer_email, tid)
        if donation:
            donation.status = "completed"
            donation.completed_at = datetime.now(UTC)

        with atomic_transaction("purchase_activate"):
            pass
        flash(gettext("✅ تم تفعيل الباقة"), "success")
    except Exception as e:
        logger.exception("Purchase activation failed")
        flash(gettext(f"❌ خطأ: {str(e)}"), "danger")

    return redirect(url_for("payment_vault.purchase_detail", id=record_id))


@payment_vault_bp.route("/api/package-stats/<int:package_id>")
@owner_only
def api_package_stats(package_id):
    """API لإحصائيات باقة محددة"""
    VaultQueryService.get_package_or_404(package_id)
    purchases = VaultQueryService.purchases_for_package(package_id)

    stats = {
        "total_sales": len(purchases),
        "total_revenue": sum([p.amount_paid for p in purchases if p.payment_status == "completed"]),
        "pending": len([p for p in purchases if p.payment_status == "pending"]),
        "completed": len([p for p in purchases if p.payment_status == "completed"]),
        "failed": len([p for p in purchases if p.payment_status == "failed"]),
    }

    return success_response(data=stats)


@payment_vault_bp.route("/package/<int:package_id>/toggle", methods=["POST"])
@owner_only
def toggle_package_status(package_id):
    """تبديل حالة الباقة (نشط/معطل)"""
    package = VaultQueryService.get_package_or_404(package_id)
    package.is_active = not package.is_active

    try:
        with atomic_transaction("package_toggle"):
            pass
        status_text = gettext("تم تنشيط") if package.is_active else gettext("تم تعطيل")
        return success_response(
            message=gettext(f"{status_text} الباقة {package.name_ar}"),
        )
    except Exception:
        logger.exception("Payment vault package toggle failed")
        return error_response(message="Could not update package at this time", status_code=500)


@payment_vault_bp.route("/donation/<int:donation_id>")
@owner_only
def donation_detail(donation_id):
    """عرض تفاصيل تبرع"""
    vault = _get_vault_for_current_tenant()
    if not vault or vault.is_locked:
        flash(gettext("❌ يجب فتح الخزينة أولاً"), "warning")
        return redirect(url_for("payment_vault.unlock_vault"))

    tid = None
    donation = VaultQueryService.get_platform_donation_or_404(donation_id, tid)
    return render_template("payment_vault/donation_detail.html", donation=donation)


@payment_vault_bp.route("/donation/<int:donation_id>/approve", methods=["POST"])
@owner_only
def approve_donation(donation_id):
    """قبول تبرع"""
    tid = None
    donation = VaultQueryService.get_platform_donation_or_404(donation_id, tid)

    try:
        donation.status = "completed"
        donation.completed_at = datetime.now(UTC)
        from services.donation_gl_service import DonationGLService

        DonationGLService.post_completed_donation(donation)
        with atomic_transaction("donation_approve"):
            LoggingCore.log_audit(
                action=f"donation_approved: ${donation.amount_usd}",
                table_name="donations",
                record_id=donation.id,
            )

        flash(gettext("✅ تم قبول التبرع"), "success")
    except Exception as e:
        logger.exception("Donation approval failed")
        flash(gettext(f"❌ خطأ: {str(e)}"), "danger")

    return redirect(url_for("payment_vault.donations"))


@payment_vault_bp.route("/donation/<int:donation_id>/reject", methods=["POST"])
@owner_only
def reject_donation(donation_id):
    """رفض تبرع"""
    tid = None
    donation = VaultQueryService.get_platform_donation_or_404(donation_id, tid)

    try:
        donation.status = "failed"
        with atomic_transaction("donation_reject"):
            LoggingCore.log_audit(
                action=f"donation_rejected: ${donation.amount_usd}",
                table_name="donations",
                record_id=donation.id,
            )

        flash(gettext("✅ تم رفض التبرع"), "warning")
    except Exception as e:
        logger.exception("Donation rejection failed")
        flash(gettext(f"❌ خطأ: {str(e)}"), "danger")

    return redirect(url_for("payment_vault.donations"))


@payment_vault_bp.route("/donation/<int:donation_id>/send-thank-you", methods=["POST"])
@owner_only
def send_donation_thank_you(donation_id):
    """إرسال رسالة شكر إلى البريد الإلكتروني للمتبرع"""
    vault = _get_vault_for_current_tenant()
    if not vault or vault.is_locked:
        return error_response(message=gettext("الخزينة مقفلة"), status_code=403)

    donation = VaultQueryService.get_any_donation_or_404(donation_id)
    if not donation.donor_email:
        return error_response(message=gettext("لا يوجد بريد إلكتروني للمتبرع"), status_code=400)

    try:
        from flask_mail import Message

        from extensions import mail

        donor_name = donation.donor_name or gettext("متبرع")
        msg = Message(
            subject=gettext(f"شكراً لتبرعكم - {donation.amount_usd} USD"),
            recipients=[donation.donor_email],
            body=gettext(
                f"عزيزنا {donor_name},\n"
                f"نشكركم جزيل الشكر على تبرعكم الكريم بقيمة {donation.amount_usd} USD.\n"
                f"دعمكم يساهم في إنجاح رسالتنا."
            ),
        )
        mail.send(msg)
        return success_response()
    except Exception as exc:
        logger.error("Failed to send donation thank-you email: %s", exc)
        return error_response(message=gettext("فشل إرسال البريد"), status_code=500)


@payment_vault_bp.route("/auto-approve", methods=["POST"])
@owner_only
def trigger_auto_approve():
    """تشغيل القبول التلقائي يدوياً"""
    from services.auto_approval_service import AutoApprovalService
    from services.notification_service import NotificationService

    result = AutoApprovalService.run_auto_approval()

    if result.get("total_approved", 0) > 0:
        NotificationService.notify_auto_approval(result["total_approved"], result["total_amount"])
        flash(
            gettext(f"✅ تم قبول {result['total_approved']} عملية تلقائياً بمبلغ ${result['total_amount']:.2f}"),
            "success",
        )
    else:
        flash(gettext("ℹ️ لا توجد عمليات تحتاج للقبول التلقائي"), "info")

    return redirect(url_for("payment_vault.dashboard"))


@payment_vault_bp.route("/api/notifications", methods=["GET"])
@owner_only
def api_notifications():
    """API للحصول على الإشعارات"""
    from services.notification_service import NotificationService

    limit = request.args.get("limit", 10, type=int)
    notifications = NotificationService.get_recent_notifications(limit)

    return success_response(data={"notifications": notifications, "count": len(notifications)})


@payment_vault_bp.route("/api/live-stats", methods=["GET"])
@owner_only
def api_live_stats():
    """API للإحصائيات المباشرة"""
    from services.analytics_service import AnalyticsService
    from services.notification_service import SecurityService

    daily_stats = AnalyticsService.get_daily_stats()
    security_status = SecurityService.get_security_status()

    tid = None
    pending_count = VaultQueryService.pending_platform_donations_count(tid)

    return success_response(
        data={
            "daily_revenue": daily_stats["today_revenue"],
            "daily_transactions": daily_stats["today_transactions"],
            "pending_count": pending_count,
            "security_level": security_status["security_level"],
            "timestamp": datetime.now(UTC).isoformat(),
        }
    )


@payment_vault_bp.route("/export/purchases")
@owner_only
def export_purchases():
    """تصدير المشتريات إلى CSV"""
    from flask import send_file

    from services.export_service import ExportService

    purchases = VaultQueryService.list_purchases_desc()
    csv_file = ExportService.export_purchases_to_csv(purchases)

    return send_file(
        csv_file,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"purchases_{datetime.now().strftime('%Y%m%d')}.csv",
    )


@payment_vault_bp.route("/export/donations")
@owner_only
def export_donations():
    """تصدير التبرعات إلى CSV"""
    from flask import send_file

    from services.export_service import ExportService

    tid = None
    donation_list = VaultQueryService.list_platform_records(tid=tid, transaction_type="donation")
    csv_file = ExportService.export_donations_to_csv(donation_list)

    return send_file(
        csv_file,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"donations_{datetime.now().strftime('%Y%m%d')}.csv",
    )


@payment_vault_bp.route("/export/cards")
@owner_only
def export_cards():
    """تصدير البطاقات إلى CSV"""
    from flask import send_file

    from services.export_service import ExportService

    card_list = tenant_query(CardPayment).order_by(CardPayment.created_at.desc()).all()
    csv_file = ExportService.export_cards_to_csv(card_list)

    return send_file(
        csv_file,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"cards_{datetime.now().strftime('%Y%m%d')}.csv",
    )


@payment_vault_bp.route("/export/report-pdf")
@owner_only
def export_report_pdf():
    """تصدير تقرير PDF"""
    from services.export_service import ExportService

    tid = None
    purchases = VaultQueryService.list_all_purchases()
    donations = VaultQueryService.list_platform_records(tid=tid, transaction_type="donation")

    stats = {
        gettext("إجمالي المشتريات"): len(purchases),
        gettext("إجمالي التبرعات"): len(donations),
        gettext(
            "إجمالي الإيرادات"
        ): f"${sum(float(p.amount_paid) for p in purchases) + sum(float(d.amount_usd or 0) for d in donations):.2f}",
    }

    table_headers = [gettext("العنصر"), gettext("العدد"), gettext("المبلغ")]
    table_data = [
        [
            gettext("المشتريات"),
            len(purchases),
            f"${sum(float(p.amount_paid) for p in purchases):.2f}",
        ],
        [
            gettext("التبرعات"),
            len(donations),
            f"${sum(float(d.amount_usd or 0) for d in donations):.2f}",
        ],
    ]

    html = ExportService.generate_pdf_report(
        gettext("تقرير الخزينة السرية الشامل"),
        {"stats": stats, "table_headers": table_headers, "table_data": table_data},
    )

    from flask import Response

    return Response(html, mimetype="text/html")


@payment_vault_bp.route("/webhook/nowpayments", methods=["POST"])
@csrf.exempt
@limiter.limit("100 per minute")
def nowpayments_webhook():
    """Webhook من NOWPayments"""
    try:
        from services.webhook_service import WebhookService

        payload = request.data
        data = request.get_json(silent=True)
        signature = request.headers.get("x-nowpayments-sig", "")

        stale = _reject_stale_webhook_timestamp(data)
        if stale:
            return stale

        vault = _get_vault_for_current_tenant()
        from utils.nowpayments_ipn import resolve_nowpayments_ipn_secret

        ipn_secret = resolve_nowpayments_ipn_secret(vault)
        if not ipn_secret:
            logger.warning("NOWPayments webhook rejected: IPN secret not configured")
            return error_response(message="Webhook not configured", status_code=503)
        if not signature:
            return error_response(message="Missing signature", status_code=400)
        if not WebhookService.verify_nowpayments_signature(payload, signature, ipn_secret):
            logger.warning("NOWPayments webhook signature verification failed")
            return error_response(message="Invalid signature", status_code=403)

        event_id = data.get("payment_id") if data else None
        if _is_duplicate_webhook("nowpayments", event_id):
            return success_response(data={"status": "duplicate"})

        result = WebhookService.process_nowpayments_webhook(data)

        if vault:
            PaymentLog.log_action(
                vault_id=vault.id,
                action="nowpayments_webhook_received",
                description=f"Payment status: {data.get('payment_status') if data else None}",
                level="info",
                transaction_id=data.get("payment_id") if data else None,
                ip_address=request.remote_addr,
                user_agent=request.headers.get("User-Agent"),
            )

        return success_response(data=result, status_code=200 if result.get("success") else 400)

    except Exception:
        logger.exception("NOWPayments webhook failed")
        return error_response(message="Webhook processing failed", status_code=500)


@payment_vault_bp.route("/webhook/stripe", methods=["POST"])
@csrf.exempt
@limiter.limit("100 per minute")
def stripe_webhook():
    """Webhook من Stripe"""
    try:
        from services.webhook_service import WebhookService

        payload = request.data
        data = request.get_json(silent=True)
        signature = request.headers.get("Stripe-Signature", "")

        stale = _reject_stale_webhook_timestamp(data)
        if stale:
            return stale

        vault = _get_vault_for_current_tenant()
        if not vault or not vault.stripe_webhook_secret:
            logger.warning("Stripe webhook rejected: webhook secret not configured")
            return error_response(message="Webhook not configured", status_code=503)
        if not signature:
            return error_response(message="Missing signature", status_code=400)
        if not WebhookService.verify_stripe_signature(payload, signature, vault.stripe_webhook_secret):
            logger.warning("Stripe webhook signature verification failed")
            return error_response(message="Invalid signature", status_code=403)

        event_id = data.get("id") if data else None
        if _is_duplicate_webhook("stripe", event_id):
            return success_response(data={"status": "duplicate"})

        result = WebhookService.process_stripe_webhook(data)

        if vault:
            PaymentLog.log_action(
                vault_id=vault.id,
                action="stripe_webhook_received",
                description=f"Event type: {data.get('type') if data else None}",
                level="info",
                ip_address=request.remote_addr,
                user_agent=request.headers.get("User-Agent"),
            )

        return success_response(data=result, status_code=200 if result.get("success") else 400)

    except Exception:
        logger.exception("Stripe webhook failed")
        return error_response(message="Webhook processing failed", status_code=500)


@payment_vault_bp.route("/health", methods=["GET"])
@owner_only
def health_check():
    """فحص صحة النظام — للمالك فقط"""
    from services.health_service import HealthCheckService

    result = HealthCheckService.run_full_health_check()
    status_code = 200 if result["overall_status"] == "healthy" else 503

    return success_response(data=result, status_code=status_code)


@payment_vault_bp.route("/metrics", methods=["GET"])
@owner_only
def system_metrics():
    """مقاييس النظام (للمالك فقط)"""
    from services.health_service import HealthCheckService

    metrics = HealthCheckService.get_system_metrics()
    return success_response(data=metrics)


# ==================== API v2 - Enhanced API with Versioning ====================


@payment_vault_bp.route("/api/v2/purchases", methods=["GET"])
@owner_only
@limiter.limit("60 per minute")
def api_v2_purchases():
    """API v2 للمشتريات - محسن مع Filtering & Pagination"""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    status = request.args.get("status", "")
    package_id = request.args.get("package_id", type=int)
    search = request.args.get("search", "")
    sort_by = request.args.get("sort_by", "created_at")
    order = request.args.get("order", "desc")

    pagination = VaultQueryService.purchases_paginated_v2(
        page=page,
        per_page=per_page,
        status=status,
        package_id=package_id,
        search=search,
        sort_by=sort_by,
        order=order,
    )

    return paginated_response(
        items=[p.to_dict() for p in pagination.items],
        page=pagination.page,
        per_page=pagination.per_page,
        total=pagination.total,
        meta={
            "version": "2.0",
            "filters_applied": {
                "status": status,
                "package_id": package_id,
                "search": search,
            },
        },
    )


@payment_vault_bp.route("/api/v2/donations", methods=["GET"])
@owner_only
@limiter.limit("60 per minute")
def api_v2_donations():
    """API v2 للتبرعات - محسن مع Filtering & Pagination"""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    status = request.args.get("status", "")
    search = request.args.get("search", "")

    tid = None
    pagination = VaultQueryService.donations_paginated_v2(tid, page, per_page, status=status, search=search)

    # Convert to dict
    donations_data = []
    for donation in pagination.items:
        donations_data.append(
            {
                "id": donation.id,
                "donor_name": donation.donor_name,
                "donor_email": donation.donor_email,
                "amount_usd": float(donation.amount_usd or 0),
                "payment_method": donation.payment_method,
                "status": donation.status,
                "created_at": (donation.created_at.isoformat() if donation.created_at else None),
            }
        )

    return paginated_response(
        items=donations_data,
        page=pagination.page,
        per_page=pagination.per_page,
        total=pagination.total,
        meta={"version": "2.0"},
    )


@payment_vault_bp.route("/api/v2/stats", methods=["GET"])
@owner_only
@limiter.limit("60 per minute")
def api_v2_stats():
    """API v2 للإحصائيات - شاملة ومحسنة"""
    from services.analytics_service import AnalyticsService
    from services.notification_service import SecurityService

    daily_stats = AnalyticsService.get_daily_stats()
    revenue_data = AnalyticsService.get_revenue_by_period(months=6)
    payment_methods = AnalyticsService.get_payment_method_stats()
    customer_behavior = AnalyticsService.get_customer_behavior()
    package_performance = AnalyticsService.get_package_performance()
    security_status = SecurityService.get_security_status()

    return success_response(
        data={
            "daily": daily_stats,
            "revenue_trend": revenue_data,
            "payment_methods": payment_methods,
            "customers": customer_behavior,
            "packages": package_performance,
            "security": security_status,
        },
        meta={"version": "2.0", "generated_at": datetime.now(UTC).isoformat()},
    )
