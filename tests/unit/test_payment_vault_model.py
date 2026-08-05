"""Regression guard for ``PaymentVault.is_vault_accessible``.

Guards against the offset-naive/aware ``TypeError`` crash that occurred when
``last_access`` (loaded from a naive ``DateTime`` column) was subtracted from
``_utc_now()`` (tz-aware), and ensures ``None`` timestamps are tolerated.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from models.payment_vault import PaymentVault


def _make_vault(**kwargs):
    vault = PaymentVault(
        tenant_id=None,
        is_locked=False,
        **kwargs,
    )
    vault.set_vault_password("test-vault-pass")
    return vault


class TestIsVaultAccessible:
    def test_naive_last_access_does_not_raise(self):
        vault = _make_vault(auto_lock_minutes=30)
        vault.last_access = datetime.now(timezone.utc).replace(tzinfo=None)
        assert vault.is_vault_accessible() is True

    def test_aware_last_access_does_not_raise(self):
        vault = _make_vault(auto_lock_minutes=30)
        vault.last_access = datetime.now(timezone.utc)
        assert vault.is_vault_accessible() is True

    def test_none_last_access_is_safe(self):
        vault = _make_vault(auto_lock_minutes=30)
        vault.last_access = None
        assert vault.is_vault_accessible() is True

    def test_locked_vault_is_not_accessible(self):
        vault = _make_vault()
        vault.is_locked = True
        assert vault.is_vault_accessible() is False

    def test_stale_last_access_auto_locks(self):
        vault = _make_vault(auto_lock_minutes=30)
        vault.last_access = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=60)
        assert vault.is_vault_accessible() is False
        assert vault.is_locked is True
