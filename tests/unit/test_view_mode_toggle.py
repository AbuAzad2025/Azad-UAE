"""
Tests for view-mode toggle (desktop/mobile/auto) in navbar.
"""

def test_base_html_has_viewmode_toggle():
    """base.html contains the view-mode toggle button."""
    with open('templates/base.html', 'r', encoding='utf-8') as f:
        html = f.read()
    assert 'data-ui-action="toggle-viewmode"' in html
    assert 'erp-viewmode-toggle' in html
    assert 'viewmode-icon' in html
    assert 'viewmode-label' in html


def test_base_html_pos_uses_tenant_only():
    """POS sidebar link checks tenant_enable_pos only (per-tenant feature)."""
    with open('templates/base.html', 'r', encoding='utf-8') as f:
        html = f.read()
    assert '{% if tenant_enable_pos %}' in html
    # Should NOT require system-level master switch
    assert 'system_enable_pos and tenant_enable_pos' not in html


def test_erp_theme_has_view_mode_css():
    """erp-theme.css contains view-desktop and view-mobile classes."""
    with open('static/css/erp-theme.css', 'r', encoding='utf-8') as f:
        css = f.read()
    assert 'body.view-desktop' in css
    assert 'body.view-mobile' in css
    assert '.erp-mobile-nav' in css


def test_base_html_has_viewmode_js():
    """base.html contains the view-mode JS logic."""
    with open('templates/base.html', 'r', encoding='utf-8') as f:
        html = f.read()
    assert 'getSavedViewMode' in html
    assert 'setViewMode' in html
    assert 'azad_view_mode' in html
