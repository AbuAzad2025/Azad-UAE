"""Guard the shared-partial script loading and empty-table templates.

Browser sweep found three recurring defects: module scripts gated on a broad
``'module' in request.endpoint`` loaded on settings/print pages that had no DOM
for them; the same script was loaded twice by both the partial and the page
template (duplicate top-level ``const`` threw); and an empty-state
``<td colspan="N">`` row inside a DataTables tbody threw ``_DT_CellIndex``.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TEMPLATES = ROOT / "templates"
PARTIAL = TEMPLATES / "partials" / "scripts.html"


def test_no_broad_endpoint_match_for_module_scripts() -> None:
    source = PARTIAL.read_text(encoding="utf-8")
    assert "'pos' in request.endpoint" not in source
    assert "'sales' in request.endpoint" not in source
    assert "'purchases' in request.endpoint" not in source
    assert "'products' in request.endpoint" not in source
    assert "'crm' in request.endpoint" not in source
    assert "'projects' in request.endpoint" not in source
    assert "'shop' in request.endpoint" not in source


def test_no_duplicate_dist_script_between_partial_and_page_templates() -> None:
    # Each of these page templates used to load a script that the shared
    # partial already loads for that exact endpoint, so a top-level `const`
    # was declared twice and threw a SyntaxError in the browser.
    fixed = {
        "sales/index.html": "js/sales-index.js",
        "purchases/create.html": "js/purchases/create.js",
        "crm/pipeline.html": "js/crm/pipeline.js",
        "products/create.html": "js/products/category-controls.js",
        "products/edit.html": "js/products/industry-fields.js",
        "products/categories.html": "js/products/category-controls.js",
        "pos/index.html": "js/pos/pos-config.js",
        "partials/print_handlers.html": "js/print-handlers.js",
    }
    offenders = []
    for rel, src in fixed.items():
        source = (TEMPLATES / rel).read_text(encoding="utf-8", errors="ignore")
        if re.search(r'<script[^>]*src="\{\{ dist_url\(\'' + re.escape(src), source):
            offenders.append(f"{rel}: {src}")
    assert not offenders, offenders


def test_no_colspan_empty_row_inside_tbody_for_direct_datatable_pages() -> None:
    # These templates initialise DataTables directly from an inline script.
    templates = [
        "purchases/index.html",
        "customers/index.html",
        "suppliers/index.html",
        "expenses/index.html",
        "expenses/archived.html",
        "products/index.html",
        "crm/leads_list.html",
        "dashboard.html",
        "hr/attendance.html",
        "hr/leave_list.html",
        "marketing/campaign_list.html",
    ]
    offenders: list[str] = []
    for rel in templates:
        source = (TEMPLATES / rel).read_text(encoding="utf-8", errors="ignore")
        bodies = re.findall(r"<tbody>(.*?)</tbody>", source, re.S)
        for body in bodies:
            for row in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
                if re.search(r"<td[^>]*colspan=", row):
                    offenders.append(rel)
                    break
    assert not offenders, offenders


def test_simple_pagination_matches_the_shared_pager_api() -> None:
    source = (ROOT / "routes" / "products.py").read_text(encoding="utf-8")
    assert "def iter_pages(" in source
    assert "left_edge" in source and "right_edge" in source


def test_nullable_min_stock_alert_is_guarded_in_templates() -> None:
    for rel in ("products/index.html", "warehouse/view_warehouse.html"):
        source = (TEMPLATES / rel).read_text(encoding="utf-8", errors="ignore")
        assert "min_stock_alert or 0" in source
