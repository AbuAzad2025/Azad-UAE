from flask_babel import gettext
from datetime import datetime, timezone
from decimal import Decimal
from flask import (
    Blueprint,
    render_template,
    current_app,
    redirect,
    url_for,
    request,
    flash,
)
from flask_login import login_required, current_user
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from extensions import db
from models import Sale, SaleLine, Customer, Product, GLAccount, GLJournalLine, User
from services.stock_service import StockService
from utils.decorators import branch_scope_id
from utils.branching import get_visible_products_query
from utils.tenanting import get_active_tenant_id
from utils.gl_tenant import get_gl_account_by_code
from utils.db_safety import atomic_transaction

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
        today = datetime.now(timezone.utc).date()
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

        if scoped_branch_id is not None:
            total_products = get_visible_products_query(current_user).count()
        else:
            tid = get_active_tenant_id(current_user)
            total_products = Product.query.filter_by(
                is_active=True, tenant_id=tid
            ).count()
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

        tid = get_active_tenant_id(current_user)
        today_sales_query = db.session.query(
            func.count(Sale.id), func.sum(Sale.amount_aed)
        ).filter(
            func.date(Sale.sale_date) == today,
            Sale.status == "confirmed",
            Sale.tenant_id == tid,
        )
        if scoped_branch_id is not None:
            today_sales_query = today_sales_query.filter(
                Sale.branch_id == scoped_branch_id
            )
        today_sales = today_sales_query.first()

        stats["today_sales_count"] = today_sales[0] or 0
        stats["today_sales_amount"] = float(today_sales[1] or 0)

        month_sales_query = db.session.query(
            func.count(Sale.id), func.sum(Sale.amount_aed)
        ).filter(
            func.date(Sale.sale_date) >= month_start,
            Sale.status == "confirmed",
            Sale.tenant_id == tid,
        )
        if scoped_branch_id is not None:
            month_sales_query = month_sales_query.filter(
                Sale.branch_id == scoped_branch_id
            )
        month_sales = month_sales_query.first()

        stats["month_sales_count"] = month_sales[0] or 0
        stats["month_sales_amount"] = float(month_sales[1] or 0)

        if current_user.can_see_costs():
            profit_expr = func.sum(
                (SaleLine.unit_price - func.coalesce(SaleLine.cost_price, 0))
                * SaleLine.quantity
                * (100 - func.coalesce(SaleLine.discount_percent, 0))
                / 100
            )
            month_profit_query = (
                db.session.query(profit_expr)
                .select_from(SaleLine)
                .join(Sale, SaleLine.sale_id == Sale.id)
                .filter(
                    func.date(Sale.sale_date) >= month_start,
                    Sale.status == "confirmed",
                    Sale.tenant_id == tid,
                )
            )
            if scoped_branch_id is not None:
                month_profit_query = month_profit_query.filter(
                    Sale.branch_id == scoped_branch_id
                )
            month_profit = month_profit_query.scalar() or Decimal("0")

            stats["month_profit"] = float(month_profit)

        total_receivables_query = db.session.query(
            func.sum(Sale.amount_aed - Sale.paid_amount_aed)
        ).filter(Sale.status == "confirmed", Sale.balance_due > 0)
        if scoped_branch_id is not None:
            total_receivables_query = total_receivables_query.filter(
                Sale.branch_id == scoped_branch_id
            )
        total_receivables = total_receivables_query.scalar() or Decimal("0")

        stats["total_receivables"] = float(total_receivables)

        if current_user.can_see_costs():
            try:
                from utils.gl_tenant import active_tenant_id

                tid = active_tenant_id()

                def liquidity_balance(kind):
                    account_query = GLAccount.query.filter(
                        GLAccount.tenant_id == int(tid or 0),
                        GLAccount.is_active,
                        GLAccount.is_header == False,
                        GLAccount.liquidity_kind == kind,
                    )
                    if scoped_branch_id is not None:
                        account_query = account_query.filter(
                            GLAccount.branch_id == scoped_branch_id
                        )
                    account_ids = [acc.id for acc in account_query.all()]
                    if not account_ids:
                        return Decimal("0")
                    debit_query = db.session.query(
                        func.sum(GLJournalLine.debit)
                    ).filter(GLJournalLine.account_id.in_(account_ids))
                    credit_query = db.session.query(
                        func.sum(GLJournalLine.credit)
                    ).filter(GLJournalLine.account_id.in_(account_ids))
                    if scoped_branch_id is not None:
                        debit_query = debit_query.join(GLJournalLine.entry).filter_by(
                            branch_id=scoped_branch_id
                        )
                        credit_query = credit_query.join(GLJournalLine.entry).filter_by(
                            branch_id=scoped_branch_id
                        )
                    return (debit_query.scalar() or Decimal("0")) - (
                        credit_query.scalar() or Decimal("0")
                    )

                stats["cash_balance"] = float(liquidity_balance("cash"))
                stats["bank_balance"] = float(liquidity_balance("bank"))

                inventory_acc = get_gl_account_by_code("1140", tenant_id=tid)
                if inventory_acc:
                    inv_debit_query = db.session.query(
                        func.sum(GLJournalLine.debit)
                    ).filter_by(account_id=inventory_acc.id)
                    inv_credit_query = db.session.query(
                        func.sum(GLJournalLine.credit)
                    ).filter_by(account_id=inventory_acc.id)
                    if scoped_branch_id is not None:
                        inv_debit_query = inv_debit_query.join(
                            GLJournalLine.entry
                        ).filter_by(branch_id=scoped_branch_id)
                        inv_credit_query = inv_credit_query.join(
                            GLJournalLine.entry
                        ).filter_by(branch_id=scoped_branch_id)
                    inv_debit = inv_debit_query.scalar() or Decimal("0")
                    inv_credit = inv_credit_query.scalar() or Decimal("0")
                    stats["inventory_value_gl"] = float(inv_debit - inv_credit)
            except Exception:
                current_app.logger.exception(
                    "Failed to compute inventory GL balance for dashboard"
                )

        # Optimized query with eager loading (N+1 problem fix)
        tid = get_active_tenant_id(current_user)
        recent_sales = Sale.query.options(
            joinedload(Sale.customer), joinedload(Sale.seller)
        ).filter_by(status="confirmed")
        if tid is not None:
            recent_sales = recent_sales.filter(Sale.tenant_id == tid)
        if scoped_branch_id is not None:
            recent_sales = recent_sales.filter(Sale.branch_id == scoped_branch_id)
        recent_sales = recent_sales.order_by(Sale.sale_date.desc()).limit(10).all()

        stats["recent_sales"] = recent_sales

        if current_user.is_seller():
            my_today_sales = (
                db.session.query(func.count(Sale.id), func.sum(Sale.amount_aed))
                .filter(
                    func.date(Sale.sale_date) == today,
                    Sale.seller_id == current_user.id,
                    Sale.status == "confirmed",
                )
                .first()
            )

            stats["my_today_sales_count"] = my_today_sales[0] or 0
            stats["my_today_sales_amount"] = float(my_today_sales[1] or 0)

        stats["can_apply_discount"] = current_user.can_apply_discount()
        stats["can_edit_price"] = current_user.can_edit_price()

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
    today = datetime.now(timezone.utc).date()
    month_start = today.replace(day=1)

    stats = {}

    # Sales stats
    from models import Sale

    today_sales = (
        db.session.query(func.count(Sale.id), func.sum(Sale.amount_aed))
        .filter(
            Sale.seller_id == user.id,
            func.date(Sale.sale_date) == today,
            Sale.status == "confirmed",
        )
        .first()
    )
    stats["today_sales_count"] = today_sales[0] or 0
    stats["today_sales_amount"] = float(today_sales[1] or 0)

    month_sales = (
        db.session.query(func.count(Sale.id), func.sum(Sale.amount_aed))
        .filter(
            Sale.seller_id == user.id,
            func.date(Sale.sale_date) >= month_start,
            Sale.status == "confirmed",
        )
        .first()
    )
    stats["month_sales_count"] = month_sales[0] or 0
    stats["month_sales_amount"] = float(month_sales[1] or 0)

    total_sales = (
        db.session.query(func.count(Sale.id), func.sum(Sale.amount_aed))
        .filter(Sale.seller_id == user.id, Sale.status == "confirmed")
        .first()
    )
    stats["total_sales_count"] = total_sales[0] or 0
    stats["total_sales_amount"] = float(total_sales[1] or 0)

    # Payment stats
    from models import Payment

    payment_stats = (
        db.session.query(func.count(Payment.id), func.sum(Payment.amount_aed))
        .filter(Payment.user_id == user.id)
        .first()
    )
    stats["payments_count"] = payment_stats[0] or 0
    stats["payments_amount"] = float(payment_stats[1] or 0)

    # Recent sales
    recent_sales = (
        Sale.query.filter_by(seller_id=user.id, status="confirmed")
        .order_by(Sale.sale_date.desc())
        .limit(10)
        .all()
    )

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
    from werkzeug.security import generate_password_hash, check_password_hash
    from utils.sanitizer import InputSanitizer

    user = current_user

    try:
        with atomic_transaction("profile_update"):
            # Whitelist: only these fields may be changed by the user

            # Sanitize and update allowed fields
            if "full_name" in request.form:
                user.full_name = (
                    InputSanitizer.sanitize_text(
                        request.form.get("full_name", ""), max_length=100
                    )
                    or user.full_name
                )

            if "full_name_ar" in request.form:
                user.full_name_ar = (
                    InputSanitizer.sanitize_text(
                        request.form.get("full_name_ar", ""), max_length=100
                    )
                    or user.full_name_ar
                )

            if "email" in request.form:
                email = InputSanitizer.sanitize_email(request.form.get("email", ""))
                if email:
                    # Check email uniqueness (excluding self)
                    existing = User.query.filter(
                        User.email == email,
                        User.id != user.id,
                        User.tenant_id == user.tenant_id,
                    ).first()
                    if existing:
                        flash(
                            gettext("⚠️ هذا البريد الإلكتروني مستخدم من قبل."), "warning"
                        )
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

                user.password_hash = generate_password_hash(
                    new_password, method="pbkdf2:sha256"
                )
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
    from models.tenant import Tenant
    from models.branch import Branch

    tenant = Tenant.query.filter_by(slug=slug).first_or_404()

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

    branches = (
        Branch.query.filter_by(tenant_id=tenant.id, is_active=True)
        .order_by(Branch.name)
        .all()
    )

    # Determine if viewer is owner (for edit/delete buttons)
    from flask_login import current_user as _current_user
    from utils.auth_helpers import is_global_owner_user

    is_owner_viewer = _current_user.is_authenticated and is_global_owner_user(
        _current_user
    )

    return render_template(
        "public/tenant_profile.html",
        tenant=tenant,
        branches=branches,
        is_owner_viewer=is_owner_viewer,
    )
