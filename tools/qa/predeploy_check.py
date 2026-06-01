"""
Unified pre-deploy QA gate — single entry point for local/staging readiness.

Run: python tools/qa/predeploy_check.py --profile local

Delegates to existing QA scripts where possible; does not replace them.
Uses DATABASE_URL from .env; never prints secrets.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from dataclasses import dataclass, field

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

REQUIRED_INDEXES = [
    "ix_stock_movements_tenant_product_created",
    "ix_stock_movements_tenant_warehouse_created",
    "ix_sales_tenant_sale_date",
    "ix_sale_lines_product_id",
    "ix_purchase_lines_product_id",
    "ix_gl_journal_entries_tenant_entry_date",
    "ix_gl_journal_lines_tenant_account",
    "ix_partner_commission_entries_tenant_product",
]

PY_COMPILE_FILES = [
    "app.py",
    "config.py",
    "utils/field_validators.py",
    "services/backup_service.py",
    "tools/qa/predeploy_check.py",
    "tools/qa/backup_restore_check.py",
    "tools/qa/gl_remediation_verify.py",
    "tools/qa/null_column_audit.py",
]

GL_DUAL_SIDE_THRESHOLD = 0.01

LEGACY_GLOBAL_UNIQUE_INDEXES = (
    "ix_products_sku",
    "ix_products_barcode",
    "ix_product_categories_name",
    "ix_sales_sale_number",
    "ix_purchases_purchase_number",
    "ix_payments_payment_number",
    "ix_cheques_cheque_number",
)

REQUIRED_PER_TENANT_UNIQUE_INDEXES = (
    "uq_products_tenant_sku",
    "uq_products_tenant_barcode",
    "uq_product_categories_tenant_name",
    "uq_branches_tenant_name",
    "uq_branches_tenant_code",
    "uq_warehouses_tenant_name",
    "uq_warehouses_tenant_code",
    "uq_sales_tenant_sale_number",
    "uq_purchases_tenant_purchase_number",
    "uq_payments_tenant_payment_number",
    "uq_cheques_tenant_cheque_number",
)

TENANT_NOT_NULL_TABLES = [
    "branches", "products", "product_categories", "product_partners",
    "customers", "suppliers", "sales", "sale_lines", "purchases", "purchase_lines",
    "payments", "expenses", "warehouses", "stock_movements",
    "gl_accounts", "gl_journal_entries", "gl_journal_lines",
    "partner_commission_entries", "employees", "salary_advances", "payroll_transactions",
    "tenant_stores", "shop_customer_accounts", "store_coupons", "invoice_settings",
]

PHONE_VARCHAR50_COLUMNS = (
    ("customers", "phone"),
    ("users", "phone"),
    ("suppliers", "phone"),
    ("branches", "phone"),
    ("employees", "phone"),
)

STAGED_FORBIDDEN_PATTERNS = (
    ".env",
    "null_column_audit_",
    ".json",
    ".csv",
    "ai_knowledge/memory/",
    "episodic_memory.json",
    "security-reports/",
    ".sql",
)


@dataclass
class Section:
    name: str
    status: str  # PASS | WARN | FAIL
    detail: str = ""


@dataclass
class Report:
    sections: list[Section] = field(default_factory=list)
    failed: bool = False

    def add(self, name: str, status: str, detail: str = "") -> None:
        self.sections.append(Section(name, status, detail))
        if status == "FAIL":
            self.failed = True

    @property
    def overall(self) -> str:
        if self.failed:
            return "FAIL"
        if any(s.status == "WARN" for s in self.sections):
            return "PASS_WITH_WARNINGS"
        return "PASS"


def _env() -> dict:
    env = os.environ.copy()
    env.setdefault("SKIP_SYSTEM_INTEGRITY", "1")
    env.setdefault("FLASK_APP", "app.py")
    return env


def _run(cmd: list[str], *, cwd: str | None = None, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=cwd or ROOT,
        env=_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def check_py_compile(report: Report) -> None:
    failed = []
    for rel in PY_COMPILE_FILES:
        path = os.path.join(ROOT, rel.replace("/", os.sep))
        r = _run([sys.executable, "-m", "py_compile", path])
        if r.returncode != 0:
            failed.append(rel)
    if failed:
        report.add("App: py_compile", "FAIL", ", ".join(failed))
    else:
        report.add("App: py_compile", "PASS", f"{len(PY_COMPILE_FILES)} files")


def check_create_app(report: Report) -> None:
    code = (
        "import os; os.environ.setdefault('SKIP_SYSTEM_INTEGRITY','1'); "
        "from app import create_app; create_app(); print('create_app OK')"
    )
    r = _run([sys.executable, "-c", code])
    if r.returncode != 0:
        report.add("App: create_app", "FAIL", (r.stderr or r.stdout)[-500:])
    else:
        report.add("App: create_app", "PASS", "OK")


def check_migrations(report: Report) -> None:
    heads = _run([sys.executable, "-m", "flask", "db", "heads"])
    current = _run([sys.executable, "-m", "flask", "db", "current"])
    if heads.returncode != 0 or current.returncode != 0:
        report.add("App: migrations", "FAIL", (heads.stderr or current.stderr or "")[-400:])
        return
    head_lines = [
        ln.strip()
        for ln in (heads.stdout or "").splitlines()
        if "(head)" in ln.lower()
    ]
    if len(head_lines) != 1:
        report.add("App: migrations", "FAIL", f"multiple heads: {head_lines}")
        return
    head_rev = head_lines[0].split()[0] if head_lines else ""
    cur_out = current.stdout or ""
    if head_rev and head_rev in cur_out:
        report.add("App: migrations", "PASS", f"current matches head {head_rev}")
    else:
        report.add(
            "App: migrations",
            "FAIL",
            f"head={head_lines!r} current={cur_out!r}",
        )


def check_pip_audit(report: Report) -> None:
    r = _run(
        [sys.executable, "-m", "pip_audit", "-r", "requirements.txt", "--progress-spinner", "off"],
        timeout=300,
    )
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0 and "No known vulnerabilities" not in out:
        report.add("App: pip_audit", "FAIL", out[-400:])
    else:
        report.add("App: pip_audit", "PASS", "clean")


def check_gl_remediation(report: Report) -> None:
    script = os.path.join(ROOT, "tools", "qa", "gl_remediation_verify.py")
    r = _run([sys.executable, script])
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0:
        report.add("DB: gl_remediation_verify", "FAIL", out[-600:])
    elif "ALL_OK_WITH_WARNINGS" in out:
        report.add("DB: gl_remediation_verify", "WARN", "critical OK, operational warnings")
    else:
        report.add("DB: gl_remediation_verify", "PASS", "ALL_OK")


def check_null_audit(report: Report) -> None:
    script = os.path.join(ROOT, "tools", "qa", "null_column_audit.py")
    r = _run([sys.executable, script], timeout=120)
    err = r.stderr or ""
    out = r.stdout or ""
    if r.returncode != 0:
        report.add("DB: null_column_audit", "FAIL", (out + err)[-600:])
    elif "OK_WITH_WARNINGS" in err or "OK_WITH_WARNINGS" in out:
        report.add("DB: null_column_audit", "WARN", "gate OK with warnings")
    else:
        report.add("DB: null_column_audit", "PASS", "gate OK")


def check_required_indexes(report: Report) -> None:
    from dotenv import load_dotenv
    from sqlalchemy import create_engine, text

    load_dotenv(os.path.join(ROOT, ".env"))
    url = os.environ.get("DATABASE_URL")
    if not url:
        report.add("DB: required indexes", "FAIL", "DATABASE_URL not set")
        return
    engine = create_engine(url)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = 'public' AND indexname = ANY(:names)"
            ),
            {"names": REQUIRED_INDEXES},
        ).fetchall()
    found = {r[0] for r in rows}
    missing = [n for n in REQUIRED_INDEXES if n not in found]
    if missing:
        report.add("DB: required indexes", "FAIL", f"missing: {missing}")
    else:
        report.add("DB: required indexes", "PASS", f"{len(REQUIRED_INDEXES)} present")


def check_uat(report: Report) -> None:
    script = os.path.join(ROOT, "tools", "qa", "uat_operational_check.py")
    if not os.path.isfile(script):
        report.add("UAT", "FAIL", "uat_operational_check.py not found")
        return
    r = _run([sys.executable, script], timeout=600)
    out = (r.stdout or "") + (r.stderr or "")
    if "59/59" in out and r.returncode == 0:
        report.add("UAT", "PASS", "59/59")
    elif "59/59" in out:
        report.add("UAT", "WARN", "59/59 but non-zero exit")
    else:
        report.add("UAT", "FAIL", out[-800:])


def check_field_quality(report: Report) -> None:
    from dotenv import load_dotenv
    from sqlalchemy import create_engine, text

    load_dotenv(os.path.join(ROOT, ".env"))
    url = os.environ.get("DATABASE_URL")
    if not url:
        report.add("Field quality", "FAIL", "DATABASE_URL not set")
        return

    engine = create_engine(url)
    fails: list[str] = []
    warns: list[str] = []

    with engine.connect() as conn:
        def scalar(sql: str) -> int:
            return int(conn.execute(text(sql)).scalar() or 0)

        def table_exists(table: str) -> bool:
            return bool(
                conn.execute(
                    text(
                        "SELECT 1 FROM information_schema.tables "
                        "WHERE table_schema='public' AND table_name=:t"
                    ),
                    {"t": table},
                ).scalar()
            )

        if table_exists("products"):
            if scalar("SELECT COUNT(*) FROM products WHERE has_serial_number IS NULL") > 0:
                fails.append("products.has_serial_number NULL rows")

        if table_exists("donations"):
            if scalar("SELECT COUNT(*) FROM donations WHERE gl_posted IS NULL") > 0:
                fails.append("donations.gl_posted NULL rows")

        for table, col in PHONE_VARCHAR50_COLUMNS:
            if not table_exists(table):
                warns.append(f"missing table {table}")
                continue
            row = conn.execute(
                text(
                    "SELECT character_maximum_length FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name=:t AND column_name=:c"
                ),
                {"t": table, "c": col},
            ).fetchone()
            if not row or row[0] != 50:
                fails.append(f"{table}.{col} length={row[0] if row else 'missing'} (expected 50)")

        if scalar(
            "SELECT COUNT(*) FROM sales WHERE currency IS NOT NULL "
            "AND LENGTH(TRIM(currency)) <> 3"
        ):
            fails.append("sales invalid currency length")

        if table_exists("products") and scalar(
            "SELECT COUNT(*) FROM products WHERE sku IS NOT NULL AND TRIM(sku) = ''"
        ):
            fails.append("products empty SKU strings")

        dual_count = scalar(
            "SELECT COUNT(*) FROM gl_journal_lines WHERE debit > 0 AND credit > 0"
        )
        if dual_count:
            fails.append(f"GL dual-side lines count={dual_count}")

        unbalanced = scalar(
            "SELECT COUNT(*) FROM gl_journal_entries "
            "WHERE ABS(COALESCE(total_debit,0)-COALESCE(total_credit,0)) > 0.001"
        )
        if unbalanced:
            fails.append(f"unbalanced journal entries={unbalanced}")

        legacy_pt = scalar(
            "SELECT COUNT(*) FROM payments WHERE payment_type = 'sale'"
        )
        if legacy_pt:
            fails.append(f"payments.payment_type legacy 'sale' rows={legacy_pt}")

        ref_lowercase = scalar(
            "SELECT COUNT(*) FROM gl_journal_entries "
            "WHERE reference_type = 'inventory_migration'"
        )
        if ref_lowercase:
            fails.append(f"gl_journal_entries.reference_type lowercase rows={ref_lowercase}")

        unknown_pt = conn.execute(
            text(
                "SELECT DISTINCT payment_type FROM payments "
                "WHERE payment_type IS NOT NULL AND payment_type NOT IN "
                "('sale', 'sale_payment', 'supplier_payment', 'bill_payment', "
                "'refund', 'customer_payment', 'manual')"
            )
        ).fetchall()
        if unknown_pt:
            fails.append(
                "unknown payment_type: "
                + ", ".join(r[0] for r in unknown_pt[:5])
            )

    if fails:
        report.add("Field quality", "FAIL", "; ".join(fails))
    elif warns:
        report.add("Field quality", "WARN", "; ".join(warns[:6]))
    else:
        report.add("Field quality", "PASS", "schema + data gates OK")


def check_schema_hardening(report: Report) -> None:
    from dotenv import load_dotenv
    from sqlalchemy import create_engine, text

    load_dotenv(os.path.join(ROOT, ".env"))
    url = os.environ.get("DATABASE_URL")
    if not url:
        report.add("Schema hardening", "FAIL", "DATABASE_URL not set")
        return

    engine = create_engine(url)
    fails: list[str] = []
    warns: list[str] = []

    with engine.connect() as conn:
        for idx in LEGACY_GLOBAL_UNIQUE_INDEXES:
            exists = conn.execute(
                text("SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname=:n"),
                {"n": idx},
            ).scalar()
            if exists:
                fails.append(f"legacy global index still present: {idx}")

        for idx in REQUIRED_PER_TENANT_UNIQUE_INDEXES:
            exists = conn.execute(
                text("SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname=:n"),
                {"n": idx},
            ).scalar()
            if not exists:
                fails.append(f"missing per-tenant index: {idx}")

        for table in TENANT_NOT_NULL_TABLES:
            row = conn.execute(
                text(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name=:t AND column_name='tenant_id'"
                ),
                {"t": table},
            ).fetchone()
            if not row:
                warns.append(f"{table}: no tenant_id column")
            elif row[0] == "YES":
                fails.append(f"{table}.tenant_id still nullable")

        active_inv = conn.execute(
            text(
                "SELECT COUNT(*) FROM invoice_settings "
                "WHERE is_active = true AND tenant_id IS NULL"
            )
        ).scalar()
        if active_inv:
            fails.append(f"active invoice_settings null tenant={active_inv}")

    if fails:
        report.add("Schema hardening", "FAIL", "; ".join(fails[:8]))
    elif warns:
        report.add("Schema hardening", "WARN", "; ".join(warns[:4]))
    else:
        report.add("Schema hardening", "PASS", "per-tenant unique + NOT NULL OK")


def _git_short_head() -> str:
    r = _run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT)
    if r.returncode == 0:
        return (r.stdout or "").strip()
    return ""


def _load_latest_restore_proof() -> dict | None:
    from services.backup_service import BackupService

    BackupService.initialize()
    marker = os.path.join(BackupService.BACKUP_DIR, ".latest_restore_proof.json")
    proof_path = None
    if os.path.isfile(marker):
        try:
            with open(marker, "r", encoding="utf-8") as f:
                meta = json.load(f)
            proof_path = os.path.join(BackupService.BACKUP_DIR, meta.get("proof_file", ""))
        except Exception:
            proof_path = None
    if not proof_path or not os.path.isfile(proof_path):
        proofs = sorted(
            glob.glob(os.path.join(BackupService.BACKUP_DIR, "*restore_proof.json")),
            key=os.path.getmtime,
            reverse=True,
        )
        proof_path = proofs[0] if proofs else None
    if not proof_path:
        return None
    try:
        with open(proof_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def check_backup_readiness(report: Report, profile: str) -> None:
    try:
        from services.backup_service import BackupService
    except Exception as e:
        report.add("Backup readiness", "FAIL", f"import backup_service: {e}")
        return

    BackupService.initialize()
    writable = os.path.isdir(BackupService.BACKUP_DIR) and os.access(
        BackupService.BACKUP_DIR, os.W_OK | os.X_OK
    )
    if not writable:
        report.add("Backup readiness", "FAIL", "instance/backups not writable")
        return

    tools = BackupService.pg_tools_status()
    backups = [b for b in BackupService.list_backups() if str(b.get("filename", "")).startswith("azad_backup_")]
    latest_age_hours = None
    if backups:
        try:
            from datetime import datetime, timezone

            dt_s = backups[0].get("datetime") or ""
            if dt_s:
                created = datetime.fromisoformat(dt_s.replace("Z", "+00:00"))
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                latest_age_hours = (
                    datetime.now(timezone.utc) - created
                ).total_seconds() / 3600.0
        except Exception:
            latest_age_hours = None

    fails: list[str] = []
    warns: list[str] = []

    if not tools.get("pg_dump"):
        msg = "pg_dump not available (set PG_DUMP_PATH)"
        if profile == "production-readiness":
            fails.append(msg)
        else:
            warns.append(msg)

    if not backups:
        if profile == "production-readiness":
            fails.append("no azad_backup_*.tar.gz found")
        else:
            warns.append("no modern backup yet")
    elif profile == "production-readiness" and latest_age_hours is not None and latest_age_hours > 168:
        warns.append(f"latest backup age {latest_age_hours:.0f}h (>7d)")

    if backups:
        latest_fn = backups[0]["filename"]
        v = BackupService.verify_backup(latest_fn)
        if not v.get("valid"):
            fails.append(f"latest backup verify failed: {latest_fn}")
        else:
            manifest = v.get("manifest") or {}
            m_commit = (manifest.get("git_commit") or "").strip()
            head = _git_short_head()
            if head and m_commit and m_commit != head:
                warns.append(f"manifest git_commit={m_commit} != HEAD={head}")

    proof = _load_latest_restore_proof()
    proof_ok = False
    tenant_proof_ok = False
    branch_store_warn = False
    if proof and proof.get("restore_success"):
        try:
            verified = proof.get("verified_at", "")
            if verified:
                dt = datetime.fromisoformat(verified.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                age_h = (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
                fresh = age_h <= 168
                proof_ok = fresh and proof.get("backup_scope") in (None, "system")
                tenant_proof_ok = fresh and proof.get("backup_scope") == "tenant"
                branch_store_warn = fresh and proof.get("backup_scope") in (
                    "branch",
                    "store",
                )
        except Exception:
            proof_ok = bool(
                proof.get("restore_success") and proof.get("backup_scope") in (None, "system")
            )
            tenant_proof_ok = bool(
                proof.get("restore_success") and proof.get("backup_scope") == "tenant"
            )

    proofs_dir = BackupService.BACKUP_DIR
    for pfile in glob.glob(os.path.join(proofs_dir, "*restore_proof.json")):
        try:
            with open(pfile, "r", encoding="utf-8") as f:
                p = json.load(f)
            if not p.get("restore_success"):
                continue
            verified = p.get("verified_at", "")
            if not verified:
                continue
            dt = datetime.fromisoformat(verified.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0 > 168:
                continue
            if p.get("backup_scope") == "tenant":
                tenant_proof_ok = True
            if p.get("backup_scope") in ("branch", "store"):
                branch_store_warn = True
            if p.get("backup_scope") in (None, "system"):
                proof_ok = True
        except Exception:
            pass

    if profile == "production-readiness":
        if not proof_ok:
            fails.append(
                "no recent system restore proof "
                "(backup_restore_check --scope system --restore-to-temp-local)"
            )
        if not tenant_proof_ok:
            fails.append(
                "no recent tenant restore proof "
                "(backup_restore_check --scope tenant --restore-to-temp-local)"
            )
    else:
        if not proof_ok:
            warns.append("no system restore proof yet")
        if not tenant_proof_ok:
            warns.append("no tenant restore proof yet")
        if not branch_store_warn:
            warns.append("no branch/store restore proof yet (optional)")

    if fails:
        report.add("Backup readiness", "FAIL", "; ".join(fails))
    elif warns:
        report.add("Backup readiness", "WARN", "; ".join(warns))
    else:
        detail = "pg_dump OK" if tools.get("pg_dump") else "tools OK"
        if backups:
            detail += f"; latest={backups[0].get('filename')}"
        if proof_ok:
            detail += "; restore_proof=PASS"
        report.add("Backup readiness", "PASS", detail)


def check_git_hygiene(report: Report) -> None:
    issues = []
    r = _run(["git", "status", "--porcelain"], cwd=ROOT)
    if r.returncode != 0:
        report.add("Git hygiene", "WARN", "git status failed")
        return
    for line in r.stdout.splitlines():
        path = line[3:].strip() if len(line) > 3 else line
        staged = line[:2]
        if path.startswith("??"):
            for pat in STAGED_FORBIDDEN_PATTERNS:
                if pat in path.replace("\\", "/"):
                    issues.append(f"untracked: {path}")
        if "A" in staged or "M" in staged[:2]:
            for pat in STAGED_FORBIDDEN_PATTERNS:
                if pat in path.replace("\\", "/"):
                    issues.append(f"staged: {path}")
    tracked_memory = _run(
        ["git", "ls-files", "ai_knowledge/memory/"],
        cwd=ROOT,
    )
    mem_out = tracked_memory.stdout or ""
    if mem_out.strip():
        for ln in mem_out.strip().splitlines():
            if ln.endswith(".json") and not ln.endswith(".example.json"):
                issues.append(f"tracked: {ln}")
    if issues:
        report.add("Git hygiene", "FAIL", "; ".join(issues[:5]))
    else:
        report.add("Git hygiene", "PASS", "no forbidden staged/untracked patterns")


def print_report(report: Report, profile: str) -> None:
    print("=" * 72)
    print(f"PREDEPLOY CHECK — profile={profile}")
    print("=" * 72)
    for s in report.sections:
        print(f"  [{s.status:4}] {s.name}")
        if s.detail:
            print(f"         {s.detail}")
    print("-" * 72)
    print(f"OVERALL: {report.overall}")
    print("=" * 72)


def main() -> int:
    parser = argparse.ArgumentParser(description="Unified pre-deploy QA gate")
    parser.add_argument(
        "--profile",
        default="local",
        choices=("local", "production-readiness"),
        help="Check profile (same checks for now)",
    )
    parser.add_argument("--skip-uat", action="store_true", help="Skip UAT (faster)")
    parser.add_argument(
        "--database-url",
        default="",
        help="Override DATABASE_URL for DB checks only (restore proof)",
    )
    args = parser.parse_args()

    from dotenv import load_dotenv

    load_dotenv(os.path.join(ROOT, ".env"))
    if args.database_url:
        os.environ["DATABASE_URL"] = args.database_url.strip()
        os.environ["SQLALCHEMY_DATABASE_URI"] = args.database_url.strip()

    report = Report()
    check_py_compile(report)
    check_create_app(report)
    check_migrations(report)
    check_pip_audit(report)
    check_gl_remediation(report)
    check_null_audit(report)
    check_required_indexes(report)
    check_field_quality(report)
    check_schema_hardening(report)
    check_backup_readiness(report, args.profile)
    if not args.skip_uat:
        check_uat(report)
    check_git_hygiene(report)

    print_report(report, args.profile)
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
