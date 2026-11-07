"""Income tax service — estimate and idempotent accrual."""

from decimal import Decimal
from unittest.mock import MagicMock

from services.income_tax_service import IncomeTaxService


def test_estimate_uae_uses_country_threshold(mocker):
    mocker.patch("services.income_tax_service.IncomeTaxService._country", return_value="AE")
    # 475,000 - 375,000 = 100,000 excess @9% = 9,000
    out = IncomeTaxService.estimate(1, taxable_profit=Decimal("475000"))
    assert out["tax"] == Decimal("9000.000")
    assert out["country"] == "AE"
    assert out["rate"] == Decimal("9")


def test_estimate_uae_below_threshold_zero(mocker):
    mocker.patch("services.income_tax_service.IncomeTaxService._country", return_value="AE")
    out = IncomeTaxService.estimate(1, taxable_profit=Decimal("200000"))
    assert out["tax"] == Decimal("0.000")


def test_estimate_ps_flat_rate(mocker):
    mocker.patch("services.income_tax_service.IncomeTaxService._country", return_value="PS")
    out = IncomeTaxService.estimate(1, taxable_profit=Decimal("100000"))
    assert out["tax"] == Decimal("15000.000")
    assert out["rate"] == Decimal("15")


def test_estimate_uses_pl_when_profit_not_supplied(mocker):
    mocker.patch("services.income_tax_service.IncomeTaxService._country", return_value="IL")
    mocker.patch(
        "services.income_tax_service.FiscalYearService.calculate_pl_balance",
        return_value={
            "net_income": Decimal("100000"),
            "total_revenue": Decimal("500000"),
            "total_expense": Decimal("400000"),
        },
    )
    out = IncomeTaxService.estimate(1, fiscal_year=2026)
    # 23% of 100,000
    assert out["tax"] == Decimal("23000.000")
    assert out["net_income"] == Decimal("100000")


def test_estimate_without_profit_and_year_raises(mocker):
    mocker.patch("services.income_tax_service.IncomeTaxService._country", return_value="AE")
    try:
        IncomeTaxService.estimate(1)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_accrue_posts_balanced_lines(mocker):
    mocker.patch("services.income_tax_service.IncomeTaxService._country", return_value="AE")
    mocker.patch("services.income_tax_service.IncomeTaxService.find_accrual", return_value=None)
    mocker.patch("services.income_tax_service.GLService.ensure_core_accounts")
    mocker.patch(
        "services.income_tax_service.GLService.get_account_code_for_concept",
        side_effect=lambda c, **kw: "6350" if c == "INCOME_TAX_EXPENSE" else "2142",
    )
    post = mocker.patch("services.income_tax_service.post_or_fail", return_value=MagicMock(id=77))
    mocker.patch("services.income_tax_service.db.session.flush")

    out = IncomeTaxService.accrue(1, 2026, taxable_profit=Decimal("475000"))
    assert out["already_accrued"] is False
    assert out["tax"] == Decimal("9000.000")
    assert out["entry"].id == 77
    post.assert_called_once()
    lines = post.call_args[0][0]
    assert lines[0]["concept_code"] == "INCOME_TAX_EXPENSE"
    assert lines[0]["debit"] == Decimal("9000.000")
    assert lines[1]["concept_code"] == "INCOME_TAX_PAYABLE"
    assert lines[1]["credit"] == Decimal("9000.000")
    assert post.call_args[1]["reference_type"] == "IncomeTax"
    assert post.call_args[1]["reference_id"] == 2026


def test_accrue_is_idempotent(mocker):
    existing = MagicMock(id=55)
    mocker.patch("services.income_tax_service.IncomeTaxService.find_accrual", return_value=existing)
    post = mocker.patch("services.income_tax_service.post_or_fail")
    out = IncomeTaxService.accrue(1, 2026, taxable_profit=Decimal("475000"))
    assert out["already_accrued"] is True
    assert out["entry"] is existing
    post.assert_not_called()


def test_accrue_zero_tax_posts_nothing(mocker):
    mocker.patch("services.income_tax_service.IncomeTaxService._country", return_value="AE")
    mocker.patch("services.income_tax_service.IncomeTaxService.find_accrual", return_value=None)
    post = mocker.patch("services.income_tax_service.post_or_fail")
    out = IncomeTaxService.accrue(1, 2026, taxable_profit=Decimal("100000"))
    assert out["already_accrued"] is False
    assert out["entry"] is None
    post.assert_not_called()
