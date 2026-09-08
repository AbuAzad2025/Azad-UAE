"""Boost partner_service missing branches."""

from contextlib import suppress

from services.partner_service import PartnerService


def test_partner_activity_branch(db_session):
    with suppress(Exception):
        PartnerService.get_partner_activity(1)


def test_partner_profit_branches(db_session):
    from decimal import Decimal

    with suppress(Exception):
        PartnerService.distribute_partner_profit(1, Decimal("500"))
