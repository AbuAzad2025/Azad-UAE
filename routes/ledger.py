from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from sqlalchemy import func
from extensions import db, csrf
from models import GLAccount, GLJournalEntry, GLJournalLine, Cheque, PaymentVault, Branch
from services.gl_service import GLService
from services.cash_flow_service import CashFlowService
from services.aging_analysis_service import AgingAnalysisService
from utils.branching import get_accessible_branches, user_can_access_branch
from utils.decorators import admin_required, permission_required, branch_scope_id
from services.logging_core import LoggingCore
from utils.currency_utils import resolve_default_currency, get_system_default_currency
from decimal import Decimal
from datetime import datetime, date, timedelta

ledger_bp = Blueprint('ledger', __name__, url_prefix='/ledger')


def _effective_branch_id():
    scoped_branch_id = branch_scope_id()
    requested_branch_id_str = request.args.get('branch_id')
    requested_branch_id = None
    try:
        if requested_branch_id_str:
            requested_branch_id = int(requested_branch_id_str)
    except ValueError:
        requested_branch_id = None
    if scoped_branch_id is not None:
        return scoped_branch_id
    if requested_branch_id and user_can_access_branch(requested_branch_id, current_user):
        return requested_branch_id
    return None


@ledger_bp.route('/')
@login_required
@permission_required('view_ledger')
def index():
    from utils.gl_tenant import scope_gl_accounts
    accounts = scope_gl_accounts(GLAccount.query.filter_by(is_active=True)).order_by(GLAccount.code).all()
    return render_template('ledger/index.html', accounts=accounts, selected_branch=_effective_branch_id(), branches=get_accessible_branches(current_user))


@ledger_bp.route('/account/<int:id>')
@login_required
@permission_required('view_ledger')
def account_ledger(id):
    from utils.gl_tenant import scope_gl_accounts
    account = scope_gl_accounts(GLAccount.query.filter_by(id=id)).first_or_404()
    
    date_from = request.args.get('date_from', type=str)
    date_to = request.args.get('date_to', type=str)
    branch_id = _effective_branch_id()
    
    # Use GLService for optimized query with branch support
    result = GLService.get_account_statement(id, date_from, date_to, branch_id)
    
    branches = get_accessible_branches(current_user)
    
    return render_template('ledger/account_ledger.html',
                         account=account,
                         transactions=result['transactions'],
                         summary={
                             'total_debit': result['total_debit'],
                             'total_credit': result['total_credit'],
                             'final_balance': result['closing_balance'],
                             'opening_balance': result['opening_balance']
                         },
                         branches=branches,
                         selected_branch=branch_id,
                         date_from=date_from,
                         date_to=date_to)


@ledger_bp.route('/trial-balance')
@login_required
@permission_required('view_ledger')
def trial_balance():
    date_from = request.args.get('date_from', type=str)
    date_to = request.args.get('date_to', type=str)
    branch_id = _effective_branch_id()
    
    result = GLService.get_trial_balance(date_from, date_to, branch_id)
    
    branches = get_accessible_branches(current_user)
    
    return render_template('ledger/trial_balance.html',
                         trial_balance=result['lines'],
                         total_debit=result['total_debit'],
                         total_credit=result['total_credit'],
                         branches=branches,
                         selected_branch=branch_id,
                          date_from=date_from,
                          date_to=date_to)


@ledger_bp.route('/journal-entries')
@login_required
@permission_required('view_ledger')
def journal_entries():
    from utils.gl_tenant import scope_journal_entries
    page = request.args.get('page', 1, type=int)
    branch_id = _effective_branch_id()
    query = scope_journal_entries(GLJournalEntry.query)
    if branch_id:
        query = query.filter(GLJournalEntry.branch_id == branch_id)
    pagination = query.order_by(GLJournalEntry.entry_date.desc()).paginate(
        page=page,
        per_page=50,
        error_out=False
    )
    branches = get_accessible_branches(current_user)
    return render_template('ledger/journal_entries.html',
                         entries=pagination.items,
                         pagination=pagination,
                         branches=branches,
                         selected_branch=branch_id)


@ledger_bp.route('/vat-report')
@login_required
@permission_required('view_ledger')
def vat_report():
    from models.tenant import Tenant
    from utils.tax_settings import is_tax_enabled, vat_country as tenant_vat_country

    tenant = Tenant.get_current()
    if tenant and not is_tax_enabled(tenant.id):
        flash('الضريبة غير مفعّلة لهذه الشركة. فعّلها من إعدادات الضرائب إن لزم.', 'info')
        return redirect(url_for('ledger.index'))

    date_from = request.args.get('date_from', type=str)
    date_to = request.args.get('date_to', type=str)
    branch_id = _effective_branch_id()
    report = GLService.get_vat_report(date_from, date_to, branch_id)
    branches = get_accessible_branches(current_user)
    return render_template(
        'ledger/vat_report.html',
        report=report,
        branches=branches,
        selected_branch=branch_id,
        date_from=date_from,
        date_to=date_to,
        vat_country=tenant_vat_country(tenant.id if tenant else None),
    )


@ledger_bp.route('/periods', methods=['GET', 'POST'])
@login_required
@permission_required('view_ledger')
def gl_periods():
    from models.gl import GLPeriod
    from utils.tenanting import get_active_tenant_id, require_active_tenant_id
    from datetime import datetime, timezone

    tenant_id = require_active_tenant_id()
    if request.method == 'POST':
        year = request.form.get('year', type=int)
        month = request.form.get('month', type=int)
        action = request.form.get('action', 'close')
        period = GLPeriod.query.filter_by(tenant_id=tenant_id, year=year, month=month).first()
        if not period:
            period = GLPeriod(tenant_id=tenant_id, year=year, month=month)
            db.session.add(period)
        period.is_closed = action == 'close'
        period.closed_at = datetime.now(timezone.utc) if period.is_closed else None
        period.closed_by = current_user.id if period.is_closed else None
        db.session.commit()
        flash('تم تحديث حالة الفترة المحاسبية.', 'success')
        return redirect(url_for('ledger.gl_periods'))

    periods = GLPeriod.query.filter_by(tenant_id=tenant_id).order_by(
        GLPeriod.year.desc(), GLPeriod.month.desc()
    ).limit(24).all()
    return render_template('ledger/periods.html', periods=periods, tenant_id=tenant_id)


@ledger_bp.route('/run-depreciation', methods=['POST'])
@login_required
@permission_required('view_ledger')
def run_depreciation():
    from services.depreciation_service import DepreciationService
    from utils.tenanting import require_active_tenant_id

    tenant_id = require_active_tenant_id()
    year = request.form.get('year', type=int)
    month = request.form.get('month', type=int)
    result = DepreciationService.run_monthly(tenant_id=tenant_id, period_year=year, period_month=month)
    if result['errors']:
        flash(f'استهلاك: {result["posted"]} أصل، أخطاء: {"; ".join(result["errors"][:3])}', 'warning')
    else:
        flash(f'تم ترحيل استهلاك {result["posted"]} أصل (تخطي {result["skipped"]}).', 'success')
    return redirect(url_for('ledger.gl_periods'))


@ledger_bp.route('/income-statement')
@login_required
@permission_required('view_ledger')
def income_statement():
    from utils.gl_tenant import scope_gl_accounts
    from utils.tenanting import get_active_tenant_id
    tid = get_active_tenant_id(current_user)
    date_from = request.args.get('date_from', type=str)
    date_to = request.args.get('date_to', type=str)
    branch_id = _effective_branch_id()
    
    revenue_accounts = scope_gl_accounts(GLAccount.query.filter(GLAccount.type == 'revenue')).all()
    expense_accounts = scope_gl_accounts(GLAccount.query.filter(GLAccount.type == 'expense')).all()
    
    def _filter_tenant(q):
        if tid is not None:
            return q.filter(GLJournalEntry.tenant_id == tid)
        return q
    
    revenues = {}
    total_revenue = Decimal('0')
    
    for acc in revenue_accounts:
        query_credit = _filter_tenant(db.session.query(func.sum(GLJournalLine.credit)).filter_by(account_id=acc.id).join(GLJournalEntry))
        query_debit = _filter_tenant(db.session.query(func.sum(GLJournalLine.debit)).filter_by(account_id=acc.id).join(GLJournalEntry))
        
        if date_from:
            query_credit = query_credit.filter(func.date(GLJournalEntry.entry_date) >= date_from)
            query_debit = query_debit.filter(func.date(GLJournalEntry.entry_date) >= date_from)
            
        if date_to:
            query_credit = query_credit.filter(func.date(GLJournalEntry.entry_date) <= date_to)
            query_debit = query_debit.filter(func.date(GLJournalEntry.entry_date) <= date_to)
        if branch_id:
            query_credit = query_credit.filter(GLJournalEntry.branch_id == branch_id)
            query_debit = query_debit.filter(GLJournalEntry.branch_id == branch_id)
            
        credit = query_credit.scalar() or Decimal('0')
        debit = query_debit.scalar() or Decimal('0')
        balance = credit - debit
        
        if balance != 0:
            revenues[acc.name] = float(balance)
            total_revenue += balance
    
    expenses = {}
    total_expense = Decimal('0')
    
    for acc in expense_accounts:
        query_debit = _filter_tenant(db.session.query(func.sum(GLJournalLine.debit)).filter_by(account_id=acc.id).join(GLJournalEntry))
        query_credit = _filter_tenant(db.session.query(func.sum(GLJournalLine.credit)).filter_by(account_id=acc.id).join(GLJournalEntry))
        
        if date_from:
            query_debit = query_debit.filter(func.date(GLJournalEntry.entry_date) >= date_from)
            query_credit = query_credit.filter(func.date(GLJournalEntry.entry_date) >= date_from)
            
        if date_to:
            query_debit = query_debit.filter(func.date(GLJournalEntry.entry_date) <= date_to)
            query_credit = query_credit.filter(func.date(GLJournalEntry.entry_date) <= date_to)
        if branch_id:
            query_debit = query_debit.filter(GLJournalEntry.branch_id == branch_id)
            query_credit = query_credit.filter(GLJournalEntry.branch_id == branch_id)
            
        debit = query_debit.scalar() or Decimal('0')
        credit = query_credit.scalar() or Decimal('0')
        balance = debit - credit
        
        if balance != 0:
            expenses[acc.name] = float(balance)
            total_expense += balance
    
    net_profit = total_revenue - total_expense
    
    return render_template('ledger/income_statement.html',
                         revenues=revenues,
                         expenses=expenses,
                         total_revenue=float(total_revenue),
                         total_expense=float(total_expense),
                         net_profit=float(net_profit),
                         branches=get_accessible_branches(current_user),
                         selected_branch=branch_id,
                         date_from=date_from,
                         date_to=date_to)


@ledger_bp.route('/balance-sheet')
@login_required
@permission_required('view_ledger')
def balance_sheet():
    from utils.gl_tenant import scope_gl_accounts
    from utils.tenanting import get_active_tenant_id
    tid = get_active_tenant_id(current_user)
    branch_id = _effective_branch_id()
    date_to = request.args.get('date_to', type=str)
    assets = {}
    liabilities = {}
    equity = {}
    
    asset_accounts = scope_gl_accounts(GLAccount.query.filter(GLAccount.type == 'asset')).all()
    liability_accounts = scope_gl_accounts(GLAccount.query.filter(GLAccount.type == 'liability')).all()
    equity_accounts = scope_gl_accounts(GLAccount.query.filter(GLAccount.type == 'equity')).all()
    
    def _apply_entry_filters(q):
        if tid is not None:
            q = q.filter(GLJournalEntry.tenant_id == tid)
        if date_to:
            q = q.filter(func.date(GLJournalEntry.entry_date) <= date_to)
        if branch_id:
            q = q.filter(GLJournalEntry.branch_id == branch_id)
        return q

    total_assets = Decimal('0')
    for acc in asset_accounts:
        debit_query = _apply_entry_filters(
            db.session.query(func.sum(GLJournalLine.debit)).filter_by(account_id=acc.id).join(GLJournalEntry)
        )
        credit_query = _apply_entry_filters(
            db.session.query(func.sum(GLJournalLine.credit)).filter_by(account_id=acc.id).join(GLJournalEntry)
        )
        debit = debit_query.scalar() or Decimal('0')
        credit = credit_query.scalar() or Decimal('0')
        balance = debit - credit
        
        if balance != 0:
            assets[acc.name] = float(balance)
            total_assets += balance
    
    total_liabilities = Decimal('0')
    for acc in liability_accounts:
        credit_query = _apply_entry_filters(
            db.session.query(func.sum(GLJournalLine.credit)).filter_by(account_id=acc.id).join(GLJournalEntry)
        )
        debit_query = _apply_entry_filters(
            db.session.query(func.sum(GLJournalLine.debit)).filter_by(account_id=acc.id).join(GLJournalEntry)
        )
        credit = credit_query.scalar() or Decimal('0')
        debit = debit_query.scalar() or Decimal('0')
        balance = credit - debit
        
        if balance != 0:
            liabilities[acc.name] = float(balance)
            total_liabilities += balance
    
    total_equity = Decimal('0')
    for acc in equity_accounts:
        credit_query = _apply_entry_filters(
            db.session.query(func.sum(GLJournalLine.credit)).filter_by(account_id=acc.id).join(GLJournalEntry)
        )
        debit_query = _apply_entry_filters(
            db.session.query(func.sum(GLJournalLine.debit)).filter_by(account_id=acc.id).join(GLJournalEntry)
        )
        credit = credit_query.scalar() or Decimal('0')
        debit = debit_query.scalar() or Decimal('0')
        balance = credit - debit
        
        if balance != 0:
            equity[acc.name] = float(balance)
            total_equity += balance

    # Calculate Net Profit (Revenue - Expenses) for Equity Section
    revenue_accounts = scope_gl_accounts(GLAccount.query.filter(GLAccount.code.like('4%'))).all()
    expense_accounts = scope_gl_accounts(GLAccount.query.filter(GLAccount.code.like('5%'))).all()
    expense_accounts += scope_gl_accounts(GLAccount.query.filter(GLAccount.code.like('6%'))).all()

    total_revenue_period = Decimal('0')
    for acc in revenue_accounts:
        credit_query = _apply_entry_filters(
            db.session.query(func.sum(GLJournalLine.credit)).filter_by(account_id=acc.id).join(GLJournalEntry)
        )
        debit_query = _apply_entry_filters(
            db.session.query(func.sum(GLJournalLine.debit)).filter_by(account_id=acc.id).join(GLJournalEntry)
        )
        credit = credit_query.scalar() or Decimal('0')
        debit = debit_query.scalar() or Decimal('0')
        total_revenue_period += (credit - debit)

    total_expense_period = Decimal('0')
    for acc in expense_accounts:
        debit_query = _apply_entry_filters(
            db.session.query(func.sum(GLJournalLine.debit)).filter_by(account_id=acc.id).join(GLJournalEntry)
        )
        credit_query = _apply_entry_filters(
            db.session.query(func.sum(GLJournalLine.credit)).filter_by(account_id=acc.id).join(GLJournalEntry)
        )
        debit = debit_query.scalar() or Decimal('0')
        credit = credit_query.scalar() or Decimal('0')
        total_expense_period += (debit - credit)

    net_profit_period = total_revenue_period - total_expense_period

    if net_profit_period != 0:
        equity['الأرباح المبقاة (صافي الربح التراكمي)'] = float(net_profit_period)
        total_equity += net_profit_period
    
    return render_template('ledger/balance_sheet.html',
                         assets=assets,
                         liabilities=liabilities,
                         equity=equity,
                         total_assets=float(total_assets),
                         total_liabilities=float(total_liabilities),
                         total_equity=float(total_equity),
                         branches=get_accessible_branches(current_user),
                         selected_branch=branch_id,
                         date_to=date_to)


@ledger_bp.route('/accounts-tree')
@login_required
@permission_required('view_ledger')
def accounts_tree():
    """عرض شجرة الحسابات"""
    tree = GLService.get_accounts_tree()
    return render_template('ledger/accounts_tree.html', accounts_tree=tree)


@ledger_bp.route('/account/<int:id>/statement')
@login_required
@permission_required('view_ledger')
def account_statement(id):
    """كشف حساب تفصيلي - مع فلترة اختيارية حسب الفرع للعزل"""
    date_from = request.args.get('date_from', type=str)
    date_to = request.args.get('date_to', type=str)
    branch_id = _effective_branch_id()
    statement = GLService.get_account_statement(id, date_from, date_to, branch_id)
    branches = get_accessible_branches(current_user)
    return render_template('ledger/account_statement.html',
                         statement=statement,
                         date_from=date_from,
                         date_to=date_to,
                         branches=branches,
                         selected_branch=branch_id)


@ledger_bp.route('/manual-entry', methods=['GET', 'POST'])
@login_required
@permission_required('manage_ledger')
def manual_entry():
    """إضافة قيد يدوي"""
    if request.method == 'POST':
        try:
            description = request.form.get('description')
            entry_date = request.form.get('entry_date')
            notes = request.form.get('notes')
            
            # تحويل التاريخ
            if entry_date:
                entry_date = datetime.strptime(entry_date, '%Y-%m-%d')
            
            # جمع السطور
            lines = []
            
            # جمع جميع السطور من الفورم
            i = 0
            while True:
                account_code = request.form.get(f'line_{i}_account')
                if not account_code:
                    break
                
                debit = request.form.get(f'line_{i}_debit', 0)
                credit = request.form.get(f'line_{i}_credit', 0)
                line_description = request.form.get(f'line_{i}_description', '')
                
                # تحويل القيم الفارغة إلى صفر
                try:
                    debit_value = float(debit) if debit and debit.strip() else 0
                    credit_value = float(credit) if credit and credit.strip() else 0
                except (ValueError, AttributeError):
                    debit_value = 0
                    credit_value = 0
                
                # إضافة السطر فقط إذا كان فيه قيمة
                if debit_value > 0 or credit_value > 0:
                    lines.append({
                        'account_code': account_code,
                        'debit': debit_value,
                        'credit': credit_value,
                        'description': line_description
                    })
                
                i += 1
            
            try:
                requested_branch_id = int(request.form.get('branch_id') or 0) or None
                if branch_scope_id() is not None:
                    branch_id = branch_scope_id()
                elif requested_branch_id and user_can_access_branch(requested_branch_id, current_user):
                    branch_id = requested_branch_id
                else:
                    branch_id = getattr(current_user, 'branch_id', None)
            except (ValueError, TypeError):
                branch_id = branch_scope_id() or getattr(current_user, 'branch_id', None)
            entry = GLService.create_manual_entry(
                description=description,
                lines=lines,
                entry_date=entry_date,
                notes=notes,
                created_by=current_user.id,
                branch_id=branch_id
            )
            
            LoggingCore.log_audit('create', 'gl_journal_entries', entry.id)
            
            flash(f'✅ تم إنشاء القيد {entry.entry_number} بنجاح', 'success')
            return redirect(url_for('ledger.view_entry', id=entry.id))
        
        except ValueError as e:
            flash(f'❌ خطأ: {str(e)}\n💡 تحقق من البيانات المدخلة وحاول مرة أخرى.', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'❌ خطأ: {str(e)}\n💡 تحقق من البيانات المدخلة وحاول مرة أخرى.', 'danger')
    
    from utils.gl_tenant import scope_gl_accounts
    accounts = scope_gl_accounts(
        GLAccount.query.filter_by(is_active=True, is_header=False)
    ).order_by(GLAccount.code).all()
    branches = get_accessible_branches(current_user)
    return render_template('ledger/manual_entry.html', accounts=accounts, branches=branches, today=date.today())


@ledger_bp.route('/entry/<int:id>')
@login_required
@permission_required('view_ledger')
def view_entry(id):
    """عرض تفاصيل القيد"""
    from utils.gl_tenant import gl_entry_query
    entry = gl_entry_query().filter_by(id=id).first_or_404()
    selected_branch_id = _effective_branch_id()
    if selected_branch_id is not None and entry.branch_id != selected_branch_id:
        return render_template('errors/403.html'), 403
    lines = entry.lines.all()
    
    return render_template('ledger/view_entry.html', entry=entry, lines=lines)


@ledger_bp.route('/entry/<int:id>/reverse', methods=['POST'])
@login_required
@permission_required('manage_ledger')
def reverse_entry(id):
    """عكس القيد"""
    try:
        from utils.gl_tenant import gl_entry_query
        entry = gl_entry_query().filter_by(id=id).first_or_404()
        selected_branch_id = _effective_branch_id()
        if selected_branch_id is not None and entry.branch_id != selected_branch_id:
            return render_template('errors/403.html'), 403
        
        description = request.form.get('description')
        reversed_entry = entry.reverse_entry(description)
        
        db.session.commit()
        
        LoggingCore.log_audit('create', 'gl_journal_entries', reversed_entry.id, 
                        changes={'reversed_from': entry.entry_number})
        
        flash(f'✅ تم عكس القيد بنجاح - القيد الجديد: {reversed_entry.entry_number}', 'success')
        return redirect(url_for('ledger.view_entry', id=reversed_entry.id))
    
    except ValueError as e:
        flash(f'❌ خطأ: {str(e)}', 'danger')
        return redirect(url_for('ledger.view_entry', id=id))
    except Exception as e:
        db.session.rollback()
        flash(f'❌ خطأ: {str(e)}', 'danger')
        return redirect(url_for('ledger.view_entry', id=id))


@ledger_bp.route('/api/accounts/search')
@login_required
@permission_required('view_ledger')
def api_search_accounts():
    """API للبحث عن الحسابات"""
    from utils.gl_tenant import scope_gl_accounts
    query = request.args.get('q', '').strip()
    
    accounts = scope_gl_accounts(GLAccount.query.filter(
        GLAccount.is_active == True,
        GLAccount.is_header == False,
        db.or_(
            GLAccount.code.ilike(f'%{query}%'),
            GLAccount.name.ilike(f'%{query}%'),
            GLAccount.name_ar.ilike(f'%{query}%')
        )
    )).order_by(GLAccount.code).limit(20).all()
    
    return jsonify([{
        'id': acc.id,
        'code': acc.code,
        'name': acc.name,
        'name_ar': acc.name_ar,
        'full_name': acc.full_name,
        'type': acc.type,
        'balance': float(acc.get_balance())
    } for acc in accounts])


@ledger_bp.route('/api/calculate-journal-balance', methods=['POST'])
@login_required
def api_calculate_journal_balance():
    """API لحساب توازن القيد اليدوي - Backend Calculation"""
    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        lines = data.get('lines', [])
        
        total_debit = Decimal('0')
        total_credit = Decimal('0')
        
        for line in lines:
            debit = Decimal(str(line.get('debit', 0) or 0))
            credit = Decimal(str(line.get('credit', 0) or 0))
            total_debit += debit
            total_credit += credit
        
        difference = abs(total_debit - total_credit)
        is_balanced = difference < Decimal('0.01') and total_debit > 0 and total_credit > 0
        
        return jsonify({
            'success': True,
            'total_debit': float(total_debit),
            'total_credit': float(total_credit),
            'difference': float(difference),
            'is_balanced': is_balanced
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400


@ledger_bp.route('/cash-flow')
@login_required
@permission_required('view_ledger')
def cash_flow():
    """قائمة التدفقات النقدية"""
    # الحصول على الفترة (آخر شهر افتراضياً)
    today = date.today()
    default_start = (today - timedelta(days=30)).strftime('%Y-%m-%d')
    default_end = today.strftime('%Y-%m-%d')
    
    date_from = request.args.get('date_from', default_start, type=str)
    date_to = request.args.get('date_to', default_end, type=str)
    branch_id = _effective_branch_id()
    
    try:
        report = CashFlowService.generate_cash_flow(date_from, date_to, branch_id=branch_id)
        
        return render_template('ledger/cash_flow.html',
                             report=report,
                             date_from=date_from,
                             date_to=date_to,
                             branches=get_accessible_branches(current_user),
                             selected_branch=branch_id)
    except Exception as e:
        flash(f'❌ فشل إنشاء قائمة التدفقات: {str(e)}\n💡 تحقق من الفترة المحددة وحاول مرة أخرى.', 'danger')
        return redirect(url_for('ledger.index'))


@ledger_bp.route('/aging-analysis')
@login_required
@permission_required('view_ledger')
def aging_analysis():
    """تحليل عمر الذمم"""
    analysis_type = request.args.get('type', 'receivables', type=str)  # receivables or payables
    as_of_date = request.args.get('as_of_date', type=str)
    branch_id = _effective_branch_id()
    
    try:
        if analysis_type == 'receivables':
            report = AgingAnalysisService.get_receivables_aging(as_of_date, branch_id=branch_id)
            title = 'تحليل عمر الذمم المدينة'
            gl_verify = AgingAnalysisService.verify_receivables_with_gl(as_of_date, branch_id=branch_id)
        else:
            report = AgingAnalysisService.get_payables_aging(as_of_date, branch_id=branch_id)
            title = 'تحليل عمر الذمم الدائنة'
            gl_verify = AgingAnalysisService.verify_payables_with_gl(as_of_date, branch_id=branch_id)
        
        return render_template('ledger/aging_analysis.html',
                             report=report,
                             analysis_type=analysis_type,
                             title=title,
                             gl_verify=gl_verify,
                             as_of_date=as_of_date or date.today().strftime('%Y-%m-%d'),
                             branches=get_accessible_branches(current_user),
                             selected_branch=branch_id)
    except Exception as e:
        flash(f'❌ فشل إنشاء تحليل الأعمار: {str(e)}\n💡 تحقق من البيانات وحاول مرة أخرى.', 'danger')
        return redirect(url_for('ledger.index'))

# ==================== لوحة التحكم الإدارية ====================

@ledger_bp.route('/admin-dashboard')
@login_required
@admin_required
def admin_dashboard():
    """لوحة تحكم شاملة لدفتر الأستاذ"""
    from utils.gl_tenant import gl_account_query, gl_entry_query, scoped_model_query
    from utils.tenanting import tenant_query

    def _accounts():
        return gl_account_query()

    def _entries():
        return gl_entry_query()

    # إحصائيات عامة
    total_accounts = _accounts().count()
    active_accounts = _accounts().filter_by(is_active=True).count()
    total_entries = _entries().count()
    posted_entries = _entries().filter_by(is_posted=True).count()
    
    # إحصائيات مالية
    cash_accounts = _accounts().filter(GLAccount.code.like('11%')).all()
    total_cash = sum(account.get_balance() for account in cash_accounts)
    
    # آخر القيود
    recent_entries = _entries().order_by(GLJournalEntry.created_at.desc()).limit(10).all()
    
    # الحسابات ذات الأرصدة العالية
    high_balance_accounts = []
    for account in _accounts().filter_by(is_active=True, is_header=False).all():
        balance = account.get_balance()
        if abs(balance) > 1000:  # أرصدة أعلى من 1000
            high_balance_accounts.append({
                'account': account,
                'balance': balance
            })
    
    # ترتيب حسب الرصيد
    high_balance_accounts.sort(key=lambda x: abs(x['balance']), reverse=True)
    
    # إحصائيات الشيكات
    total_cheques = tenant_query(Cheque).count()
    pending_cheques = tenant_query(Cheque).filter_by(status='pending').count()
    cleared_cheques = tenant_query(Cheque).filter_by(status='cleared').count()
    
    # إحصائيات المحافظ
    total_vaults = scoped_model_query(PaymentVault).count()
    active_vaults = scoped_model_query(PaymentVault).filter_by(is_locked=False).count()
    
    return render_template('admin/ledger/dashboard.html',
                         total_accounts=total_accounts,
                         active_accounts=active_accounts,
                         total_entries=total_entries,
                         posted_entries=posted_entries,
                         total_cash=total_cash,
                         recent_entries=recent_entries,
                         high_balance_accounts=high_balance_accounts[:10],
                         total_cheques=total_cheques,
                         pending_cheques=pending_cheques,
                         cleared_cheques=cleared_cheques,
                         total_vaults=total_vaults,
                         active_vaults=active_vaults)

@ledger_bp.route('/admin-accounts')
@login_required
@admin_required
def admin_accounts():
    """إدارة الحسابات المحاسبية"""
    from utils.gl_tenant import gl_account_query
    accounts = gl_account_query().order_by(GLAccount.code).all()
    return render_template('admin/ledger/accounts.html', accounts=accounts)

@ledger_bp.route('/admin-accounts/add', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_add_account():
    """إضافة حساب محاسبي جديد"""
    from utils.gl_tenant import gl_account_query, active_tenant_id
    if request.method == 'POST':
        try:
            try:
                from models import Tenant
                default_currency = resolve_default_currency()
            except Exception:
                default_currency = get_system_default_currency()
            code = request.form.get('code')
            name = request.form.get('name')
            name_ar = request.form.get('name_ar')
            account_type = request.form.get('type')
            parent_id = request.form.get('parent_id') or None
            currency = request.form.get('currency') or default_currency
            is_header = bool(request.form.get('is_header'))
            description = request.form.get('description')
            bank_name = request.form.get('bank_name')
            bank_account_number = request.form.get('bank_account_number')
            bank_iban = request.form.get('bank_iban')
            bank_swift_code = request.form.get('bank_swift_code')
            
            # التحقق من عدم تكرار الكود
            existing = gl_account_query().filter_by(code=code).first()
            if existing:
                flash('⚠️ كود الحساب موجود مسبقاً.\n💡 استخدم كود فريد أو اختر كود آخر.', 'danger')
                return redirect(url_for('ledger.admin_add_account'))
            
            # حساب المستوى
            level = 0
            if parent_id:
                parent = gl_account_query().filter_by(id=parent_id).first()
                level = parent.level + 1 if parent else 0
            
            account = GLAccount(
                code=code,
                name=name,
                name_ar=name_ar,
                type=account_type,
                parent_id=parent_id,
                currency=currency,
                is_header=is_header,
                level=level,
                description=description,
                tenant_id=active_tenant_id(),
                bank_name=bank_name,
                bank_account_number=bank_account_number,
                bank_iban=bank_iban,
                bank_swift_code=bank_swift_code,
            )
            
            db.session.add(account)
            db.session.commit()
            
            LoggingCore.log_audit('create', 'gl_accounts', account.id)
            flash(f'✅ تم إنشاء الحساب {account.full_name} بنجاح', 'success')
            return redirect(url_for('ledger.admin_accounts'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'❌ خطأ: {str(e)}\n💡 تحقق من البيانات المدخلة وحاول مرة أخرى.', 'danger')
    
    # الحصول على الحسابات الرئيسية للقائمة المنسدلة
    parent_accounts = gl_account_query().filter_by(is_header=True).order_by(GLAccount.code).all()
    return render_template('admin/ledger/add_account.html', parent_accounts=parent_accounts)

@ledger_bp.route('/admin-vaults')
@login_required
@admin_required
def admin_vaults():
    """إدارة الصناديق والمحافظ"""
    from utils.gl_tenant import scoped_model_query
    vaults = scoped_model_query(PaymentVault).all()
    return render_template('admin/ledger/vaults.html', vaults=vaults)

@ledger_bp.route('/admin-journals')
@login_required
@admin_required
def admin_journals():
    """إدارة القيود المحاسبية"""
    from utils.gl_tenant import gl_entry_query
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    entries = gl_entry_query().order_by(GLJournalEntry.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template('admin/ledger/journals.html', entries=entries)

@ledger_bp.route('/admin-reports')
@login_required
@admin_required
def admin_reports():
    """التقارير المالية المتقدمة"""
    return render_template('admin/ledger/reports.html')

@ledger_bp.route('/admin-trial-balance')
@login_required
@admin_required
def admin_trial_balance():
    """ميزان المراجعة"""
    date_from = request.args.get('date_from', date.today().strftime('%Y-%m-%d'))
    date_to = request.args.get('date_to', date.today().strftime('%Y-%m-%d'))
    
    # تحويل التواريخ
    try:
        date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
        date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        current_app.logger.warning('Invalid date format in trial balance, falling back to today')
        date_from = date_to = date.today()
    
    # حساب أرصدة الحسابات
    from utils.gl_tenant import gl_account_query
    accounts = gl_account_query().filter_by(is_active=True, is_header=False).order_by(GLAccount.code).all()
    trial_balance_data = []
    
    total_debit = total_credit = 0
    
    for account in accounts:
        balance = account.get_balance(date_from, date_to)
        if balance != 0:
            trial_balance_data.append({
                'account': account,
                'debit': balance if balance > 0 else 0,
                'credit': abs(balance) if balance < 0 else 0
            })
            total_debit += balance if balance > 0 else 0
            total_credit += abs(balance) if balance < 0 else 0
    
    return render_template('admin/ledger/trial_balance.html',
                         trial_balance_data=trial_balance_data,
                         total_debit=total_debit,
                         total_credit=total_credit,
                         date_from=date_from,
                         date_to=date_to)

@ledger_bp.route('/admin-balance-sheet')
@login_required
@admin_required
def admin_balance_sheet():
    """الميزانية العمومية"""
    as_of_date = request.args.get('as_of_date', date.today().strftime('%Y-%m-%d'))
    
    try:
        as_of_date = datetime.strptime(as_of_date, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        current_app.logger.warning('Invalid date format in balance sheet, falling back to today')
        as_of_date = date.today()
    
    # الأصول
    from utils.gl_tenant import gl_account_query
    assets = gl_account_query().filter_by(type='asset', is_active=True, is_header=False).order_by(GLAccount.code).all()
    assets_total = sum(account.get_balance(as_of_date=as_of_date) for account in assets)
    
    # الخصوم
    liabilities = gl_account_query().filter_by(type='liability', is_active=True, is_header=False).order_by(GLAccount.code).all()
    liabilities_total = sum(abs(account.get_balance(as_of_date=as_of_date)) for account in liabilities)
    
    # حقوق الملكية
    equity = gl_account_query().filter_by(type='equity', is_active=True, is_header=False).order_by(GLAccount.code).all()
    equity_total = sum(abs(account.get_balance(as_of_date=as_of_date)) for account in equity)
    
    return render_template('admin/ledger/balance_sheet.html',
                         assets=assets,
                         assets_total=assets_total,
                         liabilities=liabilities,
                         liabilities_total=liabilities_total,
                         equity=equity,
                         equity_total=equity_total,
                         as_of_date=as_of_date)

@ledger_bp.route('/budget-vs-actual')
@login_required
@permission_required('view_ledger')
def budget_vs_actual():
    """Budget vs Actual Report - compares budgeted amounts with GL actuals"""
    from models import Budget, BudgetLine
    from utils.gl_tenant import scope_gl_accounts
    from utils.tenanting import require_active_tenant_id
    from datetime import date
    from sqlalchemy import func
    
    tenant_id = require_active_tenant_id()
    branch_id = _effective_branch_id()
    
    # Get active budgets
    budget_query = Budget.query.filter_by(tenant_id=tenant_id, status='active')
    if branch_id:
        budget_query = budget_query.filter_by(branch_id=branch_id)
    budgets = budget_query.all()
    
    budget_data = []
    for budget in budgets:
        # Update actuals from GL
        budget.update_actuals()
        
        lines_data = []
        for line in budget.lines:
            lines_data.append({
                'account': line.account,
                'budgeted': float(line.budgeted_amount or 0),
                'actual': float(line.actual_amount or 0),
                'variance': float(line.variance or 0),
                'variance_pct': float(line.variance_percentage or 0),
                'status': line.variance_status,
                'status_ar': line.variance_status_ar,
            })
        
        budget_data.append({
            'budget': budget,
            'lines': lines_data,
            'total_budgeted': float(budget.total_budgeted or 0),
            'total_actual': float(budget.total_actual or 0),
            'total_variance': float(budget.total_variance or 0),
            'variance_pct': float(budget.variance_percentage or 0),
        })
    
    return render_template('ledger/budget_vs_actual.html',
                         budgets=budget_data,
                         branches=get_accessible_branches(current_user),
                         selected_branch=branch_id)

@ledger_bp.route('/admin-income-statement')
@login_required
@admin_required
def admin_income_statement():
    """قائمة الدخل"""
    date_from = request.args.get('date_from', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
    date_to = request.args.get('date_to', date.today().strftime('%Y-%m-%d'))
    
    try:
        date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
        date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        current_app.logger.warning('Invalid date format in income statement, falling back to defaults')
        date_from = date.today() - timedelta(days=30)
        date_to = date.today()
    
    # الإيرادات
    from utils.gl_tenant import gl_account_query
    revenues = gl_account_query().filter_by(type='revenue', is_active=True, is_header=False).order_by(GLAccount.code).all()
    revenues_total = sum(abs(account.get_balance(date_from, date_to)) for account in revenues)
    
    # المصروفات
    expenses = gl_account_query().filter_by(type='expense', is_active=True, is_header=False).order_by(GLAccount.code).all()
    expenses_total = sum(account.get_balance(date_from, date_to) for account in expenses)
    
    net_income = revenues_total - expenses_total
    
    return render_template('admin/ledger/income_statement.html',
                         revenues=revenues,
                         revenues_total=revenues_total,
                         expenses=expenses,
                         expenses_total=expenses_total,
                         net_income=net_income,
                         date_from=date_from,
                         date_to=date_to)

@ledger_bp.route('/admin-settings')
@login_required
@admin_required
def admin_settings():
    """إعدادات النظام المحاسبي"""
    return render_template('admin/ledger/settings.html')

