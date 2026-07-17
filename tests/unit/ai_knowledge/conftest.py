"""Shared fixtures for ai_knowledge unit tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _app_context(app):
    with app.app_context():
        yield


@pytest.fixture(autouse=True)
def _transaction_rollback(db_session):
    yield
    db_session.rollback()


@pytest.fixture
def mock_ai_user():
    user = MagicMock()
    user.is_authenticated = True
    user.is_owner = False
    user.id = 7
    user.tenant_id = 1
    user.full_name = "Test User"
    user.has_permission.return_value = True
    with patch("flask_login.utils._get_user", return_value=user):
        yield user
