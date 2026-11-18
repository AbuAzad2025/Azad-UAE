"""Guard the browser-discovered POS script-scope defects.

``partials/scripts.html`` is included on every page. A broad
``'pos' in request.endpoint`` condition also loaded the POS register module on
``pos.order_type_settings`` and ``pos.printer_settings``, where ``index.js``
threw on a missing ``#cartBody`` and aborted before attaching any handlers.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PARTIAL = ROOT / "templates" / "partials" / "scripts.html"
CASHIER_LOGIC = ROOT / "static" / "js" / "pos" / "cashier-logic.js"


def test_pos_bundle_is_loaded_only_on_the_pos_register() -> None:
    source = PARTIAL.read_text(encoding="utf-8")
    pos_block = source.split("<!-- POS Module", 1)[1].split("{% endif %}", 1)[0]
    assert "request.endpoint == 'pos.index'" in pos_block
    assert "'pos' in request.endpoint" not in pos_block


def test_cashier_logic_exports_are_browser_safe() -> None:
    source = CASHIER_LOGIC.read_text(encoding="utf-8")
    assert 'typeof module !== "undefined"' in source
    assert "window.PosCashierLogic" in source
    guard = source.index('typeof module !== "undefined"')
    export = source.index("module.exports = {")
    assert guard < export


def test_seed_provides_default_pos_order_types() -> None:
    source = (ROOT / "scripts" / "ops" / "seed_clean_isolation_db.py").read_text(encoding="utf-8")
    assert "DEFAULT_POS_ORDER_TYPES" in source
    assert '"pos_order_types"' in source
