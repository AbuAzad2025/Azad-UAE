"""
SQLAlchemy Event Listeners - thin registrations delegating to service layer
"""

import logging
import warnings
from datetime import UTC

from sqlalchemy import event

from config import ai_orm_listeners_enabled

logger = logging.getLogger(__name__)

_ADVANCED_SALE_LISTENER_ALLOWED = False

# ── Idempotency guard ────────────────────────────────────────────────────
# register_all_listeners() runs inside the app factory; the factory executes
# once per app instance (and hundreds of times across the test-suite). The
# listeners attach to GLOBAL model classes, so every extra call would stack
# duplicate hooks. Each group registers at most once per process.
_LISTENER_GROUPS_REGISTERED: set = set()


def _mark(group: str) -> bool:
    """Return True the first time a listener group is registered."""
    if group in _LISTENER_GROUPS_REGISTERED:
        logger.info("Listener group %r already registered — skipping duplicate", group)
        return False
    _LISTENER_GROUPS_REGISTERED.add(group)
    return True


def register_all_listeners():
    register_sale_listeners()
    register_receipt_listeners()
    register_purchase_listeners()
    register_payment_listeners()
    register_branch_listeners()
    register_stock_movement_listeners()
    register_cheque_listeners()
    register_product_return_listeners()
    register_expense_listeners()
    register_gl_listeners()
    register_validation_listeners()
    register_audit_listeners()
    if ai_orm_listeners_enabled():
        warnings.warn(
            "Experimental AI ORM listeners enabled — DO NOT USE IN PRODUCTION",
            RuntimeWarning,
            stacklevel=2,
        )
        register_ai_listeners()
        register_neural_training_listeners()
    else:
        logger.info("AI ORM listeners skipped (AI_ORM_LISTENERS_ENABLED=false or production default)")
    register_automatic_gl_listeners()
    logger.info(
        "[OK] Event listeners registered (core + validation + audit; AI=%s)",
        ai_orm_listeners_enabled(),
    )


def register_sale_listeners():
    if not _mark("sale"):
        return
    from models import Sale

    @event.listens_for(Sale, "after_insert")
    @event.listens_for(Sale, "after_update")
    def _h(mapper, connection, target):
        if not target.is_active or target.status == "cancelled":
            return
        try:
            logger.debug(f"Sale {target.sale_number} changed for customer {target.customer_id}")
        except Exception:
            pass

    @event.listens_for(Sale, "after_delete")
    def _h2(mapper, connection, target):
        try:
            logger.info(f"Sale {target.sale_number} deleted")
        except Exception as e:
            logger.warning(f"Failed to log sale deletion: {e}")


def register_receipt_listeners():
    if not _mark("receipt"):
        return
    from models import Receipt

    @event.listens_for(Receipt, "after_insert")
    def _h(mapper, connection, target):
        try:
            logger.info(
                f"Receipt {target.receipt_number} created - amount: {target.amount_aed} AED for customer {target.customer_id}"
            )
        except Exception as e:
            logger.warning(f"Failed to log receipt: {e}")

    @event.listens_for(Receipt, "before_delete")
    def _h2(mapper, connection, target):
        logger.warning(f"Attempted to delete receipt {target.receipt_number} - use cancellation instead")


def register_purchase_listeners():
    if not _mark("purchase"):
        return
    from models import Purchase

    @event.listens_for(Purchase, "after_insert")
    @event.listens_for(Purchase, "after_update")
    def _h(mapper, connection, target):
        if target.status == "cancelled":
            return
        try:
            logger.debug(f"Purchase {target.purchase_number} changed for supplier {target.supplier_id}")
        except Exception:
            pass


def register_payment_listeners():
    if not _mark("payment"):
        return
    from models import Payment

    @event.listens_for(Payment, "after_insert")
    def _h(mapper, connection, target):
        try:
            if hasattr(target, "supplier_id") and target.supplier_id:
                logger.info(
                    f"Payment {getattr(target, 'payment_number', target.id)} created - amount: {target.amount_aed} AED to supplier {target.supplier_id}"
                )
        except Exception as e:
            logger.warning(f"Failed to log payment: {e}")


def register_branch_listeners():
    if not _mark("branch"):
        return
    from services.branch_audit_service import register_branch_event_listeners

    register_branch_event_listeners()


def register_stock_movement_listeners():
    if not _mark("stock_movement"):
        return
    from decimal import Decimal

    from models import StockMovement

    @event.listens_for(StockMovement, "after_insert")
    def _h(mapper, connection, target):
        try:
            movement_type_ar = {
                "sale": "بيع (خروج)",
                "purchase": "شراء (دخول)",
                "adjustment": "تعديل",
                "return": "إرجاع",
                "transfer": "نقل",
            }.get(target.movement_type, target.movement_type)
            quantity_change = target.quantity or Decimal("0")
            logger.info(
                f"Stock Movement: {movement_type_ar} | Product #{target.product_id} | Qty: {abs(quantity_change)} | Ref: {target.reference_type}-{target.reference_id}"
            )
        except Exception as e:
            logger.error(f"Failed to log stock movement: {e}")


def register_cheque_listeners():
    if not _mark("cheque"):
        return
    from services.cheque_service import register_cheque_event_listeners

    register_cheque_event_listeners()


def register_product_return_listeners():
    if not _mark("product_return"):
        return
    from models import ProductReturn

    @event.listens_for(ProductReturn, "after_insert")
    def _h(mapper, connection, target):
        try:
            if target.status == "approved":
                logger.info(f"Product return {target.return_number} approved - stock will be updated via StockMovement")
        except Exception as e:
            logger.error(f"Failed to process product return: {e}")


def register_expense_listeners():
    if not _mark("expense"):
        return
    from models import Expense

    @event.listens_for(Expense, "after_insert")
    @event.listens_for(Expense, "after_update")
    def _h(mapper, connection, target):
        try:
            if target.is_active:
                logger.info(f"Expense recorded: {target.amount_aed} AED - Category: {target.category_id}")
        except Exception as e:
            logger.error(f"Failed to log expense: {e}")


def register_gl_listeners():
    if not _mark("gl"):
        return
    from services.gl_auto_service import register_gl_event_listeners

    register_gl_event_listeners()


def register_validation_listeners():
    if not _mark("validation"):
        return
    from services.gl_auto_service import register_validation_event_listeners

    register_validation_event_listeners()


def register_audit_listeners():
    if not _mark("audit"):
        return
    from models import Payment, Purchase, Receipt, Sale

    @event.listens_for(Sale, "after_delete")
    def _h1(mapper, connection, target):
        logger.warning(f"DELETED: Sale {target.sale_number} - Amount: {target.amount_aed} AED")

    @event.listens_for(Purchase, "after_delete")
    def _h2(mapper, connection, target):
        logger.warning(f"DELETED: Purchase {target.purchase_number} - Amount: {target.amount_aed} AED")

    @event.listens_for(Receipt, "after_delete")
    def _h3(mapper, connection, target):
        logger.warning(f"DELETED: Receipt {target.receipt_number} - Amount: {target.amount_aed} AED")

    @event.listens_for(Payment, "after_delete")
    def _h4(mapper, connection, target):
        logger.warning(f"DELETED: Payment - Amount: {target.amount_aed} AED")


def register_ai_listeners():
    if not _mark("ai"):
        return
    from services.events_ai_service import register_ai_event_listeners

    register_ai_event_listeners()


def register_neural_training_listeners():
    if not _mark("neural_training"):
        return
    from services.events_ai_service import register_neural_event_listeners

    register_neural_event_listeners()


def register_automatic_gl_listeners():
    logger.info("Automatic GL listeners skipped - relying on Service layer for accurate GL entries")


def register_advanced_sale_listener():
    if not _ADVANCED_SALE_LISTENER_ALLOWED:
        logger.warning(
            "register_advanced_sale_listener() is legacy/disabled; use sale_service / payment_service for balance updates."
        )
        return
    from datetime import datetime
    from decimal import Decimal

    from models import Customer, Sale

    @event.listens_for(Sale, "after_insert")
    @event.listens_for(Sale, "after_update")
    def advanced_auto_update_customer_balance(mapper, connection, target):
        if not target.is_active or target.status == "cancelled":
            return
        try:
            sales = connection.execute(
                Sale.__table__.select().where(
                    Sale.customer_id == target.customer_id,
                    Sale.status == "confirmed",
                    Sale.is_active,
                )
            ).fetchall()
            new_balance = sum(
                (sale.amount_aed or Decimal("0")) - (sale.paid_amount_aed or Decimal("0")) for sale in sales
            )
            connection.execute(
                Customer.__table__.update()
                .where(Customer.id == target.customer_id)
                .values(balance=new_balance, updated_at=datetime.now(UTC))
            )
            logger.info(f"Auto-updated customer {target.customer_id} balance to {new_balance} AED")
        except Exception as e:
            logger.error(f"Failed to auto-update customer balance: {e}")
