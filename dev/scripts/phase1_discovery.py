#!/usr/bin/env python3
"""Phase 1 Discovery: inventory all error/flash/exception patterns."""

from pathlib import Path

routes_dir = Path("routes")
results = {}

for pyfile in routes_dir.rglob("*.py"):
    rel = str(pyfile)
    text = pyfile.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    patterns = {
        "flash_calls": 0,
        "abort_calls": 0,
        "raise_statements": 0,
        "try_blocks": 0,
        "except_blocks": 0,
        "current_app_logger_exception": 0,
    }
    # Simple line-based scan (fast, not AST-precise; sufficient for audit)
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if "flash(" in stripped and not stripped.startswith("#"):
            patterns["flash_calls"] += 1
        if "abort(" in stripped and not stripped.startswith("#"):
            patterns["abort_calls"] += 1
        if stripped.startswith("raise ") or "raise ValueError" in stripped or "raise Exception" in stripped:
            patterns["raise_statements"] += 1
        if stripped.startswith("try:") or stripped.startswith("try "):
            patterns["try_blocks"] += 1
        if stripped.startswith("except ") or stripped.startswith("except(") or stripped.startswith("except Exception"):
            patterns["except_blocks"] += 1
        if "current_app.logger.exception" in stripped or ".logger.exception(" in stripped:
            patterns["current_app_logger_exception"] += 1
    if any(v > 0 for v in patterns.values()):
        results[rel] = patterns

print(f"=== ROUTES DISCOVERY ({len(results)} files with patterns) ===")
for f, p in sorted(results.items()):
    flash = p["flash_calls"]
    abort = p["abort_calls"]
    try_ = p["try_blocks"]
    except_ = p["except_blocks"]
    log_exc = p["current_app_logger_exception"]
    print(f"{f}: flash={flash}, abort={abort}, try={try_}, except={except_}, logger_exception={log_exc}")
