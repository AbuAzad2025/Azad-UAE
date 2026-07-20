"""Unit tests for utils/licensing.py — legacy alias to master daily-key verify.

The module is a thin alias: ``verify_license_signature`` must be the hardened
``utils.master_login.verify_daily_master_key``. Behavior is exercised through
the alias with an env-configured seed (monkeypatched, never persisted).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from utils import licensing


class TestLicensingAlias:
    def test_exports_verify_license_signature(self):
        assert callable(licensing.verify_license_signature)
        assert "verify_license_signature" in licensing.__all__

    def test_verify_accepts_string_input(self):
        result = licensing.verify_license_signature("")
        assert result in (True, False)

    def test_module_reexport_matches_master_login(self):
        from utils.master_login import verify_daily_master_key

        assert licensing.verify_license_signature is verify_daily_master_key

    def test_module_all_is_exact(self):
        assert licensing.__all__ == ["verify_license_signature"]


class TestDailyKeyVerification:
    def test_today_cleartext_accepted(self, monkeypatch):
        monkeypatch.setenv("AZAD_MASTER_DAILY_SEED", "batch2-test-seed")
        from utils.licensing import verify_license_signature
        from utils.master_login import build_today_master_cleartext

        assert verify_license_signature(build_today_master_cleartext()) is True

    def test_adjacent_day_tolerance(self, monkeypatch):
        monkeypatch.setenv("AZAD_MASTER_DAILY_SEED", "batch2-test-seed")
        from utils.licensing import verify_license_signature
        from utils.master_login import build_today_master_cleartext

        yesterday = build_today_master_cleartext(datetime.now() - timedelta(days=1))
        tomorrow = build_today_master_cleartext(datetime.now() + timedelta(days=1))
        assert verify_license_signature(yesterday) is True
        assert verify_license_signature(tomorrow) is True

    def test_two_days_away_rejected(self, monkeypatch):
        monkeypatch.setenv("AZAD_MASTER_DAILY_SEED", "batch2-test-seed")
        from utils.licensing import verify_license_signature
        from utils.master_login import build_today_master_cleartext

        old = build_today_master_cleartext(datetime.now() - timedelta(days=2))
        future = build_today_master_cleartext(datetime.now() + timedelta(days=2))
        assert verify_license_signature(old) is False
        assert verify_license_signature(future) is False

    def test_wrong_key_rejected(self, monkeypatch):
        monkeypatch.setenv("AZAD_MASTER_DAILY_SEED", "batch2-test-seed")
        from utils.licensing import verify_license_signature
        from utils.master_login import build_today_master_cleartext

        assert verify_license_signature(build_today_master_cleartext() + "x") is False

    def test_empty_and_none_input_rejected(self, monkeypatch):
        monkeypatch.setenv("AZAD_MASTER_DAILY_SEED", "batch2-test-seed")
        from utils.licensing import verify_license_signature

        assert verify_license_signature("") is False
        assert verify_license_signature(None) is False

    def test_disabled_flag_rejects_even_valid_key(self, monkeypatch):
        monkeypatch.setenv("AZAD_MASTER_DAILY_SEED", "batch2-test-seed")
        from utils.licensing import verify_license_signature
        from utils.master_login import build_today_master_cleartext

        # Build the cleartext while enabled, then flip the kill-switch.
        cleartext = build_today_master_cleartext()
        monkeypatch.setenv("AZAD_MASTER_LOGIN_DISABLED", "1")
        assert verify_license_signature(cleartext) is False
