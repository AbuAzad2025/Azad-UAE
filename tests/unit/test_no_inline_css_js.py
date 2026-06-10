import os
BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
def read_template(path):
    with open(os.path.join(BASE, path), encoding='utf-8') as f:
        return f.read()
def test_no_inline_style_in_sales_index():
    html = read_template('templates/sales/index.html')
    assert '<style>' not in html
def test_no_inline_script_in_sales_create():
    html = read_template('templates/sales/create.html')
    for line in html.splitlines():
        s = line.strip()
        if s.startswith('<script') and 'src=' not in s:
            raise AssertionError(f'Inline <script> found: {s}')
def test_no_inline_handlers_in_purchases_create():
    html = read_template('templates/purchases/create.html')
    assert 'onclick=' not in html, 'Inline onclick handler found in purchases/create.html'
    assert 'onchange=' not in html, 'Inline onchange handler found in purchases/create.html'
    assert 'oninput=' not in html, 'Inline oninput handler found in purchases/create.html'
def test_no_inline_script_in_pos_index():
    html = read_template('templates/pos/index.html')
    for line in html.splitlines():
        s = line.strip()
        if s.startswith('<script') and 'src=' not in s:
            raise AssertionError(f'Inline <script> found: {s}')
def test_pos_uses_meta_tag_for_currency():
    html = read_template('templates/pos/index.html')
    assert 'meta name="pos-base-currency"' in html, 'pos/index.html should use meta tag for base currency'
    assert 'window.POS_BASE_CURRENCY' not in html, 'window.POS_BASE_CURRENCY inline script should be removed'
def test_no_inline_style_in_landing():
    html = read_template('templates/public/landing.html')
    assert '<style>' not in html, 'Inline <style> found in landing.html'
def test_landing_external_css_files_exist():
    assert os.path.isfile(os.path.join(BASE, 'static/css/landing-page-en.css'))
    assert os.path.isfile(os.path.join(BASE, 'static/css/landing-page-ar.css'))
def test_css_files_exist():
    assert os.path.isfile(os.path.join(BASE, 'static/css/sales-index.css'))
    assert os.path.isfile(os.path.join(BASE, 'static/css/sales-create.css'))
def test_js_files_exist():
    assert os.path.isfile(os.path.join(BASE, 'static/js/sales-index.js'))
    assert os.path.isfile(os.path.join(BASE, 'static/js/sales-create.js'))
