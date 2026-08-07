"""Template coverage for the secret payment vault (owner-only) pages.

The vault is a *platform* resource: every detail route resolves it via
``PaymentVault.get_platform_vault()`` (``tenant_id IS NULL``) and lists
Donation/PackagePurchase records with ``tenant_id=None``. These pages are
owner-only and require an unlocked vault, so the base smoke suite never hits
them. This module logs in as the platform owner (no active tenant selected)
and renders every ``payment_vault/*.html`` template with real records.

WHY COMMITTED DATA: ``tests/conftest.py::db_session`` wraps all fixture
writes in a savepoint (``session.begin_nested()``). ``commit()`` only
releases that savepoint, so fixture-created records are never visible to the
test client's request sessions (separate connection). ``committed_platform_data``
therefore seeds records through the app's own ``atomic_transaction`` in a
fresh app context — a real DB commit that every request session can see.

WHY NO ACTIVE TENANT: the auth login flow stores ``active_tenant_id`` in the
Flask session. The factory ``before_request`` propagates it to
``g.active_tenant_id``, which the ORM scoping layer uses to filter queries.
Platform vault records have ``tenant_id=None``, so they become invisible when
``active_tenant_id`` points to a real tenant. ``vault_owner_client`` clears
this session key after login so the owner sees platform-level data.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest


@pytest.fixture
def vault_owner_client(owner_client):
    """``owner_client`` with ``active_tenant_id`` cleared from the session.

    After login the Flask session retains ``active_tenant_id=sample_tenant.id``
    which causes ORM scoping to filter platform-level queries (``tenant_id IS
    NULL``) against the tenant ID — making them invisible. Clearing this key
    via ``session_transaction`` ensures the owner operates in "no active tenant"
    mode without needing a request context.
    """
    from utils.tenanting import ACTIVE_TENANT_SESSION_KEY

    with owner_client.session_transaction() as sess:
        sess.pop(ACTIVE_TENANT_SESSION_KEY, None)
    return owner_client


@pytest.fixture(scope="module")
def committed_platform_data(app):
    """Committed platform-scoped vault, package, purchase and donation.

    Runs in a *fresh* app context so ``atomic_transaction`` performs a real DB
    commit without touching the ``db_session`` fixture's savepoint. Because the
    commit happens outside any request context the ORM write guard is skipped,
    so ``tenant_id=None`` on platform records is preserved.
    """
    from extensions import db
    from models.donation import Donation
    from models.package import Package, PackagePurchase
    from models.payment_vault import PaymentVault
    from utils.db_safety import atomic_transaction

    unique = str(uuid.uuid4())[:8]

    with app.app_context():
        with atomic_transaction("test_seed_vault"):
            vault = PaymentVault(
                tenant_id=None,
                vault_name="Test Payment Vault",
                is_locked=False,
                last_access=datetime.now(UTC),
                failed_attempts=0,
                max_failed_attempts=3,
                auto_lock_minutes=30,
                min_donation_amount=Decimal("10.00"),
                max_donation_amount=Decimal("10000.00"),
                daily_limit=Decimal("50000.00"),
                bank_name="Test Bank",
                bank_currency="USD",
                donation_title_ar="ادعم مشروعنا",
                donation_title_en="Support Us",
            )
            vault.set_vault_password("test-vault-pass")
            db.session.add(vault)
            db.session.flush()
            vault_id = vault.id

        with atomic_transaction("test_seed_package"):
            package = Package(
                name_ar=f"باقة اختبار {unique}",
                name_en=f"Test Package {unique}",
                slug=f"test-package-{unique}",
                price=Decimal("99.000"),
                currency="USD",
                description_ar="باقة اختبار",
                description_en="Test package",
                is_active=True,
                is_featured=False,
                sort_order=0,
                support_duration_months=3,
            )
            db.session.add(package)
            db.session.flush()
            package_id = package.id

            purchase = PackagePurchase(
                package_id=package_id,
                customer_name="Test Customer",
                customer_email="customer@test.com",
                customer_phone="0555000001",
                company_name="Test Co",
                payment_method="crypto",
                payment_status="completed",
                amount_paid=Decimal("99.000"),
                currency="USD",
                transaction_id=f"TXN-{unique}",
                activation_status="activated",
                activation_date=datetime.now(UTC),
            )
            db.session.add(purchase)
            db.session.flush()
            purchase_id = purchase.id

        with atomic_transaction("test_seed_donation"):
            donation = Donation(
                tenant_id=None,
                amount_usd=Decimal("50.00"),
                payment_method="crypto",
                crypto_type="btc",
                status="completed",
                donor_name="Test Donor",
                donor_email="donor@test.com",
                donor_message="Keep it up",
                transaction_type="donation",
            )
            db.session.add(donation)
            db.session.flush()
            donation_id = donation.id

    return SimpleNamespace(
        vault_id=vault_id,
        package_id=package_id,
        purchase_id=purchase_id,
        donation_id=donation_id,
    )


class TestPaymentVaultTemplates:
    """Every payment_vault/*.html template renders for the platform owner."""

    @pytest.mark.parametrize(
        ("url", "template"),
        [
            ("/payment-vault/", "payment_vault/index.html"),
            ("/payment-vault/unlock", "payment_vault/unlock.html"),
            ("/payment-vault/dashboard", "payment_vault/dashboard.html"),
            ("/payment-vault/settings", "payment_vault/settings.html"),
            ("/payment-vault/donations", "payment_vault/donations.html"),
            ("/payment-vault/packages-management", "payment_vault/packages.html"),
            ("/payment-vault/reports", "payment_vault/reports.html"),
            ("/payment-vault/cards", "payment_vault/cards.html"),
            ("/payment-vault/change-password", "payment_vault/change_password.html"),
            ("/payment-vault/purchases", "payment_vault/purchases.html"),
        ],
    )
    def test_vault_pages_render(
        self,
        committed_platform_data,
        vault_owner_client,
        url,
        template,
    ):
        resp = vault_owner_client.get(url, follow_redirects=False)
        assert resp.status_code == 200, f"{url} returned {resp.status_code}"

    def test_vault_package_edit_renders(self, committed_platform_data, vault_owner_client):
        url = f"/payment-vault/package/{committed_platform_data.package_id}/edit"
        resp = vault_owner_client.get(url, follow_redirects=False)
        assert resp.status_code == 200, f"{url} returned {resp.status_code}"

    def test_vault_purchase_detail_renders(self, committed_platform_data, vault_owner_client):
        url = f"/payment-vault/purchase/{committed_platform_data.purchase_id}"
        resp = vault_owner_client.get(url, follow_redirects=False)
        assert resp.status_code == 200, f"{url} returned {resp.status_code}"

    def test_vault_donation_detail_renders(self, committed_platform_data, vault_owner_client):
        url = f"/payment-vault/donation/{committed_platform_data.donation_id}"
        resp = vault_owner_client.get(url, follow_redirects=False)
        assert resp.status_code == 200, f"{url} returned {resp.status_code}"
