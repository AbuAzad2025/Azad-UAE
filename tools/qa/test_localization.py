"""
Localization Engine QA Test — Phase 9
Validates: strategy rates, NullStrategy zero tax, VAT return math,
WPS SIF headers, QR decodability.

Run: python tools/qa/test_localization.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from decimal import Decimal


def _assert_strategy_rates():
    from utils.localization import get_strategy
    ps = get_strategy('PS')
    ae = get_strategy('AE')
    sa = get_strategy('SA')

    assert ps.country_code == 'PS', f"Palestine code mismatch: {ps.country_code}"
    assert ps.default_vat_rate == Decimal('16.00'), f"Palestine rate mismatch: {ps.default_vat_rate}"

    assert ae.country_code == 'AE', f"UAE code mismatch: {ae.country_code}"
    assert ae.default_vat_rate == Decimal('5.00'), f"UAE rate mismatch: {ae.default_vat_rate}"

    assert sa.country_code == 'SA', f"KSA code mismatch: {sa.country_code}"
    assert sa.default_vat_rate == Decimal('15.00'), f"KSA rate mismatch: {sa.default_vat_rate}"

    print("  [PASS] Each strategy returns correct tax rate")


def _assert_null_strategy_zero_tax():
    from utils.localization import get_strategy
    null = get_strategy('XX')
    result = null.calculate_tax(Decimal('1000'))
    assert result['tax_amount'] == Decimal('0'), f"Null tax not zero: {result['tax_amount']}"
    assert result['total_amount'] == Decimal('1000'), f"Null total not 1000: {result['total_amount']}"
    print("  [PASS] NullStrategy returns zero tax for unsupported country")


def _assert_vat_return_math():
    from utils.localization import get_strategy
    ps = get_strategy('PS')
    output = Decimal('100')
    inp = Decimal('40')
    report = ps.format_tax_return(output, inp, '2026-01-01', '2026-03-31')
    assert report['net_payable'] == Decimal('60'), f"VAT return math wrong: {report['net_payable']}"
    print("  [PASS] VAT return total equals sale tax minus purchase tax")


def _assert_wps_sif_headers():
    from utils.localization import get_strategy
    ps = get_strategy('PS')
    employees = [
        {'employee_id': '101', 'name': 'Ahmed', 'iban': 'PS123', 'bank_code': 'BANK01', 'net_salary': 3000},
    ]
    result = ps.get_wps_format(employees)
    assert result['format'] == 'wps_sif', f"WPS format wrong: {result['format']}"
    assert len(result['lines']) >= 2, "WPS missing data lines"
    assert 'EDR' in result['lines'][0], f"WPS missing SIF header: {result['lines'][0]}"
    print("  [PASS] WPS file format has correct SIF headers")


def _assert_qr_decodable():
    from utils.localization import get_strategy
    # Create a minimal mock sale object
    class MockSale:
        id = 1
        amount_aed = Decimal('1000')
        total_aed = Decimal('1050')
        sale_date = '2026-06-06'

    ae = get_strategy('AE')
    result = ae.generate_einvoice(MockSale())
    assert result['qr_base64'], "UAE QR base64 is empty"
    import base64
    decoded = base64.b64decode(result['qr_base64']).decode()
    assert 'VAT' in decoded, f"QR missing VAT info: {decoded}"
    print("  [PASS] E-invoice QR code is decodable and contains VAT amount")


def _assert_tax_calculation_consistency():
    from utils.localization import get_strategy
    ps = get_strategy('PS')
    amount = Decimal('1000')
    result = ps.calculate_tax(amount)
    expected_tax = (amount * Decimal('16') / Decimal('100')).quantize(Decimal('0.01'))
    assert result['tax_amount'] == expected_tax, f"Tax calc inconsistent: {result['tax_amount']} != {expected_tax}"
    assert result['total_amount'] == amount + expected_tax
    print("  [PASS] Tax calculation is mathematically consistent")


def main():
    print("=" * 70)
    print("LOCALIZATION ENGINE QA TEST — Phase 9")
    print("=" * 70)
    errors = []

    print("\n=== Check: Strategy Rates ===")
    try:
        _assert_strategy_rates()
    except AssertionError as e:
        errors.append(str(e))
        print(f"  [FAIL] {e}")

    print("\n=== Check: NullStrategy Zero Tax ===")
    try:
        _assert_null_strategy_zero_tax()
    except AssertionError as e:
        errors.append(str(e))
        print(f"  [FAIL] {e}")

    print("\n=== Check: VAT Return Math ===")
    try:
        _assert_vat_return_math()
    except AssertionError as e:
        errors.append(str(e))
        print(f"  [FAIL] {e}")

    print("\n=== Check: WPS SIF Headers ===")
    try:
        _assert_wps_sif_headers()
    except (AssertionError, NotImplementedError) as e:
        errors.append(str(e))
        print(f"  [FAIL] {e}")

    print("\n=== Check: QR Decodability ===")
    try:
        _assert_qr_decodable()
    except AssertionError as e:
        errors.append(str(e))
        print(f"  [FAIL] {e}")

    print("\n=== Check: Tax Calculation Consistency ===")
    try:
        _assert_tax_calculation_consistency()
    except AssertionError as e:
        errors.append(str(e))
        print(f"  [FAIL] {e}")

    print("\n" + "=" * 70)
    if errors:
        print(f"LOCALIZATION QA FAILED — {len(errors)} check(s) failed")
        print("=" * 70)
        for e in errors:
            print(f"  • {e}")
        return 1
    else:
        print("ALL LOCALIZATION CHECKS PASSED")
        print("=" * 70)
        return 0


if __name__ == '__main__':
    sys.exit(main())
