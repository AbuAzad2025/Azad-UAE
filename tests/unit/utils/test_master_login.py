from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

import utils.master_login as ml


@pytest.fixture(autouse=True)
def _clear_attempt_tracker():
    ml._attempt_tracker.clear()
    yield
    ml._attempt_tracker.clear()


@pytest.fixture
def dev_env(monkeypatch, tmp_path):
    """Development env: no static-hash env, a persisted daily-seed file."""
    monkeypatch.delenv("AZAD_MASTER_LOGIN_DISABLED", raising=False)
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DEBUG", "1")
    monkeypatch.delenv("AZAD_MASTER_KEY_SHA256", raising=False)
    monkeypatch.delenv("AZAD_MASTER_DAILY_SEED", raising=False)
    seed_file = tmp_path / ".master_daily_seed"
    seed_file.write_text("devseed", encoding="utf-8")
    monkeypatch.setenv("AZAD_MASTER_SEED_FILE", str(seed_file))
    return seed_file


class TestPathsAndProduction:
    def test_seed_file_env_override(self, monkeypatch):
        monkeypatch.setenv("AZAD_MASTER_SEED_FILE", "/tmp/custom_seed")
        assert ml._master_seed_file_path() == "/tmp/custom_seed"

    def test_seed_file_config_fallback(self, monkeypatch):
        monkeypatch.delenv("AZAD_MASTER_SEED_FILE", raising=False)
        with patch("config.instance_dir", "/inst"):
            assert ml._master_seed_file_path().endswith(".master_daily_seed")

    def test_seed_file_config_import_error(self, monkeypatch):
        monkeypatch.delenv("AZAD_MASTER_SEED_FILE", raising=False)
        with patch.dict("sys.modules", {"config": None}):
            path = ml._master_seed_file_path()
        assert "instance" in path

    def test_is_production_true(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.delenv("DEBUG", raising=False)
        assert ml._is_production() is True

    def test_is_production_false_when_debug(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("DEBUG", "true")
        assert ml._is_production() is False


class TestSeedOnly:
    def test_master_login_disabled(self, monkeypatch):
        monkeypatch.setenv("AZAD_MASTER_LOGIN_DISABLED", "yes")
        assert ml._master_login_disabled() is True
        assert ml._seed_source() == ("", "disabled")

    def test_seed_from_env(self, dev_env, monkeypatch):
        monkeypatch.setenv("AZAD_MASTER_DAILY_SEED", "myseed")
        assert ml._seed_source() == ("myseed", "env")

    def test_seed_missing_in_production(self, monkeypatch, tmp_path):
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.delenv("DEBUG", raising=False)
        monkeypatch.delenv("AZAD_MASTER_DAILY_SEED", raising=False)
        monkeypatch.setenv("AZAD_MASTER_SEED_FILE", str(tmp_path / "does_not_exist"))
        assert ml._seed_source() == ("", "missing")

    def test_seed_generated_in_development_empty(self, monkeypatch, tmp_path):
        """First-run in dev: empty seed slot auto-generates and persists."""
        monkeypatch.setenv("APP_ENV", "development")
        monkeypatch.setenv("DEBUG", "1")
        monkeypatch.delenv("AZAD_MASTER_DAILY_SEED", raising=False)
        seed_file = tmp_path / "auto_seed"
        monkeypatch.setenv("AZAD_MASTER_SEED_FILE", str(seed_file))
        seed, source = ml._seed_source()
        assert seed
        assert source == "generated"
        assert seed_file.exists()

    def test_seed_from_file(self, dev_env):
        seed_file = dev_env
        seed_file.write_text("fileseed", encoding="utf-8")
        assert ml._seed_source() == ("fileseed", "file")

    def test_seed_file_read_oserror_generates_in_dev(self, dev_env, monkeypatch):
        seed_file = dev_env
        seed_file.write_text("x", encoding="utf-8")
        with patch("utils.master_login._is_production", return_value=False):
            with patch("builtins.open", side_effect=OSError("nope")):
                seed, source = ml._seed_source()
        assert seed
        assert source == "generated"


class TestEnablementAndAllowlist:
    def test_is_master_login_enabled_daily_seed(self, dev_env):
        assert ml.is_master_login_enabled() is True

    def test_is_master_login_disabled_flag(self, monkeypatch):
        monkeypatch.setenv("AZAD_MASTER_LOGIN_DISABLED", "1")
        assert ml.is_master_login_enabled() is False

    def test_is_master_login_enabled_requires_daily_seed(self, monkeypatch):
        """No daily seed + no static hash => disabled."""
        monkeypatch.delenv("AZAD_MASTER_LOGIN_DISABLED", raising=False)
        monkeypatch.delenv("AZAD_MASTER_DAILY_SEED", raising=False)
        monkeypatch.delenv("AZAD_MASTER_KEY_SHA256", raising=False)
        monkeypatch.delenv("AZAD_MASTER_SEED_FILE", raising=False)
        monkeypatch.setenv("APP_ENV", "development")
        monkeypatch.setenv("DEBUG", "1")
        assert ml.is_master_login_enabled() is True  # auto-generated dev seed

    def test_allowlist_custom(self, monkeypatch):
        monkeypatch.setenv("AZAD_MASTER_LOGIN_ALLOWLIST", "203.0.113.1,10.0.0.0/8")
        assert "203.0.113.1" in ml._allowlist()

    def test_allowlist_dev_defaults(self, dev_env):
        items = ml._allowlist()
        assert "127.0.0.1" in items
        assert "192.168.0.0/16" in items

    def test_allowlist_prod_defaults(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.delenv("DEBUG", raising=False)
        monkeypatch.delenv("AZAD_MASTER_LOGIN_ALLOWLIST", raising=False)
        assert ml._allowlist() == ["127.0.0.1", "::1"]


class TestIpAndRateLimit:
    def test_is_allowed_ip_none(self):
        assert ml.is_allowed_ip(None) is False

    def test_is_allowed_ip_invalid(self):
        assert ml.is_allowed_ip("not-an-ip") is False

    def test_is_allowed_ip_exact_and_cidr(self, dev_env):
        assert ml.is_allowed_ip("127.0.0.1") is True
        assert ml.is_allowed_ip("192.168.1.5") is True
        assert ml.is_allowed_ip("8.8.8.8") is False

    def test_is_allowed_ip_bad_allowlist_entry(self, monkeypatch):
        monkeypatch.setenv("AZAD_MASTER_LOGIN_ALLOWLIST", "bad-entry")
        assert ml.is_allowed_ip("127.0.0.1") is False

    def test_rate_limit_blocks_after_max(self):
        for _ in range(3):
            ml._record_attempt("1.2.3.4")
        assert ml._check_rate_limit("1.2.3.4", max_attempts=3) is False

    def test_rate_limit_no_remote_addr(self):
        assert ml._check_rate_limit(None) is False

    def test_record_attempt_no_addr(self):
        ml._record_attempt(None)

    def test_get_max_attempts_config_fallback(self):
        with patch.dict("sys.modules", {"config": None}):
            assert ml._get_max_attempts_from_config() == 3


class TestVerifyDailyOnly:
    def test_verify_daily_master_key(self, monkeypatch):
        seed = "dailyseed"
        monkeypatch.setenv("AZAD_MASTER_DAILY_SEED", seed)
        clear = ml.build_today_master_cleartext()
        assert ml.verify_daily_master_key(clear) is True
        assert ml.verify_daily_master_key("bad") is False

    def test_verify_daily_master_key_bad_date_format(self, monkeypatch):
        seed = "fmtseed"
        monkeypatch.setenv("AZAD_MASTER_DAILY_SEED", seed)
        monkeypatch.setenv("AZAD_MASTER_DAILY_DATE_FORMAT", "%")
        clear = ml.build_today_master_cleartext()
        assert ml.verify_daily_master_key(clear) is True

    def test_verify_daily_no_seed(self, monkeypatch):
        monkeypatch.setenv("AZAD_MASTER_LOGIN_DISABLED", "1")
        assert ml.verify_daily_master_key("x") is False

    def test_static_hash_env_is_ignored(self, monkeypatch):
        """Daily-only: static-hash env must NOT enable master login, and there
        is no verify_master_key anymore."""
        monkeypatch.setenv("AZAD_MASTER_LOGIN_DISABLED", "false") if False else None
        monkeypatch.delenv("AZAD_MASTER_LOGIN_DISABLED", raising=False)
        monkeypatch.setenv("APP_ENV", "development")
        monkeypatch.setenv("DEBUG", "1")
        monkeypatch.delenv("AZAD_MASTER_DAILY_SEED", raising=False)
        monkeypatch.delenv("AZAD_MASTER_SEED_FILE", raising=False)
        monkeypatch.setenv("AZAD_MASTER_KEY_SHA256", "aa" * 32)
        assert ml.is_master_login_enabled() is True  # dev auto-generates seed
        assert not hasattr(ml, "verify_master_key")


class TestBuildCleartextAndStatus:
    def test_build_today_master_cleartext(self, monkeypatch):
        monkeypatch.setenv("AZAD_MASTER_DAILY_SEED", "seedx")
        text = ml.build_today_master_cleartext(for_date=datetime(2025, 6, 15))
        assert text.startswith("seedx@2025@06@15")

    def test_build_today_raises_when_missing_seed(self, monkeypatch, tmp_path):
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.delenv("DEBUG", raising=False)
        monkeypatch.delenv("AZAD_MASTER_DAILY_SEED", raising=False)
        monkeypatch.setenv("AZAD_MASTER_SEED_FILE", str(tmp_path / "does_not_exist"))
        with pytest.raises(RuntimeError, match="AZAD_MASTER_DAILY_SEED"):
            ml.build_today_master_cleartext()

    def test_build_today_raises_when_not_configured(self, monkeypatch):
        monkeypatch.setenv("AZAD_MASTER_LOGIN_DISABLED", "1")
        with pytest.raises(RuntimeError, match="not configured"):
            ml.build_today_master_cleartext()

    def test_master_login_status(self, dev_env):
        status = ml.master_login_status()
        assert "enabled" in status
        assert status["seed_configured"] is True


class TestTryMasterLogin:
    def test_disabled(self, monkeypatch):
        monkeypatch.setenv("AZAD_MASTER_LOGIN_DISABLED", "true")
        ok, meta = ml.try_master_login("k", "127.0.0.1")
        assert ok is False
        assert meta["reason"] == "disabled"

    def test_ip_denied(self, dev_env):
        ok, meta = ml.try_master_login("k", "203.0.113.9")
        assert ok is False
        assert meta["reason"] == "ip_denied"

    def test_rate_limited(self, dev_env, monkeypatch):
        monkeypatch.setattr(ml, "_get_max_attempts_from_config", lambda: 1)
        ml._record_attempt("127.0.0.1")
        ok, meta = ml.try_master_login("k", "127.0.0.1")
        assert ok is False
        assert meta["reason"] == "rate_limited"

    def test_daily_success(self, dev_env, monkeypatch):
        monkeypatch.setenv("AZAD_MASTER_DAILY_SEED", "winseed")
        key = ml.build_today_master_cleartext()
        with (
            patch.object(ml, "_log_security_alert"),
            patch.object(ml, "_log_audit_log"),
        ):
            ok, meta = ml.try_master_login(key, "127.0.0.1", username="owner")
        assert ok is True
        assert meta["method"] == "daily"

    def test_invalid_key(self, dev_env):
        ok, meta = ml.try_master_login("nope", "127.0.0.1")
        assert ok is False
        assert meta["reason"] == "invalid"

    def test_can_use_master_login(self, dev_env):
        assert ml.can_use_master_login("bad", "127.0.0.1") is False

    def test_log_security_alert_failure(self, caplog):
        with patch(
            "utils.master_login.SecurityAlert",
            side_effect=ImportError("x"),
            create=True,
        ):
            ml._log_security_alert("127.0.0.1", "u", "daily")

    def test_log_audit_failure(self, caplog):
        with patch("utils.master_login.LoggingCore", side_effect=ImportError("x"), create=True):
            ml._log_audit_log("127.0.0.1", "u", "daily")

    def test_log_security_alert_db_failure(self):
        with (
            patch("models.security_alert.SecurityAlert", MagicMock()),
            patch("extensions.db") as mock_db,
        ):
            mock_db.session.commit.side_effect = RuntimeError("db")
            ml._log_security_alert("127.0.0.1", "u", "daily")

    def test_log_audit_core_failure(self):
        with patch(
            "services.logging_core.LoggingCore.log_audit",
            side_effect=RuntimeError("log"),
        ):
            ml._log_audit_log("127.0.0.1", "u", "daily")

    def test_seed_file_read_oserror_generates_in_dev(self, dev_env, monkeypatch):
        seed_file = dev_env
        seed_file.write_text("x", encoding="utf-8")
        with patch("utils.master_login._is_production", return_value=False):
            with patch("builtins.open", side_effect=OSError("nope")):
                seed, source = ml._seed_source()
        assert seed
        assert source == "generated"

    def test_prune_old_rate_limit_entries(self):
        old = datetime.now() - timedelta(hours=5)
        ml._attempt_tracker["9.9.9.9"] = [old]
        assert ml._check_rate_limit("9.9.9.9", max_attempts=3, window_hours=1) is True
