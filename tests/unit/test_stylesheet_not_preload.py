import pytest


def test_no_preload_css_in_head():
    with open('templates/partials/head.html', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'rel="preload"' not in content


def test_stylesheet_links():
    with open('templates/partials/head.html', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'rel="stylesheet"' in content
