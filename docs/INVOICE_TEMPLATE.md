# Invoice Template Specifications — Azadexa ERP

## 1. Required Fields (UAE FTA Compliance)

| Field | Arabic Label | English Label | Source |
|-------|-------------|---------------|--------|
| Invoice number | رقم الفاتورة | Invoice No. | `DocumentSequence` auto-generated |
| Issue date | تاريخ الإصدار | Issue Date | `Sale.date` |
| Seller TRN | الرقم الضريبي للبائع | Seller Tax Reg. No. | `InvoiceSettings.tax_number` |
| Buyer name | اسم المشتري | Buyer Name | `Customer.name` |
| Buyer TRN | الرقم الضريبي للمشتري | Buyer Tax Reg. No. | `Customer.tax_number` (if VAT-registered) |
| Line items | البنود | Items | `SaleLine` |
| Unit price | السعر الوحدة | Unit Price | `SaleLine.unit_price` |
| Quantity | الكمية | Qty | `SaleLine.quantity` |
| Discount | الخصم | Discount | `SaleLine.discount` |
| VAT rate | نسبة الضريبة | VAT % | `FiscalPositionTaxRule.rate` |
| VAT amount | قيمة الضريبة | VAT Amount | Calculated |
| Total with VAT | الإجمالي مع الضريبة | Total (incl. VAT) | Calculated |
| QR Code | رمز الاستجابة السريع | QR Code | Generated per UAE ZATCA spec |

## 2. Print Sizes

| Size | Dimensions | Use Case | Template File |
|------|-----------|----------|---------------|
| A4 | 210×297 mm | Formal invoices, exports | `templates/invoices/a4.html` |
| A5 | 148×210 mm | Compact invoices | `templates/invoices/a5.html` |
| Thermal 80mm | 80 mm width | POS receipts | `templates/invoices/thermal.html` |

## 3. Branding

| Element | Source | Fallback |
|---------|--------|----------|
| Logo | `InvoiceSettings.logo_path` | `Tenant.logo_url` |
| Company name | `InvoiceSettings.company_name_ar` | `Tenant.name_ar` |
| Address | `InvoiceSettings.address_ar` | `Tenant.address_ar` |
| Phone | `InvoiceSettings.phone_1` | `Tenant.phone_1` |
| Email | `InvoiceSettings.email` | `Tenant.email` |
| Footer text | `InvoiceSettings.footer_text` | Default legal notice |
| Letterhead | `branding.letterhead_url` | `assets/tenants/{slug}/headers/...` |

## 4. QR Code Specification

The QR code encodes a TLV (Tag-Length-Value) structure per UAE ZATCA e-invoicing standard:

| Tag | Field | Length |
|-----|-------|--------|
| 1 | Seller Name | Variable |
| 2 | Seller Tax Number | 15 |
| 3 | Invoice Date | 19 (YYYY-MM-DDTHH:MM:SS) |
| 4 | Invoice Total (incl. VAT) | Variable |
| 5 | VAT Total | Variable |

Encoding: Base64-encoded TLV bytes.

## 5. Digital Signature and Verification

| Aspect | Implementation |
|--------|----------------|
| Signature | SHA-256 hash of invoice JSON, signed with tenant private key |
| Verification URL | `https://azadsystems.com/verify/{token}` |
| Token | UUID stored in `DocumentVerification` model |
| Expiry | 5 years from issue date |

## 6. Multi-Currency Display

| Scenario | Display |
|----------|---------|
| Transaction currency == Tenant default currency | Show one amount |
| Transaction currency != Tenant default currency | Show both: transaction amount + AED equivalent |
| Exchange rate | Show rate used and effective date |

## 7. Numbering Rules

| Document | Prefix | Example |
|----------|--------|---------|
| Sales invoice | INV- | INV-2026-00042 |
| Purchase order | PO- | PO-2026-00123 |
| Receipt | REC- | REC-2026-00891 |
| Payment voucher | PV- | PV-2026-00555 |
| Cheque | CHQ- | CHQ-2026-00200 |

Sequences are stored in `DocumentSequence` and incremented atomically.

## 8. Template Engine

| Engine | File Extension | Notes |
|--------|----------------|-------|
| Jinja2 | `.html` | All print templates |
| WeasyPrint | — | HTML to PDF conversion |
| wkhtmltopdf | — | Fallback PDF engine |

## 9. Accessibility

- All invoice PDFs must be text-selectable (not image-only).
- Minimum font size: 10pt for body, 14pt for headings.
- Color contrast ratio: minimum 4.5:1.

## 10. Contact

AZAD Intelligent Systems
Email: rafideen.ahmadghannam@gmail.com
Phone: +972 56 215 0193
