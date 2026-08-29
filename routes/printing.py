"""
Printing Routes — Unified Professional Printing
طباعة احترافية مع دعم PDF ومعاينة وطباعة جماعية
"""

from io import BytesIO
from typing import Any, cast

from flask import (
    Blueprint,
    abort,
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

from extensions import db
from models.invoice_settings import InvoiceSettings
from services.print_service import PrintService
from utils.api_response import error_response, success_response
from utils.branching import branch_scope_id
from utils.db_safety import atomic_transaction
from utils.decorators import admin_required, permission_required
from utils.tenanting import get_active_tenant_id

printing_bp = Blueprint("printing", __name__, url_prefix="/printing")


def _normalize_doc_type(doc_type):
    """Normalize URL-friendly hyphenated doc types to registry keys (underscores)."""
    return doc_type.replace("-", "_")


def _check_branch_scope(doc):
    """Check if the document's branch_id is within the user's branch scope."""
    scoped_branch_id = branch_scope_id()
    return bool(scoped_branch_id is not None and getattr(doc, "branch_id", None) != scoped_branch_id)


def _get_filename(entry, doc, doc_type, record_id):
    """Build a meaningful PDF filename from the registry entry and document."""
    attr = entry.get("filename_attr")
    if attr:
        val = getattr(doc, attr, None)
        if val:
            return f"{entry.get('filename_prefix', doc_type)}_{val}.pdf"
    return f"{entry.get('filename_prefix', doc_type)}_{record_id}.pdf"


@printing_bp.route("/<doc_type>/<int:id>")
@login_required
def print_document(doc_type, **kwargs):
    """Generic print handler — dispatches to the correct template via PRINTABLE_DOCUMENTS registry."""
    record_id = kwargs.pop("id")
    doc_type = _normalize_doc_type(doc_type)
    registry = cast("dict[str, Any]", PrintService.PRINTABLE_DOCUMENTS)
    entry = registry.get(doc_type)
    if not entry:
        current_app.logger.warning("Unknown doc_type requested for print: %s", doc_type)
        return render_template("errors/404.html"), 404

    if not current_user.has_permission(entry["permission"]):
        flash(gettext("ليس لديك صلاحية للوصول لهذه الصفحة"), "danger")
        return render_template("errors/403.html"), 403

    tid = get_active_tenant_id(current_user)
    model_cls = PrintService._get_model(entry["model"])

    if doc_type == "packing_slip":
        return _handle_packing_slip(record_id, tid)

    doc = PrintService.get_document(model_cls, record_id, tid)
    if doc is None:
        abort(404)

    if _check_branch_scope(doc):
        return render_template("errors/403.html"), 403

    eff_tid = tid or getattr(doc, "tenant_id", None)
    PrintService.create_snapshot(eff_tid, doc_type, record_id, reason="print", document=doc)
    PrintService.audit_print(eff_tid, doc_type, record_id, action="print")

    template = entry["template"]
    requested = (request.args.get("template") or "").strip().lower()
    if template is None:
        template = PrintService.resolve_template(doc_type, tenant_id=eff_tid, requested_template=requested)

    current_template = requested
    if not current_template:
        s = InvoiceSettings.get_active(eff_tid)
        current_template = s.active_template if s and s.active_template else "modern"

    return PrintService.render_print(
        template,
        {
            entry["context_key"]: doc,
            "available_templates": sorted(
                PrintService.INVOICE_TEMPLATES if doc_type == "sale" else PrintService.RECEIPT_TEMPLATES
            ),
            "current_template": current_template,
        },
        tenant_id=eff_tid,
    )


@printing_bp.route("/<doc_type>/<int:id>/pdf")
@login_required
def print_document_pdf(doc_type, **kwargs):
    """Generic PDF handler — renders a document as PDF download via the PRINTABLE_DOCUMENTS registry."""
    record_id = kwargs.pop("id")
    doc_type = _normalize_doc_type(doc_type)
    registry = cast("dict[str, Any]", PrintService.PRINTABLE_DOCUMENTS)
    entry = registry.get(doc_type)
    if not entry:
        current_app.logger.warning("Unknown doc_type requested for PDF: %s", doc_type)
        return render_template("errors/404.html"), 404

    if not current_user.has_permission(entry["permission"]):
        flash(gettext("ليس لديك صلاحية للوصول لهذه الصفحة"), "danger")
        return render_template("errors/403.html"), 403

    tid = get_active_tenant_id(current_user)
    model_cls = PrintService._get_model(entry["model"])

    if doc_type == "packing_slip":
        return _handle_packing_slip_pdf(record_id, tid)

    doc = PrintService.get_document(model_cls, record_id, tid)
    if doc is None:
        abort(404)

    if _check_branch_scope(doc):
        return render_template("errors/403.html"), 403

    eff_tid = tid or getattr(doc, "tenant_id", None)
    filename = _get_filename(entry, doc, doc_type, record_id)
    template = entry["template"]
    if template is None:
        requested = (request.args.get("template") or "").strip().lower()
        template = PrintService.resolve_template(doc_type, tenant_id=eff_tid, requested_template=requested)

    pdf = PrintService.render_pdf(
        template,
        {entry["context_key"]: doc},
        tenant_id=eff_tid,
        filename=filename,
    )
    PrintService.create_snapshot(eff_tid, doc_type, record_id, reason="pdf_download", document=doc)
    PrintService.audit_print(eff_tid, doc_type, record_id, action="pdf_download")

    return send_file(
        BytesIO(pdf),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


def _handle_packing_slip(sale_id, tid):
    """Build packing slip context (sale + delivery info) and render."""
    from models import Sale

    sale = PrintService.get_document(Sale, sale_id, tid)
    if sale is None:
        abort(404)

    if _check_branch_scope(sale):
        return render_template("errors/403.html"), 403

    delivery = _resolve_delivery(sale, tid)
    lines = sale.lines if hasattr(sale, "lines") else []

    eff_tid = tid or getattr(sale, "tenant_id", None)
    PrintService.create_snapshot(eff_tid, "packing_slip", sale_id, reason="print", document=sale)
    PrintService.audit_print(eff_tid, "packing_slip", sale_id, action="print")

    return PrintService.render_print(
        "printing/packing_slip.html",
        {"sale": sale, "delivery": delivery, "lines": lines, "notes": None},
        tenant_id=eff_tid,
    )


def _handle_packing_slip_pdf(sale_id, tid):
    """Render packing slip as PDF."""
    from models import Sale

    sale = PrintService.get_document(Sale, sale_id, tid)
    if sale is None:
        abort(404)

    if _check_branch_scope(sale):
        return render_template("errors/403.html"), 403

    delivery = _resolve_delivery(sale, tid)
    lines = sale.lines if hasattr(sale, "lines") else []
    filename = f"packing_slip_{sale.sale_number}.pdf"
    eff_tid = tid or getattr(sale, "tenant_id", None)

    pdf = PrintService.render_pdf(
        "printing/packing_slip.html",
        {"sale": sale, "delivery": delivery, "lines": lines, "notes": None},
        tenant_id=eff_tid,
        filename=filename,
    )
    PrintService.create_snapshot(eff_tid, "packing_slip", sale_id, reason="pdf_download", document=sale)
    PrintService.audit_print(eff_tid, "packing_slip", sale_id, action="pdf_download")

    return send_file(
        BytesIO(pdf),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


def _resolve_delivery(sale, tid):
    """Resolve delivery info from shipment or fall back to sale/customer data."""
    shipment = None
    try:
        shipment = PrintService.get_shipment_for_sale(sale.id, tid)
    except Exception:
        shipment = None
    if shipment:
        return shipment

    class SimpleDelivery:
        number = None
        date = None
        method = None
        status = None
        shipping_method = None
        tracking_number = None
        address = None
        customer_name = None
        customer_phone = None

    d = SimpleDelivery()
    d.number = sale.sale_number
    d.date = sale.sale_date
    d.address = sale.customer.address if sale.customer else ""
    d.customer_name = sale.customer.name if sale.customer else ""
    d.customer_phone = sale.customer.phone if sale.customer else ""
    return d


@printing_bp.route("/bulk-print", methods=["POST"])
@login_required
@permission_required("manage_sales")
def bulk_print():
    doc_ids = request.json.get("ids", [])
    doc_type = request.json.get("type", "sale")
    doc_type = _normalize_doc_type(doc_type)
    registry = cast("dict[str, Any]", PrintService.PRINTABLE_DOCUMENTS)
    entry = registry.get(doc_type)
    if not entry:
        return error_response(message=f"Unknown document type: {doc_type}", status_code=400)

    tid = get_active_tenant_id(current_user)
    model_cls = PrintService._get_model(entry["model"])

    documents = []
    for doc_id in doc_ids:
        doc = PrintService.get_tenant_document(model_cls, doc_id, tid)
        if doc:
            eff_tid = tid or getattr(doc, "tenant_id", None)
            documents.append({"type": doc_type, "context": {entry["context_key"]: doc}})
            PrintService.create_snapshot(eff_tid, doc_type, doc_id, reason="bulk_print", document=doc)
            PrintService.audit_print(eff_tid, f"{doc_type}_bulk", doc_id, action="bulk_print")

    template_map = {}
    for d in documents:
        dt = d.get("type", doc_type)
        ent = registry.get(dt)
        tmpl = ent["template"] if ent else None
        if tmpl is None:
            tmpl = PrintService.resolve_template(dt, tenant_id=tid)
        template_map[dt] = tmpl
    html = PrintService.bulk_print_documents(documents, template_map, tid)
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}


@printing_bp.route("/history")
@login_required
@permission_required("view_reports")
def print_history():
    tid = get_active_tenant_id(current_user)
    page = request.args.get("page", 1, type=int)
    pagination = PrintService.history_query(tid).paginate(page=page, per_page=50, error_out=False)
    return render_template("printing/history.html", history=pagination.items, pagination=pagination)


@printing_bp.route("/api/preview", methods=["POST"])
@login_required
@permission_required("view_reports")
def print_preview_api():
    doc_type = request.json.get("type")
    doc_id = request.json.get("id")
    if not doc_type or not doc_id:
        return error_response(message="Missing type or id", status_code=400)

    doc_type = _normalize_doc_type(doc_type)
    registry = cast("dict[str, Any]", PrintService.PRINTABLE_DOCUMENTS)
    entry = registry.get(doc_type)
    if not entry:
        return error_response(message=f"Unsupported type: {doc_type}", status_code=400)

    tid = get_active_tenant_id(current_user)
    model_cls = PrintService._get_model(entry["model"])

    obj = PrintService.get_tenant_document(model_cls, doc_id, tid)
    if not obj:
        return error_response(message="Document not found", status_code=404)

    html = PrintService.render_print(entry["template"], {entry["context_key"]: obj}, tenant_id=tid)
    return success_response(data={"html": html})


@printing_bp.route("/api/print-history", methods=["GET"])
@login_required
@permission_required("view_reports")
def api_print_history():
    tid = get_active_tenant_id(current_user)
    limit = request.args.get("limit", 20, type=int)
    records = PrintService.list_recent_history(tid, limit=limit)
    return success_response(
        data=[
            {
                "id": r.id,
                "document_type": r.document_type,
                "document_id": r.document_id,
                "action": r.action,
                "created_at": (r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else None),
                "user_name": r.user.full_name if r.user else "—",
            }
            for r in records
        ]
    )


# ═════════════════════════════════════════════════════════════════════
# CONSOLIDATED PRINT ROUTES — Unified entry points for all document printing
# ═════════════════════════════════════════════════════════════════════

@printing_bp.route("/customer-statement/<int:id>")
@login_required
@permission_required("manage_customers")
def print_customer_statement(id):
    """Print customer statement (delegates to unified print handler)."""
    return print_document("customer_statement", id=id)


@printing_bp.route("/supplier-statement/<int:id>")
@login_required
@permission_required("manage_suppliers")
def print_supplier_statement(id):
    """Print supplier statement (delegates to unified print handler)."""
    return print_document("supplier_statement", id=id)


@printing_bp.route("/expense/<int:id>")
@login_required
@permission_required("manage_expenses")
def print_expense(id):
    """Print expense voucher (delegates to unified print handler)."""
    return print_document("expense", id=id)


@printing_bp.route("/advanced-ledger/professional-printing")
@login_required
@permission_required("view_ledger")
def print_advanced_ledger():
    """Print advanced ledger trial balance (professional printing)."""
    tid = get_active_tenant_id(current_user)

    from models import GLAccount
    from models.invoice_settings import InvoiceSettings
    from utils.tenant_branding import get_print_header_context
    from datetime import date, timedelta

    accounts = GLAccount.query.filter_by(tenant_id=get_active_tenant_id(current_user), is_active=True, is_header=False).limit(20).all()

    trial_balance_data = []
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
    settings = InvoiceSettings.get_active(user=current_user)

    return PrintService.render_print(
        "ledger/professional_printing.html",
        {
            "trial_balance_data": [
                {
                    "account": item["account"],
                    "debit": item["debit"],
                    "credit": item["credit"],
                }
                for item in [
                    {"account": a, "debit": d, "credit": c}
                    for a, d, c in zip(
                        [a for a in accounts],
                        [a.get_balance() if a.get_balance() > 0 else 0 for a in accounts],
                        [abs(a.get_balance()) if a.get_balance() < 0 else 0 for a in accounts]
                    )
                ]
            ],
            "total_debit": sum(a.get_balance() for a in accounts if a.get_balance() > 0),
            "total_credit": sum(abs(a.get_balance()) for a in accounts if a.get_balance() < 0),
            "date_from": date.today() - timedelta(days=30),
            "date_to": date.today(),
            "print_branding": get_print_header_context(),
            "settings": InvoiceSettings.get_active(user=current_user),
        },
        tenant_id=get_active_tenant_id(current_user),
    )


# ═════════════════════════════════════════════════════════════════════
# SETTINGS
# ════════════════════════════════════════════════════════════════════
@login_required
@admin_required
@printing_bp.route("/settings", methods=["GET", "POST"])
def print_settings():
    tid = get_active_tenant_id(current_user)
    settings = InvoiceSettings.get_active(tid)

    if request.method == "POST":
        with atomic_transaction("print_settings"):
            settings.paper_size = request.form.get("paper_size", "A4")
            settings.orientation = request.form.get("orientation", "portrait")
            settings.active_template = request.form.get("active_template", "modern")
            settings.header_color = request.form.get("header_color", "#667eea")
            settings.accent_color = request.form.get("accent_color", "#764ba2")
            settings.show_logo = request.form.get("show_logo") == "on"
            settings.enable_qr_code = request.form.get("enable_qr_code") == "on"
            settings.enable_watermark = request.form.get("enable_watermark") == "on"
            settings.show_terms = request.form.get("show_terms") == "on"
            db.session.flush()
            flash(gettext("تم حفظ إعدادات الطباعة"), "success")
            return redirect(url_for("printing.print_settings"))

    return render_template("printing/settings.html", settings=settings)
