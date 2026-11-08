"""Import levy defaults — statutory customs/excise wiring (landed-cost flow)."""

from decimal import Decimal

from services.purchase_service import compute_import_levy_defaults

# (quantity, unit_cost, discount_percent, excise_category)


def test_ae_customs_default_applies():
    customs, excise = compute_import_levy_defaults(
        [(Decimal("10"), Decimal("100"), Decimal("0"), None)],
        country="AE",
        customs_duty=None,
        excise_amount=None,
    )
    # AE standard rate: 5% on CIF value (1000)
    assert customs == Decimal("50.000")
    assert excise == Decimal("0")


def test_ps_customs_default_uses_profile_rate():
    customs, _ = compute_import_levy_defaults(
        [(Decimal("10"), Decimal("100"), Decimal("0"), None)],
        country="PS",
        customs_duty=None,
        excise_amount=None,
    )
    # PS default: 15%
    assert customs == Decimal("150.000")


def test_il_customs_default_uses_profile_rate():
    customs, _ = compute_import_levy_defaults(
        [(Decimal("10"), Decimal("100"), Decimal("0"), None)],
        country="IL",
        customs_duty=None,
        excise_amount=None,
    )
    # IL default: 18%
    assert customs == Decimal("180.000")


def test_sa_customs_default_uses_profile_rate():
    customs, _ = compute_import_levy_defaults(
        [(Decimal("10"), Decimal("100"), Decimal("0"), None)],
        country="SA",
        customs_duty=None,
        excise_amount=None,
    )
    # SA default: 15%
    assert customs == Decimal("150.000")


def test_discount_reduces_the_customs_base():
    customs, _ = compute_import_levy_defaults(
        [(Decimal("10"), Decimal("100"), Decimal("50"), None)],
        country="AE",
        customs_duty=None,
        excise_amount=None,
    )
    # CIF = 500, 5% = 25
    assert customs == Decimal("25.000")


def test_explicit_customs_wins_over_default():
    customs, _ = compute_import_levy_defaults(
        [(Decimal("10"), Decimal("100"), Decimal("0"), None)],
        country="AE",
        customs_duty=Decimal("7"),
        excise_amount=None,
    )
    assert customs == Decimal("7")


def test_ae_excise_tobacco_full_rate_on_customs_value():
    customs, excise = compute_import_levy_defaults(
        [(Decimal("10"), Decimal("100"), Decimal("0"), "tobacco")],
        country="AE",
        customs_duty=None,
        excise_amount=None,
    )
    # CIF 1000 + customs 50 => base 1050, tobacco 100%
    assert customs == Decimal("50.000")
    assert excise == Decimal("1050.000")


def test_ae_excise_soft_drinks_half_rate():
    _, excise = compute_import_levy_defaults(
        [(Decimal("10"), Decimal("100"), Decimal("0"), "soft_drinks")],
        country="AE",
        customs_duty=None,
        excise_amount=None,
    )
    # base 1050 * 50%
    assert excise == Decimal("525.000")


def test_excise_only_for_categorized_products():
    _, excise = compute_import_levy_defaults(
        [
            (Decimal("10"), Decimal("100"), Decimal("0"), None),
            (Decimal("10"), Decimal("100"), Decimal("0"), "energy_drinks"),
        ],
        country="AE",
        customs_duty=None,
        excise_amount=None,
    )
    assert excise == Decimal("1050.000")  # only the energy-drink line


def test_sa_excise_energy_drinks_full_rate():
    _, excise = compute_import_levy_defaults(
        [(Decimal("10"), Decimal("100"), Decimal("0"), "energy_drinks")],
        country="SA",
        customs_duty=None,
        excise_amount=None,
    )
    assert excise == Decimal("1150.000")  # base 1000 + customs 150 = 1150 * 100%


def test_explicit_excise_wins_over_computed():
    _, excise = compute_import_levy_defaults(
        [(Decimal("10"), Decimal("100"), Decimal("0"), "tobacco")],
        country="AE",
        customs_duty=None,
        excise_amount=Decimal("5"),
    )
    assert excise == Decimal("5")


def test_unsupported_country_defaults_to_zero_duty():
    customs, excise = compute_import_levy_defaults(
        [(Decimal("10"), Decimal("100"), Decimal("0"), "tobacco")],
        country="XX",
        customs_duty=None,
        excise_amount=None,
    )
    assert customs == Decimal("0")
    assert excise == Decimal("0")


def test_empty_lines_yield_zero():
    customs, excise = compute_import_levy_defaults(
        [],
        country="AE",
        customs_duty=None,
        excise_amount=None,
    )
    assert customs == Decimal("0.000")
    assert excise == Decimal("0.000")
