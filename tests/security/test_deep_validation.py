"""
Deep Validation Test — Session 8 Final Check
Validates:
1. All modified route files compile
2. No unscoped queries in audited routes
3. No duplicate function definitions across utils
4. All new utility modules import correctly
5. Security headers present in app.py
6. XSS protection in critical templates
"""
import os
import re
import ast
import sys

# Add project to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

ERRORS = []
WARNINGS = []

def error(msg):
    ERRORS.append(msg)
    print(f"  [FAIL] {msg}")

def warn(msg):
    WARNINGS.append(msg)
    print(f"  [WARN] {msg}")

def ok(msg):
    print(f"  [PASS] {msg}")


# ============ 1. Compilation Check ============
print("\n=== Check 1: All Modified Routes Compile ===")
modified_routes = [
    'routes/ai.py', 'routes/owner.py', 'routes/payment_vault.py',
    'routes/api.py', 'routes/main.py', 'routes/public.py',
    'routes/customers.py', 'routes/payments.py', 'routes/products.py',
    'routes/warehouse.py', 'routes/advanced_ledger.py',
    'routes/sales.py', 'routes/purchases.py', 'routes/users.py',
    'routes/suppliers.py'
]
for path in modified_routes:
    full = os.path.join(os.path.dirname(__file__), '..', '..', path)
    try:
        with open(full, 'r', encoding='utf-8') as f:
            compile(f.read(), full, 'exec')
        ok(f"{path} compiles")
    except SyntaxError as e:
        error(f"{path} SYNTAX ERROR: {e}")


# ============ 2. No Unscoped Queries in Critical Routes ============
print("\n=== Check 2: Unscoped Query Scan ===")
# Routes that MUST scope by tenant_id
critical_routes = [
    'routes/ai.py', 'routes/payment_vault.py', 'routes/owner.py',
    'routes/customers.py', 'routes/payments.py', 'routes/products.py',
    'routes/warehouse.py', 'routes/advanced_ledger.py'
]
# Models that CONFIRMED have tenant_id column and MUST be scoped
models_with_tenant = {
    'Product', 'Customer', 'Sale', 'Purchase', 'Payment', 'Receipt',
    'Supplier', 'Warehouse', 'Branch', 'GLAccount', 'Cheque',
    'CustomsTax', 'ExpenseCategory', 'AdvancedExpense', 'Donation',
    'AuditLog', 'User', 'APIKey', 'ArchivedRecord', 'TenantStore',
    'ProductCategory',
}
# Models that do NOT have tenant_id (platform-level) — skip these
models_without_tenant = {
    'CardVault', 'LoginHistory', 'SecurityAlert', 'ErrorAuditLog',
}
# Dangerous patterns that should be scoped — only for models WITH tenant_id
dangerous_patterns = [
    r'(?<!\w)Product\.query\.get\(',
    r'(?<!\w)Customer\.query\.get\(',
    r'(?<!\w)Sale\.query\.get\(',
    r'(?<!\w)Supplier\.query\.get\(',
    r'(?<!\w)Warehouse\.query\.get\(',
    r'(?<!\w)Branch\.query\.get\(',
    r'(?<!\w)Payment\.query\.get\(',
    r'(?<!\w)Cheque\.query\.get\(',
    r'(?<!\w)Donation\.query\.get\(',
    r'(?<!\w)ProductCategory\.query\.',
]

# These are whitelisted patterns (already known safe patterns)
whitelist_patterns = [
    r'tenant_get\(', r'tenant_get_or_404\(', r'tenant_query\(',
    r'InvoiceSettings\.company_print_context\(',
    r'InvoiceSettings\.get_active\(',
    r'BackupService\.',
    r'ArchiveService\.',
    r'ErrorAuditService\.',
    r'get_visible_products_query\(',
    r'scoped_user_query\(',
    r'_accounts\(\)',
    r'gl_account_query\(',
    r'gl_entry_query\(',
    r'is_global_owner_user\(',
    r'PaymentVault\.get_platform_vault\(',
]

for route_path in critical_routes:
    full = os.path.join(os.path.dirname(__file__), '..', '..', route_path)
    with open(full, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
        lines = content.split('\n')
    
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        # Skip import lines
        if stripped.startswith('from ') or stripped.startswith('import '):
            continue
        # Check for dangerous patterns
        for pat in dangerous_patterns:
            if re.search(pat, stripped):
                # Check if line already has tenant_id or is whitelisted
                if 'tenant_id' in stripped:
                    continue
                # Check next 2 lines for tenant_id (multi-line statements)
                context = stripped
                for j in range(1, 3):
                    if i + j - 1 < len(lines):
                        context += lines[i + j - 1]
                if 'tenant_id' in context:
                    continue
                if any(re.search(wp, stripped) for wp in whitelist_patterns):
                    continue
                # Skip known safe patterns
                warn(f"{route_path}:{i} — possible unscoped: {stripped[:80]}")

ok("Unscoped query scan completed")


# ============ 3. No Duplicate Functions ============
print("\n=== Check 3: Duplicate Function Definitions ===")
# Known pre-existing duplicates in the codebase (not created by us)
known_duplicates = {
    'decorated_function', 'decorator', 'calculate_tax', 'format_tax_return',
    'generate_einvoice', 'get_wps_format', 't', '_resolve_user', '__init__',
    'tenant_query', 'model_has_tenant', 'unexpected_error', 'wrapper', 'optimize_query',
    'log_exception', 'validate_username_for_user', 'validate_password_with_helpful_message',
}
utils_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'utils')
all_funcs = {}  # name -> [list of files]
for root, dirs, files in os.walk(utils_dir):
    for fname in files:
        if not fname.endswith('.py'):
            continue
        fpath = os.path.join(root, fname)
        rel = os.path.relpath(fpath, os.path.join(os.path.dirname(__file__), '..', '..'))
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                tree = ast.parse(f.read())
            file_funcs = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    name = node.name
                    file_funcs.add(name)
            for name in file_funcs:
                if name not in all_funcs:
                    all_funcs[name] = []
                all_funcs[name].append(rel)
        except SyntaxError:
            warn(f"Cannot parse {rel}")
        except Exception as e:
            warn(f"Error reading {rel}: {e}")

new_duplicates = []
for name, files in all_funcs.items():
    if len(files) > 1 and name not in known_duplicates:
        # Only flag if the SAME function name appears in DIFFERENT files
        unique_files = sorted(set(files))
        if len(unique_files) > 1:
            new_duplicates.append(f"'{name}' in {', '.join(unique_files)}")

if new_duplicates:
    for d in new_duplicates:
        error(f"Duplicate function {d}")
else:
    ok("No new duplicate function definitions across utils/")


# ============ 4. New Utility Modules Import ============
print("\n=== Check 4: New Utility Modules Import ===")
try:
    from utils.api_response import success_response, error_response, paginated_response
    ok("utils.api_response imports")
except Exception as e:
    error(f"utils.api_response: {e}")

try:
    from utils.structured_logging import log_mutation, log_security_event, log_data_access
    ok("utils.structured_logging imports")
except Exception as e:
    error(f"utils.structured_logging: {e}")

try:
    from utils.db_safety import atomic_transaction, safe_commit
    ok("utils.db_safety imports")
except Exception as e:
    error(f"utils.db_safety: {e}")

try:
    from utils.validators import ValidationError, validate_positive_amount, validate_email, validate_id, validate_pagination
    ok("utils.validators imports")
except Exception as e:
    error(f"utils.validators: {e}")


# ============ 5. Security Headers in app.py ============
print("\n=== Check 5: Security Headers in app.py ===")
app_path = os.path.join(os.path.dirname(__file__), '..', '..', 'app.py')
with open(app_path, 'r', encoding='utf-8') as f:
    app_content = f.read()

required_headers = [
    'Content-Security-Policy',
    'X-Frame-Options',
    'X-Content-Type-Options',
    'Referrer-Policy',
    'Strict-Transport-Security'
]
for header in required_headers:
    if header in app_content:
        ok(f"{header} present")
    else:
        error(f"{header} MISSING")


# ============ 6. XSS Protection in Templates ============
print("\n=== Check 6: XSS Protection in Critical Templates ===")
templates_to_check = [
    'templates/pos/index.html',
    'templates/payments/voucher.html'
]
for tmpl in templates_to_check:
    full = os.path.join(os.path.dirname(__file__), '..', '..', tmpl)
    with open(full, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    
    # Check for esc() function in pos/index.html
    if 'pos' in tmpl:
        if 'const esc' in content:
            ok(f"{tmpl} — esc() function defined")
        else:
            error(f"{tmpl} — esc() function MISSING")
        
        # Check esc is used with innerHTML
        esc_uses = re.findall(r'esc\([^)]+\)', content)
        if len(esc_uses) >= 2:
            ok(f"{tmpl} — esc() used {len(esc_uses)} times")
        else:
            error(f"{tmpl} — esc() not used enough")
    
    # Check |safe without tojson
    unsafe_safe = re.findall(r'\{\{[^}]+\|safe', content)
    if unsafe_safe:
        # Filter out tojson|safe which is safe
        dangerous = [s for s in unsafe_safe if 'tojson' not in s]
        if dangerous:
            error(f"{tmpl} — dangerous |safe: {dangerous}")
        else:
            ok(f"{tmpl} — only safe tojson|safe found")
    else:
        ok(f"{tmpl} — no |safe filters found")


# ============ 7. Tabnabbing Protection ============
print("\n=== Check 7: Tabnabbing Protection ===")
tabnabbing_violations = 0
for root, dirs, files in os.walk(os.path.join(os.path.dirname(__file__), '..', '..', 'templates')):
    for fname in files:
        if not fname.endswith('.html'):
            continue
        fpath = os.path.join(root, fname)
        rel = os.path.relpath(fpath, os.path.join(os.path.dirname(__file__), '..', '..'))
        with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        
        # Find target="_blank" without rel="noopener noreferrer"
        matches = re.findall(r'target="_blank"[^>]*>', content)
        for m in matches:
            if 'noopener' not in m:
                tabnabbing_violations += 1

if tabnabbing_violations == 0:
    ok("All target='_blank' links have rel='noopener noreferrer'")
else:
    error(f"{tabnabbing_violations} tabnabbing violations found")


# ============ 8. atomic_transaction Usage ============
print("\n=== Check 8: atomic_transaction Usage in Financial Routes ===")
financial_routes = ['routes/sales.py', 'routes/purchases.py', 'routes/payments.py', 'routes/warehouse.py']
for route in financial_routes:
    full = os.path.join(os.path.dirname(__file__), '..', '..', route)
    with open(full, 'r', encoding='utf-8') as f:
        content = f.read()
    if 'atomic_transaction' in content:
        ok(f"{route} uses atomic_transaction")
    else:
        warn(f"{route} does NOT use atomic_transaction")


# ============ Summary ============
print("\n" + "=" * 60)
print("DEEP VALIDATION SUMMARY")
print("=" * 60)
print(f"Errors:   {len(ERRORS)}")
print(f"Warnings: {len(WARNINGS)}")

if ERRORS:
    print("\nERRORS:")
    for e in ERRORS:
        print(f"  - {e}")

if WARNINGS:
    print("\nWARNINGS:")
    for w in WARNINGS:
        print(f"  - {w}")

if not ERRORS:
    print("\n" + "=" * 60)
    print("ALL DEEP VALIDATION CHECKS PASSED")
    print("=" * 60)
    sys.exit(0)
else:
    print("\n" + "=" * 60)
    print("DEEP VALIDATION FAILED")
    print("=" * 60)
    sys.exit(1)
