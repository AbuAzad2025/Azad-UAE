"""
Audit all suspicious / orphaned endpoints flagged in the URL audit report.
For each orphaned endpoint, determine:
1. Is it truly orphaned (no url_for, no redirect, no include)?
2. What does the route do?
3. Does it render a template? Is the template orphaned too?
4. Is it a legitimate API-only endpoint or a missing UI link?
5. Are there any conflicts with existing endpoints?
"""

import os, re, json
from collections import defaultdict

OUT = open('audit_suspicious_report.txt', 'w', encoding='utf-8')

def log(*args):
    text = ' '.join(str(a) for a in args)
    print(text, file=OUT)
    print(text)

# ── 1. Extract all url_for refs ──
url_pattern = re.compile(r"url_for\([\"\']([^\"\']+)[\"\'][^)]*\)")
url_refs = set()
for root, dirs, files in os.walk('templates'):
    for f in files:
        if f.endswith('.html'):
            path = os.path.join(root, f).replace('\\', '/')
            try:
                with open(path, 'r', encoding='utf-8') as fh:
                    content = fh.read()
                url_refs.update(url_pattern.findall(content))
            except Exception:
                pass

for scan_dir in ('routes', 'services', 'utils', 'models', '.'):
    if not os.path.isdir(scan_dir) and scan_dir != '.':
        continue
    for root, dirs, files in os.walk(scan_dir):
        for f in files:
            if f.endswith('.py'):
                path = os.path.join(root, f).replace('\\', '/')
                try:
                    with open(path, 'r', encoding='utf-8') as fh:
                        content = fh.read()
                    url_refs.update(url_pattern.findall(content))
                except Exception:
                    pass

# ── 2. Get endpoints ──
from app import create_app
app = create_app()
with app.app_context():
    endpoints = {r.endpoint for r in app.url_map.iter_rules()}

orphaned = endpoints - url_refs - {'static'}

# ── 3. For each suspicious blueprint, analyze orphans ──
SUSPICIOUS_BPS = {
    'owner': 'Owner panel - should have UI links',
    'payments': 'Payment management - potential missing nav links',
    'printing': 'Print actions - some may need UI links',
    'reports': 'Reports dashboard - potential missing nav links',
    'products': 'Product CRUD - delete/adjust/print may need links',
    'customers': 'Customer CRUD - delete/balance/sales may need links',
    'suppliers': 'Supplier CRUD - delete may need links',
    'sales': 'Sale CRUD - archive/restore/delete may need links',
    'purchases': 'Purchase CRUD - delete may need links',
    'expenses': 'Expense CRUD - archive/cancel/restore may need links',
    'cheques': 'Cheque management - archived/delete may need links',
    'warehouse': 'Warehouse management - delete/add_stock may need links',
    'users': 'User management - delete may need links',
    'branches': 'Branch management - delete may need links',
    'returns': 'Returns - api_create_return may need link',
    'main': 'Main routes - potential landing page issues',
}

# Extract route info from Python files
route_pattern = re.compile(
    r"@(\w+)_bp\.route\(['\"]([^'\"]+)['\"](?:,\s*methods=\[([^\]]+)\])?\]" +
    r".*?def\s+(\w+)\s*\(",
    re.DOTALL
)

# Better pattern: find route decorator + function def
route_func_pattern = re.compile(
    r"@(\w+)_bp\.route\(['\"]([^'\"]+)['\"](?:,\s*methods=\[([^\]]+)\])?\]" +
    r"(?:\s*@\w+\([^)]*\))*" +
    r"\s*def\s+(\w+)\s*\(",
    re.DOTALL
)

route_info = {}
for bp_name in SUSPICIOUS_BPS:
    route_file = f'routes/{bp_name}.py'
    if not os.path.exists(route_file):
        continue
    try:
        with open(route_file, 'r', encoding='utf-8') as fh:
            content = fh.read()
        # Find all route decorators and their function names
        for match in re.finditer(r"@(\w+)_bp\.route\(['\"]([^'\"]+)['\"](?:,\s*methods=\[([^\]]+)\])?\]", content):
            bp = match.group(1)
            path = match.group(2)
            methods = match.group(3) or 'GET'
            # Find the function name that follows
            pos = match.end()
            func_match = re.search(r"\s*def\s+(\w+)\s*\(", content[pos:pos+500])
            if func_match:
                func_name = func_match.group(1)
                endpoint = f"{bp}.{func_name}"
                route_info[endpoint] = {
                    'path': path,
                    'methods': methods,
                    'file': route_file,
                }
    except Exception:
        pass

# Check what template each route renders
render_pattern = re.compile(r'render_template\s*\(\s*["\']([^"\']+)["\']')
endpoint_template = {}
for bp_name in SUSPICIOUS_BPS:
    route_file = f'routes/{bp_name}.py'
    if not os.path.exists(route_file):
        continue
    try:
        with open(route_file, 'r', encoding='utf-8') as fh:
            content = fh.read()
        # Find each function and its render_template call
        for match in re.finditer(r"def\s+(\w+)\s*\([^)]*\):", content):
            func_name = match.group(1)
            endpoint = f"{bp_name}.{func_name}"
            pos = match.end()
            # Look for render_template in the next 1000 chars
            chunk = content[pos:pos+2000]
            render_match = render_pattern.search(chunk)
            if render_match:
                endpoint_template[endpoint] = render_match.group(1)
    except Exception:
        pass

# Check if templates exist on disk
def template_exists(tmpl):
    if not tmpl:
        return False
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
    for c in candidates:
        if os.path.exists(c.replace('\\', '/')):
            return True
    return False

# ── 4. Generate report ──
log("=" * 70)
log("SUSPICIOUS / ORPHANED ENDPOINT DEEP AUDIT")
log("=" * 70)

for bp, desc in SUSPICIOUS_BPS.items():
    bp_orphans = sorted([e for e in orphaned if e.startswith(bp + '.')])
    if not bp_orphans:
        continue
    
    log("")
    log("-" * 70)
    log(f"BLUEPRINT: {bp} ({len(bp_orphans)} orphaned)")
    log(f"  Context: {desc}")
    log("-" * 70)
    
    for ep in bp_orphans:
        info = route_info.get(ep, {})
        path = info.get('path', 'unknown')
        methods = info.get('methods', 'GET')
        tmpl = endpoint_template.get(ep)
        tmpl_exists = template_exists(tmpl) if tmpl else False
        
        # Classify
        func_name = ep.split('.')[1]
        if func_name.startswith('api_') or ep.startswith('api_'):
            category = "API-only (internal)"
        elif func_name in ('delete', 'archive', 'restore', 'cancel'):
            category = "CRUD lifecycle action"
        elif func_name in ('create', 'edit', 'update', 'index', 'list', 'view', 'detail', 'dashboard', 'settings', 'config'):
            category = "Primary UI route - SHOULD BE LINKED"
        else:
            category = "Secondary/utility"
        
        log(f"  . {ep}")
        log(f"    Route: {methods} {path}")
        if tmpl:
            log(f"    Template: {tmpl} {'(exists)' if tmpl_exists else '(MISSING)'}")
        else:
            log(f"    Template: None (JSON/API response)")
        log(f"    Category: {category}")

# Summary: Count by category
log("")
log("=" * 70)
log("SUMMARY: Orphaned endpoints by risk category")
log("=" * 70)

primary_ui = []
crud_actions = []
api_only = []
secondary = []

for ep in orphaned:
    func_name = ep.split('.')[1] if '.' in ep else ep
    bp = ep.split('.')[0] if '.' in ep else ''
    if bp not in SUSPICIOUS_BPS:
        continue
    if func_name.startswith('api_') or bp in ('api', 'api_analytics', 'api_docs', 'api_enhanced', 'advanced_ledger', 'admin_ledger'):
        api_only.append(ep)
    elif func_name in ('delete', 'archive', 'restore', 'cancel'):
        crud_actions.append(ep)
    elif func_name in ('create', 'edit', 'update', 'index', 'list', 'view', 'detail', 'dashboard', 'settings', 'config'):
        primary_ui.append(ep)
    else:
        secondary.append(ep)

log(f"")
log(f"CRITICAL - Primary UI routes with NO nav link ({len(primary_ui)}):")
for ep in sorted(primary_ui):
    log(f"  !! {ep}")

log(f"")
log(f"MEDIUM - CRUD lifecycle actions with NO nav link ({len(crud_actions)}):")
for ep in sorted(crud_actions):
    log(f"  ~ {ep}")

log(f"")
log(f"LOW - Secondary/utility endpoints ({len(secondary)}):")
for ep in sorted(secondary):
    log(f"  . {ep}")

log(f"")
log(f"SAFE - API-only endpoints (internal/JS consumed) ({len(api_only)}):")
for ep in sorted(api_only)[:20]:
    log(f"  . {ep}")
if len(api_only) > 20:
    log(f"  ... and {len(api_only)-20} more")

log("")
log("=" * 70)
log("RECOMMENDATIONS")
log("=" * 70)

if primary_ui:
    log("")
    log("1. PRIMARY UI ROUTES - Add sidebar/navbar links for:")
    for ep in sorted(primary_ui):
        bp, func = ep.split('.')
        log(f"   {ep} → add to sidebar under {bp} section")

if crud_actions:
    log("")
    log("2. CRUD ACTIONS - Verify these are accessible via buttons/forms (not dead links):")
    for ep in sorted(crud_actions):
        bp, func = ep.split('.')
        log(f"   {ep} → check if referenced by form action or JS fetch")

log("")
log("3. TEMPLATE ORPHANS - Check if routes render templates that don't exist:")
missing_templates = []
for ep, tmpl in endpoint_template.items():
    bp = ep.split('.')[0]
    if bp in SUSPICIOUS_BPS and not template_exists(tmpl):
        missing_templates.append((ep, tmpl))

if missing_templates:
    for ep, tmpl in sorted(missing_templates):
        log(f"   {ep} renders missing template: {tmpl}")
else:
    log("   None found - all rendered templates exist.")

log("")
log("=" * 70)
OUT.close()

print("\nReport saved to: audit_suspicious_report.txt")
