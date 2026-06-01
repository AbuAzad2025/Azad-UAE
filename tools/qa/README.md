# QA / UAT tools (development only)

Scripts in this folder are **manual QA and UAT harnesses** for [Azad-UAE](https://github.com/AbuAzad2025/Azad-UAE). They are not part of the production application and are not run in deployment pipelines by default.

## Important

- **Do not run against production databases.** Use a local or staging copy with test tenants and disposable data.
- **Run from the repository root** so `.env` resolves correctly (scripts call `load_dotenv(".env")` relative to the current working directory).
- Some checks **create temporary records** (products, customers, storefront orders, shop accounts) tagged with `[UAT-TEST]` or `[TEST-STORE]` and attempt cleanup afterward. Review output if a run fails mid-way.
- Test shop accounts use a **fixed dev-only password** for accounts created during storefront checks — not production credentials.

## Official pre-deploy command (one gate)

From the repository root, with venv active and `.env` pointing at a **non-production** database:

```bash
python tools/qa/predeploy_check.py --profile local
```

This runs (in order): `py_compile`, `create_app`, migration head/current, `pip_audit`, `gl_remediation_verify`, `null_column_audit`, field/schema gates, **backup readiness**, `uat_operational_check`, and git hygiene checks.

Exit `0` = **PASS** or **PASS_WITH_WARNINGS** (operational warnings such as backup tables or test tenants are OK for dev/staging).

Exit `1` = **FAIL** on any critical item (DB integrity, UAT, missing indexes, migration mismatch, secrets staged, etc.).

For faster iteration without UAT: `python tools/qa/predeploy_check.py --profile local --skip-uat`

`--profile production-readiness`: missing `pg_dump` or no recent `azad_backup_*.tar.gz` → **FAIL** (local profile → **WARN**).

## Backup / restore QA

```bash
python tools/qa/backup_restore_check.py --verify-tools
python tools/qa/backup_restore_check.py --scope system --create-and-verify --restore-to-temp-local
python tools/qa/backup_restore_check.py --scope tenant --tenant-id 1 --create-and-verify --restore-to-temp-local
python tools/qa/backup_restore_check.py --scope tenant --tenant-id 1 --create-and-verify --restore-to-temp-local --restore-as-new-tenant
python tools/qa/backup_restore_check.py --scope branch --tenant-id 1 --branch-id 1 --create-and-verify --restore-to-temp-local
python tools/qa/backup_restore_check.py --scope store --tenant-id 1 --with-temp-source-store --create-and-verify --restore-to-temp-local
# Or explicit target URL (must differ from DATABASE_URL):
python tools/qa/backup_restore_check.py --restore-to-target
```

Scoped archives: `data/*.jsonl`, `uploads.tar.gz`, `manifest.json`, `checksums.sha256` (system also includes `db.dump`).

Writes `instance/backups/*.restore_proof.json` (gitignored). `production-readiness` requires recent **system** and **tenant** restore proofs; branch/store proofs are optional (WARN if missing on local profile).

Never restore onto the live dev/prod DB from this repo without a separate empty database URL.

Individual scripts below remain available for debugging; you do not need to run them separately before deploy if `predeploy_check` passes.

## Current verification status

| Check | Result |
|-------|--------|
| Unified gate (`predeploy_check.py`) | **Use before every deploy** |
| UAT operational (`uat_operational_check.py`) | **59/59 PASS** |
| pip_audit | **Clean** |
| create_app | **OK** |
| Performance indexes round 1 | **Migration `perf_idx_round1_001`** |

## Field Quality Round 1 (in `predeploy_check`)

- Phone columns widened to `varchar(50)` (customers, users, suppliers, branches, employees)
- Boolean drift: `products.has_serial_number`, `donations.gl_posted` NOT NULL + default false
- Service/form validation: currency ISO-3, phone normalize, canonical payment types, GL single-sided new lines
- Field quality section: PASS/FAIL/WARN (GL dual-side historical ids 721/995/1405 = WARN only)

## Production schema hardening (`prod_schema_hardening_001`)

- Per-tenant UNIQUE on SKU, sale/payment numbers, branches, warehouses, etc.
- `tenant_id` NOT NULL on operational tables (not `users` — global developer allowed)
- GL dual-side historical lines normalized; CHECK on single-sided GL amounts
- `predeploy_check` **FAIL** if legacy global unique indexes return or `tenant_id` becomes nullable again

## Deferred (not in this gate)

- Per-tenant UNIQUE on SKU / sale_number / warehouse name (business decision)
- NOT NULL `tenant_id` migrations (bulk)
- `pg_trgm` / GIN search indexes (Round 2)
- `before_flush` tenant guard
- Status CHECK constraints in DB
- Test tenants: operational decision at production cutover (see `DEPLOYMENT_PYTHONANYWHERE.md`)

## Scripts

| File | Purpose |
|------|---------|
| **`predeploy_check.py`** | **Unified pre-deploy gate** (migrations, DB, UAT, indexes, pip, git) |
| `gl_remediation_verify.py` | GL + critical tenant NULL checks |
| `null_column_audit.py` | Broader NULL column inventory (writes gitignored JSON) |
| `uat_operational_check.py` | Broad ERP UAT: login, permissions, CRUD smoke on tenant 2, reports, ledger, AI, GraphQL |
| `storefront_isolation_check.py` | Multi-tenant storefront catalog, cart, checkout, and admin isolation |
| `storefront_verify_cleanup_check.py` | Storefront verification suite plus `[TEST-STORE]` cleanup and post-cleanup assertions |

Original copies may remain under `tools/` with `*_test.py` names for local use; names here avoid that suffix so they can be tracked in git.

## Manual pre-deploy sequence (optional — superseded by `predeploy_check.py`)

```bash
python tools/qa/predeploy_check.py --profile local
```

Or run components individually:

Optional one-time remediation (only with backup + approval):

```bash
python tools/qa/invoice_settings_inactive_null_cleanup.py
```

**Do not run remediation or audits on production** without a full `pg_dump` backup and explicit sign-off.

### PASS / WARN / FAIL

| Tool | Exit 0 | Exit 1 |
|------|--------|--------|
| `gl_remediation_verify.py` | All **critical** checks = 0; no company user with NULL `tenant_id` | GL/tenant NULL/test leftovers, or non-global user with NULL tenant |
| `null_column_audit.py` | Same critical gates | Same |
| `uat_operational_check.py` | 59/59 tests | Any failure |

**WARN (exit 0):** backup tables present, test tenants `t-aed`/`t-usd`/`t-ils` active, global `developer` user with NULL `tenant_id` (e.g. `azad`).

**FAIL:** any critical `tenant_id` NULL on operational tables, GL cross-tenant, active `invoice_settings` with NULL tenant, UAT/[TEST-STORE] leftovers, or manager/seller without tenant.

Audit JSON/CSV under `tools/qa/null_column_audit_*` are **gitignored** — do not commit them.

## Suggested commands

From the project root, with venv active and `.env` pointing at **dev/staging**:

```bash
python tools/qa/uat_operational_check.py
python tools/qa/storefront_isolation_check.py
python tools/qa/storefront_verify_cleanup_check.py
```

Exit codes: `0` success, non-zero on failures (see script output).

## Prerequisites

- Application dependencies installed (`requirements.txt` in the main project).
- Database seeded with expected tenants (e.g. 2 and 4), users referenced in the UAT script, and product IDs used by storefront checks (see script constants).
- The UAT operational script may set `SKIP_SYSTEM_INTEGRITY=1` automatically when needed — **never** set this manually in production.

---

© 2025 Azad Smart Systems — development tools only; All Rights Reserved.
