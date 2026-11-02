"""
Database Transaction Safety Utilities
Ensures all multi-step financial operations are atomic.
"""

import logging
from contextlib import contextmanager

from extensions import db

logger = logging.getLogger(__name__)

MAX_LOCK_RETRIES = 3


import random
import time

_MAX_LOCK_RETRIES = 5
_BASE_LOCK_RETRY_DELAY = 0.02  # 20ms base delay


def lock_row_for_update(model, pk, *, label=None, populate_existing=True):
    """Re-read one row under ``SELECT ... FOR UPDATE NOWAIT`` and return it.

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
    caller's transaction. On deadlock (which aborts the subtransaction),
    the savepoint rolls back the failed attempt but keeps the main transaction
    alive. Retries with exponential backoff + jitter to reduce contention.
    This prevents deadlocks on shared rows (e.g., walk-in customer in POS).
    """
    from sqlalchemy.exc import OperationalError

    query = db.session.query(model).filter(model.id == pk)
    if populate_existing:
        query = query.populate_existing()

    target = label or f"{model.__name__}({pk})"
    for attempt in range(1, _MAX_LOCK_RETRIES + 1):
        savepoint = db.session.begin_nested()
        try:
            row = query.with_for_update(of=model, nowait=True).first()
            savepoint.commit()
            if row is None:
                raise LookupError(f"{target} not found")
            return row
        except LookupError:
            savepoint.rollback()
            raise
        except OperationalError as e:
            savepoint.rollback()
            # Check if it's a lock-not-available error (PostgreSQL error code 55P03)
            # or a deadlock detected error (PostgreSQL error code 40P01)
            is_lock_error = getattr(e, "pgcode", None) in ("55P03", "40P01") or "could not obtain lock" in str(e).lower() or "deadlock detected" in str(e).lower()
            if not is_lock_error:
                # Re-raise non-lock errors immediately
                raise
            if attempt == _MAX_LOCK_RETRIES:
                logger.critical(
                    "Row lock acquisition failed after %d attempts for %s - aborting "
                    "to prevent a lost update on a money accumulator.",
                    _MAX_LOCK_RETRIES,
                    target,
                )
                raise
            logger.warning(
                "Lock contention on %s (attempt %d/%d) - retrying after backoff.",
                target,
                attempt,
                _MAX_LOCK_RETRIES,
            )
            # Exponential backoff with jitter: 20ms, 40ms, 80ms, 160ms, 320ms + random 0-20ms
            delay = _BASE_LOCK_RETRY_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 0.02)
            time.sleep(delay)
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


def release_session(description: str = "unnamed") -> bool:
    """End the current transaction and return the session to a usable state.

    This is not an atomicity rollback and must not be used to undo work. It
    exists because a statement that errored earlier leaves PostgreSQL refusing
    every later command on that connection until the aborted transaction is
    cleared, which makes each subsequent query fail with InFailedSqlTransaction
    and hides the original error behind a cascade of noise.

    Bootstrap code needs exactly this after a best-effort repair step: discard
    the possibly-aborted transaction, keep everything already committed, and
    carry on. Use atomic_transaction() for anything where losing the work on
    failure would be wrong.

    Returns True if a transaction was actually ended, False if there was nothing
    to clear or the session refused.
    """
    try:
        # db.session is a scoped_session proxy, so the Session API is behind the
        # call: db.session() returns the underlying Session, which is what has
        # in_transaction()/rollback(). Reaching through the proxy instead is
        # what mypy flagged here.
        session = db.session()
        if not session.in_transaction():
            return False
        session.rollback()
        logger.debug("Session released: %s", description)
        return True
    except Exception as e:
        logger.error("Session release failed: %s — %s", description, e)
        return False


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
