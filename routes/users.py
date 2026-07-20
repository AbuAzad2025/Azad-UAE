"""User management routes — list, create, edit, activate, delete."""

from __future__ import annotations
from flask_babel import gettext

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
from flask_login import current_user, login_required

from extensions import db, limiter
from models import Branch, Role, User
from models.tenant import Tenant
from services.logging_core import LoggingCore
from utils.auth_helpers import (
    enforce_company_user_tenant,
    role_level_for,
    role_level_for_user,
)
from utils.branching import branch_scope_id_for, role_requires_branch
from utils.db_safety import atomic_transaction
from utils.decorators import permission_required
from utils.error_messages import ErrorMessages
from utils.field_validators import (
    FieldValidationError,
    normalize_phone_optional,
    normalize_user_email_required,
)
from utils.password_validator import PasswordValidator
from utils.structured_logging import log_mutation
from utils.tenant_limits import TenantLimitError, check_users_limit
from utils.tenanting import assign_tenant_id, get_active_tenant_id, scoped_user_query
from utils.username_policy import (
    is_platform_reserved,
    tenant_username_prefix,
    validate_username_for_user,
)

users_bp = Blueprint("users", __name__, url_prefix="/users")


def _available_branches():
    tid = get_active_tenant_id(current_user)
    query = Branch.query.filter_by(is_active=True)
    if tid is not None:
        query = query.filter(Branch.tenant_id == tid)
    scoped_branch_id = branch_scope_id_for(current_user)
    if scoped_branch_id is not None:
        query = query.filter(Branch.id == scoped_branch_id)
    return query.order_by(Branch.code, Branch.name).all()


def _clean_branch_id(raw_value):
    if raw_value in (None, "", "None"):
        return None
    return int(raw_value)


def _username_example():
    tid = get_active_tenant_id(current_user)
    tenant = db.session.get(Tenant, int(tid)) if tid else None
    prefix = tenant_username_prefix(tenant) if tenant else "CODE"
    return f"{prefix}_ahmad"


def _validate_user_branch(role_id, branch_id):
    role = db.session.get(Role, role_id) if role_id else None
    if not role:
        raise ValueError(gettext("يرجى اختيار الدور الوظيفي."))

    if role_requires_branch(role):
        if not branch_id:
            raise ValueError(gettext("يجب ربط هذا المستخدم بفرع محدد."))
        if not any(branch.id == branch_id for branch in _available_branches()):
            raise ValueError(gettext("الفرع المحدد خارج نطاقك أو غير نشط."))
    return role


def _ensure_user_in_scope(user):
    scoped_branch_id = branch_scope_id_for(current_user)
    if scoped_branch_id is None:
        return user
    if getattr(user, "branch_id", None) != scoped_branch_id:
        abort(403)
    return user


def _create_form_context(roles, branches, form_values):
    return render_template(
        "users/create.html",
        roles=roles,
        branches=branches,
        form_data=form_values,
        username_example=_username_example(),
    )


@users_bp.route("/")
@login_required
@permission_required("manage_users")
def index():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    search = request.args.get("search", "", type=str)

    query = scoped_user_query(exclude_owners=True, active_only=True)
    scoped_branch_id = branch_scope_id_for(current_user)
    if scoped_branch_id is not None:
        query = query.filter(User.branch_id == scoped_branch_id)

    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            db.or_(
                User.username.ilike(search_filter),
                User.email.ilike(search_filter),
                User.full_name.ilike(search_filter),
            ),
        )

    pagination = query.order_by(User.username).paginate(
        page=page,
        per_page=per_page,
        error_out=False,
    )

    return render_template(
        "users/index.html",
        users=pagination.items,
        pagination=pagination,
    )


@users_bp.route("/create", methods=["GET", "POST"])
@login_required
@permission_required("manage_users")
@limiter.limit("10 per minute", methods=["POST"])
def create():
    current_level = role_level_for_user(current_user)
    roles = Role.query.filter_by(is_active=True).all()
    roles = [r for r in roles if role_level_for(getattr(r, "slug", None)) <= current_level]
    branches = _available_branches()
    default_form = {"is_active": "1"}

    if request.method == "POST":
        form_values = request.form.to_dict()
        form_values["is_active"] = request.form.get("is_active", "1")
        try:
            role_id = request.form.get("role_id", type=int)
            if not role_id:
                flash(gettext("يرجى اختيار الدور الوظيفي."), "warning")
                return _create_form_context(roles, branches, form_values)

            is_active = request.form.get("is_active", "1") == "1"
            branch_id = _clean_branch_id(request.form.get("branch_id"))
            role = _validate_user_branch(role_id, branch_id)

            if role_level_for(getattr(role, "slug", None)) > current_level:
                flash(gettext("لا يمكنك تعيين دور أعلى من دورك."), "danger")
                return _create_form_context(roles, branches, form_values)

            username = (request.form.get("username") or "").strip()
            if is_platform_reserved(username):
                flash(gettext("اسم المستخدم محجوز للمنصة (owner / azad)."), "danger")
                return _create_form_context(roles, branches, form_values)

            tid = get_active_tenant_id(current_user)
            tenant = db.session.get(Tenant, int(tid)) if tid else None
            uname_err = validate_username_for_user(username, is_owner=False, tenant=tenant)
            if uname_err:
                prefix = tenant_username_prefix(tenant) if tenant else "CODE"
                flash(gettext(f"{uname_err}\nمثال: {prefix}_ahmad"), "danger")
                return _create_form_context(roles, branches, form_values)

            try:
                check_users_limit()
            except TenantLimitError as e:
                flash(str(e), "warning")
                return _create_form_context(roles, branches, form_values)

            conflict = User.query.filter(User.username.ilike(username)).first()
            if conflict:
                flash(gettext("اسم المستخدم مستخدم مسبقاً على مستوى النظام."), "danger")
                return _create_form_context(roles, branches, form_values)

            try:
                email = normalize_user_email_required(request.form.get("email"))
            except FieldValidationError as exc:
                flash(str(exc), "danger")
                return _create_form_context(roles, branches, form_values)

            user = User(
                username=username,
                email=email,
                full_name=request.form.get("full_name"),
                full_name_ar=request.form.get("full_name_ar"),
                phone=normalize_phone_optional(request.form.get("phone")),
                role_id=role_id,
                branch_id=branch_id,
                is_owner=False,
                is_active=is_active,
            )

            password = request.form.get("password")
            is_valid, pwd_errors = PasswordValidator.validate(password or "")
            if not is_valid:
                flash(ErrorMessages.weak_password(pwd_errors), "danger")
                return _create_form_context(roles, branches, form_values)

            user.set_password(password)
            assign_tenant_id(user)

            with atomic_transaction("user_creation"):
                db.session.add(user)
                db.session.flush()
                LoggingCore.log_audit("create", "users", user.id)

            log_mutation("create", "User", user.id, {"username": user.username})
            flash(gettext("تم إضافة المستخدم بنجاح!"), "success")
            return redirect(url_for("users.index"))

        except Exception:
            current_app.logger.exception("User creation error")
            flash(ErrorMessages.create_failed("user"), "danger")
            return _create_form_context(roles, branches, form_values)

    return render_template(
        "users/create.html",
        roles=roles,
        branches=branches,
        form_data=default_form,
        username_example=_username_example(),
    )


@users_bp.route("/<int:id>")
@login_required
@permission_required("manage_users")
def view(**kwargs):
    record_id = kwargs.pop("id")
    tid = get_active_tenant_id(current_user)
    user_query = User.query.filter_by(id=record_id, is_owner=False)
    if tid is not None:
        user_query = user_query.filter(User.tenant_id == tid)
    user = user_query.first_or_404()
    _ensure_user_in_scope(user)
    return render_template("users/view.html", user=user)


@users_bp.route("/<int:id>/edit", methods=["GET", "POST"])
@login_required
@permission_required("manage_users")
@limiter.limit("10 per minute", methods=["POST"])
def edit(**kwargs):
    record_id = kwargs.pop("id")
    tid = get_active_tenant_id(current_user)
    user_query = User.query.filter_by(id=record_id, is_owner=False)
    if tid is not None:
        user_query = user_query.filter(User.tenant_id == tid)
    user = user_query.first_or_404()
    _ensure_user_in_scope(user)

    current_level = role_level_for_user(current_user)
    roles = Role.query.filter_by(is_active=True).all()
    roles = [r for r in roles if role_level_for(getattr(r, "slug", None)) <= current_level]
    branches = _available_branches()

    if request.method == "POST":
        try:
            with atomic_transaction("user_update"):
                try:
                    user.email = normalize_user_email_required(request.form.get("email"))
                except FieldValidationError as exc:
                    flash(str(exc), "danger")
                    return render_template("users/edit.html", user=user, roles=roles, branches=branches)
                user.full_name = request.form.get("full_name")
                user.full_name_ar = request.form.get("full_name_ar")
                user.phone = normalize_phone_optional(request.form.get("phone"))
                role_id = request.form.get("role_id", type=int)
                branch_id = _clean_branch_id(request.form.get("branch_id"))
                role = _validate_user_branch(role_id, branch_id)

                if role_level_for(getattr(role, "slug", None)) > current_level:
                    flash(gettext("لا يمكنك تعيين دور أعلى من دورك."), "danger")
                    return render_template("users/edit.html", user=user, roles=roles, branches=branches)

                user.role_id = role_id
                user.branch_id = branch_id
                enforce_company_user_tenant(user, role=role, is_owner=False)

                new_password = request.form.get("new_password")
                if new_password:
                    is_valid, pwd_errors = PasswordValidator.validate(new_password)
                    if not is_valid:
                        flash(ErrorMessages.weak_password(pwd_errors), "danger")
                        return render_template("users/edit.html", user=user, roles=roles, branches=branches)
                    user.set_password(new_password)

                user.is_active = request.form.get("is_active") == "1"

                LoggingCore.log_audit("update", "users", user.id)

            flash(gettext("تم تحديث بيانات المستخدم بنجاح!"), "success")
            return redirect(url_for("users.index"))

        except Exception as e:
            current_app.logger.error("Error updating user %s: %s", record_id, e)
            flash(ErrorMessages.update_failed("user"), "danger")
            return render_template("users/edit.html", user=user, roles=roles, branches=branches)

    return render_template("users/edit.html", user=user, roles=roles, branches=branches)


@users_bp.route("/<int:id>/toggle-active", methods=["POST"])
@login_required
@permission_required("manage_users")
def toggle_active(**kwargs):
    record_id = kwargs.pop("id")
    tid = get_active_tenant_id(current_user)
    user_query = User.query.filter_by(id=record_id, is_owner=False)
    if tid is not None:
        user_query = user_query.filter(User.tenant_id == tid)
    user = user_query.first_or_404()
    _ensure_user_in_scope(user)

    with atomic_transaction("user_toggle_active"):
        user.is_active = not user.is_active
        LoggingCore.log_audit("toggle_active", "users", user.id)

    status_msg = gettext("تفعيل") if user.is_active else gettext("إلغاء تفعيل")
    flash(gettext(f'تم {status_msg} المستخدم "{user.username}" بنجاح!'), "success")

    return redirect(url_for("users.index"))


@users_bp.route("/<int:id>/delete", methods=["POST"])
@login_required
@permission_required("manage_users")
def delete(**kwargs):
    record_id = kwargs.pop("id")
    tid = get_active_tenant_id(current_user)
    user_query = User.query.filter_by(id=record_id, is_owner=False)
    if tid is not None:
        user_query = user_query.filter(User.tenant_id == tid)
    user = user_query.first_or_404()
    _ensure_user_in_scope(user)

    current_level = role_level_for_user(current_user)
    target_role = getattr(user, "role", None)
    target_slug = getattr(target_role, "slug", None) if target_role else None
    if role_level_for(target_slug) > current_level:
        flash(gettext("لا يمكنك حذف مستخدم بدور أعلى من دورك."), "danger")
        return redirect(url_for("users.index"))

    if user.id == current_user.id:
        flash(
            gettext("لا يمكنك حذف حسابك الخاص. اطلب من مدير آخر حذف حسابك إذا لزم الأمر."),
            "danger",
        )
        return redirect(url_for("users.index"))

    try:
        with atomic_transaction("user_delete"):
            from models import Sale

            sales_query = Sale.query.filter_by(seller_id=record_id)
            if tid is not None:
                sales_query = sales_query.filter(Sale.tenant_id == tid)
            sales_count = sales_query.count()

            has_sales = sales_count > 0
            if has_sales:
                user.is_active = False
                LoggingCore.log_audit("deactivate", "users", record_id)
            else:
                db.session.delete(user)
                LoggingCore.log_audit("delete", "users", record_id)

        if has_sales:
            flash(
                gettext(f'تم إلغاء تفعيل المستخدم "{user.username}" (لديه {sales_count} عملية مسجلة). '),
                gettext("لا يمكن حذفه نهائياً للحفاظ على السجلات."),
                "warning",
            )
        else:
            flash(gettext(f'تم حذف المستخدم "{user.username}" نهائياً!'), "success")

        return redirect(url_for("users.index"))

    except Exception as e:
        current_app.logger.error("Error deleting user %s: %s", id, e)
        flash(ErrorMessages.delete_failed("user"), "danger")
        return redirect(url_for("users.index"))
