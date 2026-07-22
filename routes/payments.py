from flask_babel import gettext
from datetime import datetime, timezone

from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    request,
    current_app,
    jsonify,
    abort,
)
from flask_login import login_required, current_user
from sqlalchemy import select

from extensions import db
from models import Receipt, Customer, InvoiceSettings, Supplier, Payment
from services.payment_service import PaymentService
from services.cheque_service import process_cheque_issue
from services.currency_service import CurrencyService
from services.exchange_rate_service import ExchangeRateService
from services.gl_posting import post_or_fail
from utils.gl_reference_types import GLRef
from utils.decorators import permission_required
from utils.branching import should_show_all_branch_columns
from utils.currency_utils import resolve_default_currency, get_system_default_currency
from utils.tenanting import get_active_tenant_id
from services.logging_core import LoggingCore
from utils.number_to_arabic import number_to_arabic_words
from utils.qr_generator import generate_qr_data_url
from utils.tenanting import (
    tenant_query,
    tenant_get_or_404,
    tenant_get,
    assert_tenant_record,
)
from utils.db_safety import atomic_transaction

payments_bp = Blueprint("payments", __name__, url_prefix="/payments")


@payments_bp.route("/")
@login_required
@permission_required("manage_payments")
def index():
    return redirect(url_for("payments.receipts"))


def _in_scope_branch(entity_branch_id):
    from utils.decorators import branch_scope_id

    scoped_branch_id = branch_scope_id()
    return scoped_branch_id is None or entity_branch_id == scoped_branch_id


def _current_branch_id(default=None):
    from utils.decorators import branch_scope_id

    return branch_scope_id() or default


def _resolve_transaction_rate(currency, user_rate=None):
    from decimal import Decimal
    from utils.currency_utils import resolve_tenant_base_currency
    from utils.tenanting import get_active_tenant_id

    base_currency = resolve_tenant_base_currency(tenant_id=get_active_tenant_id(current_user))
    rate_info = ExchangeRateService.resolve_exchange_rate_for_transaction(
        currency,
        base_currency,
        user_rate=user_rate,
    )
    return Decimal(str(rate_info["rate"]))


def _ensure_customer_scope(customer_id):
    customer = _scoped_customers_query().filter(Customer.id == customer_id).first()
    if not customer:
        return None
    return customer


def _ensure_supplier_scope(supplier_id):
    supplier = _scoped_suppliers_query().filter(Supplier.id == supplier_id).first()
    if not supplier:
        return None
    return supplier


def _archived_item_branch_id(archived_record):
    data = getattr(archived_record, "data", None) or {}
    if isinstance(data, dict):
        return data.get("branch_id")
    return None


def _scoped_customer_balance(customer_id):
    branch_id = _current_branch_id()
    return float(PaymentService.get_customer_balance_scoped(customer_id, branch_id=branch_id))


def _scoped_customer_unpaid_sales(customer_id):
    from models import Sale

    query = tenant_query(Sale).filter(
        Sale.customer_id == customer_id,
        Sale.status == "confirmed",
        Sale.balance_due > 0,
    )
    branch_id = _current_branch_id()
    if branch_id is not None:
        query = query.filter(Sale.branch_id == branch_id)
    return query.order_by(Sale.sale_date.asc()).all()


def _scoped_customers_query():
    from models import Payment, Sale
    from utils.decorators import branch_scope_id

    scoped_branch_id = branch_scope_id()
    query = tenant_query(Customer).filter(Customer.is_active)
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


def _receipt_item_status(item):
    return "COMPLETED" if item.get("payment_confirmed") else "PENDING"


def _build_receipts_json_response(paginated_items, pagination):
    payload = []
    total_incoming = 0.0
    total_outgoing = 0.0
    for item in paginated_items:
        amount_value = float(item.get("amount") or 0)
        direction = item.get("direction")
        if direction == "incoming":
            total_incoming += amount_value
        elif direction == "outgoing":
            total_outgoing += amount_value
        payload.append(
            {
                "id": item.get("id"),
                "type": item.get("type"),
                "number": item.get("number"),
                "payment_date": (item.get("date").isoformat() if item.get("date") else None),
                "total_amount": amount_value,
                "currency": item.get("currency"),
                "method": item.get("payment_method"),
                "direction": direction,
                "status": _receipt_item_status(item),
                "notes": item.get("notes") or "",
                "entity_display": item.get("customer_name") or item.get("supplier_name") or "-",
                "customer_name": item.get("customer_name"),
                "supplier_name": item.get("supplier_name"),
                "source_type": item.get("source_type"),
                "payment_confirmed": bool(item.get("payment_confirmed")),
            }
        )
    totals = {
        "total_incoming": total_incoming,
        "total_outgoing": total_outgoing,
        "net_total": total_incoming - total_outgoing,
        "grand_total": total_incoming + total_outgoing,
    }
    return jsonify(
        {
            "payments": payload,
            "current_page": pagination.page,
            "total_pages": pagination.pages or 1,
            "totals": totals,
        }
    )


def _scoped_suppliers_query():
    from models import Payment, Purchase
    from utils.decorators import branch_scope_id

    scoped_branch_id = branch_scope_id()
    query = tenant_query(Supplier).filter(Supplier.is_active)
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


@payments_bp.route("/receipts")
@login_required
@permission_required("manage_payments")
def receipts():
    """عرض جميع المدفوعات (سندات القبض والصرف) في قائمة موحدة"""
    from models import Payment

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    search = request.args.get("search", "", type=str)
    direction_filter = request.args.get("direction", "", type=str)  # incoming, outgoing, all

    receipts_query = tenant_query(Receipt)
    payments_query = tenant_query(Payment)

    if search:
        search_filter = f"%{search}%"
        receipts_query = receipts_query.join(Customer).filter(
            db.or_(
                Receipt.receipt_number.ilike(search_filter),
                Customer.name.ilike(search_filter),
            )
        )
        payments_query = payments_query.filter(
            db.or_(
                Payment.payment_number.ilike(search_filter),
                Payment.supplier_name.ilike(search_filter),
            )
        )

    if direction_filter == "incoming":
        receipts_query = receipts_query.filter(Receipt.direction == "incoming")
        payments_query = payments_query.filter(Payment.direction == "incoming")
    elif direction_filter == "outgoing":
        receipts_query = receipts_query.filter(Receipt.direction == "outgoing")
        payments_query = payments_query.filter(Payment.direction == "outgoing")

    from models import ArchivedRecord

    tid = get_active_tenant_id(current_user)
    archived_receipts_select = select(ArchivedRecord.record_id).where(ArchivedRecord.table_name == "receipts")
    archived_payments_select = select(ArchivedRecord.record_id).where(ArchivedRecord.table_name == "payments")
    if tid is not None:
        archived_receipts_select = archived_receipts_select.where(ArchivedRecord.tenant_id == tid)
        archived_payments_select = archived_payments_select.where(ArchivedRecord.tenant_id == tid)

    receipts_query = receipts_query.filter(Receipt.id.notin_(archived_receipts_select))
    payments_query = payments_query.filter(Payment.id.notin_(archived_payments_select))

    if current_user.is_seller():
        receipts_query = receipts_query.filter(Receipt.user_id == current_user.id)
        payments_query = payments_query.filter(Payment.user_id == current_user.id)
    from utils.decorators import branch_scope_id

    branch_id = branch_scope_id()
    if branch_id is not None:
        receipts_query = receipts_query.filter(Receipt.branch_id == branch_id)
        payments_query = payments_query.filter(Payment.branch_id == branch_id)
    fetch_limit = max(page * per_page, per_page)
    total = receipts_query.count() + payments_query.count()
    all_receipts = receipts_query.order_by(Receipt.receipt_date.desc()).limit(fetch_limit).all()
    all_payments = payments_query.order_by(Payment.payment_date.desc()).limit(fetch_limit).all()

    combined_items = []

    for receipt in all_receipts:
        receipt_branch_label = (
            f"{receipt.branch.name} ({receipt.branch.code})"
            if receipt.branch and getattr(receipt.branch, "code", None)
            else (receipt.branch.name if receipt.branch else "-")
        )
        combined_items.append(
            {
                "id": receipt.id,
                "number": receipt.receipt_number,
                "date": receipt.receipt_date,
                "amount": receipt.amount,
                "currency": receipt.currency,
                "amount_aed": receipt.amount_aed,
                "direction": receipt.direction,
                "type": "receipt",
                "customer_name": receipt.customer.name if receipt.customer else "-",
                "supplier_name": None,
                "payment_method": receipt.payment_method,
                "payment_confirmed": receipt.payment_confirmed,
                "source_type": receipt.source_type,
                "notes": receipt.notes,
                "branch_label": receipt_branch_label,
            }
        )

    for payment in all_payments:
        payment_branch_label = (
            f"{payment.branch.name} ({payment.branch.code})"
            if payment.branch and getattr(payment.branch, "code", None)
            else (payment.branch.name if payment.branch else "-")
        )
        combined_items.append(
            {
                "id": payment.id,
                "number": payment.payment_number,
                "date": payment.payment_date,
                "amount": payment.amount,
                "currency": payment.currency,
                "amount_aed": payment.amount_aed,
                "direction": payment.direction,
                "type": "payment",
                "customer_name": None,
                "supplier_name": payment.supplier_name,
                "payment_method": payment.payment_method,
                "payment_confirmed": payment.payment_confirmed,
                "source_type": payment.payment_type,
                "notes": payment.notes,
                "branch_label": payment_branch_label,
            }
        )

    combined_items.sort(key=lambda x: x["date"], reverse=True)

    start = (page - 1) * per_page
    end = start + per_page
    paginated_items = combined_items[start:end]

    class SimplePagination:
        def __init__(self, page, per_page, total, items):
            self.page = page
            self.per_page = per_page
            self.total = total
            self.items = items
            self.pages = (total + per_page - 1) // per_page
            self.has_prev = page > 1
            self.has_next = page < self.pages
            self.prev_num = page - 1 if self.has_prev else None
            self.next_num = page + 1 if self.has_next else None

        def iter_pages(self, left_edge=1, right_edge=1, left_current=2, right_current=2):
            last = 0
            for num in range(1, self.pages + 1):
                if (
                    num <= left_edge
                    or (self.page - left_current - 1 < num < self.page + right_current)
                    or num > self.pages - right_edge
                ):
                    if last + 1 != num:
                        yield None
                    yield num
                    last = num

    pagination = SimplePagination(page=page, per_page=per_page, total=total, items=paginated_items)

    wants_json = request.args.get("format") == "json" or request.accept_mimetypes.best == "application/json"
    if wants_json:
        return _build_receipts_json_response(paginated_items, pagination)

    return render_template(
        "payments/receipts.html",
        receipts=paginated_items,
        pagination=pagination,
        direction_filter=direction_filter,
        show_branch_columns=should_show_all_branch_columns(current_user),
    )


@payments_bp.route("/search-entities")
@login_required
@permission_required("manage_payments")
def search_entities():
    """بحث خفيف للجهات المستخدمة في نماذج سندات القبض/الصرف."""
    entity_type = (request.args.get("type") or "customer").strip().lower()
    q = (request.args.get("q") or "").strip()
    limit = min(request.args.get("limit", 20, type=int), 50)

    if entity_type in ("customer", "customers"):
        query = _scoped_customers_query()
        if q:
            term = f"%{q}%"
            query = query.filter(
                db.or_(
                    Customer.name.ilike(term),
                    Customer.phone.ilike(term),
                    Customer.email.ilike(term),
                )
            )
        rows = query.order_by(Customer.name).limit(limit).all()
        return jsonify(
            [
                {
                    "id": r.id,
                    "name": r.name,
                    "display": f"{r.name} - {r.phone or ''}".strip(" -"),
                    "phone": r.phone or "",
                }
                for r in rows
            ]
        )

    if entity_type in ("supplier", "suppliers"):
        query = _scoped_suppliers_query()
        if q:
            term = f"%{q}%"
            query = query.filter(
                db.or_(
                    Supplier.name.ilike(term),
                    Supplier.phone.ilike(term),
                    Supplier.email.ilike(term),
                )
            )
        rows = query.order_by(Supplier.name).limit(limit).all()
        return jsonify(
            [
                {
                    "id": r.id,
                    "name": r.name,
                    "display": f"{r.name} - {r.phone or ''}".strip(" -"),
                    "phone": r.phone or "",
                }
                for r in rows
            ]
        )

    return jsonify([])


@payments_bp.route("/payments/<int:id>")
@login_required
@permission_required("manage_payments")
def view_payment(**kwargs):
    """عرض سند صرف - يستخدم نفس قالب سندات القبض"""
    from models import Payment

    record_id = kwargs.pop("id")
    payment = tenant_get_or_404(Payment, record_id)
    payment_branch_id = payment.branch_id
    if not _in_scope_branch(payment_branch_id):
        return render_template("errors/403.html"), 403
    return render_template("payments/view_receipt.html", receipt=payment, is_payment=True)


@payments_bp.route("/payments/<int:id>/print")
@login_required
@permission_required("manage_payments")
def print_payment(**kwargs):
    """طباعة سند صرف - يستخدم نفس قالب طباعة سندات القبض"""
    from models import Payment

    record_id = kwargs.pop("id")
    payment = tenant_get_or_404(Payment, record_id)
    payment_branch_id = payment.branch_id
    if not _in_scope_branch(payment_branch_id):
        return render_template("errors/403.html"), 403
    from models import Branch
    from utils.tenant_branding import get_print_header_context

    tid = getattr(payment, "tenant_id", None)
    tenant, settings, company = InvoiceSettings.company_print_context(tid)
    print_branding = get_print_header_context(tid)
    print_branch = Branch.query.filter_by(id=payment_branch_id, tenant_id=tid).first() if payment_branch_id else None
    try:
        default_currency = resolve_default_currency(tenant)
    except Exception:
        default_currency = get_system_default_currency()
    print_user_name = (
        payment.user.get_display_name("ar")
        if payment.user and hasattr(payment.user, "get_display_name")
        else (
            payment.user.full_name
            if payment.user and payment.user.full_name
            else (payment.user.username if payment.user else "")
        )
    )
    amount_in_words = number_to_arabic_words(float(payment.amount or 0), payment.currency or default_currency)
    qr_data_url = ""
    if settings and settings.enable_qr_code:
        from services.document_verification_service import DocumentVerificationService

        ver = DocumentVerificationService.get_or_create_verification("payment", payment.id, tid)
        if ver:
            ver_url = url_for("public.verify_document", token=ver.public_token, _external=True)
            qr_data_url = generate_qr_data_url(ver_url)
        else:
            qr_data_url = generate_qr_data_url(
                {
                    "t": "payment",
                    "n": payment.payment_number,
                    "a": float(payment.amount or 0),
                    "c": payment.currency or default_currency,
                    "d": (payment.payment_date.strftime("%Y-%m-%d") if payment.payment_date else ""),
                    "co": company.get("name_ar") or (tenant.name_ar if tenant else ""),
                    "u": print_user_name,
                    "b": print_branch.name if print_branch else "",
                }
            )
    return render_template(
        "payments/print_receipt.html",
        receipt=payment,
        is_payment=True,
        company=company,
        settings=settings,
        printed_at=datetime.now(),
        print_branch=print_branch,
        print_user_name=print_user_name,
        amount_in_words=amount_in_words,
        qr_data_url=qr_data_url,
        doc_number=payment.payment_number,
        print_branding=print_branding,
        print_tenant_id=tid,
    )


@payments_bp.route("/payments/<int:id>/archive", methods=["POST"])
@login_required
@permission_required("manage_payments")
def archive_payment(**kwargs):
    """أرشفة سند صرف"""
    from models import Payment
    from services.archive_service import ArchiveService

    record_id = kwargs.pop("id")
    payment = tenant_get_or_404(Payment, record_id)
    if not _in_scope_branch(payment.branch_id):
        return render_template("errors/403.html"), 403

    try:
        archive_service = ArchiveService()
        with atomic_transaction("payment_archive"):
            archive_service.archive_record("payments", payment, reason=gettext("تم أرشفة سند الصرف"))
            LoggingCore.log_audit("archive", "payments", payment.id)

    except Exception as e:
        current_app.logger.error(f"Failed to archive payment {record_id}: {e}")
        flash(gettext(f"فشلت الأرشفة: {str(e)}"), "danger")
        return redirect(url_for("payments.receipts"))

    return redirect(url_for("payments.receipts"))


@payments_bp.route("/payments/<int:id>/restore", methods=["POST"])
@login_required
@permission_required("manage_payments")
def restore_payment(**kwargs):
    """استعادة سند صرف من الأرشيف"""
    from models import ArchivedRecord

    record_id = kwargs.pop("id")
    tid = get_active_tenant_id(current_user)
    archived_query = ArchivedRecord.query.filter_by(table_name="payments", record_id=record_id)
    if tid is not None:
        archived_query = archived_query.filter(ArchivedRecord.tenant_id == tid)
    archived = archived_query.first_or_404()
    if not _in_scope_branch(_archived_item_branch_id(archived)):
        return render_template("errors/403.html"), 403

    try:
        with atomic_transaction("payment_restore"):
            db.session.delete(archived)
            LoggingCore.log_audit("restore", "payments", record_id)
    except Exception as exc:
        current_app.logger.error("Failed to restore payment %s: %s", record_id, exc)
        flash(gettext("تعذر استعادة سند الصرف. يرجى المحاولة مرة أخرى."), "danger")
        return redirect(url_for("payments.archived_receipts"))

    flash(gettext("تم استعادة سند الصرف بنجاح."), "success")
    return redirect(url_for("payments.archived_receipts"))


@payments_bp.route("/create_from_sale/<int:sale_id>", methods=["GET", "POST"])
@login_required
@permission_required("manage_payments")
def create_from_sale(sale_id):
    """إنشاء سند دفع من فاتورة بيع معينة"""
    from models import Sale

    sale = tenant_get_or_404(Sale, sale_id)
    if not _in_scope_branch(sale.branch_id):
        return render_template("errors/403.html"), 403
    sale_balance_aed = float(sale.balance_due or 0)
    sale_rate = float(sale.exchange_rate or 1)
    from utils.currency_utils import get_system_default_currency

    _sys_default = get_system_default_currency()
    if (sale.currency or _sys_default) != _sys_default and sale_rate > 0:
        suggested_sale_amount = sale_balance_aed / sale_rate
    else:
        suggested_sale_amount = sale_balance_aed

    if request.method == "POST":
        try:
            amount = request.form.get("amount", type=float)
            try:
                default_currency = (sale.currency or "").strip() or resolve_default_currency()
            except Exception as e:
                import sys
                import traceback

                sys.stderr.write(f"[PAYMENTS_WARNING] Failed to get tenant default currency: {e}\n")
                traceback.print_exc()
                try:
                    LoggingCore.log_error(
                        message=str(e),
                        category="PAYMENTS",
                        source="routes.payments.create_from_sale.get_default_currency",
                        level="WARNING",
                        exception=e,
                    )
                except Exception:
                    current_app.logger.exception("Failed to log currency resolution error for sale payment")
                default_currency = (sale.currency or "").strip() or resolve_default_currency()
            currency = request.form.get("currency") or default_currency
            user_exchange_rate = request.form.get("exchange_rate", type=float)
            payment_method_value = (request.form.get("payment_method") or "").strip()
            if not payment_method_value:
                flash(gettext("يرجى اختيار طريقة الدفع."), "warning")
                exchange_rates = CurrencyService.get_all_rates(default_currency)
                suggested_amount = suggested_sale_amount
                return render_template(
                    "payments/create_receipt.html",
                    customers=[sale.customer],
                    preselected_customer=sale.customer,
                    suggested_amount=suggested_amount,
                    exchange_rates=exchange_rates,
                    sale=sale,
                    form_data=request.form,
                )

            reference_number = request.form.get("reference_number")
            cheque_number = request.form.get("cheque_number")
            cheque_date = request.form.get("cheque_date") or None
            bank_name = request.form.get("bank_name")
            notes = request.form.get("notes")

            allocate_to_sales = {sale.id: amount}

            receipt_data = {
                "customer_id": sale.customer_id,
                "amount": amount,
                "currency": currency,
                "user_exchange_rate": user_exchange_rate,
                "payment_method": payment_method_value,
                "reference_number": reference_number,
                "cheque_number": cheque_number,
                "cheque_date": cheque_date,
                "bank_name": bank_name,
                "notes": notes,
                "allocate_to_sales": allocate_to_sales,
                "branch_id": sale.branch_id,
            }

            with atomic_transaction("receipt_creation_from_sale"):
                receipt = PaymentService.create_receipt(receipt_data)
                LoggingCore.log_audit("create", "receipts", receipt.id)

            flash(gettext("تم إنشاء سند القبض بنجاح"), "success")
            return redirect(url_for("payments.view_receipt", id=receipt.id))

        except Exception as e:
            flash(
                gettext(f"حدث خطأ: {str(e)}\nتحقق من البيانات المدخلة وحاول مرة أخرى."),
                "danger",
            )

    return redirect(
        url_for(
            "payments.create_voucher",
            direction="incoming",
            party_type="customer",
            party_id=sale.customer_id,
            amount=suggested_sale_amount,
            currency=sale.currency,
            exchange_rate=float(sale.exchange_rate or 1),
        )
    )


@payments_bp.route("/voucher/create", methods=["GET"])
@login_required
@permission_required("manage_payments")
def create_voucher():
    """عرض صفحة إنشاء سند مالي موحد (قبض/صرف)"""
    customers = _scoped_customers_query().order_by(Customer.name).all()
    suppliers = _scoped_suppliers_query().order_by(Supplier.name).all()

    customers_data = [{"id": c.id, "name": c.name, "type": c.customer_type} for c in customers]

    suppliers_data = [{"id": s.id, "name": s.name} for s in suppliers]

    preselected_direction = request.args.get("direction", "incoming")
    preselected_party_type = request.args.get("party_type", "customer")
    preselected_party_id = request.args.get("party_id", type=int) or request.args.get("customer_id", type=int)
    preselected_amount = request.args.get("amount", type=float)
    preselected_currency = request.args.get("currency")
    preselected_exchange_rate = request.args.get("exchange_rate", type=float)

    return render_template(
        "payments/voucher.html",
        customers_json=customers_data,
        suppliers_json=suppliers_data,
        today_date=datetime.now().date().isoformat(),
        preselected_direction=preselected_direction,
        preselected_party_type=preselected_party_type,
        preselected_party_id=preselected_party_id,
        preselected_amount=preselected_amount,
        preselected_currency=preselected_currency,
        preselected_exchange_rate=preselected_exchange_rate,
    )


@payments_bp.route("/voucher/submit", methods=["POST"])
@login_required
@permission_required("manage_payments")
def create_voucher_submit():
    """معالجة حفظ السند المالي الموحد"""
    try:
        direction = request.form.get("direction")  # incoming, outgoing
        party_type = request.form.get("party_type")  # customer, supplier
        party_id = request.form.get("party_id", type=int)
        amount = request.form.get("amount", type=float)
        payment_method = request.form.get("payment_method")
        date_str = request.form.get("date")
        notes = request.form.get("notes")
        branch_id = _current_branch_id()

        try:
            default_currency = resolve_default_currency()
        except Exception as e:
            import sys
            import traceback

            sys.stderr.write(f"[PAYMENTS_WARNING] Failed to get tenant default currency (voucher submit): {e}\n")
            traceback.print_exc()
            try:
                LoggingCore.log_error(
                    message=str(e),
                    category="PAYMENTS",
                    source="routes.payments.create_voucher_submit.get_default_currency",
                    level="WARNING",
                    exception=e,
                )
            except Exception:
                current_app.logger.exception("Failed to log currency resolution error for voucher submit")
            default_currency = get_system_default_currency()
        currency = request.form.get("currency") or default_currency
        user_exchange_rate = request.form.get("exchange_rate", type=float, default=1.0)

        cheque_number = request.form.get("cheque_number")
        cheque_date = request.form.get("cheque_date")
        bank_name = request.form.get("bank_name")

        if not party_id or not amount:
            flash(gettext("يرجى تعبئة جميع الحقول الإلزامية"), "warning")
            return redirect(url_for("payments.create_voucher"))

        if direction == "incoming":
            if party_type == "customer":
                customer = _ensure_customer_scope(party_id)
                if not customer:
                    flash(gettext("العميل المحدد خارج نطاق الفرع الحالي"), "danger")
                    return redirect(url_for("payments.create_voucher"))
                receipt_data = {
                    "customer_id": customer.id,
                    "amount": amount,
                    "currency": currency,
                    "user_exchange_rate": user_exchange_rate,
                    "payment_method": payment_method,
                    "notes": notes,
                    "cheque_number": (cheque_number if payment_method == "cheque" else None),
                    "cheque_date": cheque_date if payment_method == "cheque" else None,
                    "bank_name": bank_name if payment_method == "cheque" else None,
                    "branch_id": branch_id,
                }
                with atomic_transaction("receipt_creation_from_voucher"):
                    receipt = PaymentService.create_receipt(receipt_data)
                flash(
                    gettext(f"تم إنشاء سند القبض رقم {receipt.receipt_number} بنجاح"),
                    "success",
                )
                return redirect(url_for("payments.receipts"))

            elif party_type == "supplier":
                from utils.helpers import generate_number
                from decimal import Decimal

                exchange_rate = _resolve_transaction_rate(currency, user_exchange_rate)
                amount_decimal = Decimal(str(amount))
                from utils.currency_utils import convert_and_quantize_aed

                amount_aed = convert_and_quantize_aed(amount_decimal, currency, exchange_rate)

                supplier = _ensure_supplier_scope(party_id)
                if not supplier:
                    flash(gettext("المورد المحدد خارج نطاق الفرع الحالي"), "danger")
                    return redirect(url_for("payments.create_voucher"))
                tenant_id = getattr(supplier, "tenant_id", None) or get_active_tenant_id(current_user)
                with atomic_transaction("supplier_refund_creation"):
                    payment = Payment(
                        tenant_id=tenant_id,
                        payment_number=generate_number(
                            "PAY",
                            Payment,
                            "payment_number",
                            branch_id=branch_id,
                            tenant_id=tenant_id,
                        ),
                        payment_type="refund",
                        direction="incoming",
                        supplier_id=supplier.id,
                        supplier_name=supplier.name,
                        amount=amount_decimal,
                        currency=currency,
                        exchange_rate=exchange_rate,
                        amount_aed=amount_aed,
                        payment_method=payment_method,
                        notes=notes,
                        cheque_number=(cheque_number if payment_method == "cheque" else None),
                        cheque_date=cheque_date if payment_method == "cheque" else None,
                        bank_name=bank_name if payment_method == "cheque" else None,
                        user_id=current_user.id,
                        branch_id=branch_id,
                    )
                    db.session.add(payment)
                    db.session.flush()
                    from services.gl_service import GLService

                    GLService.ensure_core_accounts(tenant_id=tenant_id)
                    credit_account = GLService.get_payment_debit_account(
                        payment_method,
                        branch_id=payment.branch_id,
                        tenant_id=tenant_id,
                    )
                    post_or_fail(
                        [
                            {
                                "account": credit_account,
                                "concept_code": GLService.get_payment_debit_concept(payment_method),
                                "debit": payment.amount,
                                "description": gettext(f"استرداد من مورد {supplier.name}"),
                            },
                            {
                                "account": "2110",
                                "concept_code": "AP",
                                "credit": payment.amount,
                                "description": gettext(f"سند قبض {payment.payment_number}"),
                            },
                        ],
                        description=f"Supplier refund {payment.payment_number}",
                        reference_type=GLRef.PAYMENT,
                        reference_id=payment.id,
                        currency=currency,
                        exchange_rate=exchange_rate,
                        branch_id=payment.branch_id,
                        tenant_id=tenant_id,
                    )
                    # A refund received from the supplier offsets AP (the GL
                    # entry above credits AP). Reduce the cached paid total so
                    # the supplier balance and statement reflect the refund.
                    supplier.apply_payment(-Decimal(str(payment.amount_aed or 0)))
                flash(gettext("تم إنشاء سند قبض من مورد بنجاح"), "success")
                return redirect(url_for("payments.receipts"))

        elif direction == "outgoing":
            from utils.helpers import generate_number
            from decimal import Decimal

            exchange_rate = _resolve_transaction_rate(currency, user_exchange_rate)
            amount_decimal = Decimal(str(amount))
            from utils.currency_utils import convert_and_quantize_aed

            amount_aed = convert_and_quantize_aed(amount_decimal, currency, exchange_rate)

            if party_type == "supplier":
                supplier = _ensure_supplier_scope(party_id)
                if not supplier:
                    flash(gettext("المورد المحدد خارج نطاق الفرع الحالي"), "danger")
                    return redirect(url_for("payments.create_voucher"))
                tenant_id = getattr(supplier, "tenant_id", None) or get_active_tenant_id(current_user)
                with atomic_transaction("supplier_payment_creation"):
                    payment = Payment(
                        tenant_id=tenant_id,
                        payment_number=generate_number(
                            "PAY",
                            Payment,
                            "payment_number",
                            branch_id=branch_id,
                            tenant_id=tenant_id,
                        ),
                        payment_type="bill_payment",
                        direction="outgoing",
                        supplier_id=supplier.id,
                        supplier_name=supplier.name,
                        amount=amount_decimal,
                        currency=currency,
                        exchange_rate=exchange_rate,
                        amount_aed=amount_aed,
                        payment_method=payment_method,
                        notes=notes,
                        cheque_number=(cheque_number if payment_method == "cheque" else None),
                        cheque_date=cheque_date if payment_method == "cheque" else None,
                        bank_name=bank_name if payment_method == "cheque" else None,
                        user_id=current_user.id,
                        branch_id=branch_id,
                    )
                    db.session.add(payment)
                    db.session.flush()  # Flush to get ID

                    if payment_method == "cheque" and cheque_number:
                        from models import Cheque

                        cheque = Cheque(
                            tenant_id=tenant_id,
                            cheque_number=cheque_number,
                            cheque_bank_number=cheque_number,
                            cheque_type="outgoing",
                            supplier_id=supplier.id,
                            payment_id=payment.id,
                            amount=payment.amount,
                            currency=payment.currency,
                            exchange_rate=payment.exchange_rate,
                            amount_aed=payment.amount_aed,
                            issue_date=(
                                datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else datetime.now().date()
                            ),
                            due_date=(
                                datetime.strptime(cheque_date, "%Y-%m-%d").date()
                                if cheque_date
                                else datetime.now().date()
                            ),
                            bank_name=bank_name,
                            payee_name=supplier.name,
                            status="pending",
                            notes=notes,
                            user_id=current_user.id,
                            branch_id=branch_id,
                        )
                        db.session.add(cheque)
                        db.session.flush()
                        payment.cheque_id = cheque.id
                        payment.payment_confirmed = False

                        process_cheque_issue(cheque)

                    else:
                        from services.gl_service import GLService

                        GLService.ensure_core_accounts(tenant_id=tenant_id)
                        credit_account = GLService.get_payment_credit_account(
                            payment_method,
                            branch_id=payment.branch_id,
                            tenant_id=tenant_id,
                        )
                        lines = [
                            {
                                "account": "2110",
                                "concept_code": "AP",
                                "debit": payment.amount,
                                "description": gettext(f"سداد للمورد {payment.supplier_name}"),
                            },
                            {
                                "account": credit_account,
                                "concept_code": GLService.get_payment_credit_concept(payment_method),
                                "credit": payment.amount,
                                "description": gettext(f"سند صرف {payment.payment_number}"),
                            },
                        ]
                        post_or_fail(
                            lines,
                            description=f"Payment {payment.payment_number}",
                            reference_type=GLRef.PAYMENT,
                            reference_id=payment.id,
                            currency=currency,
                            exchange_rate=exchange_rate,
                            branch_id=payment.branch_id,
                            tenant_id=tenant_id,
                        )

                    supplier.apply_payment(Decimal(str(payment.amount_aed or 0)))

                flash(gettext("تم إنشاء سند صرف لمورد بنجاح"), "success")
                return redirect(url_for("payments.receipts"))

            elif party_type == "customer":
                # Payment model has customer_id field
                customer = _ensure_customer_scope(party_id)
                if not customer:
                    flash(gettext("العميل المحدد خارج نطاق الفرع الحالي"), "danger")
                    return redirect(url_for("payments.create_voucher"))
                tenant_id = getattr(customer, "tenant_id", None) or get_active_tenant_id(current_user)
                with atomic_transaction("customer_refund_creation"):
                    payment = Payment(
                        tenant_id=tenant_id,
                        payment_number=generate_number(
                            "PAY",
                            Payment,
                            "payment_number",
                            branch_id=branch_id,
                            tenant_id=tenant_id,
                        ),
                        payment_type="refund",
                        direction="outgoing",
                        customer_id=customer.id,
                        amount=amount_decimal,
                        currency=currency,
                        exchange_rate=exchange_rate,
                        amount_aed=amount_aed,
                        payment_method=payment_method,
                        notes=notes,
                        cheque_number=(cheque_number if payment_method == "cheque" else None),
                        cheque_date=cheque_date if payment_method == "cheque" else None,
                        bank_name=bank_name if payment_method == "cheque" else None,
                        user_id=current_user.id,
                        branch_id=branch_id,
                    )
                    db.session.add(payment)
                    db.session.flush()  # Flush to get ID

                    if payment_method == "cheque" and cheque_number:
                        from models import Cheque

                        cheque = Cheque(
                            tenant_id=tenant_id,
                            cheque_number=cheque_number,
                            cheque_bank_number=cheque_number,
                            cheque_type="outgoing",
                            customer_id=customer.id,
                            payment_id=payment.id,
                            amount=payment.amount,
                            currency=payment.currency,
                            exchange_rate=payment.exchange_rate,
                            amount_aed=payment.amount_aed,
                            issue_date=(
                                datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else datetime.now().date()
                            ),
                            due_date=(
                                datetime.strptime(cheque_date, "%Y-%m-%d").date()
                                if cheque_date
                                else datetime.now().date()
                            ),
                            bank_name=bank_name,
                            payee_name=customer.name,
                            status="pending",
                            notes=notes,
                            user_id=current_user.id,
                            branch_id=branch_id,
                        )
                        db.session.add(cheque)
                        db.session.flush()
                        payment.cheque_id = cheque.id
                        payment.payment_confirmed = False

                        process_cheque_issue(cheque)

                    else:
                        from services.gl_service import GLService

                        GLService.ensure_core_accounts(tenant_id=tenant_id)
                        credit_account = GLService.get_payment_credit_account(
                            payment_method,
                            branch_id=payment.branch_id,
                            tenant_id=tenant_id,
                        )
                        debit_account = GLService.get_customer_credit_account(
                            customer,
                            branch_id=payment.branch_id,
                            tenant_id=tenant_id,
                        )
                        lines = [
                            {
                                "account": debit_account,
                                "concept_code": GLService.get_customer_credit_concept(customer),
                                "debit": payment.amount,
                                "description": gettext(f"سداد/سحب {customer.name}"),
                            },
                            {
                                "account": credit_account,
                                "concept_code": GLService.get_payment_credit_concept(payment_method),
                                "credit": payment.amount,
                                "description": gettext(f"سند صرف {payment.payment_number}"),
                            },
                        ]
                        post_or_fail(
                            lines,
                            description=f"Payment {payment.payment_number}",
                            reference_type=GLRef.PAYMENT,
                            reference_id=payment.id,
                            currency=currency,
                            exchange_rate=exchange_rate,
                            branch_id=payment.branch_id,
                            tenant_id=tenant_id,
                        )

                    customer.apply_receipt(-Decimal(str(payment.amount_aed or 0)))

                flash(gettext("تم إنشاء سند صرف لعميل/شريك بنجاح"), "success")
                return redirect(url_for("payments.receipts"))

    except Exception as e:
        current_app.logger.error(f"Voucher creation error: {e}")
        flash(gettext(f"حدث خطأ أثناء حفظ السند: {str(e)}"), "danger")
        return redirect(url_for("payments.create_voucher"))

    return redirect(url_for("payments.receipts"))


@payments_bp.route("/receipts/create", methods=["GET", "POST"])
@login_required
@permission_required("manage_payments")
def create_receipt():
    """إعادة توجيه المسار القديم إلى سند موحد مع الحفاظ على معاملات الرابط."""
    return redirect(url_for("payments.create_voucher", **request.args.to_dict()))


@payments_bp.route("/receipts/<int:id>")
@login_required
@permission_required("manage_payments")
def view_receipt(**kwargs):
    record_id = kwargs.pop("id")
    receipt = tenant_get(Receipt, record_id, or_404=False)
    if not receipt:
        payment = tenant_get(Payment, record_id, or_404=False)
        if payment:
            return redirect(url_for("payments.view_payment", id=record_id))
        abort(404)
    receipt_branch_id = receipt.branch_id
    if receipt.source_type == "sale" and receipt.source_id:
        from models import Sale

        sale = tenant_get(Sale, receipt.source_id, or_404=False)
        receipt_branch_id = sale.branch_id if sale else None
    if not _in_scope_branch(receipt_branch_id):
        return render_template("errors/403.html"), 403

    if current_user.is_seller() and not current_user.is_owner and receipt.user_id != current_user.id:
        flash(gettext("ليس لديك صلاحية لعرض هذا السند"), "danger")
        return redirect(url_for("payments.receipts"))

    return render_template("payments/view_receipt.html", receipt=receipt)


@payments_bp.route("/receipts/<int:id>/print")
@login_required
@permission_required("manage_payments")
def print_receipt(**kwargs):
    record_id = kwargs.pop("id")
    receipt = tenant_get(Receipt, record_id, or_404=False)
    if receipt:
        if not assert_tenant_record(receipt):
            abort(404)
    else:
        payment = tenant_get(Payment, record_id, or_404=False)
        if payment:
            return redirect(url_for("payments.print_payment", id=record_id))
        abort(404)
    receipt_branch_id = receipt.branch_id
    if receipt.source_type == "sale" and receipt.source_id:
        from models import Sale

        sale = tenant_get(Sale, receipt.source_id, or_404=False)
        receipt_branch_id = sale.branch_id if sale else None
    if not _in_scope_branch(receipt_branch_id):
        return render_template("errors/403.html"), 403

    if current_user.is_seller() and not current_user.is_owner and receipt.user_id != current_user.id:
        flash(gettext("ليس لديك صلاحية لطباعة هذا السند"), "danger")
        return redirect(url_for("payments.receipts"))

    from utils.tenant_branding import get_print_header_context

    tid = receipt.tenant_id
    settings = InvoiceSettings.get_active(tid)
    print_branding = get_print_header_context(tid)

    template = settings.active_template if settings and settings.active_template else "modern"
    template_path = f"receipts/{template}.html"

    from models import Branch

    tenant, settings, company = InvoiceSettings.company_print_context(tid)
    print_branch = Branch.query.filter_by(id=receipt_branch_id, tenant_id=tid).first() if receipt_branch_id else None
    try:
        default_currency = resolve_default_currency(tenant)
    except Exception:
        default_currency = get_system_default_currency()
    print_user_name = (
        receipt.user.get_display_name("ar")
        if receipt.user and hasattr(receipt.user, "get_display_name")
        else (
            receipt.user.full_name
            if receipt.user and receipt.user.full_name
            else (receipt.user.username if receipt.user else "")
        )
    )
    amount_in_words = number_to_arabic_words(float(receipt.amount or 0), receipt.currency or default_currency)
    qr_data_url = ""
    if settings and settings.enable_qr_code:
        from services.document_verification_service import DocumentVerificationService

        ver = DocumentVerificationService.get_or_create_verification("receipt", receipt.id, tid)
        if ver:
            ver_url = url_for("public.verify_document", token=ver.public_token, _external=True)
            qr_data_url = generate_qr_data_url(ver_url)
        else:
            qr_data_url = generate_qr_data_url(
                {
                    "t": "receipt",
                    "n": receipt.receipt_number,
                    "a": float(receipt.amount or 0),
                    "c": receipt.currency or default_currency,
                    "d": (receipt.receipt_date.strftime("%Y-%m-%d") if receipt.receipt_date else ""),
                    "co": company.get("name_ar") or (tenant.name_ar if tenant else ""),
                    "u": print_user_name,
                    "b": print_branch.name if print_branch else "",
                }
            )
    try:
        return render_template(
            template_path,
            receipt=receipt,
            settings=settings,
            company=company,
            printed_at=datetime.now(),
            print_branch=print_branch,
            print_user_name=print_user_name,
            amount_in_words=amount_in_words,
            qr_data_url=qr_data_url,
            doc_number=receipt.receipt_number,
            print_branding=print_branding,
            print_tenant_id=tid,
        )
    except Exception as e:
        import sys
        import traceback

        sys.stderr.write(f"[PAYMENTS_WARNING] Failed to render custom receipt template, falling back to modern: {e}\n")
        traceback.print_exc()
        try:
            LoggingCore.log_error(
                message=str(e),
                category="PAYMENTS",
                source="routes.payments.print_receipt.render_template",
                level="WARNING",
                exception=e,
            )
        except Exception:
            current_app.logger.exception("Failed to log receipt template rendering error")
        return render_template(
            "receipts/modern.html",
            receipt=receipt,
            settings=settings,
            company=company,
            printed_at=datetime.now(),
            print_branch=print_branch,
            print_user_name=print_user_name,
            amount_in_words=amount_in_words,
            qr_data_url=qr_data_url,
            doc_number=receipt.receipt_number,
            print_branding=print_branding,
            print_tenant_id=tid,
        )


@payments_bp.route("/archived")
@login_required
@permission_required("manage_payments")
def archived_receipts():
    """عرض السندات المؤرشفة"""
    from models import ArchivedRecord

    tid = get_active_tenant_id(current_user)

    archived_receipts_query = db.session.query(ArchivedRecord).filter(ArchivedRecord.table_name == "receipts")
    if tid is not None:
        archived_receipts_query = archived_receipts_query.filter(ArchivedRecord.tenant_id == tid)
    archived_payments_query = db.session.query(ArchivedRecord).filter(ArchivedRecord.table_name == "payments")
    if tid is not None:
        archived_payments_query = archived_payments_query.filter(ArchivedRecord.tenant_id == tid)

    archived_items = []

    for archived in archived_receipts_query.all():
        if not _in_scope_branch(_archived_item_branch_id(archived)):
            continue
        data = archived.data
        archived_items.append(
            {
                "id": archived.record_id,
                "number": data.get("receipt_number"),
                "date": (
                    datetime.fromisoformat(data.get("receipt_date").replace("Z", "+00:00"))
                    if isinstance(data.get("receipt_date"), str)
                    else data.get("receipt_date")
                ),
                "amount": float(data.get("amount", 0)),
                "currency": data.get("currency"),
                "amount_aed": float(data.get("amount_aed", 0)),
                "type": "receipt",
                "customer_name": data.get("customer_name"),
                "supplier_name": None,
                "source_type": data.get("source_type"),
                "archived_at": archived.archived_at,
            }
        )

    for archived in archived_payments_query.all():
        if not _in_scope_branch(_archived_item_branch_id(archived)):
            continue
        data = archived.data
        archived_items.append(
            {
                "id": archived.record_id,
                "number": data.get("payment_number"),
                "date": (
                    datetime.fromisoformat(data.get("payment_date").replace("Z", "+00:00"))
                    if isinstance(data.get("payment_date"), str)
                    else data.get("payment_date")
                ),
                "amount": float(data.get("amount", 0)),
                "currency": data.get("currency"),
                "amount_aed": float(data.get("amount_aed", 0)),
                "type": "payment",
                "customer_name": None,
                "supplier_name": data.get("supplier_name"),
                "source_type": data.get("payment_type"),
                "archived_at": archived.archived_at,
            }
        )

    archived_items.sort(key=lambda x: x["archived_at"], reverse=True)

    return render_template("payments/archived.html", archived_items=archived_items)


@payments_bp.route("/receipts/<int:id>/archive", methods=["POST"])
@login_required
@permission_required("manage_payments")
def archive_receipt(**kwargs):
    """أرشفة سند قبض"""
    from services.archive_service import ArchiveService

    record_id = kwargs.pop("id")
    receipt = tenant_get_or_404(Receipt, record_id)
    if not _in_scope_branch(receipt.branch_id):
        return render_template("errors/403.html"), 403

    try:
        with atomic_transaction("receipt_archive"):
            archive_service = ArchiveService()
            archive_service.archive_record("receipts", receipt, reason=gettext("تم أرشفة سند القبض"))
            LoggingCore.log_audit("archive", "receipts", receipt.id)
    except Exception:
        current_app.logger.exception("Failed to archive receipt %s", record_id)

    return redirect(url_for("payments.receipts"))


@payments_bp.route("/receipts/<int:id>/restore", methods=["POST"])
@login_required
@permission_required("manage_payments")
def restore_receipt(**kwargs):
    """استعادة سند قبض من الأرشيف"""
    from models import ArchivedRecord

    record_id = kwargs.pop("id")
    tid = get_active_tenant_id(current_user)
    archived_query = ArchivedRecord.query.filter_by(
        table_name="receipts",
        record_id=record_id,
    )
    if tid is not None:
        archived_query = archived_query.filter_by(tenant_id=tid)
    archived = archived_query.first_or_404()
    if not _in_scope_branch(_archived_item_branch_id(archived)):
        return render_template("errors/403.html"), 403

    try:
        with atomic_transaction("receipt_restore"):
            db.session.delete(archived)
            LoggingCore.log_audit("restore", "receipts", record_id)
    except Exception:
        current_app.logger.exception("Failed to restore receipt %s", record_id)

    return redirect(url_for("payments.archived_receipts"))


@payments_bp.route("/receipts/<int:id>/delete", methods=["POST"])
@login_required
@permission_required("manage_payments")
def delete_receipt(**kwargs):
    """حذف أو أرشفة سند قبض"""
    from models import Receipt
    from services.archive_service import ArchiveService

    record_id = kwargs.pop("id")
    receipt = tenant_get_or_404(Receipt, record_id)
    if not _in_scope_branch(receipt.branch_id):
        return render_template("errors/403.html"), 403

    has_links = False
    if receipt.source_type == "sale" and receipt.source_id:
        has_links = True
    if receipt.cheque_id:
        has_links = True

    try:
        with atomic_transaction("receipt_delete"):
            if receipt.source_type == "sale" and receipt.source_id:
                from models import Sale

                sale = Sale.query.filter_by(id=receipt.source_id, tenant_id=receipt.tenant_id).first()
                if sale:
                    sale.paid_amount -= receipt.amount
                    sale.paid_amount_aed -= receipt.amount_aed

                    if sale.paid_amount < 0:
                        sale.paid_amount = 0
                    if sale.paid_amount_aed < 0:
                        sale.paid_amount_aed = 0

                    sale.balance_due = sale.amount_aed - sale.paid_amount_aed

                    if sale.balance_due <= 0:
                        sale.payment_status = "paid"
                        sale.balance_due = 0
                    elif sale.paid_amount_aed > 0:
                        sale.payment_status = "partial"
                    else:
                        sale.payment_status = "unpaid"

            if has_links:
                archive_service = ArchiveService()
                archive_service.archive_record("receipts", receipt, reason=gettext("تم أرشفة السند لوجود ارتباطات"))

                if receipt.cheque:
                    archive_service.archive_record(
                        "cheques",
                        receipt.cheque,
                        reason=gettext("تم أرشفة الشيك لارتباطه بسند مؤرشف"),
                    )

                LoggingCore.log_audit("archive", "receipts", record_id)
                flash(
                    gettext(f'تم أرشفة سند القبض "{receipt.receipt_number}" (لوجود حركات مرتبطة)'),
                    "warning",
                )
            else:
                from services.gl_service import GLService

                GLService.reverse_entry(
                    reference_type=GLRef.RECEIPT,
                    reference_id=receipt.id,
                    description=f"Reverse Receipt {receipt.receipt_number} (Deleted)",
                    tenant_id=receipt.tenant_id,
                )

                if receipt.cheque:
                    db.session.delete(receipt.cheque)

                db.session.delete(receipt)
                LoggingCore.log_audit("delete", "receipts", record_id)
                flash(
                    gettext(f'تم حذف سند القبض "{receipt.receipt_number}" نهائياً'),
                    "success",
                )

        return redirect(url_for("payments.receipts"))

    except Exception as e:
        flash(gettext(f"فشل الحذف: {str(e)}"), "danger")
        return redirect(url_for("payments.view_receipt", id=record_id))


@payments_bp.route("/payments/<int:id>/delete", methods=["POST"])
@login_required
@permission_required("manage_payments")
def delete_payment(**kwargs):
    """حذف أو أرشفة سند صرف"""
    from decimal import Decimal
    from models import Payment
    from services.archive_service import ArchiveService

    record_id = kwargs.pop("id")
    payment = tenant_get_or_404(Payment, record_id)
    if not _in_scope_branch(payment.branch_id):
        return render_template("errors/403.html"), 403

    has_links = False
    if payment.cheque_id:
        has_links = True

    try:
        with atomic_transaction("payment_delete"):
            if has_links:
                archive_service = ArchiveService()
                archive_service.archive_record("payments", payment, reason=gettext("تم أرشفة السند لوجود ارتباطات"))

                if payment.cheque:
                    archive_service.archive_record(
                        "cheques",
                        payment.cheque,
                        reason=gettext("تم أرشفة الشيك لارتباطه بسند مؤرشف"),
                    )

                LoggingCore.log_audit("archive", "payments", record_id)
                flash(
                    gettext(f'تم أرشفة سند الصرف "{payment.payment_number}" (لوجود حركات مرتبطة)'),
                    "warning",
                )
            else:
                from services.gl_service import GLService

                GLService.reverse_entry(
                    reference_type=GLRef.PAYMENT,
                    reference_id=payment.id,
                    description=f"Reverse Payment {payment.payment_number} (Deleted)",
                    tenant_id=payment.tenant_id,
                )

                if payment.supplier_id:
                    from models import Supplier

                    supplier = Supplier.query.filter_by(id=payment.supplier_id, tenant_id=payment.tenant_id).first()
                    if supplier:
                        supplier.apply_payment(-Decimal(str(payment.amount_aed or 0)))

                if payment.cheque:
                    db.session.delete(payment.cheque)

                db.session.delete(payment)
                LoggingCore.log_audit("delete", "payments", record_id)
                flash(
                    gettext(f'تم حذف سند الصرف "{payment.payment_number}" نهائياً'),
                    "success",
                )

        return redirect(url_for("payments.receipts"))

    except Exception as e:
        flash(gettext(f"فشل الحذف: {str(e)}"), "danger")
        return redirect(url_for("payments.view_payment", id=record_id))


@payments_bp.route("/create_payment/<int:purchase_id>", methods=["GET", "POST"])
@login_required
@permission_required("manage_payments")
def create_payment(purchase_id):
    """إنشاء سند صرف لفاتورة مشتريات"""
    from models import Purchase, Payment, Supplier
    from utils.helpers import generate_number
    from sqlalchemy import func

    purchase = tenant_get_or_404(Purchase, purchase_id)
    if not _in_scope_branch(purchase.branch_id):
        return render_template("errors/403.html"), 403
    supplier = tenant_get(Supplier, purchase.supplier_id, or_404=False) if purchase.supplier_id else None

    paid_amount = (
        db.session.query(func.sum(Payment.amount_aed))
        .filter(
            Payment.purchase_id == purchase.id,
            Payment.tenant_id == purchase.tenant_id,
            Payment.payment_confirmed,
        )
        .scalar()
        or 0
    )

    balance_aed = float(purchase.amount_aed or 0) - float(paid_amount)
    purchase_rate = float(purchase.exchange_rate or 1)
    from utils.currency_utils import get_system_default_currency

    _sys_def_pur = get_system_default_currency()
    if (purchase.currency or _sys_def_pur) != _sys_def_pur and purchase_rate > 0:
        suggested_amount = (balance_aed / purchase_rate) if balance_aed > 0 else 0
    else:
        suggested_amount = balance_aed if balance_aed > 0 else 0

    if request.method == "GET":
        return redirect(
            url_for(
                "payments.create_voucher",
                direction="outgoing",
                party_type="supplier",
                party_id=purchase.supplier_id,
                amount=suggested_amount,
                currency=purchase.currency,
                exchange_rate=float(purchase.exchange_rate or 1),
            )
        )

    if request.method == "POST":
        try:
            from decimal import Decimal

            amount = request.form.get("amount", type=float)
            payment_method_value = (request.form.get("payment_method") or "").strip()
            if not payment_method_value:
                flash(gettext("يرجى اختيار طريقة الدفع."), "warning")
                return render_template(
                    "payments/create_receipt.html",
                    purchase=purchase,
                    supplier=supplier,
                    suggested_amount=suggested_amount,
                    is_payment=True,
                    form_data=request.form,
                )
            notes = request.form.get("notes", "")
            user_exchange_rate = request.form.get("exchange_rate", type=float, default=1.0)
            try:
                default_currency = (purchase.currency or "").strip() or resolve_default_currency()
            except Exception as e:
                import sys
                import traceback

                sys.stderr.write(
                    f"[PAYMENTS_WARNING] Failed to get tenant default currency (create from purchase): {e}\n"
                )
                traceback.print_exc()
                try:
                    LoggingCore.log_error(
                        message=str(e),
                        category="PAYMENTS",
                        source="routes.payments.create_payment.get_default_currency",
                        level="WARNING",
                        exception=e,
                    )
                except Exception:
                    current_app.logger.exception("Failed to log currency resolution error for purchase payment")
                default_currency = (purchase.currency or "").strip() or get_system_default_currency()
            currency = request.form.get("currency") or default_currency

            reference_number = request.form.get("reference_number")
            cheque_number = request.form.get("cheque_number")
            cheque_date = request.form.get("cheque_date") or None
            bank_name = request.form.get("bank_name")
            bank_name_transfer = request.form.get("bank_name_transfer")
            reference_number_transfer = request.form.get("reference_number_transfer")
            card_last4 = request.form.get("card_last4")
            reference_number_card = request.form.get("reference_number_card")

            if amount <= 0:
                flash(
                    gettext("المبلغ غير صحيح.\nتحقق من الصيغة الصحيحة وحاول مرة أخرى."),
                    "danger",
                )
                return redirect(url_for("payments.create_payment", purchase_id=purchase_id))

            amount_decimal = Decimal(str(amount))
            exchange_rate_decimal = _resolve_transaction_rate(currency, user_exchange_rate)
            amount_aed = amount_decimal * exchange_rate_decimal
            if amount_aed > Decimal(str(balance_aed)):
                flash(
                    gettext("المبلغ غير صحيح.\nتحقق من الصيغة الصحيحة وحاول مرة أخرى."),
                    "danger",
                )
                return redirect(url_for("payments.create_payment", purchase_id=purchase_id))

            tenant_id = getattr(purchase, "tenant_id", None) or get_active_tenant_id(current_user)
            with atomic_transaction("purchase_payment_creation"):
                payment_number = generate_number(
                    "PAY",
                    Payment,
                    "payment_number",
                    branch_id=purchase.branch_id,
                    tenant_id=tenant_id,
                )
                payment = Payment(
                    tenant_id=tenant_id,
                    payment_number=payment_number,
                    supplier_id=purchase.supplier_id,
                    supplier_name=purchase.supplier_name,
                    purchase_id=purchase.id,
                    amount=amount_decimal,
                    currency=currency,
                    exchange_rate=exchange_rate_decimal,
                    amount_aed=amount_aed,
                    payment_method=payment_method_value,
                    notes=notes,
                    user_id=current_user.id,
                    direction="outgoing",
                    payment_type="supplier_payment",
                    branch_id=purchase.branch_id,
                )

                if payment_method_value == "bank_transfer":
                    payment.bank_name = bank_name_transfer or bank_name
                    payment.reference_number = reference_number_transfer or reference_number
                elif payment_method_value == "card":
                    payment.reference_number = reference_number_card or reference_number
                    if card_last4:
                        payment.notes = gettext(f"{payment.notes or ''} بطاقة آخر 4: {card_last4}").strip()
                elif payment_method_value == "e_wallet":
                    from flask import request as _req

                    ref_ew = _req.form.get("reference_number_ewallet")
                    payment.reference_number = ref_ew or reference_number
                else:
                    payment.reference_number = reference_number
                    payment.bank_name = bank_name

                db.session.add(payment)
                db.session.flush()

                if payment_method_value == "cheque" and cheque_number:
                    from models import Cheque

                    cheque = Cheque(
                        tenant_id=tenant_id,
                        cheque_number=cheque_number,
                        cheque_bank_number=cheque_number,
                        cheque_type="outgoing",
                        supplier_id=purchase.supplier_id,
                        payment_id=payment.id,
                        amount=amount_decimal,
                        currency=currency,
                        exchange_rate=exchange_rate_decimal,
                        amount_aed=amount_aed,
                        issue_date=datetime.now(timezone.utc).date(),
                        due_date=cheque_date if cheque_date else None,
                        bank_name=bank_name,
                        status="pending",
                        notes=notes,
                        branch_id=purchase.branch_id,
                    )
                    db.session.add(cheque)
                    db.session.flush()
                    payment.cheque_id = cheque.id
                    payment.payment_confirmed = False
                    process_cheque_issue(cheque)
                else:
                    from services.gl_service import GLService

                    tenant_id = getattr(payment, "tenant_id", None)
                    GLService.ensure_core_accounts(tenant_id=tenant_id)
                    cash_or_bank = GLService.get_payment_credit_account(
                        payment_method_value,
                        branch_id=payment.branch_id,
                        tenant_id=tenant_id,
                    )
                    lines = [
                        {
                            "account": "2110",
                            "concept_code": "AP",
                            "debit": payment.amount,
                            "description": gettext(f"سداد للمورد {payment.supplier_name}"),
                        },
                        {
                            "account": cash_or_bank,
                            "concept_code": GLService.get_payment_credit_concept(payment_method_value),
                            "credit": payment.amount,
                            "description": gettext(f"سند صرف {payment.payment_number}"),
                        },
                    ]
                    post_or_fail(
                        lines,
                        description=f"Payment {payment.payment_number}",
                        reference_type=GLRef.PAYMENT,
                        reference_id=payment.id,
                        currency=payment.currency,
                        exchange_rate=payment.exchange_rate,
                        branch_id=payment.branch_id,
                        tenant_id=tenant_id,
                    )

                    from services.payment_service import PaymentService

                    PaymentService._post_supplier_fx_gain_loss(payment, purchase, tenant_id)

                supplier.apply_payment(Decimal(str(payment.amount_aed or 0)))

            flash(gettext("تم إنشاء سند الصرف بنجاح"), "success")
            return redirect(url_for("purchases.view", id=purchase_id))

        except Exception as e:
            flash(gettext(f"حدث خطأ: {str(e)}"), "danger")

    return render_template(
        "payments/create_receipt.html",
        purchase=purchase,
        supplier=supplier,
        suggested_amount=suggested_amount,
        is_payment=True,
    )


@payments_bp.route("/api/customer-balance/<int:customer_id>")
@login_required
@permission_required("manage_payments")
def api_customer_balance(customer_id):
    """رصيد العميل + فواتير غير المدفوعة - API موحد (نفس الاستجابة كـ customers/<id>/balance)."""
    customer = _ensure_customer_scope(customer_id)
    if not customer:
        return render_template("errors/403.html"), 403

    try:
        default_currency = resolve_default_currency()
    except Exception:
        default_currency = get_system_default_currency()
    unpaid_sales = _scoped_customer_unpaid_sales(customer.id)
    unpaid_sale_rows = []
    for sale in unpaid_sales:
        sale_rate = float(sale.exchange_rate or 1)
        balance_due_aed = float(sale.balance_due or 0)
        if (sale.currency or default_currency) != get_system_default_currency() and sale_rate > 0:
            balance_due_display = balance_due_aed / sale_rate
        else:
            balance_due_display = balance_due_aed
        unpaid_sale_rows.append(
            {
                "id": sale.id,
                "sale_number": sale.sale_number,
                "sale_date": (
                    sale.sale_date.strftime("%Y-%m-%d")
                    if getattr(sale.sale_date, "strftime", None)
                    else str(sale.sale_date)
                ),
                "total_amount": float(sale.total_amount),
                "balance_due": balance_due_display,
                "balance_due_aed": balance_due_aed,
                "currency": sale.currency or default_currency,
            }
        )
    return jsonify(
        {
            "balance_aed": _scoped_customer_balance(customer.id),
            "balance": _scoped_customer_balance(customer.id),
            "currency": default_currency,
            "unpaid_sales": unpaid_sale_rows,
        }
    )
