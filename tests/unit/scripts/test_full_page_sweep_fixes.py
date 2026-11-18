"""Guard the defects found by the full-page browser sweep.

The sweep of every GET page as a tenant manager surfaced 500s (ambiguous GL
joins, Jinja ``abs()`` calls, nullable arithmetic, undefined tojson values),
broken JS (``notify()`` called as a function, jQuery used before it loaded,
missing asset) and an optional-module GL mapping that made a report impossible
to open.
"""

from __future__ import annotations

import glob
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_gl_joins_are_explicit() -> None:
    offenders = []
    for path in glob.glob(os.path.join(ROOT, "services", "*.py")) + glob.glob(os.path.join(ROOT, "models", "*.py")):
        source = open(path, encoding="utf-8", errors="ignore").read()
        if re.search(r"\.join\(GLJournalEntry\)", source):
            offenders.append(Path(path).name)
    assert not offenders, offenders


def test_jinja_templates_use_abs_filter_not_function() -> None:
    offenders = []
    for path in glob.glob(os.path.join(ROOT, "templates", "**", "*.html"), recursive=True):
        source = open(path, encoding="utf-8", errors="ignore").read()
        for match in re.finditer(r"(?<![.\w])abs\(", source):
            line = source[: match.start()].count("\n") + 1
            offenders.append(f"{Path(path).name}:{line}")
    assert not offenders, offenders


def test_ar_reconciliation_tolerates_disabled_partners_module() -> None:
    source = (ROOT / "services" / "ar_reconciliation_service.py").read_text(encoding="utf-8")
    assert "GLMappingError" in source
    assert "except GLMappingError" in source
    assert "if row[0]" in source


def test_broken_browser_assets_and_calls_are_gone() -> None:
    cheques = (ROOT / "templates" / "cheques" / "create.html").read_text(encoding="utf-8")
    assert "notify.warning(" in cheques
    assert not re.search(r"(?<![.\w])notify\(", cheques)

    out_of_stock = (ROOT / "templates" / "warehouse" / "out_of_stock.html").read_text(encoding="utf-8")
    assert "ready(() =>" in out_of_stock
    assert "ready((() =>" not in out_of_stock

    shipments = (ROOT / "templates" / "shipments" / "create.html").read_text(encoding="utf-8")
    assert "barcode-unified.js" not in shipments

    quotation = (ROOT / "templates" / "quotations" / "form.html").read_text(encoding="utf-8")
    assert "quotation-form.js" in quotation
    assert quotation.index("block extra_js") < quotation.index("quotation-form.js")


def test_store_reports_has_no_third_party_script() -> None:
    source = (ROOT / "templates" / "store" / "store_reports.html").read_text(encoding="utf-8")
    assert "cdn.jsdelivr.net" not in source
    assert "adminlte/plugins/chartjs/chart.min.js" in source
    assert 'nonce="{{ csp_nonce() }}"' in source
