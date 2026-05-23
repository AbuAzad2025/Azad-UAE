from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify
from flask_login import login_required, current_user
from extensions import db, limiter
from models import Expense, ExpenseCategory, Cheque
from services.currency_service import CurrencyService
from services.gl_service import GLService
from utils.decorators import permission_required, branch_scope_id
from utils.branching import should_show_all_branch_columns
from utils.helpers import create_audit_log, generate_number
from decimal import Decimal
from datetime import datetime

expenses_bp = Blueprint('expenses', __name__, url_prefix='/expenses')


def _expense_in_scope(expense):
    scoped_branch_id = branch_scope_id()
    return scoped_branch_id is None or expense.branch_id == scoped_branch_id


@expenses_bp.route('/')
@login_required
@permission_required('manage_expenses')
def index():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    category_id = request.args.get('category', type=int)
    
    query = Expense.query.filter_by(status='confirmed')
    
    # إخفاء المصروفات المؤرشفة
    from models import ArchivedRecord
    from sqlalchemy import select
    archived_expenses = select(ArchivedRecord.record_id).filter(
        ArchivedRecord.table_name == 'expenses'
    ).scalar_subquery()
    query = query.filter(~Expense.id.in_(archived_expenses))
    
    if category_id:
        query = query.filter_by(category_id=category_id)
    from utils.decorators import branch_scope_id
    branch_id = branch_scope_id()
    if branch_id is not None:
        query = query.filter(Expense.branch_id == branch_id)
    pagination = query.order_by(Expense.expense_date.desc()).paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )
    
    categories = ExpenseCategory.query.filter_by(is_active=True).all()
    
    return render_template('expenses/index.html',
                         expenses=pagination.items,
                         pagination=pagination,
                         categories=categories,
                         show_branch_columns=should_show_all_branch_columns(current_user))


@expenses_bp.route('/create', methods=['GET', 'POST'])
@login_required
@permission_required('manage_expenses')
@limiter.limit("10 per minute", methods=['POST'])
def create():
    if request.method == 'POST':
        try:
            expense_branch_id = branch_scope_id() or getattr(current_user, 'branch_id', None)
            expense_number = generate_number('EXP', Expense, 'expense_number', branch_id=expense_branch_id)
            
            currency = request.form.get('currency', 'AED')
            user_exchange_rate = request.form.get('exchange_rate', type=float)
            
            exchange_rate = CurrencyService.get_exchange_rate(
                currency,
                'AED',
                user_rate=user_exchange_rate
            )
            
            amount = Decimal(str(request.form.get('amount')))
            
            cheque_date_str = request.form.get('cheque_date')
            cheque_date_obj = None
            if cheque_date_str:
                try:
                    cheque_date_obj = datetime.strptime(cheque_date_str, '%Y-%m-%d').date()
                except ValueError:
                    pass

            expense = Expense(
                expense_number=expense_number,
                category_id=request.form.get('category_id', type=int),
                description=request.form.get('description'),
                description_ar=request.form.get('description_ar'),
                amount=amount,
                currency=currency,
                exchange_rate=exchange_rate,
                amount_aed=amount * exchange_rate,
                payment_method=request.form.get('payment_method'),
                reference_number=request.form.get('reference_number'),
                cheque_number=request.form.get('cheque_number'),
                cheque_date=cheque_date_obj,
                bank_name=request.form.get('bank_name'),
                supplier_name=request.form.get('supplier_name'),
                notes=request.form.get('notes'),
                user_id=current_user.id,
                branch_id=expense_branch_id
            )
            
            db.session.add(expense)
            db.session.flush()
            
            # Handle Cheque Creation
            cheque = None
            if expense.payment_method == 'cheque':
                cheque_date_str = request.form.get('cheque_date')
                cheque_date_val = datetime.strptime(cheque_date_str, '%Y-%m-%d').date() if cheque_date_str else datetime.now().date()
                
                cheque = Cheque(
                    cheque_number=expense.cheque_number or f'CHQ-{expense.expense_number}',
                    cheque_bank_number=expense.cheque_number or f'CHQ-{expense.expense_number}',
                    cheque_type='outgoing',
                    bank_name=expense.bank_name or 'Unknown',
                    amount=expense.amount,
                    currency=expense.currency,
                    exchange_rate=expense.exchange_rate,
                    amount_aed=expense.amount_aed,
                    issue_date=datetime.now().date(),
                    due_date=cheque_date_val,
                    status='pending',
                    payee_name=expense.supplier_name or 'Expense Payment',
                    expense_id=expense.id,
                    notes=expense.notes,
                    user_id=current_user.id,
                    branch_id=expense.branch_id,
                )
                db.session.add(cheque)
                db.session.flush()
            
            try:
                GLService.ensure_core_accounts()
                
                category = expense.category
                expense_account = category.gl_account_code if category and category.gl_account_code else '6990'
                
                # Determine Payment Account
                if expense.payment_method == 'cash':
                    payment_account = '1110'
                elif expense.payment_method == 'cheque':
                    payment_account = '2110'  # Accounts Payable (cleared by Cheque Issue)
                else:
                    payment_account = '1120'
                
                lines = [
                    {'account': expense_account, 'debit': expense.amount, 'description': expense.description},
                    {'account': payment_account, 'credit': expense.amount, 'description': f'دفع {expense.payment_method}'}
                ]
                
                GLService.post_entry(
                    lines,
                    description=f'Expense {expense.expense_number}',
                    reference_type='Expense',
                    reference_id=expense.id,
                    currency=expense.currency,
                    exchange_rate=expense.exchange_rate,
                    branch_id=expense.branch_id
                )
                
                # If Cheque, issue it (GL: Debit 2110, Credit 2120)
                if cheque:
                    cheque.issue_cheque()
                    
            except Exception as e:
                current_app.logger.warning(f'GL posting failed: {e}')
            
            db.session.commit()
            
            create_audit_log('create', 'expenses', expense.id)
            
            flash('✅ تم إضافة المصروف بنجاح!', 'success')
            return redirect(url_for('expenses.view', id=expense.id))
        
        except Exception as e:
            db.session.rollback()
            flash(f'❌ حدث خطأ: {str(e)}\n💡 تحقق من البيانات المدخلة وحاول مرة أخرى.', 'danger')
    
    categories = ExpenseCategory.query.filter_by(is_active=True).all()
    exchange_rates = CurrencyService.get_all_rates('AED')
    
    return render_template('expenses/create.html',
                         categories=categories,
                         exchange_rates=exchange_rates)


@expenses_bp.route('/<int:id>')
@login_required
@permission_required('manage_expenses')
def view(id):
    expense = Expense.query.get_or_404(id)
    if not _expense_in_scope(expense):
        return render_template('errors/403.html'), 403
    return render_template('expenses/view.html', expense=expense)


@expenses_bp.route('/<int:id>/print')
@login_required
@permission_required('manage_expenses')
def print_expense(id):
    expense = Expense.query.get_or_404(id)
    if not _expense_in_scope(expense):
        return render_template('errors/403.html'), 403
    from flask import current_app
    company = {
        'name_ar': current_app.config.get('COMPANY_NAME_AR'),
        'address': current_app.config.get('COMPANY_ADDRESS'),
        'phone': current_app.config.get('COMPANY_PHONE'),
    }
    return render_template('expenses/print.html', expense=expense, company=company)


@expenses_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@permission_required('manage_expenses')
def edit(id):
    """تعديل مصروف"""
    expense = Expense.query.get_or_404(id)
    if not _expense_in_scope(expense):
        return render_template('errors/403.html'), 403
    categories = ExpenseCategory.query.filter_by(is_active=True).all()
    
    if request.method == 'POST':
        try:
            # تحديث البيانات
            expense.category_id = request.form.get('category_id')
            expense.description = request.form.get('description')
            expense.description_ar = request.form.get('description_ar')
            expense.amount = request.form.get('amount')
            expense.currency = request.form.get('currency', 'AED')
            expense.supplier_name = request.form.get('supplier_name')
            expense.notes = request.form.get('notes')
            
            # حساب المبلغ بالدرهم
            exchange_rate = CurrencyService.get_rate(expense.currency)
            expense.exchange_rate = exchange_rate
            expense.amount_aed = float(expense.amount) * exchange_rate
            
            db.session.commit()
            
            create_audit_log('update', 'expenses', id)
            flash('✅ تم تحديث المصروف بنجاح!', 'success')
            return redirect(url_for('expenses.view', id=id))
        
        except Exception as e:
            db.session.rollback()
            flash(f'❌ حدث خطأ: {str(e)}\n💡 تحقق من البيانات المدخلة وحاول مرة أخرى.', 'danger')
    
    return render_template('expenses/edit.html', expense=expense, categories=categories)


@expenses_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@permission_required('manage_expenses')
def delete(id):
    """حذف (أرشفة) المصروف"""
    from models import Cheque, GLJournalEntry
    from services.archive_service import ArchiveService
    
    expense = Expense.query.get_or_404(id)
    if not _expense_in_scope(expense):
        return render_template('errors/403.html'), 403
    
    # التحقق من الارتباطات
    has_links = False
    
    # 1. التحقق من الشيكات
    cheque = Cheque.query.filter_by(expense_id=expense.id).first()
    if cheque and cheque.status in ['cleared', 'deposited', 'bounced', 'cancelled']:
        has_links = True
        
    try:
        if has_links:
            # أرشفة (Soft Delete)
            # عكس القيد المحاسبي للحفاظ على السجل
            try:
                GLService.reverse_entry(
                    reference_type='Expense',
                    reference_id=expense.id,
                    description=f'Reverse Expense {expense.expense_number}'
                )
            except Exception as e:
                current_app.logger.warning(f'GL reversal warning: {e}')
                
            archive_service = ArchiveService()
            archive_service.archive_record('expenses', expense, reason='تم أرشفة المصروف لوجود ارتباطات', commit=False)
            
            if cheque:
                 archive_service.archive_record('cheques', cheque, reason='تم أرشفة الشيك لارتباطه بمصروف مؤرشف', commit=False)
            
            create_audit_log('archive', 'expenses', id)
            db.session.commit()
            flash(f'✅ تم أرشفة المصروف "{expense.expense_number}" (لوجود ارتباطات)', 'warning')
            
        else:
            # حذف نهائي (Hard Delete)
            # 1. حذف القيود المحاسبية للمصروف
            GLJournalEntry.query.filter_by(reference_type='Expense', reference_id=expense.id).delete()
            
            # 2. حذف الشيك إذا كان معلقاً (وحذف قيوده إن وجدت)
            if cheque:
                # حذف قيود الشيك (نظرياً الشيك المعلق ليس له قيود، لكن للاحتياط)
                ref_types = ['cheque_receive', 'cheque_issue', 'cheque_cancel', 'cheque_clear', 'cheque_bounce', 'Cheque']
                GLJournalEntry.query.filter(
                    GLJournalEntry.reference_type.in_(ref_types),
                    GLJournalEntry.reference_id == cheque.id
                ).delete(synchronize_session=False)
                
                db.session.delete(cheque)
                
            # 3. حذف المصروف
            db.session.delete(expense)
            create_audit_log('delete', 'expenses', id)
            db.session.commit()
            flash(f'✅ تم حذف المصروف "{expense.expense_number}" نهائياً', 'success')
            
        return redirect(url_for('expenses.index'))
    
    except Exception as e:
        db.session.rollback()
        flash(f'❌ خطأ في الحذف: {str(e)}\n💡 راجع البيانات المدخلة.', 'danger')
        return redirect(url_for('expenses.view', id=id))


@expenses_bp.route('/categories')
@login_required
@permission_required('manage_expenses')
def categories():
    categories = ExpenseCategory.query.filter_by(is_active=True).order_by(ExpenseCategory.name).all()
    return render_template('expenses/categories.html', categories=categories)


@expenses_bp.route('/categories/create', methods=['POST'])
@login_required
@permission_required('manage_expenses')
def create_category():
    try:
        # دعم JSON و Form Data
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form
        
        category = ExpenseCategory(
            name=data.get('name'),
            name_ar=data.get('name_ar'),
            gl_account_code=data.get('gl_account_code')
        )
        
        db.session.add(category)
        db.session.commit()
        
        # إرجاع JSON إذا كان الطلب JSON
        if request.is_json:
            return jsonify({
                'success': True,
                'message': 'تم إضافة الفئة بنجاح',
                'category': {
                    'id': category.id,
                    'name': category.name,
                    'name_ar': category.name_ar
                }
            })
        
        flash('✅ تم إضافة فئة المصروف بنجاح!', 'success')
        return redirect(url_for('expenses.categories'))
    
    except Exception as e:
        db.session.rollback()
        
        if request.is_json:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 400
        
        flash(f'❌ حدث خطأ: {str(e)}\n💡 تحقق من البيانات المدخلة وحاول مرة أخرى.', 'danger')
        return redirect(url_for('expenses.categories'))


@expenses_bp.route('/archived')
@login_required
@permission_required('manage_expenses')
def archived():
    """عرض المصروفات المؤرشفة"""
    from models import ArchivedRecord
    from datetime import datetime
    
    archived_expenses_query = db.session.query(ArchivedRecord).filter(
        ArchivedRecord.table_name == 'expenses'
    )
    
    archived_items = []
    
    for archived in archived_expenses_query.all():
        data = archived.data
        archived_items.append({
            'id': archived.record_id,
            'expense_number': data.get('expense_number'),
            'expense_date': datetime.fromisoformat(data.get('expense_date').replace('Z', '+00:00')) if isinstance(data.get('expense_date'), str) else data.get('expense_date'),
            'category_name': data.get('category_name'),
            'description': data.get('description'),
            'amount': float(data.get('amount', 0)),
            'currency': data.get('currency'),
            'payment_method': data.get('payment_method'),
            'archived_at': archived.archived_at
        })
    
    archived_items.sort(key=lambda x: x['archived_at'], reverse=True)
    
    return render_template('expenses/archived.html', expenses=archived_items)


@expenses_bp.route('/<int:id>/archive', methods=['POST'])
@login_required
@permission_required('manage_expenses')
def archive(id):
    """أرشفة مصروف"""
    from services.archive_service import ArchiveService
    
    expense = Expense.query.get_or_404(id)
    if not _expense_in_scope(expense):
        return render_template('errors/403.html'), 403
    
    try:
        archive_service = ArchiveService()
        archive_service.archive_record('expenses', expense, reason='تم أرشفة المصروف')
        create_audit_log('archive', 'expenses', expense.id)
    except Exception as e:
        db.session.rollback()
    
    return redirect(url_for('expenses.index'))


@expenses_bp.route('/<int:id>/restore', methods=['POST'])
@login_required
@permission_required('manage_expenses')
def restore(id):
    """استعادة مصروف من الأرشيف"""
    from models import ArchivedRecord
    
    archived = ArchivedRecord.query.filter_by(
        table_name='expenses',
        record_id=id
    ).first_or_404()
    
    try:
        db.session.delete(archived)
        db.session.commit()
        create_audit_log('restore', 'expenses', id)
    except Exception as e:
        db.session.rollback()
    
    return redirect(url_for('expenses.archived'))

