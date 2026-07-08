from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify
from flask_login import login_required, current_user
from extensions import db, limiter
from models import Expense, ExpenseCategory, Cheque
from services.currency_service import CurrencyService
from services.exchange_rate_service import ExchangeRateService
from services.gl_service import GLService
from services.gl_posting import post_or_fail
from services.cheque_service import process_cheque_issue
from utils.decorators import permission_required, branch_scope_id
from utils.db_safety import atomic_transaction
from utils.branching import should_show_all_branch_columns
from services.logging_core import LoggingCore
from utils.helpers import generate_number
from utils.currency_utils import resolve_default_currency, get_system_default_currency
from utils.tenanting import tenant_query, tenant_get_or_404, require_active_tenant_id, get_active_tenant_id
from utils.gl_reference_types import GLRef
from decimal import Decimal
from datetime import datetime

expenses_bp = Blueprint('expenses', __name__, url_prefix='/expenses')


def _expense_in_scope(expense):
    scoped_branch_id = branch_scope_id()
    return scoped_branch_id is None or expense.branch_id == scoped_branch_id


def _resolve_transaction_rate(currency, user_rate=None):
    from utils.currency_utils import get_system_default_currency
    base = get_system_default_currency()
    rate_info = ExchangeRateService.resolve_exchange_rate_for_transaction(
        currency,
        base,
        user_rate=user_rate,
    )
    return Decimal(str(rate_info['rate']))


def _build_expense_gl_lines(expense, tenant_id):
    category = expense.category
    expense_account = category.gl_account_code if category and category.gl_account_code else '6990'
    expense_concept = None if category and category.gl_account_code else 'MISC_EXPENSE'
    from models import GLAccount
    tid = tenant_id
    acc_check = GLAccount.query.filter_by(
        code=str(expense_account),
        tenant_id=int(tid) if tid else None,
    ).first()
    if acc_check and acc_check.is_header:
        expense_account = '6990'
        expense_concept = 'MISC_EXPENSE'
    if expense.payment_method == 'cheque':
        payment_account = '2120'
        payment_concept = 'DEFERRED_CHEQUES_PAYABLE'
    else:
        payment_account = GLService.get_payment_credit_account(
            expense.payment_method,
            branch_id=expense.branch_id,
            tenant_id=tid,
        )
        payment_concept = GLService.get_payment_credit_concept(expense.payment_method)
    return [
        {
            'account': expense_account,
            'concept_code': expense_concept,
            'explicit_account_allowed': expense_concept is None,
            'debit': expense.amount,
            'description': expense.description or '',
        },
        {
            'account': payment_account,
            'concept_code': payment_concept,
            'credit': expense.amount,
            'description': f'دفع {expense.payment_method}',
        },
    ]


@expenses_bp.route('/')
@login_required
@permission_required('manage_expenses')
def index():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    category_id = request.args.get('category', type=int)
    
    query = tenant_query(Expense).filter_by(status='confirmed')
    
    # إخفاء المصروفات المؤرشفة (مع نطاق التيننت)
    from models import ArchivedRecord
    from sqlalchemy import select, true
    from utils.tenanting import get_active_tenant_id
    _tid = get_active_tenant_id(current_user)
    archived_filters = [ArchivedRecord.table_name == 'expenses']
    if _tid is not None:
        archived_filters.append(ArchivedRecord.tenant_id == _tid)
    archived_expenses = select(ArchivedRecord.record_id).filter(
        *archived_filters
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
    
    categories = tenant_query(ExpenseCategory).filter_by(is_active=True).all()
    
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
            tenant_id = require_active_tenant_id(current_user)
            expense_number = generate_number(
                'EXP',
                Expense,
                'expense_number',
                branch_id=expense_branch_id,
                tenant_id=tenant_id,
            )
            
            try:
                from models import Tenant
                default_currency = resolve_default_currency()
            except Exception:
                default_currency = get_system_default_currency()
            currency = request.form.get('currency') or default_currency
            user_exchange_rate = request.form.get('exchange_rate', type=float)
            
            exchange_rate = _resolve_transaction_rate(currency, user_exchange_rate)
            
            amount = Decimal(str(request.form.get('amount')))
            
            cheque_date_str = request.form.get('cheque_date')
            cheque_date_obj = None
            if cheque_date_str:
                try:
                    cheque_date_obj = datetime.strptime(cheque_date_str, '%Y-%m-%d').date()
                except ValueError:
                    pass

            expense = Expense(
                tenant_id=tenant_id,
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
                    tenant_id=getattr(current_user, 'tenant_id', None),
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
                from utils.tenanting import get_active_tenant_id
                GLService.ensure_core_accounts(tenant_id=getattr(expense, 'tenant_id', None) or get_active_tenant_id(current_user))
                
                tid = getattr(expense, 'tenant_id', None) or get_active_tenant_id(current_user)
                lines = _build_expense_gl_lines(expense, tid)
                
                post_or_fail(
                    lines,
                    description=f'Expense {expense.expense_number}',
                    reference_type=GLRef.EXPENSE,
                    reference_id=expense.id,
                    currency=expense.currency,
                    exchange_rate=expense.exchange_rate,
                    branch_id=expense.branch_id
                )
                
                if cheque:
                    process_cheque_issue(cheque)
                    
            except Exception as e:
                db.session.rollback()
                flash(f'❌ فشل الترحيل المحاسبي: {str(e)}', 'danger')
                try:
                    from models import Tenant
                    _dc = resolve_default_currency()
                except Exception:
                    _dc = get_system_default_currency()
                return render_template('expenses/create.html',
                                     categories=tenant_query(ExpenseCategory).filter_by(is_active=True).all(),
                                     exchange_rates=CurrencyService.get_all_rates(_dc))
            
            with atomic_transaction('expense_create'):
                db.session.flush()
            
            LoggingCore.log_audit('create', 'expenses', expense.id)
            
            flash('✅ تم إضافة المصروف بنجاح!', 'success')
            return redirect(url_for('expenses.view', id=expense.id))
        
        except Exception as e:
            db.session.rollback()
            flash(f'❌ حدث خطأ: {str(e)}\n💡 تحقق من البيانات المدخلة وحاول مرة أخرى.', 'danger')
    
    try:
        from models import Tenant
        _dc = resolve_default_currency()
    except Exception:
        _dc = get_system_default_currency()
    categories = tenant_query(ExpenseCategory).filter_by(is_active=True).all()
    exchange_rates = CurrencyService.get_all_rates(_dc)
    
    return render_template('expenses/create.html',
                         categories=categories,
                         exchange_rates=exchange_rates)


@expenses_bp.route('/<int:id>')
@login_required
@permission_required('manage_expenses')
def view(id):
    expense = tenant_get_or_404(Expense, id)
    if not _expense_in_scope(expense):
        return render_template('errors/403.html'), 403
    return render_template('expenses/view.html', expense=expense)


@expenses_bp.route('/<int:id>/print')
@login_required
@permission_required('manage_expenses')
def print_expense(id):
    expense = tenant_get_or_404(Expense, id)
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
    expense = tenant_get_or_404(Expense, id)
    if not _expense_in_scope(expense):
        return render_template('errors/403.html'), 403

    # منع تعديل المصروف المؤرشف
    from models import ArchivedRecord
    is_archived = ArchivedRecord.query.filter_by(
        table_name='expenses',
        record_id=expense.id
    ).first() is not None
    if is_archived:
        flash('⚠️ لا يمكن تعديل مصروف مؤرشف.', 'warning')
        return redirect(url_for('expenses.view', id=id))

    categories = tenant_query(ExpenseCategory).filter_by(is_active=True).all()
    
    if request.method == 'POST':
        try:
            # التحقق من أن الفترة المحاسبية مفتوحة
            from services.gl_helpers import assert_period_open
            assert_period_open(expense.expense_date, expense.tenant_id)

            try:
                from models import Tenant
                default_currency = resolve_default_currency()
            except Exception:
                default_currency = get_system_default_currency()
            
            new_category_id = request.form.get('category_id', type=int)
            new_amount = Decimal(str(request.form.get('amount', 0)))
            new_currency = (request.form.get('currency') or default_currency).strip()
            new_description = request.form.get('description', '').strip()
            new_supplier_name = request.form.get('supplier_name', '').strip()
            new_notes = request.form.get('notes', '').strip()
            
            # الكشف عن تغيير الحقول المالية
            financial_change = (
                new_amount != expense.amount or
                new_currency != expense.currency or
                new_category_id != expense.category_id
            )
            
            if financial_change and expense.status == 'confirmed':
                # عكس القيد المحاسبي القديم
                from utils.gl_tenant import reverse_document_gl
                reverse_document_gl(
                    GLRef.EXPENSE, expense.id,
                    f'Reverse Expense {expense.expense_number} (Edit)',
                    tenant_id=expense.tenant_id,
                )
                expense.is_reversed = True
                db.session.flush()

            # تحديث الحقول
            expense.category_id = new_category_id
            expense.description = new_description
            expense.description_ar = request.form.get('description_ar')
            expense.amount = new_amount
            expense.currency = new_currency
            expense.supplier_name = new_supplier_name
            expense.notes = new_notes
            
            # إعادة حساب المبلغ بالدرهم
            exchange_rate = CurrencyService.get_exchange_rate(expense.currency)
            expense.exchange_rate = exchange_rate
            expense.amount_aed = new_amount * exchange_rate
            
            if financial_change and expense.status == 'confirmed':
                # إعادة ترحيل القيد المحاسبي بالقيم الجديدة
                from utils.tenanting import get_active_tenant_id
                GLService.ensure_core_accounts(tenant_id=expense.tenant_id or get_active_tenant_id(current_user))
                
                tid = expense.tenant_id or get_active_tenant_id(current_user)
                lines = _build_expense_gl_lines(expense, tid)
                from services.gl_posting import post_or_fail
                post_or_fail(
                    lines,
                    description=f'Expense {expense.expense_number} (Amended)',
                    reference_type=GLRef.EXPENSE,
                    reference_id=expense.id,
                    currency=expense.currency,
                    exchange_rate=expense.exchange_rate,
                    branch_id=expense.branch_id,
                )
            
            with atomic_transaction('expense_edit'):
                db.session.flush()
            
            LoggingCore.log_audit('update', 'expenses', id)
            flash('✅ تم تحديث المصروف بنجاح!', 'success')
            return redirect(url_for('expenses.view', id=id))
        
        except Exception as e:
            flash(f'❌ حدث خطأ: {str(e)}\n💡 تحقق من البيانات المدخلة وحاول مرة أخرى.', 'danger')
    
    return render_template('expenses/edit.html', expense=expense, categories=categories)


@expenses_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@permission_required('manage_expenses')
def delete(id):
    """حذف (أرشفة) المصروف"""
    from models import Cheque, GLJournalEntry
    from services.archive_service import ArchiveService
    
    expense = tenant_get_or_404(Expense, id)
    if not _expense_in_scope(expense):
        return render_template('errors/403.html'), 403
    
    # التحقق من الارتباطات
    has_links = False
    
    # 1. التحقق من الشيكات
    cheque = Cheque.query.filter_by(expense_id=expense.id, tenant_id=expense.tenant_id).first()
    if cheque and cheque.status in ['cleared', 'deposited', 'bounced', 'cancelled']:
        has_links = True
        
    try:
        if has_links:
            archive_service = ArchiveService()
            archive_service.archive_record('expenses', expense, reason='تم أرشفة المصروف لوجود ارتباطات', commit=False)
            
            if cheque:
                 archive_service.archive_record('cheques', cheque, reason='تم أرشفة الشيك لارتباطه بمصروف مؤرشف', commit=False)
            
            LoggingCore.log_audit('archive', 'expenses', id)
            with atomic_transaction('expense_archive'):
                db.session.flush()
            flash(f'✅ تم أرشفة المصروف "{expense.expense_number}" (لوجود ارتباطات)', 'warning')
            
        else:
            # عكس القيود المحاسبية بدلاً من الحذف
            from services.gl_service import GLService
            GLService.reverse_entry(
                reference_type=GLRef.EXPENSE,
                reference_id=expense.id,
                description=f'Reverse Expense {expense.expense_number} (Deleted)',
                tenant_id=expense.tenant_id,
            )

            # 2. عكس/حذف الشيك إذا كان معلقاً
            if cheque:
                from services.cheque_service import process_cheque_cancel
                process_cheque_cancel(cheque, reason=f'حذف المصروف {expense.expense_number}')
                db.session.delete(cheque)
                
            # 3. حذف المصروف
            db.session.delete(expense)
            LoggingCore.log_audit('delete', 'expenses', id)
            with atomic_transaction('expense_delete'):
                db.session.flush()
            flash(f'✅ تم حذف المصروف "{expense.expense_number}" نهائياً', 'success')
            
        return redirect(url_for('expenses.index'))
    
    except Exception as e:
        flash(f'❌ خطأ في الحذف: {str(e)}\n💡 راجع البيانات المدخلة.', 'danger')
        return redirect(url_for('expenses.view', id=id))


@expenses_bp.route('/<int:id>/cancel', methods=['POST'])
@login_required
@permission_required('manage_expenses')
def cancel(id):
    """إلغاء مصروف — عكس القيد المحاسبي وتحديث حالة الشيك"""
    from models import Cheque, GLJournalEntry
    from utils.gl_tenant import reverse_document_gl

    expense = tenant_get_or_404(Expense, id)
    if not _expense_in_scope(expense):
        return render_template('errors/403.html'), 403

    try:
        from services.gl_helpers import assert_period_open
        assert_period_open(expense.expense_date, expense.tenant_id)

        cheque = Cheque.query.filter_by(expense_id=expense.id, tenant_id=expense.tenant_id).first()

        # عكس القيد المحاسبي — إذا كان هناك شيك مرتبط، فـ process_cheque_cancel يتولى القيد
        if cheque and cheque.status not in ('cancelled',):
            from services.cheque_service import process_cheque_cancel
            process_cheque_cancel(cheque, reason=f'إلغاء المصروف {expense.expense_number}', create_gl=True)
        else:
            reverse_document_gl(
                GLRef.EXPENSE, expense.id,
                f'Cancel Expense {expense.expense_number}',
                tenant_id=getattr(expense, 'tenant_id', None),
            )

        expense.is_reversed = True

        with atomic_transaction('expense_cancel'):
            db.session.flush()
        LoggingCore.log_audit('cancel', 'expenses', id)
        flash(f'✅ تم إلغاء المصروف "{expense.expense_number}" وعكس القيد المحاسبي.', 'success')
    except Exception as e:
        flash(f'❌ خطأ في الإلغاء: {str(e)}', 'danger')

    return redirect(url_for('expenses.view', id=id))


@expenses_bp.route('/categories')
@login_required
@permission_required('manage_expenses')
def categories():
    categories = tenant_query(ExpenseCategory).filter_by(is_active=True).order_by(ExpenseCategory.name).all()
    return render_template('expenses/categories.html', categories=categories)


def _validate_gl_account_code(gl_account_code, tenant_id):
    """التحقق من صحة حساب الأستاذ لفئة المصروف"""
    if not gl_account_code:
        return True  # سيتم استخدام الحساب الافتراضي 6990
    from models import GLAccount
    account = GLAccount.query.filter_by(
        code=str(gl_account_code),
        tenant_id=int(tenant_id) if tenant_id else None,
    ).first()
    if not account:
        raise ValueError(f'⚠️ حساب الأستاذ "{gl_account_code}" غير موجود.')
    if account.is_header:
        raise ValueError(f'⚠️ حساب "{account.name}" هو حساب رئيسي ولا يمكن الترحيل إليه.')
    if not account.is_active:
        raise ValueError(f'⚠️ حساب "{account.name}" غير نشط.')
    # التحقق من أن الحساب مناسب للمصروفات
    code_str = str(gl_account_code)
    first_digit = code_str[0] if code_str else ''
    # حسابات الأصول (1xxx), الخصوم (2xxx), حقوق ملكية (3xxx), إيرادات (4xxx)
    # وحسابات خاصة معروفة
    restricted_prefixes = ['1', '2', '3', '4']
    restricted_codes = ['1130', '1150', '1160', '2110', '2120', '2140', '3130', '3350']
    if code_str in restricted_codes:
        raise ValueError(f'⚠️ حساب "{account.name}" هو حساب أصول/خصوم/حقوق ملكية ولا يمكن استخدامه كمصروف.')
    if first_digit in restricted_prefixes and code_str != '6990':
        raise ValueError(f'⚠️ حساب "{account.name}" (يبدأ بـ {first_digit}) ليس حساب مصروفات. استخدم حساب من فئة 5xxx أو 6xxx.')
    return True


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
        
        tenant_id = require_active_tenant_id(current_user)
        
        # التحقق من حساب الأستاذ
        gl_account_code = data.get('gl_account_code')
        _validate_gl_account_code(gl_account_code, tenant_id)
        
        category = ExpenseCategory(
            tenant_id=tenant_id,
            name=data.get('name'),
            name_ar=data.get('name_ar'),
            gl_account_code=gl_account_code,
        )
        db.session.add(category)
        with atomic_transaction('expense_category_create'):
            db.session.flush()
        
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
        if request.is_json:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 400
        
        flash(f'❌ حدث خطأ: {str(e)}\n💡 تحقق من البيانات المدخلة وحاول مرة أخرى.', 'danger')
        return redirect(url_for('expenses.categories'))


def _archived_expense_row(archived):
    from datetime import datetime
    data = archived.data or {}
    raw_date = data.get('expense_date')
    if isinstance(raw_date, str):
        expense_date = datetime.fromisoformat(raw_date.replace('Z', '+00:00'))
    else:
        expense_date = raw_date
    return {
        'id': archived.record_id,
        'expense_number': data.get('expense_number'),
        'expense_date': expense_date,
        'category_name': data.get('category_name'),
        'description': data.get('description'),
        'amount': float(data.get('amount', 0) or 0),
        'currency': data.get('currency'),
        'payment_method': data.get('payment_method'),
        'archived_at': archived.archived_at,
    }


@expenses_bp.route('/archived')
@login_required
@permission_required('manage_expenses')
def archived():
    """عرض المصروفات المؤرشفة"""
    from models import ArchivedRecord

    tid = get_active_tenant_id(current_user)
    archived_expenses_query = db.session.query(ArchivedRecord).filter(
        ArchivedRecord.table_name == 'expenses'
    )
    if tid is not None:
        archived_expenses_query = archived_expenses_query.filter(ArchivedRecord.tenant_id == tid)

    archived_items = [_archived_expense_row(archived) for archived in archived_expenses_query.all()]
    archived_items.sort(key=lambda x: x['archived_at'], reverse=True)

    return render_template('expenses/archived.html', expenses=archived_items)


@expenses_bp.route('/<int:id>/archive', methods=['POST'])
@login_required
@permission_required('manage_expenses')
def archive(id):
    """أرشفة مصروف"""
    from services.archive_service import ArchiveService
    
    expense = tenant_get_or_404(Expense, id)
    if not _expense_in_scope(expense):
        return render_template('errors/403.html'), 403
    
    try:
        archive_service = ArchiveService()
        archive_service.archive_record('expenses', expense, reason='تم أرشفة المصروف')
        LoggingCore.log_audit('archive', 'expenses', expense.id)
    except Exception as e:
        db.session.rollback()
    
    return redirect(url_for('expenses.index'))


@expenses_bp.route('/<int:id>/restore', methods=['POST'])
@login_required
@permission_required('manage_expenses')
def restore(id):
    """استعادة مصروف من الأرشيف"""
    from models import ArchivedRecord
    
    tid = get_active_tenant_id(current_user)
    archived_query = ArchivedRecord.query.filter_by(
        table_name='expenses',
        record_id=id
    )
    if tid is not None:
        archived_query = archived_query.filter(ArchivedRecord.tenant_id == tid)
    archived = archived_query.first_or_404()
    
    try:
        with atomic_transaction('expense_restore'):
            db.session.delete(archived)
            db.session.flush()
        LoggingCore.log_audit('restore', 'expenses', id)
    except Exception as e:
        flash(f'تعذر الاستعادة: {str(e)}', 'danger')
        return redirect(url_for('expenses.archived'))
    return redirect(url_for('expenses.archived'))

