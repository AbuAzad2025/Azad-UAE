"""
🏪 Suppliers Routes - مسارات الموردين
إدارة الموردين: عرض، إضافة، تعديل، تقارير
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
from sqlalchemy import select
from extensions import db, limiter
from models import Supplier, Purchase, Payment
from utils.decorators import permission_required, admin_required, branch_scope_id
from utils.branching import should_show_all_branch_columns
from services.logging_core import LoggingCore
from utils.currency_utils import resolve_default_currency, get_system_default_currency
from utils.tenanting import tenant_query, tenant_get_or_404, get_active_tenant_id
from sqlalchemy import func, desc
from utils.db_safety import atomic_transaction
from utils.structured_logging import log_mutation
from utils.error_messages import ErrorMessages

suppliers_bp = Blueprint("suppliers", __name__, url_prefix="/suppliers")


def _scoped_supplier_query():
    query = tenant_query(Supplier)
    scoped_branch_id = branch_scope_id()
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
    supplier_ids = purchase_ids.union(payment_ids)
    return query.filter(Supplier.id.in_(supplier_ids))


def _supplier_in_scope(supplier_id):
    if branch_scope_id() is None:
        return True
    return db.session.query(
        _scoped_supplier_query().filter(Supplier.id == supplier_id).exists()
    ).scalar()


def _supplier_scoped_totals(supplier_id):
    tid = get_active_tenant_id(current_user)
    scoped_branch_id = branch_scope_id()
    purchases_query = Purchase.query.filter_by(
        supplier_id=supplier_id, status="confirmed", tenant_id=tid
    )
    payments_query = Payment.query.filter_by(supplier_id=supplier_id, tenant_id=tid)
    if scoped_branch_id is not None:
        purchases_query = purchases_query.filter(Purchase.branch_id == scoped_branch_id)
        payments_query = payments_query.filter(Payment.branch_id == scoped_branch_id)

    purchases = purchases_query.all()
    total_purchases = sum((p.amount_aed or 0) for p in purchases)
    total_paid = sum(
        (p.amount_aed or 0)
        for p in payments_query.filter(Payment.direction == "outgoing").all()
    )
    return purchases, total_purchases, total_paid


def _attach_supplier_branch_labels(suppliers):
    """Annotate suppliers with branch labels aggregated from purchases/payments."""
    if not suppliers:
        return

    from models import Branch

    supplier_ids = [s.id for s in suppliers]
    branch_map = {sid: set() for sid in supplier_ids}

    purchase_rows = (
        db.session.query(Purchase.supplier_id, Purchase.branch_id)
        .filter(
            Purchase.supplier_id.in_(supplier_ids),
            Purchase.branch_id.isnot(None),
        )
        .all()
    )
    payment_rows = (
        db.session.query(Payment.supplier_id, Payment.branch_id)
        .filter(
            Payment.supplier_id.in_(supplier_ids),
            Payment.branch_id.isnot(None),
        )
        .all()
    )

    branch_ids = set()
    for sid, bid in purchase_rows + payment_rows:
        if sid in branch_map and bid:
            branch_map[sid].add(bid)
            branch_ids.add(bid)

    branches = (
        Branch.query.filter(Branch.id.in_(branch_ids)).all() if branch_ids else []
    )
    branch_labels = {
        b.id: (f"{b.name} ({b.code})" if getattr(b, "code", None) else b.name)
        for b in branches
    }

    for supplier in suppliers:
        labels = [
            branch_labels.get(bid, str(bid))
            for bid in sorted(branch_map.get(supplier.id, set()))
        ]
        supplier.branch_labels = labels


@suppliers_bp.route("/")
@login_required
@permission_required("manage_suppliers")
def index():
    """قائمة الموردين"""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    search = request.args.get("search", "", type=str)
    supplier_type = request.args.get("type", "", type=str)

    query = _scoped_supplier_query().filter_by(is_active=True)

    # البحث
    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            db.or_(
                Supplier.name.ilike(search_filter),
                Supplier.company_name.ilike(search_filter),
                Supplier.phone.ilike(search_filter),
                Supplier.email.ilike(search_filter),
            )
        )

    # الفلترة حسب النوع
    if supplier_type:
        query = query.filter_by(supplier_type=supplier_type)

    pagination = query.order_by(Supplier.name).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # إحصائيات
    scoped_stats_query = _scoped_supplier_query().filter_by(is_active=True)
    stats = {
        "total": scoped_stats_query.count(),
        "verified": scoped_stats_query.filter_by(is_verified=True).count(),
        "parts": scoped_stats_query.filter_by(supplier_type="parts").count(),
        "equipment": scoped_stats_query.filter_by(supplier_type="equipment").count(),
    }

    show_branch_columns = should_show_all_branch_columns(current_user)
    if show_branch_columns:
        _attach_supplier_branch_labels(pagination.items)

    return render_template(
        "suppliers/index.html",
        suppliers=pagination.items,
        pagination=pagination,
        stats=stats,
        show_branch_columns=show_branch_columns,
    )


@suppliers_bp.route("/create", methods=["GET", "POST"])
@login_required
@permission_required("manage_suppliers")
@limiter.limit("10 per minute", methods=["POST"])
def create():
    """إضافة مورد جديد"""
    if request.method == "POST":
        try:
            supplier_type_value = (request.form.get("supplier_type") or "").strip()
            if not supplier_type_value:
                flash("⚠️ يرجى اختيار نوع المورد.", "warning")
                return render_template("suppliers/create.html")

            rating_value = (request.form.get("rating") or "").strip()
            rating = None
            if rating_value:
                try:
                    rating = int(rating_value)
                except ValueError:
                    flash("⚠️ قيمة التقييم غير صحيحة.", "warning")
                    return render_template("suppliers/create.html")

            from utils.field_validators import (
                normalize_phone_optional,
                validate_currency_code,
            )

            try:
                default_currency = resolve_default_currency()
            except Exception:
                default_currency = get_system_default_currency()

            initial_balance = request.form.get("initial_balance", type=float, default=0)

            # Check tenant supplier limit
            from utils.tenant_limits import check_suppliers_limit, TenantLimitError

            try:
                check_suppliers_limit()
            except TenantLimitError as e:
                flash(str(e), "warning")
                return redirect(url_for("suppliers.create"))

            tid = get_active_tenant_id(current_user)
            supplier = Supplier(
                tenant_id=tid,
                name=request.form.get("name"),
                name_en=request.form.get("name_en"),
                company_name=request.form.get("company_name"),
                phone=normalize_phone_optional(request.form.get("phone")),
                phone2=normalize_phone_optional(
                    request.form.get("phone2"), field_label="phone2"
                ),
                email=request.form.get("email"),
                website=request.form.get("website"),
                address=request.form.get("address"),
                city=request.form.get("city"),
                country=request.form.get("country", "PS"),
                tax_number=request.form.get("tax_number"),
                commercial_registration=request.form.get("commercial_registration"),
                supplier_type=supplier_type_value,
                rating=rating if rating is not None else None,
                credit_limit=request.form.get("credit_limit", type=float, default=0),
                payment_terms_days=request.form.get(
                    "payment_terms_days", type=int, default=30
                ),
                preferred_currency=validate_currency_code(
                    request.form.get("preferred_currency", default_currency)
                ),
                total_purchases_aed=initial_balance,
                total_paid_aed=0,
                notes=request.form.get("notes"),
                tags=request.form.get("tags"),
                is_verified=request.form.get("is_verified") == "on",
                created_by=current_user.id,
            )

            with atomic_transaction("supplier_creation"):
                db.session.add(supplier)

                if initial_balance and initial_balance > 0:
                    from services.gl_posting import post_or_fail
                    from services.gl_service import GLService

                    GLService.ensure_core_accounts(tenant_id=tid)
                    post_or_fail(
                        lines=[
                            {
                                "account": "3130",
                                "concept_code": "OPENING_BALANCE_EQUITY",
                                "debit": initial_balance,
                                "credit": 0,
                                "description": f"رصيد افتتاحي للمورد {supplier.name}",
                            },
                            {
                                "account": "2110",
                                "concept_code": "ACCOUNTS_PAYABLE",
                                "debit": 0,
                                "credit": initial_balance,
                                "description": f"رصيد افتتاحي للمورد {supplier.name}",
                            },
                        ],
                        description=f"رصيد افتتاحي للمورد {supplier.name}",
                        reference_type="supplier_opening",
                        reference_id=supplier.id,
                        tenant_id=tid,
                    )

                LoggingCore.log_audit("create", "suppliers", supplier.id)

            log_mutation("create", "Supplier", supplier.id, {"name": supplier.name})
            flash("✅ تم إضافة المورد بنجاح!", "success")
            return redirect(url_for("suppliers.view", id=supplier.id))

        except Exception as e:
            current_app.logger.error(f"Error in supplier operation: {e}")
            flash(ErrorMessages.create_failed("supplier"), "danger")

    return render_template("suppliers/create.html")


@suppliers_bp.route("/<int:id>")
@login_required
@permission_required("manage_suppliers")
def view(id):  # noqa: A002
    """عرض تفاصيل المورد"""
    supplier = tenant_get_or_404(Supplier, id)
    if not _supplier_in_scope(id):
        return render_template("errors/403.html"), 403

    # آخر المشتريات
    recent_purchases_query = supplier.purchases.filter_by(status="confirmed")
    if branch_scope_id() is not None:
        recent_purchases_query = recent_purchases_query.filter(
            Purchase.branch_id == branch_scope_id()
        )
    recent_purchases = (
        recent_purchases_query.order_by(desc(Purchase.purchase_date)).limit(10).all()
    )
    _, total_amount, total_paid = _supplier_scoped_totals(id)

    # إحصائيات
    stats = {
        "total_purchases": recent_purchases_query.count(),
        "total_amount": float(total_amount or 0),
        "balance": float((total_amount or 0) - (total_paid or 0)),
        "avg_purchase": 0,
    }

    if stats["total_purchases"] > 0:
        stats["avg_purchase"] = stats["total_amount"] / stats["total_purchases"]

    return render_template(
        "suppliers/view.html",
        supplier=supplier,
        recent_purchases=recent_purchases,
        stats=stats,
    )


@suppliers_bp.route("/<int:id>/edit", methods=["GET", "POST"])
@login_required
@permission_required("manage_suppliers")
def edit(id):  # noqa: A002
    """تعديل المورد"""
    supplier = tenant_get_or_404(Supplier, id)
    if not _supplier_in_scope(id):
        return render_template("errors/403.html"), 403

    if request.method == "POST":
        try:
            supplier.name = request.form.get("name")
            supplier.name_en = request.form.get("name_en")
            supplier.company_name = request.form.get("company_name")
            from utils.field_validators import (
                normalize_phone_optional,
                validate_currency_code,
            )

            supplier.phone = normalize_phone_optional(request.form.get("phone"))
            supplier.phone2 = normalize_phone_optional(
                request.form.get("phone2"), field_label="phone2"
            )
            supplier.email = request.form.get("email")
            supplier.website = request.form.get("website")
            supplier.address = request.form.get("address")
            supplier.city = request.form.get("city")
            supplier.country = request.form.get("country")
            supplier.tax_number = request.form.get("tax_number")
            supplier.commercial_registration = request.form.get(
                "commercial_registration"
            )
            supplier_type_value = (request.form.get("supplier_type") or "").strip()
            supplier.supplier_type = supplier_type_value or None

            rating_value = (request.form.get("rating") or "").strip()
            supplier.rating = int(rating_value) if rating_value else None
            try:
                default_currency = resolve_default_currency()
            except Exception:
                default_currency = get_system_default_currency()
            supplier.credit_limit = request.form.get("credit_limit", type=float)
            supplier.payment_terms_days = request.form.get(
                "payment_terms_days", type=int
            )
            supplier.preferred_currency = validate_currency_code(
                request.form.get("preferred_currency")
                or supplier.preferred_currency
                or default_currency
            )
            supplier.notes = request.form.get("notes")
            supplier.tags = request.form.get("tags")
            supplier.is_verified = request.form.get("is_verified") == "on"

            with atomic_transaction("supplier_edit"):
                db.session.flush()

            LoggingCore.log_audit("update", "suppliers", supplier.id)

            flash("✅ تم تحديث المورد بنجاح!", "success")
            return redirect(url_for("suppliers.view", id=supplier.id))

        except Exception as e:
            current_app.logger.error(f"Error updating supplier {id}: {e}")
            flash(ErrorMessages.update_failed("supplier"), "danger")

    return render_template("suppliers/edit.html", supplier=supplier)


@suppliers_bp.route("/<int:id>/delete", methods=["POST"])
@login_required
@permission_required("manage_suppliers")
def delete(id):  # noqa: A002
    """حذف (إلغاء تفعيل) المورد"""
    supplier = tenant_get_or_404(Supplier, id)
    if not _supplier_in_scope(id):
        return render_template("errors/403.html"), 403

    try:
        # Check for related records preventing deletion
        tid = get_active_tenant_id(current_user)
        purchases_query = Purchase.query.filter_by(supplier_id=id, tenant_id=tid)
        payments_query = Payment.query.filter_by(supplier_id=id, tenant_id=tid)
        if branch_scope_id() is not None:
            purchases_query = purchases_query.filter(
                Purchase.branch_id == branch_scope_id()
            )
            payments_query = payments_query.filter(
                Payment.branch_id == branch_scope_id()
            )
        purchases_count = purchases_query.count()
        payments_count = payments_query.count()

        if purchases_count > 0 or payments_count > 0:
            supplier.is_active = False
            with atomic_transaction("supplier_soft_delete"):
                db.session.flush()
            flash(
                f'⚠️ تم إلغاء تفعيل المورد "{supplier.name}" بدلاً من حذفه لوجود ({purchases_count} فاتورة شراء، {payments_count} دفعة) مرتبطة به.',
                "warning",
            )
        else:
            db.session.delete(supplier)
            with atomic_transaction("supplier_hard_delete"):
                db.session.flush()
            flash(f'✅ تم حذف المورد "{supplier.name}" نهائياً!', "success")

        LoggingCore.log_audit("delete", "suppliers", supplier.id)

    except Exception as e:
        current_app.logger.error(f"Error deleting supplier {id}: {e}")
        try:
            supplier.is_active = False
            with atomic_transaction("supplier_delete_fallback"):
                db.session.flush()
            flash(
                f'⚠️ تعذر الحذف النهائي للمورد "{supplier.name}" بسبب ارتباطات في قاعدة البيانات. تم إلغاء تفعيله بدلاً من ذلك.',
                "warning",
            )
        except Exception as inner_e:
            current_app.logger.error(
                f"Error falling back to soft delete for supplier {id}: {inner_e}"
            )
            flash(ErrorMessages.delete_failed("supplier"), "danger")

    return redirect(url_for("suppliers.index"))


@suppliers_bp.route("/<int:id>/statement")
@login_required
@admin_required
def statement(id):  # noqa: A002
    """كشف حساب المورد مع الرصيد الجاري والتصفية حسب التاريخ"""
    from datetime import datetime, date as date_type

    supplier = tenant_get_or_404(Supplier, id)
    if not _supplier_in_scope(id):
        return render_template("errors/403.html"), 403

    date_from = request.args.get("date_from", type=str)
    date_to = request.args.get("date_to", type=str)

    tid = get_active_tenant_id(current_user)
    purchases_q = supplier.purchases.filter_by(status="confirmed", tenant_id=tid)
    # Include both outgoing payments (credit) and incoming refunds (debit) so
    # the statement balance matches the supplier's ledger balance.
    payments_q = Payment.query.filter_by(supplier_id=id, tenant_id=tid)
    if branch_scope_id() is not None:
        purchases_q = purchases_q.filter(Purchase.branch_id == branch_scope_id())
        payments_q = payments_q.filter(Payment.branch_id == branch_scope_id())
    if date_from:
        purchases_q = purchases_q.filter(func.date(Purchase.purchase_date) >= date_from)
        payments_q = payments_q.filter(func.date(Payment.payment_date) >= date_from)
    if date_to:
        purchases_q = purchases_q.filter(func.date(Purchase.purchase_date) <= date_to)
        payments_q = payments_q.filter(func.date(Payment.payment_date) <= date_to)

    purchases = purchases_q.order_by(Purchase.purchase_date.asc()).all()
    payments = payments_q.order_by(Payment.payment_date.asc()).all()

    transactions = []
    for p in purchases:
        transactions.append(
            {
                "date": p.purchase_date,
                "type": "purchase",
                "reference": p.purchase_number,
                "debit": float(p.base_amount or 0),
                "credit": 0,
                "balance": 0,
                "currency": p.currency or "AED",
                "exchange_rate": float(p.exchange_rate or 1),
                "description": "فاتورة شراء",
                "amount": float(p.total_amount or 0),
                "base_amount": float(p.base_amount or 0),
            }
        )
    for pm in payments:
        pm_amount = float(pm.amount_aed or 0)
        # A payment affects the balance when it is confirmed, or when it is a
        # still-pending cheque (issuing an outgoing cheque reduces AP
        # immediately). Bounced/cancelled cheques carry a rejection_reason and
        # have had their AP restored, so they have no effect.
        affects_balance = bool(pm.payment_confirmed) or (
            pm.payment_method == "cheque" and not pm.rejection_reason
        )
        # Outgoing payments reduce the balance owed (credit); incoming refunds
        # from the supplier offset AP and increase the balance owed (debit).
        is_refund = pm.direction == "incoming"
        transactions.append(
            {
                "date": pm.payment_date,
                "type": "refund" if is_refund else "payment",
                "reference": pm.payment_number or pm.reference_number or "",
                "debit": (pm_amount if affects_balance else 0) if is_refund else 0,
                "credit": 0 if is_refund else (pm_amount if affects_balance else 0),
                "balance": 0,
                "currency": pm.currency or "AED",
                "exchange_rate": float(pm.exchange_rate or 1),
                "description": (
                    f"استرداد من المورد - {pm.payment_method}"
                    if is_refund
                    else f"دفعة - {pm.payment_method}"
                ),
                "amount": float(pm.amount or 0),
                "base_amount": pm_amount,
                "payment_method": pm.payment_method,
                "payment_confirmed": pm.payment_confirmed,
                "payment_number": pm.payment_number,
                "payment_date": pm.payment_date,
                "cheque_number": pm.cheque_number,
                "cheque_bank": pm.bank_name,
                "cheque_due_date": pm.cheque_date,
                "notes": pm.notes or "",
            }
        )

    transactions.sort(key=lambda x: x["date"] or datetime.min)

    # الدلالة للموردين: موجب = مستحق للمورد، سالب = المورد مدين لنا
    # المشتريات (debit) تزيد المستحق، المدفوعات (credit) تنقصه
    if date_from:
        opening_balance = 0
        for t in transactions:
            if isinstance(t["date"], (datetime, date_type)):
                d = t["date"].date() if isinstance(t["date"], datetime) else t["date"]
                if d < datetime.strptime(date_from, "%Y-%m-%d").date():
                    opening_balance += t["debit"] - t["credit"]
        # Insert opening balance entry
        transactions.insert(
            0,
            {
                "date": date_from,
                "type": "opening",
                "reference": "",
                "debit": 0,
                "credit": 0,
                "balance": opening_balance,
                "currency": "AED",
                "exchange_rate": 1,
                "description": "الرصيد الافتتاحي",
            },
        )

    running_balance = 0
    for t in transactions:
        if t["type"] != "opening":
            running_balance += t["debit"] - t["credit"]
        t["balance"] = running_balance

    return render_template(
        "suppliers/statement.html",
        supplier=supplier,
        transactions=transactions,
        final_balance=running_balance,
        filters={"date_from": date_from or "", "date_to": date_to or ""},
    )


@suppliers_bp.route("/api/search")
@login_required
@permission_required("manage_suppliers")
def api_search():
    """API endpoint للبحث عن الموردين"""
    try:
        query = request.args.get("q", "")
        request.args.get("page", 1, type=int)
        per_page = 20

        # السماح بالبحث حتى بدون query (لعرض كل الموردين)
        if query and len(query) >= 1:
            suppliers = (
                _scoped_supplier_query()
                .filter(
                    Supplier.is_active,
                    db.or_(
                        Supplier.name.ilike(f"%{query}%"),
                        Supplier.phone.ilike(f"%{query}%"),
                        Supplier.email.ilike(f"%{query}%"),
                    ),
                )
                .order_by(Supplier.name)
                .limit(per_page)
                .all()
            )
        else:
            # عرض كل الموردين (مرتبين أبجدياً)
            suppliers = (
                _scoped_supplier_query()
                .filter_by(is_active=True)
                .order_by(Supplier.name)
                .limit(per_page)
                .all()
            )

        results = []
        for s in suppliers:
            _, total_purchases, total_paid = _supplier_scoped_totals(s.id)
            results.append(
                {
                    "id": s.id,
                    "name": s.name,
                    "phone": s.phone or "",
                    "text": f"{s.name} - {s.phone}" if s.phone else s.name,
                    "supplier_type": s.supplier_type,
                    "balance": float((total_purchases or 0) - (total_paid or 0)),
                }
            )

        return jsonify(results)
    except Exception as e:
        print(f"Error in supplier search API: {e}")
        return jsonify([])
