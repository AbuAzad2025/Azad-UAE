from datetime import datetime
from decimal import Decimal

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_babel import gettext
from flask_login import current_user, login_required
from sqlalchemy import select

from extensions import db, limiter
from models import Customer, Sale
from services.customer_statement_service import CustomerStatementService
from services.logging_core import LoggingCore
from services.payment_service import PaymentService
from utils.branching import should_show_all_branch_columns
from utils.currency_utils import get_system_default_currency, resolve_default_currency
from utils.db_safety import atomic_transaction
from utils.decorators import branch_scope_id, permission_required
from utils.tenanting import get_active_tenant_id, tenant_get_or_404, tenant_query

customers_bp = Blueprint("customers", __name__, url_prefix="/customers")


def _scoped_customer_query():
    from models import Payment
    from models.receipt import Receipt

    query = tenant_query(Customer)
    scoped_branch_id = branch_scope_id()
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
    customer_ids = sale_ids.union(payment_ids, receipt_ids)
    return query.filter(Customer.id.in_(customer_ids))


def _customer_in_scope(customer_id):
    if branch_scope_id() is None:
        return True
    return db.session.query(_scoped_customer_query().filter(Customer.id == customer_id).exists()).scalar()


def _get_customer_balance(customer_id):
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is None:
        customer = tenant_get_or_404(Customer, customer_id)
        return PaymentService.get_customer_balance_aed(customer)
    return PaymentService.get_customer_balance_scoped(customer_id, branch_id=scoped_branch_id)


def _get_unpaid_sales(customer_id):
    query = Sale.query.filter(
        Sale.customer_id == customer_id,
        Sale.status == "confirmed",
        Sale.balance_due > 0,
    )
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None:
        query = query.filter(Sale.branch_id == scoped_branch_id)
    return query.order_by(Sale.sale_date.asc()).all()


def _attach_customer_branch_labels(customers):
    """Annotate customers with branch labels aggregated from related transactions."""
    if not customers:
        return

    from models import Branch, Payment
    from models.receipt import Receipt

    customer_ids = [c.id for c in customers]
    branch_map = {cid: set() for cid in customer_ids}

    sale_rows = (
        db.session.query(Sale.customer_id, Sale.branch_id)
        .filter(
            Sale.customer_id.in_(customer_ids),
            Sale.branch_id.isnot(None),
        )
        .all()
    )
    payment_rows = (
        db.session.query(Payment.customer_id, Payment.branch_id)
        .filter(
            Payment.customer_id.in_(customer_ids),
            Payment.branch_id.isnot(None),
        )
        .all()
    )
    receipt_rows = (
        db.session.query(Receipt.customer_id, Receipt.branch_id)
        .filter(
            Receipt.customer_id.in_(customer_ids),
            Receipt.branch_id.isnot(None),
        )
        .all()
    )

    branch_ids = set()
    for cid, bid in sale_rows + payment_rows + receipt_rows:
        if cid in branch_map and bid:
            branch_map[cid].add(bid)
            branch_ids.add(bid)

    branches = Branch.query.filter(Branch.id.in_(branch_ids)).all() if branch_ids else []
    branch_labels = {b.id: (f"{b.name} ({b.code})" if getattr(b, "code", None) else b.name) for b in branches}

    for customer in customers:
        labels = [branch_labels.get(bid, str(bid)) for bid in sorted(branch_map.get(customer.id, set()))]
        customer.branch_labels = labels


@customers_bp.route("/")
@login_required
@permission_required("manage_customers")
def index():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    search = request.args.get("search", "", type=str)
    customer_type = request.args.get("type", "", type=str)

    query = _scoped_customer_query()

    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            db.or_(
                Customer.name.ilike(search_filter),
                Customer.phone.ilike(search_filter),
                Customer.email.ilike(search_filter),
            )
        )

    if customer_type:
        query = query.filter_by(customer_type=customer_type)

    query = query.filter_by(is_active=True)

    pagination = query.order_by(Customer.name).paginate(page=page, per_page=per_page, error_out=False)

    show_branch_columns = should_show_all_branch_columns(current_user)
    if show_branch_columns:
        _attach_customer_branch_labels(pagination.items)

    return render_template(
        "customers/index.html",
        customers=pagination.items,
        pagination=pagination,
        show_branch_columns=show_branch_columns,
    )


@customers_bp.route("/export")
@login_required
@permission_required("manage_customers")
def export():
    from models import Payment
    from models.receipt import Receipt
    from services.export_service import ExportService

    fmt = (request.args.get("format") or "csv").strip().lower()
    search = request.args.get("search", "", type=str)
    customer_type = request.args.get("type", "", type=str)

    tenant_id = get_active_tenant_id(current_user)
    query = _scoped_customer_query()
    if tenant_id is not None:
        query = query.filter(Customer.tenant_id == tenant_id)
    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            db.or_(
                Customer.name.ilike(search_filter),
                Customer.phone.ilike(search_filter),
                Customer.email.ilike(search_filter),
            )
        )
    if customer_type:
        query = query.filter_by(customer_type=customer_type)
    query = query.filter_by(is_active=True)
    customers = query.order_by(Customer.name).all()

    scoped_branch = branch_scope_id()
    balance_map = {}
    if scoped_branch is not None and customers:
        customer_ids = [c.id for c in customers]
        sales_rows = (
            db.session.query(
                Sale.customer_id,
                db.func.coalesce(db.func.sum(Sale.amount_aed), 0).label("sales_total"),
            )
            .filter(
                Sale.status == "confirmed",
                Sale.branch_id == scoped_branch,
                Sale.customer_id.in_(customer_ids),
            )
            .group_by(Sale.customer_id)
            .all()
        )
        receipts_rows = (
            db.session.query(
                Receipt.customer_id,
                db.func.coalesce(db.func.sum(Receipt.amount_aed), 0).label("receipts_total"),
            )
            .filter(
                Receipt.branch_id == scoped_branch,
                Receipt.customer_id.in_(customer_ids),
            )
            .group_by(Receipt.customer_id)
            .all()
        )
        outgoing_rows = (
            db.session.query(
                Payment.customer_id,
                db.func.coalesce(db.func.sum(Payment.amount_aed), 0).label("outgoing_total"),
            )
            .filter(
                Payment.direction == "outgoing",
                Payment.branch_id == scoped_branch,
                Payment.customer_id.in_(customer_ids),
            )
            .group_by(Payment.customer_id)
            .all()
        )

        sales_map = {cid: Decimal(str(total or 0)) for cid, total in sales_rows}
        receipts_map = {cid: Decimal(str(total or 0)) for cid, total in receipts_rows}
        outgoing_map = {cid: Decimal(str(total or 0)) for cid, total in outgoing_rows}

        for cid in customer_ids:
            balance_map[cid] = (
                receipts_map.get(cid, Decimal("0"))
                - sales_map.get(cid, Decimal("0"))
                - outgoing_map.get(cid, Decimal("0"))
            )

    headers = [
        gettext("الاسم"),
        gettext("الاسم (ع)"),
        gettext("النوع"),
        gettext("الهاتف"),
        gettext("الإيميل"),
        gettext("العملة المفضلة"),
        gettext("الرصيد"),
        gettext("تاريخ الإنشاء"),
    ]

    data = []
    for c in customers:
        bal = balance_map.get(c.id, Decimal("0")) if scoped_branch is not None else Decimal(str(c.balance or 0))
        data.append(
            [
                c.name,
                c.name_ar or "",
                c.customer_type or "",
                c.phone or "",
                c.email or "",
                c.preferred_currency or "",
                float(bal),
                c.created_at.strftime("%Y-%m-%d") if c.created_at else "",
            ]
        )

    base_name = f"customers_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if fmt == "xlsx":
        output = ExportService.export_to_xlsx(data, headers, filename=f"{base_name}.xlsx", sheet_name="Customers")
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"{base_name}.xlsx",
        )

    output = ExportService.export_to_csv(data, headers, filename=f"{base_name}.csv")
    return send_file(
        output,
        mimetype="text/csv; charset=utf-8",
        as_attachment=True,
        download_name=f"{base_name}.csv",
    )


@customers_bp.route("/create", methods=["GET", "POST"])
@login_required
@permission_required("manage_customers")
@limiter.limit("10 per minute", methods=["POST"])
def create():
    from forms.customer import CustomerForm

    form = CustomerForm()

    if form.validate_on_submit():
        try:
            from utils.field_validators import (
                normalize_phone_optional,
                validate_currency_code,
            )

            try:
                default_currency = resolve_default_currency()
            except Exception:
                default_currency = get_system_default_currency()

            # Check tenant customer limit
            from utils.tenant_limits import TenantLimitError, check_customers_limit

            try:
                check_customers_limit()
            except TenantLimitError as e:
                flash(str(e), "warning")
                return redirect(url_for("customers.create"))

            from services.customer_service import CustomerService

            customer = CustomerService.create_customer(
                name=form.name.data,
                name_ar=form.name_ar.data,
                customer_type=form.customer_type.data,
                phone=normalize_phone_optional(form.phone.data),
                email=form.email.data,
                address=form.address.data,
                tax_number=form.tax_number.data,
                preferred_currency=validate_currency_code(form.preferred_currency.data or default_currency),
                is_active=bool(form.is_active.data),
                notes=form.notes.data,
                tenant_id=get_active_tenant_id(current_user),
            )

            with atomic_transaction("customer_create"):
                db.session.flush()
                LoggingCore.log_audit("create", "customers", customer.id)

            flash(gettext("✅ تم إضافة الزبون بنجاح!"), "success")
            return redirect(url_for("customers.index"))

        except Exception as e:
            from utils.error_messages import ErrorMessages

            current_app.logger.error(f"Error in customer operation: {e}")
            flash(ErrorMessages.database_error(), "danger")

    return render_template("customers/create.html", form=form)


@customers_bp.route("/<int:id>")
@login_required
@permission_required("manage_customers")
def view(**kwargs):
    record_id = kwargs.pop("id")
    customer = tenant_get_or_404(Customer, record_id)
    if not _customer_in_scope(record_id):
        return render_template("errors/403.html"), 403

    tid = get_active_tenant_id(current_user)
    sales = Sale.query.filter_by(customer_id=record_id, tenant_id=tid)
    if branch_scope_id() is not None:
        sales = sales.filter(Sale.branch_id == branch_scope_id())
    sales = sales.order_by(Sale.sale_date.desc()).limit(20).all()

    balance = _get_customer_balance(record_id)

    unpaid_sales = _get_unpaid_sales(record_id)

    return render_template(
        "customers/view.html",
        customer=customer,
        sales=sales,
        balance=balance,
        unpaid_sales=unpaid_sales,
    )


@customers_bp.route("/<int:id>/edit", methods=["GET", "POST"])
@login_required
@permission_required("manage_customers")
def edit(**kwargs):
    record_id = kwargs.pop("id")
    customer = tenant_get_or_404(Customer, record_id)
    if not _customer_in_scope(record_id):
        return render_template("errors/403.html"), 403

    if request.method == "POST":
        try:
            with atomic_transaction("customer_update"):
                customer.name = request.form.get("name")
                customer.name_ar = request.form.get("name_ar")
                customer.customer_type = request.form.get("customer_type")
                from utils.field_validators import (
                    normalize_phone_optional,
                    validate_currency_code,
                )

                try:
                    default_currency = resolve_default_currency()
                except Exception:
                    default_currency = get_system_default_currency()

                customer.phone = normalize_phone_optional(request.form.get("phone"))
                customer.email = request.form.get("email")
                customer.address = request.form.get("address")
                customer.tax_number = request.form.get("tax_number")
                customer.preferred_currency = validate_currency_code(
                    request.form.get("preferred_currency") or request.form.get("default_currency") or default_currency
                )
                is_active_raw = request.form.get("is_active", "1")
                customer.is_active = str(is_active_raw) in ("1", "true", "on", "True")
                customer.notes = request.form.get("notes")

                LoggingCore.log_audit("update", "customers", customer.id)

            flash(gettext("✅ تم تحديث بيانات الزبون بنجاح!"), "success")
            return redirect(url_for("customers.view", id=customer.id))

        except Exception as e:
            from utils.error_messages import ErrorMessages

            current_app.logger.error(f"Error in customer operation: {e}")
            flash(ErrorMessages.database_error(), "danger")

    return render_template("customers/edit.html", customer=customer)


@customers_bp.route("/<int:id>/delete", methods=["POST"])
@login_required
@permission_required("manage_customers")
def delete(**kwargs):
    record_id = kwargs.pop("id")
    customer = tenant_get_or_404(Customer, record_id)
    if not _customer_in_scope(record_id):
        return render_template("errors/403.html"), 403

    tid = get_active_tenant_id(current_user)
    try:
        with atomic_transaction("customer_delete"):
            sales_query = Sale.query.filter_by(customer_id=record_id, tenant_id=tid)
            from models import Payment
            from models.receipt import Receipt

            payments_query = Payment.query.filter_by(customer_id=record_id, tenant_id=tid)
            receipts_query = Receipt.query.filter_by(customer_id=record_id, tenant_id=tid)
            if branch_scope_id() is not None:
                sales_query = sales_query.filter(Sale.branch_id == branch_scope_id())
                payments_query = payments_query.filter(Payment.branch_id == branch_scope_id())
                receipts_query = receipts_query.filter(Receipt.branch_id == branch_scope_id())
            sales_count = sales_query.count()
            payments_count = payments_query.count()
            receipts_count = receipts_query.count()

            has_relations = sales_count > 0 or payments_count > 0 or receipts_count > 0
            if has_relations:
                customer.is_active = False
            else:
                db.session.delete(customer)
            LoggingCore.log_audit("delete", "customers", record_id)

        if has_relations:
            flash(
                gettext(
                    f'⚠️ تم إلغاء تفعيل العميل "{customer.name}" بدلاً من حذفه لوجود ({sales_count} فاتورة، {payments_count} دفعة، {receipts_count} سند قبض) مرتبطة به.'
                ),
                "warning",
            )
        else:
            flash(gettext(f'✅ تم حذف العميل "{customer.name}" نهائياً!'), "success")

    except Exception as e:
        current_app.logger.error(f"Error deleting customer {record_id}: {e}")
        try:
            with atomic_transaction("customer_soft_delete"):
                customer = Customer.query.filter_by(id=record_id, tenant_id=tid).first()
                if customer:
                    customer.is_active = False
                    db.session.add(customer)
                    flash(
                        gettext(
                            f'⚠️ تعذر الحذف النهائي للعميل "{customer.name}" بسبب ارتباطات في قاعدة البيانات. تم إلغاء تفعيله بدلاً من ذلك.'
                        ),
                        "warning",
                    )
        except Exception as inner_e:
            current_app.logger.error(f"Error falling back to soft delete for customer {record_id}: {inner_e}")
            from utils.error_messages import ErrorMessages

            flash(ErrorMessages.delete_failed(gettext("العميل")), "danger")

    return redirect(url_for("customers.index"))


@customers_bp.route("/<int:id>/statement/print")
@login_required
@permission_required("manage_customers")
def print_statement(**kwargs):
    """طباعة كشف حساب العميل"""
    record_id = kwargs.pop("id")
    customer = tenant_get_or_404(Customer, record_id)
    if not _customer_in_scope(record_id):
        return render_template("errors/403.html"), 403

    date_from = request.args.get("date_from", type=str)
    date_to = request.args.get("date_to", type=str)

    from sqlalchemy import func

    from models import Payment, ProductReturn
    from models.receipt import Receipt

    tid = get_active_tenant_id(current_user)
    sales_q = Sale.query.filter_by(customer_id=record_id, status="confirmed", tenant_id=tid)
    payments_q = Payment.query.filter_by(customer_id=record_id, tenant_id=tid)
    receipts_q = Receipt.query.filter_by(customer_id=record_id, tenant_id=tid)
    returns_q = ProductReturn.query.filter_by(customer_id=record_id, status="approved", tenant_id=tid)
    if branch_scope_id() is not None:
        sales_q = sales_q.filter(Sale.branch_id == branch_scope_id())
        payments_q = payments_q.filter(Payment.branch_id == branch_scope_id())
        receipts_q = receipts_q.filter(Receipt.branch_id == branch_scope_id())
        returns_q = returns_q.filter(ProductReturn.branch_id == branch_scope_id())

    opening_balance = 0.0
    if date_from:
        pre_sales = float(
            Sale.query.filter(
                Sale.customer_id == record_id,
                Sale.status == "confirmed",
                Sale.tenant_id == tid,
                func.date(Sale.sale_date) < date_from,
            )
            .with_entities(func.coalesce(func.sum(Sale.amount_aed), 0))
            .scalar()
            or 0
        )
        pre_pay = sum(
            (float(p.amount_aed or 0) if p.direction == "incoming" else -float(p.amount_aed or 0))
            for p in Payment.query.filter(
                Payment.customer_id == record_id, Payment.tenant_id == tid, func.date(Payment.payment_date) < date_from
            ).all()
            if p.payment_confirmed or (p.payment_method == "cheque" and not p.rejection_reason)
        )
        pre_receipt = sum(
            float(r.amount_aed or 0)
            for r in Receipt.query.filter(
                Receipt.customer_id == record_id, Receipt.tenant_id == tid, func.date(Receipt.receipt_date) < date_from
            ).all()
            if r.payment_confirmed or (r.payment_method == "cheque" and not r.rejection_reason)
        )
        pre_return = float(
            ProductReturn.query.filter(
                ProductReturn.customer_id == record_id,
                ProductReturn.status == "approved",
                ProductReturn.tenant_id == tid,
                func.date(ProductReturn.return_date) < date_from,
            )
            .with_entities(func.coalesce(func.sum(ProductReturn.amount_aed), 0))
            .scalar()
            or 0
        )
        opening_balance = (pre_pay + pre_receipt + pre_return) - pre_sales
        sales_q = sales_q.filter(func.date(Sale.sale_date) >= date_from)
        payments_q = payments_q.filter(func.date(Payment.payment_date) >= date_from)
        receipts_q = receipts_q.filter(func.date(Receipt.receipt_date) >= date_from)
        returns_q = returns_q.filter(func.date(ProductReturn.return_date) >= date_from)
    if date_to:
        sales_q = sales_q.filter(func.date(Sale.sale_date) <= date_to)
        payments_q = payments_q.filter(func.date(Payment.payment_date) <= date_to)
        receipts_q = receipts_q.filter(func.date(Receipt.receipt_date) <= date_to)
        returns_q = returns_q.filter(func.date(ProductReturn.return_date) <= date_to)

    transactions = []
    for s in sales_q.order_by(Sale.sale_date).all():
        transactions.append(
            {
                "date": s.sale_date,
                "type": "sale",
                "reference": s.sale_number,
                "debit": float(s.amount_aed or 0),
                "credit": 0,
                "description": gettext("فاتورة بيع"),
            }
        )
    for p in payments_q.order_by(Payment.payment_date).all():
        amt = float(p.amount_aed or 0)
        if p.direction == "incoming":
            transactions.append(
                {
                    "date": p.payment_date,
                    "type": "payment",
                    "reference": p.payment_number or p.reference_number or "",
                    "debit": 0,
                    "credit": amt,
                    "description": gettext("دفعة"),
                }
            )
        else:
            transactions.append(
                {
                    "date": p.payment_date,
                    "type": "payment",
                    "reference": p.payment_number or p.reference_number or "",
                    "debit": amt,
                    "credit": 0,
                    "description": gettext("استرداد"),
                }
            )
    for r in receipts_q.order_by(Receipt.receipt_date).all():
        transactions.append(
            {
                "date": r.receipt_date,
                "type": "receipt",
                "reference": r.receipt_number,
                "debit": 0,
                "credit": float(r.amount_aed or 0),
                "description": gettext("سند قبض"),
            }
        )
    for ret in returns_q.order_by(ProductReturn.return_date).all():
        transactions.append(
            {
                "date": ret.return_date,
                "type": "return",
                "reference": ret.return_number,
                "debit": 0,
                "credit": float(ret.amount_aed or 0),
                "description": gettext("مرتجع مبيعات"),
            }
        )

    transactions.sort(key=lambda x: x["date"] or datetime.min)

    if date_from:
        transactions.insert(
            0,
            {
                "date": date_from,
                "type": "opening",
                "reference": "",
                "debit": 0,
                "credit": 0,
                "balance": opening_balance,
                "description": gettext("الرصيد الافتتاحي"),
            },
        )

    running = opening_balance if date_from else 0
    for t in transactions:
        if t["type"] != "opening":
            running += t["credit"] - t["debit"]
        t["balance"] = running

    from models.invoice_settings import InvoiceSettings
    from utils.tenant_branding import get_print_header_context

    tenant, settings, company = InvoiceSettings.company_print_context(tid)
    branding = get_print_header_context(tid)
    return render_template(
        "customers/statement_print.html",
        customer=customer,
        transactions=transactions,
        final_balance=running,
        filters={"date_from": date_from or "", "date_to": date_to or ""},
        settings=settings,
        company=company,
        print_branding=branding,
        print_tenant_id=tid,
        tenant=tenant,
    )


@customers_bp.route("/<int:id>/statement")
@login_required
@permission_required("manage_customers")
def statement(**kwargs):
    record_id = kwargs.pop("id")
    customer = tenant_get_or_404(Customer, record_id)
    if not _customer_in_scope(record_id):
        return render_template("errors/403.html"), 403

    try:
        default_currency = resolve_default_currency()
    except Exception:
        default_currency = get_system_default_currency()

    date_from = request.args.get("date_from", type=str)
    date_to = request.args.get("date_to", type=str)
    transaction_type = request.args.get("transaction_type", "all")

    context = CustomerStatementService.build_statement_context(
        record_id=record_id,
        date_from=date_from,
        date_to=date_to,
        transaction_type=transaction_type,
        default_currency=default_currency,
        tenant_id=get_active_tenant_id(current_user),
        branch_id=branch_scope_id(),
    )

    return render_template(
        "customers/statement.html",
        customer=customer,
        **context,
    )


@customers_bp.route("/api/search")
@login_required
@permission_required("manage_customers")
def api_search():
    query = request.args.get("q", "")
    request.args.get("page", 1, type=int)
    per_page = 20
    base_query = _scoped_customer_query().filter(Customer.is_active).order_by(Customer.name)

    if query and len(query) >= 1:
        customers = (
            base_query.filter(
                db.or_(
                    Customer.name.ilike(f"%{query}%"),
                    Customer.phone.ilike(f"%{query}%"),
                    Customer.email.ilike(f"%{query}%"),
                )
            )
            .order_by(Customer.name)
            .limit(per_page)
            .all()
        )
    else:
        customers = base_query.limit(per_page).all()

    results = [
        {
            "id": c.id,
            "name": c.name,
            "phone": c.phone or "",
            "text": f"{c.name} - {c.phone}" if c.phone else c.name,
            "customer_type": c.customer_type,
            "customer_classification": c.customer_classification,
            "balance": float(_get_customer_balance(c.id)),
        }
        for c in customers
    ]

    return jsonify(results)


@customers_bp.route("/<int:id>/balance")
@login_required
@permission_required("manage_payments")
def customer_balance(**kwargs):
    """رصيد العميل + فواتير غير المدفوعة - API موحد (مصدر واحد مع payments)."""
    record_id = kwargs.pop("id")
    tenant_get_or_404(Customer, record_id)
    if not _customer_in_scope(record_id):
        return jsonify({"error": "forbidden"}), 403
    try:
        default_currency = resolve_default_currency()
    except Exception:
        default_currency = get_system_default_currency()
    return jsonify(
        {
            "balance_aed": float(_get_customer_balance(record_id)),
            "balance": float(_get_customer_balance(record_id)),
            "currency": default_currency,
            "unpaid_sales": [
                {
                    "id": s.id,
                    "sale_number": s.sale_number,
                    "sale_date": (
                        s.sale_date.strftime("%Y-%m-%d") if getattr(s.sale_date, "strftime", None) else str(s.sale_date)
                    ),
                    "total_amount": float(s.total_amount),
                    "balance_due": float(s.balance_due),
                    "currency": s.currency or default_currency,
                }
                for s in _get_unpaid_sales(record_id)
            ],
        }
    )


@customers_bp.route("/<int:id>/sales")
@login_required
@permission_required("manage_customers")
def customer_sales(**kwargs):
    record_id = kwargs.pop("id")
    tenant_get_or_404(Customer, record_id)
    if not _customer_in_scope(record_id):
        return render_template("errors/403.html"), 403

    sales = Sale.query.filter_by(customer_id=record_id, status="confirmed")
    if branch_scope_id() is not None:
        sales = sales.filter(Sale.branch_id == branch_scope_id())
    sales = sales.order_by(Sale.sale_date.desc()).all()

    sales_data = []
    for sale in sales:
        balance = sale.amount_aed - sale.paid_amount_aed
        if balance > 0:
            sales_data.append(
                {
                    "id": sale.id,
                    "invoice_number": sale.sale_number or f"#{sale.id}",
                    "sale_date": sale.sale_date.strftime("%Y-%m-%d"),
                    "amount_aed": float(sale.amount_aed),
                    "paid_amount_aed": float(sale.paid_amount_aed),
                    "balance": float(balance),
                }
            )

    return jsonify({"sales": sales_data})
