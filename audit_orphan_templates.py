"""
Audit for orphaned templates.
Fix: handle filenames with dots (like dashboard.html) correctly.
"""

import os, re, sys, json
from collections import defaultdict

OUT = open('orphan_template_report.txt', 'w', encoding='utf-8')

def log(*args):
    text = ' '.join(str(a) for a in args)
    print(text, file=OUT)
    print(text)

def _normalize_template_name(tmpl):
    """
    Convert render_template argument to possible file paths.
    Handles: 'owner/dashboard', 'owner.dashboard', 'dashboard.html', 'dashboard'
    """
    candidates = []
    # Original
    candidates.append(tmpl)
    candidates.append('templates/' + tmpl)
    # With .html extension
    if not tmpl.endswith('.html'):
        candidates.append(tmpl + '.html')
        candidates.append('templates/' + tmpl + '.html')
    # If no slash but has dot, it might be module.path (e.g. owner.dashboard)
    # OR it might be a filename with extension (e.g. dashboard.html)
    # We handle both by also trying replace('.' ,'/') only if there's no extension
    if '/' not in tmpl:
        base, _, ext = tmpl.rpartition('.')
        if base and not ext:  # like 'owner.dashboard' (no real extension)
            mod_path = tmpl.replace('.', '/')
            candidates.append(mod_path)
            candidates.append(mod_path + '.html')
            candidates.append('templates/' + mod_path)
            candidates.append('templates/' + mod_path + '.html')
    return candidates

# 1. List all template files
template_files = set()
for root, dirs, files in os.walk('templates'):
    for f in files:
        if f.endswith(('.html', '.jinja', '.j2')):
            rel = os.path.join(root, f).replace('\\', '/')
            template_files.add(rel)

template_ids = {}
for t in template_files:
    template_ids[t] = True
    short = t[len('templates/'):]
    template_ids[short] = True
    no_ext = short.rsplit('.', 1)[0]
    template_ids[no_ext] = True

# 2. Scan Python code for render_template
render_pattern = re.compile(r'render_template\s*\(\s*["\']([^"\']+)["\']')
python_refs = defaultdict(list)
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
                    python_refs[tmpl].append(f'{path}:{line}')
            except Exception:
                pass

# 3. Scan templates for include/extends
include_pattern = re.compile(r"{%\s*(include|extends)\s+['\"]([^'\"]+)['\"]\s*%}")
template_refs = defaultdict(list)
for t in template_files:
    try:
        with open(t, 'r', encoding='utf-8') as fh:
            content = fh.read()
        for m in include_pattern.finditer(content):
            action = m.group(1)
            ref = m.group(2)
            line = content[:m.start()].count('\n') + 1
            template_refs[ref].append(f'{t}:{line} ({action})')
    except Exception:
        pass

# 4. Cross-reference
always_used = {
    'partials/head.html',
    'partials/navbar.html',
    'partials/sidebar.html',
    'partials/footer.html',
    'partials/flash_messages.html',
    'partials/scripts.html',
    'partials/styles.html',
    'errors/403.html',
    'errors/404.html',
    'errors/500.html',
    'base.html',
}

used_templates = set()

for tmpl in python_refs:
    for c in _normalize_template_name(tmpl):
        c = c.replace('\\', '/')
        if c in template_ids:
            used_templates.add(c)

for ref in template_refs:
    candidates = [ref, ref.replace('\\', '/')]
    for c in candidates:
        if c in template_ids:
            used_templates.add(c)
        with_prefix = 'templates/' + c
        if with_prefix in template_ids:
            used_templates.add(with_prefix)

for au in always_used:
    candidates = [au, 'templates/' + au]
    for c in candidates:
        if c in template_ids:
            used_templates.add(c)

orphans = [t for t in template_files if t not in used_templates]

# 5. Report
log('=' * 70)
log('AZADEXA ORPHANED TEMPLATE AUDIT')
log('=' * 70)
log('')
log(f'Total template files: {len(template_files)}')
log(f'Referenced by render_template: {len(set(python_refs.keys()))}')
log(f'Referenced by include/extends: {len(template_refs)}')
log(f'Always-used partials: {len(always_used)}')
log(f'Total used: {len(used_templates)}')
log(f'Orphaned templates: {len(orphans)}')

orphan_by_dir = defaultdict(list)
for o in sorted(orphans):
    parts = o.split('/')
    dir_name = parts[1] if len(parts) > 1 else '_root'
    orphan_by_dir[dir_name].append(o)

if orphans:
    log('')
    log('=' * 70)
    log('ORPHANED TEMPLATES (by directory)')
    log('=' * 70)
    for d in sorted(orphan_by_dir.keys()):
        log(f'')
        log(f'[{d}/] ({len(orphan_by_dir[d])} file(s))')
        for f in sorted(orphan_by_dir[d]):
            log(f'   . {f}')

    log('')
    log('=' * 70)
    log('ANALYSIS: Likely Dead vs Potentially Dynamic')
    log('=' * 70)
    dead = []
    dynamic = []
    for o in sorted(orphans):
        name = os.path.basename(o).lower()
        if any(k in name for k in ('email', 'pdf', 'print', 'export', 'report', 'invoice', 'receipt', 'statement')):
            dynamic.append((o, 'Likely rendered dynamically with suffix'))
        elif 'partials/' in o:
            dynamic.append((o, 'Partial, might be included dynamically'))
        else:
            dead.append(o)

    if dead:
        log(f'')
        log(f'WARNING: Likely DEAD (no evidence of use): {len(dead)}')
        for d in dead[:30]:
            log(f'   {d}')
        if len(dead) > 30:
            log(f'   ... and {len(dead) - 30} more')

    if dynamic:
        log(f'')
        log(f'OK: Potentially DYNAMIC (rendered with variable or as email/print template): {len(dynamic)}')
        for d, reason in dynamic[:30]:
            log(f'   {d}  [{reason}]')
        if len(dynamic) > 30:
            log(f'   ... and {len(dynamic) - 30} more')
else:
    log('')
    log('OK - All templates are referenced somewhere.')

log('')
log('=' * 70)
log('TEMPLATES REFERENCED IN CODE BUT MISSING ON DISK')
log('=' * 70)
missing = []
for tmpl in sorted(python_refs.keys()):
    candidates = _normalize_template_name(tmpl)
    found = False
    for c in candidates:
        c = c.replace('\\', '/')
        if c in template_ids:
            found = True
            break
    if not found:
        missing.append(tmpl)

if missing:
    log(f'')
    log(f'Count: {len(missing)}')
    for m in missing:
        locs = python_refs.get(m, [])
        loc_str = locs[0] if locs else 'unknown location'
        # Skip flask internal references
        if '.venv/' in loc_str or 'site-packages/' in loc_str:
            continue
        log(f'  X {m}  -> {loc_str}')
else:
    log('')
    log('OK - All render_template references point to existing files.')

log('')
log('=' * 70)

report = {
    'meta': {
        'total_templates': len(template_files),
        'total_used': len(used_templates),
        'orphan_count': len(orphans),
        'dead_count': len(dead) if orphans else 0,
        'dynamic_count': len(dynamic) if orphans else 0,
        'missing_count': len(missing),
    },
    'orphans': sorted(orphans),
    'orphans_by_directory': {k: sorted(v) for k, v in sorted(orphan_by_dir.items())},
    'dead': sorted(dead) if orphans else [],
    'dynamic': [{'file': f, 'reason': r} for f, r in dynamic] if orphans else [],
    'missing_references': [{'template': m, 'locations': python_refs.get(m, [])} for m in missing],
}

with open('orphan_template_report.json', 'w', encoding='utf-8') as fh:
    json.dump(report, fh, indent=2, ensure_ascii=False)
log('Full JSON report: orphan_template_report.json')
OUT.close()
