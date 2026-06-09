"""
Audit test: owner panel routes, templates, and permissions.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import re


def test_all_owner_routes_have_auth():
    with open('routes/owner.py', 'r', encoding='utf-8') as f:
        content = f.read()

    blocks = re.findall(
        r'(@owner_bp\.route\([^\n]+\)\n(?:@[^\n]+\n)*def [^\n]+)',
        content
    )

    no_auth = []
    for b in blocks:
        if '@login_required' not in b:
            route = re.search(r"route\('([^']+)'", b).group(1)
            no_auth.append(route)

    # Only tenant_suspend_page is intentionally public
    assert no_auth == ['/tenants/<int:tenant_id>/suspend-page']


def test_all_referenced_templates_exist():
    with open('routes/owner.py', 'r', encoding='utf-8') as f:
        content = f.read()

    templates = re.findall(r"render_template\(\s*['\"](owner/[^'\"]+)['\"]", content)
    missing = []
    for t in set(templates):
        if not os.path.exists(f'templates/{t}'):
            missing.append(t)
    assert missing == [], f"Missing templates: {missing}"


def test_no_placeholder_text_in_owner_templates():
    placeholders = ['TODO', 'FIXME', 'placeholder only', 'قريبا']
    templates_dir = 'templates/owner'
    found = []
    for root, dirs, files in os.walk(templates_dir):
        for f in files:
            if f.endswith('.html'):
                path = os.path.join(root, f)
                with open(path, 'r', encoding='utf-8') as fh:
                    content = fh.read().lower()
                for ph in placeholders:
                    if ph.lower() in content:
                        found.append(f"{path}: contains '{ph}'")
    assert found == [], f"Found placeholders: {found}"


def test_owner_templates_have_functional_elements():
    """Every owner template should have a form, table, or button."""
    templates_dir = 'templates/owner'
    empty_templates = []
    for root, dirs, files in os.walk(templates_dir):
        for f in files:
            if not f.endswith('.html') or f == 'base.html':
                continue
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8') as fh:
                content = fh.read()
            has_functional = any(tag in content for tag in ['<form ', '<table ', 'btn btn-'])
            if not has_functional:
                empty_templates.append(f)
    assert empty_templates == [], f"Templates without functional elements: {empty_templates}"
