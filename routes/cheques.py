"""
مسارات الشيكات - Cheques Routes
إدارة الشيكات الواردة والصادرة
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from extensions import db, limiter
from models import Cheque, Customer, Supplier, Sale, Receipt, Expense
from services.currency_service import CurrencyService
from utils.decorators import admin_required, permission_required, branch_scope_id
from utils.branching import should_show_all_branch_columns
from utils.helpers import create_audit_log, generate_number
from datetime import datetime, timedelta
from decimal import Decimal

cheques_bp = Blueprint('cheques', __name__, url_prefix='/cheques')


def _scoped_cheques_query():
    query = Cheque.query.filter_by(is_active=True)
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None:
        query = query.filter(Cheque.branch_id == scoped_branch_id)
    return query


def _ensure_cheque_scope(cheque):
    scoped_branch_id = branch_scope_id()
    return scoped_branch_id is None or cheque.branch_id == scoped_branch_id


def _scoped_customers_query():
    from models import Payment
    from sqlalchemy import select

    scoped_branch_id = branch_scope_id()
    query = Customer.query.filter(Customer.is_active == True)
    if scoped_branch_id is None:
        return query

    sale_ids = select(Sale.customer_id).where(
        Sale.customer_id.isnot(None),
        Sale.branch_id == scoped_branch_id,
    )
    payment_ids = select(Payment.customer_id).where(
        Payment.customer_id.isnot(None),
        Payment.branch_id == scoped_branch_id,
    )
    receipt_ids = select(Receipt.customer_id).where(
        Receipt.customer_id.isnot(None),
        Receipt.branch_id == scoped_branch_id,
    )
    return query.filter(Customer.id.in_(sale_ids.union(payment_ids, receipt_ids)))


def _scoped_suppliers_query():
    from models import Payment, Purchase
    from sqlalchemy import select

    scoped_branch_id = branch_scope_id()
    query = Supplier.query.filter(Supplier.is_active == True)
    if scoped_branch_id is None:
        return query

    purchase_ids = select(Purchase.supplier_id).where(
        Purchase.supplier_id.isnot(None),
        Purchase.branch_id == scoped_branch_id,
    )
    payment_ids = select(Payment.supplier_id).where(
        Payment.supplier_id.isnot(None),
        Payment.branch_id == scoped_branch_id,
    )
    return query.filter(Supplier.id.in_(purchase_ids.union(payment_ids)))


@cheques_bp.route('/')
@login_required
@permission_required('manage_payments')
def index():
    """قائمة كل الشيكات"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)
    cheque_type = request.args.get('type', '', type=str)
    status = request.args.get('status', '', type=str)
    search = request.args.get('search', '', type=str)
    
    # تحديث حالة كل الشيكات
    scoped_branch_id = branch_scope_id()
    Cheque.update_all_statuses(branch_id=scoped_branch_id)
    
    query = _scoped_cheques_query()
    
    if cheque_type:
        query = query.filter_by(cheque_type=cheque_type)
    
    if status:
        query = query.filter_by(status=status)
    
    if search:
        search_filter = f'%{search}%'
        query = query.filter(
            db.or_(
                Cheque.cheque_number.ilike(search_filter),
                Cheque.cheque_bank_number.ilike(search_filter),
                Cheque.bank_name.ilike(search_filter),
                Cheque.drawer_name.ilike(search_filter),
                Cheque.payee_name.ilike(search_filter)
            )
        )
    
    pagination = query.order_by(Cheque.due_date).paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )
    
    stats = Cheque.get_statistics(branch_id=scoped_branch_id)
    
    return render_template('cheques/index.html',
                         cheques=pagination.items,
                         pagination=pagination,
                         stats=stats,
                         show_branch_columns=should_show_all_branch_columns(current_user))


@cheques_bp.route('/incoming')
@login_required
@permission_required('manage_payments')
def incoming():
    """الشيكات الواردة"""
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', '', type=str)
    
    scoped_branch_id = branch_scope_id()
    Cheque.update_all_statuses(branch_id=scoped_branch_id)
    
    query = _scoped_cheques_query().filter_by(cheque_type='incoming')
    
    if status:
        query = query.filter_by(status=status)
    
    pagination = query.order_by(Cheque.due_date).paginate(
        page=page,
        per_page=25,
        error_out=False
    )
    
    stats = Cheque.get_statistics(branch_id=scoped_branch_id)
    
    return render_template('cheques/incoming.html',
                         cheques=pagination.items,
                         pagination=pagination,
                         stats=stats)


@cheques_bp.route('/outgoing')
@login_required
@permission_required('manage_payments')
def outgoing():
    """الشيكات الصادرة"""
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', '', type=str)
    
    scoped_branch_id = branch_scope_id()
    Cheque.update_all_statuses(branch_id=scoped_branch_id)
    
    query = _scoped_cheques_query().filter_by(cheque_type='outgoing')
    
    if status:
        query = query.filter_by(status=status)
    
    pagination = query.order_by(Cheque.due_date).paginate(
        page=page,
        per_page=25,
        error_out=False
    )
    
    stats = Cheque.get_statistics(branch_id=scoped_branch_id)
    
    return render_template('cheques/outgoing.html',
                         cheques=pagination.items,
                         pagination=pagination,
                         stats=stats)


@cheques_bp.route('/create', methods=['GET', 'POST'])
@login_required
@permission_required('manage_payments')
@limiter.limit("10 per minute", methods=['POST'])
def create():
    """إضافة شيك جديد"""
    if request.method == 'POST':
        try:
            cheque_branch_id = branch_scope_id() or getattr(current_user, 'branch_id', None)
            cheque_number = generate_number('CHQ', Cheque, 'cheque_number', branch_id=cheque_branch_id)
            
            cheque_type = (request.form.get('cheque_type') or '').strip()
            if not cheque_type:
                flash('⚠️ يرجى اختيار نوع الشيك.', 'warning')
                customers = _scoped_customers_query().order_by(Customer.name).all()
                suppliers = _scoped_suppliers_query().order_by(Supplier.name).all()
                exchange_rates = CurrencyService.get_all_rates('AED')
                return render_template('cheques/create.html',
                                     customers=customers,
                                     suppliers=suppliers,
                                     exchange_rates=exchange_rates)
            amount = Decimal(str(request.form.get('amount')))
            currency = request.form.get('currency', 'AED')
            
            # حساب سعر الصرف
            exchange_rate = CurrencyService.get_exchange_rate(
                currency,
                'AED',
                user_rate=request.form.get('exchange_rate', type=float)
            )
            
            # تحويل التواريخ
            issue_date = datetime.strptime(request.form.get('issue_date'), '%Y-%m-%d').date()
            due_date = datetime.strptime(request.form.get('due_date'), '%Y-%m-%d').date()
            customer_id = request.form.get('customer_id', type=int) or None
            supplier_id = request.form.get('supplier_id', type=int) or None
            if customer_id and not _scoped_customers_query().filter(Customer.id == customer_id).first():
                flash('⚠️ العميل المحدد خارج نطاق الفرع الحالي.', 'warning')
                customers = _scoped_customers_query().order_by(Customer.name).all()
                suppliers = _scoped_suppliers_query().order_by(Supplier.name).all()
                exchange_rates = CurrencyService.get_all_rates('AED')
                return render_template('cheques/create.html',
                                     customers=customers,
                                     suppliers=suppliers,
                                     exchange_rates=exchange_rates)
            if supplier_id and not _scoped_suppliers_query().filter(Supplier.id == supplier_id).first():
                flash('⚠️ المورد المحدد خارج نطاق الفرع الحالي.', 'warning')
                customers = _scoped_customers_query().order_by(Customer.name).all()
                suppliers = _scoped_suppliers_query().order_by(Supplier.name).all()
                exchange_rates = CurrencyService.get_all_rates('AED')
                return render_template('cheques/create.html',
                                     customers=customers,
                                     suppliers=suppliers,
                                     exchange_rates=exchange_rates)
            
            cheque = Cheque(
                cheque_number=cheque_number,
                cheque_bank_number=request.form.get('cheque_bank_number'),
                cheque_type=cheque_type,
                bank_name=request.form.get('bank_name'),
                bank_branch=request.form.get('bank_branch'),
                account_number=request.form.get('account_number'),
                amount=amount,
                currency=currency,
                exchange_rate=exchange_rate,
                issue_date=issue_date,
                due_date=due_date,
                drawer_name=request.form.get('drawer_name'),
                drawer_id_number=request.form.get('drawer_id_number'),
                payee_name=request.form.get('payee_name'),
                customer_id=customer_id,
                supplier_id=supplier_id,
                notes=request.form.get('notes'),
                user_id=current_user.id,
                branch_id=cheque_branch_id,
            )
            
            cheque.calculate_amount_aed()
            cheque.update_status_based_on_date()
            
            db.session.add(cheque)
            db.session.commit()
            
            # إنشاء القيد المحاسبي الأولي
            try:
                if cheque.cheque_type == 'incoming':
                    cheque.receive_cheque()
                elif cheque.cheque_type == 'outgoing':
                    cheque.issue_cheque()
                db.session.commit()
            except Exception as e:
                current_app.logger.error(f"Failed to create initial GL entry for cheque {cheque.id}: {e}")
            
            create_audit_log('create', 'cheques', cheque.id)
            
            flash(f'✅ تم إضافة الشيك {cheque.cheque_bank_number} بنجاح', 'success')
            return redirect(url_for('cheques.view', id=cheque.id))
        
        except Exception as e:
            db.session.rollback()
            flash(f'❌ خطأ: {str(e)}\n💡 تحقق من البيانات وحاول مرة أخرى.', 'danger')
    
    customers = _scoped_customers_query().order_by(Customer.name).all()
    suppliers = _scoped_suppliers_query().order_by(Supplier.name).all()
    exchange_rates = CurrencyService.get_all_rates('AED')
    
    return render_template('cheques/create.html',
                         customers=customers,
                         suppliers=suppliers,
                         exchange_rates=exchange_rates)


@cheques_bp.route('/<int:id>')
@login_required
@permission_required('manage_payments')
def view(id):
    """عرض تفاصيل الشيك"""
    cheque = Cheque.query.get_or_404(id)
    if not _ensure_cheque_scope(cheque):
        return render_template('errors/403.html'), 403
    cheque.update_status_based_on_date()
    db.session.commit()
    
    # إضافة today للـ template
    today = datetime.now().strftime('%Y-%m-%d')
    
    return render_template('cheques/view.html', cheque=cheque, today=today)


@cheques_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@permission_required('manage_payments')
def edit(id):
    """تعديل الشيك"""
    cheque = Cheque.query.get_or_404(id)
    if not _ensure_cheque_scope(cheque):
        return render_template('errors/403.html'), 403
    
    # لا يمكن تعديل شيك تم صرفه أو ملغي
    if cheque.status in ['cleared', 'cancelled', 'bounced']:
        flash('⚠️ لا يمكن تعديل شيك تم صرفه أو إلغاؤه.\n💡 الشيكات المصروفة أو الملغاة لا يمكن تعديلها للحفاظ على السجلات.', 'danger')
        return redirect(url_for('cheques.view', id=id))
    
    if request.method == 'POST':
        try:
            cheque.cheque_bank_number = request.form.get('cheque_bank_number')
            cheque.bank_name = request.form.get('bank_name')
            cheque.bank_branch = request.form.get('bank_branch')
            cheque.account_number = request.form.get('account_number')
            
            cheque.amount = Decimal(str(request.form.get('amount')))
            cheque.currency = request.form.get('currency', 'AED')
            
            exchange_rate = CurrencyService.get_exchange_rate(
                cheque.currency,
                'AED',
                user_rate=request.form.get('exchange_rate', type=float)
            )
            cheque.exchange_rate = exchange_rate
            
            cheque.issue_date = datetime.strptime(request.form.get('issue_date'), '%Y-%m-%d').date()
            cheque.due_date = datetime.strptime(request.form.get('due_date'), '%Y-%m-%d').date()
            
            cheque.drawer_name = request.form.get('drawer_name')
            cheque.drawer_id_number = request.form.get('drawer_id_number')
            cheque.payee_name = request.form.get('payee_name')
            cheque.notes = request.form.get('notes')
            
            cheque.calculate_amount_aed()
            cheque.update_status_based_on_date()
            
            db.session.commit()
            
            create_audit_log('update', 'cheques', id)
            
            flash('✅ تم تحديث الشيك بنجاح', 'success')
            return redirect(url_for('cheques.view', id=id))
        
        except Exception as e:
            db.session.rollback()
            flash(f'❌ خطأ: {str(e)}\n💡 تحقق من البيانات وحاول مرة أخرى.', 'danger')
    
    customers = _scoped_customers_query().order_by(Customer.name).all()
    suppliers = _scoped_suppliers_query().order_by(Supplier.name).all()
    exchange_rates = CurrencyService.get_all_rates('AED')
    
    return render_template('cheques/edit.html',
                         cheque=cheque,
                         customers=customers,
                         suppliers=suppliers,
                         exchange_rates=exchange_rates)


@cheques_bp.route('/<int:id>/deposit', methods=['POST'])
@login_required
@permission_required('manage_payments')
def deposit_cheque(id):
    """إيداع الشيك في البنك - الخطوة 1"""
    cheque = Cheque.query.get_or_404(id)
    if not _ensure_cheque_scope(cheque):
        return render_template('errors/403.html'), 403
    
    try:
        deposit_date_str = request.form.get('deposit_date')
        deposit_date = datetime.strptime(deposit_date_str, '%Y-%m-%d').date() if deposit_date_str else None
        
        cheque.deposit_cheque(deposit_date)
        db.session.commit()
        
        create_audit_log('cheque_deposit', 'cheques', id, 
                        f'إيداع شيك رقم {cheque.cheque_bank_number} في البنك')
        
        flash(f'✅ تم إيداع الشيك {cheque.cheque_bank_number} في البنك', 'success')
    
    except ValueError as e:
        flash(f'❌ خطأ: {str(e)}', 'error')
        db.session.rollback()
    except Exception as e:
        db.session.rollback()
        flash(f'❌ خطأ: {str(e)}\n💡 تحقق من البيانات وحاول مرة أخرى.', 'danger')
    
    return redirect(url_for('cheques.view', id=id))


@cheques_bp.route('/<int:id>/clear', methods=['POST'])
@login_required
@permission_required('manage_payments')
def clear_cheque(id):
    """تأكيد صرف الشيك من البنك - الخطوة 2 - المحاسبة الفعلية"""
    cheque = Cheque.query.get_or_404(id)
    if not _ensure_cheque_scope(cheque):
        return render_template('errors/403.html'), 403
    
    try:
        clearance_date_str = request.form.get('clearance_date')
        clearance_date = datetime.strptime(clearance_date_str, '%Y-%m-%d').date() if clearance_date_str else None
        
        # سعر الصرف وقت الصرف (اختياري)
        clearance_exchange_rate = request.form.get('clearance_exchange_rate', type=float)
        
        # تأكيد الصرف - هنا تحدث المحاسبة!
        cheque.clear_cheque(clearance_date, clearance_exchange_rate)
        db.session.commit()
        
        # رسالة مفصلة عند وجود فرق عملة
        if cheque.currency_gain_loss and abs(cheque.currency_gain_loss) > Decimal('0.01'):
            if cheque.currency_gain_loss > 0:
                gain_loss_msg = f' - تم تحقيق ربح من فرق العملة: +{cheque.currency_gain_loss:.2f} AED'
            else:
                gain_loss_msg = f' - خسارة من فرق العملة: {cheque.currency_gain_loss:.2f} AED'
        else:
            gain_loss_msg = ''
        
        create_audit_log('cheque_clear', 'cheques', id,
                        f'تأكيد صرف شيك رقم {cheque.cheque_bank_number} من البنك - تم تحديث الحسابات{gain_loss_msg}')
        
        flash(f'✅ تم تأكيد صرف الشيك {cheque.cheque_bank_number} - تم تحديث الحسابات المالية{gain_loss_msg}', 'success')
    
    except ValueError as e:
        flash(f'❌ خطأ: {str(e)}', 'error')
        db.session.rollback()
    except Exception as e:
        db.session.rollback()
        flash(f'❌ خطأ: {str(e)}\n💡 تحقق من البيانات وحاول مرة أخرى.', 'danger')
    
    return redirect(url_for('cheques.view', id=id))


@cheques_bp.route('/<int:id>/bounce', methods=['POST'])
@login_required
@permission_required('manage_payments')
def bounce_cheque(id):
    """رفض الشيك من البنك - إرجاع الدين"""
    cheque = Cheque.query.get_or_404(id)
    if not _ensure_cheque_scope(cheque):
        return render_template('errors/403.html'), 403
    
    try:
        reason = request.form.get('bounce_reason', 'غير محدد')
        details = request.form.get('bounce_details', '')
        full_reason = f"{reason}. {details}" if details else reason
        
        # رفض الشيك - إرجاع الدين
        cheque.bounce_cheque(full_reason)
        db.session.commit()
        
        create_audit_log('cheque_bounce', 'cheques', id,
                        f'رفض شيك رقم {cheque.cheque_bank_number}: {full_reason}')
        
        flash(f'❌ تم رفض الشيك {cheque.cheque_bank_number} - تم إرجاع الدين للزبون', 'warning')
    
    except ValueError as e:
        flash(f'❌ خطأ: {str(e)}', 'error')
        db.session.rollback()
    except Exception as e:
        db.session.rollback()
        flash(f'❌ خطأ: {str(e)}\n💡 تحقق من البيانات وحاول مرة أخرى.', 'danger')
    
    return redirect(url_for('cheques.view', id=id))


@cheques_bp.route('/<int:id>/cancel', methods=['POST'])
@login_required
@admin_required
def cancel(id):
    """إلغاء الشيك"""
    cheque = Cheque.query.get_or_404(id)
    if not _ensure_cheque_scope(cheque):
        return render_template('errors/403.html'), 403
    
    if cheque.status == 'cleared':
        flash('⚠️ لا يمكن إلغاء شيك تم صرفه.\n💡 الشيك تم صرفه بالفعل. لا يمكن التراجع عنه.', 'danger')
        return redirect(url_for('cheques.view', id=id))
    
    try:
        reason = request.form.get('cancel_reason')
        
        cheque.cancel_cheque(reason)
        db.session.commit()
        
        create_audit_log('cancel', 'cheques', id)
        
        flash(f'✅ تم إلغاء الشيك {cheque.cheque_bank_number}', 'success')
    
    except Exception as e:
        db.session.rollback()
        flash(f'❌ خطأ: {str(e)}\n💡 تحقق من البيانات وحاول مرة أخرى.', 'danger')
    
    return redirect(url_for('cheques.view', id=id))


@cheques_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete(id):
    """حذف (أرشفة) الشيك"""
    cheque = Cheque.query.get_or_404(id)
    if not _ensure_cheque_scope(cheque):
        return render_template('errors/403.html'), 403
    
    # التحقق من الارتباطات
    has_links = False
    
    # 1. حالة الشيك (إذا لم يكن معلقاً، فهو جزء من التاريخ)
    if cheque.status in ['cleared', 'deposited', 'bounced', 'cancelled', 'under_collection']:
        has_links = True
        
    # 2. ارتباطات بكيانات أخرى
    if cheque.receipt_id or cheque.payment_id or cheque.sale_id or cheque.purchase_id or cheque.expense_id:
        has_links = True
        
    try:
        if has_links:
            # أرشفة (Soft Delete)
            reason = request.form.get('delete_reason', 'أرشفة بسبب وجود ارتباطات')
            
            # عكس القيد المحاسبي إذا كان نشطاً (يتم داخل دالة archive)
            cheque.archive(reason)
            db.session.commit()
            
            create_audit_log('archive', 'cheques', id)
            flash(f'✅ تم أرشفة الشيك {cheque.cheque_bank_number} (لوجود ارتباطات)', 'warning')
            
        else:
            # حذف نهائي (Hard Delete)
            # حذف القيود المحاسبية المرتبطة
            from models import GLJournalEntry
            
            ref_types = ['cheque_receive', 'cheque_issue', 'cheque_cancel', 'cheque_clear', 'cheque_bounce', 'Cheque']
            GLJournalEntry.query.filter(
                GLJournalEntry.reference_type.in_(ref_types),
                GLJournalEntry.reference_id == cheque.id
            ).delete(synchronize_session=False)
            
            # حذف الشيك
            db.session.delete(cheque)
            db.session.commit()
            
            create_audit_log('delete', 'cheques', id)
            flash(f'✅ تم حذف الشيك {cheque.cheque_bank_number} نهائياً', 'success')
            
        return redirect(url_for('cheques.index'))
    
    except Exception as e:
        db.session.rollback()
        flash(f'❌ خطأ: {str(e)}\n💡 تحقق من البيانات وحاول مرة أخرى.', 'danger')
        return redirect(url_for('cheques.view', id=id))


@cheques_bp.route('/<int:id>/restore', methods=['POST'])
@login_required
@admin_required
def restore(id):
    """استعادة شيك من الأرشيف"""
    cheque = Cheque.query.get_or_404(id)
    if not _ensure_cheque_scope(cheque):
        return render_template('errors/403.html'), 403
    
    try:
        cheque.restore()
        db.session.commit()
        
        create_audit_log('restore', 'cheques', id)
        
        flash(f'✅ تم استعادة الشيك {cheque.cheque_bank_number}', 'success')
    
    except Exception as e:
        db.session.rollback()
        flash(f'❌ خطأ: {str(e)}\n💡 تحقق من البيانات وحاول مرة أخرى.', 'danger')
    
    return redirect(url_for('cheques.view', id=id))


@cheques_bp.route('/alerts')
@login_required
@permission_required('manage_payments')
def alerts():
    """تنبيهات الشيكات"""
    scoped_branch_id = branch_scope_id()
    Cheque.update_all_statuses(branch_id=scoped_branch_id)
    
    due_soon = Cheque.get_due_soon_cheques(branch_id=scoped_branch_id)
    overdue = Cheque.get_overdue_cheques(branch_id=scoped_branch_id)
    bounced = Cheque.query.filter_by(status='bounced', is_active=True)
    if scoped_branch_id is not None:
        bounced = bounced.filter(Cheque.branch_id == scoped_branch_id)
    bounced = bounced.all()
    
    stats = Cheque.get_statistics(branch_id=scoped_branch_id)
    
    return render_template('cheques/alerts.html',
                         due_soon=due_soon,
                         overdue=overdue,
                         bounced=bounced,
                         stats=stats,
                         show_branch_columns=should_show_all_branch_columns(current_user))


@cheques_bp.route('/archived')
@login_required
@admin_required
def archived():
    """الشيكات المؤرشفة"""
    page = request.args.get('page', 1, type=int)

    query = Cheque.query.filter_by(is_active=False)
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None:
        query = query.filter(Cheque.branch_id == scoped_branch_id)

    pagination = query.order_by(
        Cheque.archived_at.desc()
    ).paginate(page=page, per_page=25, error_out=False)
    
    return render_template('cheques/archived.html',
                         cheques=pagination.items,
                         pagination=pagination)


@cheques_bp.route('/api/stats')
@login_required
@permission_required('manage_payments')
def api_stats():
    """API للإحصائيات"""
    scoped_branch_id = branch_scope_id()
    Cheque.update_all_statuses(branch_id=scoped_branch_id)
    stats = Cheque.get_statistics(branch_id=scoped_branch_id)
    return jsonify(stats)


@cheques_bp.route('/api/alerts')
@login_required
@permission_required('manage_payments')
def api_alerts():
    """API للتنبيهات"""
    scoped_branch_id = branch_scope_id()
    Cheque.update_all_statuses(branch_id=scoped_branch_id)
    
    due_soon = Cheque.get_due_soon_cheques(branch_id=scoped_branch_id)
    overdue = Cheque.get_overdue_cheques(branch_id=scoped_branch_id)
    
    return jsonify({
        'due_soon': len(due_soon),
        'overdue': len(overdue),
        'cheques_due_soon': [c.to_dict() for c in due_soon[:5]],
        'cheques_overdue': [c.to_dict() for c in overdue[:5]],
    })

