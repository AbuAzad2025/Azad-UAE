"""Country tax profiles — single source of truth for statutory rates.

Every tax rate in the system MUST come from COUNTRY_TAX_PROFILES, never
from a hardcoded literal elsewhere. ``utils/tax_settings.py``,
``utils/localization/*`` and ``ai_knowledge/specialized/advanced_laws.py``
all read the same numbers from here; this module reads nothing from them
(and nothing here imports the DB, Flask, or they), so there is no import
cycle and the profiles are importable from migrations, scripts and tests.

Rates below are exactly the rates already present in this repository
(``ai_knowledge/specialized/advanced_laws.py`` and
``utils/localization/{palestine,uae,ksa}.py``). Where the repository does
not carry a statutory rate (social security, withholding tax, most VAT
registration thresholds), the field is ``None`` and labelled
``configurable``: the tenant supplies it, the system never invents it.

Supported VAT countries: PS 16%, IL 18%, AE 5%, SA 15%.
Unsupported countries resolve to the ``XX`` (null) profile: zero VAT,
no filing format, generic TRN check.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal

__all__ = [
    "COUNTRY_TAX_PROFILES",
    "NULL_PROFILE",
    "SUPPORTED_COUNTRIES",
    "get_country_profile",
    "is_supported_country",
    "vat_rate_for_country",
    "corporate_rate_for_country",
    "corporate_threshold_for_country",
    "personal_brackets_for_country",
    "customs_rate_for_country",
    "excise_rate_for_country",
    "zakat_rate_for_country",
    "validate_tax_number",
    "compute_progressive_tax",
    "compute_corporate_tax",
    "social_insurance_amount",
    "payroll_income_tax_amount",
]

# (upper_bound_inclusive, marginal_rate_percent) — progressive brackets.
# ``None`` upper bound means the top bracket (no ceiling).
_PA_BRACKETS = (
    (Decimal("48000"), Decimal("0")),
    (Decimal("96000"), Decimal("5")),
    (Decimal("192000"), Decimal("10")),
    (Decimal("384000"), Decimal("15")),
    (None, Decimal("20")),
)

# IL tax credit point (נקדת זיכוי) annual value 2025 — deducted from the tax
# bill after brackets apply. 2.25 points for a single adult (no children).
# The employer withholds on the assumption the employee claims the statutory
# minimum; anything more is the employee's responsibility in the annual return.
_IL_CREDIT_POINT_ANNUAL = Decimal("2904.00")
_IL_DEFAULT_CREDIT_POINTS = Decimal("2.25")

_IL_BRACKETS = (
    (Decimal("77480"), Decimal("10")),
    (Decimal("110880"), Decimal("14")),
    (Decimal("178080"), Decimal("20")),
    (Decimal("247440"), Decimal("31")),
    (Decimal("514920"), Decimal("35")),
    (None, Decimal("47")),
)

NULL_PROFILE = {
    "code": "XX",
    "name": "Unknown / Not Supported",
    "vat_rate": Decimal("0"),
    "vat_return_format": "null",
    "vat_registration_threshold": None,
    "vat_registration_currency": None,
    "corporate_rate": Decimal("0"),
    "corporate_threshold": None,
    "corporate_threshold_currency": None,
    "zakat_rate": None,
    "personal_brackets": (),
    "customs_rates": {},
    "customs_default_rate": None,
    "excise_rates": {},
    "wht_default_rate": None,
    "social_employee_rate": None,
    "social_employer_rate": None,
    "social_employee_rate_upper": None,
    "social_employer_rate_upper": None,
    "social_ceiling": None,
    "social_floor": None,
    "pension_national_rate_employee": None,
    "pension_national_rate_employer": None,
    "pension_ceiling": None,
    "pension_floor": None,
    "gosi_joined_2024_07_03_or_later": None,
    "gosi_joined_before": None,
    "gosi_non_national_employer": None,
    "gosi_ceiling": None,
    "gosi_floor": None,
    "income_tax_credit_points_applies": False,
    "payroll_national_flag_required": False,
    "social_configurable": True,
    "tax_number_pattern": r"^\d{5,}$",
    "filing_note": "Country not supported: zero VAT, no statutory filing format.",
}

COUNTRY_TAX_PROFILES = {
    "PS": {
        "code": "PS",
        "name": "Palestine (فلسطين)",
        "vat_rate": Decimal("16.00"),
        "vat_return_format": "pma_xml_v1",
        "vat_registration_threshold": None,
        "vat_registration_currency": None,
        "corporate_rate": Decimal("15"),
        "corporate_threshold": None,
        "corporate_threshold_currency": None,
        "zakat_rate": None,
        "personal_brackets": _PA_BRACKETS,
        "customs_rates": {"agricultural": Decimal("10"), "industrial": Decimal("15"), "luxury": Decimal("30")},
        "customs_default_rate": Decimal("15"),
        "excise_rates": {},
        "wht_default_rate": None,
        "social_employee_rate": Decimal("7.00"),
        "social_employer_rate": Decimal("9.00"),
        "social_ceiling": Decimal("18800"),
        "social_floor": Decimal("1880"),
        "income_tax_credit_points_applies": False,
        "payroll_national_flag_required": False,
        "social_configurable": True,
        "tax_number_pattern": r"^\d{9,11}$",
        "filing_note": "VAT return: PMA MoF XML. Corporate income tax 15% standard.",
    },
    "IL": {
        "code": "IL",
        "name": "Israel (إسرائيل)",
        "vat_rate": Decimal("18.00"),
        "vat_return_format": "il_vat_v1",
        "vat_registration_threshold": None,
        "vat_registration_currency": None,
        "corporate_rate": Decimal("23"),
        "corporate_threshold": None,
        "corporate_threshold_currency": None,
        "zakat_rate": None,
        "personal_brackets": _IL_BRACKETS,
        "customs_rates": {"agricultural": Decimal("12"), "industrial": Decimal("18"), "luxury": Decimal("35")},
        "customs_default_rate": Decimal("18"),
        "excise_rates": {},
        "wht_default_rate": None,
        "social_employee_rate": Decimal("3.50"),
        "social_employer_rate": Decimal("4.51"),
        "social_employee_rate_upper": Decimal("12.00"),
        "social_employer_rate_upper": Decimal("7.60"),
        "social_ceiling": Decimal("50695"),
        "social_floor": Decimal("7522"),
        "income_tax_credit_points_applies": True,
        "payroll_national_flag_required": False,
        "social_configurable": True,
        "tax_number_pattern": r"^\d{9}$",
        "filing_note": "VAT return: Israeli Tax Authority (Mas Hachnaasa) report.",
    },
    "AE": {
        "code": "AE",
        "name": "UAE (الإمارات)",
        "vat_rate": Decimal("5.00"),
        "vat_return_format": "fta_vat201_v1",
        "vat_registration_threshold": Decimal("375000"),
        "vat_registration_currency": "AED",
        "corporate_rate": Decimal("9"),
        "corporate_threshold": Decimal("375000"),
        "corporate_threshold_currency": "AED",
        "zakat_rate": None,
        "personal_brackets": (),
        "customs_rates": {"standard": Decimal("5")},
        "customs_default_rate": Decimal("5"),
        "excise_rates": {"tobacco": Decimal("100"), "energy_drinks": Decimal("100"), "soft_drinks": Decimal("50")},
        "wht_default_rate": None,
        "pension_national_rate_employee": Decimal("11"),
        "pension_national_rate_employer": Decimal("15"),
        "pension_ceiling": Decimal("70000"),
        "pension_floor": Decimal("3000"),
        "social_configurable": True,
        "tax_number_pattern": r"^\d{15}$",
        "filing_note": (
            "VAT return: FTA VAT201. Corporate tax: 0% up to AED 375,000 taxable "
            "income, 9% above (Federal Decree-Law No. 47 of 2022). The threshold "
            "is a profile field so it can be lowered/rised without a code change."
        ),
    },
    "SA": {
        "code": "SA",
        "name": "Saudi Arabia (السعودية)",
        "vat_rate": Decimal("15.00"),
        "vat_return_format": "zatca_vat_v3",
        "vat_registration_threshold": None,
        "vat_registration_currency": None,
        "corporate_rate": Decimal("20"),
        "corporate_threshold": None,
        "corporate_threshold_currency": None,
        "zakat_rate": Decimal("2.5"),
        "personal_brackets": (),
        "customs_rates": {"standard": Decimal("15")},
        "customs_default_rate": Decimal("15"),
        "excise_rates": {"tobacco": Decimal("100"), "energy_drinks": Decimal("100"), "soft_drinks": Decimal("50")},
        "wht_default_rate": None,
        "gosi_joined_2024_07_03_or_later": {
            "employee": Decimal("10.25"),
            "employer": Decimal("12.25"),
        },
        "gosi_joined_before": {
            "employee": Decimal("9.75"),
            "employer": Decimal("11.75"),
        },
        "gosi_non_national_employer": Decimal("2"),
        "gosi_ceiling": Decimal("45000"),
        "gosi_floor": Decimal("1500"),
        "social_configurable": True,
        "tax_number_pattern": r"^3\d{14}$",
        "filing_note": "VAT return: ZATCA. Corporate tax 20%; zakat 2.5% applies per ZATCA rules (tenant-configured).",
    },
}

SUPPORTED_COUNTRIES = tuple(COUNTRY_TAX_PROFILES.keys())


def _norm(code) -> str:
    return (code or "").strip().upper()


def get_country_profile(code) -> dict:
    """Return the statutory profile for a country code, else the null profile."""
    return COUNTRY_TAX_PROFILES.get(_norm(code), NULL_PROFILE)


def is_supported_country(code) -> bool:
    return _norm(code) in COUNTRY_TAX_PROFILES


def vat_rate_for_country(code) -> Decimal:
    return Decimal(str(get_country_profile(code).get("vat_rate") or 0))


def corporate_rate_for_country(code) -> Decimal:
    return Decimal(str(get_country_profile(code).get("corporate_rate") or 0))


def corporate_threshold_for_country(code) -> Decimal | None:
    val = get_country_profile(code).get("corporate_threshold")
    return Decimal(str(val)) if val is not None else None


def personal_brackets_for_country(code) -> tuple:
    return tuple(get_country_profile(code).get("personal_brackets") or ())


def customs_rate_for_country(code, category: str | None = None) -> Decimal | None:
    p = get_country_profile(code)
    if category and category in (p.get("customs_rates") or {}):
        return Decimal(str(p["customs_rates"][category]))
    default = p.get("customs_default_rate")
    return Decimal(str(default)) if default is not None else None


def excise_rate_for_country(code, category: str | None = None) -> Decimal | None:
    p = get_country_profile(code)
    rates = p.get("excise_rates") or {}
    if category and category in rates:
        return Decimal(str(rates[category]))
    return None


def zakat_rate_for_country(code) -> Decimal | None:
    val = get_country_profile(code).get("zakat_rate")
    return Decimal(str(val)) if val is not None else None


def validate_tax_number(tax_number: str, country_code=None) -> bool:
    """Validate a tax registration number against the country's pattern."""
    if not tax_number:
        return False
    cleaned = re.sub(r"\D", "", str(tax_number).strip())
    pattern = get_country_profile(country_code).get("tax_number_pattern") or r"^\d{5,}$"
    return bool(re.match(pattern, cleaned))


def compute_progressive_tax(income, brackets) -> Decimal:
    """Marginal-bracket tax. income in the country's filing currency."""
    total = Decimal(str(income or 0))
    if total <= 0:
        return Decimal("0")
    tax = Decimal("0")
    lower = Decimal("0")
    for upper, rate in brackets:
        if total <= lower:
            break
        slice_top = total if upper is None else min(total, Decimal(str(upper)))
        tax += (slice_top - lower) * Decimal(str(rate)) / Decimal("100")
        if upper is None:
            break
        lower = Decimal(str(upper))
    return tax.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def compute_corporate_tax(taxable_profit, country_code=None, *, tenant_threshold=None) -> dict:
    """Corporate (income) tax on taxable profit, per the country profile.

    UAE: 0% up to AED 375,000 then 9% on the excess — the threshold is a
    profile field, and ``tenant_threshold`` overrides it when the tenant
    configures its own. PS/IL/SA: flat rate, no threshold.
    """
    profit = Decimal(str(taxable_profit or 0))
    profile = get_country_profile(country_code)
    rate = Decimal(str(profile.get("corporate_rate") or 0))
    threshold = tenant_threshold
    if threshold is None:
        raw = profile.get("corporate_threshold")
        threshold = Decimal(str(raw)) if raw is not None else None
    if profit <= 0 or rate <= 0:
        return {
            "tax": Decimal("0"),
            "rate": rate,
            "threshold": threshold,
            "taxable": profit,
            "country": profile.get("code"),
        }
    if threshold is not None and profit <= threshold:
        taxable = Decimal("0")
    elif threshold is not None:
        taxable = profit - threshold
    else:
        taxable = profit
    tax = (taxable * rate / Decimal("100")).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    return {
        "tax": tax,
        "rate": rate,
        "threshold": threshold,
        "taxable": taxable,
        "country": profile.get("code"),
    }


# --- Payroll: statutory social insurance and income tax -----------------------


def _q3(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def _tier_split(gross: Decimal, threshold: Decimal, ceiling: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    """Split a contribution base into (lower_band, upper_band, capped_base)."""
    g = min(Decimal(str(gross or 0)), Decimal(str(ceiling)))
    lower = min(g, Decimal(str(threshold)))
    upper = max(Decimal("0"), g - lower)
    return lower, upper, g


def social_insurance_amount(gross, country_code, *, is_national=False, joined_2024_07_03_or_later=False) -> dict:
    """Statutory employee/employer social insurance contribution for one month.

    Sources of truth are the ``social_*``/``gosi_*``/``pension_*`` fields on the
    country profile in this module — never a rate remembered in a service.
    Returns ``{"employee": Decimal, "employer": Decimal, "ceiling": Decimal|None,
    "floor": Decimal|None, "eligible": bool}`` quantized to 3dp.

    PS — NSSF (law 6/2016): employee 7%, employer 9% on the base, capped at the
    statutory ceiling (in 2025 terms: 10x the minimum wage).
    IL — Bituach Leumi + Mas Briut (2025): two tiers, up to the reduced-rate
    income threshold and up to the max-insurable salary; above the maximum
    salary both sides are zero.
    SA — GOSI (2025): Saudi nationals; rates depend on the join date
    (before/on-after 2024-07-03). Non-nationals: employer pays 2% occupational
    hazards only.
    AE — GPSSA (Federal Decree Law No. 57 of 2023): nationals only, 11%/15%.
    """
    code = _norm(country_code)
    profile = get_country_profile(code)
    g = Decimal(str(gross or 0))
    if g <= 0:
        return {"employee": Decimal("0"), "employer": Decimal("0"), "ceiling": None, "floor": None, "eligible": False}

    if code == "PS":
        ceiling = Decimal(str(profile.get("social_ceiling") or 0)) or None
        base = min(g, ceiling) if ceiling is not None else g
        employee = _q3(base * Decimal(str(profile.get("social_employee_rate") or 0)) / Decimal("100"))
        employer = _q3(base * Decimal(str(profile.get("social_employer_rate") or 0)) / Decimal("100"))
        return {
            "employee": employee,
            "employer": employer,
            "ceiling": ceiling,
            "floor": Decimal(str(profile.get("social_floor") or 0)),
            "eligible": True,
        }

    if code == "IL":
        lower = Decimal(str(profile.get("social_floor") or 0))
        ceiling = Decimal(str(profile.get("social_ceiling") or 0))
        lower_amt, upper_amt, capped = _tier_split(g, lower, ceiling)
        emp_lower = Decimal(str(profile.get("social_employee_rate") or 0))
        emp_upper = Decimal(str(profile.get("social_employee_rate_upper") or 0))
        er_lower = Decimal(str(profile.get("social_employer_rate") or 0))
        er_upper = Decimal(str(profile.get("social_employer_rate_upper") or 0))
        employee = _q3(lower_amt * emp_lower / Decimal("100") + upper_amt * emp_upper / Decimal("100"))
        employer = _q3(lower_amt * er_lower / Decimal("100") + upper_amt * er_upper / Decimal("100"))
        return {"employee": employee, "employer": employer, "ceiling": ceiling, "floor": lower, "eligible": True}

    if code == "SA":
        gosi_ceiling = Decimal(str(profile.get("gosi_ceiling") or 0))
        base = min(g, gosi_ceiling)
        if not is_national:
            # Occupational hazards only, employer side — no employee share.
            employee = Decimal("0")
            employer = _q3(base * Decimal(str(profile.get("gosi_non_national_employer") or 0)) / Decimal("100"))
            eligible = employer > 0
        else:
            joined = bool(joined_2024_07_03_or_later)
            rates = profile.get("gosi_joined_2024_07_03_or_later" if joined else "gosi_joined_before") or {}
            employee = _q3(base * Decimal(str(rates.get("employee") or 0)) / Decimal("100"))
            employer = _q3(base * Decimal(str(rates.get("employer") or 0)) / Decimal("100"))
            eligible = True
        return {
            "employee": employee,
            "employer": employer,
            "ceiling": gosi_ceiling,
            "floor": Decimal(str(profile.get("gosi_floor") or 0)),
            "eligible": eligible,
        }

    if code == "AE":
        if not is_national:
            return {
                "employee": Decimal("0"),
                "employer": Decimal("0"),
                "ceiling": None,
                "floor": None,
                "eligible": False,
            }
        ceiling = Decimal(str(profile.get("pension_ceiling") or 0))
        base = min(g, ceiling)
        employee = _q3(base * Decimal(str(profile.get("pension_national_rate_employee") or 0)) / Decimal("100"))
        employer = _q3(base * Decimal(str(profile.get("pension_national_rate_employer") or 0)) / Decimal("100"))
        return {
            "employee": employee,
            "employer": employer,
            "ceiling": ceiling,
            "floor": Decimal(str(profile.get("pension_floor") or 0)),
            "eligible": True,
        }

    return {"employee": Decimal("0"), "employer": Decimal("0"), "ceiling": None, "floor": None, "eligible": False}


def payroll_income_tax_amount(annual_taxable, country_code, *, credit_points=None) -> dict:
    """Annual income tax on the taxable income for the employee's country.

    Progressive schedule from ``personal_brackets``. IL deducts the statutory
    tax credit points (נק' זיכוי) from the bill: the default is a single adult
    with 2.25 points at the 2025 published value. PS has a 48k exempt band
    built into its brackets and takes no credit points. AE and SA levy no
    personal income tax.
    """
    code = _norm(country_code)
    profile = get_country_profile(code)
    brackets = personal_brackets_for_country(code)
    t = Decimal(str(annual_taxable or 0))
    if not brackets or t <= 0:
        return {"tax": Decimal("0"), "effective_rate": Decimal("0"), "country": code}
    tax = compute_progressive_tax(t, brackets)
    if bool(profile.get("income_tax_credit_points_applies")):
        points = Decimal(str(credit_points)) if credit_points is not None else _IL_DEFAULT_CREDIT_POINTS
        tax = max(Decimal("0"), _q3(tax - points * _IL_CREDIT_POINT_ANNUAL))
    rate = _q3(tax / t * Decimal("100")) if t > 0 else Decimal("0")
    return {"tax": tax, "effective_rate": rate, "country": code}
