"""PartnerCommissionEntry — currency property aliases."""

from __future__ import annotations

from decimal import Decimal

from models.partner_commission import PartnerCommissionEntry


class TestPartnerCommissionAliases:
    def test_commission_amount_get_set(self):
        e = PartnerCommissionEntry()
        e.commission_amount = Decimal("50.25")
        assert e.commission_amount_aed == Decimal("50.25")
        assert e.commission_amount == Decimal("50.25")

    def test_base_amount_get_set(self):
        e = PartnerCommissionEntry()
        e.base_amount = Decimal("200")
        assert e.base_amount_aed == Decimal("200")
        assert e.base_amount == Decimal("200")

    def test_commission_amount_base_get_set(self):
        e = PartnerCommissionEntry()
        e.commission_amount_base = Decimal("75")
        assert e.commission_amount_aed == Decimal("75")
        assert e.commission_amount_base == Decimal("75")
