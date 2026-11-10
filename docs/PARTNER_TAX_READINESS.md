# Partner and tax readiness — outstanding controls

This is an engineering risk register, not a legal or tax opinion. Do not
describe these paths as production-certified merely because tests or CI pass.

## Withholding and warehouse expenses

- A tenant can enter a non-resident service withholding percentage. The system
  does not determine the applicable country, treaty, service class or rate;
  the tenant's tax adviser must do so. There is no complete tax-authority
  settlement and reconciliation workflow yet.
- Withholding on a cheque expense is refused: cheque cancellation and bounce
  currently reverse only the cheque amount, not the complete withholding
  liability. Previously created cheque expenses with withholding require
  accounting review. A posted withholding expense must be cancelled and
  recreated rather than financially edited.
- A warehouse's partner P&L includes confirmed, non-reversed expenses explicitly
  attributed to that warehouse. General branch/company expenses are not
  automatically allocated to warehouses. Historic edited expenses may have
  `is_reversed` set despite an amended posted entry; reconcile them before
  relying on historical partner expenses.

## VAT and electronic invoices

- The sales-by-VAT-category table is intentionally unavailable. The previous
  version summed undiscounted line totals, included VAT in some cases and did
  not subtract returns; it was not net sales.
- Scope revenue/COGS now reflect approved returns in the return period
  (same convention as commission reversals): `get_scope_revenue` /
  `get_scope_cogs` subtract approved return lines scoped by the original
  sale, so a February return of a January sale reduces February, not
  January. Rejected returns never reduce. Pinned by
  `tests/integration/test_gap_scenarios.py::TestReturnsReduceScopeProfit`.
- Return VAT is computed per returned line from its tax category
  (standard/zero/exempt) and, for VAT-inclusive prices, the VAT slice is
  carved out of the gross so the refund equals exactly what was paid —
  pinned by `tests/unit/services/test_return_tax_categories.py`.
  Historical returns posted with the old single-rate math are not
  restated.
- Historical sale lines do not record whether the tenant had enabled category
  processing when the sale was posted. Do not infer that from the current
  tenant switch. A complete implementation needs a durable effective-category
  and allocation snapshot, category-aware returns, explicit handling of legacy
  ambiguity, and reconciliation to the posted journal entries.
- The ZATCA reporting request sends the stored XML with Bearer credentials;
  the stored artifact is now genuinely signed with the tenant's CSID key
  (`utils/zatca_signing.py` — enveloped SHA-256 + RSA/ECDSA signature,
  verified locally in `tests/unit/utils/test_zatca_signing.py`), with a
  loud warning fallback for unparseable keys. Full FATOORA C14N
  canonicalization and a live sandbox round-trip have not been validated
  against ZATCA's SDK and sandbox. Likewise, the ITA v2 request has not been
  validated live: the official v2 description lists lower-case field names
  and mandatory fields absent from the current request. A mocked response is not
  government acceptance. Historical records marked submitted or allocated by
  the earlier permissive response parser require authority-side verification.
  A network timeout or local database failure after the authority accepted a
  request can leave the result unknown; reconcile with the authority before
  resending rather than treating a local rollback as proof of non-submission.

  Official references: [ZATCA developer portal manual](https://zatca.gov.sa/en/E-Invoicing/Introduction/Guidelines/Documents/DEVELOPER-PORTAL-MANUAL.pdf),
  [ZATCA XML implementation standard](https://zatca.gov.sa/ar/E-Invoicing/SystemsDevelopers/Documents/20220624_ZATCA_Electronic_Invoice_XML_Implementation_Standard_vF.pdf),
  and [Israel Invoice API description v2](https://www.gov.il/BlobFolder/generalpage/israel-invoice-160723/he/vat_software-houses-180724-en.pdf).
  The ITA Approval payload now includes the mandatory fields that were
  missing (`Invoice_Issuance_Date`, `Amount_Before_Discount`, `Discount`),
  pinned by `test_gap_scenarios.py::TestAuthorityRequestShapes`; the v2
  field casing and a live authority round-trip are still unverified
  without tenant credentials.

## Partner profit and statements

- Product commissions reverse on returns in the return period; scope
  revenue/COGS now do the same (see VAT and electronic invoices above).
  Cancellations remain excluded by status.
- Product commissions now use an FX-consistent margin: base-currency cost
  is converted into the invoice currency before subtracting from revenue
  (`SaleService._commission_margin`), zero/exempt lines are never grossed
  down for VAT, and VAT-inclusive invoice discounts are stripped of VAT
  before reducing the margin. Pinned by
  `tests/unit/services/test_commission_fx_basis.py`. Historical commissions
  cannot be assumed correct and must not be silently rewritten.
- The unified statement now reports net payable: `company_total` sums
  approved distribution `net_due` only (drafts are reported separately as
  `draft_total`), and product commissions are net of return reversals
  (`product_commissions_gross` / `product_commissions_reversed` /
  `product_commissions_total`); `combined_total` is that net payable across
  both roles. Product-commission FX/discount bases still need review (see
  above); historical commissions cannot be assumed correct and must not be
  silently rewritten.
- Sequential allocation is implemented (`create_distributions`): warehouse
  entitlements reduce the branch pot, and branch + warehouse entitlements
  reduce the company pot, so the same profit is not paid twice. The fixed
  amount is paid before the profit percentage (on the remainder), prorated
  by actual active days within the period; a partner whose active window
  does not overlap the period gets no distribution; losses are borne
  sequentially on the same remainder. These policies are pinned by golden
  scenarios in `tests/unit/services/test_partner_distribution_scenarios.py`
  and a real-DB reconciliation in
  `tests/integration/test_partner_distribution_reconciliation.py`.
  Remaining: the unified statement still sums drafts/original commissions
  without all reversals/payments, so it is not a reliable net payable;
  scope revenue/COGS still do not fully account for returns and
  cancellations across periods; product-commission FX/discount bases need
  review (see above).
