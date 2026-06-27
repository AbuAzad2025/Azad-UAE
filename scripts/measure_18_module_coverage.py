#!/usr/bin/env python3
"""Measure per-module statement coverage (isolated runs with coverage erase)."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULES = [
    ("utils/tenant_orm.py", "tests/unit/utils/test_tenant_orm_assurance.py"),
    ("utils/tenant_branding.py", "tests/unit/utils/test_tenant_branding_assurance.py"),
    ("utils/static_asset_paths.py", "tests/unit/utils/test_static_asset_paths_assurance.py"),
    ("utils/safe_redirect.py", "tests/unit/utils/test_safe_redirect_assurance.py"),
    ("utils/localization/engine.py", "tests/unit/utils/test_localization_engine_assurance.py"),
    ("utils/field_validators.py", "tests/unit/utils/test_field_validators_assurance.py"),
    ("services/serial_tracking_service.py", "tests/unit/test_logistics_serial_assurance.py"),
    ("services/financial_service.py", "tests/unit/test_financial_service_assurance.py"),
    ("services/exchange_rate_service.py", "tests/unit/test_exchange_rate_service_assurance.py"),
    ("services/aging_analysis_service.py", "tests/unit/test_aging_analysis_service_assurance.py"),
    ("models/system_settings.py", "tests/unit/models/test_system_settings_assurance.py"),
    ("models/tenant.py", "tests/unit/models/test_tenant_model_assurance.py"),
    ("models/product_return.py", "tests/unit/models/test_product_return_assurance.py"),
    ("models/partner_commission.py", "tests/unit/models/test_partner_commission_assurance.py"),
    ("models/invoice_settings.py", "tests/unit/models/test_invoice_settings_assurance.py"),
    ("models/expense.py", "tests/unit/models/test_expense_assurance.py"),
    ("models/document_sequence.py", "tests/unit/test_document_sequence_assurance.py"),
    ("models/audit.py", "tests/unit/models/test_audit_model_assurance.py"),
]


def run_one(rel_path: str, test_file: str) -> tuple[int, int, list[str]]:
    subprocess.run([sys.executable, "-m", "coverage", "erase"], cwd=ROOT, capture_output=True)
    cmd = [
        sys.executable, "-m", "coverage", "run",
        "--source=.",
        "-m", "pytest", str(ROOT / test_file),
        "-q", "--override-ini=addopts=-q --tb=no --import-mode=prepend",
    ]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    inc = rel_path.replace("/", "\\")
    report = subprocess.run(
        [sys.executable, "-m", "coverage", "report", "-m", "--include", inc],
        cwd=ROOT, capture_output=True, text=True,
    )
    pct = -1
    missing: list[str] = []
    for line in report.stdout.splitlines():
        if inc in line and "%" in line:
            parts = line.split()
            if parts[-1].endswith("%"):
                pct = int(parts[-1].rstrip("%"))
        if line.strip().startswith("Missing"):
            missing = line.split("Missing")[-1].strip().split(", ")
    return r.returncode, pct, missing


def main():
    results = []
    for rel, tf in MODULES:
        code, pct, missing = run_one(rel, tf)
        results.append((rel, pct, code, missing))
        print(f"{'OK' if code == 0 else 'FAIL'} {pct:3}% {rel}")
        if missing and missing != ['']:
            print(f"      missing: {', '.join(missing)}")
    print("\n=== SUMMARY ===")
    for rel, pct, code, _ in results:
        flag = "PASS" if code == 0 and pct >= 99 else ("FAIL" if code != 0 else "LOW")
        print(f"{pct:3}% [{flag}] {rel}")
    bad = [m for m, p, c, _ in results if c != 0 or p < 99]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
