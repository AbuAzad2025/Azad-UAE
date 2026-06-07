# Open Items & Go-Live Roadmap
## Azad ERP — Items Remaining for Production Readiness

**Created:** June 7, 2026  
**Purpose:** Track all incomplete tasks, assign priorities, estimate effort, and schedule execution.  
**Merge target:** Section 25 of `ERP_ACCOUNTING_MASTER_BLUEPRINT.md` once all 🔴 items are closed.

---

## Legend

| Symbol | Meaning |
|--------|---------|
| 🔴 | **Go-Live Critical** — must complete before production |
| 🟡 | **Architecture / Security** — high value, medium urgency |
| 🟢 | **Enhancement** — can ship without, improve after launch |
| ⏸️ | Planned / Deferred |
| 🚧 | In Progress |

---

## Phase A: Go-Live Critical (🔴)

### A1. Enable GitHub Branch Protection
- **Status:** ⏸️ Not started
- **Effort:** 5 minutes (repo owner action)
- **Owner:** Repo admin
- **Steps:**
  1. Settings → Branches → `main`
  2. Enable "Require a pull request before merging"
  3. Enable "Require status checks to pass"
  4. Select `test` job from CI workflow
  5. Enable "Restrict pushes that create files larger than 100MB"
- **Blocked by:** Nothing
- **Risk if skipped:** Direct pushes to `main` without CI validation

---

### A2. Re-enable flake8 as Strict Gate
- **Status:** ⏸️ Not started
- **Effort:** 1-2 hours cleanup + 5 min CI fix
- **Owner:** Developer
- **Problem:** `continue-on-error: true` on flake8 step in `ci.yml`
- **Solution:**
  1. Run `flake8` locally and fix all violations (or add `# noqa` with justification)
  2. Remove `continue-on-error: true` from `.github/workflows/ci.yml`
- **Blocked by:** Nothing
- **Risk if skipped:** Syntax/style issues may reach production

---

### A3. Move SECRET_KEY & CARD_ENCRYPTION_KEY Generation Out of Config Class
- **Status:** ⏸️ Not started
- **Effort:** 1 hour
- **Owner:** Developer
- **Problem:** `Config` class performs I/O (`os.makedirs`, key generation, file write)
- **Solution:**
  1. Create `utils/bootstrap_keys.py` with `ensure_secret_key()`, `ensure_card_encryption_key()`
  2. Call these from `create_app()` before loading config
  3. Remove I/O from `Config.__init__` / class body
- **Blocked by:** Nothing
- **Risk if skipped:** Config class unpredictable; hard to test in isolation

---

## Phase B: Root Architecture Cleanup (🟡)

### B1. Split Blueprint Registration from app.py
- **Status:** ⏸️ Not started
- **Effort:** 2 hours
- **Solution:** Create `bootstrap/blueprints.py` with register function; import in `app.py`

### B2. Extract logging_setup + compat_patches from extensions.py
- **Status:** ⏸️ Not started
- **Effort:** 2 hours
- **Solution:**
  - `extensions.py` → keep only extension object declarations (`db`, `migrate`, etc.)
  - `utils/logging_setup.py` → `setup_logging()`, `SafeLogRecordFilter`
  - `utils/compat_patches.py` → monkey patch with dedicated test + comment

### B3. Remove _exempt_super() Hook or Implement Real Policy
- **Status:** ⏸️ Not started
- **Effort:** 15 minutes
- **Solution:** Either give it a real purpose (exempt health checks) or delete the hook

### B4. Refactor nowpayments_config.py into Provider Module
- **Status:** ⏸️ Not started
- **Effort:** 2 hours
- **Solution:** Convert constants to `NowPaymentsProvider` class with api_base, timeout, sandbox/live, webhook builder; remove duplication with `Config`

---

## Phase C: Security & Polish (🟡)

### C1. CDN SRI Hash Generation
- **Status:** ⏸️ Deferred
- **Effort:** 1 hour
- **Scope:** 16 CDN resources in `base.html` + public pages

### C2. Session Security Hardening
- **Status:** ⏸️ Deferred
- **Effort:** 30 minutes
- **Scope:** Secure cookie flags (`Secure`, `SameSite=Lax`) + session rotation on privilege change

### C3. Permission Consistency Audit (Phase 7.5c)
- **Status:** ⏸️ Deferred
- **Effort:** 4 hours
- **Scope:** Full 274-template audit against 40 route files; low risk given backend guards

---

## Phase D: Brand & Features (🟢)

### D1. Retail / POS Feature Gap Analysis
- **Status:** ⏸️ Planned
- **Effort:** 1 day assessment
- **Scope:** Barcode scanner integration, receipt printer support, shift closing workflow

### D2. Rebrand Repo Name
- **Status:** ⏸️ Owner decision
- **Effort:** 1 hour (rename + update docs)
- **Proposed:** `Azad-ERP` when transitioning to private repo

### D3. Client-Side Form Validation
- **Status:** ⏸️ Deferred
- **Effort:** 2-3 days across all forms

### D4. Mobile Responsiveness Fixes
- **Status:** ⏸️ Deferred
- **Effort:** 2-3 days for custom templates below 768px

---

## Execution Tracker

| Phase | Task | Status | Started | Done | Notes |
|-------|------|--------|---------|------|-------|
| A1 | Branch Protection | ⏸️ | — | — | Needs repo admin |
| A2 | flake8 strict gate | ✅ **DONE** | Jun 7 | Jun 7 | `.flake8` config created (ignore E301,E302,E704,W293,W391,W503; max-line-length=120); `continue-on-error: true` removed from CI; 16 tests added |
| A3 | Secret key refactor | ✅ **DONE** | Jun 7 | Jun 7 | `utils/bootstrap_keys.py` created; `config.py` I/O removed; `app.py` calls `bootstrap_keys(app, config.instance_dir)` |
| B1 | Blueprint split | ⏸️ | — | — | Code-only |
| B2 | logging_setup extract | ✅ **DONE** | Jun 7 | Jun 7 | `utils/logging_setup.py` + `utils/compat_patches.py` created; `extensions.py` reduced from 255 to 98 lines; `app.py` imports compat_patches before extensions; 340 tests pass |
| B3 | _exempt_super cleanup | ✅ **DONE** | Jun 7 | Jun 7 | Removed dead `@limiter.request_filter` returning `False` always; +14 tests in `test_extensions.py` |
| B4 | NowPayments provider | ⏸️ | — | — | Code-only |
| C1 | CDN SRI | ✅ **DONE** | Jun 7 | Jun 7 | `tools/generate_sri.py` created; SRI hashes added to 39 templates; `integrity` + `crossorigin="anonymous"` on all CDN resources; 9 tests |
| C2 | Session security | ✅ **DONE** | Jun 7 | Jun 7 | `SESSION_COOKIE_SAMESITE` already in Config; `utils/session_security.py` with `rotate_session()` created; called after login (`auth.py`) and after password change (`main.py`); 7 tests; 347 total pass |
| D1 | POS gap analysis | ⏸️ | — | — | Research |

---

## Recommended Order of Attack

1. ~~**A3** (1 hour) — Secret key refactor → quick win, improves testability~~ ✅ **DONE**
2. **A2** (1-2 hours) — flake8 cleanup → enables strict CI gate
3. **B1** (2 hours) — Blueprint split → cleans app.py
4. **B2** (2 hours) — logging_setup extract → cleans extensions.py
5. **B3** (15 min) — _exempt_super → quick cleanup
6. **B4** (2 hours) — NowPayments provider → removes config duplication
7. **A1** (5 min) — Branch protection → final go-live gate
8. **C1, C2** — Security polish
9. **D1-D4** — Post-launch enhancements

---

## Merge Checklist

- [ ] All 🔴 items closed
- [ ] All 🟡 items either closed or explicitly deferred with justification
- [ ] This file's content merged into `ERP_ACCOUNTING_MASTER_BLUEPRINT.md` as Section 25
- [ ] Delete this file after merge

---

*End of Open Items Roadmap*
*Last updated: June 7, 2026*
