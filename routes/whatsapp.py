from flask import Blueprint, request, jsonify, flash, redirect, url_for
from flask_login import login_required
from services.whatsapp_service import WhatsAppService
from utils.decorators import admin_required, permission_required

whatsapp_bp = Blueprint('whatsapp', __name__, url_prefix='/whatsapp')


@whatsapp_bp.route('/send-invoice/<int:sale_id>', methods=['POST'])
@login_required
@permission_required('manage_sales')
def send_invoice(sale_id):
    from models import Sale
    
    sale = Sale.query.get_or_404(sale_id)
    
    if not sale.customer or not sale.customer.phone:
        return jsonify({'success': False, 'error': 'Customer phone not available'})
    
    pdf_url = request.form.get('pdf_url')
    
    result = WhatsAppService.send_invoice(
        phone=sale.customer.phone,
        invoice_number=sale.sale_number,
        pdf_url=pdf_url
    )
    
    if result['success']:
        flash('تم إرسال الفاتورة عبر واتساب بنجاح', 'success')
    else:
        from flask import current_app
        current_app.logger.error(f"WhatsApp send invoice failed: {result.get('error')}")
        from utils.error_messages import ErrorMessages
        flash(ErrorMessages.whatsapp_failed(), 'danger')
    
    return jsonify(result)


@whatsapp_bp.route('/send-reminder/<int:customer_id>', methods=['POST'])
@login_required
@admin_required
def send_reminder(customer_id):
    from models import Customer
    
    customer = Customer.query.get_or_404(customer_id)
    
    if not customer.phone:
        return jsonify({'success': False, 'error': 'Customer phone not available'})
    
    balance = float(customer.get_balance_aed())
    
    result = WhatsAppService.send_payment_reminder(
        phone=customer.phone,
        customer_name=customer.name,
        amount_due=balance
    )
    
    if result['success']:
        flash('تم إرسال التذكير بنجاح', 'success')
    else:
        from flask import current_app
        current_app.logger.error(f"WhatsApp send reminder failed: {result.get('error')}")
        from utils.error_messages import ErrorMessages
        flash(ErrorMessages.whatsapp_failed(), 'danger')
    
    return jsonify(result)


@whatsapp_bp.route('/test')
@login_required
@admin_required
def test_connection():
    if not WhatsAppService.is_enabled():
        return jsonify({
            'success': False,
            'error': 'WhatsApp not configured. Set WHATSAPP_API_KEY in .env'
        })
    
    return jsonify({
        'success': True,
        'message': 'WhatsApp is configured and ready'
    })

