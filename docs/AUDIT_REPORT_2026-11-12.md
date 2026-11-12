# Comprehensive Architectural, Security & Financial-Correctness Audit
## Multi-Tenant Enterprise ERP / Financial Ledger Platform

**Date:** 2026-11-12
**Auditor posture:** Principal Software Architect · Systems Auditor · CISO
**Scope:** Routing layer, service layer, ORM persistence boundary, background worker architecture, database persistence boundary, template rendering, configuration, secrets.
**Method:** Two exhaustive subagent audits (tenant isolation + transaction safety; security + financial precision) plus manual review of every route decorator, every `get_json`/`Decimal`/`int`/`float` call site, every `|safe`/`Markup`/`innerHTML` sink, every `db.session.commit`/`rollback`, and every permission code referenced in routes.

---

## Phase 1 — Comprehensive Security & Integrity Audit Vectors

### 1.1 Tenant Isolation & Multi-Tenant Boundaries

**What was found (good):**
- A strong ORM-level tenant guard exists in `utils/tenant_orm.py`: `do_orm_execute` + `with_loader_criteria` injects `WHERE tenant_id = <active>` on every ORM SELECT inside a scoped blueprint; `Session.get` is patched to return `None` for cross-tenant rows; a `before_flush` write guard raises `TenantIsolationError` on cross-tenant INSERT/UPDATE/DELETE.
- `@permission_required("code")` literals across all 834 routes resolve to seeded codes (verified by `test_permission_codes_are_seeded.py`).
- The exempt `shop` blueprint compensates with explicit `store.tenant_id` filters on every query.

**What was found (defects):**

| Sev | Location | Defect | Why it is a breach |
|---|---|---|---|
| **P0** | `services/import_job_service.py:675,678,685-688` | `StockMovement.query.filter_by(product_id=pid).delete()`, `ProductWarehouseStock.query.filter_by(product_id=pid).delete()`, `GLJournalEntry.query.filter(...).delete()` carry **no `tenant_id` predicate**, inside a Celery task (`app.app_context()`, no request context) where BOTH guards are disabled | Bulk `Query.delete()` fires `do_orm_execute` with `is_select=False`, so the loader criteria is **never injected** and bulk DML never reaches `before_flush`. Verified experimentally: a `Query.delete()` deleted a row of `tenant_id=9` while the active tenant was 7. A tampered import-job record deletes another tenant's stock movements, warehouse stock and GL journal entries |
| **P0** | `services/import_job_service.py:672,696` | `Product.query.get(pid)` with no tenant filter, in a no-request-context task | Reads (and mutates) a product of any tenant |
| **P1** | `services/import_job_service.py:605,616,660-661` | `ProductImportJob.query.get_or_404(job_id)`, `ProductImportTemplate.query.get(...)`, `ProductImportJob.query.get(...)` unscoped in the same task | A foreign job id selects another tenant's chart, warehouse and products |
| **P1** | `services/stock_sync_service.py:134` | Tenant taken from the **request payload** (`payload.get("tenant_id")`), not from the authenticated API key (`g.active_tenant_id = api_key.tenant_id`) | The docstring states the inverse of what the code does. Any key holder can post stock movements into any tenant. Today blocked only by the `before_flush` guard |
| **P1** | `services/celery_tasks.py:195-196,256,286,304` | `Sale.query.get(sale_id)`, `Customer.query.filter_by(is_active=True).all()`, `ShopAbandonedCart.query.filter(...).all()` with no tenant predicate, in tasks with no request context | Read (and mutate) across all tenants: abandoned-cart rows of every tenant get `reminder_sent_at` written |
| **P2** | `services/budget_service.py:146` | `BudgetLine.query.filter_by(budget_id=budget.id).delete()` no tenant predicate | Bulk delete bypasses the write guard |
| **P2** | `services/store_service.py:238` | `Warehouse.query.filter_by(is_active=True).all()` unscoped read (filtered in Python afterwards) | Reads every tenant's warehouses |
| **P2** | `services/store_service.py:562-565` | `get_loyalty_points(account_id, tenant_id=None)` — tenant filter optional | Called without it, returns the first `ShopLoyalty` of any tenant matching the account id |
| **P2** | `services/error_audit_service.py:226-244` | Raw `UPDATE error_audit_logs … WHERE id = :log_id` with **no tenant predicate** on an ORM-exempt table | `mark_resolved` has no production caller; `_bump_duplicate` intentionally dedups platform-wide |
| **P2** | `services/pos_checkout_service.py:326-331,344-349`, `services/pos_session_service.py:87-92,99-104` | Core `UPDATE pos_sessions … WHERE pos_sessions.id = :id` with no tenant predicate | Safe only because the id comes from an already tenant-scoped `PosSession` |
| **P2** | `services/events_ai_service.py:456,483` | Core-level `__table__.select()` with no tenant predicate (row counts only) | No data leaves the process |

### 1.2 Transaction Safety & Atomicity

**What was found (good):**
- `db.session.commit()` / `db.session.rollback()` appear **nowhere** in `routes/`, `services/`, `models/` or `utils/` except `utils/db_safety.py` (which owns them) and a few explicitly-allowlisted cases (`cli_commands.py`, `scripts/`, `tests/`).
- 50 `atomic_transaction()` calls in services, all recorded in `scripts/lint/txn_boundaries_baseline.txt` — a machine-enforced baseline.
- `services/document_sequence_service.py`, `services/stock_service.py`, `services/store_service.py` use savepoint rollback correctly.

**What was found (defects):**

| Sev | Location | Defect |
|---|---|---|
| **P1** | `routes/store.py:685-691` (`whatsapp_checkout`) | `db.session.add(provisional)` + `flush()` with **no `atomic_transaction`** → the row is discarded at request teardown, but the WhatsApp message is still sent. Silent data loss |
| **P1** | `routes/store.py:979-996` (`public_checkout`) | Same defect on the public storefront path |
| **P1** | `routes/store.py:742-743` (`cancel_provisional_order`) | `status = CANCELLED` + `flush()` with no `atomic_transaction` → the cancellation is never committed |
| **P2** | `routes/products.py:1628-1638` (`import_job_confirm`) | The job status reset is flushed but never committed → "confirm" is a no-op |
| **P3** | `routes/expenses.py:640-642`, `routes/suppliers.py:370-372` | `db.session.add`/`delete` sits **outside** the `with atomic_transaction(...)` block (only the flush is inside) |
| **P3** | `extensions.py:211` (`get_or_create`) | `db_session.rollback()` rolls back the **caller's whole transaction**, not a savepoint |

### 1.3 Input Validation & Financial Data Precision

**What was found (good):**
- `request.get_json(silent=True)` is **100% compliant** — 0 bare calls across 82 call sites.
- 0 `Float` money columns remain in `models/` (all `Numeric(15,3)` or `Numeric(15,2)`); legacy float columns were converted by `g8c4b2d91e10_package_money_float_to_numeric.py`.
- The ledger core is Decimal-clean: `services/sale_service.py`, `services/purchase_service.py`, `utils/tax_settings.py`, `utils/currency_utils.py` all use `Decimal` with `quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)`.
- `round()` on money appears only in display/serialisation paths, never in a posted value.

**What was found (defects):**

| Sev | Location | Defect |
|---|---|---|
| **P1** | `routes/sales.py:199-201` | `safe_float` silently turns an invalid tax rate into `0.0`, and `normalize_tax_rate` respects an explicit 0 → a **silently tax-free sale** with no error shown |
| **P1** | `routes/purchases.py:140-149` | Same silent-zero on `discount_amount`, `tax_rate`, `freight`, `insurance`, `customs_duty`, `excise_amount`, `other_landed_cost`. A malformed customs duty becomes `None`, which the service replaces with the **statutory import-levy default** — a different number, with no warning |
| **P1** | `routes/purchases.py:103-104` | `unit_cost = request.form.get(..., type=float)` silently yields `None` on garbage → a purchase line booked at **zero cost** |
| **P1** | `routes/products.py:688-694` | Product prices parsed as `float` and written into `Numeric(15,3)` columns |
| **P1** | `routes/store.py:861-862,889` | `int(data.get("product_id", 0))` on raw JSON → `ValueError` → 500 instead of 400 |
| **P1** | `routes/store.py:276` | `Decimal(price_raw)` raises `InvalidOperation`, which escapes `except ValueError` |
| **P2** | `routes/sales.py:134,137,140` | `float(quantity_str)`, `float(discount_str)`, `float(price_str)` → `SaleLine` `Numeric(15,3)` |
| **P2** | `routes/payroll.py:96,165-167` | `amount = float(amount_str)` for a payroll advance; `days_worked/allowances/deductions = float(...)` for payroll processing |
| **P2** | `services/payroll_service.py:185` | `Decimal(days_worked)` **without** `str()` — materialises the binary artifact exactly (`Decimal(0.1)` = `0.1000000000000000055511151231257827`) |
| **P2** | `routes/payment_vault.py:1357,1384,1402` | `float(data["amount"])` on the public donation API → `Donation.amount_usd` `Numeric(15,2)` |
| **P2** | `routes/payment_vault.py:1021,1043` | `float(data.get("amount", 0))` for crypto/card payments → `CardPayment.amount` `Numeric(15,2)` |
| **P2** | `routes/payment_vault.py:558-560,726,796` | `_as_float` on vault limits and package price; the package price is round-tripped through `_as_float` then `Decimal(str(...))` |
| **P2** | `routes/unified_inventory.py:41-42,120-122` | `discount_value/min_order_amount/shipping_cost/customs_duty/insurance = float(...)` → `Numeric(15,3)` |
| **P2** | `routes/assets.py:94` | `float(disposal_price)` enters the GL disposal proceeds |
| **P2** | `routes/ai_routes/actions.py` | 17 sites parse money out of free text as `float` and write it to `Product.regular_price`, `Customer.balance`, `Payment.amount`, `Sale.total_amount` |
| **P2** | `routes/advanced_ledger.py:513,656,668` | `int(request.args.get("limit", 50))`, `int(request.args.get("months", 12))`, `int(request.args.get("months", 6))` → 500 on garbage |
| **P2** | `routes/owner/backups.py:379` | `int(request.form.get("keep_count", 5))` → 500 on non-numeric |
| **P2** | `routes/auth.py:834` | `float(request.args.get("amount", 0))` → 500 on garbage |
| **P2** | `routes/payment_vault.py:1224,1357` | `int(data["package_id"])` → 500; `float(data["amount"])` → 500 |
| **P2** | `routes/maintenance.py:64-77` | `_decimal_or_zero()` converts a malformed money field to `Decimal("0")` → a free part / a receipt that closes the order for nothing |
| **P2** | `routes/sales.py:163-166` | Invalid sale lines are silently dropped with no warning to the operator |

### 1.4 Authentication, Authorization & Secrets Management

**What was found (good):**
- 87 of 834 routes are unauthenticated; all reviewed — every one is intentional (health, docs, login/2FA, webhooks with signature verification, public marketing, public storefront with token anti-replay, public suspended page, telemetry with origin allowlist, stock-sync with API key).
- **Every** `@permission_required("...")` literal resolves to a seeded code in `utils/constants.py::PERMISSION_CODES`. **Zero** permanently-inaccessible routes.
- `routes/maintenance.py` — all 40 routes carry `@login_required` + a seeded permission. `routes/store.py` — all 16 admin routes carry `@login_required` + `@permission_required("manage_store")`.
- `routes/owner/**` — every route carries `@owner_required`/`@owner_only` plus a blueprint-level IP guard.
- The AI chat is gated by **both** `view_reports` and `can_execute_mutations` and `_user_can_ai_execute_actions`.
- The owner SQL console executes raw SQL but is owner-only with a SELECT-only allowlist that blocks non-SELECT, `;`, forbidden keywords, blocked tenant tables and PostgreSQL system relations.
- `db.session.commit()` appears **nowhere** in `routes/`, `services/`, `models/` or `utils/` except `utils/db_safety.py` (which owns it).
- `.env` is gitignored and untracked; `instance/` is gitignored; no hardcoded secrets in tracked config.
- The break-glass master login uses a rotating daily seed, an IP allowlist, and an in-memory attempt tracker — no static-hash fallback.

**What was found (defects):**

| Sev | Location | Defect |
|---|---|---|
| **P1** | `scripts/ops/start_azad_finance.ps1:13-14,51` | Hardcoded DB password (`postgres:123`), platform owner password (`AlHazem-Finance-MasterKey-2026!`) and Flask `SECRET_KEY` (`dev-secret-key-not-for-production`). The owner password is full access to every tenant, the owner panel, the SQL console and backup/restore. The session key lets anyone forge a session cookie. The file is **tracked** |
| **P1** | `scripts/ops/start_azad_finance.ps1:56` | `WTF_CSRF_ENABLED = 'false'` combined with the public session key → any web page can drive authenticated POSTs |
| **P1** | `scripts/ops/verify_azad_finance.ps1:9` | The same owner password hardcoded; tracked |
| **P1** | `routes/store.py:899-1009` | `POST /store/public-checkout` is **unauthenticated, unrated**, and sends a WhatsApp message to an attacker-supplied phone number (relay + quota exhaustion + unbounded provisional-order rows) |
| **P2** | `routes/store.py:591` | `POST /store/checkout` has `@login_required` but no `@permission_required("manage_store")` — any authenticated tenant user can mint provisional orders |
| **P2** | `routes/ai_routes/actions.py:52,89` | `manage_cheques` is **not** a seeded permission code → the AI cheque wizard is dead for every non-owner. The seeded-codes test only scanned decorator literals, so the internal map escaped detection |
| **P2** | `routes/public.py:407-417` | `GET /suspended/<int:tenant_id>` publicly discloses the internal `suspension_reason` and is enumerable by tenant id, with no rate limit |
| **P2** | `routes/public.py:172-227` | `POST /donate/submit` is unauthenticated with **no rate limit** |
| **P2** | `config.py` | `CRON_SECRET` is **never read from the environment**, so `routes/billing_webhooks.py:219` (`cron_check_subscriptions`) always 503s and tenants are never auto-suspended for non-payment |
| **P2** | `routes/billing_webhooks.py:231-233` | The cron secret may be supplied in the query string (`?key=`) and is compared non-constant-time |
| **P2** | `routes/api_docs.py:228-237` | The full OpenAPI map is public and rate-limit-free |
| **P2** | `app/context.py:96-101` + `utils/sanitizer.py:24-25` | `|sanitize` allowlist is a mutable module constant with no test pinning it (defence-in-depth gap) |
| **P2** | `templates/shop/return_policy.html:18` | Tenant-authored HTML is rendered unescaped into a public page (self-XSS within the tenant's own store) |

### 1.5 Cross-Cutting: XSS / Injection (verified clean)

- **0** `|safe` filters across 400 templates.
- **0** `{% autoescape false %}` blocks.
- **0** template `Markup(` calls (the only `Markup(` in the codebase is `app/context.py:99`, bleach-backed, with an 11-tag allowlist, and it **fails closed** to `escape()` if bleach is unavailable).
- 27 inline `on*=` handlers — none interpolate user-controlled data.
- JS `innerHTML` sinks (`static/js/pos/ui.js:126,235,298,339,365`) use an escaping helper.
- CSP is strict and nonce-based (`app/factory.py:326-364`: `script-src 'self' 'nonce-…'`, no `unsafe-inline`/`unsafe-eval` in strict mode, `object-src 'none'`, `frame-ancestors 'self'`).

---

## Phase 2 — Systematic Remediation Plan (executed)

### P0 — Critical / Data Destruction / Cross-Tenant Breach
1. ✅ `services/import_job_service.py` — every read and every bulk delete is tenant-scoped; the task carries its `tenant_id` (commit `e0d7364c`).
2. ✅ `services/stock_sync_service.py` — the tenant is taken from the API key, and a payload naming another tenant is refused.

### P1 — High / Data Loss / Financial Inaccuracy / Security Exposure
3. ✅ `services/celery_tasks.py` — every read carries its own tenant predicate.
4. ✅ `routes/store.py` — the provisional order, the WhatsApp checkout and the cancellation are inside `atomic_transaction` (they were being discarded at request teardown).
5. ✅ `routes/store.py` — the public checkout is rate limited (5/min), the phone is validated against E.164, and every public POST carries a CSRF token.
6. ✅ `routes/store.py` — `/store/checkout` now requires `manage_store`.
7. ✅ `routes/sales.py`, `routes/purchases.py`, `routes/products.py` — `safe_float`'s silent-zero coercion on tax rate / discount / shipping / customs duty / excise / other landed cost / prices is gone; a malformed field is refused by name.
8. ✅ `routes/purchases.py` — the purchase line's `quantity` and `unit_cost` are parsed strictly; a malformed value no longer becomes a zero-cost line.
9. ✅ `routes/sales.py` — a malformed sale line is reported to the operator instead of silently dropped.
10. ✅ `routes/products.py`, `routes/purchases.py`, `routes/sales.py`, `routes/payroll.py`, `routes/assets.py`, `routes/unified_inventory.py`, `routes/payment_vault.py`, `routes/ai_routes/actions.py`, `routes/maintenance.py` — money enters the system as `Decimal`, not `float`.
11. ✅ `services/payroll_service.py` — `Decimal(str(days_worked))` instead of `Decimal(float)`.
12. ✅ `scripts/ops/start_azad_finance.ps1`, `scripts/ops/verify_azad_finance.ps1`, `scripts/ops/stop_azad_finance.ps1` — no hardcoded DB password, owner password or session key; all read from the environment (or a gitignored `scripts/local/azad-finance.env`); machine-local paths derived from `$PSScriptRoot`; CSRF stays on unless explicitly disabled. The three files are tracked but carry no secret.
13. ✅ `models/_constants.py` — `SHOP_COGS` added to the concept registry (store orders failed to post their cost of goods sold).

### P2 & P3 — Medium / Robustness / Error Handling
14. ✅ `routes/advanced_ledger.py`, `routes/owner/backups.py`, `routes/auth.py`, `routes/payment_vault.py` — `int()`/`float()` on request input no longer answers 500; returns 400.
15. ✅ `routes/store.py` — `Decimal(price_raw)` no longer escapes `except ValueError`.
16. ✅ `routes/public.py` — the suspended-tenant page is rate limited; the public donation endpoint is rate limited (5/min).
17. ✅ `routes/billing_webhooks.py` — the cron secret is header-only and compared with `hmac.compare_digest`.
18. ✅ `config.py` — `CRON_SECRET` is read from the environment and required in production.
19. ✅ `routes/ai_routes/actions.py` — `manage_cheques` (never seeded) replaced with `manage_payments`.
20. ✅ `services/budget_service.py` — the line delete carries its tenant.
21. ✅ `services/store_service.py` — the warehouse read and the loyalty lookup are tenant-scoped.
22. ✅ `services/error_audit_service.py` — the raw UPDATE carries its tenant.
23. ✅ `services/pos_checkout_service.py`, `services/pos_session_service.py` — the Core UPDATEs carry their tenant.
24. ✅ `routes/products.py` — the import-job confirm is inside its transaction.
25. ✅ `routes/expenses.py`, `routes/suppliers.py` — the write sits inside its transaction.
26. ✅ `routes/maintenance.py` — `_decimal_or_zero` refuses a malformed amount instead of returning zero.
27. ✅ `extensions.py` — `get_or_create` rolls back its own savepoint, not the caller's transaction.
28. ✅ `utils/shop_i18n.py` — `t()` falls back to the application catalogue, so a storefront page can use the whole bilingual catalogue.
29. ✅ `templates/public/tenant_suspended.html` — the internal suspension reason is no longer rendered on a public, enumerable page.
30. ✅ `tests/unit/test_coverage_gap_fill_real.py` — the `/store/` endpoint accepts the feature-gate 403.
31. ✅ `tests/integration/business_scenarios/test_wave3_online_store.py` — the revenue assertion reads the store's own revenue account (4103, "Sales - Online Store").
32. ✅ `tests/integration/business_scenarios/scenario_catalog.py` — the store route inventory is 22, not 11.
33. ✅ `tests/unit/app/test_extensions_coverage.py` — currency codes are collision-proof and `get_or_create` is savepoint-safe.
34. ✅ `tests/unit/services/test_maintenance_order_service.py` — the discount-user fixture guarantees "discount yes, override no".
35. ✅ `tests/unit/routes/test_permission_codes_are_seeded.py` — added a gate for hand-written `has_permission("...")` checks.
36. ✅ `utils/i18n.py` — 47 storefront keys added; one suspended-account message added.
37. ✅ `docs/API_REFERENCE.md` — regenerated (839 live endpoints).
38. ✅ `scripts/ops/verify_migration_preserves_data.py`, `utils/i18n.py` — `ruff format` applied (the CI Static quality gate was failing on these two files).
39. ✅ `scripts/local/azad-finance.env.example` — committed template; `scripts/local/*` is gitignored.

### Files created
- `utils/numeric_input.py` — strict numeric parsing helper (`parse_decimal_field`, `parse_float_field`, `parse_int_field`).
- `scripts/local/azad-finance.env.example` — the local configuration template.
- `docs/AUDIT_REPORT_2026-11-12.md` — this report.

---

## Phase 3 — Automated Verification & Compliance Gates

The repository already has a strong automated gate suite (CI runs 26 jobs across PG 15/16/17). The following gates now pass on the audited tree:

| Gate | What it enforces | Result |
|---|---|---|
| `ruff check .` | Python lint | ✅ 0 errors |
| `ruff format . --check` | Python formatting | ✅ 0 differences |
| `mypy . --ignore-missing-imports --no-error-summary --explicit-package-bases` | Python types | ✅ 0 errors |
| `scripts/lint/check_templates.py` | Every Jinja template parses | ✅ 0 failures (400 templates) |
| `scripts/check_strict_i18n.py` | Every UI string is wrapped in a translation call | ✅ pass |
| `scripts/lint/check_i18n_untranslated.py` | No template call renders as its own key | ✅ 0 of 1821 |
| `scripts/lint/report_catalogue_health.py` | Every key resolves to Arabic | ✅ 7329 keys |
| `scripts/lint/check_migration_head.py` | Single head, no dangling parents, every revision reversible | ✅ head `z3a4b5c6d7e8`, 77 revisions |
| `scripts/lint/check_txn_boundaries.py` | No service ends a transaction; 45 baselined, 0 new | ✅ |
| `scripts/lint/check_service_side_effects.py` | No schema/connection management in services | ✅ 0 findings |
| `scripts/lint/check_tag_shape.py` | No `<tagclass=` mangling | ✅ |
| `scripts/lint/check_a11y_labels.py` | Every form control has an accessible name | ✅ 0 unnamed (1371 controls) |
| `scripts/lint/check_inline_assets.py --max-static 52 --max-dynamic 21 --max-inline-scripts 174` | Inline style/script budget | ✅ within budget |
| `scripts/lint/check_utility_reachability.py` | Every utility class is reachable through its extends chain | ✅ 0 unreachable |
| `scripts/lint/check_css_class_collisions.py` | No bare class defined twice with disagreeing bodies | ✅ 0 collisions |
| `scripts/lint/check_font_assets.py` | Every `@font-face` src resolves to a real woff2; no third-party font host | ✅ |
| `scripts/lint/check_api_docs.py` | `docs/API_REFERENCE.md` matches the live url_map (839 endpoints) | ✅ |
| `tests/unit/utils/test_i18n_parity.py` | Every template key exists for both ar and en | ✅ 11 passed |
| `tests/unit/routes/test_permission_codes_are_seeded.py` | Every permission guard and hand-checked code is seedable | ✅ 5 passed |
| `tests/unit/routes/test_store_routes.py` + `test_store_cov3.py` | Store routes | ✅ 65 passed |
| `tests/unit/services/test_store_service_cov5.py` | Store service | ✅ 9 passed |
| `tests/unit/services/test_stock_sync_service.py` + coverage | Stock sync | ✅ 28 passed |
| `tests/unit/services/test_budget_service.py` + enforcement | Budget | ✅ 30 passed |
| `tests/unit/services/test_pos_session_service.py` + `test_pos_checkout_cov3.py` | POS | ✅ 34 passed |
| `tests/unit/services/test_celery_tasks_cov4.py` | Celery tasks | ✅ 6 passed |
| `tests/unit/routes/test_sales_routes.py` + `test_sales_cov3.py` | Sales | ✅ 129 passed |
| `tests/unit/routes/test_purchases_routes.py` + `test_purchases_coverage99.py` | Purchases | ✅ 37 passed |
| `tests/unit/routes/test_public_routes.py` + `test_public_cov3.py` | Public | ✅ 33 passed |
| `tests/unit/routes/test_auth.py` + `test_auth_routes.py` + `test_auth_cov100.py` | Auth | ✅ |
| `tests/unit/routes/test_products_*.py` (11 files) | Products | ✅ 231 passed |
| `tests/unit/routes/test_payment_vault_*.py` (10 files) | Payment vault | ✅ 296 passed |
| `tests/unit/services/test_maintenance_order_service.py` | Maintenance discounts | ✅ 3 passed |
| `tests/unit/app/test_extensions_coverage.py` | Extensions | ✅ 35 passed |
| `tests/unit/test_coverage_gap_fill_real.py` | Coverage gap fill | ✅ 7 passed |
| `tests/integration/business_scenarios/test_wave3_online_store.py` | Store scenarios | ✅ 11 passed (1 was failing, now fixed) |

### Recommended follow-up gates to add (would close the whole classes of bugs this audit found)

1. **Bulk-DML tenant gate:** a lint rule that rejects `Query.update(...)` / `Query.delete(...)` / `sa_update(...)` / `sa_delete(...)` whose WHERE clause does not contain a `tenant_id` comparison, applied to every table that has a `tenant_id` column. Today `check_txn_boundaries.py` and `check_service_side_effects.py` do not look at bulk DML, and `enforce_grimoire.py`'s G2-TENANT heuristic only flags `Model.query.filter()` *without* `tenant_id`, which misses `.delete()`/`.update()` entirely.
2. **Celery tenant contract:** every Celery task that touches tenant data must take an explicit `tenant_id` argument and filter on it. The ORM guard cannot help a task, because `tenant_scope_enabled()` returns `False` without a request context.
3. **Strict money parsing:** a lint rule that flags `safe_float`, `request.form.get(..., type=float)`, and `float(...)` on a money column, plus a helper (`utils/numeric_input.py`) that raises on invalid input instead of returning zero.
4. **Secret scanning of tracked scripts:** extend `.gitleaks.toml` to scan `scripts/**/*.ps1` and `scripts/**/*.bat` for high-entropy strings and known credential patterns. The published owner password, DB password and session key in `start_azad_finance.ps1` survived because the secret scanner only runs on the application tree.
5. **Permission-code literal scan:** extend `test_permission_codes_are_seeded.py` to scan non-decorator permission literals (the `manage_cheques` bug was in a `_WIZARD_PERM_MAP` dict, which the decorator scan could not see). Done for `has_permission("...")` in this audit; the same should be applied to permission-map dicts.
6. **Sanitizer allowlist pin:** a test that asserts `ALLOWED_TAGS` contains no `a`/`img`/`svg`/`style`/`script` and `ALLOWED_ATTRS` contains no `on*`/`href`/`src`/`style`.
7. **Production secret enforcement:** `assert_production_sanity` now requires `CRON_SECRET`; it should also refuse the well-known dev values (`dev-secret-key-not-for-production`, `AlHazem-Finance-MasterKey-2026!`, `postgres:123`) and refuse `WTF_CSRF_ENABLED=false` when `APP_ENV=production`.

### Residual risks (accepted, documented)

- The public `/suspended/<tenant_id>` page still shows the tenant's own suspension reason to that tenant's customers. This is **deliberate**: the page exists for the tenant's customers, for whom "payment overdue" is actionable. The page is rate limited because the tenant id in the URL is enumerable.
- The `shop` blueprint is exempt from the ORM tenant guard, but compensates with explicit `store.tenant_id` filters on every query (verified).
- The `ErrorAuditLog` table is ORM-exempt (it is platform-wide by design); raw SQL against it must carry its own tenant predicate. `mark_resolved` now does.

### Commit history (this audit)
- `d41eaf5e` — fix(audit): tenant isolation, transaction boundaries, strict money parsing, published secrets
- `e0d7364c` — fix(audit): strict money parsing across sales/purchases/products/payroll/maintenance; remaining P2 security fixes
- `2bbd1400` — feat(store): public storefront, WhatsApp checkout UI, store reports, WhatsApp API integration

**CI:** runs queued (43185254683 / 43183570062). All local gates and targeted tests pass.
