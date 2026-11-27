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
| 4 | Sub-threshold: two linen-color logo usages on the receipt for ILS tenants | cosmetic; kept consistent with ₪ symbol |

(Items 1–3 were delivered on 2026-11-09 — see the resolved table below.)

## Resolved in the follow-up audit pass

| # | Item | Resolution |
|---|------|------------|
| 1 | Fiscal-year-close cannot post when the trial balance requires an entry dated inside a year-closed period | `close_fiscal_year` now posts the closing entry on the **first day of the new fiscal year** — the only date that is open by definition when all twelve of the ending year's periods are closed; pinned by `test_the_books_reconcile_to_the_cent`. |
| 2 | Statutory personal income tax for payroll; social insurance | Delivered for real: progressive brackets + credit points (IL) and the Palestinian schedule in `COUNTRY_TAX_PROFILES`; NSSF (PS, 7%/9%, 18.8k ceiling), Bituach Leumi + Mas Briut (IL, two tiers 3.5%/12% ≤ 7,522 / ≤ 50,695 NIS), GOSI (SA, new/pre-2024-07-03 laws, non-nationals 2% employer hazards only), GPSSA (AE, nationals only, 11%/15%, 70k ceiling) — all in `utils/country_tax.py`, all unit-pinned. Withholdings persist on the transaction, post to the new GL accounts (2143/2144/2147 + 6221) and the payslip shows the breakdown. Employer share posts as an additional expense. Remaining: Zakat and withholding/stamp taxes (no statutory bracket exists for them in scope), and the Israel mandatory pension fund (needs a verified rate table before it can be statutory). |
| 3 | e-invoice integration with PS/AE/SA/IL | Delivered for real as far as offline generation goes: `utils/einvoice_document.py` builds a UBL 2.1-shaped statutory document (seller/buyer TRN, lines, VAT breakdown, totals, tamper-evident SHA-256) for all four jurisdictions; KSA additionally gets the ZATCA simplified-invoice TLV QR (tags 1–6, per the published spec). Artifacts persist on `e_invoices` (one per sale, regenerated in place) and are downloadable via `/sales/<id>/einvoice.xml` (all countries) and `/sales/<id>/einvoice-qr.png` (KSA). Sales roll back if document generation fails — no sale posts without its statutory record. Government-gateway submission (ZATCA Phase-2 CSID signing, Israel Tax Authority allocation number, PMA/FTA access points) is credential-gated and explicitly not claimed anywhere. |
| 4 | `excise`/`customs` profiles in `country_tax.py` have no executing callers | Wired into the import landed-cost flow: purchases carry an explicit "imported?" flag; when the customs field is blank the statutory default of the tenant's country applies (PS 15 / IL 18 / AE 5 / SA 15) and the excise amount is computed from the imported products' excise categories at the country rates (AE/KSA: tobacco & energy drinks 100%, soft drinks 50%, base = CIF + customs duty) into the new `excise_amount` landed-cost component, posted to the new `EXCISE_DUTY` concept (account 5304). Basket preview, service and GL posting all share `compute_import_levy_defaults`. |

## Files materially changed in the pass

`services/stock_service.py` (26 ROUND_HALF_UP pins), other `services/*` (20),
`models/purchase.py`, `models/shipment.py`, `routes/sales.py`, `routes/purchases.py`,
`routes/owner/settings.py`, `templates/owner/user_profile.html`,
`utils/country_tax.py`, `utils/helpers.py`, `utils/i18n.py`,
`utils/localization/{uae,ksa,palestine,israel}.py`,
`translations/{ar,en}/LC_MESSAGES/messages.po`, `docs/USER_GUIDE.md`.

The 2026-11-09 deferred-items pass additionally changed:
`services/payroll_service.py`, `services/purchase_service.py`,
`services/sale_service.py`, `services/hr_service.py`, `services/einvoice_service.py`,
`models/{payroll,product,purchase,einvoice,gl_account_registry,_constants,__init__}.py`,
`utils/einvoice_document.py`, `utils/country_tax.py`, `utils/seed_manifest.py`,
`utils/seed_manifest_probe.py`, `utils/localization/{ksa,uae,palestine,israel,null}.py`,
`routes/{sales,purchases,products}.py`, `templates/payroll/{slip,add_employee}.html`,
`templates/products/{create,edit}.html`, `templates/purchases/create.html`,
`templates/sales/view.html`,
`migrations/versions/{f6a7b8c9d012_payroll_statutory_tax,a8b9c0d1e203_excise_customs_landed,b9c0d1e2f304_einvoice_table}.py`,
`docs/API_REFERENCE.md`.

## Verification run

* `ruff check .` and `ruff format . --check` clean (pinned `ruff==0.15.22`).
* Targeted suites re-run green: stock, purchase, payment, return, partner, payroll,
  campaign, hr, store, procurement, quotation, sales/purchase API preview paths
  (wave9 sales, purchases routes, purchase
  coverage99, sales routes, sales_cov3).
* CI is the gate; the full matrix (routes PG 15/16/17, services, integration,
  models, scenarios-a/b/c/d, coverage-report, Static quality) reruns on every push.
