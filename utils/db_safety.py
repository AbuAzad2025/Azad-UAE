"""
Database Transaction Safety Utilities
Ensures all multi-step financial operations are atomic.
"""

from contextlib import contextmanager
from extensions import db
import logging

logger = logging.getLogger(__name__)


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
