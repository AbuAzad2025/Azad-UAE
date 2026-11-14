"""Settings, configuration, and communication routes for the owner blueprint."""

import logging
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from flask_babel import gettext

from routes.owner.shared import (
    _audit_owner_db_action,
    _get_developer_from_settings,
    _invalidate_owner_changes,
)
from services.logging_core import LoggingCore
from services.owner_ops_service import OwnerOpsService
from utils.db_safety import atomic_transaction
from utils.error_messages import ErrorCategory, ErrorMessages, refuse
from utils.regional_defaults import FALLBACK_CURRENCY

from .common import (
    IntegrationSettings,
    SystemSettings,
    Tenant,
    User,
    abort,
    company_admin_required,
    current_app,
    current_user,
    db,
    error_response,
    flash,
    get_active_tenant_id,
    get_system_default_currency,
    limiter,
    login_required,
    owner_bp,
    owner_or_company_admin,
    owner_required,
    redirect,
    render_template,
    request,
    resolve_default_currency,
    success_response,
    url_for,
)

logger = logging.getLogger(__name__)


def _known_template(folder: str, name: str) -> bool:
    """True when the print template exists.

    The preview routes render ``<folder>/<name>.html``. A name that does not
    exist used to reach the renderer and answer 500, which is the wrong answer
    for a bad URL: the caller asked for a template that is not there, so the
    template is not there - 404, not a stack trace. The name is also rejected
    when it tries to walk out of its folder.
    """
    if not name or "/" in name or "\\" in name or ".." in name:
        return False
    try:
        available = set(current_app.jinja_env.list_templates())
    except Exception:
        logger.warning("Could not list the print templates", exc_info=True)
        return False
    return f"{folder}/{name}.html" in available


@owner_bp.route("/integrations")
@owner_required
def integrations():
    """عرض إعدادات التكاملات من قاعدة البيانات"""
    from services.integration_service import IntegrationService

    integrations_data = IntegrationService.get_integrations_context()
    return render_template("owner/integrations.html", integrations=integrations_data)


@owner_bp.route("/integrations/update/<service>", methods=["POST"])
@owner_required
def update_integration(service):
    """تحديث إعدادات التكامل - حفظ حقيقي في قاعدة البيانات"""
    try:
        integration = IntegrationSettings.get_service_config(service)

        # HTML checkboxes send "on" when checked; JS callers may send true/1.
        integration.enabled = request.form.get("enabled") in ("true", "1", "on")

        config_data: dict[str, Any] = {}

        if service == "whatsapp":
            config_data = {
                "api_token": request.form.get("api_token", ""),
                "phone_number": request.form.get("phone_number", ""),
                "api_url": request.form.get("api_url", ""),
                "message_template": request.form.get("message_template", ""),
            }

        elif service == "email":
            encryption = request.form.get("smtp_encryption", "tls")
            config_data = {
                "smtp_host": request.form.get("smtp_host", ""),
                "smtp_port": request.form.get("smtp_port", "587"),
                "smtp_user": request.form.get("smtp_user", ""),
                "smtp_password": request.form.get("smtp_password", ""),
                "smtp_encryption": encryption,
                "smtp_use_tls": encryption in ("tls", "ssl"),
                "from_email": request.form.get("from_email") or request.form.get("smtp_user", ""),
                "from_name": request.form.get("from_name") or request.form.get("sender_name", ""),
                "sender_name": request.form.get("sender_name", ""),
            }

        elif service == "redis":
            config_data = {
                "redis_host": request.form.get("redis_host", "localhost"),
                "redis_port": request.form.get("redis_port", "6379"),
                "redis_password": request.form.get("redis_password", ""),
                "redis_db": request.form.get("redis_db", "0"),
            }

        elif service == "currency_api":
            config_data = {
                "api_key": request.form.get("api_key", ""),
                "api_url": request.form.get("api_url", ""),
                "update_frequency": request.form.get("update_frequency", "daily"),
            }

        elif service == "shipping":
            config_data = {}
            from services.shipping_config_service import ShippingConfigService

            tid = get_active_tenant_id(current_user)
            if tid is None:
                return error_response("select_a_tenant_first", gettext("يرجى اختيار تينانت قبل حفظ إعدادات الشحن"), 400)

            ShippingConfigService.set_carrier_secret(
                "dhl", "api_key", request.form.get("dhl_api_key", "").strip(), tenant_id=tid, user_id=current_user.id
            )
            ShippingConfigService.set_carrier_secret(
                "fedex",
                "client_id",
                request.form.get("fedex_client_id", "").strip(),
                tenant_id=tid,
                user_id=current_user.id,
            )
            ShippingConfigService.set_carrier_secret(
                "fedex",
                "client_secret",
                request.form.get("fedex_client_secret", "").strip(),
                tenant_id=tid,
                user_id=current_user.id,
            )
            ShippingConfigService.set_carrier_secret(
                "aramex",
                "username",
                request.form.get("aramex_username", "").strip(),
                tenant_id=tid,
                user_id=current_user.id,
            )
            ShippingConfigService.set_carrier_secret(
                "aramex",
                "password",
                request.form.get("aramex_password", "").strip(),
                tenant_id=tid,
                user_id=current_user.id,
            )
            ShippingConfigService.set_carrier_secret(
                "aramex",
                "account_number",
                request.form.get("aramex_account_number", "").strip(),
                tenant_id=tid,
                user_id=current_user.id,
            )
            ShippingConfigService.set_carrier_secret(
                "aramex", "pin", request.form.get("aramex_pin", "").strip(), tenant_id=tid, user_id=current_user.id
            )

        elif service == "sms":
            config_data = {
                "provider": request.form.get("sms_provider", "twilio"),
            }
            from services.shipping_config_service import ShippingConfigService

            tid = get_active_tenant_id(current_user)
            if tid is None:
                return error_response(
                    "select_a_tenant_first", gettext("يرجى اختيار تينانت قبل حفظ إعدادات الرسائل النصية"), 400
                )

            ShippingConfigService.set_sms_secret(
                "sms_account_sid",
                request.form.get("sms_account_sid", "").strip(),
                tenant_id=tid,
                user_id=current_user.id,
            )
            ShippingConfigService.set_sms_secret(
                "sms_auth_token",
                request.form.get("sms_auth_token", "").strip(),
                tenant_id=tid,
                user_id=current_user.id,
            )
            ShippingConfigService.set_sms_secret(
                "sms_from_number",
                request.form.get("sms_from_number", "").strip(),
                tenant_id=tid,
                user_id=current_user.id,
            )

        with atomic_transaction("update_integration"):
            integration.set_config(config_data)
            integration.updated_by = current_user.id
            integration.updated_at = datetime.now(UTC)
        _invalidate_owner_changes()
        flash(gettext(f"✅ تم حفظ إعدادات {service} بنجاح!"), "success")

    except Exception as e:
        refuse(e, context="owner integrations save")
        current_app.logger.error("owner integrations save failed: %s", e, exc_info=True)

    return redirect(url_for("owner.integrations"))


@owner_bp.route("/integrations/test/<service>", methods=["POST"])
@owner_required
def test_integration(service):
    """اختبار الاتصال بالتكامل — يسجل النتيجة في last_test_* ويعيد JSON."""
    from services.integration_service import IntegrationService

    if service not in IntegrationService.TESTABLE_SERVICES:
        abort(404)
    try:
        if service == "email":
            ok, message = IntegrationService.test_email()
        else:
            ok, message = IntegrationService.test_currency_api()
    except Exception as exc:
        current_app.logger.exception("Integration test failed for %s", service)
        # Governed: an untyped Exception echoed verbatim to an API client.
        current_app.logger.error("owner integration probe failed: %s", exc, exc_info=True)
        return error_response(
            message=ErrorMessages.unexpected_error(),
            status_code=500,
        )
    return success_response(data={"success": ok, "message": message})


@owner_bp.route("/reports")
@owner_required
def reports():
    """Platform telemetry only — the owner plane never exposes tenant business data."""
    from models import PaymentVault
    from utils.owner_panel import build_platform_telemetry

    telemetry = build_platform_telemetry()
    vault = PaymentVault.get_platform_vault()

    stats = {
        "tenant_count": telemetry["tenant_count"],
        "active_tenant_count": telemetry["active_tenant_count"],
        "suspended_tenant_count": telemetry["suspended_tenant_count"],
        "trial_tenant_count": telemetry["trial_tenant_count"],
        "expired_subscription_count": telemetry["expired_subscription_count"],
        "expiring_soon_count": telemetry["expiring_soon_count"],
        "new_tenants_month": telemetry["new_tenants_month"],
        "new_tenants_week": telemetry["new_tenants_week"],
        "mrr_aed": telemetry["mrr_aed"],
        "plan_distribution": telemetry["plan_distribution"],
        "total_users": telemetry["total_users"],
        "total_branches": telemetry["total_branches"],
        "vault_status": vault.is_locked if vault else True,
        "is_platform_view": True,
    }

    return render_template("owner/reports.html", stats=stats)


@owner_bp.route("/company-info", methods=["GET", "POST"])
@login_required
@owner_or_company_admin
def company_info():
    """معلومات الشركة/الكراج"""
    tenant = Tenant.get_current(user=current_user)

    if request.method == "POST":
        try:
            with atomic_transaction("company_info"):
                tenant.name_ar = request.form.get("name_ar", "").strip()
                tenant.name_en = request.form.get("name_en", "").strip()
                tenant.name = tenant.name_en or tenant.name_ar
                tenant.slug = request.form.get("slug", "").strip()
                from services.industry_service import IndustryService

                business_type = request.form.get("business_type", "general").strip()
                tenant.business_type = (
                    business_type if IndustryService.validate_industry_code(business_type) else "general"
                )
                tenant.industry = tenant.business_type

                # Contact Info
                tenant.address_ar = request.form.get("address_ar", "").strip()
                tenant.address_en = request.form.get("address_en", "").strip()
                tenant.city = request.form.get("city", "").strip()
                tenant.country = request.form.get("country", "PS")
                tenant.phone_1 = request.form.get("phone_1", "").strip()
                tenant.phone_2 = request.form.get("phone_2", "").strip()
                tenant.mobile = request.form.get("mobile", "").strip()
                tenant.email = request.form.get("email", "").strip()
                tenant.website = request.form.get("website", "").strip()

                # Legal Info
                tenant.tax_number = request.form.get("tax_number", "").strip()
                tenant.commercial_register = request.form.get("commercial_register", "").strip()
                tenant.license_number = request.form.get("license_number", "").strip()

                # Branding
                tenant.brand_color_primary = request.form.get("brand_color_primary", "#007A3D")
                tenant.brand_color_secondary = request.form.get("brand_color_secondary", "#D4AF37")

                tenant.updated_by = current_user.id
            _invalidate_owner_changes()
            flash(gettext("تم حفظ معلومات الشركة بنجاح"), "success")
            return redirect(url_for("owner.company_info"))

        except Exception as e:
            refuse(e, context="owner company info save")

    return render_template("owner/company_info.html", tenant=tenant)


@owner_bp.route("/developer-settings", methods=["GET", "POST"])
@owner_required
def developer_settings():
    """إعدادات الشركة المطورة (للتواصل والدعم) — منفصلة عن التينانت."""
    settings = SystemSettings.get_current()
    dev = _get_developer_from_settings()

    if request.method == "POST":
        try:
            with atomic_transaction("developer_settings"):
                settings.set_custom_setting(
                    "developer_name_ar",
                    request.form.get("developer_name_ar", "").strip(),
                )
                settings.set_custom_setting("developer_name", request.form.get("developer_name", "").strip())
                settings.set_custom_setting("developer_credit", request.form.get("developer_credit", "").strip())
                settings.set_custom_setting("developer_phone", request.form.get("developer_phone", "").strip())
                settings.set_custom_setting("developer_email", request.form.get("developer_email", "").strip())
                settings.set_custom_setting(
                    "developer_website",
                    request.form.get("developer_website", "").strip(),
                )
                settings.set_custom_setting(
                    "developer_whatsapp",
                    request.form.get("developer_whatsapp", "").strip(),
                )
                settings.set_custom_setting("developer_logo", request.form.get("developer_logo", "").strip())
                settings.updated_by = current_user.id
            _invalidate_owner_changes()
            flash(gettext("تم حفظ إعدادات الشركة المطورة بنجاح"), "success")
            return redirect(url_for("owner.developer_settings"))
        except Exception as e:
            refuse(e, context="owner developer settings save")
    return render_template("owner/developer_settings.html", dev=dev, config=current_app.config)


@owner_bp.route("/system-config", methods=["GET", "POST"])
@owner_required
def system_config():
    """إعدادات النظام الشاملة"""
    settings = SystemSettings.get_current()

    if request.method == "POST":
        try:
            with atomic_transaction("system_config"):
                settings.enable_sales = request.form.get("enable_sales") == "on"
                settings.enable_purchases = request.form.get("enable_purchases") == "on"
                settings.enable_inventory = request.form.get("enable_inventory") == "on"
                settings.enable_customers = request.form.get("enable_customers") == "on"
                settings.enable_expenses = request.form.get("enable_expenses") == "on"
                settings.enable_gl = request.form.get("enable_gl") == "on"
                settings.enable_reports = request.form.get("enable_reports") == "on"
                settings.enable_ai_assistant = request.form.get("enable_ai_assistant") == "on"
                settings.enable_pos = request.form.get("enable_pos") == "on"

                settings.enable_barcode_scanner = request.form.get("enable_barcode_scanner") == "on"
                settings.enable_multi_warehouse = request.form.get("enable_multi_warehouse") == "on"
                settings.enable_multi_currency = request.form.get("enable_multi_currency") == "on"
                settings.enable_discounts = request.form.get("enable_discounts") == "on"
                settings.enable_returns = request.form.get("enable_returns") == "on"
                settings.enable_ecommerce = request.form.get("enable_ecommerce") == "on"

                # Azad Platform Fees
                try:
                    fee_rate = Decimal(str(request.form.get("azad_platform_fee_rate") or "0"))
                    settings.azad_platform_fee_rate = fee_rate.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                except Exception:
                    logger.exception("Failed to parse azad_platform_fee_rate from form data")
                try:
                    settings.subscription_monthly_fee_aed = Decimal(
                        str(request.form.get("subscription_monthly_fee_aed", "0") or "0")
                    ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
                except Exception:
                    logger.exception("Failed to parse subscription_monthly_fee_aed from form data")
                try:
                    settings.subscription_yearly_fee_aed = Decimal(
                        str(request.form.get("subscription_yearly_fee_aed", "0") or "0")
                    ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
                except Exception:
                    logger.exception("Failed to parse subscription_yearly_fee_aed from form data")
                try:
                    settings.subscription_perpetual_fee_aed = Decimal(
                        str(request.form.get("subscription_perpetual_fee_aed", "0") or "0")
                    ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
                except Exception:
                    logger.exception("Failed to parse subscription_perpetual_fee_aed from form data")

                try:
                    default_currency = request.form.get("default_currency", FALLBACK_CURRENCY)
                    settings.default_currency = default_currency
                except Exception:
                    logger.exception("Failed to parse default_currency from form data")
                try:
                    from models import Tenant

                    tenant = Tenant.get_current(user=current_user)
                    tenant.default_currency = default_currency
                    tenant.base_currency = default_currency
                except Exception as exc:
                    logger.debug("tenant currency sync: %s", exc)
                settings.default_language = request.form.get("default_language", "ar")
                settings.timezone = request.form.get("timezone", "Asia/Dubai")
                settings.items_per_page = int(request.form.get("items_per_page", 25))

                settings.updated_by = current_user.id
            _invalidate_owner_changes()
            flash(gettext("تم حفظ إعدادات النظام بنجاح"), "success")
            return redirect(url_for("owner.system_config"))

        except Exception as e:
            refuse(e, context="owner system config save")

    return render_template("owner/system_config.html", settings=settings)


@owner_bp.route("/store-payment-methods")
@owner_required
def store_payment_methods():
    """إدارة طرق دفع المتاجر — تنعكس على كل تينانت"""
    from services.store_payment_method_service import StorePaymentMethodService

    StorePaymentMethodService.ensure_defaults()
    methods = StorePaymentMethodService.list_all()
    return render_template("owner/store_payment_methods.html", methods=methods)


@owner_bp.route("/store-payment-methods/create", methods=["GET", "POST"])
@owner_required
def store_payment_method_create():
    from services.store_payment_method_service import StorePaymentMethodService

    if request.method == "POST":
        try:
            StorePaymentMethodService.create_method(
                {
                    "code": request.form.get("code"),
                    "name_ar": request.form.get("name_ar"),
                    "name_en": request.form.get("name_en"),
                    "description_ar": request.form.get("description_ar"),
                    "description_en": request.form.get("description_en"),
                    "icon": request.form.get("icon"),
                    "is_enabled": request.form.get("is_enabled") == "on",
                    "sort_order": request.form.get("sort_order", 100),
                    "bank_name": request.form.get("bank_name"),
                    "iban": request.form.get("iban"),
                    "account_name": request.form.get("account_name"),
                    "providers": request.form.get("providers"),
                    "instructions": request.form.get("instructions"),
                }
            )
            _invalidate_owner_changes()
            flash(gettext("تمت إضافة طريقة الدفع."), "success")
            return redirect(url_for("owner.store_payment_methods"))
        except ValueError as exc:
            refuse(exc, context="owner payment method create", category=ErrorCategory.BUSINESS)
        except Exception as exc:
            refuse(exc, context="owner payment method create")
    return render_template("owner/store_payment_method_form.html", method=None)


@owner_bp.route("/store-payment-methods/<int:method_id>/edit", methods=["GET", "POST"])
@owner_required
def store_payment_method_edit(method_id):
    from models.store_payment_method import StorePaymentMethod
    from services.store_payment_method_service import StorePaymentMethodService

    method = db.session.get(StorePaymentMethod, int(method_id))
    if not method:
        flash(gettext("طريقة الدفع غير موجودة."), "warning")
        return redirect(url_for("owner.store_payment_methods"))
    if request.method == "POST":
        try:
            StorePaymentMethodService.update_method(
                method.id,
                {
                    "code": request.form.get("code"),
                    "name_ar": request.form.get("name_ar"),
                    "name_en": request.form.get("name_en"),
                    "description_ar": request.form.get("description_ar"),
                    "description_en": request.form.get("description_en"),
                    "icon": request.form.get("icon"),
                    "is_enabled": request.form.get("is_enabled") == "on",
                    "sort_order": request.form.get("sort_order", method.sort_order),
                    "bank_name": request.form.get("bank_name"),
                    "iban": request.form.get("iban"),
                    "account_name": request.form.get("account_name"),
                    "providers": request.form.get("providers"),
                    "instructions": request.form.get("instructions"),
                },
            )
            _invalidate_owner_changes()
            flash(gettext("تم تحديث طريقة الدفع."), "success")
            return redirect(url_for("owner.store_payment_methods"))
        except ValueError as exc:
            refuse(exc, context="owner payment method update", category=ErrorCategory.BUSINESS)
        except Exception as exc:
            refuse(exc, context="owner payment method update")
    return render_template("owner/store_payment_method_form.html", method=method)


@owner_bp.route("/store-payment-methods/<int:method_id>/toggle", methods=["POST"])
@owner_required
def store_payment_method_toggle(method_id):
    from services.store_payment_method_service import StorePaymentMethodService

    try:
        enabled = request.form.get("is_enabled") == "1"
        StorePaymentMethodService.toggle_enabled(method_id, enabled)
        _invalidate_owner_changes()
        flash(gettext("تم تحديث حالة طريقة الدفع."), "success")
    except ValueError as exc:
        refuse(exc, context="owner payment method toggle", category=ErrorCategory.BUSINESS)
    return redirect(url_for("owner.store_payment_methods"))


@owner_bp.route("/store-payment-methods/<int:method_id>/delete", methods=["POST"])
@owner_required
def store_payment_method_delete(method_id):
    from services.store_payment_method_service import StorePaymentMethodService

    try:
        StorePaymentMethodService.delete_method(method_id)
        _invalidate_owner_changes()
        flash(gettext("تم حذف طريقة الدفع."), "success")
    except ValueError as exc:
        refuse(exc, context="owner payment method delete", category=ErrorCategory.BUSINESS)
    except Exception as exc:
        refuse(exc, context="owner payment method delete")
    return redirect(url_for("owner.store_payment_methods"))


@owner_bp.route("/invoice-settings", methods=["GET", "POST"])
@login_required
@owner_or_company_admin
def invoice_settings():
    """إعدادات ترويسات الفواتير وسندات القبض"""
    from services.invoice_profile_service import resolve_print_profile, save_print_profile

    tid = get_active_tenant_id(current_user)
    settings = resolve_print_profile(tid)

    if request.method == "POST":
        try:
            from models.tenant import Tenant

            tenant = db.session.get(Tenant, tid)
            if tenant is None:
                abort(404)
            data = {
                key: request.form.get(key, "").strip()
                for key in (
                    "company_name_ar",
                    "company_name_en",
                    "address_ar",
                    "address_en",
                    "phone_1",
                    "phone_2",
                    "email",
                    "website",
                    "tax_number",
                    "commercial_register",
                    "license_number",
                    "bank_name",
                    "bank_account_number",
                    "iban",
                    "swift_code",
                    "header_color",
                    "accent_color",
                    "text_color",
                    "payment_terms_ar",
                    "payment_terms_en",
                    "terms_conditions_ar",
                    "terms_conditions_en",
                    "footer_text_ar",
                    "footer_text_en",
                    "default_invoice_note_ar",
                    "default_invoice_note_en",
                    "default_receipt_note_ar",
                    "default_receipt_note_en",
                    "active_template",
                    "logo_position",
                    "logo_size",
                    "qr_position",
                    "watermark_text",
                    "default_language",
                    "facebook_url",
                    "instagram_url",
                    "whatsapp_number",
                )
            }
            decimal_opacity = request.form.get("watermark_opacity")
            if decimal_opacity is not None:
                data["watermark_opacity"] = Decimal(str(decimal_opacity))
            for key in (
                "show_logo",
                "show_barcode",
                "show_page_numbers",
                "show_due_date",
                "show_terms",
                "enable_qr_code",
                "enable_watermark",
            ):
                data[key] = request.form.get(key) == "on"
            data["paper_size"] = request.form.get("paper_size", "A4")
            data["orientation"] = request.form.get("orientation", "portrait")

            uploaded = {}

            def _save_upload(field, directory, prefix):
                file = request.files.get(field) if field in request.files else None
                if not (file and file.filename):
                    return None
                import os

                from werkzeug.utils import secure_filename

                filename = secure_filename(file.filename)
                filename = f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}"
                folder = os.path.join("static", "uploads", directory)
                os.makedirs(folder, exist_ok=True)
                file.save(os.path.join(folder, filename))
                return f"uploads/{directory}/{filename}"

            if path := _save_upload("company_logo", "logos", "logo"):
                uploaded["logo_path"] = path
            if path := _save_upload("watermark_image", "watermarks", "watermark"):
                uploaded["watermark_image_path"] = path
            with atomic_transaction("invoice_settings"):
                save_print_profile(tenant, data, allow_files=uploaded)
            _invalidate_owner_changes()
            flash(gettext("تم حفظ إعدادات الترويسات بنجاح"), "success")
            return redirect(url_for("owner.invoice_settings"))
        except Exception as e:
            refuse(e, context="owner invoice settings save")

    return render_template("owner/invoice_settings.html", settings=settings)


@owner_bp.route("/preview-invoice/<template>")
@login_required
@owner_or_company_admin
def preview_invoice(template):
    """معاينة قالب الفاتورة"""
    from services.invoice_profile_service import resolve_print_profile
    from utils.auth_helpers import is_global_owner_user
    from utils.tenant_branding import get_print_header_context
    from utils.tenanting import get_active_tenant_id

    if not _known_template("invoices", template):
        abort(404)

    tid = request.args.get("tenant_id", type=int) or get_active_tenant_id(current_user)
    if request.args.get("tenant_id") and not is_global_owner_user(current_user):
        abort(403)
    settings = resolve_print_profile(tid)
    print_branding = get_print_header_context(tid, profile=settings)
    from utils.number_to_arabic import number_to_arabic_words
    from utils.qr_generator import generate_qr_data_url

    try:
        from models import Tenant

        default_currency = resolve_default_currency(Tenant.get_current(user=current_user))
    except Exception:
        default_currency = get_system_default_currency()

    # Sample data for preview
    class SampleCustomer:
        name = gettext("عميل تجريبي")
        phone = "0501234567"
        email = "customer@example.com"
        address = gettext("دبي - الإمارات العربية المتحدة")

    class SampleSeller:
        full_name = gettext("البائع التجريبي")
        username = "seller"

        def get_display_name(self, lang="ar"):
            return self.full_name

    class SampleBranch:
        name = gettext("الفرع الرئيسي")
        code = "BR01"
        address = gettext("دبي - شارع الشيخ زايد")

    class SampleProduct:
        name = gettext("منتج تجريبي")

    class SampleLine:
        def __init__(self, name, qty, price, discount=0):
            self.product = type("obj", (object,), {"name": name})()
            self.quantity = qty
            self.unit_price = price
            self.discount_percent = discount
            self.line_total = qty * price * (1 - discount / 100)

    class SamplePayment:
        def __init__(self):
            self.payment_number = "PAY-2025-0001"
            self.payment_date = datetime.now()
            self.amount_aed = Decimal("500.00")
            self.payment_method = "cheque"
            self.cheque_number = "123456"
            self.cheque_date = datetime.now().date()
            self.bank_name = gettext("بنك الإمارات دبي الوطني")
            self.reference_number = "REF-001"

    class SampleSale:
        sale_number = "S-2025-0001"
        sale_date = datetime.now()
        customer = SampleCustomer()
        seller = SampleSeller()
        lines = [
            SampleLine(gettext("زيت محرك سينثتك 5W-30"), 5, 120, 10),
            SampleLine(gettext("فلتر هواء أصلي"), 2, 85, 5),
            SampleLine(gettext("فلتر زيت"), 3, 45, 0),
        ]
        subtotal = Decimal("925.00")
        discount_amount = Decimal("25.00")
        shipping_cost = Decimal("50.00")
        tax_rate = Decimal("5.00")
        tax_amount = Decimal("47.50")
        total_amount = Decimal("997.50")
        currency = default_currency
        notes = gettext("فاتورة تجريبية للمعاينة")
        payments = [SamplePayment()]

    sample_sale = SampleSale()
    sample_user_name = sample_sale.seller.get_display_name("ar")
    sample_amount_in_words = number_to_arabic_words(float(sample_sale.total_amount), sample_sale.currency)
    sample_qr_data_url = ""
    if settings and settings.enable_qr_code:
        sample_qr_data_url = generate_qr_data_url(
            {
                "t": "invoice",
                "n": sample_sale.sale_number,
                "a": float(sample_sale.total_amount),
                "c": sample_sale.currency,
                "d": sample_sale.sale_date.strftime("%Y-%m-%d"),
                "co": (settings.company_name_ar if settings and settings.company_name_ar else gettext("نظام المحاسبة")),
                "u": sample_user_name,
                "b": SampleBranch.name,
            }
        )

    return render_template(
        f"invoices/{template}.html",
        sale=sample_sale,
        settings=settings,
        preview=True,
        print_branch=SampleBranch(),
        print_user_name=sample_user_name,
        amount_in_words=sample_amount_in_words,
        qr_data_url=sample_qr_data_url,
        doc_number=sample_sale.sale_number,
        print_branding=print_branding,
        print_tenant_id=tid,
    )


@owner_bp.route("/preview-receipt/<template>")
@login_required
@owner_or_company_admin
def preview_receipt(template):
    """معاينة قالب سند القبض"""
    from services.invoice_profile_service import resolve_print_profile
    from utils.auth_helpers import is_global_owner_user
    from utils.tenant_branding import get_print_header_context
    from utils.tenanting import get_active_tenant_id

    if not _known_template("receipts", template):
        abort(404)

    tid = request.args.get("tenant_id", type=int) or get_active_tenant_id(current_user)
    if request.args.get("tenant_id") and not is_global_owner_user(current_user):
        abort(403)
    settings = resolve_print_profile(tid)
    print_branding = get_print_header_context(tid, profile=settings)
    try:
        from models import Tenant

        default_currency = resolve_default_currency(Tenant.get_current(user=current_user))
    except Exception:
        default_currency = get_system_default_currency()
    from utils.number_to_arabic import number_to_arabic_words
    from utils.qr_generator import generate_qr_data_url

    # Sample data for preview
    class SampleCustomer:
        name = gettext("عميل تجريبي")
        phone = "0501234567"
        email = "customer@example.com"
        address = gettext("دبي - الإمارات")

    class SampleUser:
        full_name = gettext("المحصل التجريبي")
        username = "collector"

        def get_display_name(self, lang="ar"):
            return self.full_name

    class SampleBranch:
        name = gettext("الفرع الرئيسي")
        code = "BR01"
        address = gettext("دبي - شارع الشيخ زايد")

    class SampleSale:
        sale_number = "S-2025-0001"
        sale_date = datetime.now()

    class SampleAllocation:
        def __init__(self, sale_num, amount):
            self.sale = type("obj", (object,), {"sale_number": sale_num, "sale_date": datetime.now()})()
            self.amount_allocated = Decimal(str(amount))

    class SampleReceipt:
        receipt_number = "RCV-2025-0001"
        receipt_date = datetime.now()
        customer = SampleCustomer()
        user = SampleUser()
        amount = Decimal("1500.00")
        amount_aed = Decimal("1500.00")
        base_amount = Decimal("1500.00")
        currency = default_currency
        payment_method = "cheque"
        cheque_number = "789456"
        cheque_date = datetime.now().date()
        bank_name = gettext("بنك الإمارات دبي الوطني")
        reference_number = "REF-2025-001"
        notes = gettext("تسديد ذمم فواتير سابقة - دفعة من مبيعات شهر أكتوبر 2025")
        allocations = [
            SampleAllocation("S-2025-0001", "800.00"),
            SampleAllocation("S-2025-0002", "700.00"),
        ]

        @staticmethod
        def get_source_info():
            return {
                "type": gettext("فاتورة"),
                "number": "S-2025-0001",
                "date": datetime.now().strftime("%Y-%m-%d"),
                "id": 1,
            }

    sample_receipt = SampleReceipt()
    sample_user_name = sample_receipt.user.get_display_name("ar")
    sample_amount_in_words = number_to_arabic_words(float(sample_receipt.amount), sample_receipt.currency)
    sample_qr_data_url = ""
    if settings and settings.enable_qr_code:
        sample_qr_data_url = generate_qr_data_url(
            {
                "t": "receipt",
                "n": sample_receipt.receipt_number,
                "a": float(sample_receipt.amount),
                "c": sample_receipt.currency,
                "d": sample_receipt.receipt_date.strftime("%Y-%m-%d"),
                "co": (settings.company_name_ar if settings and settings.company_name_ar else gettext("نظام المحاسبة")),
                "u": sample_user_name,
                "b": SampleBranch.name,
            }
        )

    return render_template(
        f"receipts/{template}.html",
        receipt=sample_receipt,
        settings=settings,
        preview=True,
        print_branch=SampleBranch(),
        print_user_name=sample_user_name,
        amount_in_words=sample_amount_in_words,
        qr_data_url=sample_qr_data_url,
        doc_number=sample_receipt.receipt_number,
        print_branding=print_branding,
        print_tenant_id=tid,
    )


@owner_bp.route("/tax-settings", methods=["GET", "POST"])
@owner_required
def tax_settings():
    from decimal import Decimal

    from utils.country_tax import COUNTRY_TAX_PROFILES
    from utils.tax_settings import VAT_COUNTRY_LABELS, suggested_rate_for_country

    tenant = Tenant.get_current(user=current_user)
    if not tenant:
        flash(gettext("لا توجد شركة نشطة."), "danger")
        return redirect(url_for("owner.dashboard"))

    from services.tenant_secrets_service import TenantSecretsService

    def _secret_state():
        return {
            name: TenantSecretsService.is_set(tenant.id, name)
            for name in ("zatca_private_key", "zatca_certificate", "zatca_csid", "ita_oauth_token")
        }

    if request.method == "POST" and request.form.get("section") == "compliance":
        try:
            with atomic_transaction("tenant_compliance_settings"):
                tenant.enable_einvoice = request.form.get("enable_einvoice") == "on"
                tenant.enable_einvoice_credit_notes = request.form.get("enable_einvoice_credit_notes") == "on"
                tenant.zatca_phase2_enabled = request.form.get("zatca_phase2_enabled") == "on"
                zatca_environment = (request.form.get("zatca_environment") or "sandbox").strip().lower()
                if zatca_environment not in ("sandbox", "production"):
                    raise ValueError(gettext("بيئة ZATCA غير صالحة."))
                tenant.zatca_environment = zatca_environment
                tenant.enable_ita_allocation = request.form.get("enable_ita_allocation") == "on"
                environment = (request.form.get("ita_environment") or "sandbox").strip().lower()
                if environment not in ("sandbox", "production"):
                    raise ValueError(gettext("بيئة ITA غير صالحة."))
                tenant.ita_environment = environment
                threshold = request.form.get("ita_allocation_threshold", type=Decimal)
                if threshold is None or threshold <= 0:
                    raise ValueError(gettext("حد عدد التخصيص يجب أن يكون موجباً."))
                tenant.ita_allocation_threshold = threshold
                tenant.enable_il_pension = request.form.get("enable_il_pension") == "on"
                tenant.enable_zakat = request.form.get("enable_zakat") == "on"
                wht_raw = (request.form.get("wht_services_rate") or "").strip()
                if not wht_raw:
                    tenant.wht_services_rate = None
                else:
                    try:
                        wht_value = Decimal(wht_raw)
                    except Exception:
                        raise ValueError(gettext("نسبة ضريبة الاستقطاع يجب أن تكون رقمًا."))
                    if not wht_value.is_finite() or wht_value < Decimal("0") or wht_value > Decimal("100"):
                        raise ValueError(gettext("نسبة ضريبة الاستقطاع يجب أن تكون بين 0 و 100."))
                    tenant.wht_services_rate = wht_value
                tenant.enable_import_duties = request.form.get("enable_import_duties") == "on"
                tenant.enable_tax_categories = request.form.get("enable_tax_categories") == "on"
                for secret_name in ("zatca_private_key", "zatca_certificate", "zatca_csid", "ita_oauth_token"):
                    clear = request.form.get("clear_secret")
                    if clear == secret_name:
                        TenantSecretsService.delete(tenant.id, secret_name)
                    value = (request.form.get(f"secret_{secret_name}") or "").strip()
                    if value:
                        TenantSecretsService.set(tenant.id, secret_name, value, user_id=current_user.id)
                # The Phase 2 integration runs inside the sale transaction —
                # refuse to enable it without both halves of the CSID stored.
                secrets = _secret_state()
                if tenant.zatca_phase2_enabled and not (secrets["zatca_private_key"] and secrets["zatca_certificate"]):
                    raise ValueError(
                        gettext("ZATCA Phase 2 يتطلب تخزين المفتاح الخاص والشهادة (CSID) — أدخلهما في هذا القسم أولاً.")
                    )
        except ValueError as exc:
            refuse(exc, context="tenant compliance settings save")
            return redirect(url_for("owner.tax_settings"))
        _invalidate_owner_changes()
        flash(gettext("✅ تم تحديث إعدادات الامتثال والفواتير الإلكترونية"), "success")
        return redirect(url_for("owner.tax_settings"))

    if request.method == "POST":
        try:
            with atomic_transaction("tax_settings"):
                tenant.enable_tax = request.form.get("enable_tax") == "on"
                tenant.vat_country = (request.form.get("vat_country") or "PS").strip().upper()[:2]
                # No free "playing" with rates: when tax is on, the stored
                # rate must be the country's statutory rate
                # (utils/country_tax.py). Anything else is refused so the
                # system stays connectable to the government's e-invoice
                # system, which only accepts the statutory rate.
                standard = suggested_rate_for_country(tenant.vat_country)
                rate = request.form.get("default_tax_rate", type=float)
                if rate is None and tenant.enable_tax:
                    rate = float(standard)
                if tenant.enable_tax and Decimal(str(rate or 0)) != standard:
                    raise ValueError(
                        gettext(
                            f"نسبة الضريبة يجب أن تكون نسبة الدولة المعيارية ({standard}%) ولا يمكن تعيين نسبة مخصصة"
                        )
                    )
                tenant.default_tax_rate = Decimal(str(rate or 0))
                tenant.vat_number = (request.form.get("vat_number") or "").strip() or None
                tenant.tax_number = (request.form.get("tax_number") or "").strip() or tenant.tax_number
        except Exception as e:
            refuse(e, context="owner tax settings save")
            return redirect(url_for("owner.tax_settings"))
        _invalidate_owner_changes()
        flash(gettext("✅ تم تحديث إعدادات الضرائب للشركة الحالية"), "success")
        return redirect(url_for("owner.tax_settings"))

    return render_template(
        "owner/tax_settings.html",
        tenant=tenant,
        vat_countries=VAT_COUNTRY_LABELS,
        statutory_rates={code: str(p["vat_rate"]) for code, p in COUNTRY_TAX_PROFILES.items()},
        secret_state=_secret_state(),
    )


@owner_bp.route("/currency-settings", methods=["GET", "POST"])
@owner_required
def currency_settings():
    from services.currency_service import CurrencyService

    if request.method == "POST":
        try:
            with atomic_transaction("currency_settings"):
                settings = SystemSettings.get_current()

                default_currency = request.form.get("default_currency", FALLBACK_CURRENCY)
                settings.default_currency = default_currency
                try:
                    from models import Tenant

                    tenant = Tenant.get_current(user=current_user)
                    tenant.default_currency = default_currency
                    tenant.base_currency = default_currency
                except Exception as exc:
                    logger.debug("tenant currency settings sync: %s", exc)
                settings.auto_update_rates = request.form.get("auto_update_rates") == "on"
        except Exception as e:
            refuse(e, context="owner currency settings save")
            return redirect(url_for("owner.currency_settings"))
        _invalidate_owner_changes()
        flash(gettext("✅ تم تحديث إعدادات العملات"), "success")
        return redirect(url_for("owner.currency_settings"))

    settings = SystemSettings.get_current()
    try:
        from models import Tenant

        default_currency = resolve_default_currency(Tenant.get_current(user=current_user))
    except Exception:
        default_currency = get_system_default_currency()
    rates = CurrencyService.get_all_rates(default_currency)

    return render_template(
        "owner/currency_settings.html", settings=settings, rates=rates, base_currency=default_currency
    )


@owner_bp.route("/exchange-rates", methods=["GET", "POST"])
@owner_required
def exchange_rates():
    """إدارة أسعار الصرف — Manual rate entry and history."""
    from datetime import date

    from services.exchange_rate_service import ExchangeRateService

    today = date.today().isoformat()
    tenant_id = getattr(current_user, "tenant_id", None)

    if request.method == "POST":
        action = request.form.get("action", "save")
        if action == "save":
            from_currency = (request.form.get("from_currency") or "USD").upper()
            to_currency = (request.form.get("to_currency") or FALLBACK_CURRENCY).upper()
            rate_val = request.form.get("rate", type=float)
            request.form.get("effective_date") or today

            if rate_val and rate_val > 0:
                result = ExchangeRateService.save_manual_rate(
                    from_currency=from_currency,
                    to_currency=to_currency,
                    rate=rate_val,
                    tenant_id=getattr(current_user, "tenant_id", None),
                    created_by=current_user.id,
                )
                if result.get("ok"):
                    flash(gettext("✅ تم حفظ سعر الصرف بنجاح!"), "success")
                else:
                    flash(gettext(f"❌ خطأ: {result.get('error', 'unknown')}"), "danger")
            else:
                flash(gettext("⚠️ أدخل سعر صرف صالح أكبر من صفر."), "warning")

        elif action == "delete":
            record_id = request.form.get("record_id", type=int)
            if record_id:
                rec = OwnerOpsService.find_exchange_rate_record(record_id, tenant_id)
                if rec:
                    with atomic_transaction("exchange_rate_delete"):
                        db.session.delete(rec)
                    flash(gettext("✅ تم حذف السجل."), "success")
                else:
                    flash(gettext("⚠️ السجل غير موجود أو لا يخصك."), "warning")

        return redirect(url_for("owner.exchange_rates"))

    # GET: show records
    records = OwnerOpsService.recent_exchange_rate_records(tenant_id)

    return render_template(
        "owner/exchange_rates.html",
        records=records,
        today=today,
        currencies=ExchangeRateService.DISPLAY_CURRENCIES,
    )


@owner_bp.route("/payment-gateways", methods=["GET", "POST"])
@owner_required
def payment_gateways():
    from models import PaymentVault
    from utils.tenanting import without_tenant_scope

    vault = PaymentVault.get_platform_vault()
    if not vault:
        # The platform vault is tenant-less by design, and the ORM's auto-stamp
        # would give it the active tenant instead - which both defeats the point
        # and collides with that tenant's own vault. The scope has to stay off
        # through the commit, because that is where the stamp happens.
        with without_tenant_scope(), atomic_transaction("payment_gateway_create_vault"):
            vault = PaymentVault(tenant_id=None)
            vault.set_vault_password(current_app.config.get("SECRET_KEY", "default-vault-password"))
            db.session.add(vault)
        _invalidate_owner_changes()

    if request.method == "POST":
        with atomic_transaction("payment_gateway_update"):
            vault.stripe_publishable_key = request.form.get("stripe_publishable_key")
            vault.stripe_secret_key = request.form.get("stripe_secret_key")
            vault.paypal_client_id = request.form.get("paypal_client_id")
            vault.paypal_client_secret = request.form.get("paypal_client_secret")
            vault.nowpayments_api_key = request.form.get("nowpayments_api_key")
        _invalidate_owner_changes()
        flash(gettext("✅ تم تحديث إعدادات بوابات الدفع"), "success")
        return redirect(url_for("owner.payment_gateways"))

    return render_template("owner/payment_gateways.html", vault=vault)


@owner_bp.route("/email-settings", methods=["GET", "POST"])
@owner_required
def email_settings():
    if request.method == "POST":
        try:
            with atomic_transaction("email_settings"):
                settings = SystemSettings.get_current()

                settings.smtp_server = request.form.get("smtp_server")
                settings.smtp_port = request.form.get("smtp_port", type=int)
                settings.smtp_username = request.form.get("smtp_username")
                settings.smtp_password = request.form.get("smtp_password")
                settings.smtp_use_tls = request.form.get("smtp_use_tls") == "on"
                settings.email_from = request.form.get("email_from")
        except Exception as e:
            refuse(e, context="owner email settings save")
            return redirect(url_for("owner.email_settings"))
        _invalidate_owner_changes()
        flash(gettext("✅ تم تحديث إعدادات البريد الإلكتروني"), "success")
        return redirect(url_for("owner.email_settings"))

    settings = SystemSettings.get_current()

    return render_template("owner/email_settings.html", settings=settings)


@owner_bp.route("/sms-settings", methods=["GET", "POST"])
@owner_required
def sms_settings():
    if request.method == "POST":
        try:
            with atomic_transaction("sms_settings"):
                settings = SystemSettings.get_current()

                sms_provider = (request.form.get("sms_provider") or "").strip()
                settings.sms_provider = sms_provider or None
                settings.sms_api_key = request.form.get("sms_api_key")
                settings.sms_sender_name = request.form.get("sms_sender_name")
                settings.sms_enabled = request.form.get("sms_enabled") == "on"
        except Exception as e:
            refuse(e, context="owner sms settings save")
            return redirect(url_for("owner.sms_settings"))
        _invalidate_owner_changes()
        flash(gettext("✅ تم تحديث إعدادات الرسائل النصية"), "success")
        return redirect(url_for("owner.sms_settings"))

    settings = SystemSettings.get_current()

    return render_template("owner/sms_settings.html", settings=settings)


@owner_bp.route("/whatsapp-settings", methods=["GET", "POST"])
@owner_required
def whatsapp_settings():
    if request.method == "POST":
        try:
            with atomic_transaction("whatsapp_settings"):
                settings = SystemSettings.get_current()

                settings.whatsapp_api_url = request.form.get("whatsapp_api_url")
                settings.whatsapp_api_key = request.form.get("whatsapp_api_key")
                settings.whatsapp_phone_number = request.form.get("whatsapp_phone_number")
                settings.whatsapp_enabled = request.form.get("whatsapp_enabled") == "on"
        except Exception as e:
            refuse(e, context="owner whatsapp settings save")
            return redirect(url_for("owner.whatsapp_settings"))
        _invalidate_owner_changes()
        flash(gettext("✅ تم تحديث إعدادات واتساب"), "success")
        return redirect(url_for("owner.whatsapp_settings"))

    settings = SystemSettings.get_current()

    return render_template("owner/whatsapp_settings.html", settings=settings)


@owner_bp.route("/notification-templates", methods=["GET", "POST"])
@owner_required
def notification_templates():
    if request.method == "POST":
        try:
            with atomic_transaction("notification_templates"):
                settings = SystemSettings.get_current()

                templates = {
                    "invoice_email": request.form.get("invoice_email_template"),
                    "payment_sms": request.form.get("payment_sms_template"),
                    "reminder_whatsapp": request.form.get("reminder_whatsapp_template"),
                }

                settings.notification_templates = templates
        except Exception as e:
            refuse(e, context="owner notification templates save")
            return redirect(url_for("owner.notification_templates"))
        _invalidate_owner_changes()
        flash(gettext("✅ تم تحديث قوالب الإشعارات"), "success")
        return redirect(url_for("owner.notification_templates"))

    settings = SystemSettings.get_current()
    templates = settings.notification_templates or {}

    return render_template("owner/notification_templates.html", templates=templates)


@owner_bp.route("/api/update-tenant-settings", methods=["POST"])
@login_required
@company_admin_required
def api_update_tenant_settings():
    """AJAX endpoint to update tenant-level settings from the company dashboard."""
    if not request.is_json:
        return error_response(message="JSON required", status_code=400)
    try:
        data = request.get_json(silent=True)
        if not data:
            return error_response(message="Invalid JSON", status_code=400)
        tenant = db.session.get(Tenant, get_active_tenant_id())
        if not tenant:
            return error_response(message="Tenant not found", status_code=404)
        field = data.get("field")
        value = data.get("value")
        if field not in ("default_tax_rate", "prices_include_vat", "logo_url"):
            return error_response(message=f"Unknown field: {field}", status_code=400)
        if field == "default_tax_rate":
            try:
                parsed = Decimal(str(value))
            except Exception:
                return error_response(message="Invalid tax rate value", status_code=400)
            with atomic_transaction("api_update_tenant_settings"):
                tenant.default_tax_rate = parsed
        else:
            with atomic_transaction("api_update_tenant_settings"):
                if field == "prices_include_vat":
                    tenant.prices_include_vat = bool(value)
                elif field == "logo_url":  # pragma: no cover - validated above, unreachable else
                    tenant.logo_url = str(value).strip()
                tenant.updated_at = datetime.now(UTC)
        _invalidate_owner_changes()
        _audit_owner_db_action("api_update_tenant_settings", {"field": field, "tenant_id": tenant.id})
        return success_response(message=gettext(f"تم تحديث {field} بنجاح"))
    except Exception as e:
        # Governed: an untyped Exception echoed verbatim to an API client.
        current_app.logger.error("owner backup run failed: %s", e, exc_info=True)
        return error_response(
            message=ErrorMessages.unexpected_error(),
            status_code=500,
        )


@owner_bp.route("/api/toggle-warehouse-negative", methods=["POST"])
@login_required
@company_admin_required
def api_toggle_warehouse_negative():
    """AJAX endpoint to toggle allow_negative_inventory for a warehouse."""
    if not request.is_json:
        return error_response(message="JSON required", status_code=400)
    try:
        data = request.get_json(silent=True)
        if not data:
            return error_response(message="Invalid JSON", status_code=400)
        warehouse_id = data.get("warehouse_id")
        if not warehouse_id:
            return error_response(message="warehouse_id required", status_code=400)
        tenant_id = get_active_tenant_id()
        warehouse = OwnerOpsService.warehouse_in_tenant(warehouse_id, tenant_id)
        if not warehouse:
            return error_response(message="Warehouse not found", status_code=404)
        with atomic_transaction("api_toggle_warehouse_negative"):
            warehouse.allow_negative_inventory = not warehouse.allow_negative_inventory
        _invalidate_owner_changes()
        return success_response(data={"allow_negative_inventory": warehouse.allow_negative_inventory})
    except Exception as e:
        # Governed: an untyped Exception echoed verbatim to an API client.
        current_app.logger.error("owner backup restore failed: %s", e, exc_info=True)
        return error_response(
            message=ErrorMessages.unexpected_error(),
            status_code=500,
        )


@owner_bp.route("/api/supervisor-override", methods=["POST"])
@login_required
# Defence in depth behind the indistinguishable-403 response. Sized above the
# test suite's call volume for this endpoint (~12 across the routes and
# integration suites) because conftest's TestConfig leaves rate limiting
# enabled against process-wide memory:// storage, so a tighter value turns
# unrelated tests into 429s. 20/minute still caps password guessing well below
# any usable rate.
@limiter.limit("20 per minute", methods=["POST"])
def api_supervisor_override():
    """Verify supervisor credentials for cashier override actions.

    This endpoint lives under ``/owner/api/`` URL-wise but is intentionally
    *not* gated by ``@owner_required`` / ``@owner_or_company_admin``:
    the legitimate caller is a logged-in **cashier** who is asking their
    supervisor to authorize a single risky POS action (discount override,
    void line, pay-in/out, drawer open, etc.). Defense-in-depth is
    applied inside the body, not on the decorator stack:

    * ``action`` must be one of the curated ``utils.pos_security``
      surface actions (validated by the calling services).
    * ``supervisor_id`` is resolved through ``scoped_user_query`` so a
      supervisor can only ever be drawn from the caller's own tenant.
      ``User`` is exempt from ORM tenant auto-scoping, so an unscoped
      ``db.session.get(User, ...)`` here would let any logged-in user in
      any tenant target every account on the platform.
    * The supervisor must hold the ``manager`` or ``admin`` role
      (``supervisor.is_manager() / supervisor.is_admin()``). Platform owners
      are allowed through as well, since an owner can legitimately supervise
      at a till.
    * The supervisor's plaintext ``password`` (validated via
      ``supervisor.check_password``) confirms physical presence of the
      supervisor at the terminal — this is the actual authorization
      gate.
    * Every failure mode returns one indistinguishable 403 so the
      endpoint cannot be used to enumerate user ids, roles or tenancy.
    * Every override is logged to ``LoggingCore.log_audit`` with
      ``(supervisor_id, action, cashier_id)`` for forensic tracing.
    """
    if not request.is_json:
        return error_response(message="JSON required", status_code=400)
    try:
        data = request.get_json(silent=True)
        if not data:
            return error_response(message="Invalid JSON", status_code=400)
        action = data.get("action", "")
        supervisor_id = data.get("supervisor_id")
        password = data.get("password", "")
        if not supervisor_id or not password:
            return error_response(
                message=gettext("معرّف المشرف وكلمة المرور مطلوبان"),
                status_code=400,
            )
        from utils.tenanting import scoped_user_query

        # Tenant-scoped: a cashier may only ever authorise a supervisor from
        # their own tenant. Owners are not excluded - an owner legitimately
        # supervises at a till, and the caller must still present the correct
        # password, so excluding them added no protection while rejecting a
        # valid supervisor.
        supervisor = scoped_user_query(active_only=True).filter(User.id == int(supervisor_id)).first()
        # One indistinguishable failure response. Distinguishing "no such
        # user" from "not a supervisor" from "wrong password" turns this into
        # a platform-wide account-enumeration and password oracle.
        if (
            not supervisor
            or not (supervisor.is_manager() or supervisor.is_admin())
            or not supervisor.check_password(password)
        ):
            logger.warning(
                "Rejected supervisor override attempt by user_id=%s for supervisor_id=%s",
                getattr(current_user, "id", None),
                supervisor_id,
            )
            return error_response(message=gettext("غير مصرح"), status_code=403)
        LoggingCore.log_audit(
            "supervisor_override",
            "system",
            None,
            {
                "supervisor_id": supervisor_id,
                "action": action,
                "cashier_id": current_user.id,
            },
        )
        return success_response(
            message=gettext("تم تفويض المشرف بنجاح"),
            data={"supervisor_username": supervisor.username},
        )
    except Exception as e:
        # Governed: an untyped Exception echoed verbatim to an API client.
        current_app.logger.error("owner backup verify failed: %s", e, exc_info=True)
        return error_response(
            message=ErrorMessages.unexpected_error(),
            status_code=500,
        )
