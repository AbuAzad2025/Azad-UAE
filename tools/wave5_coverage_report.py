"""Print coverage for the 24 STRICT EXECUTION target modules."""
from __future__ import annotations

import subprocess
import sys

TARGETS = [
    "services/sale_service.py",
    "services/payment_service.py",
    "extensions.py",
    "models/sale.py",
    "utils/tenant_limits.py",
    "utils/auth_helpers.py",
    "utils/password_validator.py",
    "app/integrity.py",
    "models/card_vault.py",
    "routes/customers.py",
    "routes/payment_vault.py",
    "services/ai_executor.py",
    "app/context.py",
    "app/factory.py",
    "bootstrap/blueprints.py",
    "routes/owner.py",
    "routes/ai.py",
    "routes/reports.py",
    "ai_knowledge/learning/continuous_learner.py",
    "ai_knowledge/agents/multi_agent_system.py",
    "ai_knowledge/core/context_engine.py",
    "ai_knowledge/generation/document_generator.py",
    "ai_knowledge/neural/transformers_brain.py",
    "ai_knowledge/core/conversation_manager.py",
]

TEST_ARGS = [
    "tests/unit/routes/",
    "tests/unit/app/",
    "tests/unit/services/test_payment_service_coverage.py",
    "tests/unit/test_sale_service_chunk3.py",
    "tests/unit/test_sale_service_fulfill.py",
    "tests/unit/test_extensions_coverage.py",
    "tests/unit/models/",
    "tests/unit/utils/test_tenant_limits.py",
    "tests/unit/utils/test_auth_helpers.py",
    "tests/unit/utils/test_password_validator.py",
    "tests/unit/test_payment_vault_chunk1.py",
    "tests/unit/test_payment_vault_chunk2.py",
    "tests/unit/test_payment_vault_chunk3.py",
    "tests/unit/test_payment_vault_chunk4.py",
    "tests/unit/test_ai_executor_extended.py",
    "tests/unit/test_ai_executor_assurance.py",
    "tests/unit/test_bootstrap_blueprints.py",
    "tests/unit/test_owner_routes_chunk1.py",
    "tests/unit/test_owner_routes_chunk2.py",
    "tests/unit/test_ai_routes_chunk1.py",
    "tests/unit/ai_knowledge/test_strict_execution_push.py",
    "tests/unit/ai_knowledge/test_wave4_coverage.py",
    "tests/unit/ai_knowledge/test_wave5_coverage.py",
    "tests/unit/ai_knowledge/test_wave6_coverage.py",
    "tests/unit/ai_knowledge/test_wave7_coverage.py",
    "tests/unit/ai_knowledge/test_wave8_final_coverage.py",
    "tests/unit/ai_knowledge/test_99_coverage_push.py",
]


def main() -> int:
    cov = sys.executable.replace("python.exe", "coverage.exe")
    if not cov.endswith("coverage.exe"):
        cov = ".venv/Scripts/coverage.exe"
    subprocess.run([cov, "erase"], check=False)
    pytest = [sys.executable, "-m", "pytest", *TEST_ARGS, "-q", "--tb=no",
              "--override-ini=addopts=-q --tb=no --import-mode=importlib --basetemp=tests/.pytest-temp -p no:cacheprovider"]
    rc = subprocess.run(pytest).returncode
    include = ",".join(TARGETS)
    subprocess.run([cov, "report", f"--include={include}", "--precision=1"], check=False)
    at_target = 0
    print("\n=== SUMMARY ===")
    result = subprocess.run(
        [cov, "report", f"--include={include}", "--precision=1"],
        capture_output=True, text=True,
    )
    for line in result.stdout.splitlines():
        if line.endswith(".py") or "\\" in line and "Stmts" not in line and "TOTAL" not in line and "---" not in line:
            parts = line.split()
            if len(parts) >= 4 and parts[-1].endswith("%"):
                pct = float(parts[-1].rstrip("%"))
                if pct >= 99.0:
                    at_target += 1
    print(f"Files at >=99%: {at_target}/24")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
