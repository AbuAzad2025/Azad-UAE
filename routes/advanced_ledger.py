from flask import (
    Blueprint,
    render_template,
    request,
    jsonify,
    flash,
    redirect,
    url_for,
    current_app,
)
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from decimal import Decimal
from extensions import db
from models import GLAccount, GLJournalEntry, Cheque
from models.advanced_accounting import CustomsTax, AdvancedExpense
from models.expense import ExpenseCategory
from services.advanced_journal_manager import AdvancedJournalEntryManager
from services.cheque_accounting_integration import ChequeAccountingIntegration
from services.real_time_listeners import accounting_event_stream
from services.advanced_analytics import AdvancedFinancialAnalytics
from utils.decorators import permission_required, admin_required
from services.logging_core import LoggingCore
from utils.currency_utils import resolve_default_currency, get_system_default_currency
from utils.gl_tenant import gl_account_query, gl_entry_query, active_tenant_id
from utils.db_safety import atomic_transaction
from utils.tenanting import tenant_get_or_404

advanced_ledger_bp = Blueprint(
    "advanced_ledger", __name__, url_prefix="/ledger/advanced"
)


def _accounts():
    return gl_account_query()


@advanced_ledger_bp.route("/professional-printing")
@login_required
@permission_required("view_ledger")
def professional_printing():
    """نظام الطباعة الاحترافي"""
    # بيانات تجريبية للطباعة
    trial_balance_data = []
    accounts = _accounts().filter_by(is_active=True, is_header=False).limit(20).all()

    total_debit = total_credit = 0

    for account in accounts:
        balance = account.get_balance()
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

    from models.invoice_settings import InvoiceSettings
    from utils.tenant_branding import get_print_header_context

    print_branding = get_print_header_context()
    settings = InvoiceSettings.get_active()

    trial_balance_json = [
        {
            "code": item["account"].code,
            "full_name": item["account"].full_name,
            "type_ar": item["account"].type_ar,
            "debit": item["debit"],
            "credit": item["credit"],
            "balance": item["account"].get_balance(),
        }
        for item in trial_balance_data
    ]

    return render_template(
        "ledger/professional_printing.html",
        trial_balance_data=trial_balance_data,
        trial_balance_json=trial_balance_json,
        total_debit=total_debit,
        total_credit=total_credit,
        date_from=date.today() - timedelta(days=30),
        date_to=date.today(),
        print_branding=print_branding,
        settings=settings,
    )


@advanced_ledger_bp.route("/customs-taxes")
@login_required
@admin_required
def customs_taxes():
    """إدارة الجمارك والضرائب"""
    tid = active_tenant_id(current_user)
    taxes = (
        CustomsTax.query.filter_by(is_active=True, tenant_id=tid)
        .order_by(CustomsTax.name_ar)
        .all()
    )
    return render_template("ledger/advanced/customs_taxes.html", taxes=taxes)


@advanced_ledger_bp.route("/customs-taxes/add", methods=["GET", "POST"])
@login_required
@admin_required
def add_customs_tax():
    """إضافة ضريبة أو جمرك جديد"""
    accounts = (
        _accounts()
        .filter_by(is_active=True, is_header=False)
        .order_by(GLAccount.code)
        .all()
    )

    if request.method == "POST":
        try:
            gl_account_id = request.form.get("gl_account_id", type=int)
            if not gl_account_id:
                flash("⚠️ يرجى اختيار الحساب المحاسبي.", "warning")
                return render_template(
                    "ledger/advanced/add_customs_tax.html",
                    accounts=accounts,
                    form_data=request.form,
                )

            tid = active_tenant_id(current_user)
            tax = CustomsTax(
                tenant_id=tid,
                name=request.form.get("name"),
                name_ar=request.form.get("name_ar"),
                tax_type=request.form.get("tax_type"),
                rate=Decimal(request.form.get("rate", 0)),
                is_percentage=bool(request.form.get("is_percentage")),
                fixed_amount=Decimal(request.form.get("fixed_amount", 0)),
                gl_account_id=gl_account_id,
                effective_from=datetime.strptime(
                    request.form.get("effective_from") or "", "%Y-%m-%d"
                ).date(),
                effective_to=(
                    datetime.strptime(
                        request.form.get("effective_to") or "", "%Y-%m-%d"
                    ).date()
                    if request.form.get("effective_to")
                    else None
                ),
                description=request.form.get("description"),
            )

            with atomic_transaction("add_customs_tax"):
                db.session.add(tax)
                LoggingCore.log_audit("create", "customs_taxes", tax.id)
            flash(f"✅ تم إضافة {tax.name_ar} بنجاح", "success")
            return redirect(url_for("advanced_ledger.customs_taxes"))

        except Exception as e:
            current_app.logger.error(f"Error in advanced ledger operation: {e}")
            from utils.error_messages import ErrorMessages

            flash(ErrorMessages.unexpected_error(), "danger")
            return render_template(
                "ledger/advanced/add_customs_tax.html",
                accounts=accounts,
                form_data=request.form,
            )

    return render_template("ledger/advanced/add_customs_tax.html", accounts=accounts)


@advanced_ledger_bp.route("/expense-categories")
@login_required
@admin_required
def expense_categories():
    """إدارة فئات المصروفات المتقدمة"""
    tid = active_tenant_id(current_user)
    categories = (
        ExpenseCategory.query.filter_by(is_active=True, tenant_id=tid)
        .order_by(ExpenseCategory.name)
        .all()
    )
    return render_template(
        "ledger/advanced/expense_categories.html", categories=categories
    )


@advanced_ledger_bp.route("/expense-categories/add", methods=["GET", "POST"])
@login_required
@admin_required
def add_expense_category():
    """إضافة فئة مصروفات جديدة"""
    tid = active_tenant_id(current_user)
    parent_categories = ExpenseCategory.query.filter_by(
        is_active=True, tenant_id=tid
    ).all()
    accounts = (
        _accounts()
        .filter_by(is_active=True, is_header=False)
        .order_by(GLAccount.code)
        .all()
    )

    if request.method == "POST":
        try:
            gl_account_id = request.form.get("gl_account_id", type=int)
            if not gl_account_id:
                flash("⚠️ يرجى اختيار الحساب المحاسبي.", "warning")
                return render_template(
                    "ledger/advanced/add_expense_category.html",
                    parent_categories=parent_categories,
                    accounts=accounts,
                    form_data=request.form,
                )

            (
                request.form.get("parent_id", type=int)
                if request.form.get("parent_id")
                else None
            )

            tid = active_tenant_id(current_user)
            account = _accounts().filter_by(id=gl_account_id).first()
            category = ExpenseCategory(
                tenant_id=tid,
                name=request.form.get("name"),
                name_ar=request.form.get("name_ar"),
                gl_account_code=account.code if account else None,
            )

            with atomic_transaction("add_expense_category"):
                db.session.add(category)
                LoggingCore.log_audit("create", "expense_categories", category.id)
            flash(f"✅ تم إضافة فئة المصروفات {category.name_ar} بنجاح", "success")
            return redirect(url_for("advanced_ledger.expense_categories"))

        except Exception as e:
            current_app.logger.error(f"Error in advanced ledger operation: {e}")
            from utils.error_messages import ErrorMessages

            flash(ErrorMessages.unexpected_error(), "danger")
            return render_template(
                "ledger/advanced/add_expense_category.html",
                parent_categories=parent_categories,
                accounts=accounts,
                form_data=request.form,
            )

    return render_template(
        "ledger/advanced/add_expense_category.html",
        parent_categories=parent_categories,
        accounts=accounts,
    )


@advanced_ledger_bp.route("/advanced-expenses")
@login_required
@permission_required("view_ledger")
def advanced_expenses():
    """إدارة المصروفات المتقدمة"""
    page = request.args.get("page", 1, type=int)
    per_page = 20

    tid = active_tenant_id(current_user)
    expenses = (
        AdvancedExpense.query.filter_by(tenant_id=tid)
        .order_by(AdvancedExpense.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    return render_template("ledger/advanced/advanced_expenses.html", expenses=expenses)


@advanced_ledger_bp.route("/advanced-expenses/add", methods=["GET", "POST"])
@login_required
@admin_required
def add_advanced_expense():
    """إضافة مصروف متقدم جديد"""
    if request.method == "POST":
        try:
            try:
                default_currency = resolve_default_currency()
            except Exception:
                default_currency = get_system_default_currency()
            tid = active_tenant_id(current_user)
            expense = AdvancedExpense(
                tenant_id=tid,
                expense_number=f"EXP-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                expense_date=datetime.strptime(
                    request.form.get("expense_date") or "", "%Y-%m-%d"
                ).date(),
                description=request.form.get("description"),
                description_ar=request.form.get("description_ar"),
                category_id=int(request.form.get("category_id") or 0),
                supplier_id=(
                    int(request.form.get("supplier_id") or 0)
                    if request.form.get("supplier_id")
                    else None
                ),
                amount=Decimal(request.form.get("amount", 0)),
                currency=request.form.get("currency") or default_currency,
                exchange_rate=Decimal(request.form.get("exchange_rate", 1)),
                amount_aed=Decimal(request.form.get("amount_aed", 0)),
                taxable_amount=Decimal(request.form.get("taxable_amount", 0)),
                tax_amount=Decimal(request.form.get("tax_amount", 0)),
                tax_rate=Decimal(request.form.get("tax_rate", 0)),
                tax_exempt=bool(request.form.get("tax_exempt")),
                customs_amount=Decimal(request.form.get("customs_amount", 0)),
                customs_rate=Decimal(request.form.get("customs_rate", 0)),
                customs_exempt=bool(request.form.get("customs_exempt")),
                payment_method=request.form.get("payment_method"),
                payment_status=request.form.get("payment_status", "pending"),
                due_date=(
                    datetime.strptime(
                        request.form.get("due_date") or "", "%Y-%m-%d"
                    ).date()
                    if request.form.get("due_date")
                    else None
                ),
                requires_approval=bool(request.form.get("requires_approval")),
                approval_status=request.form.get("approval_status", "pending"),
                has_receipt=bool(request.form.get("has_receipt")),
                receipt_number=request.form.get("receipt_number"),
                created_by=current_user.id,
            )

            # حساب الضرائب والجمارك
            expense.calculate_taxes()

            with atomic_transaction("add_advanced_expense"):
                db.session.add(expense)
                LoggingCore.log_audit("create", "advanced_expenses", expense.id)
            flash(f"✅ تم إضافة المصروف {expense.expense_number} بنجاح", "success")
            return redirect(url_for("advanced_ledger.advanced_expenses"))

        except Exception as e:
            current_app.logger.error(f"Error in advanced ledger operation: {e}")
            from utils.error_messages import ErrorMessages

            flash(ErrorMessages.unexpected_error(), "danger")

    # الحصول على البيانات المطلوبة
    tid = active_tenant_id(current_user)
    categories = ExpenseCategory.query.filter_by(is_active=True, tenant_id=tid).all()
    from models import Supplier

    suppliers = (
        Supplier.query.filter_by(tenant_id=tid)
        .with_entities(Supplier.id, Supplier.name)
        .all()
    )

    return render_template(
        "ledger/advanced/add_advanced_expense.html",
        categories=categories,
        suppliers=suppliers,
    )


@advanced_ledger_bp.route("/journal-management")
@login_required
@admin_required
def journal_management():
    """إدارة القيود المحاسبية المتقدمة"""
    page = request.args.get("page", 1, type=int)
    per_page = 20

    entries = (
        gl_entry_query()
        .order_by(GLJournalEntry.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    return render_template("ledger/advanced/journal_management.html", entries=entries)


@advanced_ledger_bp.route(
    "/journal-management/<int:entry_id>/reverse", methods=["POST"]
)
@login_required
@admin_required
def reverse_journal_entry(entry_id):
    """عكس قيد محاسبي"""
    try:
        reason = request.form.get("reason", "عكس القيد")

        with atomic_transaction("reverse_journal_entry"):
            reversal_entry = AdvancedJournalEntryManager.reverse_entry_advanced(
                entry_id=entry_id,
                reversed_by=current_user,
                reason=reason,
                create_reversal_entry=True,
            )

        flash(
            f"✅ تم عكس القيد بنجاح - القيد العكسي: {reversal_entry.entry_number}",
            "success",
        )

    except Exception as e:
        current_app.logger.error(f"Error reversing journal entry {entry_id}: {e}")
        from utils.error_messages import ErrorMessages

        flash(ErrorMessages.unexpected_error(), "danger")

    return redirect(url_for("advanced_ledger.journal_management"))


@advanced_ledger_bp.route("/journal-management/<int:entry_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_journal_entry(entry_id):
    """حذف قيد محاسبي"""
    try:
        reason = request.form.get("reason", "حذف القيد")

        with atomic_transaction("delete_journal_entry"):
            AdvancedJournalEntryManager.delete_entry(
                entry_id=entry_id, deleted_by=current_user, reason=reason
            )

        flash("✅ تم إلغاء القيد بنجاح", "success")

    except Exception as e:
        current_app.logger.error(f"Error deleting journal entry {entry_id}: {e}")
        from utils.error_messages import ErrorMessages

        flash(ErrorMessages.unexpected_error(), "danger")

    return redirect(url_for("advanced_ledger.journal_management"))


@advanced_ledger_bp.route(
    "/journal-management/<int:entry_id>/approve", methods=["POST"]
)
@login_required
@admin_required
def approve_journal_entry(entry_id):
    """الموافقة على قيد محاسبي"""
    try:
        approval_notes = request.form.get("approval_notes", "موافقة على القيد")

        with atomic_transaction("approve_journal_entry"):
            AdvancedJournalEntryManager.approve_entry(
                entry_id=entry_id,
                approved_by=current_user,
                approval_notes=approval_notes,
            )

        flash("✅ تم الموافقة على القيد وترحيله بنجاح", "success")

    except Exception as e:
        current_app.logger.error(f"Error approving journal entry {entry_id}: {e}")
        from utils.error_messages import ErrorMessages

        flash(ErrorMessages.unexpected_error(), "danger")

    return redirect(url_for("advanced_ledger.journal_management"))


@advanced_ledger_bp.route("/cheque-integration")
@login_required
@permission_required("view_ledger")
def cheque_integration():
    """تكامل الشيكات مع النظام المحاسبي"""
    tid = active_tenant_id(current_user)
    # الحصول على الشيكات الأخيرة
    recent_cheques = (
        Cheque.query.filter_by(tenant_id=tid)
        .order_by(Cheque.updated_at.desc())
        .limit(20)
        .all()
    )

    # إحصائيات الشيكات
    stats = {
        "total_cheques": Cheque.query.filter_by(tenant_id=tid).count(),
        "pending_cheques": Cheque.query.filter_by(
            tenant_id=tid, status="pending"
        ).count(),
        "cleared_cheques": Cheque.query.filter_by(
            tenant_id=tid, status="cleared"
        ).count(),
        "bounced_cheques": Cheque.query.filter_by(
            tenant_id=tid, status="bounced"
        ).count(),
        "total_amount": db.session.query(db.func.sum(Cheque.amount_aed))
        .filter_by(tenant_id=tid)
        .scalar()
        or 0,
    }

    return render_template(
        "ledger/advanced/cheque_integration.html",
        recent_cheques=recent_cheques,
        stats=stats,
    )


@advanced_ledger_bp.route(
    "/cheque-integration/<int:cheque_id>/receive", methods=["POST"]
)
@login_required
@admin_required
def receive_cheque(cheque_id):
    """تسجيل استلام شيك"""
    cheque = tenant_get_or_404(Cheque, cheque_id)
    try:
        with atomic_transaction("advanced_receive_cheque"):
            entry = ChequeAccountingIntegration.receive_cheque(
                cheque_id=cheque.id, received_by=current_user
            )

        flash(
            f"✅ تم تسجيل استلام الشيك بنجاح - القيد: {entry.entry_number}", "success"
        )

    except Exception as e:
        current_app.logger.error(f"Error receiving cheque {cheque_id}: {e}")
        from utils.error_messages import ErrorMessages

        flash(ErrorMessages.unexpected_error(), "danger")

    return redirect(url_for("advanced_ledger.cheque_integration"))


@advanced_ledger_bp.route("/cheque-integration/<int:cheque_id>/clear", methods=["POST"])
@login_required
@admin_required
def clear_cheque(cheque_id):
    """تسجيل صرف شيك"""
    cheque = tenant_get_or_404(Cheque, cheque_id)
    try:
        with atomic_transaction("advanced_clear_cheque"):
            bank_charges = Decimal(request.form.get("bank_charges", 0))
            exchange_gain_loss = Decimal(request.form.get("exchange_gain_loss", 0))

            entry = ChequeAccountingIntegration.clear_cheque(
                cheque_id=cheque.id,
                cleared_by=current_user,
                bank_charges=bank_charges,
                exchange_gain_loss=exchange_gain_loss,
            )

        flash(f"✅ تم تسجيل صرف الشيك بنجاح - القيد: {entry.entry_number}", "success")

    except Exception as e:
        current_app.logger.error(f"Error clearing cheque {cheque_id}: {e}")
        from utils.error_messages import ErrorMessages

        flash(ErrorMessages.unexpected_error(), "danger")

    return redirect(url_for("advanced_ledger.cheque_integration"))


@advanced_ledger_bp.route("/real-time-events")
@login_required
@admin_required
def real_time_events():
    """مستمعات الأحداث اللحظية"""
    # الحصول على الأحداث الأخيرة
    recent_events = accounting_event_stream.get_recent_events(limit=100)

    # إحصائيات الأحداث
    event_stats = {}
    for event in recent_events:
        event_type = event["type"]
        event_stats[event_type] = event_stats.get(event_type, 0) + 1

    return render_template(
        "ledger/advanced/real_time_events.html",
        recent_events=recent_events,
        event_stats=event_stats,
    )


@advanced_ledger_bp.route("/api/events/stream")
@login_required
@admin_required
def events_stream_api():
    """API لتيار الأحداث"""
    event_type = request.args.get("type")
    limit = int(request.args.get("limit", 50))

    if event_type:
        events = accounting_event_stream.get_events_by_type(event_type)
    else:
        events = accounting_event_stream.get_recent_events(limit)

    return jsonify({"success": True, "events": events, "total": len(events)})


@advanced_ledger_bp.route("/api/cheque/<int:cheque_id>/accounting-summary")
@login_required
@permission_required("view_ledger")
def cheque_accounting_summary_api(cheque_id):
    """API لملخص محاسبي للشيك"""
    try:
        summary = ChequeAccountingIntegration.get_cheque_accounting_summary(cheque_id)
        return jsonify({"success": True, "summary": summary})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@advanced_ledger_bp.route("/professional-reports")
@login_required
@permission_required("view_ledger")
def professional_reports():
    """تقارير مالية احترافية مع رسوم بيانية"""
    # الحصول على البيانات
    trends = AdvancedFinancialAnalytics.get_trend_analysis(months=12)
    AdvancedFinancialAnalytics.get_expense_breakdown()
    AdvancedFinancialAnalytics.get_revenue_breakdown()

    # حساب الإحصائيات
    total_revenue = sum(item["revenue"] for item in trends)
    total_expenses = sum(item["expenses"] for item in trends)
    net_profit = total_revenue - total_expenses
    profit_margin = (net_profit / total_revenue * 100) if total_revenue > 0 else 0

    # تحضير البيانات للرسوم البيانية
    months = [item["month"] for item in trends]
    revenue_data = [item["revenue"] for item in trends]
    expense_data = [item["expenses"] for item in trends]
    profit_data = [item["profit"] for item in trends]

    return render_template(
        "ledger/advanced/professional_reports.html",
        monthly_data=trends,
        total_revenue=total_revenue,
        total_expenses=total_expenses,
        net_profit=net_profit,
        profit_margin=profit_margin,
        months=months,
        revenue_data=revenue_data,
        expense_data=expense_data,
        profit_data=profit_data,
        date_from=date.today() - timedelta(days=365),
        date_to=date.today(),
    )


@advanced_ledger_bp.route("/advanced-analytics")
@login_required
@admin_required
def advanced_analytics():
    """نظام التحليل المالي المتقدم"""
    # الحصول على جميع البيانات التحليلية
    dashboard_summary = AdvancedFinancialAnalytics.get_dashboard_summary()

    return render_template(
        "ledger/advanced/advanced_analytics.html",
        summary=dashboard_summary,
        ratios=dashboard_summary["ratios"],
        trends=dashboard_summary["trends"],
        expense_breakdown=dashboard_summary["expense_breakdown"],
        revenue_breakdown=dashboard_summary["revenue_breakdown"],
        forecast=dashboard_summary["forecast"],
    )


@advanced_ledger_bp.route("/api/financial-ratios")
@login_required
@permission_required("view_ledger")
def api_financial_ratios():
    """API للنسب المالية"""
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")

    if date_from:
        date_from = datetime.strptime(date_from, "%Y-%m-%d").date()
    if date_to:
        date_to = datetime.strptime(date_to, "%Y-%m-%d").date()

    ratios = AdvancedFinancialAnalytics.get_financial_ratios(date_from, date_to)

    return jsonify({"success": True, "ratios": ratios})


@advanced_ledger_bp.route("/api/trend-analysis")
@login_required
@permission_required("view_ledger")
def api_trend_analysis():
    """API لتحليل الاتجاهات"""
    months = int(request.args.get("months", 12))

    trends = AdvancedFinancialAnalytics.get_trend_analysis(months=months)

    return jsonify({"success": True, "trends": trends})


@advanced_ledger_bp.route("/api/forecasting")
@login_required
@admin_required
def api_forecasting():
    """API للتوقعات المالية"""
    months_ahead = int(request.args.get("months", 6))

    forecast = AdvancedFinancialAnalytics.get_forecasting_data(
        months_ahead=months_ahead
    )

    return jsonify({"success": True, "forecast": forecast})
