"""
مسارات الشيكات - Cheques Routes
إدارة الشيكات الواردة والصادرة
"""

from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    request,
    jsonify,
    current_app,
)
from flask_login import login_required, current_user
from extensions import db, limiter
from models import Cheque, Customer, Supplier, Sale, Receipt
from services.currency_service import CurrencyService
from services.exchange_rate_service import ExchangeRateService
from services.cheque_service import (
    calculate_amount_aed,
    process_cheque_receive,
    process_cheque_issue,
    process_cheque_deposit,
    process_cheque_clear,
    process_cheque_bounce,
    process_cheque_cancel,
)
from utils.db_safety import atomic_transaction
from utils.decorators import admin_required, permission_required, branch_scope_id
from utils.tenanting import get_active_tenant_id
from utils.branching import should_show_all_branch_columns
from services.logging_core import LoggingCore
from utils.helpers import generate_number
from utils.currency_utils import resolve_default_currency, get_system_default_currency
from datetime import datetime
from decimal import Decimal

cheques_bp = Blueprint("cheques", __name__, url_prefix="/cheques")


def _scoped_cheques_query():
    tid = get_active_tenant_id(current_user)
    query = Cheque.query.filter_by(is_active=True)
    if tid is not None:
        query = query.filter(Cheque.tenant_id == tid)
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None:
        query = query.filter(Cheque.branch_id == scoped_branch_id)
    return query


def _ensure_cheque_scope(cheque):
    tid = get_active_tenant_id(current_user)
    if tid is not None and getattr(cheque, "tenant_id", None) != tid:
        return False
    scoped_branch_id = branch_scope_id()
    return scoped_branch_id is None or cheque.branch_id == scoped_branch_id


def _get_cheque_or_404(cheque_id):
    from utils.tenanting import tenant_get_or_404

    return tenant_get_or_404(Cheque, cheque_id)


def _resolve_transaction_rate(currency, user_rate=None):
    rate_info = ExchangeRateService.resolve_exchange_rate_for_transaction(
        currency,
        "AED",
        user_rate=user_rate,
    )
    return Decimal(str(rate_info["rate"]))


def _scoped_customers_query():
    from models import Payment
    from sqlalchemy import select

    tid = get_active_tenant_id(current_user)
    scoped_branch_id = branch_scope_id()
    query = Customer.query.filter(Customer.is_active)
    if tid is not None:
        query = query.filter(Customer.tenant_id == tid)
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

    tid = get_active_tenant_id(current_user)
    scoped_branch_id = branch_scope_id()
    query = Supplier.query.filter(Supplier.is_active)
    if tid is not None:
        query = query.filter(Supplier.tenant_id == tid)
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


@cheques_bp.route("/")
@login_required
@permission_required("manage_payments")
def index():
    """قائمة كل الشيكات"""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)
    cheque_type = request.args.get("type", "", type=str)
    status = request.args.get("status", "", type=str)
    search = request.args.get("search", "", type=str)

    tid = get_active_tenant_id(current_user)
    # تحديث حالة كل الشيكات
    scoped_branch_id = branch_scope_id()
    Cheque.update_all_statuses(tenant_id=tid, branch_id=scoped_branch_id)

    query = _scoped_cheques_query()

    if cheque_type:
        query = query.filter_by(cheque_type=cheque_type)

    if status:
        query = query.filter_by(status=status)

    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            db.or_(
                Cheque.cheque_number.ilike(search_filter),
                Cheque.cheque_bank_number.ilike(search_filter),
                Cheque.bank_name.ilike(search_filter),
                Cheque.drawer_name.ilike(search_filter),
                Cheque.payee_name.ilike(search_filter),
            )
        )

    pagination = query.order_by(Cheque.due_date).paginate(
        page=page, per_page=per_page, error_out=False
    )

    stats = Cheque.get_statistics(tenant_id=tid, branch_id=scoped_branch_id)

    return render_template(
        "cheques/index.html",
        cheques=pagination.items,
        pagination=pagination,
        stats=stats,
        show_branch_columns=should_show_all_branch_columns(current_user),
    )


@cheques_bp.route("/incoming")
@login_required
@permission_required("manage_payments")
def incoming():
    """الشيكات الواردة"""
    page = request.args.get("page", 1, type=int)
    status = request.args.get("status", "", type=str)

    tid = get_active_tenant_id(current_user)
    scoped_branch_id = branch_scope_id()
    Cheque.update_all_statuses(tenant_id=tid, branch_id=scoped_branch_id)

    query = _scoped_cheques_query().filter_by(cheque_type="incoming")

    if status:
        query = query.filter_by(status=status)

    pagination = query.order_by(Cheque.due_date).paginate(
        page=page, per_page=25, error_out=False
    )

    stats = Cheque.get_statistics(tenant_id=tid, branch_id=scoped_branch_id)

    return render_template(
        "cheques/incoming.html",
        cheques=pagination.items,
        pagination=pagination,
        stats=stats,
    )


@cheques_bp.route("/outgoing")
@login_required
@permission_required("manage_payments")
def outgoing():
    """الشيكات الصادرة"""
    page = request.args.get("page", 1, type=int)
    status = request.args.get("status", "", type=str)

    tid = get_active_tenant_id(current_user)
    scoped_branch_id = branch_scope_id()
    Cheque.update_all_statuses(tenant_id=tid, branch_id=scoped_branch_id)

    query = _scoped_cheques_query().filter_by(cheque_type="outgoing")

    if status:
        query = query.filter_by(status=status)

    pagination = query.order_by(Cheque.due_date).paginate(
        page=page, per_page=25, error_out=False
    )

    stats = Cheque.get_statistics(tenant_id=tid, branch_id=scoped_branch_id)

    return render_template(
        "cheques/outgoing.html",
        cheques=pagination.items,
        pagination=pagination,
        stats=stats,
    )


@cheques_bp.route("/create", methods=["GET", "POST"])
@login_required
@permission_required("manage_payments")
@limiter.limit("10 per minute", methods=["POST"])
def create():
    """إضافة شيك جديد"""
    if request.method == "POST":
        try:
            cheque_branch_id = branch_scope_id() or getattr(
                current_user, "branch_id", None
            )
            cheque_number = generate_number(
                "CHQ", Cheque, "cheque_number", branch_id=cheque_branch_id
            )

            cheque_type = (request.form.get("cheque_type") or "").strip()
            if not cheque_type:
                flash("⚠️ يرجى اختيار نوع الشيك.", "warning")
                customers = _scoped_customers_query().order_by(Customer.name).all()
                suppliers = _scoped_suppliers_query().order_by(Supplier.name).all()
                try:
                    _dc = resolve_default_currency()
                except Exception:
                    _dc = get_system_default_currency()
                exchange_rates = CurrencyService.get_all_rates(_dc)
                return render_template(
                    "cheques/create.html",
                    customers=customers,
                    suppliers=suppliers,
                    exchange_rates=exchange_rates,
                )
            amount = Decimal(str(request.form.get("amount")))
            try:
                default_currency = resolve_default_currency()
            except Exception as e:
                import sys
                import traceback

                sys.stderr.write(
                    f"[CHEQUES_WARNING] Failed to get tenant default currency (create cheque): {e}\n"
                )
                traceback.print_exc()
                try:
                    LoggingCore.log_error(
                        message=str(e),
                        category="CHEQUES",
                        source="routes.cheques.create_cheque.get_default_currency",
                        level="WARNING",
                        exception=e,
                    )
                except Exception:
                    current_app.logger.exception("Failed to log currency resolution error for cheque creation")
                default_currency = get_system_default_currency()
            currency = request.form.get("currency") or default_currency

            # حساب سعر الصرف
            exchange_rate = _resolve_transaction_rate(
                currency,
                request.form.get("exchange_rate", type=float),
            )

            # تحويل التواريخ
            issue_date = datetime.strptime(
                request.form.get("issue_date") or "", "%Y-%m-%d"
            ).date()
            due_date = datetime.strptime(
                request.form.get("due_date") or "", "%Y-%m-%d"
            ).date()
            customer_id = request.form.get("customer_id", type=int) or None
            supplier_id = request.form.get("supplier_id", type=int) or None
            if (
                customer_id
                and not _scoped_customers_query()
                .filter(Customer.id == customer_id)
                .first()
            ):
                flash("⚠️ العميل المحدد خارج نطاق الفرع الحالي.", "warning")
                customers = _scoped_customers_query().order_by(Customer.name).all()
                suppliers = _scoped_suppliers_query().order_by(Supplier.name).all()
                exchange_rates = CurrencyService.get_all_rates(default_currency)
                return render_template(
                    "cheques/create.html",
                    customers=customers,
                    suppliers=suppliers,
                    exchange_rates=exchange_rates,
                )
            if (
                supplier_id
                and not _scoped_suppliers_query()
                .filter(Supplier.id == supplier_id)
                .first()
            ):
                flash("⚠️ المورد المحدد خارج نطاق الفرع الحالي.", "warning")
                customers = _scoped_customers_query().order_by(Customer.name).all()
                suppliers = _scoped_suppliers_query().order_by(Supplier.name).all()
                exchange_rates = CurrencyService.get_all_rates(default_currency)
                return render_template(
                    "cheques/create.html",
                    customers=customers,
                    suppliers=suppliers,
                    exchange_rates=exchange_rates,
                )

            cheque = Cheque(
                tenant_id=getattr(current_user, "tenant_id", None),
                cheque_number=cheque_number,
                cheque_bank_number=request.form.get("cheque_bank_number"),
                cheque_type=cheque_type,
                bank_name=request.form.get("bank_name"),
                bank_branch=request.form.get("bank_branch"),
                account_number=request.form.get("account_number"),
                amount=amount,
                currency=currency,
                exchange_rate=exchange_rate,
                issue_date=issue_date,
                due_date=due_date,
                drawer_name=request.form.get("drawer_name"),
                drawer_id_number=request.form.get("drawer_id_number"),
                payee_name=request.form.get("payee_name"),
                customer_id=customer_id,
                supplier_id=supplier_id,
                notes=request.form.get("notes"),
                user_id=current_user.id,
                branch_id=cheque_branch_id,
            )

            calculate_amount_aed(cheque)
            cheque.update_status_based_on_date()

            with atomic_transaction("cheque_create"):
                db.session.add(cheque)
                db.session.flush()
                if cheque.cheque_type == "incoming":
                    process_cheque_receive(cheque)
                elif cheque.cheque_type == "outgoing":
                    process_cheque_issue(cheque)
                LoggingCore.log_audit("create", "cheques", cheque.id)

            flash(f"✅ تم إضافة الشيك {cheque.cheque_bank_number} بنجاح", "success")
            return redirect(url_for("cheques.view", id=cheque.id))

        except Exception as e:
            current_app.logger.error(f"Error in cheque operation: {e}")
            from utils.error_messages import ErrorMessages
            import uuid as _uuid

            flash(
                ErrorMessages.unexpected_error(error_id=_uuid.uuid4().hex[:8]), "danger"
            )

    try:
        default_currency = resolve_default_currency()
    except Exception:
        default_currency = get_system_default_currency()
    customers = _scoped_customers_query().order_by(Customer.name).all()
    suppliers = _scoped_suppliers_query().order_by(Supplier.name).all()
    exchange_rates = CurrencyService.get_all_rates(default_currency)

    return render_template(
        "cheques/create.html",
        customers=customers,
        suppliers=suppliers,
        exchange_rates=exchange_rates,
    )


@cheques_bp.route("/<int:id>")
@login_required
@permission_required("manage_payments")
def view(**kwargs):
    """عرض تفاصيل الشيك"""
    record_id = kwargs.pop("id")
    cheque = _get_cheque_or_404(record_id)
    if not _ensure_cheque_scope(cheque):
        return render_template("errors/403.html"), 403
    cheque.update_status_based_on_date()

    # إضافة today للـ template
    today = datetime.now().strftime("%Y-%m-%d")

    from models import Tenant
    tenant_default_currency = ""
    tenant = Tenant.get_current()
    if tenant:
        tenant_default_currency = tenant.get_base_currency if tenant else ""
    is_foreign_currency = bool(cheque.currency != tenant_default_currency)

    return render_template(
        "cheques/view.html",
        cheque=cheque,
        today=today,
        is_foreign_currency=is_foreign_currency,
    )


@cheques_bp.route("/<int:id>/edit", methods=["GET", "POST"])
@login_required
@permission_required("manage_payments")
def edit(**kwargs):
    """تعديل الشيك"""
    record_id = kwargs.pop("id")
    cheque = _get_cheque_or_404(record_id)
    if not _ensure_cheque_scope(cheque):
        return render_template("errors/403.html"), 403

    # لا يمكن تعديل شيك تم صرفه أو ملغي
    if cheque.status in ["cleared", "cancelled", "bounced"]:
        flash(
            "⚠️ لا يمكن تعديل شيك تم صرفه أو إلغاؤه.\n💡 الشيكات المصروفة أو الملغاة لا يمكن تعديلها للحفاظ على السجلات.",
            "danger",
        )
        return redirect(url_for("cheques.view", id=record_id))

    if request.method == "POST":
        try:
            with atomic_transaction("cheque_update"):
                cheque.cheque_bank_number = request.form.get("cheque_bank_number")
                cheque.bank_name = request.form.get("bank_name")
                cheque.bank_branch = request.form.get("bank_branch")
                cheque.account_number = request.form.get("account_number")

                cheque.amount = Decimal(str(request.form.get("amount")))
                try:
                    default_currency = resolve_default_currency()
                except Exception as e:
                    import sys
                    import traceback

                    sys.stderr.write(
                        f"[CHEQUES_WARNING] Failed to get tenant default currency (create cheque): {e}\n"
                    )
                    traceback.print_exc()
                    try:
                        LoggingCore.log_error(
                            message=str(e),
                            category="CHEQUES",
                            source="routes.cheques.create_cheque.get_default_currency",
                            level="WARNING",
                            exception=e,
                        )
                    except Exception:
                        current_app.logger.exception("Failed to log currency resolution error for cheque update")
                    default_currency = get_system_default_currency()
                cheque.currency = request.form.get("currency") or default_currency

                exchange_rate = _resolve_transaction_rate(
                    cheque.currency,
                    request.form.get("exchange_rate", type=float),
                )
                cheque.exchange_rate = exchange_rate

                cheque.issue_date = datetime.strptime(
                    request.form.get("issue_date") or "", "%Y-%m-%d"
                ).date()
                cheque.due_date = datetime.strptime(
                    request.form.get("due_date") or "", "%Y-%m-%d"
                ).date()

                cheque.drawer_name = request.form.get("drawer_name")
                cheque.drawer_id_number = request.form.get("drawer_id_number")
                cheque.payee_name = request.form.get("payee_name")
                cheque.notes = request.form.get("notes")

                calculate_amount_aed(cheque)
                cheque.update_status_based_on_date()

                LoggingCore.log_audit("update", "cheques", record_id)

            flash("✅ تم تحديث الشيك بنجاح", "success")
            return redirect(url_for("cheques.view", id=record_id))

        except Exception as e:
            current_app.logger.error(f"Error in cheque operation: {e}")
            from utils.error_messages import ErrorMessages
            import uuid as _uuid

            flash(
                ErrorMessages.unexpected_error(error_id=_uuid.uuid4().hex[:8]), "danger"
            )

    try:
        default_currency = resolve_default_currency()
    except Exception:
        default_currency = get_system_default_currency()
    customers = _scoped_customers_query().order_by(Customer.name).all()
    suppliers = _scoped_suppliers_query().order_by(Supplier.name).all()
    exchange_rates = CurrencyService.get_all_rates(default_currency)

    return render_template(
        "cheques/edit.html",
        cheque=cheque,
        customers=customers,
        suppliers=suppliers,
        exchange_rates=exchange_rates,
    )


@cheques_bp.route("/<int:id>/deposit", methods=["POST"])
@login_required
@permission_required("manage_payments")
def deposit_cheque(**kwargs):
    """إيداع الشيك في البنك - الخطوة 1"""
    record_id = kwargs.pop("id")
    cheque = _get_cheque_or_404(record_id)
    if not _ensure_cheque_scope(cheque):
        return render_template("errors/403.html"), 403

    try:
        deposit_date_str = request.form.get("deposit_date")
        deposit_date = (
            datetime.strptime(deposit_date_str, "%Y-%m-%d").date()
            if deposit_date_str
            else None
        )

        with atomic_transaction("cheque_deposit"):
            process_cheque_deposit(cheque, deposit_date)
            LoggingCore.log_audit(
                "cheque_deposit",
                "cheques",
                record_id,
                {"message": f"إيداع شيك رقم {cheque.cheque_bank_number} في البنك"},
            )

        flash(f"✅ تم إيداع الشيك {cheque.cheque_bank_number} في البنك", "success")

    except ValueError as e:
        current_app.logger.warning(f"ValueError in cheque operation: {e}")
        flash(f"❌ خطأ: {str(e)}", "error")
    except Exception as e:
        flash(f"❌ خطأ: {str(e)}\n💡 تحقق من البيانات وحاول مرة أخرى.", "danger")

    return redirect(url_for("cheques.view", id=record_id))


@cheques_bp.route("/<int:id>/clear", methods=["POST"])
@login_required
@permission_required("manage_payments")
def clear_cheque(**kwargs):
    """تأكيد صرف الشيك من البنك - الخطوة 2 - المحاسبة الفعلية"""
    record_id = kwargs.pop("id")
    cheque = _get_cheque_or_404(record_id)
    if not _ensure_cheque_scope(cheque):
        return render_template("errors/403.html"), 403

    try:
        clearance_date_str = request.form.get("clearance_date")
        clearance_date = (
            datetime.strptime(clearance_date_str, "%Y-%m-%d").date()
            if clearance_date_str
            else None
        )

        # سعر الصرف وقت الصرف (اختياري)
        clearance_exchange_rate = request.form.get(
            "clearance_exchange_rate", type=float
        )

        try:
            default_currency = resolve_default_currency()
        except Exception:
            default_currency = get_system_default_currency()

        # تأكيد الصرف - هنا تحدث المحاسبة!
        with atomic_transaction("cheque_clear"):
            process_cheque_clear(cheque, clearance_date, clearance_exchange_rate)

        # رسالة مفصلة عند وجود فرق عملة
        if cheque.currency_gain_loss and abs(cheque.currency_gain_loss) > Decimal(
            "0.01"
        ):
            if cheque.currency_gain_loss > 0:
                gain_loss_msg = f" - تم تحقيق ربح من فرق العملة: +{cheque.currency_gain_loss:.2f} {default_currency}"
            else:
                gain_loss_msg = f" - خسارة من فرق العملة: {cheque.currency_gain_loss:.2f} {default_currency}"
        else:
            gain_loss_msg = ""

        with atomic_transaction("cheque_clear_log"):
            LoggingCore.log_audit(
                "cheque_clear",
                "cheques",
                record_id,
                {
                    "message": f"تأكيد صرف شيك رقم {cheque.cheque_bank_number} من البنك - تم تحديث الحسابات{gain_loss_msg}"
                },
            )

        flash(
            f"✅ تم تأكيد صرف الشيك {cheque.cheque_bank_number} - تم تحديث الحسابات المالية{gain_loss_msg}",
            "success",
        )

    except ValueError as e:
        current_app.logger.warning(f"ValueError in cheque operation: {e}")
        flash(f"❌ خطأ: {str(e)}", "error")
    except Exception as e:
        flash(f"❌ خطأ: {str(e)}\n💡 تحقق من البيانات وحاول مرة أخرى.", "danger")

    return redirect(url_for("cheques.view", id=record_id))


@cheques_bp.route("/<int:id>/bounce", methods=["POST"])
@login_required
@permission_required("manage_payments")
def bounce_cheque(**kwargs):
    """رفض الشيك من البنك - إرجاع الدين"""
    record_id = kwargs.pop("id")
    cheque = _get_cheque_or_404(record_id)
    if not _ensure_cheque_scope(cheque):
        return render_template("errors/403.html"), 403

    try:
        reason = request.form.get("bounce_reason", "غير محدد")
        details = request.form.get("bounce_details", "")
        full_reason = f"{reason}. {details}" if details else reason

        # رفض الشيك - إرجاع الدين
        with atomic_transaction("cheque_bounce"):
            process_cheque_bounce(cheque, full_reason)
            LoggingCore.log_audit(
                "cheque_bounce",
                "cheques",
                record_id,
                {"message": f"رفض شيك رقم {cheque.cheque_bank_number}: {full_reason}"},
            )

        flash(
            f"❌ تم رفض الشيك {cheque.cheque_bank_number} - تم إرجاع الدين للزبون",
            "warning",
        )

    except ValueError as e:
        current_app.logger.warning(f"ValueError in cheque operation: {e}")
        flash(f"❌ خطأ: {str(e)}", "error")
    except Exception as e:
        flash(f"❌ خطأ: {str(e)}\n💡 تحقق من البيانات وحاول مرة أخرى.", "danger")

    return redirect(url_for("cheques.view", id=record_id))


@cheques_bp.route("/<int:id>/cancel", methods=["POST"])
@login_required
@admin_required
def cancel(**kwargs):
    """إلغاء الشيك"""
    record_id = kwargs.pop("id")
    cheque = _get_cheque_or_404(record_id)
    if not _ensure_cheque_scope(cheque):
        return render_template("errors/403.html"), 403

    if cheque.status == "cleared":
        flash(
            "⚠️ لا يمكن إلغاء شيك تم صرفه.\n💡 الشيك تم صرفه بالفعل. لا يمكن التراجع عنه.",
            "danger",
        )
        return redirect(url_for("cheques.view", id=record_id))

    try:
        reason = request.form.get("cancel_reason")

        with atomic_transaction("cheque_cancel"):
            process_cheque_cancel(cheque, reason)
            LoggingCore.log_audit("cancel", "cheques", record_id)

        flash(f"✅ تم إلغاء الشيك {cheque.cheque_bank_number}", "success")

    except Exception as e:
        flash(f"❌ خطأ: {str(e)}\n💡 تحقق من البيانات وحاول مرة أخرى.", "danger")

    return redirect(url_for("cheques.view", id=record_id))


@cheques_bp.route("/<int:id>/delete", methods=["POST"])
@login_required
@admin_required
def delete(**kwargs):
    """حذف (أرشفة) الشيك"""
    record_id = kwargs.pop("id")
    cheque = _get_cheque_or_404(record_id)
    if not _ensure_cheque_scope(cheque):
        return render_template("errors/403.html"), 403

    # التحقق من الارتباطات
    has_links = False

    # 1. حالة الشيك (إذا لم يكن معلقاً، فهو جزء من التاريخ)
    if cheque.status in [
        "cleared",
        "deposited",
        "bounced",
        "cancelled",
        "under_collection",
    ]:
        has_links = True

    # 2. ارتباطات بكيانات أخرى
    if (
        cheque.receipt_id
        or cheque.payment_id
        or cheque.sale_id
        or cheque.purchase_id
        or cheque.expense_id
    ):
        has_links = True

    try:
        if has_links:
            # أرشفة (Soft Delete)
            reason = request.form.get("delete_reason", "أرشفة بسبب وجود ارتباطات")

            # عكس القيد المحاسبي إذا كان نشطاً (يتم داخل دالة archive)
            with atomic_transaction("cheque_archive"):
                cheque.archive(reason)
                LoggingCore.log_audit("archive", "cheques", record_id)
            flash(
                f"✅ تم أرشفة الشيك {cheque.cheque_bank_number} (لوجود ارتباطات)",
                "warning",
            )

        else:
            with atomic_transaction("cheque_delete_hard"):
                # حذف القيود المحاسبية المرتبطة
                from models import GLJournalEntry

                ref_types = [
                    "cheque_receive",
                    "cheque_issue",
                    "cheque_cancel",
                    "cheque_clear",
                    "cheque_bounce",
                    "Cheque",
                ]
                gl_query = GLJournalEntry.query.filter(
                    GLJournalEntry.reference_type.in_(ref_types),
                    GLJournalEntry.reference_id == cheque.id,
                    GLJournalEntry.tenant_id == cheque.tenant_id,
                )
                gl_query.delete(synchronize_session=False)

                # حذف الشيك
                db.session.delete(cheque)
                LoggingCore.log_audit("delete", "cheques", record_id)
            flash(f"✅ تم حذف الشيك {cheque.cheque_bank_number} نهائياً", "success")

        return redirect(url_for("cheques.index"))

    except Exception as e:
        flash(f"❌ خطأ: {str(e)}\n💡 تحقق من البيانات وحاول مرة أخرى.", "danger")
        return redirect(url_for("cheques.view", id=record_id))


@cheques_bp.route("/<int:id>/restore", methods=["POST"])
@login_required
@admin_required
def restore(**kwargs):
    """استعادة شيك من الأرشيف"""
    record_id = kwargs.pop("id")
    cheque = _get_cheque_or_404(record_id)
    if not _ensure_cheque_scope(cheque):
        return render_template("errors/403.html"), 403

    try:
        with atomic_transaction("cheque_restore"):
            cheque.restore()
            LoggingCore.log_audit("restore", "cheques", record_id)

        flash(f"✅ تم استعادة الشيك {cheque.cheque_bank_number}", "success")

    except Exception as e:
        flash(f"❌ خطأ: {str(e)}\n💡 تحقق من البيانات وحاول مرة أخرى.", "danger")

    return redirect(url_for("cheques.view", id=record_id))


@cheques_bp.route("/alerts")
@login_required
@permission_required("manage_payments")
def alerts():
    """تنبيهات الشيكات"""
    tid = get_active_tenant_id(current_user)
    scoped_branch_id = branch_scope_id()
    Cheque.update_all_statuses(tenant_id=tid, branch_id=scoped_branch_id)

    due_soon = Cheque.get_due_soon_cheques(tenant_id=tid, branch_id=scoped_branch_id)
    overdue = Cheque.get_overdue_cheques(tenant_id=tid, branch_id=scoped_branch_id)
    bounced = _scoped_cheques_query().filter_by(status="bounced")
    bounced = bounced.all()

    stats = Cheque.get_statistics(tenant_id=tid, branch_id=scoped_branch_id)

    return render_template(
        "cheques/alerts.html",
        due_soon=due_soon,
        overdue=overdue,
        bounced=bounced,
        stats=stats,
        show_branch_columns=should_show_all_branch_columns(current_user),
    )


@cheques_bp.route("/archived")
@login_required
@admin_required
def archived():
    """الشيكات المؤرشفة"""
    page = request.args.get("page", 1, type=int)

    query = _scoped_cheques_query().filter_by(is_active=False)

    pagination = query.order_by(Cheque.archived_at.desc()).paginate(
        page=page, per_page=25, error_out=False
    )

    return render_template(
        "cheques/archived.html", cheques=pagination.items, pagination=pagination
    )


@cheques_bp.route("/api/stats")
@login_required
@permission_required("manage_payments")
def api_stats():
    """API للإحصائيات"""
    tid = get_active_tenant_id(current_user)
    scoped_branch_id = branch_scope_id()
    Cheque.update_all_statuses(tenant_id=tid, branch_id=scoped_branch_id)
    stats = Cheque.get_statistics(tenant_id=tid, branch_id=scoped_branch_id)
    return jsonify(stats)


@cheques_bp.route("/api/alerts")
@login_required
@permission_required("manage_payments")
def api_alerts():
    """API للتنبيهات"""
    tid = get_active_tenant_id(current_user)
    scoped_branch_id = branch_scope_id()
    Cheque.update_all_statuses(tenant_id=tid, branch_id=scoped_branch_id)

    due_soon = Cheque.get_due_soon_cheques(tenant_id=tid, branch_id=scoped_branch_id)
    overdue = Cheque.get_overdue_cheques(tenant_id=tid, branch_id=scoped_branch_id)

    return jsonify(
        {
            "due_soon": len(due_soon),
            "overdue": len(overdue),
            "cheques_due_soon": [c.to_dict() for c in due_soon[:5]],
            "cheques_overdue": [c.to_dict() for c in overdue[:5]],
        }
    )
