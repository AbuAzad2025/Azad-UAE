from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _app_context(app):
    with app.app_context():
        yield
