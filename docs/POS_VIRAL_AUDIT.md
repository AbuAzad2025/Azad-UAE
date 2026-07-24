# 🔍 POS Viral Codebase Audit — Findings & Remediation Strategy

**Date:** 2026-07-24 · **Scope:** routes → services → models/events → frontend
**Trigger:** SYSTEM DIRECTIVE — Mission-Critical POS Overhaul
**Headline:** Directive Phases 1–4 are ~90% implemented in the backend (commit `8ae9edbb` + fixes). The audit below maps exactly what exists, the real gaps, and the execution order. No code was duplicated; no new files proposed where a helper exists.

---

## 1. What Already Exists (verified, file:line in audit raw data)

| Directive feature | Status | Where |
|---|---|---|
| Bundle "Buy N for X" + deterministic remainder (4 = 3+1) | ✅ | `services/promotion_service.py:232` (`groups = len // size`, most-expensive-first) |
| Tiered / combo / BOGO without coupons | ✅ | `promotion_service.py:269/300/347` |
| Greedy deterministic multi-rule allocation | ✅ | `promotion_service.py:412-420` |
| Upsell UI metadata in payloads | ✅ backend | `promotion_service.py:426,487` (`upsell_prompts`, Arabic, `needed_quantity/amount`) |
| Split tender multi-currency, each leg via `convert_and_quantize_aed` | ✅ | `sale_service.py:763-784` + per-leg GL `post_or_fail` |
| Promotional discounts → dedicated GL (6131 `CAMPAIGN_DISCOUNT_EXPENSE`) | ✅ | `sale_service.py:662-675`, `gl_service.py:58-59` |
| Concurrent parked carts (server-side, atomic resume) | ✅ | `services/pos_cart_service.py` (max 25/cashier, `with_for_update` → `PosCartConflictError`) |
| Session state machine Open→Paused→Closed + HMAC terminal tokens | ✅ | `models/pos_session.py:17-118`, `utils/pos_security.py:55-71` |
| Supervisor PIN → 60 s single-use override tokens; RBAC gates on void/discount/drawer/pay-in-out | ✅ | `services/pos_override_service.py`, applied at `routes/pos.py:976,1962,2078,2141` |
| Blind close (mandatory `counted_cash`, expected redacted from cashiers) + Cash Over/Short GL | ✅ | `routes/pos.py:1544-1581`, `utils/pos_helpers.py:354-439` |
| Pay-ins/outs → expense/asset GL via `post_or_fail` | ✅ | `services/pos_cash_service.py:32-86` |
| RMA: receipt → original sale, historical FX, proportional promo reversal | ✅ | `services/pos_rma_service.py`, `return_service.py:137,503-520,545` |
| Idempotency ledger (409 in-flight / 422 hash-mismatch / replay, 24 h TTL) | ✅ backend | `services/idempotency_service.py`; wired to checkout/session open/close/returns |
| Subscription tier gating (pro+ for promotions/multi-tender/returns/shifts) | ✅ inline | `utils/pos_features.py`, `_pos_feature_denied` `pos.py:261-281` |
| GL immutability + reversal entries + Decimal everywhere (GL) | ✅ | `models/gl.py`, `services/advanced_journal_manager.py` |
| Phase-5 service tests (~279) | ✅ | `tests/unit/services/test_pos_*`, `test_promotion_*`, `test_idempotency_service.py` |

## 2. The Real Gaps (prioritized)

### 🔴 P0 — Security holes (production red lines)
1. **Drawer-open bypass:** `POST /pos/api/hardware/open-drawer` (`pos.py:2547`) opens the drawer with only `manage_sales` — no override token, no audit. Bypasses the entire `no_sale_drawer` control.
2. **Cross-tenant FK injection:** `tables/assign` inserts arbitrary `sale_id` into `PosTableOrder` without tenant validation (`pos.py:2713-2722`).
3. **Unauthenticated data leak:** `/pos/api/customer-display/<session_id>/stream` + `/pos/customer-display` (`pos.py:2446,2504`) expose last-5 sale details with no auth.

### 🟠 P1 — GRIMOIRE invariant violations
4. `sale_service.py:753-759` — `has_inventory_posted` query **without tenant filter** (P0-level tenant isolation defect).
5. FX conversions bypassing `convert_and_quantize_aed`: `sale_service.py:391,490` (legacy single-payment path), `:32` (commission base).
6. Blind-close GL bypasses the gateway: `utils/pos_helpers.py:409` calls `GLService.create_journal_entry` directly instead of `post_or_fail` (skips balance assert + period lock).
7. `pos_cash_difference` fallback shares account 6500 with `misc_expense` (`gl_service.py:72,81`) — overage (income) lands in expense.
8. Float money columns: `models/package.py:23,112` (only two in the codebase).
9. ~15 raw `db.session.query` in `routes/pos.py` (incl. `:2637` PosTable without tenant filter) instead of `tenant_query`; `pos.py:1413` `Decimal()` without `str()` guard → 500 on bad input.

### 🟡 P2 — Directive features entirely missing
10. **Scale barcode parsing (prefix-20, SKU+weight):** absent backend + frontend. Exact-match lookup only.
11. **FEFO/FIFO batch deduction:** no `batch_number`/`expiry_date` in stock schema at all (only dormant `enable_batches` toggle). Deduction is single-row MWAC. Greenfield schema + StockService picking logic required.
12. **Immutable fraud audit log + anomaly detection:** current `audit_logs` is mutable, tenant-nullable, 180-day-purged. POS events are logged but there is no tamper-evident store and no repeated-voids/drawer aggregation.
13. **Middleware-level tier gating:** `@require_subscription_feature` exists but is applied to zero routes; inline per-endpoint checks instead (works, but not the directive's middleware contract; 403 payload lacks "Feature Locked" text).
14. **WebSockets dormant:** Flask-SocketIO installed, service + handlers exist, but `register_websocket_events` is never called and `socketio.run` never used. POS real-time is SSE-only (in-process fanout — breaks under multi-worker).

### 🟡 P2 — Frontend gaps (entire Phase 2-4 surface is backend-only)
15. No split-tender UI (single payment chip only); backend `payments[]` unused.
16. No upsell rendering; `/api/promotions/evaluate` never called by JS.
17. No supervisor-PIN modals; cashiers hit backend 403s blindly.
18. Cart tabs UI missing — only a localStorage LIFO stack; server `/api/carts/*` unused.
19. Blind close defeated: modal shows expected balance *before* counting (`index.html:288`).
20. **Idempotency-Key never sent by the client** (0 hits in static/templates) — double-click/retry can double-post; offline queue replays without keys.
21. Offline service worker fully built but **never registered** (`offline.js` included by no template; `pos-sw.js` caches a nonexistent CSS path).
22. Defects: `grid.js:607` scanner never `.start()`ed; `grid.js:60` `innerHTML` XSS path; `index.js:323` results-box never hides (uses wrapper `.length`).

### 🟡 P3 — Phase 5 verification gaps
23. No end-to-end journey matrix (cart → promo → multi-tender → shift close → GL validation).
24. No concurrency stress tests (simultaneous checkout → negative stock / deadlock guarantees). Existing locking: `with_for_update` on products (`pos.py:800-804`) and cart resume; untested under race.

## 3. Architecture Notes (non-blocking)
- `api_checkout` is ~460 lines of business logic in a route handler — should become `PosCheckoutService` (routes = HTTP only). Floors/tables + order-type CRUD also mutate models directly in routes.
- `_accumulate_shift_totals` is a reporting service living in `routes/pos.py:1794-1840`.
- KDS SSE fanout is an in-process global — fine single-worker, breaks multi-worker.
- `SecurityAlert` model has **no tenant_id** (cross-tenant exposure if queried carelessly).
- Frontend stack is Flask/Jinja + vanilla JS (directive's "Next.js/Zustand" mention is N/A — no such stack exists).
- `cashier-logic.js` is the only tested pure cart module but is loaded by no template; `index.js`/`grid.js` are ~80% duplicated with divergent bugs.

## 4. Remediation Strategy (execution order)

**Wave A — P0 security (small, surgical):** gate hardware drawer-open with `require_permission_or_override("no_sale_drawer")` + audit; tenant-validate `tables/assign` sale; put customer-display stream behind session-token query param or auth.
**Wave B — GRIMOIRE compliance:** tenant-scope `has_inventory_posted`; route the 3 FX sites through `convert_and_quantize_aed`; move blind-close GL to `post_or_fail`; dedicated `POS_CASH_DIFFERENCE` fallback account; `str()`-guard the Decimal at `pos.py:1413`; convert the 15 raw queries to `tenant_query` where behavior-neutral.
**Wave C — Missing backend features:** scale-barcode parser in `utils/pos_helpers.py` (lookup pipeline) + tests; **FEFO batches** (new `StockBatch` model + deduction ordering in `StockService` behind the existing `enable_batches` toggle — no disruption to MWAC default); **immutable POS fraud log** (new insert-only model, tenant NOT NULL, hash-chained, no purge) + repeated-action aggregation hook at void/drawer log points.
**Wave D — Frontend wiring:** send `Idempotency-Key` (UUID per cart, regenerated on success) from both registers + SW replay; register `offline.js`; render `upsell_prompts`; split-tender UI rows; supervisor-PIN modal wired to `/api/authorize-override`; hide expected balance in close modal; fix the 3 spotted JS defects; make `grid.js`/`index.js` consume shared logic where surgical.
**Wave E — Phase 5 tests:** E2E journey matrix in `tests/unit/services/` (real DB, no mock traps) + concurrency stress (threads/processes hitting checkout to prove no negative stock/deadlock).
**Protocol:** zero pushes until the full local suite is green; every wave keeps tests passing (fix/adapt tests broken by behavior changes).

## 5. Explicitly Out of Scope (do-not-duplicate guard)
No new promotion engine, cart service, override service, idempotency ledger, RMA flow, or GL gateway — all exist and work. WebSocket production wiring is deferred (SSE covers current POS needs; multi-worker fanout redesign is a separate infra decision).

## 6. Remediation Log

### Wave A — P0 security ✅ (2026-07-24, all local tests green)
- `hardware_open_drawer` bypass closed: active session + session-token + `require_permission_or_override("no_sale_drawer")` + high-severity audit (`routes/pos.py`).
- `api_table_assign` cross-tenant sale attach fixed: `tenant_query(Sale)` 404 gate (`routes/pos.py`).
- Customer-display stream + page gated by HMAC `issue_customer_display_token`/`verify_customer_display_token` (`utils/pos_security.py`); signed URL in `/api/session/current`; JS passes token to EventSource.
- Tests: 96 v2-routes + 49 phase3-routes + 33 phase3-services green.

### Wave B — GRIMOIRE compliance ✅ (2026-07-24, 293 tests green)
- `SaleService.has_inventory_posted` tenant-scoped (`StockMovement.tenant_id == sale.tenant_id`).
- FX bypasses routed through `convert_and_quantize_aed`: `sale_service.py` `_commission_base_aed`, `create_sale` paid_amount, `fulfill_sale` paid_amount (dead `Decimal(str(sale.exchange_rate or 1))` line removed).
- Blind-close session-difference GL moved from raw `GLService.create_journal_entry` to the `post_or_fail` gateway (`utils/pos_helpers.py`).
- `pos.py` opening_balance: `Decimal(payload...)` → `safe_decimal` (never-raise guard).
- `api_floor_tables` PosTable query gained `tenant_id` filter (was cross-tenant readable by floor-id guessing).
- 8 raw `.query` sites converted to `tenant_query` (PosShift `_get_active_shift`, KDS orders/status, floors list/tables, table create/status/assign). Entity-derived filters inside SSE streams (`shift.tenant_id`, `session.tenant_id` at pos.py:1817/1834/2475/2492) kept manual deliberately — documented as verified-scoped.
- Test harness: `_pos_api_patches` tenant_query patch is now a per-model dispatcher (`tenant_query_models={...}` + PosShift default open shift); KDS/floor/table tests adapted to the new boundary.

### Documented exceptions — RESOLVED ✅ (owner approved 2026-07-24, see Wave F)
- ~~`gl_service.py:72,81` — `pos_cash_difference` shares fallback account 6500~~ → dedicated `POS_CASH_DIFFERENCE` → account **6550** (Wave F).
- ~~`models/package.py:23,112` — `Float` columns in donation/package payment path~~ → `Numeric(14, 3)` + migration `g8c4b2d91e10` (Wave F).

### Wave C — Missing backend features ✅ (2026-07-24, 463 tests green)
- **Scale barcodes**: `parse_scale_barcode` (GS1 prefix-20, EAN-13 checksum, grams→kg Decimal-exact) in `utils/pos_helpers.py`; integrated into `lookup_pos_product_exact` (item-code/SKU/template match after exact-miss); `/api/product` enriches payload with `is_scale_item` + `scale_weight_kg`. 8 new tests.
- **Immutable fraud log**: `models/pos_fraud_log.py` `PosFraudSignal` (tenant NOT NULL, insert-only, no purge); `log_pos_fraud_signal` + `verify_pos_fraud_chain` in `utils/pos_security.py` — per-tenant SHA-256 hash chain (tamper-evident), 60-min repeat aggregation escalating to `high` at 3+ repeats; hooked at `api_cart_void_line`, `api_drawer_open`, `hardware_open_drawer` (inside the same atomic transactions). 6 new tests; route harness mocks it at the boundary like `log_audit`.
- **FEFO batches**: `models/stock_batch.py` `StockBatch` + `services/stock_batch_service.py` (record_receipt / consume_fefo with FOR-UPDATE row locks via `_safe_for_update` / restore_on_reversal), gated by the dormant global `enable_batches` toggle via `SystemSettings.get_current()` (strict `is True` — mocks can never flip it on). Hooks: `_update_wac_on_receipt` creates lots; `calculate_sale_cogs_and_deduct` positive branch prices COGS from FEFO blended cost (MWAC path byte-identical when off); `reverse_sale` restores lots at original cost. 9 new tests.
- **Migration** `f7b3a1c82e09` (down_revision `d4a2b8c91e07`) creates both tables with all indexes.
- Bonus fix: 3 legacy `close_pos_session` tests in `test_pos_service.py` adapted to the `post_or_fail` gateway (validate/post mocks).

### Wave D — Frontend wiring ✅ (2026-07-24, 312 tests green: 97 pos-v2 + 132 phase3+smoke + 83 smoke re-run)
- **Idempotency keys**: `newCartKey()` (crypto.randomUUID + fallback) in both registers; `state.idemKey` regenerated on every cart mutation and after successful checkout; sent both as body `idempotency_key` and `Idempotency-Key` header (server reads header first via `_extract_idempotency_key`). SW offline replay re-sends stored headers, so the key survives queueing.
- **Offline SW actually registered**: `offline.js` now included by both templates; `pos-sw.js` cache manifest fixed (was caching nonexistent `/static/css/pos.css`) to `pos-theme.css` + `pos_v2.css` + `pos/grid.js` + `pos-config.js`; `Service-Worker-Allowed: /pos/` header added in `app/factory.py` security-headers hook (scope `/pos/` from `/static/` script was being rejected) + `Cache-Control: no-cache` for the SW script.
- **Upsell prompts rendered**: debounced (400ms) live evaluation via `/pos/api/promotions/evaluate` on every cart change → `#upsellBar` (both templates); checkout-success recap rendered into `#doneUpsellList` in the done modal. All DOM writes via `textContent` (no XSS surface).
- **Split-tender UI**: `#splitTenderToggle` reveals dynamic amount+method rows (`#splitTenderRows`), live sum; checkout sends `payments[]` (server `_parse_split_tenders` takes precedence over legacy single-payment fields); rows reset after success; client-side validation (amount>0 + method per row).
- **Supervisor PIN modal**: `#posPinModal` in both templates; `requestOverrideToken(action)` → `/pos/api/authorize-override`; `postWithOverride` wrapper retries guarded POSTs once with `override_token`; drawer-open button (`#drawerOpenBtn`, action `no_sale_drawer`) added to both session bars; checkout retries with `discount_override` token on 403-تفويض.
- **Blind close**: expected-balance rows wrapped in `#closeExpectedBlock` (both templates); shown only when the report payload carries `total_cash_sales`+`expected_balance` (server strips them for users without POS_VIEW_EXPECTED); `expected_balance` read from payload instead of client-computed.
- **JS defects fixed**: grid.js `innerHTML` XSS → `textContent`; missing `state.barcodeScanner.start()`; scale weight propagation (`d.scale_weight_kg || 1`) in both onScan handlers; index.js `res.length` → `res.data.length`; `addToCart(p, qty=1)` quantity parameter.
- JS syntax verified (`node --check` ×4); `app/factory.py` ruff clean.

### Wave E — Phase 5 journey matrix + concurrency stress ✅ (2026-07-24, 4 new tests green)
- New `tests/integration/test_pos_e2e_journey.py` (real DB, full route stack, zero route mocks):
  - `test_full_journey_promo_split_tender_close_gl` — 10% campaign + split cash/card tenders → `promotion_discount == 10.0`, `tenders` order preserved, session `total_cash_sales/total_card_sales` accumulate per chunk, blind close (`counted_cash`) succeeds, and EVERY GL journal entry for the tenant is balanced (Σdebit == Σcredit).
  - `test_checkout_idempotency_replay_returns_same_sale` — identical payload + `Idempotency-Key` twice → same `sale_id`, exactly one Sale row, stock deducted exactly once (50 → 47).
  - `test_evaluate_endpoint_matches_checkout_discount` — register's live `/api/promotions/evaluate` preview equals checkout reality (5.0 == 5.0).
  - `test_concurrent_checkouts_never_oversell` (marked `slow`, runs in CI) — 4 threads × qty 3 against stock 10 on the same session via separate test clients: exactly 3 succeed, 1 availability-rejected, final stock == 1, no deadlock (join-timeout guard), no negative balance.

### Wave F — Documented exceptions resolved (owner-approved protected zones) ✅ (2026-07-24, 344 consumer tests green)
- **Dedicated POS cash-difference account**: new registry template `6550 POS Cash Difference / فروقات صندوق نقاط البيع` (expense, parent 6000) + `POS_CASH_DIFFERENCE → 6550` concept mapping (`core_sales`); `gl_service` concept fallback `pos_cash_difference` 6500 → 6550; `_constants` legacy_code synchronized. `GLTreeBuilder.build` (invoked through `ensure_core_accounts` on posting paths) creates 6550 per tenant automatically — no backfill migration needed.
- **Package money Float → Numeric(14,3)**: `Package.price` and `PackagePurchase.amount_paid`; `to_dict` keeps returning `float(...)` for API compatibility. `routes/payment_vault.py` compares/creates with `Decimal(str(...))` (invalid amount → 400 Arabic message). Migration `g8c4b2d91e10` (down_revision `f7b3a1c82e09`) with `postgresql_using='ROUND("col"::numeric, 3)'` + downgrade.
- **Tests**: `TestPosCashDifferenceDedicatedAccount` (5) + `TestPackageMoneyColumnsNumeric` (3) appended to `test_gl_tree_builder_assurance.py`; migration-head expectation updated in `test_pos_phase3_models.py`; consumer batches re-run green (saas/webhook/owner_admin/payment-vault chunks 1-4/analytics).
- **Bonus root fix (production 500)**: `models/tenant.py` naive-`subscription_end` crash — the column is naive `DateTime` while provisioning writes aware datetimes; after a PG round-trip `is_subscription_active`/`get_remaining_days`/`extend_subscription` raised `TypeError` (owner dashboard 500). Read/compare paths now normalize naive → UTC per the established `pos_session`/`pos_override_token` pattern; 4 regression tests in `TestNaiveSubscriptionEnd`. This also eliminates the pre-existing saas→owner_admin test-order flakiness at its root.
