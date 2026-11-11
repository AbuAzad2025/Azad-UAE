"""WhatsApp message generation for store provisional orders.

Builds an Arabic message containing:
- Order number and date
- Customer name
- Itemized product list with quantities, unit prices, and line totals
- Subtotal in transaction currency and tenant base currency
- Tenant contact info
- Payment instruction (Cash on Delivery / bank transfer)
- Approval instructions for the tenant
"""

from __future__ import annotations

import os
from typing import Any

from flask import current_app
from flask_babel import gettext

from models.store_provisional_order import StoreProvisionalOrder


class StoreWhatsAppService:
    """Build WhatsApp checkout messages for provisional orders."""

    @staticmethod
    def build_message(provisional: StoreProvisionalOrder, tenant, store) -> str:
        """Build the full WhatsApp message for a provisional order.

        Args:
            provisional: The StoreProvisionalOrder instance
            tenant: Tenant model instance
            store: TenantStore model instance

        Returns:
            A formatted Arabic WhatsApp message string.
        """
        lines = []

        # Header
        lines.append(gettext("طلب متجر إلكتروني جديد"))
        lines.append(gettext("رقم الطلب: {number}").format(number=provisional.provisional_number))
        lines.append(gettext("التاريخ: {date}").format(date=provisional.created_at.strftime("%Y-%m-%d %H:%M")))
        lines.append("")

        # Customer info
        if provisional.customer_name:
            lines.append(gettext("العميل: {name}").format(name=provisional.customer_name))
        if provisional.customer_phone:
            lines.append(gettext("الهاتف: {phone}").format(phone=provisional.customer_phone))
        if provisional.customer_email:
            lines.append(gettext("البريد الإلكتروني: {email}").format(email=provisional.customer_email))
        lines.append("")

        # Items
        lines.append(gettext("المنتجات:"))
        cart = provisional.cart_json or []
        for idx, item in enumerate(cart, start=1):
            product_name = item.get("product_name", f"منتج #{item.get('product_id', '')}")
            qty = item.get("quantity", 0)
            unit_price = item.get("unit_price", 0)
            line_total = item.get("line_total", 0)
            lines.append(
                f"{idx}. {product_name} × {qty} = {unit_price} {provisional.currency_code} (المجموع: {line_total} {provisional.currency_code})"
            )
        lines.append("")

        # Totals
        lines.append(
            gettext("المجموع الفرعي: {subtotal} {ccy}").format(
                subtotal=provisional.subtotal_tx_ccy, ccy=provisional.currency_code
            )
        )
        if provisional.subtotal_aed and provisional.subtotal_aed != provisional.subtotal_tx_ccy:
            lines.append(
                gettext("المجموع بالعملة الأساسية: {subtotal_aed} {base}").format(
                    subtotal_aed=provisional.subtotal_aed, base=getattr(tenant, "base_currency", "") or ""
                )
            )
        lines.append("")

        # Payment instruction
        lines.append(gettext("طريقة الدفع: الدفع عند الاستلام / تحويل بنكي"))
        lines.append(gettext("سيتم تأكيد الطلب بعد التواصل معكم."))
        lines.append("")

        # Tenant info
        if store and store.title:
            lines.append(gettext("من: {title}").format(title=store.title))
        if store and store.whatsapp:
            lines.append(gettext("للتواصل: {whatsapp}").format(whatsapp=store.whatsapp))
        elif store and store.phone:
            lines.append(gettext("للتواصل: {phone}").format(phone=store.phone))

        return "\n".join(lines)

    @staticmethod
    def whatsapp_url(phone: str, message: str) -> str:
        """Build a WhatsApp wa.me URL with the message pre-filled.

        Args:
            phone: Customer phone number (with country code, no '+').
            message: The message text.

        Returns:
            A wa.me URL that opens WhatsApp with the message ready to send.
        """
        import urllib.parse

        clean_phone = "".join(ch for ch in phone if ch.isdigit() or ch == "+")
        if clean_phone.startswith("+"):
            clean_phone = clean_phone[1:]
        encoded_message = urllib.parse.quote(message)
        return f"https://wa.me/{clean_phone}?text={encoded_message}"

    @staticmethod
    def generate_provisional_number(tenant_id: int) -> str:
        """Generate a unique provisional order number.

        Format: PRV-{tenant_id}-{YYYYMMDD}-{seq}
        """
        from datetime import UTC, datetime

        from extensions import db

        today = datetime.now(UTC).strftime("%Y%m%d")
        prefix = f"PRV-{tenant_id}-{today}"
        # Find the next sequence number for today
        last = (
            db.session.query(StoreProvisionalOrder)
            .filter_by(tenant_id=tenant_id)
            .filter(StoreProvisionalOrder.provisional_number.like(f"{prefix}-%"))
            .order_by(StoreProvisionalOrder.id.desc())
            .first()
        )
        seq = 1
        if last and last.provisional_number:
            try:
                seq = int(last.provisional_number.rsplit("-", 1)[-1]) + 1
            except (ValueError, IndexError):
                seq = 1
        return f"{prefix}-{seq:03d}"

    @staticmethod
    def send_message(phone: str, message: str) -> bool:
        """Send a WhatsApp message via configured provider.

        Tries in order:
        1. Twilio WhatsApp API (if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN are set)
        2. WhatsApp Business API (if WHATSAPP_API_URL and WHATSAPP_API_TOKEN are set)
        3. Falls back to False - caller can generate wa.me link instead.

        Args:
            phone: Customer phone number (with country code).
            message: The message text to send.

        Returns:
            True if message was sent successfully, False otherwise.
        """
        clean_phone = "".join(ch for ch in phone if ch.isdigit() or ch == "+")
        if clean_phone.startswith("+"):
            clean_phone = clean_phone[1:]

        # Option 1: Twilio WhatsApp API
        try:
            account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
            auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
            twilio_from = os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

            if account_sid and auth_token:
                from twilio.rest import Client

                client = Client(account_sid, auth_token)
                client.messages.create(
                    body=message,
                    from_=twilio_from,
                    to=f"whatsapp:{clean_phone}",
                )
                return True
        except Exception as exc:
            current_app.logger.debug(f"Twilio WhatsApp send failed: {exc}")

        # Option 2: WhatsApp Business API (direct HTTP)
        try:
            api_url = os.environ.get("WHATSAPP_API_URL")
            api_token = os.environ.get("WHATSAPP_API_TOKEN")

            if api_url and api_token:
                import requests

                payload: Any = {
                    "messaging_product": "whatsapp",
                    "to": clean_phone,
                    "type": "text",
                    "text": {"body": message},
                }
                headers = {
                    "Authorization": f"Bearer {api_token}",
                    "Content-Type": "application/json",
                }
                requests.post(api_url, json=payload, headers=headers, timeout=10)
                return True
        except Exception as exc:
            current_app.logger.debug(f"WhatsApp Business API send failed: {exc}")

        # Option 3: No API configured - caller should use wa.me link instead
        return False
