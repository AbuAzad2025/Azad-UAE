#!/usr/bin/env python3
"""Phase 0 Deep Audit: complete inventory before framework application."""

from pathlib import Path

print("=" * 60)
print("PHASE 0 — DEEP DISCOVERY AUDIT")
print("=" * 60)

# --- 1. Routes ---
routes_dir = Path("routes")
route_files = sorted(p for p in routes_dir.rglob("*.py") if p.is_file())
print(f"\n[1] ROUTES: {len(route_files)} Python files scanned")
route_stats = {}
for f in route_files:
    rel = str(f)
    text = f.read_text(encoding="utf-8", errors="replace")
    flash = text.count("flash(")
    abort = text.count("abort(")
    raise_ = text.count("raise ")
    try_ = text.count("try:")
    except_ = text.count("except ")
    log_exc = text.count("current_app.logger.exception")
    if any([flash, abort, raise_, try_, except_, log_exc]):
        route_stats[rel] = {
            "flash": flash,
            "abort": abort,
            "raise": raise_,
            "try": try_,
            "except": except_,
            "logger_exception": log_exc,
        }

# Sort by (flash + abort + except) descending
top_routes = sorted(route_stats.items(), key=lambda x: x[1]["flash"] + x[1]["abort"] + x[1]["except"], reverse=True)
print("\nTop routes by exception/flash volume:")
for rel, s in top_routes[:10]:
    print(
        f"  {rel}: flash={s['flash']} abort={s['abort']} raise={s['raise']} try={s['try']} except={s['except']} logger_exception={s['logger_exception']}"
    )

# --- 2. Services ---
services_dir = Path("services")
service_files = sorted(p for p in services_dir.rglob("*.py") if p.is_file())
print(f"\n[2] SERVICES: {len(service_files)} Python files scanned")
service_stats = {}
for f in service_files:
    rel = str(f)
    text = f.read_text(encoding="utf-8", errors="replace")
    flash = text.count("flash(")
    abort = text.count("abort(")
    raise_ = text.count("raise ")
    try_ = text.count("try:")
    except_ = text.count("except ")
    log_exc = text.count("current_app.logger.exception")
    atomic_txn = text.count("atomic_transaction")
    if any([flash, abort, raise_, try_, except_, log_exc, atomic_txn]):
        service_stats[rel] = {
            "flash": flash,
            "abort": abort,
            "raise": raise_,
            "try": try_,
            "except": except_,
            "logger_exception": log_exc,
            "atomic_transaction": atomic_txn,
        }

top_services = sorted(service_stats.items(), key=lambda x: x[1]["try"] + x[1]["except"], reverse=True)
print("\nTop services by try/except volume:")
for rel, s in top_services[:10]:
    print(
        f"  {rel}: try={s['try']} except={s['except']} atomic_txn={s['atomic_transaction']} flash={s['flash']} abort={s['abort']}"
    )

# --- 3. Models with to_dict ---
models_dir = Path("models")
model_files = sorted(p for p in models_dir.rglob("*.py") if p.is_file() and p.name != "__init__.py")
print(f"\n[3] MODELS: {len(model_files)} files")
models_with_dict = []
for f in model_files:
    text = f.read_text(encoding="utf-8", errors="replace")
    if "def to_dict" in text:
        models_with_dict.append(str(f))
print(f"Models with to_dict(): {len(models_with_dict)}")
for m in sorted(models_with_dict):
    print(f"  {m}")

# --- 4. Check if branch_id present in to_dict ---
print("\n[4] to_dict() branch_id audit:")
for m_path in sorted(models_with_dict):
    text = Path(m_path).read_text(encoding="utf-8", errors="replace")
    has_branch = '"branch_id"' in text or "'branch_id'" in text
    print(f"  {m_path}: branch_id in to_dict = {has_branch}")

# --- 5. Migration head check ---
print("\n[5] MIGRATION HEAD:")
try:
    import subprocess

    result = subprocess.run(
        ["python", "scripts/lint/check_migration_head.py"], capture_output=True, text=True, timeout=30
    )
    for line in result.stdout.splitlines()[-3:]:
        print(f"  {line}")
except Exception as e:
    print(f"  Migration check error: {e}")

# --- 6. Framework status ---
print("\n[6] FRAMEWORK (core/messages.py):")
framework_path = Path("core/messages.py")
if framework_path.exists():
    text = framework_path.read_text(encoding="utf-8", errors="replace")
    lines = len(text.splitlines())
    classes = text.count("class ")
    functions = text.count("def ")
    print(f"  Exists: yes ({lines} lines, {classes} classes, {functions} functions)")
    print(f"  Contains ERPError: {'ERPError' in text}")
    print(f"  Contains UnbalancedLedgerError: {'UnbalancedLedgerError' in text}")
    print(f"  Contains InsufficientStockError: {'InsufficientStockError' in text}")
    print(f"  Contains ClosedPeriodError: {'ClosedPeriodError' in text}")
else:
    print("  Exists: NO")

# --- 7. CI timeout setting ---
print("\n[7] CI TIMEOUT (.github/workflows/ci.yml):")
ci_text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8", errors="replace")
for line in ci_text.splitlines():
    if "timeout-minutes" in line:
        print(f"  {line.strip()}")
