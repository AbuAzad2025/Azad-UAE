"""Coverage-4 for services.reports_query_service — date/branch/bucket arcs."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from services.reports_query_service import ReportsQueryService


@pytest.fixture(autouse=True)
def _ctx(app, db_session):
    with app.app_context():
        yield
        db_session.rollback()


class TestApAgingDates:
    def _run(self, mocker, as_of, purchases, payments):
        mocker.patch.object(ReportsQueryService, "fetch_purchases_payments", return_value=({}, payments))
        mocker.patch.object(ReportsQueryService, "fetch_purchases_report", return_value=purchases)
        return ReportsQueryService.build_ap_aging_report(1, None, as_of_date=as_of)

    def test_string_date(self, mocker):
        out = self._run(mocker, "2026-02-01", [], {})
        assert out["as_of"] == "2026-02-01"

    def test_datetime_date(self, mocker):
        out = self._run(mocker, datetime(2026, 2, 5, 10), [], {})
        assert out["as_of"] == "2026-02-05"

    def test_date_object(self, mocker):
        out = self._run(mocker, date(2026, 3, 1), [], {})
        assert out["as_of"] == "2026-03-01"

    def test_none_defaults_today(self, mocker):
        out = self._run(mocker, None, [], {})
        assert out["as_of"] == date.today().strftime("%Y-%m-%d")

    def test_blank_string_defaults_today(self, mocker):
        out = self._run(mocker, "   ", [], {})
        assert out["as_of"] == date.today().strftime("%Y-%m-%d")


class TestApAgingBuckets:
    def _purchase(self, pid, sid, total, pdate):
        return SimpleNamespace(
            id=pid,
            supplier_id=sid,
            total_amount=total,
            purchase_date=pdate,
            purchase_number=f"PO-{pid}",
        )

    def test_bucket_boundaries_and_fifo(self, mocker):
        as_of = date(2026, 6, 30)
        purchases = [
            self._purchase(1, 10, Decimal("100"), date(2026, 6, 20)),  # 10d -> 0-30
            self._purchase(2, 10, Decimal("100"), date(2026, 5, 1)),  # 60d -> 31-60
            self._purchase(3, 10, Decimal("100"), date(2026, 4, 1)),  # 90d -> 61-90
            self._purchase(4, 10, Decimal("100"), date(2026, 1, 1)),  # 180d -> 90+
        ]
        mocker.patch.object(ReportsQueryService, "fetch_purchases_payments", return_value=({}, {10: Decimal("150")}))
        mocker.patch.object(ReportsQueryService, "fetch_purchases_report", return_value=purchases)
        mocker.patch("services.reports_query_service.tenant_query")
        out = ReportsQueryService.build_ap_aging_report(1, None, as_of_date=as_of)
        row = next(r for r in out["rows"] if r["supplier_id"] == 10)
        # FIFO (oldest invoices first):
        # Purchase 4 (Jan 1, 180d): 100 paid -> 0 balance (90+ bucket, skipped)
        # Purchase 3 (Apr 1, 90d): 50 paid -> 50 balance (61-90 bucket)
        # Purchase 2 (May 1, 60d): 0 paid -> 100 balance (31-60 bucket)
        # Purchase 1 (Jun 20, 10d): 0 paid -> 100 balance (0-30 bucket)
        assert row["buckets"]["0-30"] == 100.0
        assert row["buckets"]["31-60"] == 100.0
        assert row["buckets"]["61-90"] == 50.0
        assert row["buckets"]["90+"] == 0.0

    def test_fully_paid_supplier_skipped(self, mocker):
        purchases = [self._purchase(1, 11, Decimal("50"), date(2026, 6, 1))]
        mocker.patch.object(ReportsQueryService, "fetch_purchases_payments", return_value=({}, {11: Decimal("50")}))
        mocker.patch.object(ReportsQueryService, "fetch_purchases_report", return_value=purchases)
        mocker.patch("services.reports_query_service.tenant_query")
        out = ReportsQueryService.build_ap_aging_report(1, None, as_of_date=date(2026, 6, 30))
        assert all(r["supplier_id"] != 11 for r in out["rows"])

    def test_datetime_purchase_date_and_missing_day(self, mocker):
        purchases = [
            self._purchase(5, 12, Decimal("80"), datetime(2026, 6, 10, 12)),
            SimpleNamespace(
                id=6,
                supplier_id=12,
                total_amount=Decimal("20"),
                purchase_date=None,
                purchase_number="PO-6",
            ),
        ]
        mocker.patch.object(ReportsQueryService, "fetch_purchases_payments", return_value=({}, {}))
        mocker.patch.object(ReportsQueryService, "fetch_purchases_report", return_value=purchases)

        mq = MagicMock()
        mq.filter.return_value = mq
        mq.all.return_value = [SimpleNamespace(id=12, name="S12")]
        mocker.patch("services.reports_query_service.tenant_query", return_value=mq)
        out = ReportsQueryService.build_ap_aging_report(1, None, as_of_date=date(2026, 6, 30))
        row = next(r for r in out["rows"] if r["supplier_id"] == 12)
        assert row["total"] == 100.0


class TestSearchEntities:
    def test_search_unknown_type(self, mocker):
        sq = MagicMock()
        sq.filter.return_value = sq
        sq.limit.return_value = sq
        sq.all.return_value = []
        mocker.patch.object(ReportsQueryService, "_scoped_customer_query", return_value=sq)
        out = ReportsQueryService.search_entities("query", "bogus_type")
        assert out == []

    def test_search_supplier_and_customer_paths(self, mocker):

        sq = MagicMock()
        sq.filter.return_value = sq
        sq.limit.return_value = sq
        sq.all.return_value = []
        mocker.patch.object(ReportsQueryService, "_scoped_supplier_query", return_value=sq)
        mocker.patch.object(ReportsQueryService, "_scoped_customer_query", return_value=sq)
        assert ReportsQueryService.search_entities("q", "supplier") == []
        assert ReportsQueryService.search_entities("q", "customer") == []
        # default/merchant branch falls to customer query
        assert ReportsQueryService.search_entities("q", "merchant") == []

    def test_scope_helpers_false_when_missing(self, mocker):
        mocker.patch.object(ReportsQueryService, "_scoped_customer_query", side_effect=RuntimeError("x"))
        with pytest.raises(RuntimeError):
            ReportsQueryService.customer_in_branch_scope(1)
