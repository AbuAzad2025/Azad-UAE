import os
BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
def read_template(path):
    with open(os.path.join(BASE, path), encoding='utf-8') as f:
        return f.read()
def test_no_inline_style_in_purchases_create():
    html = read_template('templates/purchases/create.html')
    assert '<style>' not in html
def test_no_inline_script_in_purchases_create():
    html = read_template('templates/purchases/create.html')
    for line in html.splitlines():
        s = line.strip()
        if s.startswith('<script') and 'src=' not in s:
            raise AssertionError(f'Inline <script> found: {s}')
def test_purchases_css_exists():
    assert os.path.isfile(os.path.join(BASE, 'static/css/purchases.css'))
def test_purchases_js_exists():
    assert os.path.isfile(os.path.join(BASE, 'static/js/purchases/create.js'))
def test_no_debug_totals():
    html = read_template('templates/purchases/create.html')
    assert 'debugTotals' not in html
def test_no_force_calculate():
    html = read_template('templates/purchases/create.html')
    assert 'forceCalculate' not in html
