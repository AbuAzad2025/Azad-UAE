"""Cov4: owner_panel pure helpers — pricing, logos, backups, warnings."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from utils.owner_panel import (
    _latest_backup_by_tenant,
    _plan_monthly_price,
    _system_backup_status,
    _tenant_logo_display_url,
    evaluate_tenant_user_warnings,
    tenants_without_users_allowlist,
)


def test_plan_price_branches():
    assert _plan_monthly_price(None) == Decimal("0")  # line 33-34
    assert _plan_monthly_price("BASIC") == Decimal("199")
    assert _plan_monthly_price("unknown-plan") == Decimal("0")  # .get default


def test_logo_display_branches():
    t = SimpleNamespace(logo_url="tenant/logo.png")
    assert _tenant_logo_display_url(t, {"logo_url": "http://x/y.png"}) == "http://x/y.png"  # 40-41
    assert _tenant_logo_display_url(t, {"logo_url": "a/b.png"}) == "/static/a/b.png"  # 42-43
    assert _tenant_logo_display_url(SimpleNamespace(logo_url=""), {}) == ""  # 44


def test_latest_backup_skips_and_dedups(caplog):
    backups = [
        {"no_tenant": 1},
        {"tenant_id": "abc"},
        {"tenant_id": "7", "filename": "first"},
        {"tenant_id": 7, "filename": "second"},
    ]
    out = _latest_backup_by_tenant(backups)  # lines 47-60
    assert out[7]["filename"] == "first"


def test_system_backup_branches():
    assert _system_backup_status([])["status"] == "missing"  # 69-70
    b = [{"backup_scope": "system", "filename": "x"}]
    assert _system_backup_status(b)["status"] == "ok"  # 71-72
    b2 = [{"backup_scope": "tenant", "filename": "azad_backup_system_1.zip"}]
    assert _system_backup_status(b2)["status"] == "ok"


def test_allowlist_parsing(monkeypatch):
    monkeypatch.setenv("OWNER_PANEL_ALLOW_TENANTS_WITHOUT_USERS", " Nasrallah , Foo ")
    assert tenants_without_users_allowlist() == {"nasrallah", "foo"}  # 395-397


def test_evaluate_warnings_matrix(monkeypatch):
    monkeypatch.setenv("OWNER_PANEL_ALLOW_TENANTS_WITHOUT_USERS", "nasrallah")
    rows = [
        {"tenant": SimpleNamespace(id=1, is_active=False), "warn_slug": "x", "warn_no_users": True},
        {"tenant": SimpleNamespace(id=2, is_active=True), "warn_slug": "sync-test-1", "warn_no_users": True},
        {"tenant": SimpleNamespace(id=3, is_active=True), "warn_slug": "acme", "warn_no_users": False},
        {"tenant": SimpleNamespace(id=4, is_active=True), "warn_slug": "nasrallah", "warn_no_users": True},
        {"tenant": SimpleNamespace(id=5, is_active=True), "warn_slug": "other", "warn_no_users": True},
    ]
    fails, warns = evaluate_tenant_user_warnings(rows)  # lines 400-418
    assert warns == ["tenant nasrallah: no users"]
    assert fails == ["tenant other: no users"]
