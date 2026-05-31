# QA / UAT tools (development only)

Scripts in this folder are **manual QA and UAT harnesses** for [Azad-UAE](https://github.com/AbuAzad2025/Azad-UAE). They are not part of the production application and are not run in deployment pipelines by default.

## Important

- **Do not run against production databases.** Use a local or staging copy with test tenants and disposable data.
- **Run from the repository root** so `.env` resolves correctly (scripts call `load_dotenv(".env")` relative to the current working directory).
- Some checks **create temporary records** (products, customers, storefront orders, shop accounts) tagged with `[UAT-TEST]` or `[TEST-STORE]` and attempt cleanup afterward. Review output if a run fails mid-way.
- Test shop accounts use a **fixed dev-only password** for accounts created during storefront checks — not production credentials.

## Current verification status

| Check | Result |
|-------|--------|
| UAT operational (`uat_operational_check.py`) | **59/59 PASS** |
| pip_audit | **Clean** |
| create_app | **OK** |
| Tenant isolation | **Tested** |
| Storefront isolation | **Tested** |

## Scripts

| File | Purpose |
|------|---------|
| `uat_operational_check.py` | Broad ERP UAT: login, permissions, CRUD smoke on tenant 2, reports, ledger, AI, GraphQL |
| `storefront_isolation_check.py` | Multi-tenant storefront catalog, cart, checkout, and admin isolation |
| `storefront_verify_cleanup_check.py` | Storefront verification suite plus `[TEST-STORE]` cleanup and post-cleanup assertions |

Original copies may remain under `tools/` with `*_test.py` names for local use; names here avoid that suffix so they can be tracked in git.

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
