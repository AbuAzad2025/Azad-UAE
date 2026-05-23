from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from extensions import db
from models import Branch
from utils.decorators import admin_required
from utils.tenanting import get_active_tenant_id

branches_bp = Blueprint('branches', __name__, url_prefix='/branches')

@branches_bp.route('/')
@login_required
@admin_required
def index():
    tenant_id = get_active_tenant_id(current_user)
    q = Branch.query
    if tenant_id is not None:
        q = q.filter(Branch.tenant_id == tenant_id)
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
        phone = request.form.get('phone')
        is_main = request.form.get('is_main') == 'on'
        
        if not name or not code:
            flash('الاسم والكود مطلوبان', 'danger')
            return redirect(url_for('branches.create'))
            
        # Check if code exists
        if Branch.query.filter_by(code=code).first():
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
        
        db.session.add(branch)
        db.session.commit()
        
        flash('تم إضافة الفرع بنجاح', 'success')
        return redirect(url_for('branches.index'))
        
    return render_template('branches/create.html')

@branches_bp.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit(id):
    branch = Branch.query.get_or_404(id)
    tenant_id = get_active_tenant_id(current_user)
    if tenant_id is not None and branch.tenant_id != tenant_id:
        abort(404)
    
    if request.method == 'POST':
        branch.name = request.form.get('name')
        branch.city = request.form.get('city')
        branch.address = request.form.get('address')
        branch.phone = request.form.get('phone')
        branch.is_main = request.form.get('is_main') == 'on'
        
        db.session.commit()
        
        flash('تم تحديث الفرع بنجاح', 'success')
        return redirect(url_for('branches.index'))
        
    return render_template('branches/edit.html', branch=branch)

@branches_bp.route('/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete(id):
    branch = Branch.query.get_or_404(id)
    tenant_id = get_active_tenant_id(current_user)
    if tenant_id is not None and branch.tenant_id != tenant_id:
        abort(404)
    
    # Check for related data before deletion
    # This is a basic check. In a real system, you might want to soft-delete or strict check.
    if branch.users or branch.warehouses or branch.sales:
        flash('لا يمكن حذف الفرع لوجود بيانات مرتبطة به (مستخدمين، مستودعات، أو مبيعات)', 'danger')
        return redirect(url_for('branches.index'))
        
    db.session.delete(branch)
    db.session.commit()
    flash('تم حذف الفرع بنجاح', 'success')
    return redirect(url_for('branches.index'))
