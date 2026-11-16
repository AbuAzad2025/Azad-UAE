"""Regression tests for the verified financial-correctness fixes."""

from __future__ import annotations

from decimal import Decimal


def test_social_insurance_floors_are_applied_to_low_paid_employees():
    from utils.country_tax import social_insurance_amount

    ps = social_insurance_amount("1500", "PS")
    assert ps["employee"] == Decimal("131.600")  # 1880 * 7%
    assert ps["employer"] == Decimal("169.200")  # 1880 * 9%

    from datetime import date

    sa = social_insurance_amount(
        "1000",
        "SA",
        is_national=True,
        joined_2024_07_03_or_later=True,
        payroll_date=date(2025, 8, 1),
    )
    assert sa["employee"] > Decimal("0")
    # The base was the 1500 floor, not the 1000 gross:
    assert sa["employee"] == (Decimal("1500") * Decimal("10.25") / Decimal("100")).quantize(Decimal("0.001"))

    ae = social_insurance_amount("2000", "AE", is_national=True)
    assert ae["employee"] == Decimal("330.000")  # 3000 * 11%
    assert ae["employer"] == Decimal("450.000")  # 3000 * 15%


def test_straight_line_depreciation_never_exceeds_the_depreciable_base():
    from models.fixed_asset import FixedAsset

    asset = FixedAsset(
        purchase_price=Decimal("1000"),
        salvage_value=Decimal("0"),
        useful_life_years=5,
        depreciation_method="straight_line",
        category="equipment",
        accumulated_depreciation=Decimal("0"),
    )
    monthly = asset.calculate_monthly_depreciation()
    assert monthly == Decimal("16.667")

    # Last period: only 0.001 of depreciable base is left.
    asset.accumulated_depreciation = Decimal("999.999")
    assert asset.calculate_monthly_depreciation() == Decimal("0.001")

    asset.accumulated_depreciation = Decimal("1000")
    assert asset.calculate_monthly_depreciation() == Decimal("0")


def test_purchase_delete_reverses_purchases_field_once(mocker):
    from services.purchase_service import PurchaseService

    purchase = mocker.MagicMock(supplier_id=7, tenant_id=1, amount_aed=Decimal("100"), id=3)
    supplier = mocker.MagicMock(
        total_purchases_aed=Decimal("100"), total_paid_aed=Decimal("0"), _locked=mocker.MagicMock()
    )
    mocker.patch(
        "models.Supplier.query",
        mocker.MagicMock(
            filter_by=mocker.MagicMock(return_value=mocker.MagicMock(first=mocker.MagicMock(return_value=supplier)))
        ),
    )
    mocker.patch(
        "services.purchase_service.PurchaseLine",
        mocker.MagicMock(
            query=mocker.MagicMock(filter_by=mocker.MagicMock(return_value=mocker.MagicMock(delete=mocker.MagicMock())))
        ),
    )
    mocker.patch("services.purchase_service.db")

    PurchaseService.delete_purchase(purchase)

    supplier.apply_purchase.assert_called_once_with(Decimal("-100"))
    assert supplier.apply_payment.call_count == 0
