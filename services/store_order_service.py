"""Online store order lifecycle — confirm, cancel, fulfillment."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from flask import current_app
from flask_babel import gettext

from extensions import db
from models import Sale
from models.store_provisional_order import StoreProvisionalOrder
from services.sale_service import SaleService
from services.stock_service import StockService
from services.store_service import StoreService
from utils.currency_utils import convert_and_quantize_aed, resolve_tenant_base_currency
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

        stmt = sa_select(Sale.id).where(Sale.id == sale.id, Sale.tenant_id == sale.tenant_id).with_for_update()
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
            SaleService.fulfill_sale(
                sale,
                revenue_concept="SHOP_SALES_REVENUE",
                cogs_concept="SHOP_COGS",
            )

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

        # The fee must not be able to roll back the tenant's order.
        #
        # record_store_online_fee deliberately raises when the platform vault is
        # missing ("Platform vault does not exist"), which is right for its direct
        # callers - a settlement that cannot find the vault must not report
        # success. But here it runs inside the confirm_order transaction, and the
        # vault is platform-side configuration the tenant cannot see or change.
        # Before this guard, a deployment without a platform vault made every
        # online-store order impossible to confirm: the exception propagated out of
        # atomic_transaction, the whole confirmation rolled back, and the route
        # flashed a warning while the order silently stayed pending. The shop could
        # not fulfil anything and nothing in the UI said why.
        #
        # So the failure is logged at ERROR with the sale number and re-surfaced by
        # monitoring, and the tenant's order still completes. The fee is then owed
        # and can be accrued separately; losing it silently would be worse, which
        # is why this logs rather than returns quietly.
        try:
            AzadPlatformFeeService.record_store_online_fee(sale, payment=payment)
        except Exception:
            current_app.logger.error(
                "Platform fee accrual failed for online order %s (id %s); the order is "
                "confirmed but the platform fee is unaccrued and must be booked separately.",
                getattr(sale, "sale_number", None),
                getattr(sale, "id", None),
                exc_info=True,
            )

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

    @staticmethod
    def create_store_order_from_cart(
        tenant_id: int,
        *,
        customer_id: int | None,
        cart: dict[int, Decimal],
        currency_code: str,
        warehouse_id: int | None = None,
        branch_id: int | None = None,
        payment_method: str = "cod",
        notes: str | None = None,
        seller_id: int | None = None,
    ) -> Sale:
        """Create an online-store order from a shopping cart in a given currency.

        Each cart line price is resolved via StorePricingService.resolve_store_price
        (explicit StoreProductPrice if present, else base-currency conversion).
        The order total is converted to the tenant base currency for accounting
        using the live/stored exchange rate (ExchangeRateRecord).

        The Sale is created with ``source="online_store"`` so it flows through
        the store order lifecycle (confirm/cancel/fulfill) and the Azad platform
        fee is accrued on confirmation.
        """
        from models import Product, SaleLine

        tenant_id = int(tenant_id)
        currency_code = (currency_code or "").strip().upper()
        base_currency = resolve_tenant_base_currency(tenant_id=tenant_id)

        from services.store_pricing_service import StorePricingService
        from services.store_service import StoreService

        # Resolve exchange rate from currency_code -> base_currency
        rate = Decimal("1")
        if currency_code != base_currency:
            stored = StoreOrderService._latest_stored_rate(tenant_id, currency_code, base_currency)
            if stored is not None and Decimal(str(stored)) > 0:
                rate = Decimal(str(stored))
            else:
                current_app.logger.warning(
                    "No exchange rate %s -> %s for tenant %s; using rate=1",
                    currency_code,
                    base_currency,
                    tenant_id,
                )

        online_wh = StoreService.get_online_warehouse(tenant_id, create=False)
        if warehouse_id is None:
            warehouse_id = online_wh.id if online_wh else None

        # Build sale lines and compute totals in transaction currency
        lines: list[dict] = []
        subtotal_tx_ccy = Decimal("0")
        for pid, qty in cart.items():
            product = Product.query.filter_by(id=int(pid), tenant_id=tenant_id, is_active=True).first()
            if not product:
                continue
            qty = Decimal(str(qty))
            if qty <= 0:
                continue
            from models import Tenant

            _tenant = db.session.get(Tenant, tenant_id)
            unit_price = StorePricingService.resolve_store_price(product, _tenant, currency_code=currency_code)
            if unit_price is None:
                unit_price = Decimal(str(product.regular_price or 0))
            line_total = (unit_price * qty).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
            subtotal_tx_ccy += line_total
            lines.append(
                {
                    "product": product,
                    "quantity": qty,
                    "unit_price": unit_price,
                    "line_total": line_total,
                }
            )

        if not lines:
            raise ValueError(gettext("السلة فارغة أو لا تحتوي على منتجات صالحة."))

        # Convert subtotal to tenant base currency for accounting
        subtotal_aed = convert_and_quantize_aed(
            subtotal_tx_ccy, currency_code, rate, base_currency=base_currency, tenant_id=tenant_id
        )
        tax_amount = Decimal("0")  # store tax handled separately if enabled
        total_amount = subtotal_tx_ccy
        total_amount_aed = subtotal_aed

        sale = Sale(
            tenant_id=tenant_id,
            customer_id=customer_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            branch_id=branch_id,
            source="online_store",
            currency=currency_code,
            exchange_rate=rate,
            base_currency=base_currency,
            subtotal=subtotal_tx_ccy,
            discount_amount=Decimal("0"),
            shipping_cost=Decimal("0"),
            tax_rate=Decimal("0"),
            tax_amount=tax_amount,
            taxable_amount=subtotal_tx_ccy,
            total_amount=total_amount,
            amount=total_amount,
            paid_amount=Decimal("0"),
            balance_due=total_amount,
            amount_aed=total_amount_aed,
            paid_amount_aed=Decimal("0"),
            currency_rate_source="stored" if currency_code != base_currency else "same",
            payment_status="unpaid",
            status="pending",
            is_active=True,
            notes=notes or gettext("طلب من المتجر الإلكتروني"),
        )
        db.session.add(sale)
        db.session.flush()

        for line in lines:
            line_total_aed = convert_and_quantize_aed(
                line["line_total"], currency_code, rate, base_currency=base_currency, tenant_id=tenant_id
            )
            sl = SaleLine(
                tenant_id=tenant_id,
                sale_id=sale.id,
                product_id=line["product"].id,
                quantity=line["quantity"],
                unit_price=line["unit_price"],
                discount_percent=Decimal("0"),
                line_total=line["line_total"],
                cost_price=Decimal("0"),
                unit_price_aed=line_total_aed / line["quantity"] if line["quantity"] > 0 else Decimal("0"),
                line_total_aed=line_total_aed,
            )
            db.session.add(sl)
        db.session.flush()

        current_app.logger.info(
            "Store order created: %s (currency=%s rate=%s total_tx=%s total_aed=%s)",
            sale.sale_number,
            currency_code,
            rate,
            subtotal_tx_ccy,
            subtotal_aed,
        )
        return sale

    @staticmethod
    def _latest_stored_rate(tenant_id: int, from_currency: str, to_currency: str) -> Decimal | None:
        """Latest stored ExchangeRateRecord rate from from_currency -> to_currency."""
        try:
            from models.exchange_rate_record import ExchangeRateRecord

            row = (
                ExchangeRateRecord.query.filter_by(
                    tenant_id=int(tenant_id),
                    from_currency=from_currency,
                    to_currency=to_currency,
                )
                .order_by(ExchangeRateRecord.effective_date.desc(), ExchangeRateRecord.created_at.desc())
                .first()
            )
            if row:
                return Decimal(str(row.rate))
        except Exception:
            current_app.logger.debug("ExchangeRateRecord lookup failed", exc_info=True)
        return None

    @staticmethod
    def convert_provisional_to_sale(provisional: StoreProvisionalOrder, approver_user) -> Sale:
        """Convert a pending provisional order into a real online-store Sale.

        Steps:
        1. Validate stock availability in the online warehouse for each cart line
        2. Create a Sale with source="online_store", currency and amounts from the provisional order
        3. Create SaleLines
        4. Call SaleService.fulfill_sale with SHOP_SALES_REVENUE / SHOP_COGS concepts
           (posts GL: Dr Customer AR / Cr SHOP_SALES_REVENUE, Dr SHOP_COGS / Cr INVENTORY_ASSET)
        5. Mark the provisional order as converted with the new sale_id
        """
        from models import Customer, SaleLine

        tenant_id = int(provisional.tenant_id)
        currency_code = provisional.currency_code or "USD"
        rate = provisional.exchange_rate or Decimal("1")

        # Resolve base currency for accounting
        base_currency = resolve_tenant_base_currency(tenant_id=tenant_id)

        online_wh = StoreService.get_online_warehouse(tenant_id, create=False)
        if not online_wh:
            raise ValueError(gettext("لا يوجد مستودع أونلاين نشط لهذا المتجر."))

        warehouse_id = online_wh.id

        # Validate stock for each line
        cart = provisional.cart_json or []
        if not cart:
            raise ValueError(gettext("الطلب المؤقت لا يحتوي على منتجات."))

        # Build sale lines and check stock
        sale_lines_data = []
        for item in cart:
            pid = int(item["product_id"])
            qty = Decimal(str(item["quantity"]))
            unit_price = Decimal(str(item["unit_price"]))
            line_total = Decimal(str(item["line_total"]))

            available, msg = StockService.check_availability_in_warehouse(pid, qty, warehouse_id)
            if not available:
                product_name = item.get("product_name", f"Product {pid}")
                raise ValueError(gettext("المוצר {name}: {msg}").format(name=product_name, msg=msg))

            sale_lines_data.append(
                {
                    "product_id": pid,
                    "quantity": qty,
                    "unit_price": unit_price,
                    "line_total": line_total,
                }
            )

        # Create the Sale
        customer = None
        customer_id = None
        if provisional.customer_email:
            from models import Customer

            customer = Customer.query.filter_by(email=provisional.customer_email, tenant_id=tenant_id).first()
            if customer:
                customer_id = customer.id

        sale = Sale(
            tenant_id=tenant_id,
            customer_id=customer_id,
            seller_id=int(approver_user.id) if approver_user and hasattr(approver_user, "id") else None,
            warehouse_id=warehouse_id,
            source="online_store",
            currency=currency_code,
            exchange_rate=rate,
            base_currency=base_currency,
            subtotal=provisional.subtotal_tx_ccy,
            discount_amount=Decimal("0"),
            shipping_cost=Decimal("0"),
            tax_rate=Decimal("0"),
            tax_amount=Decimal("0"),
            taxable_amount=provisional.subtotal_tx_ccy,
            total_amount=provisional.subtotal_tx_ccy,
            amount=provisional.subtotal_tx_ccy,
            paid_amount=Decimal("0"),
            balance_due=provisional.subtotal_tx_ccy,
            amount_aed=provisional.subtotal_aed,
            paid_amount_aed=Decimal("0"),
            payment_status="unpaid",
            status="confirmed",  # approved by tenant -> confirmed
            is_active=True,
            notes=gettext("طلب متجر إلكتروني معتمد من الطلب المؤقت {number}").format(
                number=provisional.provisional_number
            ),
        )
        db.session.add(sale)
        db.session.flush()

        # Create sale lines
        for line_data in sale_lines_data:
            line_total_aed = convert_and_quantize_aed(
                line_data["line_total"], currency_code, rate, base_currency=base_currency, tenant_id=tenant_id
            )
            sl = SaleLine(
                tenant_id=tenant_id,
                sale_id=sale.id,
                product_id=line_data["product_id"],
                quantity=line_data["quantity"],
                unit_price=line_data["unit_price"],
                discount_percent=Decimal("0"),
                line_total=line_data["line_total"],
                cost_price=Decimal("0"),
                unit_price_aed=(
                    line_total_aed / Decimal(str(line_data["quantity"]))
                    if Decimal(str(line_data["quantity"])) > 0
                    else Decimal("0")
                ),
                line_total_aed=line_total_aed,
            )
            db.session.add(sl)
        db.session.flush()

        # Deduct stock and post GL using SHOP_SALES_REVENUE / SHOP_COGS concepts
        SaleService.fulfill_sale(
            sale,
            revenue_concept="SHOP_SALES_REVENUE",
            cogs_concept="SHOP_COGS",
        )

        # Update sale status to confirmed (fulfill_sale may have set it)
        sale.status = "confirmed"
        db.session.flush()

        # Mark provisional as converted
        provisional.status = StoreProvisionalOrder.STATUS_CONVERTED
        provisional.converted_sale_id = sale.id
        provisional.approved_by = int(approver_user.id) if approver_user and hasattr(approver_user, "id") else None
        from datetime import UTC, datetime

        provisional.approved_at = datetime.now(UTC)
        db.session.flush()

        current_app.logger.info(
            "Provisional order %s converted to Sale %s", provisional.provisional_number, sale.sale_number
        )
        return sale
