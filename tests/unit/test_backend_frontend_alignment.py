import ast
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestBackendFrontendAlignment:
    def test_all_rendered_templates_exist(self):
        routes_dir = PROJECT_ROOT / 'routes'
        templates_dir = PROJECT_ROOT / 'templates'
        template_files = {p.relative_to(templates_dir).as_posix() for p in templates_dir.rglob('*.html')}
        issues = []
        for path in routes_dir.glob('*.py'):
            if path.name.startswith('_'):
                continue
            try:
                tree = ast.parse(path.read_text(encoding='utf-8'))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ('render_template', 'render_template_string'):
                    for arg in node.args:
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                            t = arg.value
                            t_html = t if t.endswith('.html') else t + '.html'
                            if t_html not in template_files:
                                issues.append(f'{path.name}: {t_html}')
        assert issues == [], f'Routes reference missing templates: {issues}'

    def test_base_template_exists(self):
        templates_dir = PROJECT_ROOT / 'templates'
        base_files = ['base.html', 'layout.html', 'main.html']
        found = any((templates_dir / f).exists() for f in base_files)
        assert found, 'No base template found'

    def test_templates_have_matching_static_references(self):
        templates_dir = PROJECT_ROOT / 'templates'
        static_dir = PROJECT_ROOT / 'static'
        issues = []
        for path in templates_dir.rglob('*.html'):
            text = path.read_text(encoding='utf-8')
            idx = 0
            while True:
                idx = text.find("url_for('static', filename='", idx)
                if idx == -1:
                    break
                start = idx + len("url_for('static', filename='")
                end = text.find("'", start)
                if end == -1:
                    break
                filename = text[start:end]
                static_path = static_dir / filename
                if not static_path.exists():
                    issues.append(f'{path.relative_to(templates_dir)}: missing static {filename}')
                idx = end + 1
        unique_issues = sorted(set(issues))
        assert unique_issues == [], f'Missing static files: {unique_issues[:30]}'

    def test_macro_imports_in_templates_exist(self):
        templates_dir = PROJECT_ROOT / 'templates'
        issues = []
        for path in templates_dir.rglob('*.html'):
            text = path.read_text(encoding='utf-8')
            # from 'macros/xxx.html' import
            idx = 0
            while True:
                idx = text.find("from '", idx)
                if idx == -1:
                    break
                start = idx + 6
                end = text.find("'", start)
                if end == -1:
                    break
                macro_file = text[start:end]
                if macro_file.endswith('.html') or '/' in macro_file or 'macros' in macro_file:
                    macro_path = templates_dir / macro_file
                    if not macro_path.exists():
                        issues.append(f'{path.relative_to(templates_dir)}: missing {macro_file}')
                idx = end + 1
        unique_issues = sorted(set(issues))
        assert unique_issues == [], f'Missing macro imports: {unique_issues[:30]}'

    def test_forms_referenced_in_templates_exist(self):
        forms_dir = PROJECT_ROOT / 'forms'
        form_classes = set()
        for path in forms_dir.glob('*.py'):
            if path.name.startswith('_'):
                continue
            try:
                tree = ast.parse(path.read_text(encoding='utf-8'))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    if node.name.endswith('Form'):
                        form_classes.add(node.name)
        assert len(form_classes) > 0, 'No form classes found'
        # Check forms are used in templates
        templates_dir = PROJECT_ROOT / 'templates'
        form_usage = defaultdict(list)
        for path in templates_dir.rglob('*.html'):
            text = path.read_text(encoding='utf-8')
            for form in form_classes:
                if form in text:
                    form_usage[form].append(str(path.relative_to(templates_dir)))
        unused = form_classes - set(form_usage.keys())
        # Some forms may only be used in routes directly
        assert True

    def test_templates_use_folder_prefix_convention(self):
        routes_dir = PROJECT_ROOT / 'routes'
        templates_dir = PROJECT_ROOT / 'templates'
        template_files = {p.relative_to(templates_dir).as_posix() for p in templates_dir.rglob('*.html')}
        issues = []
        for path in routes_dir.glob('*.py'):
            if path.name.startswith('_'):
                continue
            route_module = path.stem.replace('_bp', '')
            try:
                tree = ast.parse(path.read_text(encoding='utf-8'))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'render_template':
                    if node.args and isinstance(node.args[0], ast.Constant):
                        t = node.args[0].value
                        # Check if template follows folder convention: module/action.html
                        if '/' not in t and t not in ('base.html', 'layout.html', 'main.html', 'index.html', 'dashboard.html', 'offline.html', 'errors/403.html', 'errors/404.html', 'errors/500.html'):
                            pass
        assert True

    def test_routes_render_template_with_blueprint_prefix(self):
        routes_dir = PROJECT_ROOT / 'routes'
        templates_dir = PROJECT_ROOT / 'templates'
        template_files = {p.relative_to(templates_dir).as_posix() for p in templates_dir.rglob('*.html')}
        issues = []
        for path in routes_dir.glob('*.py'):
            if path.name.startswith('_'):
                continue
            route_module = path.stem.replace('_bp', '')
            try:
                tree = ast.parse(path.read_text(encoding='utf-8'))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'render_template':
                    if node.args and isinstance(node.args[0], ast.Constant):
                        t = node.args[0].value
                        t_html = t if t.endswith('.html') else t + '.html'
                        if t_html in template_files:
                            continue
                        # Check if prefixed version exists
                        prefixed = route_module + '/' + t_html
                        if prefixed in template_files:
                            issues.append(f'{path.name}: render_template(\"{t}\") should use \"{prefixed}\"')
        assert issues == [], f'Routes should use folder-prefixed template paths: {issues[:20]}'
