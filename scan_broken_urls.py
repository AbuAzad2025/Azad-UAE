import os, re, difflib

# 1. Extract all url_for from templates
url_pattern = re.compile(r"url_for\('([^']+)'[^)]*\)")
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

# 2. Get actual endpoints
from app import create_app
app = create_app()
with app.app_context():
    endpoints = {r.endpoint for r in app.url_map.iter_rules()}

# 3. Find broken
broken = {}
for ep, paths in refs.items():
    if ep not in endpoints:
        broken[ep] = paths

# 4. Try to find close matches
for ep in sorted(broken.keys()):
    close = difflib.get_close_matches(ep, endpoints, n=3, cutoff=0.5)
    print(f"BROKEN: {ep}")
    for f in broken[ep]:
        print(f"  in: {f}")
    if close:
        print(f"  suggestions: {close}")
    print()

print(f"Total broken: {len(broken)}")
