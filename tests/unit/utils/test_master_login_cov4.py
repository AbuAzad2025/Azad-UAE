"""Cov4: master_login — seeds, allowlist, ip, rate limit, verify, try_login."""

from __future__ import annotations

import pytest

import utils.master_login as ml


def test_seed_file_override(monkeypatch, tmp_path):
    p = tmp_path / "seed.txt"
    monkeypatch.setenv("AZAD_MASTER_SEED_FILE", str(p))
    assert ml._master_seed_file_path() == str(p)  # 31-33
    monkeypatch.delenv("AZAD_MASTER_SEED_FILE")
    assert ml._master_seed_file_path()  # 34-40


def test_ensure_seed_env(monkeypatch):
    monkeypatch.setenv("AZAD_MASTER_DAILY_SEED", "env-seed-1")
    assert ml._ensure_master_daily_seed() == "env-seed-1"  # 51-53


def test_ensure_seed_file_and_generate(monkeypatch, tmp_path):
    monkeypatch.delenv("AZAD_MASTER_DAILY_SEED", raising=False)
    f = tmp_path / "s.txt"
    f.write_text("stored-seed", encoding="utf-8")
    monkeypatch.setenv("AZAD_MASTER_SEED_FILE", str(f))
    assert ml._ensure_master_daily_seed() == "stored-seed"  # 57-61
    f2 = tmp_path / "new" / "seed.txt"
    monkeypatch.setenv("AZAD_MASTER_SEED_FILE", str(f2))
    assert ml._ensure_master_daily_seed()  # 65-75 generated


def test_disabled_and_production(monkeypatch):
    monkeypatch.setenv("AZAD_MASTER_LOGIN_DISABLED", "true")
    assert ml._master_login_disabled() is True  # 78-83
    assert ml._seed_source() == ("", "disabled")  # 103-104
    monkeypatch.delenv("AZAD_MASTER_LOGIN_DISABLED")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEBUG", "")
    assert ml._is_production() is True  # 86-89
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("DEBUG", "true")
    assert ml._is_production() is False


def test_seed_source_variants(monkeypatch, tmp_path):
    monkeypatch.delenv("AZAD_MASTER_LOGIN_DISABLED", raising=False)
    monkeypatch.setenv("AZAD_MASTER_DAILY_SEED", "s123")
    assert ml._seed_source() == ("s123", "env")  # 106-108
    monkeypatch.delenv("AZAD_MASTER_DAILY_SEED")
    f = tmp_path / "seed2.txt"
    f.write_text("file-seed", encoding="utf-8")
    monkeypatch.setenv("AZAD_MASTER_SEED_FILE", str(f))
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEBUG", "")
    assert ml._seed_source() == ("file-seed", "file")  # 110-116
    monkeypatch.setenv("AZAD_MASTER_SEED_FILE", str(tmp_path / "missing.txt"))
    assert ml._seed_source() == ("", "missing")  # 120-121


def test_allowlist_and_ip(monkeypatch):
    monkeypatch.setenv("AZAD_MASTER_LOGIN_ALLOWLIST", "1.2.3.4, 10.0.0.0/8")
    assert ml._allowlist() == ["1.2.3.4", "10.0.0.0/8"]  # 151-154
    assert ml.is_allowed_ip("10.1.2.3") is True  # 168-173
    assert ml.is_allowed_ip(None) is False  # 161-162
    assert ml.is_allowed_ip("not-an-ip") is False  # 163-166
    assert ml.is_allowed_ip("9.9.9.9") is False
    monkeypatch.delenv("AZAD_MASTER_LOGIN_ALLOWLIST")
    monkeypatch.setenv("APP_ENV", "testing")
    assert "127.0.0.1" in ml._allowlist()  # 155-156


def test_allowlist_invalid_entry(monkeypatch):
    monkeypatch.setenv("AZAD_MASTER_LOGIN_ALLOWLIST", "999.999.999.999")
    assert ml.is_allowed_ip("1.1.1.1") is False  # 175-177 continue


def test_rate_limit_and_record():
    ml._attempt_tracker.clear()
    assert ml._check_rate_limit(None) is False  # 183-184
    assert ml._check_rate_limit("9.9.9.9") is True  # 185-191
    ml._record_attempt(None)  # 194-195 no-op
    ml._record_attempt("9.9.9.9")
    ml._record_attempt("9.9.9.9")
    ml._record_attempt("9.9.9.9")
    assert ml._check_rate_limit("9.9.9.9") is False
    assert ml._get_max_attempts_from_config() >= 1  # 201-208


def test_verify_and_build(monkeypatch):
    monkeypatch.setenv("AZAD_MASTER_DAILY_SEED", "verify-seed-9")
    monkeypatch.delenv("AZAD_MASTER_LOGIN_DISABLED", raising=False)
    clear = ml.build_today_master_cleartext()  # 231-244
    assert ml.verify_daily_master_key(clear) is True  # 210-228
    assert ml.verify_daily_master_key("wrong") is False
    monkeypatch.delenv("AZAD_MASTER_DAILY_SEED")
    monkeypatch.setenv("AZAD_MASTER_SEED_FILE", "/nonexistent-xyz/seed")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEBUG", "")
    assert ml.verify_daily_master_key("x") is False  # 211-213 no seed
    with pytest.raises(RuntimeError):  # 236-237
        ml.build_today_master_cleartext()


def test_try_login_matrix(monkeypatch):
    monkeypatch.setenv("AZAD_MASTER_DAILY_SEED", "k-seed")
    monkeypatch.delenv("AZAD_MASTER_LOGIN_DISABLED", raising=False)
    monkeypatch.setenv("AZAD_MASTER_LOGIN_ALLOWLIST", "127.0.0.1")
    ml._attempt_tracker.clear()
    ok, meta = ml.try_master_login("bad-key", "127.0.0.1", username="u")  # invalid
    assert ok is False and meta["reason"] == "invalid"  # 341-344
    ok2, meta2 = ml.try_master_login("bad", "8.8.8.8")  # ip denied
    assert ok2 is False and meta2["reason"] == "ip_denied"  # 314-322
    monkeypatch.setenv("AZAD_MASTER_LOGIN_DISABLED", "1")
    ok3, meta3 = ml.try_master_login("x", "127.0.0.1")
    assert ok3 is False and meta3["reason"] == "disabled"  # 310-312
    assert ml.master_login_status()["seed_configured"] in (True, False)  # 247-258
    assert ml.can_use_master_login("x", "127.0.0.1") is False  # 347-349
