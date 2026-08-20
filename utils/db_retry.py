"""Database retry utilities.

Provides decorators and context managers for retrying operations that fail due
to PostgreSQL serialization errors (SQLSTATE 40001) under REPEATABLE READ
isolation. These errors are transient: a retry with a short backoff usually
succeeds without user intervention.
"""

from __future__ import annotations

import functools
import logging
import random
import time
from typing import Callable, TypeVar

from sqlalchemy.exc import DBAPIError, OperationalError

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable)


def _is_serialization_error(exc: BaseException) -> bool:
    """Return True if ``exc`` is a PostgreSQL 40001 serialization failure."""
    if isinstance(exc, OperationalError):
        orig = getattr(exc, "orig", None)
        if orig is not None:
            sqlstate = getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)
            if sqlstate == "40001":
                return True
    if isinstance(exc, DBAPIError):
        orig = getattr(exc, "orig", None)
        if orig is not None:
            sqlstate = getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)
            if sqlstate == "40001":
                return True
    # Fallback: inspect the string representation for the SQLSTATE.
    if "40001" in str(exc):
        return True
    return False


def _retry_callable(
    func: Callable,
    *args,
    max_retries: int = 3,
    base_delay: float = 0.1,
    max_delay: float = 2.0,
    exceptions: tuple[type[BaseException], ...] = (OperationalError, DBAPIError),
    **kwargs,
):
    """Run ``func`` and retry on PostgreSQL serialization failures."""
    last_exc: BaseException | None = None
    for attempt in range(max_retries + 1):
        try:
            return func(*args, **kwargs)
        except exceptions as exc:
            last_exc = exc
            if attempt >= max_retries or not _is_serialization_error(exc):
                raise
            delay = min(base_delay * (2**attempt), max_delay)
            jitter = random.uniform(0, delay)
            logger.warning(
                "Serialization failure (40001) on %s attempt %s; retrying in %.3fs",
                getattr(func, "__name__", "<callable>"),
                attempt + 1,
                jitter,
            )
            time.sleep(jitter)
    if last_exc is not None:
        raise last_exc
    return None  # pragma: no cover


def retry_on_serialization_error(
    max_retries: int = 3,
    base_delay: float = 0.1,
    max_delay: float = 2.0,
    exceptions: tuple[type[BaseException], ...] = (OperationalError, DBAPIError),
):
    """Decorator that retries a function on PostgreSQL serialization failures.

    Args:
        max_retries: Maximum number of retry attempts after the initial failure.
        base_delay: Initial backoff delay in seconds.
        max_delay: Cap on the backoff delay in seconds.
        exceptions: Exception types to catch and inspect for SQLSTATE 40001.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return _retry_callable(
                func,
                *args,
                max_retries=max_retries,
                base_delay=base_delay,
                max_delay=max_delay,
                exceptions=exceptions,
                **kwargs,
            )

        return wrapper  # type: ignore[return-value]

    return decorator


def retry_call(
    func: Callable,
    *args,
    max_retries: int = 3,
    base_delay: float = 0.1,
    max_delay: float = 2.0,
    exceptions: tuple[type[BaseException], ...] = (OperationalError, DBAPIError),
    **kwargs,
):
    """Call ``func`` and retry on PostgreSQL serialization failures.

    Use this for ad-hoc blocks that cannot be wrapped in a decorator::

        retry_call(lambda: db.session.flush())
    """
    return _retry_callable(
        func,
        *args,
        max_retries=max_retries,
        base_delay=base_delay,
        max_delay=max_delay,
        exceptions=exceptions,
        **kwargs,
    )
