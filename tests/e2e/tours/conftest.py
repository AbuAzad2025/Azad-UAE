"""Shared fixtures for Odoo-style business flow tours.

All tours share a common Playwright page and pre-loaded auth state
for the target role.

Blocking behavior
-----------------
Tours are **blocking** in CI: ``.github/workflows/ci.yml`` runs

    pytest tests/e2e/tours/ -v --tb=short --reporter=list --base-url=...

and ``npm run test:tours`` (playwright) with ``--reporter=list``.
Both commands exit non-zero on any failure, so the ``e2e-tours`` job
fails the whole workflow (no ``continue-on-error``). See
``scripts/playwright.config.json`` and ``package.json``.

Python tours use ``pytest-playwright``; if the plugin is not installed
the fixtures below gracefully ``pytest.skip`` so that
``pytest tests/e2e -q --collect-only`` still shows the 4 e2e suites
without error, while ``pytest tests/e2e/tours -q`` is discoverable as a
separate suite.
"""

import json
import os

import pytest

BASE_URL = os.environ.get("PLAYWRIGHT_BASE_URL", "http://localhost:5000")
STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "auth")

# Graceful fallback when pytest-playwright is not installed (local dev without
# browser deps). This makes ``pytest tests/e2e -q`` not error out on missing
# ``browser`` fixture; tours will simply be skipped.
try:
    import pytest_playwright  # noqa: F401  # type: ignore

    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False

    @pytest.fixture(scope="session")
    def browser():  # type: ignore[no-redef]
        pytest.skip(
            "pytest-playwright not installed — tours require `pip install pytest-playwright` "
            "and `playwright install chromium`. Skipping tour."
        )

    @pytest.fixture(scope="session")
    def playwright():  # type: ignore[no-redef]
        pytest.skip("playwright not installed — skipping tour")


def _load_state(role_slug):
    path = os.path.join(STATE_DIR, f"{role_slug}_state.json")
    if not os.path.exists(path):
        pytest.skip(f"Auth state file not found: {path}. Run: python scripts/auth/setup_test_users.py")
    with open(path, encoding="utf-8") as f:
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
        storage_state=state,
        base_url=BASE_URL,
        locale="ar-AE",
    )
    yield context
    context.close()


@pytest.fixture(scope="module")
def manager_context(browser):
    state = _load_state("store_manager")
    context = browser.new_context(
        storage_state=state,
        base_url=BASE_URL,
        locale="ar-AE",
    )
    yield context
    context.close()


@pytest.fixture(scope="module")
def owner_context(browser):
    state = _load_state("tenant_owner")
    context = browser.new_context(
        storage_state=state,
        base_url=BASE_URL,
        locale="ar-AE",
    )
    yield context
    context.close()


@pytest.fixture(scope="module")
def admin_context(browser):
    state = _load_state("super_admin")
    context = browser.new_context(
        storage_state=state,
        base_url=BASE_URL,
        locale="ar-AE",
    )
    yield context
    context.close()
