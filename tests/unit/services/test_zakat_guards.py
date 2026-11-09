"""Unit tests for ZakatService guard branches."""

from __future__ import annotations

import pytest

from services.zakat_service import ZakatService


class TestGuards:
    def test_estimate_requires_tenant(self):
        with pytest.raises(ValueError, match="tenant_id is required"):
            ZakatService.estimate(None, fiscal_year=2026)

    def test_accrue_requires_both(self):
        with pytest.raises(ValueError, match="tenant_id and fiscal_year"):
            ZakatService.accrue(None, 2026)
        with pytest.raises(ValueError, match="tenant_id and fiscal_year"):
            ZakatService.accrue(1, None)
