"""POS session service - session and shift management."""

from __future__ import annotations

import logging

from extensions import db

logger = logging.getLogger(__name__)


class PosSessionService:
    """Pure business logic for POS session operations. Uses flush only — callers manage transactions."""

    @staticmethod
    def update_session_totals(
        session,
        sale,
        payment_data=None,
        payments_data=None,
        payment_currency="AED",
        payment_exchange_rate=1,
        tenant_id=None,
    ):
        """Update session totals after a sale."""
        from decimal import Decimal

        from utils.currency_utils import convert_and_quantize_aed

        session.total_sales = Decimal(str(session.total_sales or 0)) + Decimal(str(sale.total_amount or 0))
        if payment_data and payment_data.get("payment_method") == "cash":
            session.total_cash_sales = Decimal(str(session.total_cash_sales or 0)) + convert_and_quantize_aed(
                payment_data.get("amount", 0),
                payment_currency,
                payment_exchange_rate,
                tenant_id=tenant_id,
            )
        if payments_data:
            for tender_chunk in payments_data:
                _accumulate_session_tender(session, tender_chunk, tenant_id)
        db.session.add(session)

    @staticmethod
    def create_shift(tenant_id: int, branch_id: int | None = None, user_id: int | None = None, starting_cash=0):
        """Create a new POS shift."""
        from models import PosShift

        shift = PosShift(
            tenant_id=tenant_id,
            user_id=user_id,
            starting_cash=starting_cash,
            is_open=True,
        )
        db.session.add(shift)
        return shift


def _accumulate_session_tender(session, tender_chunk, tenant_id=None):
    """Accumulate tender amounts into session totals."""
    from decimal import Decimal

    from utils.currency_utils import convert_and_quantize_aed

    method = tender_chunk.get("payment_method", "cash")
    amount = Decimal(str(tender_chunk.get("amount", 0)))
    currency = tender_chunk.get("currency", "AED")
    rate = Decimal(str(tender_chunk.get("exchange_rate", 1)))
    amount_aed = convert_and_quantize_aed(amount, currency, rate, tenant_id=tenant_id)

    if method == "cash":
        session.total_cash_sales = Decimal(str(session.total_cash_sales or 0)) + amount_aed
    elif method == "card":
        session.total_card_sales = Decimal(str(session.total_card_sales or 0)) + amount_aed
    session.total_sales = Decimal(str(session.total_sales or 0)) + amount_aed
