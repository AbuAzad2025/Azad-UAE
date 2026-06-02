"""Email / log notifications for new online store orders."""
from __future__ import annotations

from flask import current_app, url_for

from models import TenantStore


class StoreNotificationService:
    @staticmethod
    def _safe_log_text(text: str) -> str:
        """Return ASCII-safe text to avoid console encoding crashes."""
        if text is None:
            return ''
        return str(text).encode('ascii', errors='replace').decode('ascii', errors='replace')

    @staticmethod
    def _order_summary(sale, store: TenantStore, lang: str = 'ar') -> str:
        customer = sale.customer
        lines = []
        for line in sale.lines:
            name = line.product.name if line.product else str(line.product_id)
            lines.append(f'  - {name} × {line.quantity}')
        pay = sale.checkout_payment_method or 'cod'
        if lang == 'en':
            return (
                f'New order {sale.sale_number}\n'
                f'Store: {store.title}\n'
                f'Customer: {customer.name if customer else "-"}\n'
                f'Phone: {getattr(customer, "phone", "") or "-"}\n'
                f'Payment: {pay}\n'
                f'Total: {sale.total_amount} {sale.currency}\n'
                f'Items:\n' + '\n'.join(lines)
            )
        return (
            f'طلب جديد {sale.sale_number}\n'
            f'المتجر: {store.title}\n'
            f'العميل: {customer.name if customer else "-"}\n'
            f'الهاتف: {getattr(customer, "phone", "") or "-"}\n'
            f'طريقة الدفع: {pay}\n'
            f'الإجمالي: {sale.total_amount} {sale.currency}\n'
            f'البنود:\n' + '\n'.join(lines)
        )

    @staticmethod
    def notify_new_order(sale, store: TenantStore):
        summary = StoreNotificationService._order_summary(sale, store)
        current_app.logger.info(
            'Store new order: %s',
            StoreNotificationService._safe_log_text(summary.replace('\n', ' | ')),
        )

        if not getattr(store, 'notify_email_on_order', True):
            return

        recipients = []
        email = (store.email or '').strip()
        if email and '@' in email:
            recipients.append(email)

        if not recipients:
            return

        if not current_app.config.get('MAIL_USERNAME') or not current_app.config.get('MAIL_PASSWORD'):
            current_app.logger.info('Store order email skipped — mail not configured.')
            return

        try:
            from flask_mail import Message
            from extensions import mail

            admin_url = None
            try:
                admin_url = url_for('store.admin_order_detail', order_id=sale.id, _external=True)
            except Exception:
                admin_url = f'/store/admin/orders/{sale.id}'

            msg = Message(
                subject=f'طلب متجر جديد — {sale.sale_number}',
                recipients=recipients,
                body=f'{summary}\n\nرابط الإدارة:\n{admin_url}',
            )
            mail.send(msg)
        except Exception as exc:
            current_app.logger.warning('Store order email failed: %s', exc)

    @staticmethod
    def whatsapp_admin_link(sale, store: TenantStore) -> str | None:
        if not getattr(store, 'notify_whatsapp_on_order', True):
            return None
        wa = (store.whatsapp or store.phone or '').strip()
        import re
        from urllib.parse import quote

        digits = re.sub(r'\D', '', wa)
        if not digits:
            return None
        text = StoreNotificationService._order_summary(sale, store, 'ar')
        return f'https://wa.me/{digits}?text={quote(text)}'
