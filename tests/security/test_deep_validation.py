"""
Deep Validation Test Suite — Professional pytest-compatible security audit.

Validates:
1. All route files compile without syntax errors
2. Models have tenant_id where expected for multi-tenancy isolation
3. Security headers are set on HTTP responses
4. Critical routes have authentication decorators
5. Templates are free from tabnabbing and unsafe filter vulnerabilities
6. Utility modules import cleanly
7. No unexpected duplicate function definitions across utils/
"""

import ast
import os
import re

import pytest


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


class TestRouteCompilation:
    """Verify all Python route files compile without syntax errors."""

    def _route_files(self):
        routes_dir = os.path.join(PROJECT_ROOT, "routes")
        for fname in os.listdir(routes_dir):
            if fname.endswith(".py") and not fname.startswith("__"):
                yield os.path.join(routes_dir, fname)

    @pytest.mark.parametrize("path", list(_route_files(None)))
    def test_route_compiles(self, path):
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
        compile(source, path, "exec")


class TestModelIntegrity:
    """Verify model definitions enforce tenant isolation."""

    KNOWN_NON_TENANT_MODELS = frozenset({
        "LoginHistory",
        "SecurityAlert",
        "ErrorAuditLog",
        "CardVault",
        "Tenant",
        "SystemSettings",
        "IntegrationSettings",
        "Package",
        "StorePaymentMethod",
        "Currency",
        "ExchangeRate",
        "PackagePurchase",
        "APIKey",
        "CardPayment",
        "IndustryFieldDefinition",
    })

    @pytest.fixture(scope="class")
    def all_model_files(self):
        models_dir = os.path.join(PROJECT_ROOT, "models")
        files = []
        for fname in sorted(os.listdir(models_dir)):
            if fname.endswith(".py") and not fname.startswith("__"):
                files.append(os.path.join(models_dir, fname))
        return files

    def _extract_model_names_and_tenant(self, filepath):
        names = []
        has_tenant = False
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                tree = ast.parse(f.read())
            except SyntaxError:
                return names, has_tenant
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    base_name = ""
                    if isinstance(base, ast.Name):
                        base_name = base.id
                    elif isinstance(base, ast.Attribute):
                        base_name = base.attr
                    if base_name in ("Model", "db.Model", "Base"):
                        names.append(node.name)
                        break
                for item in node.body:
                    if isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name) and target.id == "tenant_id":
                                has_tenant = True
        return names, has_tenant

    def test_models_compile(self, all_model_files):
        errors = []
        for path in all_model_files:
            with open(path, "r", encoding="utf-8") as f:
                source = f.read()
            try:
                compile(source, path, "exec")
            except SyntaxError as exc:
                errors.append(f"{os.path.basename(path)}: {exc}")
        assert not errors, "; ".join(errors)

    def test_tenant_id_on_data_models(self, all_model_files):
        violations = []
        for path in all_model_files:
            names, has_tenant = self._extract_model_names_and_tenant(path)
            if not names:
                continue
            if has_tenant:
                continue
            for name in names:
                if name not in self.KNOWN_NON_TENANT_MODELS:
                    violations.append(f"{name} in {os.path.basename(path)} lacks tenant_id")
        assert not violations, "Tenant isolation gaps: " + "; ".join(violations)

    def test_all_exported_models_exist(self):
        from models import __all__ as exported
        import models
        missing = []
        for name in exported:
            if not hasattr(models, name):
                missing.append(name)
        assert not missing, f"Models missing from models/__init__.py: {missing}"


class TestSecurityHeaders:
    """Verify security headers are present on HTTP responses."""

    REQUIRED_HEADERS = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "SAMEORIGIN",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Content-Security-Policy": None,
    }

    OPTIONAL_HEADERS = {
        "Strict-Transport-Security": None,
    }

    def test_security_headers_on_public_route(self, app):
        with app.test_client() as client:
            response = client.get("/")
            for header, expected in self.REQUIRED_HEADERS.items():
                assert header in response.headers, f"Missing header: {header}"
                if expected is not None:
                    actual = response.headers.get(header, "").lower()
                    assert expected.lower() in actual, (
                        f"Header {header} expected to contain '{expected}', got '{actual}'"
                    )

    def test_csp_header_present(self, app):
        with app.test_client() as client:
            response = client.get("/")
            assert "Content-Security-Policy" in response.headers
            csp = response.headers.get("Content-Security-Policy", "")
            assert "default-src 'self'" in csp


class TestAuthDecorators:
    """Verify critical routes have authentication protection."""

    CRITICAL_ROUTE_FILES = frozenset({
        "routes/owner.py",
        "routes/payment_vault.py",
        "routes/payments.py",
        "routes/products.py",
        "routes/sales.py",
        "routes/customers.py",
        "routes/suppliers.py",
        "routes/warehouse.py",
        "routes/expenses.py",
        "routes/cheques.py",
        "routes/purchases.py",
        "routes/payroll.py",
        "routes/ledger.py",
    })

    DECORATOR_PATTERNS = [
        r"@login_required",
        r"@owner_required",
        r"@owner_only",
        r"@admin_required",
        r"@permission_required",
        r"@seller_or_above",
        r"@super_admin_required",
        r"@api_key_required",
        r"@jwt_required",
        r"@token_required",
    ]

    WHITELISTED_ROUTES = [
        r"def health_check",
        r"def webhook",
        r"def ipn",
        r"def public_",
        r"def landing",
        r"def about",
        r"def contact",
        r"def tenant_suspend_page",
        r"def serve_static",
        r"def robots",
        r"def sitemap",
        r"def .*_webhook",
        r"def api_create_",
        r"def api_v2_",
    ]

    def test_critical_routes_have_auth(self):
        failures = []
        for rel_path in self.CRITICAL_ROUTE_FILES:
            full = os.path.join(PROJECT_ROOT, rel_path)
            if not os.path.exists(full):
                continue
            with open(full, "r", encoding="utf-8") as f:
                content = f.read()
            lines = content.split("\n")
            in_route = False
            route_name = ""
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith("@") and "route(" in stripped:
                    in_route = True
                    route_name = stripped
                    continue
                if in_route and stripped.startswith("def "):
                    func_name = stripped.split("(")[0].replace("def ", "")
                    is_whitelisted = any(
                        re.search(pat, stripped) for pat in self.WHITELISTED_ROUTES
                    )
                    if is_whitelisted:
                        in_route = False
                        continue
                    preceding = "\n".join(lines[max(0, i - 5):i])
                    has_auth = any(
                        re.search(pat, preceding) for pat in self.DECORATOR_PATTERNS
                    )
                    if not has_auth:
                        failures.append(f"{rel_path}:{i + 1} {func_name}()")
                    in_route = False
                elif stripped.startswith("@") and not stripped.startswith("@route") and in_route:
                    continue
                elif stripped and not stripped.startswith("#") and not stripped.startswith("@") and in_route:
                    in_route = False
        assert not failures, (
            f"Unprotected route functions found ({len(failures)}): " + "; ".join(failures)
        )


class TestTemplateSecurity:
    """Verify templates are free from common security vulnerabilities."""

    def _template_files(self):
        templates_dir = os.path.join(PROJECT_ROOT, "templates")
        for root, _dirs, files in os.walk(templates_dir):
            for fname in files:
                if fname.endswith(".html"):
                    yield os.path.join(root, fname)

    def test_no_tabnabbing_without_noopener(self):
        violations = []
        for path in self._template_files():
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            for match in re.finditer(r'target="_blank"[^>]*>', content):
                tag = match.group(0)
                if 'rel="noopener' not in tag and "rel='noopener" not in tag:
                    rel_path = os.path.relpath(path, PROJECT_ROOT)
                    violations.append(f"{rel_path}: {tag[:80]}")
        assert not violations, f"Tabnabbing violations ({len(violations)}): " + "; ".join(violations)

    def test_no_dangerous_safe_filters(self):
        violations = []
        for path in self._template_files():
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            matches = re.findall(r'\{\{[^}]+\|safe', content)
            for m in matches:
                if "tojson" not in m.lower():
                    rel_path = os.path.relpath(path, PROJECT_ROOT)
                    violations.append(f"{rel_path}: {m}")
        assert not violations, f"Dangerous |safe filters ({len(violations)}): " + "; ".join(violations)


class TestUtilityModules:
    """Verify all utils modules import cleanly without runtime errors."""

    UTILS_TO_CHECK = [
        ("utils.api_response", ["success_response", "error_response", "paginated_response"]),
        ("utils.structured_logging", ["log_mutation", "log_security_event", "log_data_access"]),
        ("utils.db_safety", ["atomic_transaction", "safe_commit"]),
        ("utils.validators", ["ValidationError", "validate_positive_amount", "validate_email", "validate_id", "validate_pagination"]),
        ("utils.decorators", ["permission_required", "admin_required", "owner_required", "seller_or_above"]),
        ("utils.tenanting", ["get_active_tenant_id"]),
        ("utils.branching", ["branch_scope_id_for"]),
        ("utils.auth_helpers", ["is_admin_surface_user", "is_global_owner_user"]),
        ("utils.sanitizer", ["InputSanitizer", "sanitize_form_data"]),
        ("utils.helpers", ["format_currency", "timeago"]),
        ("utils.i18n", ["get_current_language", "is_rtl", "t"]),
        ("utils.security_helpers", ["owner_ip_check", "enforce_owner_ip_if_needed", "sanitize_sql_like", "validate_sql_order_by"]),
        ("utils.password_validator", ["PasswordValidator", "validate_password_with_helpful_message"]),
        ("utils.username_policy", ["validate_username_for_user", "normalize_username", "is_platform_user"]),
        ("utils.field_validators", ["FieldValidationError", "validate_currency_code", "validate_payment_method"]),
        ("utils.safe_redirect", ["is_safe_redirect_url", "safe_redirect_target"]),
        ("utils.error_messages", ["ErrorMessages", "error", "warning", "success"]),
        ("utils.constants", ["ROLE_LEVELS", "PERMISSIONS"]),
    ]

    @pytest.mark.parametrize("module_name,symbols", UTILS_TO_CHECK)
    def test_utils_module_imports(self, module_name, symbols):
        mod = __import__(module_name, fromlist=symbols)
        for sym in symbols:
            assert hasattr(mod, sym), f"{module_name}.{sym} missing"


class TestCodeQuality:
    """Static code quality checks across utils/."""

    KNOWN_DUPLICATES = frozenset({
        "decorated_function",
        "decorator",
        "wrapper",
        "__init__",
        "t",
        "log_exception",
        "model_has_tenant",
        "optimize_query",
        "tenant_query",
        "_resolve_user",
        "is_platform_owner",
        "filter",
    })

    def test_no_unexpected_duplicate_functions(self):
        utils_dir = os.path.join(PROJECT_ROOT, "utils")
        all_funcs = {}
        for root, _dirs, files in os.walk(utils_dir):
            if "localization" in root:
                continue
            for fname in files:
                if not fname.endswith(".py") or fname.startswith("__"):
                    continue
                fpath = os.path.join(root, fname)
                rel = os.path.relpath(fpath, PROJECT_ROOT)
                with open(fpath, "r", encoding="utf-8") as f:
                    try:
                        tree = ast.parse(f.read())
                    except SyntaxError:
                        continue
                file_funcs = set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        file_funcs.add(node.name)
                for name in file_funcs:
                    all_funcs.setdefault(name, []).append(rel)

        new_dups = []
        for name, files in all_funcs.items():
            if len(files) > 1 and name not in self.KNOWN_DUPLICATES:
                unique = sorted(set(files))
                if len(unique) > 1:
                    new_dups.append(f"'{name}' in {', '.join(unique)}")
        assert not new_dups, f"Duplicate functions: " + "; ".join(new_dups)

    def test_no_sys_exit_in_test_files(self):
        skip_files = {
            "tests/security/test_deep_validation.py",
            "tests/security/test_security_boundaries.py",
            "tests/regression/test_dynamic_gl_no_hardcoded.py",
            "tests/regression/test_dynamic_gl_resolution_path.py",
            "tests/regression/test_full_regression.py",
            "tests/regression/test_phase10.py",
        }
        for subdir in ["tests/unit", "tests/security", "tests/regression", "tests/integration"]:
            full_dir = os.path.join(PROJECT_ROOT, subdir)
            if not os.path.exists(full_dir):
                continue
            violations = []
            for root, _dirs, files in os.walk(full_dir):
                for fname in files:
                    if not fname.endswith(".py"):
                        continue
                    fpath = os.path.join(root, fname)
                    rel = os.path.relpath(fpath, PROJECT_ROOT).replace("\\", "/")
                    if rel in skip_files:
                        continue
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()
                    if "sys.exit(" in content:
                        violations.append(rel)
            assert not violations, f"Tests using sys.exit(): {violations}"
