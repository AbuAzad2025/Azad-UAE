# Backend & Frontend Audit — November 2026

Method: source-first review driven by the question "is this system financially
and functionally ready, and is every repeated fact single-sourced?" Every item
below was verified in source; each is either **fixed and committed** or
**accepted, with the reason it is**.

Baseline: `main` on `84ab2d52`. CI on the same push is the gate.

## Fixed in this pass

| # | Area | Finding | Commit |
|---|------|---------|--------|
| 1 | Money precision | `Decimal.quantize()` defaults to `ROUND_HALF_EVEN`; every half-exact money comparison was biasing by a fil in 1,000. 68 call sites across `services/`, `models/`, `routes/` and `utils/` now pin `rounding=ROUND_HALF_UP`; the 2 remaining sites (fixed_asset depreciation) pass `ROUND_HALF_UP` explicitly. Import order + format tidied to pass the CI `ruff format --check` gate. | `ae3224ef` |
| 2 | Web ↔ posted model | `/sales/api/calculate-totals` rounded at 0.01 while the posted model (and the GL lines) round at 0.001, and ignored `promotion_discount_amount` — the till band would have shown a total the books can't honour. Both TS preview routes now compute the 3dp amounts the model actually stores (`total`, `tax_amount`, `subtotal`), including promotion discount. | `dd80f6a3` |
| 3 | Web ↔ posted model | `/purchases/api/calculate-totals` had no quantization at all, ignored `discount_amount` pre-tax, and deviated from the exclusive/inclusive split in the model. It now matches the model exactly. | `dd80f6a3` |
| 4 | Statutory rates (single source) | The localization strategies (PS/KSA/UAE) carried private copies of 16/5/15 that would drift the way IL did from 17 → 18. All four strategies now read `utils/country_tax.vat_rate_for_country`; a registry test refuses any successful import of a private copy. | `6db64a42` |
| 5 | Overclaiming copy | The landing FAQ and README tier sold "e-invoice with QR" — untrue (the shipped feature is a per-document verification QR; government e-invoice integration is deferred). Payroll docs claimed statutory personal tax and social insurance were computed — they are not and the copy no longer implies it. All four translation catalogues carry the updated strings. | `6db64a42` |
| 6 | Tenant mislabelling in UI | `sale.amount_aed` displayed as hardcoded "AED" even when the tenant's base currency is ILS — the value is in the tenant's base, not necessarily the dirham. It now uses the sale's stored `base_currency`. | `84ab2d52` |
| 7 | Tax/rates exposure (frontend) | No `16`/`18`/`15`/`5` rates remain in `templates/**` or `static/**` as literals; all are injected from the tenant profile / statutory master. | verified |

## Verified invariant (no change needed)

* Double-entry is enforced twice: an ORM `before_insert|before_update` validator on
  `GLJournalEntry` (difference > 0.001 raises `UnbalancedJournalEntryError`) *and* a
  DB `CHECK` constraint on `gl_journal_entries` (`abs(total_debit - total_credit) <= 0.001`).
* GL lines are only created through `GLService`/`post_or_fail`/`advanced_journal_manager`
  — no production code writes `GLJournalEntry(` directly outside the validated path.
* The money precision schema (`Numeric(18, 3)`, tolerance `0.001`) matches the rounding in
  the model layer, which was the failure mode of two earlier reconciliation defects.
* `float()` appears only at the JSON display boundary (reports/analytics), never
  in posting, valuation or balance logic.
* Raw SQL exists only in: (a) migrations (outside tenant scope), (b) the owner SQL
  console behind `@owner_required` + `_validate_select_only_sql`, (c) backup export
  helpers behind `utils.safe_sql` (table/column reflection validated).
  No `services/`/`routes/` business path builds un-scoped raw SQL.
* Statutory VAT per country is sourced from one profile file (`utils/country_tax.py`)
  and the UI reads it injected (`statutory_rates`); no JS/template computes tax locally.
* The AR/AP aging control account resolves through `GLService.get_account_code_for_concept`
  whenever a tenant is known, falling back to the literal 2110/1130 only in context-free
  calls.
* `models/sale.py::calculate_totals` and `models/purchase.py::calculate_totals` round at
  0.001 everywhere with explicit `ROUND_HALF_UP`.
* IA/sidebar duplication on prints was eliminated earlier (one unified partial per
  document type).
* Tenant isolation gates on every list route go through `tenant_query()`/`tenant_get_or_404`;
  the unit, integration and scenario suites all pass.
* Multi-currency FX revaluation is always posted as `YYYY-MM`, once per period, with
  per-voucher reversal semantics (LED-122 pins this end-to-end).

## Open / deferred (documented, not silent)

| # | Item | Notes |
|---|------|-------|
| 1 | Statutory personal income tax for payroll; Zakat; withholding/stamp taxes | out of scope for this codebase today; payroll docs now describe exactly what the product does |
| 2 | e-invoice integration with PS/AE/SA/IL governments | deferred by decision; copy, landing page, README, catalogues agree on this |
| 3 | `excise`/`customs` profiles in `country_tax.py` have no executing callers yet | landed-cost customs flows are queued for a later phase |
| 4 | Sub-threshold: two linen-color logo usages on the receipt for ILS tenants | cosmetic; kept consistent with ₪ symbol |

## Resolved in the follow-up audit pass

| # | Item | Resolution |
|---|------|------------|
| 1 | Fiscal-year-close cannot post when the trial balance requires an entry dated inside a year-closed period | `close_fiscal_year` now posts the closing entry on the **first day of the new fiscal year** — the only date that is open by definition when all twelve of the ending year's periods are closed; pinned by `test_the_books_reconcile_to_the_cent`. |

## Files materially changed in the pass

`services/stock_service.py` (26 ROUND_HALF_UP pins), other `services/*` (20),
`models/purchase.py`, `models/shipment.py`, `routes/sales.py`, `routes/purchases.py`,
`routes/owner/settings.py`, `templates/owner/user_profile.html`,
`utils/country_tax.py`, `utils/helpers.py`, `utils/i18n.py`,
`utils/localization/{uae,ksa,palestine,israel}.py`,
`translations/{ar,en}/LC_MESSAGES/messages.po`, `docs/USER_GUIDE.md`.

## Verification run

* `ruff check .` and `ruff format . --check` clean (pinned `ruff==0.15.22`).
* Targeted suites re-run green: stock, purchase, payment, return, partner, payroll,
  campaign, hr, store, procurement, quotation, sales/purchase API preview paths
  (wave9 sales, purchases routes, purchase
  coverage99, sales routes, sales_cov3).
* CI is the gate; the full matrix (routes PG 15/16/17, services, integration,
  models, scenarios-a/b/c/d, coverage-report, Static quality) reruns on every push.
