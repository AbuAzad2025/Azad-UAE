"""Cov4: advanced_analytics — ratios/edge-zero/trend/comparative/breakdown/forecast arcs."""

from __future__ import annotations

from unittest.mock import patch

from services.advanced_analytics import AdvancedFinancialAnalytics as AFA


def test_ratios_all_zero_branch(sample_tenant):
    with patch.object(AFA, "_calculate_balance_by_prefix", return_value=__import__("decimal").Decimal("0")):
        ratios = AFA.get_financial_ratios(tenant_id=sample_tenant.id)
    assert ratios["liquidity"]["current_ratio"] == 0
    assert ratios["profitability"]["net_profit_margin"] == 0
    assert ratios["efficiency"]["asset_turnover"] == 0
    assert ratios["leverage"]["debt_to_equity"] == 0
    assert ratios["base_data"]["net_profit"] == 0.0


def test_ratios_nonzero_math():
    from decimal import Decimal

    vals = {
        "11": Decimal("200"),
        "1": Decimal("1000"),
        "21": Decimal("100"),
        "2": Decimal("400"),
        "3": Decimal("600"),
        "4": Decimal("500"),
        "multi": Decimal("300"),
    }
    with patch.object(
        AFA,
        "_calculate_balance_by_prefix",
        side_effect=lambda *a, **k: vals.get(a[0] if isinstance(a[0], str) else "multi", Decimal("0")),
    ):
        ratios = AFA.get_financial_ratios(tenant_id=1)
    assert ratios["liquidity"]["current_ratio"] == 2.0
    assert ratios["profitability"]["net_profit_margin"] == 40.0
    assert ratios["leverage"]["debt_to_equity"] == float(Decimal("400") / Decimal("600"))


def test_balance_by_prefix_branches(db_session, sample_tenant, sample_gl_accounts):
    from datetime import date
    from decimal import Decimal

    from models import GLAccount

    acc = GLAccount.query.filter_by(tenant_id=sample_tenant.id, code="1111").first()
    assert acc is not None
    out = AFA._calculate_balance_by_prefix("111", date(2026, 1, 1), date(2026, 12, 31), tenant_id=sample_tenant.id)
    assert out == Decimal("0")
    out2 = AFA._calculate_balance_by_prefix(["11", "12"], tenant_id=sample_tenant.id)
    assert isinstance(out2, Decimal)


def test_account_type_balance_else_branch(db_session, sample_tenant, sample_gl_accounts):
    out = AFA._calculate_account_type_balance("asset", tenant_id=sample_tenant.id)
    assert out >= 0


def test_trend_and_change_math():
    with patch.object(AFA, "_calculate_account_type_balance", side_effect=[100, 60, 200, 50, 0, 0]):
        trends = AFA.get_trend_analysis(months=3)
    assert len(trends) == 3
    assert trends[0]["change"] == 0
    # Month 1: profit = 100-60 = 40
    # Month 2: profit = 200-50 = 150, change from 40 = ((150-40)/40)*100 = 275.0
    # Month 3: profit = 0-0 = 0, change from 150 = ((0-150)/150)*100 = -100.0
    assert trends[1]["change"] == 275.0
    assert trends[2]["change"] == -100.0


def test_comparative_unknown_period_skipped():
    out = AFA.get_comparative_analysis(periods=["current", "bogus"])
    assert set(out) == {"current"}
    out2 = AFA.get_comparative_analysis(periods=["last_month", "last_year"])
    assert set(out2) == {"last_month", "last_year"}


def test_breakdowns_sort_and_zero_pct(db_session, sample_tenant, sample_gl_accounts):
    exp = AFA.get_expense_breakdown(tenant_id=sample_tenant.id)
    assert exp["total"] == 0.0
    assert all(i["percentage"] == 0 for i in exp["items"])
    rev = AFA.get_revenue_breakdown(tenant_id=sample_tenant.id)
    assert rev["total"] == 0.0


def test_forecast_short_history_and_normal():
    with patch.object(AFA, "get_trend_analysis", return_value=[{"revenue": 1}]):
        assert AFA.get_forecasting_data() == []
    hist = [{"revenue": 100.0, "expenses": 60.0, "change": 10.0} for _ in range(12)]
    with patch.object(AFA, "get_trend_analysis", return_value=hist):
        fc = AFA.get_forecasting_data(months_ahead=2)
        assert len(fc) == 2
        assert fc[0]["is_forecast"] is True
    with patch.object(AFA, "get_trend_analysis", return_value=[{"revenue": 0.0, "expenses": 0.0}] * 12):
        fc = AFA.get_forecasting_data(months_ahead=1)
        assert fc[0]["margin"] == 0  # zero-revenue margin branch


def test_dashboard_summary_keys():
    with (
        patch.object(AFA, "get_financial_ratios", return_value={"r": 1}),
        patch.object(AFA, "get_trend_analysis", return_value=[]),
        patch.object(AFA, "get_expense_breakdown", return_value={}),
        patch.object(AFA, "get_revenue_breakdown", return_value={}),
        patch.object(AFA, "get_forecasting_data", return_value=[]),
    ):
        dash = AFA.get_dashboard_summary()
        assert set(dash) == {"ratios", "trends", "expense_breakdown", "revenue_breakdown", "forecast", "generated_at"}


def test_ratios_with_explicit_dates():
    from datetime import date, timedelta
    from decimal import Decimal

    today = date.today()
    with patch.object(AFA, "_calculate_balance_by_prefix", return_value=Decimal("0")):
        ratios = AFA.get_financial_ratios(date_from=today - timedelta(days=10), date_to=today, tenant_id=1)
    assert ratios["base_data"]["net_profit"] == 0.0


def test_trend_zero_previous_profit_uses_zero_change():
    with patch.object(AFA, "_calculate_account_type_balance", side_effect=[100, 100, 0, 0, 0, 0]):
        trends = AFA.get_trend_analysis(months=3)
    assert trends[0]["change"] == 0
    assert trends[1]["change"] == 0  # prev profit == 0 -> change = 0
    assert trends[2]["change"] == 0


def test_trend_empty_months_returns_empty():
    assert AFA.get_trend_analysis(months=0) == []


def test_comparative_default_periods(db_session, sample_tenant, sample_gl_accounts):
    out = AFA.get_comparative_analysis()
    assert set(out) == {"current", "last_month", "last_year"}


def test_balance_by_prefix_without_tenant(mocker, db_session, sample_gl_accounts):
    from decimal import Decimal

    with patch("utils.gl_tenant.active_tenant_id", return_value=None):
        out = AFA._calculate_balance_by_prefix("11")
    assert isinstance(out, Decimal)


def _seed_posted_lines(db_session, sample_tenant, entry_specs):
    from models import GLJournalEntry, GLJournalLine

    entries = []
    for idx, specs in enumerate(entry_specs):
        total_debit = sum(d for _, d, _ in specs)
        total_credit = sum(c for _, _, c in specs)
        entry = GLJournalEntry(
            tenant_id=sample_tenant.id,
            entry_number=f"cov4-aa-{idx}",
            entry_date=__import__("datetime").datetime(2026, 1, 15, 10, 0, 0),
            description="cov4 advanced analytics",
            total_debit=total_debit,
            total_credit=total_credit,
            status="posted",
            is_posted=True,
        )
        db_session.add(entry)
        db_session.flush()
        for account, debit, credit in specs:
            line = GLJournalLine(
                tenant_id=sample_tenant.id,
                entry_id=entry.id,
                account_id=account.id,
                debit=debit,
                credit=credit,
                amount_aed=debit - credit,
            )
            db_session.add(line)
        entries.append(entry)
    db_session.commit()
    return entries


def _cleanup_posted_lines(db_session, entries):
    from models import GLJournalEntry, GLJournalLine

    entries_created = db_session.query(GLJournalEntry).filter(GLJournalEntry.id.in_([e.id for e in entries])).all()
    entry_ids = [e.id for e in entries_created]
    GLJournalLine.query.filter(GLJournalLine.entry_id.in_(entry_ids)).delete(synchronize_session=False)
    GLJournalEntry.query.filter(GLJournalEntry.id.in_(entry_ids)).delete(synchronize_session=False)
    db_session.commit()


def _pick_account(sample_tenant, code_prefix, account_type):
    from models import GLAccount

    acc = (
        GLAccount.query.filter(
            GLAccount.tenant_id == sample_tenant.id,
            GLAccount.code.startswith(code_prefix),
            GLAccount.type == account_type,
            GLAccount.is_header.is_(False),
            GLAccount.is_active,
        )
        .order_by(GLAccount.code)
        .first()
    )
    assert acc is not None, f"no {account_type} account for prefix {code_prefix}"
    return acc


def test_prefix_is_pl_with_posted_lines(db_session, sample_tenant, sample_gl_accounts):
    from datetime import date
    from decimal import Decimal

    asset_acc = _pick_account(sample_tenant, "11", "asset")
    revenue_acc = _pick_account(sample_tenant, "4", "revenue")
    equity_acc = _pick_account(sample_tenant, "3", "equity")
    expense_acc = _pick_account(sample_tenant, "5", "expense")
    entries = _seed_posted_lines(
        db_session,
        sample_tenant,
        [
            [(asset_acc, Decimal("100"), Decimal("0")), (equity_acc, Decimal("0"), Decimal("100"))],
            [(revenue_acc, Decimal("0"), Decimal("50")), (expense_acc, Decimal("50"), Decimal("0"))],
        ],
    )
    try:
        asset_total = AFA._calculate_balance_by_prefix(
            "11", date(2026, 1, 1), date(2026, 1, 31), is_pl=True, tenant_id=sample_tenant.id
        )
        assert asset_total == Decimal("100")
        revenue_total = AFA._calculate_balance_by_prefix(
            "4", date(2026, 1, 1), date(2026, 1, 31), is_pl=True, tenant_id=sample_tenant.id
        )
        assert revenue_total == Decimal("50")
    finally:
        _cleanup_posted_lines(db_session, entries)


def test_account_type_balance_with_posted_lines(db_session, sample_tenant, sample_gl_accounts):
    from datetime import date, datetime
    from decimal import Decimal

    asset_acc = _pick_account(sample_tenant, "11", "asset")
    revenue_acc = _pick_account(sample_tenant, "4", "revenue")
    equity_acc = _pick_account(sample_tenant, "3", "equity")
    expense_acc = _pick_account(sample_tenant, "5", "expense")
    entries = _seed_posted_lines(
        db_session,
        sample_tenant,
        [
            [(asset_acc, Decimal("80"), Decimal("0")), (equity_acc, Decimal("0"), Decimal("80"))],
            [(revenue_acc, Decimal("0"), Decimal("30")), (expense_acc, Decimal("30"), Decimal("0"))],
        ],
    )
    try:
        from_a = date(2026, 1, 1)
        to_a = datetime(2026, 1, 31, 23, 59, 59)
        asset_total = AFA._calculate_account_type_balance("asset", from_a, to_a, tenant_id=sample_tenant.id)
        assert asset_total == Decimal("80")
        revenue_total = AFA._calculate_account_type_balance("revenue", from_a, to_a, tenant_id=sample_tenant.id)
        assert revenue_total == Decimal("30")
    finally:
        _cleanup_posted_lines(db_session, entries)


def test_breakdowns_percentage_with_balances(db_session, sample_tenant, sample_gl_accounts):
    from decimal import Decimal

    expense_acc = _pick_account(sample_tenant, "5", "expense")
    revenue_acc = _pick_account(sample_tenant, "4", "revenue")
    equity_acc = _pick_account(sample_tenant, "3", "equity")
    entries = _seed_posted_lines(
        db_session,
        sample_tenant,
        [
            [(expense_acc, Decimal("200"), Decimal("0")), (equity_acc, Decimal("0"), Decimal("200"))],
            [(revenue_acc, Decimal("0"), Decimal("150")), (equity_acc, Decimal("150"), Decimal("0"))],
        ],
    )
    try:
        exp = AFA.get_expense_breakdown(tenant_id=sample_tenant.id)
        assert exp["total"] > 0
        assert any(i["percentage"] > 0 for i in exp["items"])
        rev = AFA.get_revenue_breakdown(tenant_id=sample_tenant.id)
        assert rev["total"] > 0
        assert any(i["percentage"] > 0 for i in rev["items"])
    finally:
        _cleanup_posted_lines(db_session, entries)
