import re
import os

# ── 1. Extract all routes from owner.py ──
with open('routes/owner.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find route definitions
route_pattern = re.compile(
    r"@owner_bp\.route\('([^']+)'[^\n]*\)\n"
    r"@login_required\n"
    r"@(?:owner_required|company_admin_required)\n"
    r"def ([^(]+)",
    re.MULTILINE
)

routes = []
for match in route_pattern.finditer(content):
    url = match.group(1)
    func = match.group(2).strip()
    routes.append((url, func))

print(f"Found {len(routes)} owner routes:\n")
for url, func in routes:
    print(f"  {url:50} -> {func}")

# ── 2. Extract all render_template calls ──
template_pattern = re.compile(r"render_template\(\s*['\"](owner/[^'\"]+)['\"]")
templates = template_pattern.findall(content)
unique_templates = sorted(set(templates))

print(f"\n\nFound {len(unique_templates)} unique templates referenced:\n")
for t in unique_templates:
    exists = os.path.exists(f"templates/{t}")
    status = "OK" if exists else "MISSING"
    print(f"  [{status:7}] {t}")

# ── 3. Find orphan templates (exist on disk but not referenced by routes) ──
existing_templates = []
templates_dir = "templates/owner"
if os.path.isdir(templates_dir):
    for root, dirs, files in os.walk(templates_dir):
        for f in files:
            if f.endswith('.html'):
                rel = os.path.join(root, f).replace('templates/', '')
                existing_templates.append(rel)

orphans = [t for t in existing_templates if t not in unique_templates]

print(f"\n\nOrphan templates (exist but no route uses them): {len(orphans)}")
for o in orphans:
    print(f"  {o}")

# ── 4. Missing templates (referenced by routes but not on disk) ──
missing = [t for t in unique_templates if not os.path.exists(f"templates/{t}")]
print(f"\n\nMissing templates (route references but no file): {len(missing)}")
for m in missing:
    print(f"  {m}")
