# 10-AGENT SECURITY & ARCHITECTURE AUDIT — ZERO FRONTEND FINANCIAL LOGIC

## EXECUTIVE SUMMARY (Principal Architect / Security Lead)
RULE ENFORCED: Zero financial/business logic calculations in frontend.
FINDING: CRITICAL violations confirmed in `static/js/pos/cart.js`, `base-helpers.js`, `ai-sales.js`.
STATUS: Templates clean (Agent 1 PASS), JS violated (Agent 2 FAIL), Payload mixed (Agent 3 FAIL),
Currency relies on backend (`CurrencyService` / ILS base — PASS with gaps), Migration required.

---

## AGENT 1 — DOM & TEMPLATE INSPECTOR
SCANNED: templates/shop/cart.html, checkout.html, product.html, order_invoice.html, partials/cart_drawer.html
EVIDENCE:
  - `format_currency(line.display_line_total, currency=store_currency)` — backend-provided
  - `format_currency(totals.display_subtotal, ...)` — backend-provided
  - `format_currency(sale.total_amount, sale.currency)` — backend-provided
VERDICT: PASS. Jinja renders backend-calculated values; no inline `qty*price` expressions.

---

## AGENT 2 — JS SCRIPT AUDITOR (CRITICAL)
SCANNED: static/js/pos/cart.js, base-helpers.js, ai-sales.js, customer-select.js
VIOLATIONS FOUND:

FILE: static/js/pos/cart.js (lines 47-63, 194)
```
const lineBase = it.qty * it.price;          // CLIENT-SIDE CALCULATION — VIOLATION
const lineDisc = lineBase * (it.discountPercent / 100);
subtotal += lineBase - lineDisc;              // CLIENT-SIDE AGGREGATION — VIOLATION
const quickTax = subtotal * (taxRate / 100);   // CLIENT-SIDE TAX — VIOLATION
const quickTotal = Math.max(0, subtotal + quickTax + shipping - discountAmount);
```
IMPACT: User can manipulate `state.cart[].qty`, `.price`, `.discountPercent` via DevTools
before `recalc()` executes, altering the submitted payload to `/sales/api/calculate-totals`.

FILE: static/js/base-helpers.js (lines 636-683)
```
const emi = r > 0 ? (p * r * (1 + r) ** months) / ((1 + r) ** months - 1) : p / months;
const margin = (profit / sell) * 100;          // CLIENT-SIDE MARGIN
const markup = cost > 0 ? (profit / cost) * 100 : 0;  // CLIENT-SIDE MARKUP
```
IMPACT: Loan calculators and pricing analytics run entirely in browser; results displayed
without server-side verification.

FILE: static/js/ai-sales.js (lines 42, 52, 108, 160, 257, 282)
```
const p = parseFloat(document.getElementById(btnId)?.getAttribute("data-price")) || 0;
const currentPrice = parseFloat(priceInput.val()) || 0;
$unitPrice.val(price.toFixed(2));
```
IMPACT: AI-recommended prices formatted and applied client-side; price inputs parsed
and rewritten without server validation.

VERDICT: FAIL — Multiple client-side financial computations confirmed.

---

## AGENT 3 — API & PAYLOAD CONTRACT VERIFIER
ENDPOINT: POST /sales/api/calculate-totals (routes/services)
PAYLOAD INSPECTION (cart.js lines 67-84):
```json
{
  "lines": [{"quantity": it.qty, "unit_price": it.price, "discount_percent": it.discountPercent}],
  "discount_amount": discountAmount,
  "shipping_cost": shipping,
  "tax_rate": taxRate,
  "prices_include_vat": pricesIncludeVatMeta
}
```
FINDING: Frontend sends raw line parameters BUT also computes `subtotal`/`quickTotal`
before API call (line 63 `fmt(quickTotal)`). This creates a dual-truth scenario:
- User sees `quickTotal` (client-computed)
- Backend returns `data.subtotal` / `data.total` (server-computed)
- If mismatch, UI flashes incorrect value briefly (line 89-91 updates after response).
VERDICT: FAIL — Mixed state; payload should only send raw user intents (qty changes),
not pre-computed line values that could be tampered with.

---

## AGENT 4 — CURRENCY & EXCHANGE RATE ENFORCER
SCANNED: static/js/pos/cart.js, base-helpers.js, ai-sales.js, templates/macros/currency_options.html
EVIDENCE:
  - `currencySymbolFor(selectedCurrency())` — frontend mapping (PASS if backed by server config)
  - `fmt(subtotal)` — formatting utility (PASS if pure formatter, not calculator)
  - `base-helpers.js` line 258-260: `toFixed(2/3/4)` — formatting only
  - `ai-sales.js`: `toFixed(2)` on AI recommendations — formatting only
BACKEND SERVICE: `CurrencyService` / base currency `ILS` (from docs/GRIMOIRE.md reference)
VERDICT: PASS WITH GAPS — Formatting is safe, but `ai-sales.js` applies `toFixed()`
to `suggested_price_aed` before displaying; the value itself must originate from backend.

---

## AGENT 5 — BACKEND ROUTE MAPPER
IDENTIFIED ENDPOINTS WHERE CALC MUST LIVE:
  - `routes/sales.py` / `/sales/api/calculate-totals` (POST) — MUST become sole calculator
  - `services/cart_service.py` (if exists) or `services/sale_service.py` — totals logic
  - `models/sale.py` — `line_total` should be `property` computed from DB, not JS-derived
  - `models/gl_posting.py` / GL services — balance and debit/credit logic
  - `services/advanced_journal_manager.py` — journal entry totals
  - `routes/shop/store.py` — storefront checkout calculations
VERDICT: Routes exist; logic must be centralized in `/sales/api/calculate-totals` and
corresponding service layer. No duplicate client logic permitted.

---

## AGENT 6 — DATA FLOW & STATE ARCHITECT
CURRENT (BROKEN) FLOW:
```
Frontend: User changes qty → state.cart updated → recalc() runs (client math)
         → displays quickTotal (line 63) → sends payload to /sales/api/calculate-totals
         → receives {subtotal, total} → updates display (lines 89-91)
```
REQUIRED (SECURE) FLOW:
```
Frontend: User changes qty → sends ONLY {line_id, new_qty} to POST /cart/update-line
         → receives full line object (qty, unit_price [read-only], line_total [server-computed])
         → renders display using server line_total only → NO recalc() function
         → totals endpoint `/sales/api/calculate-totals` returns ONLY server-computed {subtotal, tax, total, discount}
         → frontend is DUMB RENDERER; never computes total
```
STATE MECHANISM: Remove `recalc()` from `cart.js`. Replace with `renderTotals(data)`
that reads exclusively from API response. Remove `state.cart[].qty` mutation for price;
only `qty` can change (and only via API confirmation).

---

## AGENT 7 — SECURITY & TAMPER-PREVENTION LEAD
VULNERABILITY CLASS: Client-Side Price/Total Manipulation
ATTACK VECTOR:
  1. Attacker opens DevTools → modifies `state.cart[0].qty` (increases quantity without server update)
  2. Attacker modifies `state.cart[0].price` (reduces price directly)
  3. Attacker modifies `state.cart[0].discountPercent` (increases discount to 100%)
  4. `recalc()` computes reduced total; user submits to `/sales/api/calculate-totals`
  5. Even if backend recalculates, attacker can intercept response with proxy
     and inject false `data.subtotal` / `data.total` values into DOM
  6. `fmt()` updates display; user pays manipulated amount.
IMPACT: Financial fraud, inventory/GL integrity compromise, audit trail corruption.
MITIGATION (IMMEDIATE):
  - Remove all `qty * price` expressions from `cart.js`, `base-helpers.js`
  - Force `line_total`, `subtotal`, `tax`, `discount` to come ONLY from `/sales/api/calculate-totals`
  - Add server-side idempotency key check for cart updates (already exists per docs for POS)
  - Implement response signature/HMAC for totals payload (advanced)

---

## AGENT 8 — MIGRATION & BACKWARD-COMPATIBILITY STRATEGIST
PHASE 1 (IMMEDIATE — ZERO BREAKING):
  - Keep `recalc()` but disable its calculation: make it a thin wrapper that ONLY
    calls `/sales/api/calculate-totals` and updates display from response.
  - Comment out `lineBase`, `lineDisc`, `subtotal += ...`, `quickTax` calculations.
  - Change `fmt(subtotal)` → `fmt(data.subtotal)`; `fmt(quickTotal)` → `fmt(data.total)`.

PHASE 2 (SHORT-TERM — 1 SPRINT):
  - Remove `recalc()` entirely. Replace with `renderCartFromServer()`.
  - Modify `/sales/api/calculate-totals` to accept ONLY `{cart_items: [{id, qty}], ...}` with
    `qty` as only mutable field; `unit_price` and `line_total` returned read-only.
  - Update `base-helpers.js` loan/margin calculators: convert to API endpoints (`/api/calculate-loan`, `/api/calculate-margin`) or remove from storefront if non-essential.

PHASE 3 (LONG-TERM — 2 SPRINTS):
  - Full removal of `parseFloat(priceInput)` in `ai-sales.js`; AI recommendations
    must come from `/api/ai/recommend-price` endpoint returning `{recommended_price}`.
  - All print templates (`templates/shop/order_invoice.html`) must use backend-rendered
    `line.line_total` exclusively; no JS formatting of raw DB floats.

---

## AGENT 9 — TEST SUITE & REGRESSION GUARD
TEST REQUIREMENTS:
UNIT TESTS (Python — services layer):
  - `tests/unit/services/test_cart_totals.py`: Assert `/sales/api/calculate-totals`
    computes `subtotal = sum(qty * price * (1 - discount/100))` exactly.
  - `tests/unit/services/test_currency_service.py`: Assert `format_currency()`
    uses backend `CurrencyService.base_currency` (ILS) and never client-side rate.

INTEGRATION TESTS (Vitest — frontend):
  - `tests/vitest/cart_real_calculation.test.js`: Assert that after `import("../../static/js/pos/cart.js")`,
    `recalc()` does NOT reference `lineBase` or `lineDisc` variables; only calls `fetch()`.
  - Assert that `window.parseScaleFrame` (from `scale_serial_branch.test.js`) is NOT
    used for price calculations (already fixed in audit session).

REGRESSION GUARD:
  - CI must include `ruff check .` (formatting clean — confirmed `1449` files formatted).
  - Add new lint rule: `grep -r 'qty \* it\.price' static/js/ --include='*.js'` must return 0 results.
  - Add `npm test` coverage threshold: `COVERAGE_FAIL_UNDER: 85` (from `ci.yml`); maintain.

---

## AGENT 10 — CHIEF INTEGRATION OFFICER / FINAL SYNTHESIS

FINAL REPORT — FILE PATHS & PRODUCTION REFACTORING:

1. DELETE FROM FRONTEND (Client-side math expressions):
  - `static/js/pos/cart.js`: Lines 47-63 (`recalc()` calculation block)
  - `static/js/pos/cart.js`: Line 194 (`lineTotal = qty * price * ...`)
  - `static/js/base-helpers.js`: Lines 636-683 (loan EMI, margin, markup calculators)
  - `static/js/ai-sales.js`: Lines 35, 42, 52, 108, 160, 257, 282 (parseFloat price manipulation)

2. REFACTOR TO BACKEND-ONLY:
  - `routes/sales.py` / `/sales/api/calculate-totals`: Must become authoritative calculator.
  - `services/cart_service.py`: Must receive raw `{cart_items: [{id, qty}], discount_amount, tax_rate}`
    and return `{subtotal, discount, tax, total}` using server-side `Decimal` arithmetic.
  - `models/sale.py`: Line `line_total` must be computed property based on DB fields, not JS input.

3. STATE SYNC MECHANISM (Code Replacement):
Replace `cart.js` lines 47-63 with:
```javascript
const recalc = async () => {
  // ZERO client-side calculation; pure API fetch
  const r = await fetch("/sales/api/calculate-totals", {
    method: "POST",
    headers: {"Content-Type":"application/json", "X-CSRFToken": csrf},
    credentials: "same-origin",
    body: JSON.stringify({
      lines: state.cart.map((it) => ({id: it.id, quantity: it.qty})),
      discount_amount: toNum(qs("#discountAmount").value),
      tax_rate: Math.max(0, Math.min(100, toNum(qs("#taxRate").value))),
      prices_include_vat: pricesIncludeVatMeta,
    }),
  });
  const data = (await r.json()).data || await r.json();
  qs("#kpiSubtotal").textContent = fmt(data.subtotal);
  qs("#kpiDiscount").textContent = fmt(data.discount);
  qs("#kpiTotal").textContent = fmt(data.total);
};
```

4. SECURITY FIXES (Agent 7):
  - Add server-side validation that `qty >= 0` and `qty <= stock_level` (warehouse model).
  - Ensure `unit_price` from payload is IGNORED; server looks up price from `product.id`.
  - Implement `atomic_transaction` (from `utils/db_safety.py`) for cart updates.

5. COMMIT HISTORY (This Audit Session):
  - `4f1fad7e`: vitest JS coverage fix + scale_serial tests
  - `e3cbb1ca`: ruff fix (contextlib import)
  - `2a8d1acf`: ruff format (ai_executor, ai_service, backup)
  - `c560c432`: removed broken `pos_low_coverage_branch.test.js`
  - `b9d54147`: restored and fixed `pos_low_coverage_branch.test.js`
  - `770e49f4`: removed `.mjs`, fixed `.js` import patterns
  - `35dd80c1`: restored `scale_serial_branch.test.js` (proper .js version)

RECOMMENDATION: DO NOT PUSH additional frontend logic without backend route verification.
The audit is COMPLETE; migration plan is actionable; security gaps are identified with exact
line numbers in `static/js/pos/cart.js`, `base-helpers.js`, `ai-sales.js`.

--- END OF 10-AGENT AUDIT REPORT ---
Principal Architect / Security Lead — Audit Complete — No financial logic permitted in frontend.
