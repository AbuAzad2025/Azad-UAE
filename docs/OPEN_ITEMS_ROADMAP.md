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
- **Status:** ✅ **DONE**
- **Effort:** 1-2 hours cleanup + 5 min CI fix
- **Owner:** Developer
- **Done:** `.flake8` config created (ignore E301,E302,E704,W293,W391,W503; max-line-length=120); `continue-on-error: true` removed from flake8 step in CI; 16 tests in `test_flake8_config.py`

---

### A3. Move SECRET_KEY & CARD_ENCRYPTION_KEY Generation Out of Config Class
- **Status:** ✅ **DONE**
- **Effort:** 1 hour
- **Owner:** Developer
- **Done:** `utils/bootstrap_keys.py` created; `config.py` I/O removed; `app.py` calls `bootstrap_keys(app, config.instance_dir)`

---

## Phase B: Root Architecture Cleanup (🟡)

### B1. Split Blueprint Registration from app.py
- **Status:** ✅ **DONE**
- **Effort:** 2 hours
- **Done:** `bootstrap/blueprints.py` created with `_import_bp`, `_make_ai_fallback`, `register_blueprints`; `app.py` reduced from ~941 to ~688 lines; all 38 blueprints registered via `register_blueprints(app)`; AI fallback preserved; 11 tests in `test_bootstrap_blueprints.py`

### B2. Extract logging_setup + compat_patches from extensions.py
- **Status:** ✅ **DONE**
- **Effort:** 2 hours
- **Done:** `utils/logging_setup.py` + `utils/compat_patches.py` created; `extensions.py` reduced from 255 to 98 lines; `app.py` imports compat_patches before extensions; 340 tests pass

### B3. Remove _exempt_super() Hook or Implement Real Policy
- **Status:** ✅ **DONE**
- **Effort:** 15 minutes
- **Done:** Removed dead `@limiter.request_filter` returning `False` always; +14 tests in `test_extensions.py`

### B4. Refactor nowpayments_config.py into Provider Module
- **Status:** ✅ **DONE**
- **Effort:** 2 hours
- **Done:** `services/payments/nowpayments_provider.py` created with `NowPaymentsProvider` class; `nowpayments_config.py` deleted; `NOWPaymentsService` and `utils/nowpayments_ipn.py` migrated; 13 tests in `test_nowpayments_provider.py`

---

## Phase C: Security & Polish (🟡)

### C1. CDN SRI Hash Generation
- **Status:** ✅ **DONE**
- **Effort:** 1 hour
- **Done:** `tools/generate_sri.py` created; SRI hashes added to 39 templates; `integrity` + `crossorigin="anonymous"` on all CDN resources; 9 tests in `test_sri.py`

### C2. Session Security Hardening
- **Status:** ✅ **DONE**
- **Effort:** 30 minutes
- **Done:** `SESSION_COOKIE_SAMESITE="Lax"` in Config; `SESSION_COOKIE_SECURE = not DEBUG`; `REMEMBER_COOKIE_HTTPONLY/SECURE/SAMESITE` set; `utils/session_security.py` with `rotate_session()` created; called after login (`auth.py`) and after password change (`main.py`); 7 tests in `test_session_security.py`; production sanity asserts `SESSION_COOKIE_SECURE` is True

### C3. Permission Consistency Audit (Phase 7.5c)
- **Status:** ⏸️ Deferred
- **Effort:** 4 hours
- **Scope:** Full 274-template audit against 40 route files; low risk given backend guards

---

## Phase D: Brand & Features (🟢)

### D1. Retail / POS Feature Gap Analysis
- **Status:** ✅ **DONE**
- **Effort:** 1 day assessment
- **Done:** Touch-friendly CSS (48px inputs, 52px tablet buttons), KPI sizing, scan-focus indicator, cash button styling; POS enable guard (`SystemSettings.enable_pos` + `Tenant.enable_pos` flags) with backend `_require_pos_enabled()` and frontend sidebar conditional link; `test_pos_helpers.py` (17 tests), `test_pos_routes.py` (25 tests), `test_pos_routes_extra.py` (14 tests); 56 POS tests total

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
| B1 | Blueprint split | ✅ **DONE** | Jun 8 | Jun 8 | `bootstrap/blueprints.py` created; `app.py` reduced from ~941 to ~688 lines; all 38 blueprints registered via `register_blueprints(app)`; AI fallback preserved; 11 tests in `test_bootstrap_blueprints.py` |
| B2 | logging_setup extract | ✅ **DONE** | Jun 7 | Jun 7 | `utils/logging_setup.py` + `utils/compat_patches.py` created; `extensions.py` reduced from 255 to 98 lines; `app.py` imports compat_patches before extensions; 340 tests pass |
| B3 | _exempt_super cleanup | ✅ **DONE** | Jun 7 | Jun 7 | Removed dead `@limiter.request_filter` returning `False` always; +14 tests in `test_extensions.py` |
| B4 | NowPayments provider | ✅ **DONE** | Jun 8 | Jun 8 | `services/payments/nowpayments_provider.py` created with `NowPaymentsProvider` class; `nowpayments_config.py` deleted; `NOWPaymentsService` and `utils/nowpayments_ipn.py` migrated; 13 tests in `test_nowpayments_provider.py` |
| C1 | CDN SRI | ✅ **DONE** | Jun 7 | Jun 7 | `tools/generate_sri.py` created; SRI hashes added to 39 templates; `integrity` + `crossorigin="anonymous"` on all CDN resources; 9 tests |
| C2 | Session security | ✅ **DONE** | Jun 7 | Jun 7 | `SESSION_COOKIE_SAMESITE` already in Config; `utils/session_security.py` with `rotate_session()` created; called after login (`auth.py`) and after password change (`main.py`); 7 tests; 347 total pass |
| D1 | POS supermarket enhancements | ✅ **DONE** | Jun 7 | Jun 7 | Touch-friendly CSS (48px inputs, 52px tablet buttons), KPI sizing, scan-focus indicator, cash button styling; POS enable guard (`SystemSettings` + `Tenant` flags); `test_pos_helpers.py` (17 tests), `test_pos_routes.py` (25 tests); 404 total pass |

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
*Last updated: June 8, 2026*
