"""Per-line VAT categories — mixed documents (Standard/Zero/Exempt)."""

from decimal import Decimal

from utils.tax_categories import compute_amounts


def test_all_standard_exclusive_matches_legacy_math():
    lines = [{"line_total": Decimal("100"), "tax_category": "standard"}]
    taxable, tax, total, _ = compute_amounts(
        lines,
        tax_rate=Decimal("18"),
        discount_amount=Decimal("0"),
        prices_include_vat=False,
        tax_categories_enabled=True,
    )
    assert taxable == Decimal("100.000")
    assert tax == Decimal("18.000")
    assert total == Decimal("118.000")


def test_zero_rated_line_excluded_from_tax():
    lines = [
        {"line_total": Decimal("100"), "tax_category": "standard"},
        {"line_total": Decimal("50"), "tax_category": "zero"},
    ]
    taxable, tax, total, _ = compute_amounts(
        lines,
        tax_rate=Decimal("18"),
        discount_amount=Decimal("0"),
        prices_include_vat=False,
        tax_categories_enabled=True,
    )
    assert tax == Decimal("18.000")  # 100 * 18%
    assert taxable == Decimal("150.000")  # standard + zero
    assert total == Decimal("168.000")


def test_exempt_line_excluded_from_base_and_tax():
    lines = [
        {"line_total": Decimal("100"), "tax_category": "standard"},
        {"line_total": Decimal("50"), "tax_category": "exempt"},
    ]
    taxable, tax, total, _ = compute_amounts(
        lines,
        tax_rate=Decimal("18"),
        discount_amount=Decimal("0"),
        prices_include_vat=False,
        tax_categories_enabled=True,
    )
    assert tax == Decimal("18.000")
    assert taxable == Decimal("100.000")
    assert total == Decimal("168.000")


def test_inclusive_split_extracts_tax_on_standard_only():
    lines = [
        {"line_total": Decimal("105"), "tax_category": "standard"},  # 100 + 5 VAT
        {"line_total": Decimal("50"), "tax_category": "zero"},
    ]
    taxable, tax, total, _ = compute_amounts(
        lines, tax_rate=Decimal("5"), discount_amount=Decimal("0"), prices_include_vat=True, tax_categories_enabled=True
    )
    assert tax == Decimal("5.000")
    assert total == Decimal("155.000")


def test_discount_allocated_pro_rata():
    lines = [
        {"line_total": Decimal("200"), "tax_category": "standard"},
        {"line_total": Decimal("100"), "tax_category": "zero"},
    ]
    taxable, tax, total, _ = compute_amounts(
        lines,
        tax_rate=Decimal("10"),
        discount_amount=Decimal("30"),
        prices_include_vat=False,
        tax_categories_enabled=True,
    )
    # after_discount = 270; standard share = 180, zero = 90; tax = 18
    assert tax == Decimal("18.000")
    assert total == Decimal("288.000")


def test_tenant_flag_off_coerces_zero_to_standard():
    # With the flag off, effective_tax_category returns "standard" for any
    # input — verified via the helper directly.
    from utils.tax_settings import effective_tax_category

    assert effective_tax_category("zero", None) == "standard"
    assert effective_tax_category("exempt", None) == "standard"


def test_sale_model_all_standard_matches_legacy():
    from models import Sale

    sale = Sale(
        tenant_id=1,
        subtotal=Decimal("0"),
        discount_amount=Decimal("0"),
        promotion_discount_amount=Decimal("0"),
        shipping_cost=Decimal("0"),
        tax_rate=Decimal("18"),
        tax_amount=Decimal("0"),
        taxable_amount=Decimal("0"),
        total_amount=Decimal("0"),
        amount=Decimal("0"),
        amount_aed=Decimal("0"),
        currency="ILS",
        base_currency="ILS",
        exchange_rate=Decimal("1"),
        prices_include_vat=False,
    )
    from models import SaleLine

    line = SaleLine(
        tenant_id=1,
        sale_id=0,
        product_id=1,
        quantity=Decimal("1"),
        unit_price=Decimal("100"),
        line_total=Decimal("100"),
        tax_category="standard",
    )
    sale.lines = [line]
    sale.calculate_totals()
    assert sale.tax_amount == Decimal("18.000")
    assert sale.total_amount == Decimal("118.000")
