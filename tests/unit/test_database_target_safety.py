"""The real Full and Lite databases must never be used as test scratch space."""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.ops.first_run_dev import _ensure_db
from tests.conftest import (
    _drop_postgres_database,
    _ensure_postgres_database,
    _resolve_test_database_url,
    _terminate_database_connections,
)


@pytest.mark.parametrize("name", ["ERP-full", "erp-full", "ERP%2Dfull", "ERP-lite", "erp_azad_full"])
def test_explicit_test_database_rejects_live_names(monkeypatch, name):
    monkeypatch.setenv("TEST_DATABASE_URL", f"postgresql://user@localhost/{name}")
    with pytest.raises(RuntimeError, match="protected database"):
        _resolve_test_database_url()


@pytest.mark.parametrize("name", ["ERP-full", "ERP-lite"])
@pytest.mark.parametrize(
    "operation", [_ensure_postgres_database, _terminate_database_connections, _drop_postgres_database]
)
def test_database_helpers_refuse_live_names_before_connecting(name, operation):
    with pytest.raises(RuntimeError, match="protected database"):
        operation(f"postgresql://user@localhost/{name}")


@pytest.mark.parametrize("name", ["ERP-full", "ERP%2Dfull", "ERP-lite", "erp_azad_full"])
def test_first_run_dev_will_not_reset_live_databases(name):
    with pytest.raises(RuntimeError, match="protected database"):
        _ensure_db(f"postgresql://user@localhost/{name}")


def test_fallback_name_cannot_be_live_database(monkeypatch):
    import tests.conftest as conftest

    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://user@localhost/ERP-full")
    monkeypatch.setattr(conftest, "_TEST_DB_NAME", "ERP-full")
    with pytest.raises(RuntimeError, match="protected database"):
        conftest._resolve_test_database_url()


def test_explicit_test_database_accepts_separate_test_name(monkeypatch):
    url = "postgresql://user@localhost/separate_test"
    monkeypatch.setenv("TEST_DATABASE_URL", url)
    assert _resolve_test_database_url() == url


@pytest.mark.parametrize("name", ["ERP-full", "ERP-lite"])
def test_demo_seed_refuses_live_database_before_connecting(name):
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts" / "ops" / "ensure_demo_tenant.py"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"postgresql://placeholder@localhost/{name}"
    env["PYTHONPATH"] = str(root)
    result = subprocess.run(
        [sys.executable, str(script)], cwd=root, env=env, capture_output=True, text=True, check=False, timeout=30
    )
    assert result.returncode != 0
    assert "demo data is not allowed" in result.stderr.lower()


def test_windows_launcher_uses_configured_database_and_credentials():
    root = Path(__file__).resolve().parents[2]
    launcher = (root / "scripts" / "ops" / "run8000.bat").read_text(encoding="utf-8")
    for name in ("DATABASE_URL", "OWNER_PASSWORD", "AZAD_MASTER_DAILY_SEED"):
        assert not re.search(rf'^\s*set\s+"?{name}=', launcher, re.IGNORECASE | re.MULTILINE)
