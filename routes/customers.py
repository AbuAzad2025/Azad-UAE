from datetime import datetime
from decimal import Decimal
from typing import cast

from flask import (
    Blueprint,
    current_app,
    flash,
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
from services.customer_service import CustomerService
from services.customer_statement_service import CustomerStatementService
from services.logging_core import LoggingCore
from services.payment_service import PaymentService
from utils.api_response import error_response, success_response
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
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is None:
        return True
    return CustomerService.customer_id_in_branch_scope(customer_id, scoped_branch_id)


def _get_customer_balance(customer_id):
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is None:
        customer = tenant_get_or_404(Customer, customer_id)
        return PaymentService.get_customer_balance_aed(customer)
    return PaymentService.get_customer_balance_scoped(customer_id, branch_id=scoped_branch_id)


def _get_unpaid_sales(customer_id):
    return CustomerService.get_unpaid_sales(customer_id, branch_id=branch_scope_id())


def _attach_customer_branch_labels(customers):
    """Annotate customers with branch labels aggregated from related transactions."""
    CustomerService.attach_branch_labels(customers)


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
        balance_map = CustomerService.branch_balance_map(customers, scoped_branch)

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
    sales = CustomerService.recent_sales(record_id, tid, branch_id=branch_scope_id())

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
            sales_count, payments_count, receipts_count = CustomerService.relation_counts(
                record_id,
                tid,
                branch_id=branch_scope_id(),
            )

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
                customer = CustomerService.get_tenant_customer(record_id, tid)
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

    tid = get_active_tenant_id(current_user)

    opening_balance = 0.0
    if date_from:
        opening_balance = CustomerService.statement_opening_balance(record_id, tid, date_from)

    records = CustomerService.statement_records(
        record_id,
        tid,
        date_from,
        date_to,
        branch_id=branch_scope_id(),
    )

    transactions = []
    for s in records["sales"]:
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
    for p in records["payments"]:
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
    for r in records["receipts"]:
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
    for ret in records["returns"]:
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
        tenant_id=cast(int, get_active_tenant_id(current_user)),
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

    return success_response(data=results)


@customers_bp.route("/<int:id>/balance")
@login_required
@permission_required("manage_payments")
def customer_balance(**kwargs):
    """رصيد العميل + فواتير غير المدفوعة - API موحد (مصدر واحد مع payments)."""
    record_id = kwargs.pop("id")
    tenant_get_or_404(Customer, record_id)
    if not _customer_in_scope(record_id):
        return error_response(message="forbidden", status_code=403)
    try:
        default_currency = resolve_default_currency()
    except Exception:
        default_currency = get_system_default_currency()
    return success_response(
        data={
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

    sales = CustomerService.confirmed_sales(record_id, branch_id=branch_scope_id())

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

    return success_response(data={"sales": sales_data})
