import os, re, difflib

# Match url_for with single or double quotes
url_pattern = re.compile(r'url_for\(["\']([^"\']+)["\'][^)]*\)')
refs = {}
for root, dirs, files in os.walk('templates'):
    for f in files:
        if f.endswith(('.html', '.jinja', '.j2')):
            path = os.path.join(root, f)
            try:
                with open(path, 'r', encoding='utf-8') as fh:
                    content = fh.read()
                matches = url_pattern.findall(content)
                for m in matches:
                    refs.setdefault(m, []).append(path)
            except Exception:
                pass

# Also scan routes/*.py for redirect(url_for(...))
py_pattern = re.compile(r'url_for\(["\']([^"\']+)["\'][^)]*\)')
for root, dirs, files in os.walk('routes'):
    for f in files:
        if f.endswith('.py'):
            path = os.path.join(root, f)
            try:
                with open(path, 'r', encoding='utf-8') as fh:
                    content = fh.read()
                matches = py_pattern.findall(content)
                for m in matches:
                    refs.setdefault(m, []).append(path)
            except Exception:
                pass

# Also scan services/*.py and models/*.py
for scan_dir in ['services', 'models', 'utils']:
    for root, dirs, files in os.walk(scan_dir):
        for f in files:
            if f.endswith('.py'):
                path = os.path.join(root, f)
                try:
                    with open(path, 'r', encoding='utf-8') as fh:
                        content = fh.read()
                    matches = py_pattern.findall(content)
                    for m in matches:
                        refs.setdefault(m, []).append(path)
                except Exception:
                    pass

from app import create_app
app = create_app()
with app.app_context():
    endpoints = {r.endpoint for r in app.url_map.iter_rules()}

broken = {}
for ep, paths in refs.items():
    if ep not in endpoints:
        broken[ep] = paths

for ep in sorted(broken.keys()):
    close = difflib.get_close_matches(ep, endpoints, n=3, cutoff=0.5)
    print(f"BROKEN: {ep}")
    for f in broken[ep]:
        print(f"  in: {f}")
    if close:
        print(f"  suggestions: {close}")
    print()

print(f"Total broken: {len(broken)}")
