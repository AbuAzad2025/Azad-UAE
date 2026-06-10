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
def test_css_files_exist():
    assert os.path.isfile(os.path.join(BASE, 'static/css/sales-index.css'))
    assert os.path.isfile(os.path.join(BASE, 'static/css/sales-create.css'))
def test_js_files_exist():
    assert os.path.isfile(os.path.join(BASE, 'static/js/sales-index.js'))
    assert os.path.isfile(os.path.join(BASE, 'static/js/sales-create.js'))
