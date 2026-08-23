from datetime import UTC, datetime

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_babel import gettext
from flask_login import current_user, login_required

from extensions import db
from models import Customer, Sale
from services.main_site_service import MainSiteService
from services.stock_service import StockService
from utils.branching import get_visible_products_query
from utils.db_safety import atomic_transaction
from utils.decorators import branch_scope_id
from utils.gl_tenant import get_gl_account_by_code
from utils.tenanting import get_active_tenant_id

main_bp = Blueprint("main", __name__)


@main_bp.route("/login")
def login_alias():
    return redirect(url_for("auth.login"))


@main_bp.route("/app")
def index():
    return redirect(url_for("main.dashboard"))


@main_bp.route("/dashboard")
@login_required
def dashboard():
    # Dashboard route with error handling
    try:
        today = datetime.now(UTC).date()
        month_start = today.replace(day=1)

        stats = {}
        scoped_branch_id = branch_scope_id()

        from utils.tenanting import tenant_query

        total_customers_query = tenant_query(Customer).filter_by(is_active=True)
        if scoped_branch_id is not None:
            total_customers_query = (
                total_customers_query.join(Sale, Sale.customer_id == Customer.id)
                .filter(Sale.branch_id == scoped_branch_id, Sale.status == "confirmed")
                .distinct()
            )
        total_customers = total_customers_query.count()
        stats["customers_count"] = total_customers

        tid = get_active_tenant_id(current_user)
        if scoped_branch_id is not None:
            total_products = get_visible_products_query(current_user).count()
        else:
            total_products = MainSiteService.count_active_products(tid)
        stats["products_count"] = total_products

        low_stock = []
        try:
            low_stock = StockService.get_low_stock_products(limit=10, user=current_user)
        except Exception as e:
            current_app.logger.error(f"Failed to fetch low stock products: {e}")

        stats["low_stock_count"] = len(low_stock)
        stats["low_stock_products"] = low_stock

        out_of_stock = []
        try:
            out_of_stock = StockService.get_out_of_stock_products(user=current_user)
        except Exception as e:
            current_app.logger.error(f"Failed to fetch out of stock products: {e}")

        stats["out_of_stock_count"] = len(out_of_stock)

        today_sales = MainSiteService.today_sales_totals(tid, today, scoped_branch_id)

        stats["today_sales_count"] = today_sales[0] or 0
        stats["today_sales_amount"] = float(today_sales[1] or 0)

        month_sales = MainSiteService.month_sales_totals(tid, month_start, scoped_branch_id)

        stats["month_sales_count"] = month_sales[0] or 0
        stats["month_sales_amount"] = float(month_sales[1] or 0)

        if current_user.can_see_costs():
            stats["month_profit"] = float(MainSiteService.month_profit_total(tid, month_start, scoped_branch_id))

        stats["total_receivables"] = float(MainSiteService.total_receivables(scoped_branch_id))

        if current_user.can_see_costs():
            try:
                from utils.gl_tenant import active_tenant_id

                gl_tid = active_tenant_id()

                stats["cash_balance"] = float(MainSiteService.liquidity_balance("cash", gl_tid, scoped_branch_id))
                stats["bank_balance"] = float(MainSiteService.liquidity_balance("bank", gl_tid, scoped_branch_id))

                inventory_acc = get_gl_account_by_code("1140", tenant_id=gl_tid)
                if inventory_acc:
                    stats["inventory_value_gl"] = float(
                        MainSiteService.inventory_gl_value(inventory_acc, scoped_branch_id)
                    )
            except Exception:
                current_app.logger.exception("Failed to compute inventory GL balance for dashboard")

        # Optimized query with eager loading (N+1 problem fix)
        recent_sales = MainSiteService.recent_confirmed_sales(tid, scoped_branch_id)

        stats["recent_sales"] = recent_sales

        if current_user.is_seller():
            my_today_sales = MainSiteService.seller_sales_totals_on(current_user.id, today)

            stats["my_today_sales_count"] = my_today_sales[0] or 0
            stats["my_today_sales_amount"] = float(my_today_sales[1] or 0)

        stats["can_apply_discount"] = current_user.can_apply_discount()
        stats["can_edit_price"] = current_user.can_edit_price()

        usage_summary = []
        try:
            from models import Tenant
            from utils.tenant_limits import get_tenant_usage_summary

            if tid:
                usage_summary = get_tenant_usage_summary(db.session.get(Tenant, int(tid)))
        except Exception as e:
            current_app.logger.error(f"Failed to build tenant usage summary: {e}")
        stats["usage_summary"] = usage_summary
        stats["usage_warnings"] = [row for row in usage_summary if row["warn"]]

        return render_template("dashboard.html", stats=stats)

    except Exception:
        current_app.logger.exception("Dashboard failed")
        return render_template("errors/500.html"), 500


# ───────────────────────────────────────────────────────────────
# User Self-Profile — view and edit own data only
# ───────────────────────────────────────────────────────────────


@main_bp.route("/my-profile")
@login_required
def my_profile():
    """Current user's own profile — view-only with edit form."""
    from models.tenant import Tenant

    user = current_user
    tenant = db.session.get(Tenant, user.tenant_id) if user.tenant_id else None

    # Personal stats
    today = datetime.now(UTC).date()
    month_start = today.replace(day=1)

    stats = {}

    # Sales stats
    today_sales = MainSiteService.seller_sales_totals_on(user.id, today)
    stats["today_sales_count"] = today_sales[0] or 0
    stats["today_sales_amount"] = float(today_sales[1] or 0)

    month_sales = MainSiteService.seller_sales_totals_since(user.id, month_start)
    stats["month_sales_count"] = month_sales[0] or 0
    stats["month_sales_amount"] = float(month_sales[1] or 0)

    total_sales = MainSiteService.seller_sales_totals(user.id)
    stats["total_sales_count"] = total_sales[0] or 0
    stats["total_sales_amount"] = float(total_sales[1] or 0)

    # Payment stats
    payment_stats = MainSiteService.payment_totals_for_user(user.id)
    stats["payments_count"] = payment_stats[0] or 0
    stats["payments_amount"] = float(payment_stats[1] or 0)

    # Recent sales
    recent_sales = MainSiteService.recent_sales_for_seller(user.id)

    return render_template(
        "my_profile.html",
        user=user,
        tenant=tenant,
        stats=stats,
        recent_sales=recent_sales,
    )


@main_bp.route("/my-profile/update", methods=["POST"])
@login_required
def my_profile_update():
    """Update own profile — strict whitelist of allowed fields."""
    from werkzeug.security import check_password_hash, generate_password_hash

    from utils.sanitizer import InputSanitizer

    user = current_user

    try:
        with atomic_transaction("profile_update"):
            # Whitelist: only these fields may be changed by the user

            # Sanitize and update allowed fields
            if "full_name" in request.form:
                user.full_name = (
                    InputSanitizer.sanitize_text(request.form.get("full_name", ""), max_length=100) or user.full_name
                )

            if "full_name_ar" in request.form:
                user.full_name_ar = (
                    InputSanitizer.sanitize_text(request.form.get("full_name_ar", ""), max_length=100)
                    or user.full_name_ar
                )

            if "email" in request.form:
                email = InputSanitizer.sanitize_email(request.form.get("email", ""))
                if email:
                    # Check email uniqueness (excluding self)
                    existing = MainSiteService.email_exists(email, user.id, user.tenant_id)
                    if existing:
                        flash(gettext("⚠️ هذا البريد الإلكتروني مستخدم من قبل."), "warning")
                        return redirect(url_for("main.my_profile"))
                    user.email = email

            if "phone" in request.form:
                from utils.field_validators import normalize_phone_optional

                user.phone = normalize_phone_optional(request.form.get("phone", ""))

            current_password = request.form.get("current_password", "").strip()
            new_password = request.form.get("new_password", "").strip()
            confirm_password = request.form.get("confirm_password", "").strip()

            if new_password:
                if not current_password:
                    flash(gettext("⚠️ يجب إدخال كلمة المرور الحالية."), "warning")
                    return redirect(url_for("main.my_profile"))

                if not check_password_hash(user.password_hash, current_password):
                    flash(gettext("❌ كلمة المرور الحالية غير صحيحة."), "danger")
                    return redirect(url_for("main.my_profile"))

                if new_password != confirm_password:
                    flash(gettext("❌ كلمة المرور الجديدة غير متطابقة."), "danger")
                    return redirect(url_for("main.my_profile"))

                from utils.password_validator import PasswordValidator

                is_valid, errors = PasswordValidator.validate(new_password)
                if not is_valid:
                    from utils.error_messages import ErrorMessages

                    flash(ErrorMessages.weak_password(errors), "danger")
                    return redirect(url_for("main.my_profile"))

                user.password_hash = generate_password_hash(new_password, method="pbkdf2:sha256")
                flash(gettext("✅ تم تغيير كلمة المرور بنجاح."), "success")

        if new_password:
            from utils.session_security import rotate_session

            rotate_session()
        flash(gettext("✅ تم تحديث البيانات بنجاح."), "success")

    except Exception as e:
        current_app.logger.error(f"My profile update error: {e}")
        flash(gettext(f"❌ خطأ في التحديث: {str(e)}"), "danger")

    return redirect(url_for("main.my_profile"))


# ───────────────────────────────────────────────────────────────
# Tenant Public Profile — read-only company info page
# ───────────────────────────────────────────────────────────────


@main_bp.route("/tenant/<slug>")
def tenant_public_profile(slug):
    """Public company profile page — no login required."""
    tenant = MainSiteService.tenant_by_slug(slug)

    # Only show active tenants
    if not tenant.is_active or getattr(tenant, "is_suspended", False):
        return (
            render_template(
                "public/tenant_suspended.html",
                tenant=tenant,
                reason=tenant.suspension_reason or "Tenant suspended",
            ),
            503,
        )

    branches = MainSiteService.active_branches_for_tenant(tenant.id)

    # Determine if viewer is owner (for edit/delete buttons)
    from flask_login import current_user as _current_user

    from utils.auth_helpers import is_global_owner_user

    is_owner_viewer = _current_user.is_authenticated and is_global_owner_user(_current_user)

    return render_template(
        "public/tenant_profile.html",
        tenant=tenant,
        branches=branches,
        is_owner_viewer=is_owner_viewer,
    )
