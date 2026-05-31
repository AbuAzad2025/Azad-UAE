"""Online store order lifecycle — confirm, cancel, fulfillment."""
from __future__ import annotations

from decimal import Decimal

from flask import current_app

from extensions import db
from models import Sale
from services.sale_service import SaleService
from services.stock_service import StockService
from utils.constants import normalize_payment_method_code

STATUS_LABELS_AR = {
    'pending': 'بانتظار التأكيد',
    'confirmed': 'مؤكد',
    'cancelled': 'ملغى',
}

STATUS_LABELS_EN = {
    'pending': 'Pending',
    'confirmed': 'Confirmed',
    'cancelled': 'Cancelled',
}

CHECKOUT_PAYMENT_MAP = {
    'cod': 'cash',
    'bank_transfer': 'bank_transfer',
    'card': 'card',
    'e_wallet': 'e_wallet',
}


class StoreOrderService:
    STORE_ORDER_STATUSES = ('pending', 'confirmed', 'cancelled')

    @staticmethod
    def status_label(status: str, lang: str = 'ar') -> str:
        labels = STATUS_LABELS_EN if lang == 'en' else STATUS_LABELS_AR
        return labels.get(status or '', status or '—')

    @staticmethod
    def is_online_order(sale: Sale) -> bool:
        return getattr(sale, 'source', None) == 'online_store'

    @staticmethod
    def is_fulfilled(sale: Sale) -> bool:
        return SaleService.has_inventory_posted(sale)

    @staticmethod
    def get_tenant_order(tenant_id: int, order_id: int) -> Sale | None:
        return Sale.query.filter_by(
            id=int(order_id),
            tenant_id=int(tenant_id),
            source='online_store',
        ).first()

    @staticmethod
    def list_for_customer(tenant_id: int, customer_id: int, limit: int = 50):
        return (
            Sale.query.filter_by(
                tenant_id=int(tenant_id),
                customer_id=int(customer_id),
                source='online_store',
            )
            .order_by(Sale.sale_date.desc())
            .limit(limit)
            .all()
        )

    @staticmethod
    def order_counts(tenant_id: int) -> dict:
        base = Sale.query.filter_by(tenant_id=int(tenant_id), source='online_store')
        return {
            'pending': base.filter_by(status='pending').count(),
            'confirmed': base.filter_by(status='confirmed').count(),
            'cancelled': base.filter_by(status='cancelled').count(),
            'total': base.count(),
        }

    @staticmethod
    def confirm_order(sale: Sale, *, mark_paid: bool = False) -> Sale:
        if not StoreOrderService.is_online_order(sale):
            raise ValueError('هذا ليس طلب متجر إلكتروني.')
        if sale.status == 'cancelled':
            raise ValueError('لا يمكن تأكيد طلب ملغى.')
        if sale.status == 'confirmed' and StoreOrderService.is_fulfilled(sale):
            raise ValueError('الطلب مؤكد مسبقاً.')

        if not StoreOrderService.is_fulfilled(sale):
            SaleService.fulfill_sale(sale)

        sale.status = 'confirmed'

        if mark_paid and (sale.payment_status or 'unpaid') != 'paid':
            checkout_code = (sale.checkout_payment_method or 'cod').strip().lower()
            internal_method = CHECKOUT_PAYMENT_MAP.get(
                checkout_code,
                normalize_payment_method_code(checkout_code),
            )
            if internal_method == 'cod':
                internal_method = 'cash'
            SaleService.create_payment_for_sale(
                sale=sale,
                amount=sale.total_amount,
                payment_method=internal_method,
                currency=sale.currency,
                exchange_rate=sale.exchange_rate,
                notes='دفع طلب متجر — تأكيد من لوحة المتجر',
            )
            sale.recalculate_payment_status()

        db.session.commit()
        current_app.logger.info('Store order confirmed: %s', sale.sale_number)
        return sale

    @staticmethod
    def cancel_order(sale: Sale) -> Sale:
        if not StoreOrderService.is_online_order(sale):
            raise ValueError('هذا ليس طلب متجر إلكتروني.')
        if sale.status == 'cancelled':
            raise ValueError('الطلب ملغى بالفعل.')
        if sale.status == 'confirmed' or StoreOrderService.is_fulfilled(sale):
            coupon_code = sale.coupon_code
            SaleService.cancel_sale(sale)
            if coupon_code:
                from services.store_coupon_service import StoreCouponService
                StoreCouponService.release_use(coupon_code, sale.tenant_id)
                db.session.commit()
            return sale

        sale.status = 'cancelled'
        if sale.coupon_code:
            from services.store_coupon_service import StoreCouponService
            StoreCouponService.release_use(sale.coupon_code, sale.tenant_id)
        db.session.commit()
        current_app.logger.info('Store order cancelled (unfulfilled): %s', sale.sale_number)
        return sale

    @staticmethod
    def validate_stock_for_order(sale: Sale) -> list[str]:
        """Return list of product names with insufficient stock (empty if OK)."""
        issues = []
        warehouse_id = sale.warehouse_id
        for line in sale.lines:
            available, msg = StockService.check_availability_in_warehouse(
                line.product_id, line.quantity, warehouse_id
            )
            if not available:
                name = line.product.name if line.product else str(line.product_id)
                issues.append(f'{name}: {msg}')
        return issues
