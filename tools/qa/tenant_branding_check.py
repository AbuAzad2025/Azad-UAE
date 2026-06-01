"""
Tenant branding isolation checks — alhazem vs nasrallah, no cross-tenant logo leak.

Run: python tools/qa/tenant_branding_check.py
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from decimal import Decimal

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _fail(msg: str) -> None:
    raise AssertionError(msg)


def check_resolve_branding(app) -> None:
    from utils.tenant_branding import resolve_tenant_branding

    with app.app_context():
        alh = resolve_tenant_branding(1)
        nas = resolve_tenant_branding(7)

        if "alhazem" not in (alh.get("logo_url") or ""):
            _fail(f"alhazem tenant logo missing alhazem slug: {alh.get('logo_url')}")
        if "nasrallah" not in (nas.get("logo_url") or ""):
            _fail(f"nasrallah tenant logo missing nasrallah slug: {nas.get('logo_url')}")
        if alh["logo_url"] == nas["logo_url"]:
            _fail("alhazem and nasrallah share the same logo_url")
        if "alhazem" in (nas.get("logo_url") or ""):
            _fail("nasrallah branding contains alhazem path")
        if "nasrallah" in (alh.get("logo_url") or ""):
            _fail("alhazem branding contains nasrallah path")

        if "nasrallah" not in (nas.get("favicon_url") or ""):
            _fail(f"nasrallah favicon wrong: {nas.get('favicon_url')}")

        if nas.get("company_name_en") and "nasrallah" not in nas["company_name_en"].lower():
            _fail(f"nasrallah company_name_en unexpected: {nas.get('company_name_en')}")
        if nas.get("vat_country") != "PS":
            _fail(f"nasrallah vat_country expected PS, got {nas.get('vat_country')}")


def _mock_sale(tenant_id: int):
    customer = SimpleNamespace(name="Test Customer", phone="0500000000", address="Test")
    seller = SimpleNamespace(
        full_name="Seller",
        username="seller",
        get_display_name=lambda lang="ar": "Seller",
    )
    line = SimpleNamespace(
        product=SimpleNamespace(name="Item"),
        quantity=1,
        unit_price=Decimal("100"),
        discount_percent=0,
        line_total=Decimal("100"),
    )
    return SimpleNamespace(
        tenant_id=tenant_id,
        sale_number="TST-001",
        sale_date=SimpleNamespace(strftime=lambda fmt: "2026-05-31"),
        customer=customer,
        seller=seller,
        lines=[line],
        subtotal=Decimal("100"),
        discount_amount=Decimal("0"),
        shipping_cost=Decimal("0"),
        tax_rate=Decimal("0"),
        tax_amount=Decimal("0"),
        total_amount=Decimal("100"),
        currency="AED",
        notes="",
        payments=[],
    )


def check_render_invoice_templates(app) -> None:
    from flask import render_template
    from models.invoice_settings import InvoiceSettings
    from utils.tenant_branding import get_print_header_context

    with app.app_context(), app.test_request_context("/"):
        for tid, slug, forbidden in (
            (1, "alhazem", "nasrallah"),
            (7, "nasrallah", "alhazem"),
        ):
            settings = InvoiceSettings.get_active(tid)
            branding = get_print_header_context(tid)
            sale = _mock_sale(tid)
            html = render_template(
                "invoices/modern.html",
                sale=sale,
                settings=settings,
                print_branding=branding,
                print_tenant_id=tid,
                print_branch=None,
                print_user_name="Test",
                amount_in_words="مائة",
                qr_data_url="",
            )
            if slug not in html:
                _fail(f"tenant {tid} invoice render missing {slug} logo path")
            if forbidden in html:
                _fail(f"tenant {tid} invoice render leaked {forbidden}")


def check_render_receipt_templates(app) -> None:
    from flask import render_template
    from models.invoice_settings import InvoiceSettings
    from utils.tenant_branding import get_print_header_context

    with app.app_context(), app.test_request_context("/"):
        receipt = SimpleNamespace(
            receipt_number="RCV-TST",
            receipt_date=SimpleNamespace(strftime=lambda fmt: "2026-05-31"),
            customer=SimpleNamespace(name="Customer"),
            user=SimpleNamespace(
                full_name="User",
                username="user",
                get_display_name=lambda lang="ar": "User",
            ),
            amount=Decimal("50"),
            amount_aed=Decimal("50"),
            currency="AED",
            payment_method="cash",
            cheque_number=None,
            cheque_date=None,
            bank_name=None,
            reference_number=None,
            notes="",
            allocations=[],
            get_source_info=lambda: {"type": "manual", "label": "Test"},
        )
        for tid, slug, forbidden in (
            (1, "alhazem", "nasrallah"),
            (7, "nasrallah", "alhazem"),
        ):
            settings = InvoiceSettings.get_active(tid)
            branding = get_print_header_context(tid)
            html = render_template(
                "receipts/modern.html",
                receipt=receipt,
                settings=settings,
                print_branding=branding,
                print_tenant_id=tid,
                print_branch=None,
                print_user_name="Test",
                amount_in_words="خمسون",
                qr_data_url="",
                doc_number="RCV-TST",
            )
            if slug not in html:
                _fail(f"tenant {tid} receipt render missing {slug} logo path")
            if forbidden in html:
                _fail(f"tenant {tid} receipt render leaked {forbidden}")


def run_tenant_branding_check() -> tuple[list[str], list[str]]:
    fails: list[str] = []
    warns: list[str] = []
    os.environ.setdefault("SKIP_SYSTEM_INTEGRITY", "1")
    from app import create_app

    app = create_app()
    try:
        check_resolve_branding(app)
    except AssertionError as exc:
        fails.append(str(exc))
    except Exception as exc:
        fails.append(f"resolve branding: {exc}")

    if not fails:
        try:
            check_render_invoice_templates(app)
        except AssertionError as exc:
            fails.append(str(exc))
        except Exception as exc:
            fails.append(f"invoice render: {exc}")

    if not fails:
        try:
            check_render_receipt_templates(app)
        except AssertionError as exc:
            fails.append(str(exc))
        except Exception as exc:
            fails.append(f"receipt render: {exc}")

    return fails, warns


def main() -> int:
    fails, warns = run_tenant_branding_check()
    if fails:
        sys.stderr.write("TENANT BRANDING CHECK — FAIL\n")
        for f in fails:
            sys.stderr.write(f"  FAIL: {f}\n")
        return 1
    sys.stderr.write("TENANT BRANDING CHECK — PASS\n")
    for w in warns:
        sys.stderr.write(f"  WARN: {w}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
