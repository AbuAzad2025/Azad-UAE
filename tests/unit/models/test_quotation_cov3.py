"""Gap coverage for models/quotation.py — expiry and status branches."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from models.quotation import Quotation, QuotationLine


def _quotation(**kwargs):
    params = {
        "tenant_id": 1,
        "quotation_number": "Q-COV3",
        "customer_id": 1,
        "created_by": 1,
    }
    params.update(kwargs)
    return Quotation(**params)


class TestIsExpired:
    def test_no_expiry(self):
        assert _quotation(expiry_date=None, status="draft").is_expired is False

    def test_future_expiry(self):
        future = (datetime.now(UTC) + timedelta(days=5)).date()
        assert _quotation(expiry_date=future, status="draft").is_expired is False

    def test_past_draft_expired(self):
        past = (datetime.now(UTC) - timedelta(days=1)).date()
        assert _quotation(expiry_date=past, status="draft").is_expired is True

    def test_past_sent_expired(self):
        past = (datetime.now(UTC) - timedelta(days=1)).date()
        assert _quotation(expiry_date=past, status="sent").is_expired is True

    def test_past_accepted_not_expired(self):
        past = (datetime.now(UTC) - timedelta(days=10)).date()
        assert _quotation(expiry_date=past, status="accepted").is_expired is False

    def test_past_converted_not_expired(self):
        past = (datetime.now(UTC) - timedelta(days=10)).date()
        assert _quotation(expiry_date=past, status="converted_to_sale").is_expired is False


class TestStatusAr:
    def test_unknown_returns_status(self):
        assert _quotation(status="mystery").status_ar == "mystery"

    def test_known(self):
        assert _quotation(status="draft").status_ar == "مسودة"
        assert _quotation(status="expired").status_ar == "منتهية"


class TestReprs:
    def test_quotation_repr(self):
        assert "Q-COV3" in repr(_quotation())

    def test_line_repr(self):
        line = QuotationLine(product_id=9, quantity=2)
        assert "product=9" in repr(line)
