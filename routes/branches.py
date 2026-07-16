from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from extensions import db
from models import Branch
from utils.decorators import admin_required
from utils.tenanting import get_active_tenant_id, tenant_query, tenant_get_or_404
from utils.db_safety import atomic_transaction

branches_bp = Blueprint('branches', __name__, url_prefix='/branches')


def _sync_branch_financial_accounts(tenant_id):
    from services.gl_service import GLService

    GLService.ensure_core_accounts(tenant_id=tenant_id)


@branches_bp.route('/')
@login_required
@admin_required
def index():
    tenant_id = get_active_tenant_id(current_user)
    q = tenant_query(Branch)
    branches = q.order_by(Branch.is_main.desc(), Branch.code, Branch.name).all()
    return render_template('branches/index.html', branches=branches)

@branches_bp.route('/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create():
    if request.method == 'POST':
        name = request.form.get('name')
        code = request.form.get('code')
        city = request.form.get('city')
        address = request.form.get('address')
        from utils.field_validators import normalize_phone_optional

        phone = normalize_phone_optional(request.form.get('phone'))
        is_main = request.form.get('is_main') == 'on'

        if not name or not code:
            flash('الاسم والكود مطلوبان', 'danger')
            return redirect(url_for('branches.create'))

        # Check tenant branch limit
        from utils.tenant_limits import check_branches_limit, TenantLimitError
        try:
            check_branches_limit()
        except TenantLimitError as e:
            flash(str(e), 'warning')
            return redirect(url_for('branches.create'))

        if tenant_query(Branch).filter_by(code=code).first():
            flash('الكود مستخدم مسبقاً', 'danger')
            return redirect(url_for('branches.create'))

        branch = Branch(
            tenant_id=get_active_tenant_id(current_user),
            name=name,
            code=code,
            city=city,
            address=address,
            phone=phone,
            is_main=is_main
        )

        with atomic_transaction('branch_create'):
            db.session.add(branch)
            db.session.flush()
            _sync_branch_financial_accounts(branch.tenant_id)

        flash('تم إضافة الفرع بنجاح', 'success')
        return redirect(url_for('branches.index'))

    return render_template('branches/create.html')

@branches_bp.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit(id):  # noqa: A002
    branch = tenant_get_or_404(Branch, id)

    if request.method == 'POST':
        branch.name = request.form.get('name')
        branch.city = request.form.get('city')
        branch.address = request.form.get('address')
        from utils.field_validators import normalize_phone_optional

        branch.phone = normalize_phone_optional(request.form.get('phone'))
        branch.is_main = request.form.get('is_main') == 'on'
        raw_piv = request.form.get('prices_include_vat')
        branch.prices_include_vat = True if raw_piv == 'on' else (False if raw_piv == 'off' else None)

        with atomic_transaction('branch_update'):
            db.session.flush()
            _sync_branch_financial_accounts(branch.tenant_id)

        flash('تم تحديث الفرع بنجاح', 'success')
        return redirect(url_for('branches.index'))

    return render_template('branches/edit.html', branch=branch)

@branches_bp.route('/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete(id):  # noqa: A002
    branch = tenant_get_or_404(Branch, id)

    # Check for related data before deletion
    # This is a basic check. In a real system, you might want to soft-delete or strict check.
    if branch.users or branch.warehouses or branch.sales:
        flash('لا يمكن حذف الفرع لوجود بيانات مرتبطة به (مستخدمين، مستودعات، أو مبيعات)', 'danger')
        return redirect(url_for('branches.index'))

    with atomic_transaction('branch_delete'):
        db.session.delete(branch)
    flash('تم حذف الفرع بنجاح', 'success')
    return redirect(url_for('branches.index'))
