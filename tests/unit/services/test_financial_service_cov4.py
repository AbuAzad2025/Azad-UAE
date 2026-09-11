"""Cov4: financial_service — dashboard/periods/sum-filter arcs."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from services.financial_service import FinancialService


def test_sum_sales_no_rows_returns_zero(sample_tenant):
    assert FinancialService.sum_sales(sample_tenant.id) == 0
    assert FinancialService.sum_purchases(sample_tenant.id) == 0
    assert FinancialService.sum_receipts(sample_tenant.id) == 0


def test_sum_sales_with_filters(
    db_session, sample_tenant, sample_branch, sample_user, sample_customer, sample_warehouse
):
    from datetime import datetime

    from models import Sale

    sale = Sale(
        tenant_id=sample_tenant.id,
        sale_number="FIN-SUM-1",
        customer_id=sample_customer.id,
        seller_id=sample_user.id,
        warehouse_id=sample_warehouse.id,
        branch_id=sample_branch.id,
        sale_date=datetime.now(),
        status="confirmed",
        subtotal=Decimal("100"),
        total_amount=Decimal("100"),
        amount=Decimal("100"),
        amount_aed=Decimal("100"),
    )
    db_session.add(sale)
    db_session.flush()
    assert float(FinancialService.sum_sales(sample_tenant.id)) == 100.0
    assert float(FinancialService.sum_sales(sample_tenant.id, branch_id=sample_branch.id)) == 100.0
    assert FinancialService.sum_sales(sample_tenant.id, branch_id=999999) == 0
    assert float(FinancialService.sum_sales(sample_tenant.id, seller_id=sample_user.id)) == 100.0
    assert float(FinancialService.sum_sales(sample_tenant.id, date_from=date.today() - timedelta(days=1))) == 100.0
    assert FinancialService.sum_sales(sample_tenant.id, date_from=date.today() + timedelta(days=1)) == 0
    assert float(FinancialService.sum_sales(sample_tenant.id, date_to=date.today() + timedelta(days=1))) == 100.0
    assert FinancialService.sum_sales(sample_tenant.id, status="draft") == 0
    assert FinancialService.sum_sales(sample_tenant.id, status=None) != 0


def test_sum_purchases_receipts_filters(db_session, sample_tenant, sample_branch, sample_user):
    from datetime import datetime

    from models import Purchase

    po = Purchase(
        tenant_id=sample_tenant.id,
        purchase_number="FIN-PO-1",
        supplier_name="Fin Supplier",
        branch_id=sample_branch.id,
        purchase_date=datetime.now(),
        status="confirmed",
        total_amount=Decimal("50"),
        amount=Decimal("50"),
        amount_aed=Decimal("50"),
        user_id=sample_user.id,
    )
    db_session.add(po)
    db_session.flush()
    assert float(FinancialService.sum_purchases(sample_tenant.id)) == 50.0
    assert FinancialService.sum_purchases(sample_tenant.id, branch_id=999999) == 0
    assert float(FinancialService.sum_purchases(sample_tenant.id, status=None)) == 50.0
    assert FinancialService.sum_receipts(sample_tenant.id, branch_id=sample_branch.id) == 0


def test_dashboard_context_structure(sample_tenant):
    ctx = FinancialService.get_financial_dashboard_advanced_context(sample_tenant.id)
    assert len(ctx["months_data"]) == 12
    assert ctx["months_data"][0].keys() == {"month", "revenue", "expenses", "profit", "margin"}
    assert set(ctx["kpis"]) == {"avg_revenue", "avg_profit", "avg_margin", "growth_rate"}


def test_dashboard_context_with_branch_and_december_path(sample_tenant, sample_branch):
    ctx = FinancialService.get_financial_dashboard_advanced_context(sample_tenant.id, branch_id=sample_branch.id)
    assert len(ctx["months_data"]) == 12


def test_financial_overview_periods(sample_tenant, app):
    from flask import render_template as _rt  # noqa: F401  (ensures template path importable)

    with patch("flask.render_template", return_value="RENDERED") as rt:
        for period in ["today", "week", "month", "year", "bogus"]:
            out = FinancialService.financial_overview(period, sample_tenant.id, None)
            assert out == "RENDERED"
        assert rt.call_count == 5
        kwargs = rt.call_args[1]
        assert kwargs["period"] == "bogus"
        assert kwargs["financial_data"]["platform_mode"] is False


def test_financial_overview_platform_mode_with_branch(sample_tenant, sample_branch):
    with patch("flask.render_template", return_value="R") as rt:
        FinancialService.financial_overview("month", None, sample_branch.id)
        assert rt.call_args[1]["financial_data"]["platform_mode"] is True
