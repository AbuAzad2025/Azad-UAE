"""
Security Boundary Audit — Multi-Tenant Data Leak Prevention
Phase 7.5: Security Hardening

Checks every route, service, and template for cross-tenant,
cross-branch, and cross-role data leakage.

Run: python tools/qa/test_security_boundaries.py
"""

from decimal import Decimal


def _assert_no_unscoped_query_in_file(file_path, model_name, required_filter):
    """Fail if a .query operation on model_name exists without required_filter."""
    with open(file_path, 'r', encoding='utf-8') as f:
        source = f.read()
    lines = source.splitlines()
    violations = []
    for i, line in enumerate(lines, 1):
        if f'{model_name}.query' in line and required_filter not in line:
            # Exclude comment lines and lines that already have the filter
            stripped = line.strip()
            if stripped.startswith('#') or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            # Exclude lines where the filter is on a previous continuation
            if i > 1 and required_filter in lines[i - 2]:
                continue
            violations.append((i, stripped))
    return violations


def _audit_routes_for_auth():
    """Ensure all non-public routes have @login_required."""
    import os
    import ast
    route_files = [
        os.path.join('routes', f)
        for f in os.listdir('routes')
        if f.endswith('.py') and f != 'public.py'
    ]
    violations = []
    for rf in route_files:
        path = os.path.join('d:/Data/karaj/UAE/Azad-UAE', rf)
        if not os.path.exists(path):
            continue
        with open(path, 'r', encoding='utf-8') as f:
            source = f.read()
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                decorators = [d for d in node.decorator_list]
                has_route = any(
                    isinstance(d, ast.Call) and
                    getattr(d.func, 'attr', '') == 'route'
                    for d in decorators
                )
                has_login = any(
                    isinstance(d, ast.Name) and d.id == 'login_required'
                    for d in decorators
                )
                if has_route and not has_login:
                    # Exclude before_request / after_request helpers
                    if not node.name.startswith('_'):
                        violations.append((rf, node.name))
    return violations


def _audit_ai_routes_tenant_scope():
    """AI routes must not use bare Product/Customer.query.get(id)."""
    path = 'd:/Data/karaj/UAE/Azad-UAE/routes/ai.py'
    with open(path, 'r', encoding='utf-8') as f:
        source = f.read()
    violations = []
    dangerous_patterns = [
        'Product.query.get(',
        'Customer.query.get(',
        'Customer.query.filter_by(is_active=True).all()',
        'Product.query.filter_by(is_active=True).all()',
        'Customer.query.filter_by(is_active=True).limit',
        'Product.query.filter_by(is_active=True).limit',
        'Customer.query.filter_by(name=',
    ]
    for pat in dangerous_patterns:
        if pat in source:
            violations.append(pat)
    return violations


def _audit_owner_dashboard_tenant_scope():
    """Owner dashboard must scope AuditLog, User, Product, Branch by tenant."""
    path = 'd:/Data/karaj/UAE/Azad-UAE/routes/owner.py'
    with open(path, 'r', encoding='utf-8') as f:
        source = f.read()
    violations = []
    dangerous = [
        'AuditLog.query.count()',
        'AuditLog.query.order_by',
        'User.query.filter_by(is_active=True, is_owner=False).count()',
        'Product.query.filter_by(is_active=True).count()',
        'Branch.query.all()',
    ]
    for pat in dangerous:
        if pat in source:
            violations.append(pat)
    return violations


def _audit_api_routes_tenant_scope():
    """API routes must not use bare User.query or unscoped customer query."""
    path = 'd:/Data/karaj/UAE/Azad-UAE/routes/api.py'
    with open(path, 'r', encoding='utf-8') as f:
        source = f.read()
    violations = []
    dangerous = [
        'User.query.filter_by(username=username).first()',
    ]
    for pat in dangerous:
        if pat in source:
            violations.append(pat)
    # Check _scoped_customer_query for tenant_id
    if 'def _scoped_customer_query' in source and 'tenant_id' not in source.split('def _scoped_customer_query')[1].split('def ')[0]:
        violations.append('_scoped_customer_query missing tenant_id filter')
    if 'def _scoped_supplier_query' in source and 'tenant_id' not in source.split('def _scoped_supplier_query')[1].split('def ')[0]:
        violations.append('_scoped_supplier_query missing tenant_id filter')
    return violations


def _audit_payment_vault_tenant_scope():
    """PaymentVault and Donation queries must be tenant-scoped."""
    path = 'd:/Data/karaj/UAE/Azad-UAE/routes/payment_vault.py'
    with open(path, 'r', encoding='utf-8') as f:
        source = f.read()
    violations = []
    dangerous = [
        'PaymentVault.query.first()',
        'Donation.query.filter_by(transaction_type=',
        'Package.query.order_by(Package.sort_order.asc()).all()',
    ]
    for pat in dangerous:
        if pat in source:
            violations.append(pat)
    return violations


def _audit_main_dashboard_tenant_scope():
    """Main dashboard Product count must be tenant-scoped when branch=None."""
    path = 'd:/Data/karaj/UAE/Azad-UAE/routes/main.py'
    with open(path, 'r', encoding='utf-8') as f:
        source = f.read()
    violations = []
    # The pattern: else: total_products = Product.query.filter_by(is_active=True).count()
    if 'Product.query.filter_by(is_active=True).count()' in source:
        violations.append('Product.query.filter_by(is_active=True).count() — missing tenant_id')
    return violations


def _audit_templates_for_leaks():
    """Templates should not access unscoped models directly."""
    import os
    violations = []
    template_dir = 'd:/Data/karaj/UAE/Azad-UAE/templates'
    for root, _, files in os.walk(template_dir):
        for f in files:
            if not f.endswith('.html'):
                continue
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8') as tf:
                content = tf.read()
            # Look for direct model queries in Jinja2 (anti-pattern)
            if 'query.filter' in content or 'query.all()' in content or 'query.first()' in content:
                violations.append(f'{f}: contains raw query in template')
    return violations


def main():
    print("=" * 70)
    print("SECURITY BOUNDARY AUDIT — Phase 7.5")
    print("=" * 70)
    errors = []

    # 1. Auth decorators
    print("\n=== Check 1: Route Auth Decorators ===")
    auth_violations = _audit_routes_for_auth()
    if auth_violations:
        for file_name, func_name in auth_violations[:10]:
            msg = f"  [FAIL] {file_name}::{func_name} missing @login_required"
            print(msg)
            errors.append(msg)
        if len(auth_violations) > 10:
            print(f"  ... and {len(auth_violations) - 10} more")
    else:
        print("  [PASS] All routes have login_required")

    # 2. AI routes tenant scope
    print("\n=== Check 2: AI Routes Tenant Scope ===")
    ai_violations = _audit_ai_routes_tenant_scope()
    if ai_violations:
        for v in ai_violations:
            msg = f"  [FAIL] routes/ai.py: unscoped query pattern: {v}"
            print(msg)
            errors.append(msg)
    else:
        print("  [PASS] AI routes are tenant-scoped")

    # 3. Owner dashboard tenant scope
    print("\n=== Check 3: Owner Dashboard Tenant Scope ===")
    owner_violations = _audit_owner_dashboard_tenant_scope()
    if owner_violations:
        for v in owner_violations:
            msg = f"  [FAIL] routes/owner.py: unscoped query: {v}"
            print(msg)
            errors.append(msg)
    else:
        print("  [PASS] Owner dashboard is tenant-scoped")

    # 4. API routes tenant scope
    print("\n=== Check 4: API Routes Tenant Scope ===")
    api_violations = _audit_api_routes_tenant_scope()
    if api_violations:
        for v in api_violations:
            msg = f"  [FAIL] routes/api.py: unscoped query: {v}"
            print(msg)
            errors.append(msg)
    else:
        print("  [PASS] API routes are tenant-scoped")

    # 5. Payment vault tenant scope
    print("\n=== Check 5: Payment Vault Tenant Scope ===")
    pv_violations = _audit_payment_vault_tenant_scope()
    if pv_violations:
        for v in pv_violations:
            msg = f"  [FAIL] routes/payment_vault.py: unscoped query: {v}"
            print(msg)
            errors.append(msg)
    else:
        print("  [PASS] Payment vault routes are tenant-scoped")

    # 6. Main dashboard tenant scope
    print("\n=== Check 6: Main Dashboard Tenant Scope ===")
    main_violations = _audit_main_dashboard_tenant_scope()
    if main_violations:
        for v in main_violations:
            msg = f"  [FAIL] routes/main.py: unscoped query: {v}"
            print(msg)
            errors.append(msg)
    else:
        print("  [PASS] Main dashboard is tenant-scoped")

    # 7. Templates
    print("\n=== Check 7: Template Query Anti-Patterns ===")
    tmpl_violations = _audit_templates_for_leaks()
    if tmpl_violations:
        for v in tmpl_violations:
            msg = f"  [FAIL] {v}"
            print(msg)
            errors.append(msg)
    else:
        print("  [PASS] No raw queries in templates")

    # Summary
    print("\n" + "=" * 70)
    if errors:
        print(f"SECURITY AUDIT FAILED — {len(errors)} violation(s)")
        print("=" * 70)
        for e in errors:
            print(f"  • {e}")
        return 1
    else:
        print("ALL SECURITY CHECKS PASSED")
        print("=" * 70)
        return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
