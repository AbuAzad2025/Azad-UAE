import os

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


def _read(path):
    with open(os.path.join(BASE_DIR, path), 'r', encoding='utf-8') as f:
        return f.read()


def test_base_html_under_300_lines():
    content = _read('templates/base.html')
    lines = content.splitlines()
    assert len(lines) < 300, f'base.html has {len(lines)} lines, expected < 300'


def test_includes_navbar():
    content = _read('templates/base.html')
    assert "{% include 'partials/navbar.html' %}" in content


def test_includes_sidebar():
    content = _read('templates/base.html')
    assert "{% include 'partials/sidebar.html' %}" in content


def test_includes_scripts():
    content = _read('templates/base.html')
    assert "{% include 'partials/scripts.html' %}" in content


def test_content_block_preserved():
    content = _read('templates/base.html')
    assert '{% block content %}' in content


def test_extra_js_block_preserved():
    content = _read('templates/base.html')
    assert '{% block extra_js %}' in content


def test_base_helpers_js_exists():
    assert os.path.isfile(os.path.join(BASE_DIR, 'static', 'js', 'base-helpers.js'))
