import logging
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)


def validate_decimal_precision(value: Any, max_digits=15, decimal_places=3):
    if value is None:
        return True
    try:
        decimal_value = Decimal(str(value))
        if abs(int(decimal_value.as_tuple().exponent)) > decimal_places:
            return False
        total_digits = len(decimal_value.as_tuple().digits)
        if total_digits > max_digits:
            return False
        return True
    except (ArithmeticError, ValueError, TypeError):
        return False


def ensure_balance_consistency(connection, model, record_id):
    try:
        from models import Customer, Sale

        if model == Customer:
            result = connection.execute(
                Sale.__table__.select().where(Sale.customer_id == record_id, Sale.status == "confirmed")
            ).fetchall()
            calculated_balance = sum(
                (row.amount_aed or Decimal("0")) - (row.paid_amount_aed or Decimal("0")) for row in result
            )
            customer = connection.execute(Customer.__table__.select().where(Customer.id == record_id)).first()
            stored_balance = customer.balance if customer else Decimal("0")
            return {
                "stored": stored_balance,
                "calculated": calculated_balance,
                "consistent": abs(stored_balance - calculated_balance) < Decimal("0.01"),
            }
    except Exception as e:
        logger.error(f"Failed to check balance consistency: {e}")
        return {"stored": None, "calculated": None, "consistent": None}


def validate_journal_entry_balance(mapper, connection, target):
    try:
        debit = target.total_debit or Decimal("0")
        credit = target.total_credit or Decimal("0")
        if (debit > 0 or credit > 0) and abs(debit - credit) > Decimal("0.01"):
            logger.error(f"Journal entry {target.entry_number} is UNBALANCED! Debit: {debit}, Credit: {credit}")
            raise ValueError(f"القيد غير متوازن! المدين: {debit}, الدائن: {credit}")
        logger.info(f"Journal entry {target.entry_number} is balanced: {debit} = {credit}")
    except ValueError:
        raise
    except Exception as e:
        logger.error(f"Failed to validate journal entry: {e}")
        raise


def register_gl_event_listeners():
    # GLJournalEntry balance validation is handled by the model-level event
    # listener in models/gl.py (lines 429-446) which is the authoritative check.
    # This function is kept as a no-op for backward compatibility with
    # models/events.py and existing tests.
    pass


def register_validation_event_listeners():
    from models import Sale, Purchase, Receipt, Payment, Product
    from sqlalchemy import event

    @event.listens_for(Sale, "before_insert")
    @event.listens_for(Sale, "before_update")
    def _validate_sale(mapper, connection, target):
        try:
            if target.amount_aed and target.amount_aed < 0:
                logger.error(f"Sale {target.sale_number}: Negative amount detected!")
        except Exception as e:
            logger.error(f"Failed to validate sale: {e}")

    @event.listens_for(Purchase, "before_insert")
    @event.listens_for(Purchase, "before_update")
    def _validate_purchase(mapper, connection, target):
        try:
            if target.amount_aed and target.amount_aed < 0:
                logger.error(f"Purchase {target.purchase_number}: Negative amount detected!")
        except Exception as e:
            logger.error(f"Failed to validate purchase: {e}")

    @event.listens_for(Receipt, "before_insert")
    def _validate_receipt(mapper, connection, target):
        try:
            if target.amount_aed and target.amount_aed <= 0:
                logger.error(f"Receipt {target.receipt_number}: Invalid amount!")
        except Exception as e:
            logger.error(f"Failed to validate receipt: {e}")

    @event.listens_for(Payment, "before_insert")
    def _validate_payment(mapper, connection, target):
        try:
            if target.amount_aed and target.amount_aed <= 0:
                logger.error("Payment: Invalid amount!")
        except Exception as e:
            logger.error(f"Failed to validate payment: {e}")

    @event.listens_for(Product, "before_update")
    def _validate_product_stock(mapper, connection, target):
        try:
            if target.current_stock and target.current_stock < 0:
                logger.warning(f"Product {target.name}: Negative stock detected ({target.current_stock})")
        except Exception as e:
            logger.error(f"Failed to validate product stock: {e}")
