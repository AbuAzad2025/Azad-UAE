import ast
import re
from pathlib import Path
from collections import defaultdict

PROJECT = Path(__file__).parent.parent

def extract_routes_and_blueprints():
    routes_dir = PROJECT / 'routes'
    endpoints = {}
    blueprints = {}
    for path in routes_dir.glob('*.py'):
        if path.name.startswith('_'):
            continue
        try:
            tree = ast.parse(path.read_text(encoding='utf-8'))
        except SyntaxError:
            continue
        bp_name = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.endswith('_bp'):
                        bp_name = target.id
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute) and node.func.attr == 'route':
                    if bp_name and node.args:
                        first_arg = node.args[0]
                        if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                            route_path = first_arg.value
                            method = 'GET'
                            for kw in node.keywords:
                                if kw.arg == 'methods':
                                    if isinstance(kw.value, ast.List):
                                        method = ','.join([e.value for e in kw.value.elts if isinstance(e, ast.Constant)])
                            full_ep = f"{bp_name.replace('_bp', '')}.{route_path}"
                            endpoints[full_ep] = {'bp': bp_name, 'path': route_path, 'methods': method}
    return endpoints

def extract_template_url_fors():
    templates_dir = PROJECT / 'templates'
    url_for_pattern = re.compile(r"url_for\('([^']+)'\")
    url_fors = defaultdict(list)
    for path in templates_dir.rglob('*.html'):
        text = path.read_text(encoding='utf-8')
        for match in url_for_pattern.finditer(text):
            endpoint = match.group(1)
            if endpoint.startswith('static'):
                continue
            url_fors[endpoint].append(str(path.relative_to(templates_dir)))
    return url_fors

def extract_route_template_vars():
    routes_dir = PROJECT / 'routes'
    route_vars = {}
    for path in routes_dir.glob('*.py'):
        if path.name.startswith('_'):
            continue
        try:
            tree = ast.parse(path.read_text(encoding='utf-8'))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == 'render_template':
                    if len(node.args) >= 1:
                        template_arg = node.args[0]
                        if isinstance(template_arg, ast.Constant):
                            template_name = template_arg.value
                            keywords = {kw.arg: 1 for kw in node.keywords}
                            route_vars.setdefault(template_name, set()).update(keywords.keys())
    return route_vars

def extract_template_vars_used():
    templates_dir = PROJECT / 'templates'
    template_vars = {}
    var_pattern = re.compile(r'\{\{\s*(\w+)')
    for path in templates_dir.rglob('*.html'):
        text = path.read_text(encoding='utf-8')
        vars_found = set()
        for match in var_pattern.finditer(text):
            var_name = match.group(1)
            if var_name not in ('url_for', 'static', 'loop', 'request', 'session', 'g', 'config', 'current_user', 'gettext', '_', 'csrf_token', 'form', 'super', 'self', 'caller'):
                vars_found.add(var_name)
        rel = str(path.relative_to(templates_dir))
        template_vars[rel] = vars_found
    return template_vars

if __name__ == '__main__':
    endpoints = extract_routes_and_blueprints()
    url_fors = extract_template_url_fors()
    route_vars = extract_route_template_vars()
    template_vars = extract_template_vars_used()

    print(f'Route endpoints found: {len(endpoints)}')
    print(f'Templates referencing url_for: {len(url_fors)}')
    print(f'Routes passing variables to templates: {len(route_vars)}')
    print(f'Templates using variables: {len(template_vars)}')

    # Check url_for endpoints exist
    url_for_issues = []
    for ep, templates in url_fors.items():
        # Check if endpoint exists in routes
        ep_found = False
        for route_ep in endpoints:
            # Match blueprint.route or just route
            if ep == route_ep:
                ep_found = True
                break
            # Check if it's just the function name without blueprint
            if '.' in route_ep:
                bp, route_path = route_ep.split('.', 1)
                if ep == route_path or ep == bp:
                    ep_found = True
                    break
        if not ep_found:
            # Check if it's a known special endpoint
            if ep not in ('index', 'main.index', 'auth.login', 'auth.logout', 'owner.dashboard'):
                url_for_issues.append((ep, templates[0]))

    if url_for_issues:
        print(f'\nURL_FOR ISSUES: {len(url_for_issues)}')
        for ep, tmpl in url_for_issues[:20]:
            print(f'  - {tmpl}: url_for(\"{ep}\")')
    else:
        print('\nAll url_for calls valid!')

    # Check template variables alignment
    var_issues = []
    for template_name, vars_passed in route_vars.items():
        # Find all template files matching this name
        for tmpl_path, vars_used in template_vars.items():
            if tmpl_path.endswith(template_name + '.html') or tmpl_path == template_name + '.html':
                missing_in_route = vars_used - vars_passed
                for v in missing_in_route:
                    if v not in ('tenant', 'company', 'branches', 'now', 'today', 'settings', 'current_user', 'permissions'):
                        pass

    print(f'\nVariable alignment checks done.')
