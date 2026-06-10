"""Tests for self-hosted Tajawal font (zero Google Fonts dependency)."""
import os


def test_tajawal_font_files_exist():
    font_dir = 'static/fonts/tajawal'
    for w in ['regular', 'medium', 'bold']:
        assert os.path.exists(f'{font_dir}/tajawal-{w}.woff2'), f'Missing tajawal-{w}.woff2'


def test_tajawal_css_declares_fontface():
    with open('static/fonts/tajawal/tajawal.css', 'r', encoding='utf-8') as f:
        css = f.read()
    assert "font-family: 'Tajawal'" in css
    assert 'format(' in css


def test_base_html_uses_local_font():
    with open('templates/partials/head.html', 'r', encoding='utf-8') as f:
        html = f.read()
    assert "fonts/tajawal/tajawal.css" in html
    assert 'fonts.googleapis.com/css2?family=Tajawal' not in html
