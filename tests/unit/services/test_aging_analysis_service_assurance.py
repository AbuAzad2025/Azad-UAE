"""Aging analysis — AR/AP buckets, FIFO payments, GL verification."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
import utils.tenanting as tenanting_mod


@pytest.fixture(autouse=True)
def _patch_tenanting_active_id(mocker):
    mocker.patch.object(tenanting_mod, "active_tenant_id", lambda: 1, create=True)


def _mock_tenant_customers(mocker, customers):
    mock_tq = MagicMock()
    mock_tq.filter_by.return_value.order_by.return_value.all.return_value = customers
    mocker.patch.object(tenanting_mod, "tenant_query", return_value=mock_tq)
    return mock_tq


def _mock_tenant_suppliers(mocker, suppliers):
    mock_tq = MagicMock()
    mock_tq.filter_by.return_value.order_by.return_value.all.return_value = suppliers
    mocker.patch.object(tenanting_mod, "tenant_query", return_value=mock_tq)
    return mock_tq


def _sale(sale_number, sale_date, amount, paid=0, branch_id=1):
    s = MagicMock()
    s.sale_number = sale_number
    s.sale_date = datetime.combine(sale_date, datetime.min.time())
    s.amount_aed = Decimal(str(amount))
    s.paid_amount_aed = Decimal(str(paid))
    s.branch_id = branch_id
    return s


def _purchase(purchase_number, purchase_date, total, branch_id=1):
    p = MagicMock()
    p.purchase_number = purchase_number
    p.purchase_date = datetime.combine(purchase_date, datetime.min.time())
    p.total_amount = Decimal(str(total))
    p.branch_id = branch_id
    return p


class TestReceivablesAging:
    """get_receivables_aging — boundary buckets and branch filter."""

    @pytest.mark.parametrize(
        "days_ago,bucket",
        [
            (0, "0-30"),
            (30, "0-30"),
            (31, "31-60"),
            (60, "31-60"),
            (61, "61-90"),
            (90, "61-90"),
            (91, "91-120"),
            (120, "91-120"),
            (121, "+120"),
        ],
    )
    def test_boundary_age_buckets(self, mocker, days_ago, bucket):
        as_of = date(2025, 6, 30)
        sale_date = as_of - timedelta(days=days_ago)
        customer = MagicMock(id=1, name="Cust A")

        _mock_tenant_customers(mocker, [customer])

        sale_q = MagicMock()
        sale_q.filter.return_value = sale_q
        sale_q.order_by.return_value = sale_q
        sale_q.all.return_value = [_sale("S-1", sale_date, 1000, paid=0)]
        mocker.patch.object(
            __import__("models", fromlist=["Sale"]).Sale,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=sale_q,
        )

        from services.aging_analysis_service import AgingAnalysisService

        report = AgingAnalysisService.get_receivables_aging(as_of_date=as_of, tenant_id=1)
        assert report["customer_count"] == 1
        assert report["customers"][0]["invoices"][0]["age_category"] == bucket
        assert report["totals"]["total"] == pytest.approx(1000.0)

    def test_zero_balance_sales_excluded(self, mocker):
        customer = MagicMock(id=2, name="Paid Up")
        _mock_tenant_customers(mocker, [customer])

        sale_q = MagicMock()
        sale_q.filter.return_value = sale_q
        sale_q.order_by.return_value = sale_q
        sale_q.all.return_value = [_sale("S-2", date.today(), 500, paid=500)]
        mocker.patch.object(
            __import__("models", fromlist=["Sale"]).Sale,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=sale_q,
        )

        from services.aging_analysis_service import AgingAnalysisService

        report = AgingAnalysisService.get_receivables_aging(tenant_id=1)
        assert report["customer_count"] == 0
        assert report["totals"]["total"] == 0.0

    def test_branch_filter_on_sales(self, mocker):
        customer = MagicMock(id=3, name="Branch Cust")
        _mock_tenant_customers(mocker, [customer])

        sale_q = MagicMock()
        sale_q.filter.return_value = sale_q
        sale_q.order_by.return_value = sale_q
        sale_q.all.return_value = [
            _sale("S-A", date.today(), 100, branch_id=1),
            _sale("S-B", date.today(), 200, branch_id=2),
        ]
        mocker.patch.object(
            __import__("models", fromlist=["Sale"]).Sale,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=sale_q,
        )

        from services.aging_analysis_service import AgingAnalysisService

        report = AgingAnalysisService.get_receivables_aging(branch_id=2, tenant_id=1)
        assert report["totals"]["total"] == pytest.approx(200.0)


class TestPayablesAging:
    """get_payables_aging — FIFO payment allocation across purchases."""

    def test_fifo_allocates_oldest_invoice_first(self, mocker, app):
        supplier = MagicMock(id=10, name="Supp X")
        _mock_tenant_suppliers(mocker, [supplier])

        purchases = [
            _purchase("P-OLD", date(2025, 1, 1), 1000),
            _purchase("P-NEW", date(2025, 2, 1), 500),
        ]
        purchase_q = MagicMock()
        purchase_q.filter.return_value = purchase_q
        purchase_q.order_by.return_value = purchase_q
        purchase_q.all.return_value = purchases
        mocker.patch.object(
            __import__("models", fromlist=["Purchase"]).Purchase,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=purchase_q,
        )

        pay_q = MagicMock()
        pay_q.filter.return_value = pay_q
        pay_q.scalar.return_value = Decimal("800")
        mock_session = mocker.patch("services.aging_analysis_service.db.session")
        mock_session.query.return_value = pay_q

        from services.aging_analysis_service import AgingAnalysisService

        with app.app_context():
            report = AgingAnalysisService.get_payables_aging(as_of_date=date(2025, 6, 1), tenant_id=1)

        invoices = report["suppliers"][0]["invoices"]
        assert invoices[0]["paid"] == pytest.approx(800.0)
        assert invoices[0]["balance"] == pytest.approx(200.0)
        assert invoices[1]["balance"] == pytest.approx(500.0)
        assert report["totals"]["total"] == pytest.approx(700.0)

    def test_unallocated_payment_zero_leaves_full_balance(self, mocker, app):
        supplier = MagicMock(id=11, name="Supp Y")
        _mock_tenant_suppliers(mocker, [supplier])

        purchase_q = MagicMock()
        purchase_q.filter.return_value = purchase_q
        purchase_q.order_by.return_value = purchase_q
        purchase_q.all.return_value = [_purchase("P-1", date(2025, 3, 1), 300)]
        mocker.patch.object(
            __import__("models", fromlist=["Purchase"]).Purchase,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=purchase_q,
        )

        pay_q = MagicMock()
        pay_q.filter.return_value = pay_q
        pay_q.scalar.return_value = Decimal("0")
        mocker.patch("services.aging_analysis_service.db.session").query.return_value = pay_q

        from services.aging_analysis_service import AgingAnalysisService

        with app.app_context():
            report = AgingAnalysisService.get_payables_aging(tenant_id=1)

        assert report["suppliers"][0]["total"] == pytest.approx(300.0)
        assert report["suppliers"][0]["invoices"][0]["paid"] == 0.0


class TestGLVerification:
    """verify_receivables/payables_with_gl — subledger vs ledger."""

    def test_receivables_in_balance_when_within_tolerance(self, mocker):
        mocker.patch(
            "services.aging_analysis_service.AgingAnalysisService.get_receivables_aging",
            return_value={"totals": {"total": 5000.0}},
        )
        ar_acc = MagicMock(id=99)
        mocker.patch(
            "services.aging_analysis_service.AgingAnalysisService._resolve_aging_account",
            return_value=ar_acc,
        )

        gl_q = MagicMock()
        gl_q.join.return_value = gl_q
        gl_q.filter.return_value = gl_q
        gl_q.scalar.return_value = Decimal("5000.005")
        mocker.patch("services.aging_analysis_service.db.session").query.return_value = gl_q

        from services.aging_analysis_service import AgingAnalysisService

        result = AgingAnalysisService.verify_receivables_with_gl(tenant_id=1)
        assert result["in_balance"] is True
        assert result["difference"] == pytest.approx(0.005, abs=0.01)

    def test_payables_no_gl_account_zero_total(self, mocker):
        mocker.patch(
            "services.aging_analysis_service.AgingAnalysisService.get_payables_aging",
            return_value={"totals": {"total": 1200.0}},
        )
        mocker.patch(
            "services.aging_analysis_service.AgingAnalysisService._resolve_aging_account",
            return_value=None,
        )

        from services.aging_analysis_service import AgingAnalysisService

        result = AgingAnalysisService.verify_payables_with_gl(tenant_id=1)
        assert result["gl_total"] == 0.0
        assert result["in_balance"] is False

    def test_resolve_aging_account_payable_code(self, mocker):
        ap_acc = MagicMock(code="2110")
        mock_q = MagicMock()
        mock_q.filter_by.return_value = mock_q
        mock_q.first.return_value = ap_acc
        mocker.patch.object(
            __import__("models", fromlist=["GLAccount"]).GLAccount,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=mock_q,
        )

        from services.aging_analysis_service import AgingAnalysisService

        result = AgingAnalysisService._resolve_aging_account("AP", tenant_id=5)
        assert result is ap_acc
        mock_q.filter_by.assert_called()


class TestReceivablesStringDate:
    def test_as_of_date_string_parsed(self, mocker):
        customer = MagicMock(id=1, name="Cust")
        _mock_tenant_customers(mocker, [customer])
        sale_q = MagicMock()
        sale_q.filter.return_value = sale_q
        sale_q.order_by.return_value = sale_q
        sale_q.all.return_value = [_sale("S-1", date(2025, 1, 1), 100, paid=0)]
        mocker.patch.object(
            __import__("models", fromlist=["Sale"]).Sale,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=sale_q,
        )
        from services.aging_analysis_service import AgingAnalysisService

        report = AgingAnalysisService.get_receivables_aging(as_of_date="2025-06-30", tenant_id=1)
        assert report["as_of_date"] == date(2025, 6, 30)


class TestPayablesExtended:
    def test_payables_string_date_and_branch_filter(self, mocker, app):
        supplier = MagicMock(id=20, name="Supp")
        _mock_tenant_suppliers(mocker, [supplier])
        purchase_q = MagicMock()
        purchase_q.filter.return_value = purchase_q
        purchase_q.order_by.return_value = purchase_q
        purchase_q.all.return_value = [_purchase("P-1", date(2025, 1, 1), 400, branch_id=2)]
        mocker.patch.object(
            __import__("models", fromlist=["Purchase"]).Purchase,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=purchase_q,
        )
        pay_q = MagicMock()
        pay_q.filter.return_value = pay_q
        pay_q.scalar.return_value = Decimal("0")
        mocker.patch("services.aging_analysis_service.db.session").query.return_value = pay_q

        from services.aging_analysis_service import AgingAnalysisService

        with app.app_context():
            report = AgingAnalysisService.get_payables_aging(
                as_of_date="2025-06-01",
                branch_id=2,
                tenant_id=1,
            )
        assert report["as_of_date"] == date(2025, 6, 1)
        assert purchase_q.filter.call_count >= 1

    @pytest.mark.parametrize("days_ago,bucket", [(15, "0-30"), (45, "31-60"), (75, "61-90"), (100, "91-120")])
    def test_payables_age_buckets(self, mocker, app, days_ago, bucket):
        supplier = MagicMock(id=21, name="Supp B")
        _mock_tenant_suppliers(mocker, [supplier])
        as_of = date(2025, 6, 30)
        purchase_date = as_of - timedelta(days=days_ago)
        purchase_q = MagicMock()
        purchase_q.filter.return_value = purchase_q
        purchase_q.order_by.return_value = purchase_q
        purchase_q.all.return_value = [_purchase("P-X", purchase_date, 300)]
        mocker.patch.object(
            __import__("models", fromlist=["Purchase"]).Purchase,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=purchase_q,
        )
        pay_q = MagicMock()
        pay_q.filter.return_value = pay_q
        pay_q.scalar.return_value = Decimal("0")
        mocker.patch("services.aging_analysis_service.db.session").query.return_value = pay_q

        from services.aging_analysis_service import AgingAnalysisService

        with app.app_context():
            report = AgingAnalysisService.get_payables_aging(as_of_date=as_of, tenant_id=1)
        assert report["suppliers"][0]["invoices"][0]["age_category"] == bucket


class TestGLVerificationExtended:
    def test_payables_with_gl_account_in_balance(self, mocker):
        mocker.patch(
            "services.aging_analysis_service.AgingAnalysisService.get_payables_aging",
            return_value={"totals": {"total": 1000.0}},
        )
        ap_acc = MagicMock(id=50)
        mocker.patch(
            "services.aging_analysis_service.AgingAnalysisService._resolve_aging_account",
            return_value=ap_acc,
        )
        gl_q = MagicMock()
        gl_q.join.return_value = gl_q
        gl_q.filter.return_value = gl_q
        gl_q.scalar.return_value = Decimal("1000")
        mocker.patch("services.aging_analysis_service.db.session").query.return_value = gl_q

        from services.aging_analysis_service import AgingAnalysisService

        result = AgingAnalysisService.verify_payables_with_gl(tenant_id=1, branch_id=2)
        assert result["in_balance"] is True
        assert result["gl_total"] == pytest.approx(1000.0)

    def test_receivables_string_as_of_date(self, mocker):
        mocker.patch(
            "services.aging_analysis_service.AgingAnalysisService.get_receivables_aging",
            return_value={"totals": {"total": 100.0}},
        )
        mocker.patch(
            "services.aging_analysis_service.AgingAnalysisService._resolve_aging_account",
            return_value=None,
        )
        from services.aging_analysis_service import AgingAnalysisService

        AgingAnalysisService.verify_receivables_with_gl(as_of_date="2025-01-15", tenant_id=1)

    def test_payables_string_as_of_date(self, mocker):
        mocker.patch(
            "services.aging_analysis_service.AgingAnalysisService.get_payables_aging",
            return_value={"totals": {"total": 50.0}},
        )
        mocker.patch(
            "services.aging_analysis_service.AgingAnalysisService._resolve_aging_account",
            return_value=None,
        )
        from services.aging_analysis_service import AgingAnalysisService

        AgingAnalysisService.verify_payables_with_gl(as_of_date="2025-02-20", tenant_id=1)

    def test_receivables_out_of_balance(self, mocker):
        mocker.patch(
            "services.aging_analysis_service.AgingAnalysisService.get_receivables_aging",
            return_value={"totals": {"total": 500.0}},
        )
        ar_acc = MagicMock(id=60)
        mocker.patch(
            "services.aging_analysis_service.AgingAnalysisService._resolve_aging_account",
            return_value=ar_acc,
        )
        gl_q = MagicMock()
        gl_q.join.return_value = gl_q
        gl_q.filter.return_value = gl_q
        gl_q.scalar.return_value = Decimal("400")
        mocker.patch("services.aging_analysis_service.db.session").query.return_value = gl_q

        from services.aging_analysis_service import AgingAnalysisService

        result = AgingAnalysisService.verify_receivables_with_gl(tenant_id=1, branch_id=1)
        assert result["in_balance"] is False
