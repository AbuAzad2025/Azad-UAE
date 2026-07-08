"""
Printing Routes — Unified Professional Printing
طباعة احترافية مع دعم PDF ومعاينة وطباعة جماعية
"""
from datetime import datetime, timezone
from io import BytesIO

from flask import Blueprint, render_template, request, jsonify, send_file, url_for, flash, redirect, current_app
from flask_login import login_required, current_user
from utils.decorators import admin_required
from extensions import db

from models.print_history import PrintHistory
from models.invoice_settings import InvoiceSettings
from services.print_service import PrintService
from utils.decorators import permission_required
from utils.tenanting import tenant_get_or_404, get_active_tenant_id
from utils.branching import branch_scope_id

printing_bp = Blueprint('printing', __name__, url_prefix='/printing')


def _normalize_doc_type(doc_type):
    """Normalize URL-friendly hyphenated doc types to registry keys (underscores)."""
    return doc_type.replace('-', '_')


def _check_branch_scope(doc):
    """Check if the document's branch_id is within the user's branch scope."""
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None and getattr(doc, 'branch_id', None) != scoped_branch_id:
        return True
    return False


def _get_filename(entry, doc, doc_type, id):
    """Build a meaningful PDF filename from the registry entry and document."""
    attr = entry.get('filename_attr')
    if attr:
        val = getattr(doc, attr, None)
        if val:
            return f"{entry.get('filename_prefix', doc_type)}_{val}.pdf"
    return f"{entry.get('filename_prefix', doc_type)}_{id}.pdf"


@printing_bp.route('/<doc_type>/<int:id>')
@login_required
def print_document(doc_type, id):
    """Generic print handler — dispatches to the correct template via PRINTABLE_DOCUMENTS registry."""
    doc_type = _normalize_doc_type(doc_type)
    entry = PrintService.PRINTABLE_DOCUMENTS.get(doc_type)
    if not entry:
        current_app.logger.warning("Unknown doc_type requested for print: %s", doc_type)
        return render_template('errors/404.html'), 404

    if not current_user.has_permission(entry['permission']):
        flash('ليس لديك صلاحية للوصول لهذه الصفحة', 'danger')
        return render_template('errors/403.html'), 403

    tid = get_active_tenant_id(current_user)
    model_cls = PrintService._get_model(entry['model'])

    if doc_type == 'packing_slip':
        return _handle_packing_slip(id, tid)

    result = model_cls.query.filter_by(id=id)
    if tid is not None:
        result = result.filter(model_cls.tenant_id == tid)
    doc = result.first_or_404()

    if _check_branch_scope(doc):
        return render_template('errors/403.html'), 403

    PrintService.create_snapshot(tid, doc_type, id, reason='print', document=doc)
    PrintService.audit_print(tid, doc_type, id, action='print')

    return PrintService.render_print(
        entry['template'],
        {entry['context_key']: doc},
        tenant_id=tid,
    )


@printing_bp.route('/<doc_type>/<int:id>/pdf')
@login_required
def print_document_pdf(doc_type, id):
    """Generic PDF handler — renders a document as PDF download via the PRINTABLE_DOCUMENTS registry."""
    doc_type = _normalize_doc_type(doc_type)
    entry = PrintService.PRINTABLE_DOCUMENTS.get(doc_type)
    if not entry:
        current_app.logger.warning("Unknown doc_type requested for PDF: %s", doc_type)
        return render_template('errors/404.html'), 404

    if not current_user.has_permission(entry['permission']):
        flash('ليس لديك صلاحية للوصول لهذه الصفحة', 'danger')
        return render_template('errors/403.html'), 403

    tid = get_active_tenant_id(current_user)
    model_cls = PrintService._get_model(entry['model'])

    if doc_type == 'packing_slip':
        return _handle_packing_slip_pdf(id, tid)

    result = model_cls.query.filter_by(id=id)
    if tid is not None:
        result = result.filter(model_cls.tenant_id == tid)
    doc = result.first_or_404()

    if _check_branch_scope(doc):
        return render_template('errors/403.html'), 403

    filename = _get_filename(entry, doc, doc_type, id)
    pdf = PrintService.render_pdf(
        entry['template'],
        {entry['context_key']: doc},
        tenant_id=tid,
        filename=filename,
    )
    PrintService.create_snapshot(tid, doc_type, id, reason='pdf_download', document=doc)
    PrintService.audit_print(tid, doc_type, id, action='pdf_download')

    return send_file(
        BytesIO(pdf),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename,
    )


def _handle_packing_slip(sale_id, tid):
    """Build packing slip context (sale + delivery info) and render."""
    from models import Sale
    sale = Sale.query.filter_by(id=sale_id)
    if tid is not None:
        sale = sale.filter(Sale.tenant_id == tid)
    sale = sale.first_or_404()

    if _check_branch_scope(sale):
        return render_template('errors/403.html'), 403

    delivery = _resolve_delivery(sale, tid)
    lines = sale.lines if hasattr(sale, 'lines') else []

    PrintService.create_snapshot(tid, 'packing_slip', sale_id, reason='print', document=sale)
    PrintService.audit_print(tid, 'packing_slip', sale_id, action='print')

    return PrintService.render_print(
        'printing/packing_slip.html',
        {'sale': sale, 'delivery': delivery, 'lines': lines, 'notes': None},
        tenant_id=tid,
    )


def _handle_packing_slip_pdf(sale_id, tid):
    """Render packing slip as PDF."""
    from models import Sale
    sale = Sale.query.filter_by(id=sale_id)
    if tid is not None:
        sale = sale.filter(Sale.tenant_id == tid)
    sale = sale.first_or_404()

    if _check_branch_scope(sale):
        return render_template('errors/403.html'), 403

    delivery = _resolve_delivery(sale, tid)
    lines = sale.lines if hasattr(sale, 'lines') else []
    filename = f'packing_slip_{sale.sale_number}.pdf'

    pdf = PrintService.render_pdf(
        'printing/packing_slip.html',
        {'sale': sale, 'delivery': delivery, 'lines': lines, 'notes': None},
        tenant_id=tid,
        filename=filename,
    )
    PrintService.create_snapshot(tid, 'packing_slip', sale_id, reason='pdf_download', document=sale)
    PrintService.audit_print(tid, 'packing_slip', sale_id, action='pdf_download')

    return send_file(
        BytesIO(pdf),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename,
    )


def _resolve_delivery(sale, tid):
    """Resolve delivery info from shipment or fall back to sale/customer data."""
    shipment = None
    try:
        from models import Shipment
        shipment = Shipment.query.filter_by(sale_id=sale.id, tenant_id=tid).first()
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
    d.address = sale.customer.address if sale.customer else ''
    d.customer_name = sale.customer.name if sale.customer else ''
    d.customer_phone = sale.customer.phone if sale.customer else ''
    return d


@printing_bp.route('/bulk-print', methods=['POST'])
@login_required
@permission_required('manage_sales')
def bulk_print():
    doc_ids = request.json.get('ids', [])
    doc_type = request.json.get('type', 'sale')
    doc_type = _normalize_doc_type(doc_type)
    entry = PrintService.PRINTABLE_DOCUMENTS.get(doc_type)
    if not entry:
        return jsonify({'error': f'Unknown document type: {doc_type}'}), 400

    tid = get_active_tenant_id(current_user)
    model_cls = PrintService._get_model(entry['model'])

    documents = []
    for doc_id in doc_ids:
        doc = model_cls.query.filter_by(id=doc_id, tenant_id=tid).first()
        if doc:
            documents.append({'type': doc_type, 'context': {entry['context_key']: doc}})
            PrintService.create_snapshot(tid, doc_type, doc_id, reason='bulk_print', document=doc)
            PrintService.audit_print(tid, f'{doc_type}_bulk', doc_id, action='bulk_print')

    html = PrintService.bulk_print_documents(documents, {doc_type: entry['template']}, tid)
    return html, 200, {'Content-Type': 'text/html; charset=utf-8'}


@printing_bp.route('/history')
@login_required
@permission_required('view_reports')
def print_history():
    tid = get_active_tenant_id(current_user)
    page = request.args.get('page', 1, type=int)
    query = PrintHistory.query.filter_by(tenant_id=tid).order_by(PrintHistory.created_at.desc())
    pagination = query.paginate(page=page, per_page=50, error_out=False)
    return render_template('printing/history.html', history=pagination.items, pagination=pagination)


@printing_bp.route('/api/preview', methods=['POST'])
@login_required
@permission_required('view_reports')
def print_preview_api():
    doc_type = request.json.get('type')
    doc_id = request.json.get('id')
    if not doc_type or not doc_id:
        return jsonify({'error': 'Missing type or id'}), 400

    doc_type = _normalize_doc_type(doc_type)
    entry = PrintService.PRINTABLE_DOCUMENTS.get(doc_type)
    if not entry:
        return jsonify({'error': f'Unsupported type: {doc_type}'}), 400

    tid = get_active_tenant_id(current_user)
    model_cls = PrintService._get_model(entry['model'])

    obj = model_cls.query.filter_by(id=doc_id, tenant_id=tid).first()
    if not obj:
        return jsonify({'error': 'Document not found'}), 404

    html = PrintService.render_print(entry['template'], {entry['context_key']: obj}, tenant_id=tid)
    return jsonify({'html': html})


@printing_bp.route('/api/print-history', methods=['GET'])
@login_required
@permission_required('view_reports')
def api_print_history():
    tid = get_active_tenant_id(current_user)
    limit = request.args.get('limit', 20, type=int)
    records = PrintHistory.query.filter_by(tenant_id=tid).order_by(PrintHistory.created_at.desc()).limit(limit).all()
    return jsonify([{
        'id': r.id,
        'document_type': r.document_type,
        'document_id': r.document_id,
        'action': r.action,
        'created_at': r.created_at.strftime('%Y-%m-%d %H:%M:%S') if r.created_at else None,
        'user_name': r.user.full_name if r.user else '—',
    } for r in records])


@printing_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def print_settings():
    tid = get_active_tenant_id(current_user)
    settings = InvoiceSettings.get_active(tid)

    if request.method == 'POST':
        settings.paper_size = request.form.get('paper_size', 'A4')
        settings.orientation = request.form.get('orientation', 'portrait')
        settings.active_template = request.form.get('active_template', 'modern')
        settings.header_color = request.form.get('header_color', '#667eea')
        settings.accent_color = request.form.get('accent_color', '#764ba2')
        settings.show_logo = request.form.get('show_logo') == 'on'
        settings.enable_qr_code = request.form.get('enable_qr_code') == 'on'
        settings.enable_watermark = request.form.get('enable_watermark') == 'on'
        settings.show_terms = request.form.get('show_terms') == 'on'
        db.session.commit()
        flash('تم حفظ إعدادات الطباعة', 'success')
        return redirect(url_for('printing.print_settings'))

    return render_template('printing/settings.html', settings=settings)
