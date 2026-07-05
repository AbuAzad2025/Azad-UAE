"""
Post-move audit: check for any broken references after template moves.
Also deep-dive into POS blueprint.
"""

import os, re, json
from collections import defaultdict

OUT = open('audit_pos_and_post_move.txt', 'w', encoding='utf-8')

def log(*args):
    text = ' '.join(str(a) for a in args)
    print(text, file=OUT)
    print(text)

# 1. Check all render_template still point to existing files
log("=" * 70)
log("POST-MOVE TEMPLATE REFERENCE INTEGRITY CHECK")
log("=" * 70)

render_pattern = re.compile(r'render_template\s*\(\s*["\']([^"\']+)["\']')
missing_templates = []

for scan_dir in ('routes', 'services', 'utils', 'models', '.'):
    if not os.path.isdir(scan_dir) and scan_dir != '.':
        continue
    for root, dirs, files in os.walk(scan_dir):
        for f in files:
            if not f.endswith('.py'):
                continue
            path = os.path.join(root, f).replace('\\', '/')
            try:
                with open(path, 'r', encoding='utf-8') as fh:
                    content = fh.read()
                for m in render_pattern.finditer(content):
                    tmpl = m.group(1)
                    line = content[:m.start()].count('\n') + 1
                    # Check if template exists
                    candidates = [
                        tmpl,
                        tmpl + '.html',
                        'templates/' + tmpl,
                        'templates/' + tmpl + '.html',
                    ]
                    # Handle dotted paths
                    if '/' not in tmpl and '.' in tmpl:
                        mod_path = tmpl.replace('.', '/')
                        candidates.extend([
                            mod_path,
                            mod_path + '.html',
                            'templates/' + mod_path,
                            'templates/' + mod_path + '.html',
                        ])
                    found = False
                    for c in candidates:
                        c = c.replace('\\', '/')
                        if os.path.exists(c):
                            found = True
                            break
                    if not found:
                        missing_templates.append((tmpl, f'{path}:{line}'))
            except Exception:
                pass

if missing_templates:
    log(f"\nBROKEN: {len(missing_templates)} render_template references point to missing files:")
    for tmpl, loc in sorted(missing_templates):
        log(f"  X {tmpl}  -> {loc}")
else:
    log("\nOK - All render_template references point to existing files.")

# 2. POS deep-dive
log("\n" + "=" * 70)
log("POS BLUEPRINT DEEP AUDIT")
log("=" * 70)

from app import create_app
app = create_app()
with app.app_context():
    endpoints = {r.endpoint for r in app.url_map.iter_rules()}
    pos_endpoints = sorted([e for e in endpoints if e.startswith('pos.')])

log(f"\nRegistered POS endpoints: {len(pos_endpoints)}")
for ep in pos_endpoints:
    log(f"  . {ep}")

# Check POS templates
pos_templates = []
for root, dirs, files in os.walk('templates/pos'):
    for f in files:
        if f.endswith('.html'):
            pos_templates.append(os.path.join(root, f).replace('\\', '/'))

log(f"\nPOS templates: {len(pos_templates)}")
for t in sorted(pos_templates):
    log(f"  . {t}")

# Check static JS for POS
pos_js = []
js_dir = 'static/js/pos'
if os.path.isdir(js_dir):
    for f in os.listdir(js_dir):
        if f.endswith('.js'):
            pos_js.append(f)

log(f"\nPOS JS files: {len(pos_js)}")
for j in sorted(pos_js):
    log(f"  . {j}")

# Check POS template url_for
log("\nPOS template url_for references:")
url_pattern = re.compile(r"url_for\([\"\']([^\"\']+)[\"\'][^)]*\)")
for t in sorted(pos_templates):
    try:
        with open(t, 'r', encoding='utf-8') as fh:
            content = fh.read()
        matches = url_pattern.findall(content)
        if matches:
            log(f"  {t}:")
            for m in matches:
                status = "OK" if m in endpoints else "X BROKEN"
                log(f"    [{status}] {m}")
    except Exception:
        pass

# Check POS JS API calls against routes
log("\nPOS JS API calls vs registered routes:")
api_pattern = re.compile(r"['\"](/pos/api/[^'\"]+)['\"]")
js_api_calls = set()
for js_file in pos_js:
    path = os.path.join(js_dir, js_file).replace('\\', '/')
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            content = fh.read()
        for m in api_pattern.finditer(content):
            route = m.group(1)
            js_api_calls.add(route)
    except Exception:
        pass

# Map JS API paths to endpoint names (rough)
for call in sorted(js_api_calls):
    # Check if any route rule matches this path pattern
    matched = False
    with app.app_context():
        for rule in app.url_map.iter_rules():
            if rule.endpoint.startswith('pos.'):
                rule_str = str(rule)
                # Very rough match
                base_call = call.split('?')[0].rstrip('/')
                base_rule = rule_str.rstrip('/')
                if base_call == base_rule or base_call.replace('<int:', '').replace('>', '') in base_rule:
                    matched = True
                    break
    status = "OK" if matched else "X MAYBE BROKEN"
    log(f"  [{status}] {call}")

# 3. Check for url_for in templates that reference moved templates
log("\n" + "=" * 70)
log("CHECKING FOR REFERENCES TO MOVED TEMPLATES")
log("=" * 70)

moved = [
    'offline.html',
    'payments/create.html',
    'payments/create_payment.html',
    'payments/index.html',
    'payments/print.html',
    'payments/print_payment.html',
    'public/demo.html',
    'sales/print.html',
]

# These would appear as render_template or url_for or redirect
for scan_dir in ('routes', 'templates'):
    if not os.path.isdir(scan_dir):
        continue
    for root, dirs, files in os.walk(scan_dir):
        for f in files:
            if f.endswith(('.py', '.html')):
                path = os.path.join(root, f).replace('\\', '/')
                try:
                    with open(path, 'r', encoding='utf-8') as fh:
                        content = fh.read()
                    for m in moved:
                        # Look for the exact template path as a string literal
                        patterns = [
                            f"'{m}'",
                            f'"{m}"',
                            f"'templates/{m}'",
                            f'"templates/{m}"',
                        ]
                        for p in patterns:
                            if p in content:
                                log(f"  WARNING: {path} still references moved template {m}")
                                break
                except Exception:
                    pass

log("\n" + "=" * 70)
log("DONE")
log("=" * 70)
OUT.close()
