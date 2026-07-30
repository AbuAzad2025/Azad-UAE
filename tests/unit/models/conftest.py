"""Shared fixtures for models unit tests."""

import pytest


@pytest.fixture(autouse=True)
def _reset_listener_group_registry():
    """Each test must see a fresh listener-registration registry.

    models/events.py guards each register_* group with a process-level
    idempotency flag (listeners attach to global model classes). Tests call
    the register functions directly and expect them to run every time, so
    the registry is cleared between tests.
    """
    from models.events import _LISTENER_GROUPS_REGISTERED

    _LISTENER_GROUPS_REGISTERED.clear()
    yield
    _LISTENER_GROUPS_REGISTERED.clear()
