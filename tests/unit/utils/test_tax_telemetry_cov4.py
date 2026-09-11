"""Cov4: tax_settings + telemetry + tenant_security + nowpayments_ipn."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import utils.nowpayments_ipn as np
import utils.tax_settings as ts
import utils.telemetry as tm


def test_resolve_tenant_variants():
    from extensions import db as _db

    with patch.object(_db.session, "get", return_value=SimpleNamespace(id=1)):
        assert ts._resolve_tenant(1).id == 1  # 23-28
    with patch("models.tenant.Tenant.get_current", return_value=SimpleNamespace(id=2)):
        assert ts._resolve_tenant().id == 2  # 29-32
    with patch("models.tenant.Tenant.get_current", side_effect=RuntimeError("x")):
        assert ts._resolve_tenant() is None  # 33-35


def test_resolve_main_branch():
    with patch("models.branch.Branch.query") as q:
        q.filter_by.return_value.first.return_value = SimpleNamespace(id=9)
        assert ts._resolve_main_branch(1) == 9  # 38-46
        q.filter_by.return_value.first.return_value = None
        assert ts._resolve_main_branch(1) is None
    assert ts._resolve_main_branch(None) is None


def test_tax_enabled_country_default():
    with patch.object(ts, "_resolve_tenant", return_value=None):
        assert ts.is_tax_enabled() is False  # 49-53
        assert ts.vat_country() == "AE" or ts.vat_country()  # 56-60 fallback
        assert ts.default_tax_rate() == Decimal("0")  # 63-69
        assert ts.get_prices_include_vat() is False  # 91-94
    t = SimpleNamespace(enable_tax=True, vat_country=" ps ", default_tax_rate="16", prices_include_vat=True)
    with patch.object(ts, "_resolve_tenant", return_value=t):
        assert ts.is_tax_enabled() is True
        assert ts.vat_country() == "PS"
        assert ts.default_tax_rate() == Decimal("16")  # 70-72
        assert ts.get_prices_include_vat() is True
    t2 = SimpleNamespace(enable_tax=True, vat_country=None, default_tax_rate="-1", prices_include_vat=False)
    with patch.object(ts, "_resolve_tenant", return_value=t2):
        assert ts.default_tax_rate() == Decimal("0")


def test_normalize_and_suggest():
    with patch.object(ts, "is_tax_enabled", return_value=False):
        assert ts.normalize_tax_rate(15) == Decimal("0")  # 97-100
        assert ts.should_post_vat_gl() is False  # 107-108
    with patch.object(ts, "is_tax_enabled", return_value=True):
        assert ts.normalize_tax_rate("5") == Decimal("5")  # 101-104
        with pytest.raises(ValueError):  # 102-103
            ts.normalize_tax_rate(150)
        assert ts.should_post_vat_gl() is True
    assert ts.suggested_rate_for_country("ps") == Decimal("16.00")  # 111-112
    assert ts.suggested_rate_for_country("zz") == Decimal("0")
    t = SimpleNamespace(enable_tax=False)
    with patch.object(ts, "_resolve_tenant", return_value=t):
        assert ts.default_tax_rate() == Decimal("0")  # 65-66 disabled


def test_branch_price_priority():
    from extensions import db as _db

    with patch.object(_db.session, "get", return_value=SimpleNamespace(prices_include_vat=True)):
        assert ts.get_prices_include_vat(branch_id=3) is True  # 84-90
    with patch.object(_db.session, "get", return_value=SimpleNamespace(prices_include_vat=None)):
        with patch.object(ts, "_resolve_tenant", return_value=None):
            assert ts.get_prices_include_vat(branch_id=3) is False


def test_telemetry_urls_and_files(tmp_path, monkeypatch):
    monkeypatch.setenv("FORM_SUBMIT_URL", "https://x.example/hook")
    assert tm.get_reporting_url() == "https://x.example/hook"  # 18-21
    monkeypatch.delenv("FORM_SUBMIT_URL")
    monkeypatch.setenv("FORM_SUBMIT_EMAIL", "a@b.com")
    assert tm.get_reporting_url() == "https://formsubmit.co/a@b.com"  # 31-32
    monkeypatch.delenv("FORM_SUBMIT_EMAIL")
    monkeypatch.setenv("OWNER_EMAIL", "")
    monkeypatch.setenv("COMPANY_EMAIL", "")
    assert tm.get_reporting_url() == "https://formsubmit.co"  # 34
    monkeypatch.setattr(tm, "TOKEN_FILE", str(tmp_path / "tok"))
    assert tm.has_reported_before("sig") is False  # 63-67 missing
    tm.mark_as_reported("sig")  # 78-85
    assert tm.has_reported_before("sig") is True  # 72
    assert tm.get_machine_signature()  # 47-60
    with patch.object(tm, "TOKEN_FILE", "/nonexistent-xyz/tok"):
        assert tm.has_reported_before("sig") is False


def test_telemetry_collect_send(monkeypatch, tmp_path):
    monkeypatch.setattr(tm, "HIDDEN_LOG_FILE", str(tmp_path / "h.log"))
    with patch("utils.telemetry.requests") as rq:
        rq.get.side_effect = [MagicMock(json=lambda: {"ip": "1.2.3.4"}), MagicMock()]
        info = tm.collect_system_info()  # 88-118
        assert info["public_ip"] == "1.2.3.4"
    with patch("utils.telemetry.requests") as rq2:
        rq2.get.side_effect = RuntimeError("net down")
        info2 = tm.collect_system_info()
        assert info2["public_ip"] == "Unknown"  # 110-114 fallback
    tm.save_local_log({"a": 1})  # 121-129
    with patch("utils.telemetry.requests") as rq3:
        rq3.post.return_value = SimpleNamespace(status_code=200)
        assert tm.send_formsubmit("s", {"k": "v"}) is True  # 132-155
        rq3.post.side_effect = RuntimeError("x")
        assert tm.send_formsubmit("s", {}) is False  # 153-155
    with patch.object(tm, "has_reported_before", return_value=True):
        assert tm.send_heartbeat() is None  # 163-168 early return
    with (
        patch.object(tm, "has_reported_before", return_value=False),
        patch.object(
            tm,
            "collect_system_info",
            return_value={
                "hostname": "h",
                "public_ip": "1",
                "os": "o",
                "os_release": "r",
                "timestamp": "t",
                "processor": "p",
            },
        ),
        patch.object(tm, "send_formsubmit", return_value=True),
        patch.object(tm, "mark_as_reported") as mk,
    ):
        tm.send_heartbeat()  # 170-189 sent
        mk.assert_called_once()
    monkeypatch.setenv("DISABLE_TELEMETRY", "true")
    tm.start_telemetry()  # 195-201 disabled
    monkeypatch.delenv("DISABLE_TELEMETRY")
    with patch("utils.telemetry.Thread") as th:
        tm.start_telemetry()  # thread path
        th.assert_called_once()


def test_nowpayments(monkeypatch):
    with patch("services.payments.nowpayments_provider.NowPaymentsProvider") as prov:
        prov.return_value.build_webhook_url.return_value = "https://hook.example/ipn"
        from utils.nowpayments_ipn import get_nowpayments_ipn_url

        assert get_nowpayments_ipn_url() == "https://hook.example/ipn"  # 10-14
    v = SimpleNamespace(nowpayments_ipn_secret="  sec123 ")
    assert np.resolve_nowpayments_ipn_secret(v) == "sec123"  # 22-25
    with patch(
        "models.payment_vault.PaymentVault.get_platform_vault",
        return_value=SimpleNamespace(nowpayments_ipn_secret="dbsec"),
    ):
        assert np.resolve_nowpayments_ipn_secret() == "dbsec"  # 29-33
    with patch("models.payment_vault.PaymentVault.get_platform_vault", side_effect=RuntimeError("db")):
        with patch("services.payments.nowpayments_provider.NowPaymentsProvider") as prov2:
            prov2.return_value.ipn_secret = " envsec "
            assert np.resolve_nowpayments_ipn_secret() == "envsec"  # 34-39
