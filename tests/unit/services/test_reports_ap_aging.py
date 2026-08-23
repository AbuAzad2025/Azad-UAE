"""AP aging report (ReportsQueryService.build_ap_aging_report) — bucket math, FIFO allocation, scoping."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

import services.reports_query_service as rq_mod

AS_OF = date(2025, 6, 30)


def _purchase(purchase_number, purchase_date, total, purchase_id=1, supplier_id=10):
    p = MagicMock()
    p.id = purchase_id
    p.purchase_number = purchase_number
    p.purchase_date = datetime.combine(purchase_date, datetime.min.time())
    p.total_amount = Decimal(str(total))
    p.supplier_id = supplier_id
    return p


def _supplier(sid=10, name="Supp X"):
    s = MagicMock()
    s.id = sid
    s.name = name
    return s


def _stub_queries(mocker, suppliers, purchases, remaining_by_supplier):
    mock_tq = MagicMock()
    mock_tq.filter.return_value.all.return_value = suppliers
    mocker.patch.object(rq_mod, "tenant_query", return_value=mock_tq)
    mocker.patch.object(rq_mod.ReportsQueryService, "fetch_purchases_report", return_value=purchases)
    mocker.patch.object(
        rq_mod.ReportsQueryService,
        "fetch_purchases_payments",
        return_value=({}, dict(remaining_by_supplier)),
    )


class TestAPAgingBuckets:
    @pytest.mark.parametrize(
        "days_ago,bucket",
        [
            (0, "0-30"),
            (30, "0-30"),
            (31, "31-60"),
            (60, "31-60"),
            (61, "61-90"),
            (90, "61-90"),
            (91, "90+"),
            (365, "90+"),
        ],
    )
    def test_boundary_age_buckets(self, mocker, days_ago, bucket):
        supplier = _supplier()
        purchase = _purchase("P-1", AS_OF - timedelta(days=days_ago), 1000, purchase_id=1)
        _stub_queries(mocker, [supplier], [purchase], {10: Decimal("0")})

        report = rq_mod.ReportsQueryService.build_ap_aging_report(tenant_id=1, scoped_branch_id=None, as_of_date=AS_OF)

        assert report["supplier_count"] == 1
        row = report["rows"][0]
        assert row["invoices"][0]["bucket"] == bucket
        assert row["buckets"][bucket] == pytest.approx(1000.0)
        assert sum(row["buckets"].values()) == pytest.approx(row["total"])
        assert report["totals"]["total"] == pytest.approx(1000.0)

    def test_future_dated_purchase_falls_in_current_bucket(self, mocker):
        supplier = _supplier()
        purchase = _purchase("P-F", AS_OF + timedelta(days=5), 300, purchase_id=2)
        _stub_queries(mocker, [supplier], [purchase], {10: Decimal("0")})

        report = rq_mod.ReportsQueryService.build_ap_aging_report(tenant_id=1, scoped_branch_id=None, as_of_date=AS_OF)

        assert report["rows"][0]["buckets"]["0-30"] == pytest.approx(300.0)


class TestAPAgingFIFO:
    def test_fifo_allocates_oldest_purchase_first(self, mocker):
        supplier = _supplier()
        purchases = [
            _purchase("P-OLD", date(2025, 1, 1), 1000, purchase_id=1),
            _purchase("P-NEW", date(2025, 6, 1), 500, purchase_id=2),
        ]
        # P-OLD lands in 61-90 bucket (Jan 1 -> Jun 30 = 180 days), P-NEW in 0-30.
        _stub_queries(mocker, [supplier], purchases, {10: Decimal("800")})

        report = rq_mod.ReportsQueryService.build_ap_aging_report(tenant_id=1, scoped_branch_id=None, as_of_date=AS_OF)

        invoices = report["rows"][0]["invoices"]
        assert invoices[0]["purchase_number"] == "P-OLD"
        assert invoices[0]["paid"] == pytest.approx(800.0)
        assert invoices[0]["balance"] == pytest.approx(200.0)
        assert invoices[1]["paid"] == pytest.approx(0.0)
        assert invoices[1]["balance"] == pytest.approx(500.0)
        assert report["totals"]["total"] == pytest.approx(700.0)

    def test_overpayment_leaves_no_negative_balance(self, mocker):
        supplier = _supplier()
        purchase = _purchase("P-1", date(2025, 6, 15), 400, purchase_id=3)
        _stub_queries(mocker, [supplier], [purchase], {10: Decimal("900")})

        report = rq_mod.ReportsQueryService.build_ap_aging_report(tenant_id=1, scoped_branch_id=None, as_of_date=AS_OF)

        assert report["rows"] == []
        assert report["totals"]["total"] == pytest.approx(0.0)


class TestAPAgingGrouping:
    def test_suppliers_grouped_and_sorted_by_name(self, mocker):
        supp_b = _supplier(sid=20, name="Beta")
        supp_a = _supplier(sid=30, name="Alpha")
        purchases = [
            _purchase("PB-1", date(2025, 6, 20), 150, purchase_id=4, supplier_id=20),
            _purchase("PA-1", date(2025, 6, 21), 250, purchase_id=5, supplier_id=30),
        ]
        _stub_queries(
            mocker,
            [supp_a, supp_b],
            purchases,
            {20: Decimal("0"), 30: Decimal("50")},
        )

        report = rq_mod.ReportsQueryService.build_ap_aging_report(tenant_id=1, scoped_branch_id=None, as_of_date=AS_OF)

        names = [row["supplier_name"] for row in report["rows"]]
        assert names == ["Alpha", "Beta"]
        assert report["rows"][0]["total"] == pytest.approx(200.0)  # 250 - 50 FIFO credit
        assert report["rows"][1]["total"] == pytest.approx(150.0)
        assert report["totals"]["total"] == pytest.approx(350.0)

    def test_zero_balance_supplier_excluded(self, mocker):
        supplier = _supplier(name="Paid Up")
        purchase = _purchase("P-9", date(2025, 6, 1), 600, purchase_id=6)
        _stub_queries(mocker, [supplier], [purchase], {10: Decimal("600")})

        report = rq_mod.ReportsQueryService.build_ap_aging_report(tenant_id=1, scoped_branch_id=None, as_of_date=AS_OF)

        assert report["supplier_count"] == 0
        assert report["rows"] == []


class TestAPAgingContract:
    def test_as_of_string_is_parsed(self, mocker):
        supplier = _supplier()
        purchase = _purchase("P-1", date(2025, 6, 29), 100, purchase_id=7)
        _stub_queries(mocker, [supplier], [purchase], {10: Decimal("0")})

        report = rq_mod.ReportsQueryService.build_ap_aging_report(
            tenant_id=1, scoped_branch_id=None, as_of_date="2025-06-30"
        )

        assert report["as_of"] == "2025-06-30"

    def test_defaults_to_today_without_as_of(self, mocker):
        supplier = _supplier()
        _stub_queries(mocker, [supplier], [], {10: Decimal("0")})

        report = rq_mod.ReportsQueryService.build_ap_aging_report(tenant_id=1, scoped_branch_id=None)

        assert report["as_of"] == date.today().isoformat()

    def test_scope_and_filters_forwarded_to_queries(self, mocker):
        supplier = _supplier()
        _stub_queries(mocker, [supplier], [], {})
        fetch_purchases = rq_mod.ReportsQueryService.fetch_purchases_report
        fetch_payments = rq_mod.ReportsQueryService.fetch_purchases_payments

        rq_mod.ReportsQueryService.build_ap_aging_report(
            tenant_id=7, scoped_branch_id=3, as_of_date="2025-06-30", supplier_id=42
        )

        assert fetch_purchases.call_args.args == (7, 3, "", "2025-06-30", 42)
        assert fetch_payments.call_args.args == (7, 3, "", "2025-06-30", 42)

    def test_output_is_json_safe_floats(self, mocker):
        supplier = _supplier()
        purchase = _purchase("P-1", date(2025, 6, 1), Decimal("333.333"), purchase_id=8)
        _stub_queries(mocker, [supplier], [purchase], {10: Decimal("33.333")})

        report = rq_mod.ReportsQueryService.build_ap_aging_report(tenant_id=1, scoped_branch_id=None, as_of_date=AS_OF)

        row = report["rows"][0]
        assert all(isinstance(v, float) for v in row["buckets"].values())
        assert isinstance(row["total"], float)
        invoice = row["invoices"][0]
        assert isinstance(invoice["balance"], float)
        assert isinstance(invoice["paid"], float)
