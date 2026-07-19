"""Shared fixtures for Odoo-style business flow tours.

All tours share a common Playwright page and pre-loaded auth state
for the target role.
"""

import json
import os
import pytest

BASE_URL = os.environ.get("PLAYWRIGHT_BASE_URL", "http://localhost:5000")
STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "auth")


def _load_state(role_slug):
    path = os.path.join(STATE_DIR, f"{role_slug}_state.json")
    if not os.path.exists(path):
        pytest.skip(
            f"Auth state file not found: {path}. Run: python scripts/auth/setup_test_users.py"
        )
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def browser_context_args():
    return {
        "base_url": BASE_URL,
        "locale": "ar-AE",
        "viewport": {"width": 1440, "height": 900},
    }


@pytest.fixture(scope="module")
def cashier_context(browser):
    state = _load_state("cashier")
    context = browser.new_context(
        storage_state=json.dumps(state),
        base_url=BASE_URL,
        locale="ar-AE",
    )
    yield context
    context.close()


@pytest.fixture(scope="module")
def manager_context(browser):
    state = _load_state("store_manager")
    context = browser.new_context(
        storage_state=json.dumps(state),
        base_url=BASE_URL,
        locale="ar-AE",
    )
    yield context
    context.close()


@pytest.fixture(scope="module")
def owner_context(browser):
    state = _load_state("tenant_owner")
    context = browser.new_context(
        storage_state=json.dumps(state),
        base_url=BASE_URL,
        locale="ar-AE",
    )
    yield context
    context.close()


@pytest.fixture(scope="module")
def admin_context(browser):
    state = _load_state("super_admin")
    context = browser.new_context(
        storage_state=json.dumps(state),
        base_url=BASE_URL,
        locale="ar-AE",
    )
    yield context
    context.close()
