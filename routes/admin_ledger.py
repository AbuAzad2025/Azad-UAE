from flask_babel import gettext
from flask import (
    Blueprint,
    render_template,
    request,
    flash,
    redirect,
    url_for,
    jsonify,
    current_app,
)
from flask_login import login_required
from datetime import datetime, date, timedelta
from extensions import db
from models import GLAccount, GLJournalEntry, GLJournalLine
from services.gl_service import GLService
from utils.decorators import admin_required
from services.logging_core import LoggingCore
from utils.currency_utils import resolve_default_currency, get_system_default_currency
from utils.gl_tenant import (
    gl_account_query,
    gl_entry_query,
    scoped_model_query,
    active_tenant_id,
)
from utils.tenanting import tenant_query
from utils.db_safety import atomic_transaction

admin_ledger_bp = Blueprint("admin_ledger", __name__, url_prefix="/admin/ledger")


def _accounts():
    return gl_account_query()


def _entries():
    return gl_entry_query()


def _cheques():
    from models import Cheque

    return tenant_query(Cheque)


def _vaults():
    from models import PaymentVault

    return scoped_model_query(PaymentVault)


@admin_ledger_bp.route("/")
@login_required
@admin_required
def dashboard():
    """لوحة تحكم شاملة لدفتر الأستاذ"""

    total_accounts = _accounts().count()
    active_accounts = _accounts().filter_by(is_active=True).count()
    total_entries = _entries().count()
    posted_entries = _entries().filter_by(is_posted=True).count()

    cash_accounts = _accounts().filter(GLAccount.code.like("11%")).all()
    total_cash = sum(account.get_balance() for account in cash_accounts)

    recent_entries = _entries().order_by(GLJournalEntry.created_at.desc()).limit(10).all()

    high_balance_accounts = []
    for account in _accounts().filter_by(is_active=True, is_header=False).limit(500).all():
        balance = account.get_balance()
        if abs(balance) > 1000:
            high_balance_accounts.append({"account": account, "balance": balance})

    high_balance_accounts.sort(key=lambda x: abs(x["balance"]), reverse=True)

    total_cheques = _cheques().count()
    pending_cheques = _cheques().filter_by(status="pending").count()
    cleared_cheques = _cheques().filter_by(status="cleared").count()

    total_vaults = _vaults().count()
    active_vaults = _vaults().filter_by(is_locked=False).count()

    return render_template(
        "admin/ledger/dashboard.html",
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
        active_vaults=active_vaults,
    )


@admin_ledger_bp.route("/accounts")
@login_required
@admin_required
def accounts_management():
    """إدارة الحسابات المحاسبية"""
    accounts = _accounts().order_by(GLAccount.code).all()
    return render_template("admin/ledger/accounts.html", accounts=accounts)


@admin_ledger_bp.route("/accounts/add", methods=["GET", "POST"])
@login_required
@admin_required
def add_account():
    """إضافة حساب محاسبي جديد"""
    parent_accounts = _accounts().filter_by(is_header=True).order_by(GLAccount.code).all()
    default_form = {"is_active": "on"}

    if request.method == "POST":
        try:
            try:
                default_currency = resolve_default_currency()
            except Exception:
                default_currency = get_system_default_currency()
            code = (request.form.get("code") or "").strip()
            name = (request.form.get("name") or "").strip()
            name_ar = (request.form.get("name_ar") or "").strip()
            account_type = (request.form.get("type") or "").strip()
            parent_id_raw = (request.form.get("parent_id") or "").strip()
            parent_id = int(parent_id_raw) if parent_id_raw else None
            currency = request.form.get("currency") or default_currency
            is_header = "on" in request.form.getlist("is_header")
            is_active = "on" in request.form.getlist("is_active")
            description = request.form.get("description")

            if not account_type:
                flash(gettext("⚠️ يرجى اختيار نوع الحساب."), "warning")
                form_values = request.form.to_dict()
                form_values["is_header"] = "on" if is_header else "off"
                form_values["is_active"] = "on" if is_active else "off"
                return render_template(
                    "admin/ledger/add_account.html",
                    parent_accounts=parent_accounts,
                    form_data=form_values,
                )

            existing = _accounts().filter_by(code=code).first()
            if existing:
                flash(gettext("❌ كود الحساب موجود مسبقاً"), "danger")
                form_values = request.form.to_dict()
                form_values["is_header"] = "on" if is_header else "off"
                form_values["is_active"] = "on" if is_active else "off"
                return render_template(
                    "admin/ledger/add_account.html",
                    parent_accounts=parent_accounts,
                    form_data=form_values,
                )

            level = 0
            if parent_id:
                parent = _accounts().filter_by(id=parent_id).first()
                level = parent.level + 1 if parent else 0

            account = GLAccount(
                tenant_id=active_tenant_id(),
                code=code,
                name=name,
                name_ar=name_ar,
                type=account_type,
                parent_id=parent_id,
                currency=currency,
                is_header=is_header,
                is_active=is_active,
                level=level,
                description=description,
            )

            with atomic_transaction("add_gl_account"):
                db.session.add(account)
                LoggingCore.log_audit("create", "gl_accounts", account.id)
            flash(gettext(f"✅ تم إنشاء الحساب {account.full_name} بنجاح"), "success")
            return redirect(url_for("admin_ledger.accounts_management"))

        except Exception as e:
            current_app.logger.error(f"Error in admin ledger operation: {e}")
            from utils.error_messages import ErrorMessages

            flash(ErrorMessages.unexpected_error(), "danger")
            form_values = request.form.to_dict()
            form_values["is_header"] = "on" if "on" in request.form.getlist("is_header") else "off"
            form_values["is_active"] = "on" if "on" in request.form.getlist("is_active") else "off"
            return render_template(
                "admin/ledger/add_account.html",
                parent_accounts=parent_accounts,
                form_data=form_values,
            )

    return render_template(
        "admin/ledger/add_account.html",
        parent_accounts=parent_accounts,
        form_data=default_form,
    )


@admin_ledger_bp.route("/accounts/<int:id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_account(**kwargs):
    """تعديل حساب محاسبي"""
    record_id = kwargs.pop("id")
    account = _accounts().filter_by(id=record_id).first_or_404()

    if request.method == "POST":
        try:
            account.code = request.form.get("code")
            account.name = request.form.get("name")
            account.name_ar = request.form.get("name_ar")
            account.type = request.form.get("type")
            account.parent_id = request.form.get("parent_id") or None
            try:
                default_currency = resolve_default_currency()
            except Exception:
                default_currency = get_system_default_currency()
            account.currency = request.form.get("currency") or default_currency
            account.is_header = bool(request.form.get("is_header"))
            account.description = request.form.get("description")
            account.is_active = bool(request.form.get("is_active"))

            if account.parent_id:
                parent = _accounts().filter_by(id=account.parent_id).first()
                account.level = parent.level + 1 if parent else 0
            else:
                account.level = 0

            with atomic_transaction("edit_gl_account"):
                db.session.flush()
                LoggingCore.log_audit("update", "gl_accounts", account.id)
            flash(gettext(f"✅ تم تحديث الحساب {account.full_name} بنجاح"), "success")
            return redirect(url_for("admin_ledger.accounts_management"))

        except Exception as e:
            current_app.logger.error(f"Error in admin ledger operation: {e}")
            from utils.error_messages import ErrorMessages

            flash(ErrorMessages.unexpected_error(), "danger")

    parent_accounts = _accounts().filter_by(is_header=True).order_by(GLAccount.code).all()
    return render_template(
        "admin/ledger/edit_account.html",
        account=account,
        parent_accounts=parent_accounts,
    )


@admin_ledger_bp.route("/accounts/<int:id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_account(**kwargs):
    """حذف حساب محاسبي"""
    record_id = kwargs.pop("id")
    account = _accounts().filter_by(id=record_id).first_or_404()

    try:
        has_entries = scoped_model_query(GLJournalLine).filter_by(account_id=record_id).first()
        if has_entries:
            flash(gettext("❌ لا يمكن حذف الحساب لوجود قيود مرتبطة به"), "danger")
            return redirect(url_for("admin_ledger.accounts_management"))

        has_children = _accounts().filter_by(parent_id=record_id).first()
        if has_children:
            flash(gettext("❌ لا يمكن حذف الحساب لوجود حسابات فرعية مرتبطة به"), "danger")
            return redirect(url_for("admin_ledger.accounts_management"))

        with atomic_transaction("delete_gl_account"):
            db.session.delete(account)
            LoggingCore.log_audit("delete", "gl_accounts", record_id)
        flash(gettext(f"✅ تم حذف الحساب {account.full_name} بنجاح"), "success")

    except Exception as e:
        flash(gettext(f"❌ خطأ: {str(e)}"), "danger")

    return redirect(url_for("admin_ledger.accounts_management"))


@admin_ledger_bp.route("/vaults")
@login_required
@admin_required
def vaults_management():
    """إدارة الصناديق والمحافظ"""
    vaults = _vaults().all()
    return render_template("admin/ledger/vaults.html", vaults=vaults)


@admin_ledger_bp.route("/journals")
@login_required
@admin_required
def journals_management():
    """إدارة القيود المحاسبية"""
    page = request.args.get("page", 1, type=int)
    per_page = 20

    entries = (
        _entries().order_by(GLJournalEntry.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    )

    return render_template("admin/ledger/journals.html", entries=entries)


@admin_ledger_bp.route("/journals/<int:id>/view")
@login_required
@admin_required
def view_journal(**kwargs):
    """عرض تفاصيل قيد محاسبي"""
    record_id = kwargs.pop("id")
    entry = _entries().filter_by(id=record_id).first_or_404()
    return render_template("admin/ledger/view_journal.html", entry=entry)


@admin_ledger_bp.route("/journals/<int:id>/reverse", methods=["POST"])
@login_required
@admin_required
def reverse_journal(**kwargs):
    """عكس قيد محاسبي"""
    record_id = kwargs.pop("id")
    entry = _entries().filter_by(id=record_id).first_or_404()

    try:
        with atomic_transaction("reverse_journal"):
            entry.reverse_entry()
            LoggingCore.log_audit("reverse", "gl_journal_entries", record_id)
        flash(gettext(f"✅ تم عكس القيد {entry.entry_number} بنجاح"), "success")

    except Exception as e:
        flash(gettext(f"❌ خطأ: {str(e)}"), "danger")

    return redirect(url_for("admin_ledger.view_journal", id=record_id))


@admin_ledger_bp.route("/reports")
@login_required
@admin_required
def reports():
    """التقارير المالية المتقدمة"""
    return render_template("admin/ledger/reports.html")


@admin_ledger_bp.route("/reports/trial-balance")
@login_required
@admin_required
def trial_balance():
    """ميزان المراجعة"""
    date_from = request.args.get("date_from", date.today().strftime("%Y-%m-%d"))
    date_to = request.args.get("date_to", date.today().strftime("%Y-%m-%d"))

    try:
        date_from = datetime.strptime(date_from, "%Y-%m-%d").date()
        date_to = datetime.strptime(date_to, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        current_app.logger.warning("Invalid date format in admin trial balance, falling back to today")
        date_from = date_to = date.today()

    from services.gl_service import GLService

    accounts = _accounts().filter_by(is_active=True, is_header=False).order_by(GLAccount.code).all()
    _all_balances = GLService.get_all_account_balances(start_date=date_from, end_date=date_to)
    trial_balance_data = []

    total_debit = total_credit = 0

    for account in accounts:
        balance = _all_balances.get(account.id, 0)
        if balance != 0:
            trial_balance_data.append(
                {
                    "account": account,
                    "debit": balance if balance > 0 else 0,
                    "credit": abs(balance) if balance < 0 else 0,
                }
            )
            total_debit += balance if balance > 0 else 0
            total_credit += abs(balance) if balance < 0 else 0

    return render_template(
        "admin/ledger/trial_balance.html",
        trial_balance_data=trial_balance_data,
        total_debit=total_debit,
        total_credit=total_credit,
        date_from=date_from,
        date_to=date_to,
    )


@admin_ledger_bp.route("/reports/balance-sheet")
@login_required
@admin_required
def balance_sheet():
    """الميزانية العمومية"""
    as_of_date = request.args.get("as_of_date", date.today().strftime("%Y-%m-%d"))

    try:
        as_of_date = datetime.strptime(as_of_date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        current_app.logger.warning("Invalid date format in admin balance sheet, falling back to today")
        as_of_date = date.today()

    from services.gl_service import GLService

    _all_balances = GLService.get_all_account_balances(as_of_date=as_of_date)

    assets = _accounts().filter_by(type="asset", is_active=True, is_header=False).order_by(GLAccount.code).all()
    assets_total = sum(_all_balances.get(a.id, 0) for a in assets)

    liabilities = (
        _accounts().filter_by(type="liability", is_active=True, is_header=False).order_by(GLAccount.code).all()
    )
    liabilities_total = sum(abs(_all_balances.get(a.id, 0)) for a in liabilities)

    equity = _accounts().filter_by(type="equity", is_active=True, is_header=False).order_by(GLAccount.code).all()
    equity_total = sum(abs(_all_balances.get(a.id, 0)) for a in equity)

    return render_template(
        "admin/ledger/balance_sheet.html",
        assets=assets,
        assets_total=assets_total,
        liabilities=liabilities,
        liabilities_total=liabilities_total,
        equity=equity,
        equity_total=equity_total,
        as_of_date=as_of_date,
    )


@admin_ledger_bp.route("/reports/income-statement")
@login_required
@admin_required
def income_statement():
    """قائمة الدخل"""
    date_from = request.args.get("date_from", (date.today() - timedelta(days=30)).strftime("%Y-%m-%d"))
    date_to = request.args.get("date_to", date.today().strftime("%Y-%m-%d"))

    try:
        date_from = datetime.strptime(date_from, "%Y-%m-%d").date()
        date_to = datetime.strptime(date_to, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        current_app.logger.warning("Invalid date format in admin income statement, falling back to defaults")
        date_from = date.today() - timedelta(days=30)
        date_to = date.today()

    from services.gl_service import GLService

    _all_balances = GLService.get_all_account_balances(start_date=date_from, end_date=date_to)

    revenues = _accounts().filter_by(type="revenue", is_active=True, is_header=False).order_by(GLAccount.code).all()
    revenues_total = sum(abs(_all_balances.get(a.id, 0)) for a in revenues)

    expenses = _accounts().filter_by(type="expense", is_active=True, is_header=False).order_by(GLAccount.code).all()
    expenses_total = sum(_all_balances.get(a.id, 0) for a in expenses)

    net_income = revenues_total - expenses_total

    return render_template(
        "admin/ledger/income_statement.html",
        revenues=revenues,
        revenues_total=revenues_total,
        expenses=expenses,
        expenses_total=expenses_total,
        net_income=net_income,
        date_from=date_from,
        date_to=date_to,
    )


@admin_ledger_bp.route("/settings")
@login_required
@admin_required
def settings():
    """إعدادات النظام المحاسبي"""
    return render_template("admin/ledger/settings.html")


@admin_ledger_bp.route("/api/account-balance/<int:account_id>")
@login_required
@admin_required
def api_account_balance(account_id):
    """API للحصول على رصيد حساب"""
    account = _accounts().filter_by(id=account_id).first_or_404()
    balance = account.get_balance()

    return jsonify(
        {
            "account_code": account.code,
            "account_name": account.full_name,
            "balance": float(balance),
            "balance_formatted": f"{balance:,.2f}",
        }
    )


@admin_ledger_bp.route("/api/account-statement/<int:account_id>")
@login_required
@admin_required
def api_account_statement(account_id):
    """API لكشف حساب - مع فلترة اختيارية حسب الفرع للعزل"""
    account = _accounts().filter_by(id=account_id).first_or_404()
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")
    branch_id = request.args.get("branch_id", type=int)
    statement = GLService.get_account_statement(account_id, date_from, date_to, branch_id)
    return jsonify(
        {
            "account": {"code": account.code, "name": account.full_name},
            "statement": statement,
            "branch_id": branch_id,
        }
    )
