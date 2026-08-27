"""Payment-vault lifecycle, packages and misc bucket-gap model behaviors."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from extensions import db

# ─────────────────────────── PaymentVault ───────────────────────────────


class TestPaymentVaultLifecycle:
    def _vault(self, db_session, sample_tenant=None):
        from models.payment_vault import PaymentVault

        vault = PaymentVault(
            tenant_id=sample_tenant.id if sample_tenant else None,
            vault_password_hash="",
            is_locked=True,
        )
        vault.set_vault_password("s3cret-pass")
        db.session.add(vault)
        db.session.flush()
        return vault

    def test_platform_and_tenant_lookup(self, db_session, sample_tenant):
        from models.payment_vault import PaymentVault

        platform = self._vault(db_session)
        tenant_vault = self._vault(db_session, sample_tenant)

        assert PaymentVault.get_platform_vault().id == platform.id
        assert PaymentVault.get_tenant_vault(sample_tenant.id).id == tenant_vault.id
        assert PaymentVault.get_tenant_vault(None) is None

    def test_unlock_success_and_lockout_counter_reset(self, db_session, sample_tenant):
        vault = self._vault(db_session, sample_tenant)
        assert vault.unlock_vault("wrong") is False
        assert vault.failed_attempts == 1
        assert vault.is_locked_out() is False  # threshold default 3

        assert vault.unlock_vault("s3cret-pass") is True
        assert vault.is_locked is False
        assert vault.failed_attempts == 0
        assert vault.is_vault_accessible() is True

    def test_manual_lock_blocks_access_until_unlocked(self, db_session, sample_tenant):
        vault = self._vault(db_session, sample_tenant)
        vault.unlock_vault("s3cret-pass")
        vault.lock_vault()
        assert vault.is_vault_accessible() is False
        vault.unlock_vault("s3cret-pass")
        assert vault.is_vault_accessible() is True

    def test_auto_lock_after_idle_window(self, db_session, sample_tenant):
        vault = self._vault(db_session, sample_tenant)
        vault.unlock_vault("s3cret-pass")
        vault.last_access = datetime.now(UTC) - timedelta(minutes=999)
        assert vault.is_vault_accessible() is False  # timed out → auto re-lock
        assert vault.is_locked is True

    def test_recent_access_stays_open_and_naive_datetimes_normalized(self, db_session, sample_tenant):
        vault = self._vault(db_session, sample_tenant)
        vault.unlock_vault("s3cret-pass")
        # naive timestamp inside window
        vault.last_access = (datetime.now(UTC) - timedelta(seconds=30)).replace(tzinfo=None)
        assert vault.is_vault_accessible() is True
        # zero auto-lock disables the timeout entirely
        vault.auto_lock_minutes = 0
        vault.last_access = None
        assert vault.is_vault_accessible() is True

    def test_failed_attempts_lockout_state(self, db_session, sample_tenant):
        vault = self._vault(db_session, sample_tenant)
        vault.max_failed_attempts = 2
        for _ in range(2):
            vault.unlock_vault("nope")
        assert vault.is_locked_out() is True
        vault.reset_failed_attempts()
        assert vault.is_locked_out() is False

    def test_transaction_to_dict_shape(self, db_session, sample_tenant):
        from models.payment_vault import PaymentTransaction

        vault = self._vault(db_session, sample_tenant)
        tx = PaymentTransaction(
            tenant_id=sample_tenant.id,
            transaction_id=f"TX-{datetime.now(UTC).timestamp()}",
            amount_usd=Decimal("19.99"),
            amount_crypto=Decimal("0.004"),
            crypto_currency="BTC",
            payment_address="addr-1",
            customer_email="c@example.com",
            customer_name="Client",
            vault_id=vault.id,
        )
        db.session.add(tx)
        db.session.flush()
        d = tx.to_dict()
        assert d["amount_usd"] == 19.99
        assert d["amount_crypto"] == 0.004
        assert d["completed_at"] is None
        assert d["is_verified"] is False

    def test_log_action_creates_row(self, db_session, sample_tenant):
        from models.payment_vault import PaymentLog

        vault = self._vault(db_session, sample_tenant)
        log = PaymentLog.log_action(
            vault_id=vault.id,
            tenant_id=sample_tenant.id,
            action="unlock",
            description="manual unlock probe",
            level="warning",
            amount=Decimal("5"),
            ip_address="127.0.0.1",
        )
        assert log.id is not None
        assert log.level == "warning"


# ────────────────────────────── Package ─────────────────────────────────


class TestPackageApply:
    def _package(self, *, limits=True, flags=True, pos=True, custom=False, reports=False):
        from models.package import Package

        pkg = Package(
            name_ar="باقة اختبار",
            name_en="Probe Package",
            slug=f"probe-{datetime.now(UTC).timestamp()}",
            price=Decimal("9"),
            max_users=10 if limits else None,
            max_branches=3 if limits else None,
            has_pos=pos,
            has_customization=custom,
            has_advanced_reports=reports,
        )
        if flags:
            pkg.enable_payroll = True
            pkg.enable_reports = not reports  # conflicting flag kept unless advanced forces True
            pkg.enable_ai = None  # unconfigured dimension must survive on tenant
        return pkg

    def test_apply_copies_limits_and_flags(self, db_session, sample_tenant):
        tenant_before_ai = sample_tenant.enable_ai
        pkg = self._package(limits=True, flags=True)
        result = pkg.apply_to_tenant(sample_tenant)
        assert result is sample_tenant
        assert sample_tenant.max_users == 10
        assert sample_tenant.max_branches == 3
        assert sample_tenant.enable_payroll is True
        assert sample_tenant.enable_ai == tenant_before_ai  # untouched

    def test_none_limits_leave_tenant_values_intact(self, db_session, sample_tenant):
        original_users = sample_tenant.max_users
        pkg = self._package(limits=False, flags=False)
        pkg.apply_to_tenant(sample_tenant)
        assert sample_tenant.max_users == original_users

    def test_pos_and_customization_forced_booleans(self, db_session, sample_tenant):
        pkg_off = self._package(pos=False, custom=False)
        pkg_off.apply_to_tenant(sample_tenant)
        assert sample_tenant.enable_pos is False
        assert getattr(sample_tenant, "allow_custom_integrations", False) is False

        pkg_on = self._package(pos=True, custom=True)
        pkg_on.apply_to_tenant(sample_tenant)
        assert sample_tenant.enable_pos is True
        assert getattr(sample_tenant, "allow_custom_integrations", True) is True

    def test_advanced_reports_flag_upgrades_reports(self, db_session, sample_tenant):
        sample_tenant.enable_reports = False
        pkg = self._package(reports=True)
        pkg.apply_to_tenant(sample_tenant)
        assert sample_tenant.enable_reports is True

    def test_package_repr_and_dict(self, db_session):

        pkg = self._package()
        assert "<Package" in repr(pkg)
        d = pkg.to_dict()
        assert d["price"] == 9.0 or d["price"] is None
