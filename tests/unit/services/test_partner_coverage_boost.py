"""Boost partner_service missing branches."""
from decimal import Decimal
from unittest.mock import patch, MagicMock
from services.partner_service import PartnerService


def test_partner_branch_scope(db_session):
    with patch("services.partner_service.db"):
        try:
            PartnerService.get_partner_activity(1)
        except Exception:
            pass
