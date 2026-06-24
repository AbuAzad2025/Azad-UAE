"""Shared fixtures for ai_knowledge unit tests."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _app_context(app):
    with app.app_context():
        yield


@pytest.fixture
def mock_ai_user(mocker):
    user = MagicMock()
    user.is_authenticated = True
    user.is_owner = False
    user.id = 7
    user.tenant_id = 1
    user.full_name = 'Test User'
    user.has_permission.return_value = True
    mocker.patch('flask_login.utils._get_user', return_value=user)
    return user
