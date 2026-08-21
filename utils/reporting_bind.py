"""Reporting-bind routing for heavy analytical queries.

SQLAlchemy supports multiple binds via ``SQLALCHEMY_BINDS``. This module
provides a decorator and context manager that route the active session to the
``reporting`` bind, which can be configured with a longer statement timeout
than the primary transactional bind.

If no ``reporting`` bind is configured, operations fall back to the default
bind so the code works in development and test environments.
"""

from __future__ import annotations

import contextlib
import functools
import logging
from collections.abc import Callable, Iterator
from typing import Any, TypeVar

from flask import current_app

from extensions import db

logger = logging.getLogger(__name__)
F = TypeVar("F", bound=Callable)


def _get_session() -> Any:
    return db.session


def _bind_is_configured(bind_name: str) -> bool:
    try:
        binds = current_app.config.get("SQLALCHEMY_BINDS") or {}
        return bind_name in binds
    except RuntimeError:
        return False


def _set_bind(session: Any, bind_name: str | None) -> None:
    """Set the session's active bind (None means default)."""
    if bind_name:
        bind = db.engines[bind_name]
    else:
        bind = db.engine
    session.bind = bind


@contextlib.contextmanager
def reporting_bind(bind_name: str = "reporting") -> Iterator[None]:
    """Context manager that routes the current session to ``bind_name``.

    Falls back to the default bind if ``bind_name`` is not configured.
    """
    session = _get_session()
    original_bind = session.bind
    if not _bind_is_configured(bind_name):
        logger.debug("Bind %r not configured; using default bind", bind_name)
        yield
        return

    _set_bind(session, bind_name)
    try:
        yield
    finally:
        session.bind = original_bind


def use_reporting_bind(bind_name: str = "reporting") -> Callable[[F], F]:
    """Decorator that runs the wrapped function against the reporting bind.

    Example::

        @use_reporting_bind()
        def generate_aging_report():
            return db.session.execute(...)
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with reporting_bind(bind_name):
                return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
