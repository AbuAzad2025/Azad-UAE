"""Context processors and template globals for AZADEXA ERP."""

import re
from datetime import datetime
from flask import current_app
from flask_login import current_user
from services.logging_core import LoggingCore
from typing import Any
from utils.currency_utils import (
    get_system_default_currency,
    get_currency_symbol,
    get_currency_name_ar,
)


def register_context_processors(app):
    """Register context processors and template globals on the Flask app."""

    @app.template_global()
    def tenant_document_logo(settings=None, tenant_id=None):
        from utils.tenant_branding import document_logo_relative_path

        return document_logo_relative_path(settings, tenant_id)

    # make t() available as a Jinja2 global so macros can use it
    app.jinja_env.globals.setdefault("t", __import__("utils.i18n", fromlist=["t"]).t)

    @app.context_processor
    def inject_has_endpoint():
        return dict(
            has_endpoint=lambda endpoint: endpoint in current_app.view_functions
        )

    @app.context_processor
    def utility_processor() -> dict[str, Any]:
        from utils.helpers import format_currency, timeago
        from utils.number_to_arabic import number_to_arabic_words
        from utils.i18n import t, is_rtl, get_current_language
        from utils.report_registry import (
            REPORT_REGISTRY,
            REPORT_CATEGORIES,
            get_reports_by_category,
        )

        tenant_name_ar = ""
        tenant_name = ""
        tenant_phone = ""
        tenant_email = ""
        tenant_address = ""
        tenant_logo_url = ""
        tenant_logo_dark_url = ""
        tenant_favicon_url = ""
        tenant_default_currency = ""
        tenant_enable_tax = None
        tenant_default_tax_rate = None
        tenant_enable_pos = True
        try:
            from models import Tenant
            from models.invoice_settings import InvoiceSettings

            tenant = Tenant.get_current()
            if tenant:
                tenant_name_ar = (tenant.name_ar or "").strip()
                tenant_name = (tenant.name_en or tenant.name or "").strip()
                tenant_phone = (tenant.phone_1 or tenant.mobile or "").strip()
                tenant_email = (tenant.email or "").strip()
                tenant_address = (tenant.address_ar or tenant.address_en or "").strip()
                tenant_logo_url = (tenant.logo_url or "").strip()
                tenant_logo_dark_url = (tenant.logo_dark_url or "").strip()
                tenant_favicon_url = (tenant.favicon_url or "").strip()
                tenant_default_currency = tenant.get_base_currency if tenant else ""
                tenant_enable_tax = bool(getattr(tenant, "enable_tax", True))
                tenant_default_tax_rate = getattr(tenant, "default_tax_rate", None)
                tenant_enable_pos = bool(getattr(tenant, "enable_pos", True))
            if not tenant_name_ar:
                inv = InvoiceSettings.get_active()
                if inv:
                    tenant_name_ar = (inv.company_name_ar or "").strip()
                    tenant_name = (inv.company_name_en or "").strip() or tenant_name
                    tenant_phone = (inv.phone_1 or "").strip() or tenant_phone
                    tenant_email = (inv.email or "").strip() or tenant_email
                    tenant_address = (
                        inv.address_ar or inv.address_en or ""
                    ).strip() or tenant_address
                    tenant_logo_url = (inv.logo_url or "").strip() or tenant_logo_url
            if tenant:
                from utils.tenant_branding import resolve_tenant_branding

                branding = resolve_tenant_branding(tenant.id)
                tenant_logo_url = branding.get("logo_url") or tenant_logo_url
                tenant_logo_dark_url = (
                    branding.get("logo_dark_url") or tenant_logo_dark_url
                )
                tenant_favicon_url = branding.get("favicon_url") or tenant_favicon_url
                if not tenant_name_ar:
                    tenant_name_ar = branding.get("company_name_ar") or tenant_name_ar
                if not tenant_name:
                    tenant_name = branding.get("company_name_en") or tenant_name
        except Exception as e:
            try:
                LoggingCore.log_error(
                    message=str(e) or "Failed to load tenant/invoice settings",
                    category="FRONTEND",
                    level="WARNING",
                    source="app.context_processor.tenant_settings",
                    exception=e,
                )
            except Exception:
                LoggingCore.log_error(
                    message="Context processor tenant_settings inner guard failed",
                    category="SYSTEM",
                    level="WARNING",
                    source="app.context_processor.tenant_settings",
                )

        try:
            from models.system_settings import SystemSettings

            sys_settings = SystemSettings.get_current()
            developer_name_ar = (
                sys_settings.get_custom_setting("developer_name_ar") or ""
            ).strip() or app.config.get("DEVELOPER_NAME_AR", "")
            developer_name = (
                sys_settings.get_custom_setting("developer_name") or ""
            ).strip() or app.config.get("DEVELOPER_NAME", "")
            developer_credit = (
                sys_settings.get_custom_setting("developer_credit") or ""
            ).strip() or app.config.get("DEVELOPER_CREDIT", "")
            developer_phone = (
                sys_settings.get_custom_setting("developer_phone") or ""
            ).strip() or app.config.get("DEVELOPER_PHONE", "")
            developer_email = (
                sys_settings.get_custom_setting("developer_email") or ""
            ).strip() or app.config.get("DEVELOPER_EMAIL", "")
            developer_website = (
                sys_settings.get_custom_setting("developer_website") or ""
            ).strip() or app.config.get("DEVELOPER_WEBSITE", "")
            developer_whatsapp = (
                sys_settings.get_custom_setting("developer_whatsapp") or ""
            ).strip() or app.config.get("DEVELOPER_WHATSAPP", "")
            developer_logo_raw = (
                sys_settings.get_custom_setting("developer_logo") or ""
            ).strip()
            if developer_logo_raw and (
                ":\\" in developer_logo_raw or ":/" in developer_logo_raw
            ):
                developer_logo_raw = ""
            if developer_logo_raw.startswith("/static/"):
                developer_logo_raw = developer_logo_raw[len("/static/") :]
            if developer_logo_raw.startswith("static/"):
                developer_logo_raw = developer_logo_raw[len("static/") :]
            developer_logo = developer_logo_raw or app.config.get(
                "DEVELOPER_LOGO", "assets/brand/azad/logos/logo.png"
            )
            system_default_currency = (
                sys_settings.default_currency or ""
            ).strip() or get_system_default_currency()
            system_currency_symbol = (
                sys_settings.currency_symbol or ""
            ).strip() or system_default_currency
            system_currency_position = (
                sys_settings.currency_position or ""
            ).strip() or "after"
            system_decimal_places = (
                sys_settings.decimal_places
                if isinstance(sys_settings.decimal_places, int)
                else 2
            )
            system_enable_tax = bool(getattr(sys_settings, "enable_tax", True))
            system_default_tax_rate = getattr(sys_settings, "default_tax_rate", None)
            system_enable_pos = bool(getattr(sys_settings, "enable_pos", False))
        except Exception as e:
            try:
                LoggingCore.log_error(
                    message=str(e) or "Failed to load system settings",
                    category="FRONTEND",
                    level="WARNING",
                    source="app.context_processor.system_settings",
                    exception=e,
                )
            except Exception:
                LoggingCore.log_error(
                    message="Context processor system_settings inner guard failed",
                    category="SYSTEM",
                    level="WARNING",
                    source="app.context_processor.system_settings",
                )
            developer_name_ar = app.config.get("DEVELOPER_NAME_AR", "")
            developer_name = app.config.get("DEVELOPER_NAME", "")
            developer_credit = app.config.get("DEVELOPER_CREDIT", "")
            developer_phone = app.config.get("DEVELOPER_PHONE", "")
            developer_email = app.config.get("DEVELOPER_EMAIL", "")
            developer_website = app.config.get("DEVELOPER_WEBSITE", "")
            developer_whatsapp = app.config.get("DEVELOPER_WHATSAPP", "")
            developer_logo = app.config.get(
                "DEVELOPER_LOGO", "assets/brand/azad/logos/logo.png"
            )
            system_default_currency = get_system_default_currency()
            system_currency_symbol = get_system_default_currency()
            system_currency_position = "after"
            system_decimal_places = 2
            system_enable_tax = True
            system_default_tax_rate = None
            system_enable_pos = False
            tenant_enable_pos = True

        def _normalize_whatsapp_link(value):
            digits = re.sub(r"\D+", "", value or "")
            if digits.startswith("00"):
                digits = digits[2:]
            return digits

        developer_whatsapp_link = _normalize_whatsapp_link(
            developer_whatsapp or developer_phone
        )

        from utils.constants import (
            PERMISSIONS,
            PERMISSION_CODES,
            CUSTOMER_TYPES,
            PAYMENT_STATUSES,
            SALE_STATUSES,
            PAYMENT_METHODS,
            USER_ROLES,
        )
        from utils.branching import get_active_branch, get_active_branch_mode

        current_user_permissions = []
        if current_user.is_authenticated and getattr(
            current_user, "has_permission", None
        ):
            current_user_permissions = [
                c for c in PERMISSION_CODES if current_user.has_permission(c)
            ]
        active_branch = (
            get_active_branch(current_user) if current_user.is_authenticated else None
        )
        active_branch_mode = (
            get_active_branch_mode() if current_user.is_authenticated else "single"
        )

        available_tenants = []
        active_tenant_id = None
        try:
            from utils.tenanting import get_active_tenant_id, is_global_tenant_user

            if current_user.is_authenticated and is_global_tenant_user(current_user):
                active_tenant_id = get_active_tenant_id(current_user)
                from models.tenant import Tenant as TenantModel

                available_tenants = (
                    TenantModel.query.filter_by(is_active=True)
                    .order_by(TenantModel.id.desc())
                    .limit(200)
                    .all()
                )
        except Exception as e:
            try:
                LoggingCore.log_error(
                    message=str(e) or "Failed to load available tenants",
                    category="FRONTEND",
                    level="WARNING",
                    source="app.context_processor.available_tenants",
                    exception=e,
                )
            except Exception:
                LoggingCore.log_error(
                    message="Context processor available_tenants inner guard failed",
                    category="SYSTEM",
                    level="WARNING",
                    source="app.context_processor.available_tenants",
                )
        app_enums = {
            "permissions": PERMISSIONS,
            "permission_codes": PERMISSION_CODES,
            "customer_types": CUSTOMER_TYPES,
            "payment_statuses": PAYMENT_STATUSES,
            "sale_statuses": SALE_STATUSES,
            "payment_methods": PAYMENT_METHODS,
            "user_roles": USER_ROLES,
        }
        from utils.ai_access import get_ai_access_state

        ai_access_state = get_ai_access_state(
            current_user if current_user.is_authenticated else None
        )

        # ── Tenant usage vs limits (for upgrade banners / usage meters) ──
        tenant_usage = {}
        tenant_subscription = {}
        wa_upgrade_link = ""
        try:
            from models import (
                Tenant as Tn,
                User,
                Branch,
                Warehouse,
                Product,
                Customer,
                Supplier,
            )

            _t = Tn.get_current()
            if _t:
                _res_map = {
                    "users": (
                        "users",
                        "User",
                        lambda: User.query.filter(
                            User.tenant_id == _t.id, User.is_active
                        ).count(),
                    ),
                    "branches": (
                        "branches",
                        "Branch",
                        lambda: Branch.query.filter(Branch.tenant_id == _t.id).count(),
                    ),
                    "warehouses": (
                        "warehouses",
                        "Warehouse",
                        lambda: Warehouse.query.filter(
                            Warehouse.tenant_id == _t.id
                        ).count(),
                    ),
                    "products": (
                        "products",
                        "Product",
                        lambda: Product.query.filter(
                            Product.tenant_id == _t.id, Product.is_active
                        ).count(),
                    ),
                    "customers": (
                        "customers",
                        "Customer",
                        lambda: Customer.query.filter(
                            Customer.tenant_id == _t.id, Customer.is_active
                        ).count(),
                    ),
                    "suppliers": (
                        "suppliers",
                        "Supplier",
                        lambda: Supplier.query.filter(
                            Supplier.tenant_id == _t.id, Supplier.is_active
                        ).count(),
                    ),
                }
                for key, (_res_name, _model_name, _counter) in _res_map.items():
                    max_val = getattr(_t, f"max_{key}", None)  # type: int | None
                    cur_val = _counter()
                    tenant_usage[key] = {
                        "current": cur_val,
                        "max": max_val,
                        "percent": round(
                            (cur_val / max_val * 100) if max_val and max_val > 0 else 0
                        ),
                    }
                tenant_subscription = {
                    "plan": _t.subscription_plan or "basic",
                    "is_trial": getattr(_t, "is_trial", False),
                    "is_active": _t.is_active,
                    "is_suspended": getattr(_t, "is_suspended", False),
                    "expiry_date": (
                        _t.subscription_end_at.isoformat()
                        if getattr(_t, "subscription_end_at", None)
                        else None
                    ),
                }
                wa_upgrade_link = developer_whatsapp_link or _normalize_whatsapp_link(
                    developer_whatsapp or developer_phone
                )
        except Exception:
            LoggingCore.log_error(
                message="Context processor WhatsApp upgrade link resolution failed",
                category="SYSTEM",
                level="WARNING",
                source="app.context_processor.whatsapp_link",
            )

        return {
            "format_currency": format_currency,
            "timeago": timeago,
            "t": t,
            "is_rtl": is_rtl(),
            "is_rtl_fn": is_rtl,
            "current_language": get_current_language(),
            "get_current_language": get_current_language,
            "get_currency_symbol": get_currency_symbol,
            "number_to_arabic_words": number_to_arabic_words,
            "current_user_permissions": current_user_permissions,
            "app_enums": app_enums,
            "role_enum": {
                "OWNER": "owner",
                "DEVELOPER": "developer",
                "SUPER_ADMIN": "super_admin",
                "MANAGER": "manager",
                "BRANCH_MANAGER": "branch_manager",
                "ACCOUNTANT": "accountant",
                "SELLER": "seller",
                "CASHIER": "cashier",
                "global_scope": list(
                    __import__(
                        "models.enums", fromlist=["RoleEnum"]
                    ).RoleEnum.global_scope_values()
                ),
                "company_admin": list(
                    __import__(
                        "models.enums", fromlist=["RoleEnum"]
                    ).RoleEnum.company_admin_values()
                ),
            },
            "tenant_name_ar": tenant_name_ar,
            "tenant_name": tenant_name,
            "tenant_phone": tenant_phone,
            "tenant_email": tenant_email,
            "tenant_address": tenant_address,
            "tenant_logo_url": tenant_logo_url,
            "tenant_logo_dark_url": tenant_logo_dark_url,
            "tenant_favicon_url": tenant_favicon_url,
            "tenant_default_currency": tenant_default_currency
            or system_default_currency
            or get_system_default_currency(),
            "tenant_currency_symbol": get_currency_symbol(
                tenant_default_currency
                or system_default_currency
                or get_system_default_currency()
            ),
            "tenant_currency_name_ar": get_currency_name_ar(
                tenant_default_currency
                or system_default_currency
                or get_system_default_currency()
            ),
            "tenant_enable_tax": (
                tenant_enable_tax
                if tenant_enable_tax is not None
                else system_enable_tax
            ),
            "tenant_default_tax_rate": (
                tenant_default_tax_rate
                if tenant_default_tax_rate is not None
                else system_default_tax_rate
            ),
            "company_name": tenant_name or "ERP System",
            "company_name_ar": tenant_name_ar or "نظام المحاسبة",
            "company_phone": tenant_phone,
            "company_email": tenant_email,
            "company_address": tenant_address,
            "company_default_currency": tenant_default_currency
            or system_default_currency,
            "company_enable_tax": (
                tenant_enable_tax
                if tenant_enable_tax is not None
                else system_enable_tax
            ),
            "company_default_tax_rate": (
                tenant_default_tax_rate
                if tenant_default_tax_rate is not None
                else system_default_tax_rate
            ),
            "system_default_currency": system_default_currency,
            "system_currency_symbol": system_currency_symbol,
            "system_currency_position": system_currency_position,
            "system_decimal_places": system_decimal_places,
            "system_enable_tax": system_enable_tax,
            "system_default_tax_rate": system_default_tax_rate,
            "system_enable_pos": system_enable_pos,
            "tenant_enable_pos": tenant_enable_pos,
            "developer_name_ar": developer_name_ar,
            "developer_name": developer_name,
            "developer_credit": developer_credit,
            "developer_phone": developer_phone,
            "developer_email": developer_email,
            "developer_website": developer_website,
            "developer_whatsapp": developer_whatsapp,
            "developer_whatsapp_link": developer_whatsapp_link,
            "developer_logo": developer_logo,
            "active_branch": active_branch,
            "active_branch_mode": active_branch_mode,
            "available_tenants": available_tenants,
            "active_tenant_id": active_tenant_id,
            "current_year": datetime.now().year,
            "now": datetime.now,
            "ai_enabled": "ai" in app.blueprints,
            "ai_access_state": ai_access_state,
            "ai_nav_visible": bool(ai_access_state.get("allowed")),
            "ai_effective_enabled": bool(
                ai_access_state.get("allowed")
                and ai_access_state.get("global_enabled")
                and (ai_access_state.get("tenant_enabled") is not False)
            ),
            "report_categories": REPORT_CATEGORIES,
            "report_registry_by_category": get_reports_by_category(current_user),
            "report_registry": REPORT_REGISTRY,
            "tenant_usage": tenant_usage,
            "tenant_subscription": tenant_subscription,
            "wa_upgrade_link": wa_upgrade_link,
        }
