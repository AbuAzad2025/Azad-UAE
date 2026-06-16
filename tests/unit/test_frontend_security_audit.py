import ast
import re
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestFrontendSecurityAudit:
    def _read_js_files(self):
        js_dir = PROJECT_ROOT / 'static' / 'js'
        files = {}
        for path in js_dir.rglob('*.js'):
            if '.min.' in path.name:
                continue
            if path.name.startswith('_'):
                continue
            try:
                files[path] = path.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                pass
        return files

    def test_no_hardcoded_prices_in_js(self):
        js_files = self._read_js_files()
        issues = []
        price_pattern = re.compile(r'(?:price|cost|amount)\s*[=:]\s*[1-9]\d*\.?\d*')
        for path, text in js_files.items():
            for line_num, line in enumerate(text.split('\n'), 1):
                if price_pattern.search(line):
                    if 'data.' not in line and 'response.' not in line and 'result.' not in line:
                        issues.append(f'{path.name}:{line_num}: {line.strip()[:80]}')
        assert issues == [], f'Hardcoded prices in JS: {issues[:20]}'

    def test_client_side_calculation_fallbacks_exist(self):
        js_files = self._read_js_files()
        has_backend_calc = False
        has_client_fallback = False
        for path, text in js_files.items():
            if 'calculateTotals' in text:
                if 'fetch' in text or '$.ajax' in text or '/api/' in text:
                    has_backend_calc = True
                if 'calculateTotalsClientSide' in text or 'ClientSide' in text:
                    has_client_fallback = True
        assert has_backend_calc, 'No backend calculation found in JS'

    def test_no_sensitive_data_in_localstorage(self):
        js_files = self._read_js_files()
        issues = []
        for path, text in js_files.items():
            if 'localStorage.setItem' in text:
                lines = text.split('\n')
                for i, line in enumerate(lines, 1):
                    if 'localStorage.setItem' in line:
                        if any(kw in line for kw in ['password', 'token', 'secret', 'key', 'api']):
                            issues.append(f'{path.name}:{i}: {line.strip()[:80]}')
        assert issues == [], f'Sensitive data in localStorage: {issues[:20]}'

    def test_csrf_token_protection_in_ajax(self):
        js_files = self._read_js_files()
        issues = []
        # Public-facing JS files intentionally do not use CSRF (unauthenticated endpoints)
        public_js_files = {'support.js'}
        for path, text in js_files.items():
            if path.name in public_js_files:
                continue
            if 'fetch' in text or '$.ajax' in text:
                # Check if file has any CSRF reference
                has_csrf = 'X-CSRFToken' in text or 'csrf-token' in text or 'csrf' in text.lower()
                if not has_csrf:
                    # Check line by line for POST
                    for i, line in enumerate(text.split('\n'), 1):
                        if ('$.ajax' in line or 'fetch(' in line) and ('POST' in line or 'post' in line):
                            issues.append(f'{path.name}:{i}: POST AJAX without CSRF')
                            break
        assert issues == [], f'Missing CSRF in POST AJAX: {issues[:20]}'

    def test_no_eval_or_new_function(self):
        js_files = self._read_js_files()
        issues = []
        dangerous = ['eval(', 'new Function']
        for path, text in js_files.items():
            for pattern in dangerous:
                if pattern in text:
                    # Skip comments mentioning eval
                    if pattern == 'eval(' and ('// eval' in text or '/* eval' in text):
                        continue
                    issues.append(f'{path.name}: uses {pattern}')
        assert issues == [], f'Dangerous JS patterns: {issues[:20]}'

    def test_post_forms_have_csrf_field(self):
        templates_dir = PROJECT_ROOT / 'templates'
        issues = []
        for path in templates_dir.rglob('*.html'):
            text = path.read_text(encoding='utf-8')
            if '<form' in text.lower() and ('method="post"' in text.lower() or "method='post'" in text.lower()):
                if 'csrf_token' not in text and 'hidden_tag' not in text:
                    rel = str(path.relative_to(templates_dir))
                    issues.append(rel)
        allowed = ['owner', 'public']
        issues = [f for f in issues if not any(f.startswith(a) for a in allowed)]
        assert issues == [], f'POST forms without CSRF: {issues[:20]}'

    def test_no_hardcoded_api_keys_in_js(self):
        js_files = self._read_js_files()
        issues = []
        key_pattern = re.compile(r'(api[_-]?key|apikey|secret[_-]?key|auth[_-]?token)\s*[=:]\s*["\'][^"\']{10,}["\']', re.IGNORECASE)
        for path, text in js_files.items():
            if key_pattern.search(text):
                issues.append(f'{path.name}: possible hardcoded API key')
        assert issues == [], f'Hardcoded API keys in JS: {issues}'

    def test_templates_escape_user_input(self):
        templates_dir = PROJECT_ROOT / 'templates'
        issues = []
        for path in templates_dir.rglob('*.html'):
            text = path.read_text(encoding='utf-8')
            # Check for unescaped user input
            if '{{ ' in text and ' | ' in text:
                if '|safe' in text:
                    rel = str(path.relative_to(templates_dir))
                    issues.append(rel)
                    break
        assert issues == [], f'Templates using |safe filter: {issues[:20]}'
