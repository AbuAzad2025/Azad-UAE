"""Cov4: currency_utils — fallbacks, tenant objects, quantize, symbols."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import utils.currency_utils as cu


def test_get_system_default():
    assert cu.get_system_default_currency()  # line 10-15


def test_context_no_request():
    with patch("flask.has_request_context", return_value=False):
        assert cu.context_aware_default_currency() == cu.get_system_default_currency()  # 37


def test_context_exception_returns_default():
    with patch("flask.has_request_context", side_effect=RuntimeError("x")):
        assert cu.context_aware_default_currency() == cu.get_system_default_currency()  # 38-39


def test_resolve_default_tenant_obj():
    t = SimpleNamespace(default_currency=" aed ")
    assert cu.resolve_default_currency(t) == "AED"  # 43-46
    assert cu.resolve_default_currency(None)  # settings fallback lines 47-56


def test_resolve_default_settings_exception():
    with patch("models.system_settings.SystemSettings.get_current", side_effect=RuntimeError("db down")):
        assert cu.resolve_default_currency(None) == cu.get_system_default_currency()  # 54-55


def test_get_tenant_base_branches():
    assert cu.get_tenant_base_currency(None) == cu.get_system_default_currency()  # 88
    tenant = SimpleNamespace(base_currency=" usd ", default_currency="AED")
    with patch.object(cu.db.session, "get", return_value=tenant):
        assert cu.get_tenant_base_currency(5) == "USD"  # 73-76
    tenant2 = SimpleNamespace(base_currency=" ", default_currency=" sar")
    with patch.object(cu.db.session, "get", return_value=tenant2):
        assert cu.get_tenant_base_currency(5) == "SAR"  # 77-81
    with patch.object(cu.db.session, "get", side_effect=RuntimeError("x")):
        assert cu.get_tenant_base_currency(5) == cu.get_system_default_currency()  # 82-87


def test_resolve_tenant_base_variants():
    t = SimpleNamespace(base_currency="EUR", default_currency="AED")
    assert cu.resolve_tenant_base_currency(tenant=t) == "EUR"  # 94-98
    t2 = SimpleNamespace(base_currency="", default_currency="jod")
    assert cu.resolve_tenant_base_currency(tenant=t2) == "JOD"  # 99-103
    with patch.object(cu, "get_tenant_base_currency", return_value="ILS"):
        assert cu.resolve_tenant_base_currency(tenant_id=3) == "ILS"  # 104-105


def test_convert_quantize_both():
    assert cu.convert_and_quantize_aed("10", "AED", 1, base_currency="aed") == Decimal("10.000")  # 141-142
    assert cu.convert_and_quantize_aed(10, "USD", 3.67, base_currency="AED") == Decimal("36.700")  # 143
    assert cu.convert_and_quantize_aed(None, "USD", None, base_currency="AED") == Decimal("0.000")


def test_symbols_fallback():
    assert cu.get_currency_symbol("XXX-UNKNOWN") == "XXX-UNKNOWN"  # 152
    assert cu.get_currency_name_ar("XXX-UNKNOWN") == "XXX-UNKNOWN"  # 161
    assert cu.get_currency_symbol("AED")
