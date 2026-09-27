"""
Database Transaction Safety Utilities
Ensures all multi-step financial operations are atomic.
"""

import logging
from contextlib import contextmanager

from extensions import db

logger = logging.getLogger(__name__)

MAX_LOCK_RETRIES = 3


def lock_row_for_update(model, pk, *, label=None, populate_existing=True):
    """Re-read one row under ``SELECT ... FOR UPDATE`` and return it.

    Money accumulators on Customer / Supplier / Partner are read-modify-write
    targets: ``balance = (balance or 0) - amount``. Under PostgreSQL READ
    COMMITTED two concurrent transactions both read the old value and both
    write the decremented one, so one transaction's movement is lost forever -
    the ledger and the sub-ledger then disagree permanently.

    The lock is taken here, inside the accumulator, rather than at each call
    site, so no caller can forget it. ``populate_existing`` refreshes the
    identity-mapped instance, so the caller keeps working with its own object
    and reads the freshly locked value.

    Uses a savepoint per attempt so lock contention does not roll back the
    caller's transaction, and aborts on final failure rather than silently
    proceeding unlocked. Mirrors ``services.stock_service._safe_for_update``.
    """
    from sqlalchemy.exc import OperationalError

    query = db.session.query(model).filter(model.id == pk)
    if populate_existing:
        query = query.populate_existing()

    target = label or f"{model.__name__}({pk})"
    for attempt in range(1, MAX_LOCK_RETRIES + 1):
        savepoint = db.session.begin_nested()
        try:
            row = query.with_for_update().first()
            savepoint.commit()
            if row is None:
                raise LookupError(f"{target} not found")
            return row
        except LookupError:
            savepoint.rollback()
            raise
        except OperationalError:
            savepoint.rollback()
            if attempt == MAX_LOCK_RETRIES:
                logger.critical(
                    "Row lock acquisition failed after %d attempts for %s - aborting "
                    "to prevent a lost update on a money accumulator.",
                    MAX_LOCK_RETRIES,
                    target,
                )
                raise
            logger.warning(
                "Lock contention on %s (attempt %d/%d) - retrying.",
                target,
                attempt,
                MAX_LOCK_RETRIES,
            )
    raise RuntimeError(f"Failed to acquire row lock for {target}")  # pragma: no cover


@contextmanager
def atomic_transaction(description: str = "unnamed"):
    """
    Context manager for atomic database transactions.
    Automatically rolls back on any exception.

    Usage:
        with atomic_transaction("sale_creation"):
            sale = Sale(...)
            db.session.add(sale)
            # if any step fails, everything rolls back
    """
    try:
        yield
        db.session.commit()
        logger.debug(f"Transaction committed: {description}")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Transaction rolled back: {description} — {e}")
        raise


def safe_commit(description: str = "unnamed"):
    """
    Safe commit with automatic rollback on failure.
    Returns True on success, False on failure.
    """
    try:
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        logger.error(f"Commit failed: {description} — {e}")
        return False
