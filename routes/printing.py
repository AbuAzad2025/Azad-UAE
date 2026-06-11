"""
Printing Routes — Unified Professional Printing
طباعة احترافية مع دعم PDF ومعاينة وطباعة جماعية
"""
from datetime import datetime, timezone
from io import BytesIO

from flask import Blueprint, render_template, request, jsonify, send_file, url_for, flash, redirect, current_app
from flask_login import login_required, current_user
from extensions import db

from models import Purchase, Expense, PayrollTransaction, Cheque, Sale, Shipment
from models.print_history import PrintHistory
from models.invoice_settings import InvoiceSettings
from services.print_service import PrintService
from utils.decorators import permission_required
from utils.tenanting import tenant_get_or_404, get_active_tenant_id
from utils.branching import branch_scope_id

printing_bp = Blueprint('printing', __name__, url_prefix='/printing')

DOCUMENT_TEMPLATES = {
    'purchase': 'purchases/print.html',
    'expense': 'expenses/print.html',
    'payroll_slip': 'payroll/slip.html',
    'sale': 'invoices/modern.html',
    'cheque': 'printing/cheque.html',
    'packing_slip': 'printing/packing_slip.html',
}


@printing_bp.route('/purchase/<int:id>')
@login_required
@permission_required('manage_purchases')
def print_purchase(id):
    purchase = tenant_get_or_404(Purchase, id)
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None and purchase.branch_id != scoped_branch_id:
        return render_template('errors/403.html'), 403
    PrintService.audit_print(purchase.tenant_id, 'purchase', purchase.id, action='print')
    return PrintService.render_print(
        'purchases/print.html',
        {'purchase': purchase},
        tenant_id=purchase.tenant_id,
    )


@printing_bp.route('/purchase/<int:id>/pdf')
@login_required
@permission_required('manage_purchases')
def purchase_pdf(id):
    purchase = tenant_get_or_404(Purchase, id)
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None and purchase.branch_id != scoped_branch_id:
        return render_template('errors/403.html'), 403
    pdf = PrintService.render_pdf(
        'purchases/print.html',
        {'purchase': purchase},
        tenant_id=purchase.tenant_id,
        filename=f'purchase_{purchase.purchase_number}.pdf',
    )
    PrintService.audit_print(purchase.tenant_id, 'purchase', purchase.id, action='pdf_download')
    return send_file(
        BytesIO(pdf),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'purchase_{purchase.purchase_number}.pdf',
    )


@printing_bp.route('/expense/<int:id>')
@login_required
@permission_required('manage_expenses')
def print_expense(id):
    expense = tenant_get_or_404(Expense, id)
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None and expense.branch_id != scoped_branch_id:
        return render_template('errors/403.html'), 403
    PrintService.audit_print(expense.tenant_id, 'expense', expense.id, action='print')
    return PrintService.render_print(
        'expenses/print.html',
        {'expense': expense},
        tenant_id=expense.tenant_id,
    )


@printing_bp.route('/expense/<int:id>/pdf')
@login_required
@permission_required('manage_expenses')
def expense_pdf(id):
    expense = tenant_get_or_404(Expense, id)
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None and expense.branch_id != scoped_branch_id:
        return render_template('errors/403.html'), 403
    pdf = PrintService.render_pdf(
        'expenses/print.html',
        {'expense': expense},
        tenant_id=expense.tenant_id,
        filename=f'expense_{expense.expense_number}.pdf',
    )
    PrintService.audit_print(expense.tenant_id, 'expense', expense.id, action='pdf_download')
    return send_file(
        BytesIO(pdf),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'expense_{expense.expense_number}.pdf',
    )


@printing_bp.route('/payroll-slip/<int:id>')
@login_required
@permission_required('manage_payroll')
def salary_slip(id):
    tid = get_active_tenant_id(current_user)
    transaction = PayrollTransaction.query.filter_by(id=id)
    if tid is not None:
        transaction = transaction.filter(PayrollTransaction.tenant_id == tid)
    transaction = transaction.first_or_404()
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None and transaction.branch_id != scoped_branch_id:
        return render_template('errors/403.html'), 403
    PrintService.audit_print(tid, 'payroll_slip', id, action='print')
    return PrintService.render_print(
        'payroll/slip.html',
        {'slip': transaction},
        tenant_id=tid,
    )


@printing_bp.route('/payroll-slip/<int:id>/pdf')
@login_required
@permission_required('manage_payroll')
def payroll_slip_pdf(id):
    tid = get_active_tenant_id(current_user)
    transaction = PayrollTransaction.query.filter_by(id=id)
    if tid is not None:
        transaction = transaction.filter(PayrollTransaction.tenant_id == tid)
    transaction = transaction.first_or_404()
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None and transaction.branch_id != scoped_branch_id:
        return render_template('errors/403.html'), 403
    pdf = PrintService.render_pdf(
        'payroll/slip.html',
        {'slip': transaction},
        tenant_id=tid,
        filename=f'salary_slip_{id}.pdf',
    )
    PrintService.audit_print(tid, 'payroll_slip', id, action='pdf_download')
    return send_file(
        BytesIO(pdf),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'salary_slip_{id}.pdf',
    )


@printing_bp.route('/cheque/<int:id>')
@login_required
@permission_required('manage_payments')
def print_cheque(id):
    tid = get_active_tenant_id(current_user)
    cheque = Cheque.query.filter_by(id=id)
    if tid is not None:
        cheque = cheque.filter(Cheque.tenant_id == tid)
    cheque = cheque.first_or_404()
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None and cheque.branch_id != scoped_branch_id:
        return render_template('errors/403.html'), 403
    PrintService.audit_print(tid, 'cheque', id, action='print')
    return PrintService.render_print(
        'printing/cheque.html',
        {'cheque': cheque},
        tenant_id=tid,
    )


@printing_bp.route('/packing-slip/<int:sale_id>')
@login_required
@permission_required('manage_sales')
def packing_slip(sale_id):
    sale = tenant_get_or_404(Sale, sale_id)
    delivery = None
    try:
        from models import Shipment as ShipmentModel
        shipment = ShipmentModel.query.filter_by(sale_id=sale.id, tenant_id=sale.tenant_id).first()
    except Exception:
        shipment = None
    if not shipment:
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
        delivery = SimpleDelivery()
        delivery.number = sale.sale_number
        delivery.date = sale.sale_date
        delivery.address = sale.customer.address if sale.customer else ''
        delivery.customer_name = sale.customer.name if sale.customer else ''
        delivery.customer_phone = sale.customer.phone if sale.customer else ''
    else:
        delivery = shipment
    lines = sale.lines if hasattr(sale, 'lines') else []
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None and sale.branch_id != scoped_branch_id:
        return render_template('errors/403.html'), 403
    PrintService.audit_print(sale.tenant_id, 'packing_slip', sale_id, action='print')
    return PrintService.render_print(
        'printing/packing_slip.html',
        {'sale': sale, 'delivery': delivery, 'lines': lines, 'notes': None},
        tenant_id=sale.tenant_id,
    )


@printing_bp.route('/bulk-print', methods=['POST'])
@login_required
@permission_required('manage_sales')
def bulk_print():
    doc_ids = request.json.get('ids', [])
    doc_type = request.json.get('type', 'sale')
    tmpl = DOCUMENT_TEMPLATES.get(doc_type)
    if not tmpl:
        return jsonify({'error': f'Unknown document type: {doc_type}'}), 400
    tid = get_active_tenant_id(current_user)
    models_map = {
        'purchase': Purchase,
        'expense': Expense,
        'sale': Sale,
    }
    model_cls = models_map.get(doc_type)
    if not model_cls:
        return jsonify({'error': f'No model for type: {doc_type}'}), 400
    documents = []
    for doc_id in doc_ids:
        doc = model_cls.query.filter_by(id=doc_id, tenant_id=tid).first()
        if doc:
            documents.append({'type': doc_type, 'context': {doc_type: doc}})
            PrintService.audit_print(tid, f'{doc_type}_bulk', doc_id, action='bulk_print')
    html = PrintService.bulk_print_documents(documents, {doc_type: tmpl}, tid)
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
    tid = get_active_tenant_id(current_user)
    ctx = {}
    obj = None
    if doc_type == 'purchase':
        obj = Purchase.query.filter_by(id=doc_id, tenant_id=tid).first()
        ctx['purchase'] = obj
        tmpl = 'purchases/print.html'
    elif doc_type == 'expense':
        obj = Expense.query.filter_by(id=doc_id, tenant_id=tid).first()
        ctx['expense'] = obj
        tmpl = 'expenses/print.html'
    elif doc_type == 'cheque':
        obj = Cheque.query.filter_by(id=doc_id, tenant_id=tid).first()
        ctx['cheque'] = obj
        tmpl = 'printing/cheque.html'
    else:
        return jsonify({'error': 'Unsupported type'}), 400
    if not obj:
        return jsonify({'error': 'Document not found'}), 404
    html = PrintService.render_print(tmpl, ctx, tenant_id=tid)
    return jsonify({'html': html})


@printing_bp.route('/api/print-history', methods=['GET'])
@login_required
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
@permission_required('admin')
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
