import os

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read_file(path):
    with open(os.path.join(BASE, path), encoding="utf-8") as f:
        return f.read()


def test_purchases_js_has_recalc_event_listener():
    js = read_file("static/js/purchases/create.js")
    assert "$('#recalcTotalsBtn').on('click'" in js, (
        "purchases/create.js should have recalcTotalsBtn click listener"
    )


def test_purchases_js_has_addline_event_listener():
    js = read_file("static/js/purchases/create.js")
    assert "$('#addLineBtn').on('click'" in js, (
        "purchases/create.js should have addLineBtn click listener"
    )


def test_pos_js_reads_currency_from_meta():
    js = read_file("static/js/pos/index.js")
    assert "window.POS_BASE_CURRENCY" not in js, (
        "pos/index.js should not use window.POS_BASE_CURRENCY"
    )
    assert 'meta[name="pos-base-currency"]' in js, (
        "pos/index.js should read currency from meta tag"
    )
