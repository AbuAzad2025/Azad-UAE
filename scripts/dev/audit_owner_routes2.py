import re
import os
import codecs

with open('routes/owner.py', 'r', encoding='utf-8') as f:
    content = f.read()

route_pattern = re.compile(
    r"@owner_bp\.route\('([^']+)'[^\n]*\)\n"
    r"@login_required\n"
    r"@(?:owner_required|company_admin_required)\n"
    r"def ([^(]+)",
    re.MULTILINE
)

routes = [(m.group(1), m.group(2).strip()) for m in route_pattern.finditer(content)]

template_pattern = re.compile(r"render_template\(\s*['\"](owner/[^'\"]+)['\"]")
templates = template_pattern.findall(content)
unique_templates = sorted(set(templates))

existing_templates = []
templates_dir = "templates/owner"
if os.path.isdir(templates_dir):
    for root, dirs, files in os.walk(templates_dir):
        for f in files:
            if f.endswith('.html'):
                rel = os.path.join(root, f).replace('templates/', '').replace('\\', '/')
                existing_templates.append(rel)

orphans = [t for t in existing_templates if t not in unique_templates]
missing = [t for t in unique_templates if not os.path.exists(f"templates/{t}")]

with codecs.open('scripts/maintenance/audit_result.txt', 'w', 'utf-8') as out:
    out.write(f"ROUTES: {len(routes)}\n")
    for url, func in routes:
        out.write(f"  {url:50} -> {func}\n")

    out.write(f"\nREFERENCED_TEMPLATES: {len(unique_templates)}\n")
    for t in unique_templates:
        exists = os.path.exists(f"templates/{t}")
        out.write(f"  [{'OK' if exists else 'MISSING':7}] {t}\n")

    out.write(f"\nORPHANS: {len(orphans)}\n")
    for o in orphans:
        out.write(f"  {o}\n")

    out.write(f"\nMISSING: {len(missing)}\n")
    for m in missing:
        out.write(f"  {m}\n")

print("Done. See scripts/maintenance/audit_result.txt")
