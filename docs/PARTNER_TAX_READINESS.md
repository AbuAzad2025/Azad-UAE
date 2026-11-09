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
- `ReturnService.create_return` currently calculates return tax from the total
  returned value using the sale's single rate, not the returned lines' effective
  categories; inclusive-price returns also need separate treatment. Review
  affected refunds, GL postings and credit notes before filing.
- Historical sale lines do not record whether the tenant had enabled category
  processing when the sale was posted. Do not infer that from the current
  tenant switch. A complete implementation needs a durable effective-category
  and allocation snapshot, category-aware returns, explicit handling of legacy
  ambiguity, and reconciliation to the posted journal entries.
- The ZATCA reporting request currently sends raw XML with Bearer credentials;
  the document/signature and the submission protocol have not been validated
  against ZATCA's SDK and sandbox. Likewise, the ITA v2 request has not been
  validated: the official v2 description lists lower-case field names and
  mandatory fields absent from the current request. A mocked response is not
  government acceptance. Historical records marked submitted or allocated by
  the earlier permissive response parser require authority-side verification.
  A network timeout or local database failure after the authority accepted a
  request can leave the result unknown; reconcile with the authority before
  resending rather than treating a local rollback as proof of non-submission.

  Official references: [ZATCA developer portal manual](https://zatca.gov.sa/en/E-Invoicing/Introduction/Guidelines/Documents/DEVELOPER-PORTAL-MANUAL.pdf),
  [ZATCA XML implementation standard](https://zatca.gov.sa/ar/E-Invoicing/SystemsDevelopers/Documents/20220624_ZATCA_Electronic_Invoice_XML_Implementation_Standard_vF.pdf),
  and [Israel Invoice API description v2](https://www.gov.il/BlobFolder/generalpage/israel-invoice-160723/he/vat_software-houses-180724-en.pdf).

## Partner profit and statements

- Return reversals of product commissions are scoped to the original sale's
  branch and warehouse and recognized in the return period. This does **not**
  make the complete partner P&L correct: scope revenue and COGS currently do
  not fully account for returns and cancellations across periods.
- Product commission creation currently subtracts base-currency cost from
  invoice-currency revenue before FX conversion; VAT-inclusive discounts and
  zero/exempt lines also need review. Historical commissions cannot be assumed
  correct and must not be silently rewritten.
- The unified statement sums distribution share amounts including drafts and
  original product commissions without all reversals/payments. It is not a
  reliable net amount payable.
- A company, branch and warehouse may cover the same underlying profit. The
  contract must define whether smaller-scope entitlements reduce the larger
  pot, whether overlapping shares are independent, or whether overlap is
  prohibited. Expense-share treatment, losses, partner entry/exit dates and
  partial-month fixed amounts likewise need an explicit policy before an
  implementation can be certified.
