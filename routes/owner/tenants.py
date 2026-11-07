"""Tenant management routes for the owner blueprint."""

import logging
from datetime import UTC, date, datetime

from flask_babel import gettext

from services.logging_core import LoggingCore
from services.owner_ops_service import OwnerOpsService
from services.saas_provisioning_service import SaaSProvisioningService
from utils.db_safety import atomic_transaction

from .common import (
    Tenant,
    db,
    error_response,
    flash,
    get_system_default_currency,
    get_tenant_ai_level,
    owner_bp,
    owner_required,
    redirect,
    render_template,
    request,
    set_tenant_ai_level,
    success_response,
    url_for,
)
from .shared import _audit_owner_db_action, _invalidate_owner_changes

logger = logging.getLogger(__name__)


@owner_bp.route("/tenant-stores")
@owner_required
def tenant_stores():
    """التحكم الهرمي بمتاجر التينانتس — قفل/فك قفل من مالك المنصة."""
    from services.store_service import StoreService

    stores = OwnerOpsService.tenant_stores_with_tenants()
    rows = []
    for store, tenant in stores:
        rows.append(
            {
                "store": store,
                "tenant": tenant,
                "is_enabled": store.is_enabled,
                "platform_disabled": store.platform_disabled,
                "public_available": StoreService.is_store_publicly_available(store),
            }
        )
    return render_template(
        "owner/tenant_stores.html",
        rows=rows,
        global_enabled=StoreService.stores_globally_enabled(),
    )


@owner_bp.route("/tenant-ai")
@owner_required
def tenant_ai():
    """Platform-level per-tenant AI visibility toggle."""
    tenants = OwnerOpsService.active_ai_tenants()
    tenant_ai_levels = {int(t.id): get_tenant_ai_level(int(t.id), default="execute") for t in tenants}
    return render_template("owner/tenant_ai.html", tenants=tenants, tenant_ai_levels=tenant_ai_levels)


@owner_bp.route("/tenant-ai/<int:tenant_id>/toggle", methods=["POST"])
@owner_required
def tenant_ai_toggle(tenant_id):
    tenant = OwnerOpsService.get_tenant(int(tenant_id))
    if not tenant:
        flash(gettext("التينانت غير موجود."), "warning")
        return redirect(url_for("owner.tenant_ai"))

    enabled = request.form.get("enable_ai") == "1"
    ai_access_level = (
        (request.form.get("ai_access_level") or get_tenant_ai_level(int(tenant.id), default="execute")).strip().lower()
    )
    if ai_access_level not in ("basic", "advanced", "execute"):
        ai_access_level = "execute"
    # AI external-sharing privacy flag (P1): hidden+checkbox pattern —
    # getlist returns DOM order, so the checkbox value (when checked) wins.
    ext_sharing_values = request.form.getlist("ai_external_sharing_enabled")
    new_ext_sharing = None
    if ext_sharing_values:
        new_ext_sharing = ext_sharing_values[-1] == "1"
    try:
        with atomic_transaction("tenant_ai_toggle"):
            tenant.enable_ai = enabled
            if new_ext_sharing is not None:
                tenant.ai_external_sharing_enabled = new_ext_sharing
            ai_access_level = set_tenant_ai_level(int(tenant.id), ai_access_level)
        LoggingCore.log_audit(
            "platform_tenant_ai_enable" if enabled else "platform_tenant_ai_disable",
            "tenants",
            tenant.id,
            {
                "tenant_name": tenant.name,
                "enabled": enabled,
                "ai_access_level": ai_access_level,
                "ai_external_sharing_enabled": tenant.ai_external_sharing_enabled,
            },
        )
        _invalidate_owner_changes()
        flash(
            gettext(f"تم {'تفعيل' if enabled else 'إيقاف'} المساعد الذكي للتينانت: {tenant.name_ar or tenant.name}"),
            "success",
        )
    except Exception as exc:
        flash(gettext(f"تعذر تحديث إعداد AI: {exc}"), "danger")
    return redirect(url_for("owner.tenant_ai"))


@owner_bp.route("/tenant-stores/<int:store_id>/platform-toggle", methods=["POST"])
@owner_required
def tenant_store_platform_toggle(store_id):
    """قفل (force-OFF) أو فك قفل متجر تينانت من مالك المنصة."""
    from services.store_service import StoreService

    store = OwnerOpsService.get_tenant_store(store_id)
    if not store:
        flash(gettext("المتجر غير موجود."), "warning")
        return redirect(url_for("owner.tenant_stores"))

    disabled = request.form.get("platform_disabled") == "1"
    try:
        StoreService.set_platform_disabled(store, disabled)
        LoggingCore.log_audit(
            "platform_store_lock" if disabled else "platform_store_unlock",
            "tenant_stores",
            store.id,
        )
        _invalidate_owner_changes()
        flash(
            (
                gettext("تم تعطيل المتجر من مستوى المنصة. لا يستطيع مالك التينانت تفعيله.")
                if disabled
                else gettext("تم فك القفل. أصبح التحكم بيد مالك التينانت.")
            ),
            "success",
        )
    except Exception as exc:
        flash(gettext(f"تعذر تحديث حالة المتجر: {exc}"), "danger")
    return redirect(url_for("owner.tenant_stores"))


@owner_bp.route("/tenants")
@owner_required
def tenants_list():
    from services.tenant_service import TenantService

    sort = (request.args.get("sort") or "created_at").lower()
    order = (request.args.get("order") or "desc").lower()
    q = (request.args.get("q") or "").strip()

    context = TenantService.get_tenants_list_context(sort=sort, order=order, search=q)
    return render_template(
        "owner/tenants_list.html",
        tenants=context["tenants"],
        user_counts=context["user_counts"],
        branch_counts=context["branch_counts"],
        store_counts=context["store_counts"],
        today_date=date.today(),
    )


@owner_bp.route("/tenants/create", methods=["GET", "POST"])
@owner_required
def tenant_create():
    """Create a new tenant from the owner panel."""
    packages = OwnerOpsService.active_packages_sorted()

    if request.method == "POST":
        try:
            name_ar = request.form.get("name_ar", "").strip()
            name_en = request.form.get("name_en", "").strip() or name_ar
            slug = request.form.get("slug", "").strip()
            if not name_ar or not slug:
                flash(gettext("الاسم العربي والـ Slug مطلوبان."), "danger")
                return redirect(url_for("owner.tenant_create"))
            default_currency = request.form.get("default_currency", "").strip().upper()
            if not default_currency:
                flash(gettext("يجب اختيار العملة الافتراضية للتينانت."), "danger")
                return redirect(url_for("owner.tenant_create"))
            if OwnerOpsService.find_tenant_by_slug(slug):
                flash(gettext("الـ Slug مستخدم مسبقاً."), "danger")
                return redirect(url_for("owner.tenant_create"))

            def _form_int(name, default):
                try:
                    raw = str(request.form.get(name, "")).strip()
                    return int(raw) if raw else default
                except (TypeError, ValueError):
                    return default

            def _tristate(name):
                raw = request.form.get(name, "")
                if raw == "1":
                    return True
                if raw == "0":
                    return False
                return None

            # Tax & invoice constants are fixed at creation from the
            # tenant's profile (the user's rule: statutory rates are never
            # "played with" — always standard-or-exempt). The rate itself is
            # derived server-side from vat_country; it is never read from the
            # form, so the stranded legacy default (5%) can never leak into a
            # tenant whose country bills a different rate.
            from utils.country_tax import (
                validate_tax_number,
                vat_rate_for_country,
            )
            from utils.regional_defaults import FALLBACK_VAT_COUNTRY

            vat_country = (request.form.get("vat_country") or FALLBACK_VAT_COUNTRY).strip().upper()[:2]
            if vat_country not in ("PS", "IL", "AE", "SA"):
                vat_country = FALLBACK_VAT_COUNTRY
            vat_number = (request.form.get("vat_number") or "").strip() or None
            tax_number = (request.form.get("tax_number") or "").strip() or None
            for _candidate, _label in ((vat_number, "VAT_TRN_Number"), (tax_number, "General_Tax_Number")):
                if _candidate and not validate_tax_number(_candidate, vat_country):
                    flash(gettext(f"رقم غير صالح لدولة {vat_country}."), "danger")
                    return redirect(url_for("owner.tenant_create"))

            def _inv_text(name, default=None):
                """Blank invoice-constant form values become None (never "")."""
                raw = (request.form.get(name) or "").strip()
                return raw or default

            tenant = Tenant(
                name=name_ar,
                name_ar=name_ar,
                name_en=name_en,
                slug=slug,
                business_type=request.form.get("business_type", "general").strip(),
                phone_1=request.form.get("phone_1", "").strip() or None,
                phone_2=request.form.get("phone_2", "").strip() or None,
                email=request.form.get("email", "").strip() or None,
                address_ar=request.form.get("address_ar", "").strip() or None,
                address_en=_inv_text("address_en"),
                city=_inv_text("city"),
                country=_inv_text("country"),
                website=_inv_text("website"),
                commercial_register=_inv_text("commercial_register"),
                license_number=_inv_text("license_number"),
                default_currency=default_currency,
                vat_country=vat_country,
                default_tax_rate=vat_rate_for_country(vat_country),
                enable_tax=(request.form.get("enable_tax") == "on"),
                prices_include_vat=(request.form.get("prices_include_vat") == "on"),
                vat_number=vat_number,
                tax_number=tax_number,
                logo_url=(request.form.get("logo_url") or "").strip() or None,
                bank_name=_inv_text("bank_name"),
                bank_account_number=_inv_text("bank_account_number"),
                iban=_inv_text("iban"),
                swift_code=_inv_text("swift_code"),
                invoice_header_color=_inv_text("invoice_header_color", "#667eea"),
                invoice_accent_color=_inv_text("invoice_accent_color", "#764ba2"),
                payment_terms_ar=_inv_text("payment_terms_ar"),
                payment_terms_en=_inv_text("payment_terms_en"),
                footer_invoice_text_ar=_inv_text("footer_invoice_text_ar"),
                footer_invoice_text_en=_inv_text("footer_invoice_text_en"),
                default_invoice_note_ar=_inv_text("default_invoice_note_ar"),
                default_invoice_note_en=_inv_text("default_invoice_note_en"),
                active_invoice_template=(request.form.get("active_invoice_template") or "modern").strip() or "modern",
                max_users=_form_int("max_users", 5),
                max_products=_form_int("max_products", 1000),
                max_customers=_form_int("max_customers", 500),
                max_suppliers=_form_int("max_suppliers", 200),
                max_branches=_form_int("max_branches", 3),
                max_warehouses=_form_int("max_warehouses", 2),
                max_storage_mb=_form_int("max_storage_mb", 1024),
                max_invoices_per_month=_form_int("max_invoices_per_month", 1000),
                max_sales_per_month=_form_int("max_sales_per_month", 5000),
                data_retention_days=_form_int("data_retention_days", 365),
                enable_pos=request.form.get("enable_pos") == "on",
                enable_payroll=request.form.get("enable_payroll") == "on",
                enable_cheques=request.form.get("enable_cheques") == "on",
                enable_expenses=request.form.get("enable_expenses") == "on",
                enable_reports=request.form.get("enable_reports") == "on",
                enable_ai=request.form.get("enable_ai") == "on",
                enable_store=request.form.get("enable_store") == "on",
                enable_gl=request.form.get("enable_gl") == "on",
                enable_api=request.form.get("enable_api") == "on",
                enable_multi_warehouse=request.form.get("enable_multi_warehouse") == "on",
                enable_multi_currency=request.form.get("enable_multi_currency") == "on",
                enable_auto_backup=request.form.get("enable_auto_backup") == "on",
                allow_data_export=request.form.get("allow_data_export") == "on",
                allow_custom_integrations=request.form.get("allow_custom_integrations") == "on",
                enable_pos_promotions=_tristate("enable_pos_promotions"),
                enable_pos_multi_tender=_tristate("enable_pos_multi_tender"),
                enable_pos_returns=_tristate("enable_pos_returns"),
                enable_pos_shifts=_tristate("enable_pos_shifts"),
                is_active=True,
                is_suspended=False,
            )
            with atomic_transaction("tenant_create"):
                db.session.add(tenant)
                db.session.flush()
                from models import ensure_default_pos_order_types

                # Provisioning writes rows for the tenant being created, but the
                # request is still authenticated as the platform owner, whose
                # active tenant is a different one. The ORM write guard reads the
                # active tenant and raised TenantIsolationError on the first
                # PosOrderType row, which rolled the whole transaction back - so
                # the tenant row never landed and no tenant could be onboarded
                # through this endpoint at all. Seeding a brand new tenant is
                # necessarily cross-tenant relative to the current session, which
                # is exactly what without_tenant_scope() exists for.
                from utils.tenanting import without_tenant_scope

                with without_tenant_scope():
                    ensure_default_pos_order_types(tenant.id)
            from services.gl_service import GLService

            with atomic_transaction("tenant_gl_setup"):
                # Same cross-tenant condition as the order types above: the
                # chart of accounts and the concept mappings are being written
                # for the new tenant while the session still belongs to the
                # platform owner. Without the scope bypass the first GLAccount
                # insert raised TenantIsolationError and rolled the whole GL
                # setup back, leaving the tenant with an empty chart of accounts
                # and therefore unable to post anything.
                with without_tenant_scope():
                    GLService.ensure_core_accounts(tenant_id=tenant.id, cleanup_extra=False)
                # Explicitly ensure GL concept -> account mappings exist.
                # This guarantees that OPENING_BALANCE_EQUITY->3130 (and all
                # other required mappings) are persisted immediately, preventing
                # failures when products are later created with opening balances.
                # In the same cross-tenant situation as above.
                with without_tenant_scope():
                    GLService.ensure_gl_mappings(tenant_id=tenant.id)

            # Optional subscription scenario: activate a purchased package
            # (applies the plan label, duration window, and the package's
            # limits/flags template on top of the form values).
            package_id_raw = str(request.form.get("package_id", "")).strip()
            if package_id_raw:
                duration = request.form.get("subscription_plan_duration", "monthly").strip() or "monthly"
                if duration not in ("monthly", "annual", "trial", "lifetime"):
                    duration = "monthly"
                SaaSProvisioningService.activate_purchased_package(
                    tenant_id=tenant.id,
                    package_id=int(package_id_raw),
                    duration_type=duration,
                )
                explicit_end = (request.form.get("subscription_end") or "").strip()
                if explicit_end:
                    with atomic_transaction("tenant_create_subscription_end"):
                        tenant.set_subscription_end(explicit_end)
                        db.session.flush()

            _invalidate_owner_changes()
            _audit_owner_db_action("tenant_create", {"tenant_id": tenant.id, "slug": slug})
            flash(gettext(f'تم إنشاء التينانت "{tenant.name_ar}" بنجاح.'), "success")
            return redirect(url_for("owner.tenants_list"))
        except Exception as e:
            flash(gettext(f"خطأ في إنشاء التينانت: {str(e)}"), "danger")
    from utils.tax_settings import VAT_COUNTRY_LABELS

    return render_template("owner/tenant_create.html", packages=packages, vat_countries=VAT_COUNTRY_LABELS)


@owner_bp.route("/tenants/<int:tenant_id>/suspend", methods=["POST"])
@owner_required
def tenant_suspend(tenant_id):
    """Suspend a tenant (soft-disable all operations)."""
    tenant = OwnerOpsService.get_tenant_or_404(tenant_id)
    reason = request.form.get("reason", "").strip()

    # Owner can suspend any tenant — the numeric id=1 block was a stale
    # "default tenant" guard that ended up blocking the operator from
    # touching the first row inserted, regardless of what it is.

    try:
        with atomic_transaction("tenant_suspend"):
            tenant.is_active = False
            tenant.is_suspended = True
            tenant.suspension_reason = reason or "Suspended by owner"
            tenant.updated_at = datetime.now(UTC)
    except Exception as e:
        flash(gettext(f"خطأ في تعليق التينانت: {str(e)}"), "danger")
        return redirect(url_for("owner.tenants_list"))
    _invalidate_owner_changes()
    _audit_owner_db_action("tenant_suspend", {"tenant_id": tenant_id, "reason": reason})
    flash(
        gettext(f'تم تعليق التينانت "{tenant.name_ar or tenant.name}" بنجاح.'),
        "success",
    )
    return redirect(url_for("owner.tenants_list"))


@owner_bp.route("/tenants/<int:tenant_id>/activate", methods=["POST"])
@owner_required
def tenant_activate(tenant_id):
    """Re-activate a suspended tenant."""
    tenant = OwnerOpsService.get_tenant_or_404(tenant_id)

    try:
        with atomic_transaction("tenant_activate"):
            tenant.is_active = True
            tenant.is_suspended = False
            tenant.suspension_reason = None
            tenant.updated_at = datetime.now(UTC)
    except Exception as e:
        flash(gettext(f"خطأ في تفعيل التينانت: {str(e)}"), "danger")
        return redirect(url_for("owner.tenants_list"))
    _invalidate_owner_changes()
    _audit_owner_db_action("tenant_activate", {"tenant_id": tenant_id})
    flash(
        gettext(f'تم تفعيل التينانت "{tenant.name_ar or tenant.name}" بنجاح.'),
        "success",
    )
    return redirect(url_for("owner.tenants_list"))


@owner_bp.route("/tenants/<int:tenant_id>/edit", methods=["GET", "POST"])
@owner_required
def tenant_edit(tenant_id):
    """Edit tenant core settings."""
    tenant = OwnerOpsService.get_tenant_or_404(tenant_id)

    if request.method == "POST":
        try:

            def _form_int(name, current):
                try:
                    raw = str(request.form.get(name, "")).strip()
                    return int(raw) if raw else current
                except (TypeError, ValueError):
                    return current

            def _tristate(name, current):
                raw = request.form.get(name, "")
                if raw == "1":
                    return True
                if raw == "0":
                    return False
                return current

            def _text(name, current):
                """A submitted-but-blank field keeps its current value.

                name and slug are both NOT NULL and UNIQUE, and form.get's fallback
                argument only helps when a field is *absent* - not when it is
                present and empty, which is exactly what an emptied <input>
                posts. Writing "" into either one erases the tenant's identity
                from every list and breadcrumb that renders it, and the second
                tenant blanked the same way collides on the unique index. The
                nullable columns below deliberately keep their "or None" behaviour;
                these four do not.
                """
                raw = request.form.get(name)
                if raw is None:
                    return current
                return raw.strip() or current

            with atomic_transaction("tenant_edit"):
                tenant.name = _text("name_ar", tenant.name)
                tenant.name_ar = _text("name_ar", tenant.name_ar)
                tenant.name_en = _text("name_en", tenant.name_en)
                tenant.slug = _text("slug", tenant.slug)
                tenant.business_type = _text("business_type", tenant.business_type)
                tenant.phone_1 = (request.form.get("phone_1") or tenant.phone_1 or "").strip() or None
                tenant.phone_2 = (request.form.get("phone_2") or tenant.phone_2 or "").strip() or None
                tenant.email = (request.form.get("email") or tenant.email or "").strip() or None
                tenant.address_ar = (request.form.get("address_ar") or tenant.address_ar or "").strip() or None
                for _field in ("address_en", "city", "country", "website", "commercial_register", "license_number"):
                    if _field in request.form:
                        setattr(tenant, _field, (request.form.get(_field) or "").strip() or None)
                # Tax & invoice constants travel with the profile: changing
                # the VAT country re-locks the rate to that country's
                # statutory rate (never whatever the operator typed).
                from utils.country_tax import validate_tax_number, vat_rate_for_country
                from utils.regional_defaults import FALLBACK_VAT_COUNTRY

                _country = (
                    (request.form.get("vat_country") or tenant.vat_country or FALLBACK_VAT_COUNTRY).strip().upper()[:2]
                )
                if _country not in ("PS", "IL", "AE", "SA"):
                    _country = tenant.vat_country or FALLBACK_VAT_COUNTRY
                for _field in ("vat_number", "tax_number"):
                    if _field not in request.form:
                        continue
                    _candidate = (request.form.get(_field) or "").strip() or None
                    if _candidate and not validate_tax_number(_candidate, _country):
                        raise ValueError(gettext(f"رقم غير صالح لدولة {_country}."))
                    setattr(tenant, _field, _candidate)
                if _country != tenant.vat_country:
                    tenant.default_tax_rate = vat_rate_for_country(_country)
                tenant.vat_country = _country
                if "profile_tax_fields" in request.form or "enable_tax" in request.form:
                    tenant.enable_tax = request.form.get("enable_tax") == "on"
                if "logo_url" in request.form:
                    tenant.logo_url = (request.form.get("logo_url") or "").strip() or None
                # A missing field is not a request to erase it. An explicitly
                # submitted empty value still allows the operator to clear it.
                for _field in (
                    "bank_name",
                    "bank_account_number",
                    "iban",
                    "swift_code",
                    "invoice_header_color",
                    "invoice_accent_color",
                    "payment_terms_ar",
                    "payment_terms_en",
                    "footer_invoice_text_ar",
                    "footer_invoice_text_en",
                    "default_invoice_note_ar",
                    "default_invoice_note_en",
                ):
                    if _field in request.form:
                        setattr(tenant, _field, (request.form.get(_field) or "").strip() or None)
                if "active_invoice_template" in request.form:
                    tenant.active_invoice_template = (
                        request.form.get("active_invoice_template") or "modern"
                    ).strip() or "modern"
                # Keeps the tenant's own currency when the field is submitted
                # blank, for the reason _text gives: an emptied <input> posts as
                # "" and form.get's fallback only helps when the field is
                # absent. Falling back to get_system_default_currency() here
                # silently repointed a tenant's books at the platform default
                # (ILS) the moment an operator cleared the box - a currency
                # change with no confirmation, no audit line and no warning,
                # applied by an edit form whose other identity fields all
                # preserve instead.
                tenant.default_currency = (
                    (request.form.get("default_currency") or "").strip()
                    or tenant.default_currency
                    or get_system_default_currency()
                )
                tenant.max_users = _form_int("max_users", tenant.max_users or 5)
                tenant.max_products = _form_int("max_products", tenant.max_products or 1000)
                tenant.max_customers = _form_int("max_customers", tenant.max_customers or 500)
                tenant.max_suppliers = _form_int("max_suppliers", tenant.max_suppliers or 200)
                tenant.max_branches = _form_int("max_branches", tenant.max_branches or 3)
                tenant.max_warehouses = _form_int("max_warehouses", tenant.max_warehouses or 2)
                tenant.max_storage_mb = _form_int("max_storage_mb", tenant.max_storage_mb or 1024)
                tenant.max_invoices_per_month = _form_int(
                    "max_invoices_per_month", tenant.max_invoices_per_month or 1000
                )
                tenant.max_sales_per_month = _form_int("max_sales_per_month", tenant.max_sales_per_month or 5000)
                tenant.data_retention_days = _form_int("data_retention_days", tenant.data_retention_days or 365)
                for _field in (
                    "enable_pos",
                    "enable_payroll",
                    "enable_cheques",
                    "enable_expenses",
                    "enable_reports",
                    "enable_ai",
                    "enable_store",
                    "enable_gl",
                    "enable_api",
                    "enable_multi_warehouse",
                    "enable_multi_currency",
                    "enable_auto_backup",
                    "allow_data_export",
                    "allow_custom_integrations",
                ):
                    if "profile_feature_fields" in request.form or _field in request.form:
                        setattr(tenant, _field, request.form.get(_field) == "on")
                if "profile_tax_fields" in request.form or "prices_include_vat" in request.form:
                    tenant.prices_include_vat = request.form.get("prices_include_vat") == "on"
                tenant.enable_pos_promotions = _tristate("enable_pos_promotions", tenant.enable_pos_promotions)
                tenant.enable_pos_multi_tender = _tristate("enable_pos_multi_tender", tenant.enable_pos_multi_tender)
                tenant.enable_pos_returns = _tristate("enable_pos_returns", tenant.enable_pos_returns)
                tenant.enable_pos_shifts = _tristate("enable_pos_shifts", tenant.enable_pos_shifts)
                tenant.updated_at = datetime.now(UTC)
                # The owner may edit a tenant other than the active one.
                from services.invoice_profile_service import InvoiceProfileService
                from utils.invoice_profile import PROFILE_TO_INVOICE_SETTINGS

                _submitted = set(request.form).intersection(PROFILE_TO_INVOICE_SETTINGS)
                if _submitted:
                    InvoiceProfileService.sync_from_tenant(tenant, _submitted)
            _invalidate_owner_changes()
            _audit_owner_db_action("tenant_edit", {"tenant_id": tenant_id})
            flash(
                gettext(f'تم تحديث بيانات التينانت "{tenant.name_ar}" بنجاح.'),
                "success",
            )
            return redirect(url_for("owner.tenants_list"))
        except Exception as e:
            flash(gettext(f"خطأ في تحديث التينانت: {str(e)}"), "danger")

    from utils.tax_settings import VAT_COUNTRY_LABELS

    return render_template("owner/tenant_edit.html", tenant=tenant, vat_countries=VAT_COUNTRY_LABELS)


@owner_bp.route("/tenants/<int:tenant_id>/delete", methods=["POST"])
@owner_required
def tenant_delete(tenant_id):
    """Soft-delete a tenant (mark as inactive, do not purge)."""
    tenant = OwnerOpsService.get_tenant_or_404(tenant_id)

    # Owner has full control over tenants; the historical "id==1 is sacred"
    # guard only made sense when the platform kept an Azad-default tenant
    # at that id, which we no longer do (the platform vault is tenant-less).

    # Check for active users
    active_users = OwnerOpsService.count_tenant_active_users(tenant_id)
    if active_users > 0:
        flash(
            gettext(f"⚠️ التينانت يحتوي على {active_users} مستخدمين نشطين. قم بتعطيلهم أولاً أو قم بالتعليق."),
            "warning",
        )
        return redirect(url_for("owner.tenants_list"))

    try:
        with atomic_transaction("tenant_delete"):
            tenant.is_active = False
            tenant.is_suspended = True
            tenant.suspension_reason = "Deleted by owner"
            tenant.updated_at = datetime.now(UTC)
    except Exception as e:
        flash(gettext(f"خطأ في حذف التينانت: {str(e)}"), "danger")
        return redirect(url_for("owner.tenants_list"))
    _invalidate_owner_changes()
    _audit_owner_db_action("tenant_soft_delete", {"tenant_id": tenant_id})
    flash(gettext(f'تم حذف التينانت "{tenant.name_ar or tenant.name}" بنجاح.'), "success")
    return redirect(url_for("owner.tenants_list"))


@owner_bp.route("/api/tenant/<int:tenant_id>/toggle-status", methods=["POST"])
@owner_required
def api_tenant_toggle_status(tenant_id):
    """AJAX endpoint to toggle tenant active/suspended status from super admin dashboard."""
    if not request.is_json:
        return error_response(message="JSON required", status_code=400)
    try:
        tenant = OwnerOpsService.get_tenant(tenant_id)
        if not tenant:
            return error_response(message="Tenant not found", status_code=404)
        with atomic_transaction("api_tenant_toggle_status"):
            tenant.is_active = not tenant.is_active
            tenant.is_suspended = not tenant.is_active
            if not tenant.is_active:
                tenant.suspension_reason = "Disabled via API"
            else:
                tenant.suspension_reason = None
            tenant.updated_at = datetime.now(UTC)
        _invalidate_owner_changes()
        _audit_owner_db_action(
            "api_tenant_toggle_status",
            {"tenant_id": tenant_id, "is_active": tenant.is_active},
        )
        status_label = gettext("مفعل") if tenant.is_active else gettext("معطل")
        return success_response(
            message=gettext(f'تم {status_label} التينانت "{tenant.name_ar or tenant.name}" بنجاح'),
            data={"is_active": tenant.is_active},
        )
    except Exception as e:
        return error_response(message=str(e), status_code=500)


@owner_bp.route("/api/tenant/<int:tenant_id>/update-package", methods=["POST"])
@owner_required
def api_tenant_update_package(tenant_id):
    """AJAX endpoint to update tenant package limits from super admin dashboard."""
    if not request.is_json:
        return error_response(message="JSON required", status_code=400)
    try:
        data = request.get_json(silent=True) or {}
        tenant = OwnerOpsService.get_tenant(tenant_id)
        if not tenant:
            return error_response(message="Tenant not found", status_code=404)
        field = data.get("field")
        value = data.get("value")
        allowed_fields = [
            "max_users",
            "max_products",
            "max_customers",
            "max_suppliers",
            "max_branches",
            "max_warehouses",
            "max_invoices_per_month",
            "max_sales_per_month",
        ]
        if field not in allowed_fields:
            return error_response(message=f"Unknown field: {field}", status_code=400)
        try:
            val = int(str(value))
        except (ValueError, TypeError):
            return error_response(message="Invalid integer value", status_code=400)
        with atomic_transaction("api_tenant_update_package"):
            setattr(tenant, field, val)
            tenant.updated_at = datetime.now(UTC)
        _invalidate_owner_changes()
        _audit_owner_db_action(
            "api_tenant_update_package",
            {"tenant_id": tenant_id, "field": field, "value": value},
        )
        return success_response(message=gettext(f"تم تحديث {field} إلى {value}"))
    except Exception as e:
        return error_response(message=str(e), status_code=500)


@owner_bp.route("/tenants/<int:tenant_id>/extend-subscription", methods=["POST"])
@owner_required
def tenant_extend_subscription(tenant_id):
    """Manually extend (or shorten) a tenant's subscription duration."""
    tenant = OwnerOpsService.get_tenant_or_404(tenant_id)

    days_raw = str(request.form.get("days", "0") or "0").strip()
    try:
        days = int(days_raw)
    except (ValueError, TypeError):
        flash(gettext("عدد الأيام غير صالح."), "danger")
        return redirect(url_for("owner.tenant_edit", tenant_id=tenant_id))

    explicit_end = (request.form.get("subscription_end") or "").strip() or None
    plan = (request.form.get("subscription_plan") or "").strip() or None
    duration = (request.form.get("subscription_plan_duration") or "").strip() or None
    is_trial_raw = request.form.get("is_trial")
    is_trial = None if is_trial_raw in (None, "") else (is_trial_raw == "1" or is_trial_raw == "on")

    try:
        with atomic_transaction("tenant_extend_subscription"):
            if explicit_end:
                tenant.set_subscription_end(explicit_end)
            elif days != 0:
                tenant.extend_subscription(days)
            if plan or duration or is_trial is not None:
                SaaSProvisioningService.apply_plan_with_template(tenant, plan, duration, is_trial)
        _invalidate_owner_changes()
        _audit_owner_db_action(
            "tenant_extend_subscription",
            {
                "tenant_id": tenant_id,
                "days": days,
                "subscription_end": explicit_end,
                "plan": plan,
                "duration": duration,
                "is_trial": is_trial,
            },
        )
        flash(
            gettext(f'تم تحديث اشتراك التينانت "{tenant.name_ar or tenant.name}" بنجاح.'),
            "success",
        )
    except Exception as e:
        flash(gettext(f"خطأ في تمديد الاشتراك: {e}"), "danger")
    return redirect(url_for("owner.tenant_edit", tenant_id=tenant_id))


@owner_bp.route("/api/tenant/<int:tenant_id>/extend-subscription", methods=["POST"])
@owner_required
def api_tenant_extend_subscription(tenant_id):
    """AJAX endpoint to extend or adjust a tenant subscription."""
    if not request.is_json:
        return error_response(message="JSON required", status_code=400)
    data = request.get_json(silent=True) or {}
    tenant = OwnerOpsService.get_tenant(tenant_id)
    if not tenant:
        return error_response(message="Tenant not found", status_code=404)

    days_raw = str(data.get("days", "0") or "0").strip()
    try:
        days = int(days_raw)
    except (ValueError, TypeError):
        return error_response(message="Invalid days value", status_code=400)

    explicit_end = data.get("subscription_end") or None
    plan = data.get("subscription_plan") or None
    duration = data.get("subscription_plan_duration") or None
    is_trial = data.get("is_trial")

    try:
        with atomic_transaction("api_tenant_extend_subscription"):
            if explicit_end:
                tenant.set_subscription_end(explicit_end)
            elif days != 0:
                tenant.extend_subscription(days)
            if plan or duration or is_trial is not None:
                SaaSProvisioningService.apply_plan_with_template(tenant, plan, duration, is_trial)
        _invalidate_owner_changes()
        _audit_owner_db_action(
            "api_tenant_extend_subscription",
            {
                "tenant_id": tenant_id,
                "days": days,
                "subscription_end": explicit_end,
                "plan": plan,
                "duration": duration,
                "is_trial": is_trial,
            },
        )
        return success_response(
            message=gettext(f"تم تحديث اشتراك التينانت '{tenant.name_ar or tenant.name}'"),
            data={
                "subscription_end": (
                    tenant.subscription_end.isoformat() if isinstance(tenant.subscription_end, datetime) else None
                ),
                "subscription_plan": (tenant.subscription_plan if isinstance(tenant.subscription_plan, str) else None),
                "subscription_plan_duration": (
                    tenant.subscription_plan_duration if isinstance(tenant.subscription_plan_duration, str) else None
                ),
                "is_trial": bool(tenant.is_trial),
            },
        )
    except Exception as e:
        return error_response(message=str(e), status_code=500)
