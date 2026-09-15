"""Online store order lifecycle — confirm, cancel, fulfillment."""

from __future__ import annotations

from flask import current_app
from flask_babel import gettext

from extensions import db
from models import Sale
from services.sale_service import SaleService
from services.stock_service import StockService
from utils.payment_constants import normalize_payment_method_code

STATUS_LABELS_AR = {
    "pending": gettext("بانتظار التأكيد"),
    "confirmed": gettext("مؤكد"),
    "processing": gettext("قيد التجهيز"),
    "shipped": gettext("تم الشحن"),
    "delivered": gettext("تم التوصيل"),
    "cancelled": gettext("ملغى"),
}

STATUS_LABELS_EN = {
    "pending": "Pending",
    "confirmed": "Confirmed",
    "processing": "Processing",
    "shipped": "Shipped",
    "delivered": "Delivered",
    "cancelled": "Cancelled",
}

CHECKOUT_PAYMENT_MAP = {
    "cod": "cash",
    "bank_transfer": "bank_transfer",
    "card": "card",
    "e_wallet": "e_wallet",
    "online_pay": "card",
}


class StoreOrderService:
    STORE_ORDER_STATUSES = (
        "pending",
        "confirmed",
        "processing",
        "shipped",
        "delivered",
        "cancelled",
    )

    @staticmethod
    def status_label(status: str, lang: str = "ar") -> str:
        labels = STATUS_LABELS_EN if lang == "en" else STATUS_LABELS_AR
        return labels.get(status or "", status or "—")

    @staticmethod
    def is_online_order(sale: Sale) -> bool:
        return getattr(sale, "source", None) == "online_store"

    @staticmethod
    def is_fulfilled(sale: Sale) -> bool:
        return SaleService.has_inventory_posted(sale)

    @staticmethod
    def get_tenant_order(tenant_id: int, order_id: int) -> Sale | None:
        return Sale.query.filter_by(
            id=int(order_id),
            tenant_id=int(tenant_id),
            source="online_store",
        ).first()

    @staticmethod
    def list_for_customer(tenant_id: int, customer_id: int, limit: int = 50):
        return (
            Sale.query.filter_by(
                tenant_id=int(tenant_id),
                customer_id=int(customer_id),
                source="online_store",
            )
            .order_by(Sale.sale_date.desc())
            .limit(limit)
            .all()
        )

    @staticmethod
    def order_counts(tenant_id: int) -> dict:
        base = Sale.query.filter_by(tenant_id=int(tenant_id), source="online_store")
        return {
            "pending": base.filter_by(status="pending").count(),
            "confirmed": base.filter_by(status="confirmed").count(),
            "cancelled": base.filter_by(status="cancelled").count(),
            "total": base.count(),
        }

    @staticmethod
    def _locked_sale(sale: Sale) -> Sale:
        """Serialize concurrent confirm/cancel on the sale row.

        Uses a Core SELECT … FOR UPDATE (single table, so PG accepts it
        despite Sale.lines being lazy="joined", and the ORM tenant listener
        does not interfere), then refreshes the passed instance so guard
        reads happen under the lock. Sales without a persistent integer id
        (transients, test doubles) cannot be row-locked and pass through.
        """
        if not isinstance(getattr(sale, "id", None), int):
            return sale
        try:
            from sqlalchemy import inspect as sa_inspect
            from sqlalchemy import select as sa_select

            if not sa_inspect(sale).persistent:
                return sale
        except Exception:
            return sale
        from sqlalchemy.exc import OperationalError

        from services.stock_service import _MAX_LOCK_RETRIES

        stmt = (
            sa_select(Sale.id)
            .where(Sale.id == sale.id, Sale.tenant_id == sale.tenant_id)
            .with_for_update()
        )
        row = None
        for attempt in range(1, _MAX_LOCK_RETRIES + 1):
            savepoint = db.session.begin_nested()
            try:
                row = db.session.execute(stmt).first()
                savepoint.commit()
                break
            except OperationalError:
                savepoint.rollback()
                if attempt == _MAX_LOCK_RETRIES:
                    raise
        if row is None:
            # Row not visible in this session (e.g. uncommitted fixture state
            # in tests, or a concurrently deleted order in production).
            # Proceed with the passed instance — downstream guards and the
            # surrounding atomic_transaction still apply.
            current_app.logger.debug("Store order row %s not visible for locking; proceeding unlocked", sale.id)
            return sale
        try:
            db.session.refresh(sale)
        except Exception:
            current_app.logger.debug("Store order refresh after lock failed for %s", sale.id, exc_info=True)
        return sale

    @staticmethod
    def confirm_order(sale: Sale, *, mark_paid: bool = False) -> Sale:
        if not StoreOrderService.is_online_order(sale):
            raise ValueError(gettext("هذا ليس طلب متجر إلكتروني."))
        sale = StoreOrderService._locked_sale(sale)
        if sale.status == "cancelled":
            raise ValueError(gettext("لا يمكن تأكيد طلب ملغى."))
        if sale.status == "confirmed" and StoreOrderService.is_fulfilled(sale):
            raise ValueError(gettext("الطلب مؤكد مسبقاً."))

        if not StoreOrderService.is_fulfilled(sale):
            SaleService.fulfill_sale(sale)

        sale.status = "confirmed"

        payment = None
        if mark_paid and (sale.payment_status or "unpaid") != "paid":
            checkout_code = (sale.checkout_payment_method or "cod").strip().lower()
            internal_method = CHECKOUT_PAYMENT_MAP.get(
                checkout_code,
                normalize_payment_method_code(checkout_code),
            )
            if internal_method == "cod":
                internal_method = "cash"
            amount_to_pay = sale.balance_due if sale.balance_due and sale.balance_due > 0 else sale.total_amount
            if amount_to_pay and amount_to_pay > 0:
                payment = SaleService.create_payment_for_sale(
                    sale=sale,
                    amount=amount_to_pay,
                    payment_method=internal_method,
                    currency=sale.currency,
                    exchange_rate=sale.exchange_rate,
                    notes=gettext("دفع طلب متجر — تأكيد من لوحة المتجر"),
                )
                sale.recalculate_payment_status()

        # Azad platform fee — every confirmed online-store sale, any payment channel
        # (offline channels gated by SystemSettings.azad_platform_fee_include_offline)
        from services.azad_platform_fee_service import AzadPlatformFeeService

        AzadPlatformFeeService.record_store_online_fee(sale, payment=payment)

        try:
            db.session.flush()
        except Exception:
            raise

        StoreOrderService._award_loyalty_points(sale)

        current_app.logger.info("Store order confirmed: %s", sale.sale_number)
        return sale

    @staticmethod
    def _award_loyalty_points(sale: Sale):
        if not sale.customer_id:
            return
        from models.shop_customer_account import ShopCustomerAccount
        from models.shop_loyalty import ShopLoyaltyTransaction
        from services.store_service import StoreService

        existing = ShopLoyaltyTransaction.query.filter_by(
            sale_id=sale.id,
            reason="order",
        ).first()
        if existing:
            return

        account = ShopCustomerAccount.query.filter_by(customer_id=sale.customer_id, tenant_id=sale.tenant_id).first()
        if not account:
            return
        from decimal import Decimal

        total = Decimal(str(sale.total_amount or 0))
        if total > 0:
            StoreService.earn_loyalty_points(sale.tenant_id, account.id, sale.id, total)

    @staticmethod
    def _reverse_loyalty_points(sale: Sale):
        if not sale.customer_id:
            return
        from models.shop_customer_account import ShopCustomerAccount
        from models.shop_loyalty import ShopLoyalty, ShopLoyaltyTransaction

        txn = ShopLoyaltyTransaction.query.filter_by(
            sale_id=sale.id,
            reason="order",
        ).first()
        if not txn:
            return

        account = ShopCustomerAccount.query.filter_by(customer_id=sale.customer_id, tenant_id=sale.tenant_id).first()
        if not account:
            return

        lp = ShopLoyalty.query.filter_by(account_id=int(account.id), tenant_id=sale.tenant_id).first()
        if lp:
            points = abs(int(txn.points or 0))
            lp.points = max(0, (lp.points or 0) - points)
            lp.points_earned = max(0, (lp.points_earned or 0) - points)

        reversal = ShopLoyaltyTransaction(
            tenant_id=sale.tenant_id,
            account_id=account.id,
            sale_id=sale.id,
            points=-abs(int(txn.points or 0)),
            reason="cancel",
        )
        db.session.add(reversal)

    @staticmethod
    def cancel_order(sale: Sale) -> Sale:
        if not StoreOrderService.is_online_order(sale):
            raise ValueError(gettext("هذا ليس طلب متجر إلكتروني."))
        sale = StoreOrderService._locked_sale(sale)
        if sale.status == "cancelled":
            raise ValueError(gettext("الطلب ملغى بالفعل."))

        StoreOrderService._reverse_loyalty_points(sale)

        if sale.status == "confirmed" or StoreOrderService.is_fulfilled(sale):
            SaleService.cancel_sale(sale)
            if sale.coupon_code:
                from services.store_coupon_service import StoreCouponService

                StoreCouponService.release_use(sale.coupon_code, sale.tenant_id)
            try:
                db.session.flush()
            except Exception:
                raise
            return sale

        sale.status = "cancelled"
        if sale.coupon_code:
            from services.store_coupon_service import StoreCouponService

            StoreCouponService.release_use(sale.coupon_code, sale.tenant_id)
        try:
            db.session.flush()
        except Exception:
            raise

        current_app.logger.info("Store order cancelled (unfulfilled): %s", sale.sale_number)
        return sale

    @staticmethod
    def validate_stock_for_order(sale: Sale) -> list[str]:
        """Return list of product names with insufficient stock (empty if OK)."""
        issues = []
        warehouse_id = sale.warehouse_id
        for line in sale.lines:  # type: ignore[attr-defined]
            available, msg = StockService.check_availability_in_warehouse(line.product_id, line.quantity, warehouse_id)
            if not available:
                name = line.product.name if line.product else str(line.product_id)
                issues.append(f"{name}: {msg}")
        return issues
