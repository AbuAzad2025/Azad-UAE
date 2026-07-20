from flask_babel import gettext
from flask import Blueprint, request, jsonify, flash
from flask_login import current_user, login_required
from services.whatsapp_service import WhatsAppService
from utils.decorators import admin_required, permission_required

whatsapp_bp = Blueprint("whatsapp", __name__, url_prefix="/whatsapp")


@whatsapp_bp.route("/send-invoice/<int:sale_id>", methods=["POST"])
@login_required
@permission_required("manage_sales")
def send_invoice(sale_id):
    from models import Sale
    from utils.tenanting import get_active_tenant_id

    tid = get_active_tenant_id(current_user)
    sale_query = Sale.query.filter_by(id=sale_id)
    if tid is not None:
        sale_query = sale_query.filter(Sale.tenant_id == tid)
    sale = sale_query.first_or_404()

    if not sale.customer or not sale.customer.phone:
        return jsonify({"success": False, "error": "Customer phone not available"})

    pdf_url = request.form.get("pdf_url")

    result = WhatsAppService.send_invoice(phone=sale.customer.phone, invoice_number=sale.sale_number, pdf_url=pdf_url)

    if result["success"]:
        flash(gettext("تم إرسال الفاتورة عبر واتساب بنجاح"), "success")
    else:
        from flask import current_app

        current_app.logger.error(f"WhatsApp send invoice failed: {result.get('error')}")
        from utils.error_messages import ErrorMessages

        flash(ErrorMessages.whatsapp_failed(), "danger")

    return jsonify(result)


@whatsapp_bp.route("/send-reminder/<int:customer_id>", methods=["POST"])
@login_required
@admin_required
def send_reminder(customer_id):
    from models import Customer
    from utils.tenanting import get_active_tenant_id

    tid = get_active_tenant_id(current_user)
    customer_query = Customer.query.filter_by(id=customer_id)
    if tid is not None:
        customer_query = customer_query.filter(Customer.tenant_id == tid)
    customer = customer_query.first_or_404()

    if not customer.phone:
        return jsonify({"success": False, "error": "Customer phone not available"})

    balance = float(customer.get_balance_aed())

    result = WhatsAppService.send_payment_reminder(
        phone=customer.phone, customer_name=customer.name, amount_due=balance
    )

    if result["success"]:
        flash(gettext("تم إرسال التذكير بنجاح"), "success")
    else:
        from flask import current_app

        current_app.logger.error(f"WhatsApp send reminder failed: {result.get('error')}")
        from utils.error_messages import ErrorMessages

        flash(ErrorMessages.whatsapp_failed(), "danger")

    return jsonify(result)


@whatsapp_bp.route("/test")
@login_required
@admin_required
def test_connection():
    if not WhatsAppService.is_enabled():
        return jsonify(
            {
                "success": False,
                "error": "WhatsApp not configured. Set WHATSAPP_API_KEY in .env",
            }
        )

    return jsonify({"success": True, "message": "WhatsApp is configured and ready"})
