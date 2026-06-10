import os
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'templates', 'partials')
def test_datatables_not_in_scripts():
    path = os.path.join(TEMPLATES_DIR, 'scripts.html')
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'datatables' not in content
def test_select2_not_in_scripts():
    path = os.path.join(TEMPLATES_DIR, 'scripts.html')
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'select2' not in content
def test_datatables_partial_exists():
    path = os.path.join(TEMPLATES_DIR, 'datatables_assets.html')
    assert os.path.exists(path)
def test_select2_partial_exists():
    path = os.path.join(TEMPLATES_DIR, 'select2_assets.html')
    assert os.path.exists(path)
