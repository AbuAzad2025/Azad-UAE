# Invoice Template Specifications | مواصفات قالب الفاتورة

## 1. Required Fields (UAE FTA Compliance) | الحقول المطلوبة (الامتثال لـ FTA الإمارات)

| Field (EN) | الحقل (AR) | Arabic Label | التسمية العربية | English Label | التسمية الإنجليزية | Source | المصدر |
|------------|-----------|-------------|-----------------|---------------|-------------------|--------|--------|
| Invoice number | رقم الفاتورة | رقم الفاتورة | Invoice No. | `DocumentSequence` auto-generated | توليد تلقائي `DocumentSequence` |
| Issue date | تاريخ الإصدار | تاريخ الإصدار | Issue Date | `Sale.date` | `Sale.date` |
| Seller TRN | الرقم الضريبي للبائع | الرقم الضريبي للبائع | Seller Tax Reg. No. | `InvoiceSettings.tax_number` | `InvoiceSettings.tax_number` |
| Buyer name | اسم المشتري | اسم المشتري | Buyer Name | `Customer.name` | `Customer.name` |
| Buyer TRN | الرقم الضريبي للمشتري | الرقم الضريبي للمشتري | Buyer Tax Reg. No. | `Customer.tax_number` (if VAT-registered) | `Customer.tax_number` (إذا مسجل VAT) |
| Line items | البنود | البنود | Items | `SaleLine` | `SaleLine` |
| Unit price | السعر الوحدة | السعر الوحدة | Unit Price | `SaleLine.unit_price` | `SaleLine.unit_price` |
| Quantity | الكمية | الكمية | Qty | `SaleLine.quantity` | `SaleLine.quantity` |
| Discount | الخصم | الخصم | Discount | `SaleLine.discount` | `SaleLine.discount` |
| VAT rate | نسبة الضريبة | نسبة الضريبة | VAT % | `FiscalPositionTaxRule.rate` | `FiscalPositionTaxRule.rate` |
| VAT amount | قيمة الضريبة | قيمة الضريبة | VAT Amount | Calculated | محسوب |
| Total with VAT | الإجمالي مع الضريبة | الإجمالي مع الضريبة | Total (incl. VAT) | Calculated | محسوب |
| QR Code | رمز الاستجابة السريع | رمز الاستجابة السريع | QR Code | Generated per UAE ZATCA spec | مُنشأ حسب مواصفات ZATCA الإمارات |

## 2. Print Sizes | أحجام الطباعة

| Size (EN) | الحجم (AR) | Dimensions | الأبعاد | Use Case | حالة الاستخدام | Template File | ملف القالب |
|-----------|-----------|------------|--------|----------|---------------|--------------|------------|
| A4 | A4 | 210×297 mm | 210×297 ملم | Formal invoices, exports | الفواتير الرسمية، الصادرات | `templates/invoices/a4.html` | `templates/invoices/a4.html` |
| A5 | A5 | 148×210 mm | 148×210 ملم | Compact invoices | الفواتير المدمجة | `templates/invoices/a5.html` | `templates/invoices/a5.html` |
| Thermal 80mm | حراري 80 ملم | 80 mm width | عرض 80 ملم | POS receipts | إيصالات POS | `templates/invoices/thermal.html` | `templates/invoices/thermal.html` |

## 3. Branding | العلامة التجارية

| Element (EN) | العنصر (AR) | Source | المصدر | Fallback | الاحتياطي |
|--------------|-------------|--------|--------|----------|------------|
| Logo | الشعار | `InvoiceSettings.logo_path` | `InvoiceSettings.logo_path` | `Tenant.logo_url` | `Tenant.logo_url` |
| Company name | اسم الشركة | `InvoiceSettings.company_name_ar` | `InvoiceSettings.company_name_ar` | `Tenant.name_ar` | `Tenant.name_ar` |
| Address | العنوان | `InvoiceSettings.address_ar` | `InvoiceSettings.address_ar` | `Tenant.address_ar` | `Tenant.address_ar` |
| Phone | الهاتف | `InvoiceSettings.phone_1` | `InvoiceSettings.phone_1` | `Tenant.phone_1` | `Tenant.phone_1` |
| Email | البريد | `InvoiceSettings.email` | `InvoiceSettings.email` | `Tenant.email` | `Tenant.email` |
| Footer text | نص التذييل | `InvoiceSettings.footer_text` | `InvoiceSettings.footer_text` | Default legal notice | إشعار قانوني افتراضي |
| Letterhead | رأس الصفحة | `branding.letterhead_url` | `branding.letterhead_url` | `assets/tenants/{slug}/headers/...` | `assets/tenants/{slug}/headers/...` |

## 4. QR Code Specification | مواصفات QR Code

**EN:** The QR code encodes a TLV (Tag-Length-Value) structure per UAE ZATCA e-invoicing standard:

**AR:** يُشفّر QR Code بنية TLV (Tag-Length-Value) حسب معيار ZATCA الإمارات للفواتير الإلكترونية:

| Tag (EN) | Tag (AR) | Field | الحقل | Length | الطول |
|----------|----------|-------|-------|--------|-------|
| 1 | 1 | Seller Name | اسم البائع | Variable | متغير |
| 2 | 2 | Seller Tax Number | الرقم الضريبي للبائع | 15 | 15 |
| 3 | 3 | Invoice Date | تاريخ الفاتورة | 19 (YYYY-MM-DDTHH:MM:SS) | 19 (YYYY-MM-DDTHH:MM:SS) |
| 4 | 4 | Invoice Total (incl. VAT) | إجمالي الفاتورة (شامل VAT) | Variable | متغير |
| 5 | 5 | VAT Total | إجمالي VAT | Variable | متغير |

**EN:** Encoding: Base64-encoded TLV bytes.
**AR:** التشفير: بايت TLV مشفرة بـ Base64.

## 5. Digital Signature and Verification | التوقيع الرقمي والتحقق

| Aspect (EN) | الجانب (AR) | Implementation | التنفيذ |
|-------------|-------------|----------------|---------|
| Signature | التوقيع | SHA-256 hash of invoice JSON, signed with tenant private key | تجزئة SHA-256 لـ JSON الفاتورة، موقعة بمفتاح المستأجر الخاص |
| Verification URL | URL التحقق | `https://azadsystems.com/verify/{token}` | `https://azadsystems.com/verify/{token}` |
| Token | الرمز | UUID stored in `DocumentVerification` model | UUID مخزن في نموذج `DocumentVerification` |
| Expiry | الانتهاء | 5 years from issue date | 5 سنوات من تاريخ الإصدار |

## 6. Multi-Currency Display | عرض العملات المتعددة

| Scenario (EN) | السيناريو (AR) | Display | العرض |
|---------------|---------------|---------|-------|
| Transaction currency == Tenant default currency | عملة المعاملة == العملة الافتراضية للمستأجر | Show one amount | عرض مبلغ واحد |
| Transaction currency != Tenant default currency | عملة المعاملة != العملة الافتراضية للمستأجر | Show both: transaction amount + AED equivalent | عرض كليهما: مبلغ المعاملة + ما يعادله AED |
| Exchange rate | سعر الصرف | Show rate used and effective date | عرض السعر المستخدم وتاريخ النفاذ |

## 7. Numbering Rules | قواعد الترقيم

| Document (EN) | المستند (AR) | Prefix | البادئة | Example | المثال |
|---------------|-------------|--------|---------|--------|--------|
| Sales invoice | فاتورة مبيعات | INV- | INV- | INV-2026-00042 | INV-2026-00042 |
| Purchase order | أمر شراء | PO- | PO- | PO-2026-00123 | PO-2026-00123 |
| Receipt | سند | REC- | REC- | REC-2026-00891 | REC-2026-00891 |
| Payment voucher | سند دفع | PV- | PV- | PV-2026-00555 | PV-2026-00555 |
| Cheque | شيك | CHQ- | CHQ- | CHQ-2026-00200 | CHQ-2026-00200 |

**EN:** Sequences are stored in `DocumentSequence` and incremented atomically.
**AR:** تُخزّن التسلسلات في `DocumentSequence` وتتزايد ذرياً.

## 8. Template Engine | محرك القوالب

| Engine (EN) | المحرك (AR) | File Extension | امتداد الملف | Notes | ملاحظات |
|-------------|-------------|---------------|-------------|-------|---------|
| Jinja2 | Jinja2 | `.html` | `.html` | All print templates | جميع قوالب الطباعة |
| WeasyPrint | WeasyPrint | — | — | HTML to PDF conversion | تحويل HTML إلى PDF |
| wkhtmltopdf | wkhtmltopdf | — | — | Fallback PDF engine | محرك PDF الاحتياطي |

## 9. Accessibility | إمكانية الوصول

**EN:** All invoice PDFs must be text-selectable (not image-only). Minimum font size: 10pt for body, 14pt for headings. Color contrast ratio: minimum 4.5:1.
**AR:** يجب أن تكون جميع فواتير PDF قابلة لتحديد النص (وليست صورة فقط). الحد الأدنى لحجم الخط: 10 نقطة للنص، 14 نقطة للعناوين. نسبة تباين الألوان: حد أدنى 4.5:1.

## 10. Contact | التواصل

AZAD Intelligent Systems | شركة أزاد للأنظمة الذكية
Email: rafideen.ahmadghannam@gmail.com
Phone: +972 56 215 0193
