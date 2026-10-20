# Audit — Chart of Accounts and Concept → Account Mapping

**Scope:** `models/gl_account_registry.py`, `models/_constants.py`, `utils/constants.py`, `services/gl_posting.py`,
`services/gl_service.py`, `services/gl_account_resolver.py`, `services/gl_provisioning_service.py`,
`services/gl_tree_builder.py`, and every service that posts a journal entry.
**Date:** 2026-10-20 · **Branch:** `main` @ `e8095b06` · **Type:** read-only review, no code changed.
**Question answered:** *the books balance — but are they posted to the right accounts?*

---

## 0. How to read this document

A journal entry can be perfectly balanced and still be materially wrong. The CI suite proves balance
(a `CHECK (abs(total_debit - total_credit) <= 0.001)` constraint on `gl_journal_entries`,
`models/gl.py:208-211`) and the scenario suite proves the posting *machinery* works. Neither proves that the
account on the debit is the account a competent accountant would choose.

This review therefore does not re-derive whether entries balance. It reads the chart, reads the mapping
table, and asks a different question of each mapping: **would a competent accountant for a trading /
distribution company in the UAE / Palestine have chosen this account?**

Every claim below is anchored to a file and line. Where two readings of a mapping are possible, the
document says which one the code implements and which one a reviewer would expect, and marks the verdict
**questionable** rather than guessing.

**Verdict scale**

| Verdict | Meaning |
|---|---|
| correct | The account a competent accountant would pick. |
| questionable | Defensible, but a reviewer would choose differently, or the treatment is internally inconsistent. |
| wrong | The money lands in an account that does not represent it. |

**Severity scale (for §4 findings)**

| Severity | Meaning |
|---|---|
| **P0** | Money lands in the wrong account (or fails to land) on a *normal* operation. |
| **P1** | Wrong only in a specific flow (returns, disposals, reconciliation, FX settlement). |
| **P2** | Naming / presentation / guardrails; no immediate misstatement. |

---

## 1. The chart of accounts

### 1.1 How the chart is created

There is exactly one writer: `GLTreeBuilder.build` (`services/gl_tree_builder.py:49-140`), called through
`GLService.ensure_core_accounts` (`services/gl_service.py:533-570`). It copies `BASE_ACCOUNTS` (98 templates)
plus the tenant's own industry extension (`INDUSTRY_EXTENSIONS`, 49 templates over 13 industries), matching
on **code** and repairing name / type / parent / header / level / contra on every boot. The tree builder is
self-healing, so a tenant's chart converges on the registry whether or not it was created that way.

Because the match is on code, the registry is the authoritative chart: **the code numbers in this document
are the codes that will exist in every tenant's `gl_accounts` table.**

### 1.2 Header semantics

`is_header=True` means *no direct posting*. `GLService._resolve_journal_line_account` refuses a header
account unless the line carries `explicit_account_allowed=True` (`services/gl_service.py:219-225`, `366-367`),
and the provisioning engine refuses to create a mapping that points at a header
(`services/gl_provisioning_service.py:117-121`). 17 of the 98 base accounts are headers.

### 1.3 Contra semantics

`is_contra` marks an account whose normal balance is opposite to its type
(`models/gl.py:41-43`). It is honoured in exactly one place — `GLAccount.get_balance`
(`models/gl.py:166-175`) — and only for `asset` and `equity` types:

```python
is_contra = getattr(self, "is_contra", False)
if is_contra:
    if self.type in ("asset", "equity"):
        balance = -balance
elif self.type in ("liability", "equity", "revenue"):
    balance = -balance
```

Three accounts carry the flag: `1190` Accumulated Depreciation (contra-asset), `3300` Owner Drawings
(contra-equity), `5201` Inventory Gain (contra-expense — the flag has **no** effect on it, because the
type is `expense`, not asset/equity). A fourth, meaningful contra — contra-**revenue** — does not exist in
the chart at all; this matters for §3.2(d).

### 1.4 The 98 base accounts

| Code | Name (EN) | Name (AR) | Type | Parent | Flags |
|---|---|---|---|---|---|
| 1000 | Assets | الأصول | asset | - | header |
| 1100 | Current Assets | أصول متداولة | asset | 1000 | header |
| 1110 | Cash and Cash Equivalents | النقد وما في حكمه | asset | 1100 | header |
| 1111 | Cash Box (Main) | الصندوق الرئيسي | asset | 1110 | - |
| 1112 | Cash Box (Branch) | صندوق الفرع | asset | 1110 | - |
| 1120 | Bank Accounts | الحسابات البنكية | asset | 1100 | header |
| 1130 | Accounts Receivable | العملاء (ذمم مدينة) | asset | 1100 | - |
| 1131 | AR - Trade Customers | عملاء التجارة | asset | 1130 | - |
| 1132 | AR - Partners | عملاء الشراكة | asset | 1130 | - |
| 1133 | AR - Staff | ذمم الموظفين | asset | 1130 | - |
| 1140 | Inventory | المخزون | asset | 1100 | - |
| 1141 | Inventory - Finished Goods | مخزون بضاعة جاهزة | asset | 1140 | - |
| 1142 | Inventory - Raw Materials | مخزون مواد أولية | asset | 1140 | - |
| 1143 | Inventory - Spare Parts | مخزون قطع غيار | asset | 1140 | - |
| 1150 | Cheques Under Collection | شيكات برسم التحصيل | asset | 1100 | - |
| 1160 | Prepayments | مدفوعات مقدمة | asset | 1100 | - |
| 1170 | Employee Advances | سلف الموظفين | asset | 1100 | - |
| 1180 | Fixed Assets | الأصول الثابتة | asset | 1100 | header |
| 1190 | Accumulated Depreciation | مجمع الإهلاك | asset | 1100 | **contra** |
| 1200 | Non-Current Assets | أصول غير متداولة | asset | 1000 | header |
| 2000 | Liabilities | الخصوم | liability | - | header |
| 2100 | Current Liabilities | خصوم متداولة | liability | 2000 | header |
| 2110 | Accounts Payable | الموردين (ذمم دائنة) | liability | 2100 | - |
| 2111 | AP - Suppliers | موردين | liability | 2110 | - |
| 2112 | AP - Trade Payables | ذمم دائنة تجارية | liability | 2110 | - |
| 2120 | VAT Payable | ضريبة القيمة المضافة | liability | 2100 | - |
| 2121 | VAT Output | ضريبة مخرجات | liability | 2120 | - |
| 2122 | VAT Input | ضريبة مدخلات | asset | 1100 | - |
| 2130 | Deferred Cheques Payable | شيكات برسم الدفع | liability | 2100 | - |
| 2140 | End of Service Benefits Provision | مخصص نهاية الخدمة للموظفين | liability | 2100 | - |
| 2141 | Payroll Payable | رواتب مستحقة | liability | 2100 | - |
| 2150 | Partner Current Accounts | حسابات الشركاء الجارية | liability | 2100 | - |
| 2151 | Partner - Merchant Account | حساب التاجر | liability | 2150 | - |
| 2152 | Partner - Commission Hold | عمولات محتجزة | liability | 2150 | - |
| 2999 | Suspense Account | حساب معلق | liability | 2100 | - |
| 2160 | Accrued Vacations Provision | مخصص استحقاقات الإجازات السنوية | liability | 2100 | - |
| 2161 | Loyalty Points Liability | التزام نقاط الولاء | liability | 2100 | - |
| 2170 | Customer Deposits | عربون العملاء | liability | 2100 | - |
| 2180 | Azad Platform Payable | ذمم دائنة - منصة أزاد | liability | 2100 | - |
| 2181 | Azad Platform Fee Accrued | رسوم منصة متراكمة | liability | 2180 | - |
| 2182 | Azad Platform Fee Paid | رسوم منصة مدفوعة | liability | 2180 | - |
| 2200 | Non-Current Liabilities | خصوم غير متداولة | liability | 2000 | header |
| 3000 | Equity | حقوق الملكية | equity | - | header |
| 3100 | Capital | رأس المال | equity | 3000 | - |
| 3130 | Opening Balance Equity | رصيد افتتاحي | equity | 3000 | - |
| 3200 | Retained Earnings | أرباح مرحلة | equity | 3000 | - |
| 3300 | Owner Drawings | مسحوبات المالك | equity | 3000 | **contra** |
| 4000 | Revenue | الإيرادات | revenue | - | header |
| 4100 | Sales Revenue | إيرادات المبيعات | revenue | 4000 | - |
| 4101 | Sales - Retail | مبيعات التجزئة | revenue | 4100 | - |
| 4102 | Sales - Wholesale | مبيعات الجملة | revenue | 4100 | - |
| 4103 | Sales - Online Store | مبيعات المتجر الإلكتروني | revenue | 4100 | - |
| 4104 | Sales - Services | إيرادات الخدمات | revenue | 4100 | - |
| 4200 | Shipping Revenue | إيرادات الشحن | revenue | 4000 | - |
| 4300 | Other Revenue | إيرادات أخرى | revenue | 4000 | - |
| 4400 | FX Gains | أرباح صرف العملات | revenue | 4000 | - |
| 4500 | Donation Revenue | إيرادات التبرعات | revenue | 4000 | - |
| 4600 | Fixed Asset Disposal Gain | أرباح بيع الأصول | revenue | 4000 | - |
| 4700 | Azad Subscription Revenue | إيرادات اشتراك أزاد | revenue | 4000 | - |
| 5000 | Cost of Sales | تكلفة المبيعات | expense | - | header |
| 5100 | Cost of Goods Sold | تكلفة البضاعة المباعة | expense | 5000 | - |
| 5101 | COGS - Retail | تكلفة بضاعة تجزئة | expense | 5100 | - |
| 5102 | COGS - Wholesale | تكلفة بضاعة جملة | expense | 5100 | - |
| 5103 | COGS - Online | تكلفة بضاعة أونلاين | expense | 5100 | - |
| 5150 | Inventory Adjustment | تسوية تكلفة المخزون | expense | 5000 | - |
| 5200 | Inventory Adjustments | تسويات المخزون | expense | 5000 | header |
| 5201 | Inventory Gain | ربح مخزوني | expense | 5200 | **contra** |
| 5202 | Inventory Loss | خسارة مخزونية | expense | 5200 | - |
| 5300 | Landed Costs | تكاليف الشحن والجمارك | expense | 5000 | header |
| 5301 | Freight In | شحن وارد | expense | 5300 | - |
| 5302 | Customs Duty | رسوم جمركية | expense | 5300 | - |
| 5303 | Insurance In | تأمين وارد | expense | 5300 | - |
| 6000 | Operating Expenses | مصروفات تشغيلية | expense | - | header |
| 6100 | Sales & Marketing Expenses | مصروفات تسويق ومبيعات | expense | 6000 | header |
| 6110 | Advertising & Marketing | إعلان وتسويق | expense | 6100 | - |
| 6120 | Sales Commissions | عمولات المبيعات | expense | 6100 | - |
| 6130 | Store Discounts & Coupons | خصومات وكوبونات | expense | 6100 | - |
| 6131 | Campaign Discounts | خصومات الحملات | expense | 6100 | - |
| 6140 | Shipping & Delivery Cost | تكلفة الشحن والتوصيل | expense | 6100 | - |
| 6150 | Partner Commissions | عمولات الشركاء | expense | 6100 | - |
| 6200 | Administrative Expenses | مصروفات إدارية | expense | 6000 | header |
| 6210 | Rent | الإيجار | expense | 6200 | - |
| 6220 | Salaries & Wages | الرواتب والأجور | expense | 6200 | - |
| 6230 | Utilities | الكهرباء والمياه | expense | 6200 | - |
| 6240 | Maintenance & Repairs | صيانة وإصلاحات | expense | 6200 | - |
| 6250 | Office Supplies | قرطاسية ومستلزمات | expense | 6200 | - |
| 6260 | Bank Fees & Charges | رسوم بنكية | expense | 6200 | - |
| 6270 | Insurance | تأمين | expense | 6200 | - |
| 6280 | Legal & Professional Fees | رسوم قانونية | expense | 6200 | - |
| 6290 | Communication | اتصالات | expense | 6200 | - |
| 6300 | Depreciation Expense | مصروف الإهلاك | expense | 6000 | - |
| 6400 | Warranty Claims | مطالبات الضمان | expense | 6000 | - |
| 6410 | Platform Subscription Expense | مصروف اشتراك المنصة | expense | 6000 | - |
| 6500 | Miscellaneous Expenses | مصروفات متنوعة | expense | 6000 | - |
| 6550 | POS Cash Difference | فروقات صندوق نقاط البيع | expense | 6000 | - |
| 6600 | FX Losses | خسائر صرف العملات | expense | 6000 | - |
| 6190 | End of Service Provision Expenses | مصروف مخصص نهاية الخدمة | expense | 6000 | - |
| 6700 | Fixed Asset Disposal Loss | خسائر بيع الأصول | expense | 6000 | - |

### 1.5 Business meaning (what each group is for)

| Range | Meaning |
|---|---|
| 1111–1112 | Tills (per branch). `liquidity_kind='cash'`; the only cash accounts a posting may touch. |
| 1120 | Bank accounts (header; the branch-level bank accounts are created per branch by `_ensure_branch_liquidity_accounts`). |
| 1130–1133 | Trade / partner / staff receivables. `1130` is the account every sale and receipt posts to. |
| 1140–1143 (+ industry) | Inventory at cost, relieved into COGS on sale. |
| 1150 | Cheques received but not yet cleared (a receivable in transit). |
| 1160 / 1170 | Prepayments to third parties / advances to employees (both assets, both recoverable). |
| 1180 / 1190 | Fixed-asset header and the accumulated-depreciation contra. **There is no postable fixed-asset cost account** — see §4 F-12. |
| 2110–2112 | Supplier payables. |
| 2120 / 2121 / 2122 | VAT: a liability parent, output VAT (credit) and input VAT (debit, an asset since the F-08 fix). |
| 2130 | Post-dated cheques issued but not yet presented (a liability). |
| 2140 / 2141 | End-of-service provision; payroll/deduction payable. |
| 2150–2152 | Partner and merchant current accounts (liability) and held commissions. |
| 2160 / 2161 | Accrued annual leave; loyalty-point obligation. |
| 2180–2182 | Amounts owed to the Azad platform. |
| 2999 | Suspense — unmatched bank items. |
| 3100 / 3130 / 3200 / 3300 | Capital, opening-balance equity, retained earnings, owner drawings (contra-equity). |
| 4100–4118 | Revenue by channel (retail / wholesale / online / services / industry). |
| 4200 / 4300 | Shipping charged to customers; other income (bank interest). |
| 4400 / 6600 | FX gain (revenue) / FX loss (**operating** expense). |
| 4500 / 4600 / 4700 | Donations; gains on asset disposal; Azad subscription revenue. |
| 5100–5112 | Cost of goods sold by channel. |
| 5150 / 5200–5204 | Inventory adjustment expense, with a contra gain (5201) and a loss (5202) under a header (5200). |
| 5300–5303 | Landed costs (freight, customs, insurance) — capitalised into inventory by default. |
| 6100–6190 | Selling & marketing: advertising, commissions, discounts, shipping cost, warranty, platform fee. |
| 6200–6290 | Administration: rent, salaries, utilities, bank fees, insurance, legal, comms. |
| 6300 / 6190 / 6400 / 6500 / 6550 / 6600 / 6700 | Depreciation, EOS provision, warranty claims, misc, POS cash difference, FX loss, disposal loss. |

### 1.6 Industry extensions (49 accounts over 13 industries)

Only the tenant's own `business_type` extension is created (`services/gl_tree_builder.py:77-85`).
Each extension pairs an inventory account, a revenue account and usually a COGS account with the base
`1140 / 4100 / 5100` structure — i.e. **the industry split is dimensional, not a different chart.**

**automotive** (3)

| Code | Name (EN) | Name (AR) | Type | Parent |
|---|---|---|---|---|
| 4105 | Service Revenue | إيرادات الخدمات | revenue | 4100 |
| 5104 | COGS - Services | تكلفة خدمات | expense | 5100 |
| 6241 | Workshop Equipment | معدات الورشة | expense | 6200 |

**supermarket** (4)

| Code | Name (EN) | Name (AR) | Type | Parent |
|---|---|---|---|---|
| 1144 | Inventory - Perishable Goods | مخزون بضاعة سريعة التلف | asset | 1140 |
| 1145 | Inventory - Packaged Goods | مخزون بضاعة معبأة | asset | 1140 |
| 4106 | Fresh Sales | مبيعات طازجة | revenue | 4100 |
| 5203 | Expiry Loss | خسارة انتهاء الصلاحية | expense | 5200 |

**pharmacy** (4)

| Code | Name (EN) | Name (AR) | Type | Parent |
|---|---|---|---|---|
| 1146 | Inventory - Prescription | مخزون أدوية بوصفة | asset | 1140 |
| 1147 | Inventory - OTC | مخزون أدوية بدون وصفة | asset | 1140 |
| 4107 | Prescription Sales | مبيعات بوصفة | revenue | 4100 |
| 5105 | COGS - Prescription | تكلفة أدوية بوصفة | expense | 5100 |

**electronics** (3)

| Code | Name (EN) | Name (AR) | Type | Parent |
|---|---|---|---|---|
| 1148 | Inventory - Devices | مخزون أجهزة | asset | 1140 |
| 4108 | Device Sales | مبيعات أجهزة | revenue | 4100 |
| 6121 | Device Warranty Expense | مصروف ضمان أجهزة | expense | 6100 |

**mobile_new** (3)

| Code | Name (EN) | Name (AR) | Type | Parent |
|---|---|---|---|---|
| 1149 | Inventory - Mobile Phones | مخزون موبايلات جديدة | asset | 1140 |
| 4109 | Mobile Sales | مبيعات موبايلات | revenue | 4100 |
| 6122 | IMEI Registration Cost | تكلفة تسجيل IMEI | expense | 6100 |

**mobile_used** (3)

| Code | Name (EN) | Name (AR) | Type | Parent |
|---|---|---|---|---|
| 1151 | Inventory - Used Mobile | مخزون موبايلات مستعملة | asset | 1140 |
| 4110 | Used Mobile Sales | مبيعات موبايلات مستعملة | revenue | 4100 |
| 5204 | Refurbishment Cost | تكلفة تجديد | expense | 5200 |

**mobile_parts** (3)

| Code | Name (EN) | Name (AR) | Type | Parent |
|---|---|---|---|---|
| 1152 | Inventory - Spare Parts Mobile | مخزون قطع غيار موبايلات | asset | 1140 |
| 4111 | Parts Sales | مبيعات قطع غيار | revenue | 4100 |
| 5106 | COGS - Parts | تكلفة قطع غيار | expense | 5100 |

**batteries** (4)

| Code | Name (EN) | Name (AR) | Type | Parent |
|---|---|---|---|---|
| 1153 | Inventory - Batteries | مخزون بطاريات | asset | 1140 |
| 4112 | Battery Sales | مبيعات بطاريات | revenue | 4100 |
| 5107 | COGS - Batteries | تكلفة بطاريات | expense | 5100 |
| 6242 | Battery Recycling | إعادة تدوير بطاريات | expense | 6200 |

**clothing** (4)

| Code | Name (EN) | Name (AR) | Type | Parent |
|---|---|---|---|---|
| 1154 | Inventory - Clothing | مخزون ملابس | asset | 1140 |
| 4113 | Clothing Sales | مبيعات ملابس | revenue | 4100 |
| 5108 | COGS - Clothing | تكلفة ملابس | expense | 5100 |
| 6123 | Seasonal Clearance | تصفية موسمية | expense | 6100 |

**restaurant** (5)

| Code | Name (EN) | Name (AR) | Type | Parent |
|---|---|---|---|---|
| 1155 | Inventory - Food | مخزون طعام | asset | 1140 |
| 1156 | Inventory - Beverage | مخزون مشروبات | asset | 1140 |
| 4114 | Food Sales | مبيعات طعام | revenue | 4100 |
| 4115 | Beverage Sales | مبيعات مشروبات | revenue | 4100 |
| 5109 | COGS - Food | تكلفة طعام | expense | 5100 |

**construction** (5)

| Code | Name (EN) | Name (AR) | Type | Parent |
|---|---|---|---|---|
| 1157 | Inventory - Materials | مخزون مواد بناء | asset | 1140 |
| 1158 | Equipment Rental | تأجير معدات | asset | 1140 |
| 4116 | Contract Revenue | إيرادات عقود | revenue | 4100 |
| 5110 | COGS - Materials | تكلفة مواد بناء | expense | 5100 |
| 6243 | Site Expenses | مصروفات موقع | expense | 6200 |

**jewelry** (5)

| Code | Name (EN) | Name (AR) | Type | Parent |
|---|---|---|---|---|
| 1159 | Inventory - Gold | مخزون ذهب | asset | 1140 |
| 1162 | Inventory - Gemstones | مخزون أحجار كريمة | asset | 1140 |
| 4117 | Jewelry Sales | مبيعات مجوهرات | revenue | 4100 |
| 5111 | COGS - Gold | تكلفة ذهب | expense | 5100 |
| 6244 | Security Cost | تكلفة أمن | expense | 6200 |

**trading** (3) — *the industry this audit is written against*

| Code | Name (EN) | Name (AR) | Type | Parent |
|---|---|---|---|---|
| 1161 | Inventory - General Trading | مخزون تجارة عامة | asset | 1140 |
| 4118 | Trading Revenue | إيرادات تجارة | revenue | 4100 |
| 5112 | COGS - Trading | تكلفة تجارة | expense | 5100 |

**Observation.** The industry revenue (`4118 Trading Revenue`) and COGS (`5112`) accounts are **never posted
to** — every sale posts to the base `4100 / 5100` regardless of the tenant's industry
(`services/sale_service.py:680-689`, `766-786`). The same is true of `4101/4102/4103` (retail / wholesale /
online) and every industry COGS account. The chart promises a channel and industry split that the ledger
never produces.

---

## 2. How a concept becomes an account

This is the machinery the whole mapping question runs through, and it has **two** branches.

### 2.1 The concept registry

`models/_constants.py:141-560` declares 63 concepts, each with a `resolution_mode`:

| Mode | Meaning | Example |
|---|---|---|
| `mapping` | Resolved through the tenant's `gl_account_mappings` table. | `AR` → 1130 |
| `liquidity` | The caller must name a cash/bank account; the resolver checks `liquidity_kind`. | `CASH`, `BANK` |
| `record` | The caller must name an account explicitly (`explicit_account_allowed=True`). | `FIXED_ASSET_ASSET`, `DEPRECIATION_EXPENSE`, `ACCUMULATED_DEPRECIATION` |
| `non_posting` | Posting to it is refused outright. | `LANDED_COST` |

### 2.2 The mapping table (the chart of concepts)

`GL_MODULE_DEFINITIONS` (`models/gl_account_registry.py:867-1074`) is the *only* source of
concept → account pairs. 16 modules; 6 are required (always provisioned), 10 are gated on a feature flag.

| Module | Required | Flag | Concept → account |
|---|---|---|---|
| `core_sales` | yes | - | `SALES_REVENUE`→4100, `SALES_RETURNS`→4100, `SALES_DISCOUNT`→6130, `SALES_COMMISSION`→6120, `TIER_DISCOUNT`→4100, `POS_CASH_DIFFERENCE`→6550, `AR`→1130 |
| `core_purchases` | yes | - | `AP`→2110, `PURCHASE_RETURNS`→2110, `INVENTORY_ASSET`→1140, `COGS`→5100, `FREIGHT_IN`→5301, `CUSTOMS_DUTY`→5302 |
| `core_payments` | yes | - | `CHEQUES_UNDER_COLLECTION`→1150, `DEFERRED_CHEQUES_PAYABLE`→2130, `BANK_FEES`→6260, `CARD_PROCESSING_FEES`→6260 |
| `core_inventory` | yes | - | `INVENTORY_ASSET`→1140, `COGS`→5100, `COGS_REVERSAL`→5100, `INVENTORY_ADJUSTMENT_GAIN`→5150, `INVENTORY_ADJUSTMENT_LOSS`→5150, `OPENING_BALANCE_EQUITY`→3130 |
| `currency_fx` | yes | - | `FX_GAIN`→4400, `FX_LOSS`→6600 |
| `vat` | yes | - | `VAT_INPUT`→2122, `VAT_OUTPUT`→2121 |
| `payroll` | no | `enable_payroll` | `PAYROLL_EXPENSE`→6220, `PAYROLL_PAYABLE`→2141, `END_OF_SERVICE_PROVISION`→6190, `END_OF_SERVICE_LIABILITY`→2140, `LEAVE_ACCRUAL_LIABILITY`→2160, `EMPLOYEE_ADVANCES`→1170 |
| `shop_online` | no | `enable_online_store` | `SHOP_SALES_REVENUE`→4103, `COUPON_EXPENSE`→6130, `LOYALTY_LIABILITY`→2161 |
| `shipments` | no | `enable_shipments` | `SHIPPING_REVENUE`→4200, `SHIPPING_COST_EXPENSE`→6140 |
| `campaigns` | no | `enable_campaigns` | `CAMPAIGN_DISCOUNT_EXPENSE`→6131 |
| `partners` | no | `enable_partners` | `PARTNER_CURRENT_ACCOUNT`→2150, `MERCHANT_CURRENT_ACCOUNT`→2151, `COMMISSION_EXPENSE`→6120 |
| `fixed_assets` | no | `enable_fixed_assets` | `FIXED_ASSET_GAIN`→4600, `FIXED_ASSET_LOSS`→6700 |
| `donations` | no | `enable_donations` | `DONATION_REVENUE`→4500 |
| `warranty` | no | `enable_warranty_tracking` | `WARRANTY_CLAIM_EXPENSE`→6400 |
| `bank_reconciliation` | no | `enable_bank_reconciliation` | `BANK_INTEREST_INCOME`→4300 |
| `azad_platform` | no | `enable_ecommerce` | `AZAD_PLATFORM_PAYABLE`→2180, `AZAD_PLATFORM_FEE_ACCRUED`→2181, `AZAD_PLATFORM_FEE_PAID`→2182, `AZAD_SUBSCRIPTION_EXPENSE`→6410, `AZAD_SUBSCRIPTION_REVENUE`→4700 |

### 2.3 Resolution, end to end

```
line {account?, concept_code?}  →  GLService._resolve_journal_line_account   (services/gl_service.py:182)
   ├─ unknown concept_code?           → GLMappingError  (UNCONDITIONAL — line 194-200)
   ├─ mode == non_posting             → GLMappingError  (line 279-285)
   ├─ mode == liquidity               → explicit account, liquidity_kind must match
   ├─ mode == record                  → explicit account + explicit_account_allowed
   └─ mode == mapping (default)
        └─ dynamic mapping ON  →  resolve_gl_account()  →  gl_account_mappings row  →  that account
                                 · no row  → GLMappingError
                                 · explicit "account" in the line is IGNORED
        └─ dynamic mapping OFF →  the explicit "account" in the line is used, else ValueError
```

Two facts follow, and both matter for this audit:

1. **With the mapping feature on, the account code hard-coded in the service is decorative.** The mapping
   table decides. (`services/gl_service.py:324-342`)
2. **With the mapping feature off, the mapping table is decorative and the hard-coded code decides.**
   Two different charts, and the second one is not the seed.

`services/gl_service.py:39-125` (`GL_ACCOUNTS`, `GL_ACCOUNT_CONCEPTS`) is that second chart. It is a
*second source of truth* and it disagrees with the seed in several places — see §4 F-08.

---

## 3. The concept → account mapping, and the judgement on each

### 3.1 Mapping table with debit/credit and the posting service

Legend: **Dr** = the concept is debited on the named line, **Cr** = credited, **D/C** = both, depending on
the direction of the event.

| Concept | Account | Dr/Cr | Where it is posted |
|---|---|---|---|
| `AR` | 1130 Accounts Receivable | Dr (sale) / Cr (receipt) | `services/sale_service.py:674` (Dr), `services/payment_service.py:701` (Cr) |
| `AP` | 2110 Accounts Payable | Cr (purchase) / Dr (payment) | `services/purchase_service.py:325` (Cr), `services/payment_service.py:311` (Dr) |
| `INVENTORY_ASSET` | 1140 Inventory | Dr (buy) / Cr (sell, adjust) | `services/purchase_service.py:319`, `services/sale_service.py:783`, `services/return_service.py:340`, `services/stock_service.py:205,215,291,1002` |
| `COGS` | 5100 Cost of Goods Sold | Dr | `services/sale_service.py:772` |
| `COGS_REVERSAL` | 5100 | Cr | `services/return_service.py:354` |
| `SALES_REVENUE` | 4100 Sales Revenue | Cr | `services/sale_service.py:686` |
| `SALES_RETURNS` | 4100 | Dr | `services/return_service.py:495` |
| `SALES_DISCOUNT` | 6130 Store Discounts & Coupons | Dr | `services/sale_service.py:716` |
| `CAMPAIGN_DISCOUNT_EXPENSE` | 6131 Campaign Discounts | Dr | `services/sale_service.py:731` |
| `CAMPAIGN_DISCOUNT_REVERSAL` | *(not a concept — see F-01)* | Cr | `services/return_service.py:532` |
| `VAT_OUTPUT` | 2121 VAT Output | Cr (sale) / Dr (return) | `services/sale_service.py:746`, `services/return_service.py:513` |
| `VAT_INPUT` | 2122 VAT Input | Dr (buy) / Cr (buy return) | `services/purchase_service.py:374`, `services/purchase_service.py:693` |
| `FREIGHT_IN` | 5301 | Dr | `services/purchase_service.py:337` (only when landed cost is *not* capitalised) |
| `CUSTOMS_DUTY` | 5302 | Dr | `services/purchase_service.py:346` (same condition) |
| `INVENTORY_ADJUSTMENT_LOSS` | 5150 | Dr | `services/stock_service.py:198`, `services/stock_service.py:982` |
| `INVENTORY_ADJUSTMENT_GAIN` | 5150 | Cr | `services/stock_service.py:222`, `services/stock_service.py:1009` |
| `OPENING_BALANCE_EQUITY` | 3130 | Cr | `services/stock_service.py:298`, `routes/suppliers.py:206` |
| `CASH` | tenant cash box (1111/1112) | Dr/Cr | `services/payroll_service.py:121,284`, `services/pos_cash_service.py:57,67`, `utils/pos_helpers.py:436,447` |
| `BANK` | tenant bank account | Dr/Cr | `services/cheque_service.py:755`, `services/donation_gl_service.py:71`, `services/partner_service.py:336` |
| `CHEQUES_UNDER_COLLECTION` | 1150 | Dr (receive) / Cr (clear) | `services/cheque_service.py:306,418`, `services/sale_service.py:1138` |
| `DEFERRED_CHEQUES_PAYABLE` | 2130 | Cr (issue) / Dr (clear) | `services/cheque_service.py:377,464` |
| `FX_GAIN` | 4400 FX Gains | Cr | `services/payment_service.py:155`, `services/fx_revaluation_service.py:255`, `services/cheque_service.py:434` |
| `FX_LOSS` | 6600 FX Losses | Dr | `services/payment_service.py:128`, `services/fx_revaluation_service.py:260`, `services/cheque_service.py:449` |
| `BANK_FEES` | 6260 | Dr | `services/bank_reconciliation_service.py:225` |
| `BANK_INTEREST_INCOME` | 4300 Other Revenue | Cr | `services/bank_reconciliation_service.py:255` |
| `MISC_EXPENSE` | 6500 | Dr / Cr | `services/pos_cash_service.py:50,74`, `services/cheque_service.py:648,735,850`, `routes/expenses.py:68,74` |
| `COMMISSION_EXPENSE` | 6120 | Dr | `services/commission_gl_service.py:45`, `services/azad_platform_fee_service.py:135` |
| `PARTNER_CURRENT_ACCOUNT` | 2150 | Cr (accrual) / Dr (payment) | `services/commission_gl_service.py:51`, `services/partner_service.py:330,434` |
| `MERCHANT_CURRENT_ACCOUNT` | 2151 | Cr | `services/gl_service.py:855` (legacy fallback), `GLService.get_customer_credit_concept` |
| `SHIPPING_REVENUE` | 4200 Shipping Revenue | Cr | `services/sale_service.py:701` |
| `SHIPPING_COST_EXPENSE` | 6140 | — | **never posted** |
| `PAYROLL_EXPENSE` | 6220 Salaries & Wages | Dr | `services/payroll_service.py:277,449`, `services/hr_service.py:495` |
| `PAYROLL_PAYABLE` | 2141 Payroll Payable | Cr | `services/payroll_service.py:300`, `services/hr_service.py:512` |
| `END_OF_SERVICE_PROVISION` | 6190 | Dr | `services/payroll_service.py:419,556` |
| `END_OF_SERVICE_LIABILITY` | 2140 | Cr | `services/payroll_service.py:433,568` |
| `LEAVE_ACCRUAL_LIABILITY` | 2160 | Cr | `services/payroll_service.py:463` |
| `EMPLOYEE_ADVANCES` | 1170 | Dr (advance) / Cr (recovered) | `services/payroll_service.py:114,311` |
| `DEPRECIATION_EXPENSE` | *(record)* — user-chosen account | Dr | `models/fixed_asset.py:206` |
| `ACCUMULATED_DEPRECIATION` | *(record)* — user-chosen account, typically 1190 | Cr | `models/fixed_asset.py:214,297` |
| `FIXED_ASSET_ASSET` | *(record)* — user-chosen account | Cr (disposal) | `models/fixed_asset.py:340` |
| `FIXED_ASSET_GAIN` | 4600 | Cr | `models/fixed_asset.py:320` |
| `FIXED_ASSET_LOSS` | 6700 | Dr | `models/fixed_asset.py:330` |
| `DONATION_REVENUE` | 4500 | Cr | `services/donation_gl_service.py:77` |
| `POS_CASH_DIFFERENCE` | 6550 | Dr (short) / Cr (over) | `utils/pos_helpers.py:427,456` |
| `SUSPENSE` | 2999 | Dr/Cr | `services/bank_reconciliation_service.py:557` |
| `ACCOUNTS_PAYABLE` | 2110 | Cr | `routes/suppliers.py:213` |
| `SHOP_SALES_REVENUE` | 4103 | — | **never posted** |
| `COUPON_EXPENSE` | 6130 | — | **never posted** |
| `LOYALTY_LIABILITY` | 2161 | — | **never posted** |
| `WARRANTY_CLAIM_EXPENSE` | 6400 | — | **never posted** |
| `SALES_COMMISSION` | 6120 | — | **never posted** (commissions use `COMMISSION_EXPENSE`) |
| `TIER_DISCOUNT` | 4100 | — | **never posted** |
| `CARD_PROCESSING_FEES` | 6260 | — | **never posted** |
| `PURCHASE_RETURNS` | 2110 | — | **never posted** (purchase returns post to `AP`) |
| `PURCHASES` | — | — | **never posted** |
| `FOOD_SALES_REVENUE` / `BEVERAGE_SALES_REVENUE` | 4114 / 4115 | — | **never posted** |
| `AZAD_PLATFORM_PAYABLE` | 2180 | Cr | `services/azad_platform_fee_service.py:146`, `services/azad_subscription_fee_service.py:110` |
| `AZAD_SUBSCRIPTION_EXPENSE` | 6410 | Dr | `services/azad_subscription_fee_service.py:99` |
| `AZAD_PLATFORM_FEE_ACCRUED` | 2181 | — | **never posted** (the fee is credited to `2180` in one line) |
| `AZAD_PLATFORM_FEE_PAID` | 2182 | — | **never posted** |
| `AZAD_SUBSCRIPTION_REVENUE` | 4700 | — | **never posted** (the platform never books the fee as its own revenue) |

### 3.2 The judgement — trading/distribution company, UAE / Palestine VAT

#### (a) Inventory: valued at cost, and the sale relieves stock into COGS — **correct**

Buy: `Dr 1140 Inventory` for `purchase.taxable_amount` (VAT-exclusive) plus capitalised landed cost,
`Cr 2110 AP` for the gross invoice, `Dr 2122 VAT Input` for the tax
(`services/purchase_service.py:295-378`). Landed cost is capitalised by default
(`ENABLE_LANDED_COST_CAPITALIZATION`, `config.py:232`) and is therefore part of the inventory cost, not an
expense — correct for a trader; if the flag is off, freight/customs/insurance go to `5301/5302/5303`, also
correct.

Sell: the stock movement is valued at the moving weighted average cost (`ENABLE_MWAC`,
`services/stock_service.py:693-853`) and the entry is `Dr 5100 COGS / Cr 1140 Inventory`
(`services/sale_service.py:763-796`) — **the cost goes to cost of sales, never to revenue.** This is the
single most important mapping in the system and it is right. Returns reverse it symmetrically:
`Dr 1140 / Cr 5100` (`services/return_service.py:332-359`).

Two caveats, both in §4: the inventory *gain* and *loss* both land in `5150` instead of the seeded
contra pair `5201/5202` (F-13), and a sale whose cost cannot be resolved is logged and posted as COGS = 0
(`services/sale_service.py:797-801`) — stock leaves the shelf with no cost relieved.

#### (b) VAT: output and input separated, net is a liability — **correct**

Output VAT is credited to `2121 VAT Output` (a liability), input VAT is debited to `2122 VAT Input`
(an asset, re-parented under `1100` by the F-08 migration). Neither touches the P&L: the tax is never in
`4100` and never in an expense. The VAT return reads the two accounts straight from the ledger and nets
them (`services/gl_service.py:679-750`, `services/tax_service.py:62-83`), which is the right shape for the
UAE/Palestine return where output and input are separate lines and a net position can be a receivable.
Rates are tenant-configurable with AE 5 % / PS 16 % / IL 17 % (`utils/tax_settings.py`).

Caveat: `2120 VAT Payable` is a postable account with no children in use except `2121`, so the balance sheet
shows a permanently nil "VAT Payable" line while the real balance sits in its child (F-15).

#### (c) Receivables and payables: gross balances, not netted — **correct**

A sale debits AR with `sale.total_amount` — the **gross** invoice including VAT
(`services/sale_service.py:672-678`) — while revenue is credited net of VAT and the VAT is credited to
`2121`. A receipt credits AR with the amount collected (`services/payment_service.py:699-704`). A purchase
credits AP with the gross amount including VAT (`services/purchase_service.py:323-328`). Nothing anywhere
nets a receivable against a payable: there is no net-settlement concept, and the customer and supplier
sub-ledgers are separate from `1130`/`2110`. **Correct.**

#### (d) Revenue: gross, with discounts and returns reducing revenue — **questionable**

This is the weakest of the eight, in two distinct ways.

**Discounts do not reduce revenue.** The sale credits `4100` *gross of the trade discount* and debits the
discount to `6130 Store Discounts & Coupons` — a selling expense:

```python
revenue_credit = (sale.taxable_amount - shipping_credit + discount_debit + promo_debit)   # sale_service.py:658
...
{"account": ..., "concept_code": "SALES_DISCOUNT", "debit": discount_debit, ...}          # sale_service.py:716
```

With subtotal 100, discount 10, no VAT: revenue credited **100**, discount expensed **10**. The net effect on
profit is right, but the *presentation* is gross-of-discount revenue with the discount buried in
"Sales & Marketing Expenses". A reviewer would expect either net revenue (contra-revenue) or, at minimum, a
**contra-revenue** account. The chart has none: `3300` is contra-equity, `1190` contra-asset, `5201`
contra-expense — there is no contra-revenue anywhere in the 98 accounts. **Questionable.**

**Returns and sales use opposite conventions.** A return *debits* revenue (`services/return_service.py:495`)
with the amount **net of the discount** and including a share of the shipping charged, and it credits back
only the *promotional* discount (`6131`), never the manual discount (`6130`) and never the shipping revenue
(`4200`). So after a return the ledger keeps a phantom credit in `4100` and a phantom debit in `6130`/
`4200` (§4 F-07). Revenue and discount are therefore internally inconsistent — one is gross, the other net —
which is exactly the condition the brief asks about.

#### (e) Payroll: employer's share a liability until paid; net pay split — **questionable (split is right, timing is not)**

The posting itself is correct and complete:

```python
Dr 6220 PAYROLL_EXPENSE   gross (basic + allowances)     payroll_service.py:271-281
Cr 1170 EMPLOYEE_ADVANCES advance recovered               payroll_service.py:307-316
Cr 2141 PAYROLL_PAYABLE    deductions                     payroll_service.py:291-305
Cr CASH                    net paid                       payroll_service.py:282-288
```

Deductions are **not** expensed — they are credited to a payable (`2141`), so the employer's obligation for
them survives on the balance sheet. Advances are relieved against the advance asset. The employer's own
obligations are accrued separately and correctly: end-of-service `Dr 6190 / Cr 2140` and annual leave
`Dr 6220 / Cr 2160` (`services/payroll_service.py:384-479`).

The questionable part: `PayrollTransaction` is created with `status="paid"` and the cash is credited at
processing time (`services/payroll_service.py:235, 282-288`). There is no "accrue now, pay later" state —
the employer's obligation to the employee is settled the moment the payroll is run. For a monthly payroll
processed before the payment date, the liability to the employee is understated by one run. A second,
*correct* accrual path exists in `services/hr_service.py:457-535` (`Dr 6220 / Cr 2141` for net **and**
deductions) but it is wired to no route — dead code (F-18).

#### (f) Fixed assets: capitalised, depreciated into an expense, disposal through a clearing account — **questionable**

Depreciation is right: `Dr <expense account> / Cr <accumulated depreciation account>` — the cost walks into
an expense and the accumulated amount into a contra-asset (`models/fixed_asset.py:203-220`). The disposal is
also arithmetically right: it debits accumulated depreciation, credits the asset's **gross cost**, credits
the proceeds to bank and posts the difference to `4600`/`6700`
(`models/fixed_asset.py:285-346`) — the gain/loss is computed against *net* book value
(`self.disposal_price - self.book_value`, line 269), so the entry balances exactly.

But the chart cannot support the model:

* **There is no postable fixed-asset cost account.** `1180 Fixed Assets` is a header and its only child is
  `1190` (the contra). Every other asset account in the chart is cash, AR, inventory, cheques, prepayments
  or advances. A fixed asset therefore has nowhere to be capitalised except an account the operator types in
  by hand (`templates/assets/create.html:29-31` — three raw numeric *account IDs*, with no validation that
  the depreciation account is a contra-asset or that the expense account is an expense). The seed's
  `6300 Depreciation Expense` is never referenced by any code path.
* **The acquisition is never posted.** `AssetService.create_asset` (`services/asset_service.py:17-54`)
  writes the `fixed_assets` row and posts nothing — no `Dr fixed asset / Cr cash or AP`. Only the
  depreciation and the disposal ever reach the ledger. Consequently the asset account is credited at
  disposal without ever having been debited: the balance sheet carries a **negative** fixed-asset balance
  equal to the cost of every asset ever disposed, while the P&L happens to be right because the credit lands
  on an asset account (§4 F-12).

#### (g) FX: realized and unrealized separated, in a financial account — **questionable**

The *mechanics* are good. Unrealized differences are revalued per voucher against the open balance only
(`services/fx_revaluation_service.py:210-340`, per-voucher with `branch_id` after the D-C13 fix), and the
realized difference is booked at settlement against AR/AP (`services/payment_service.py:113-169`,
`services/sale_service.py:1226-1293`, `services/cheque_service.py:424-509`). Nothing is double counted: the
revaluation adjusts the carrying amount, and the settlement difference settles the remainder.

Two things are not what a reviewer would expect:

* **Realized and unrealized are not separated.** Both use the same pair of accounts, `4400 FX Gains`
  (revenue) and `6600 FX Losses` (expense). A revaluation gain and a settlement gain are indistinguishable
  in the ledger.
* **`6600 FX Losses` sits under `6000 Operating Expenses`.** An FX loss is a finance cost. As charted, FX
  losses depress **operating** profit, and FX gains inflate revenue, so operating margin is moved by
  currency movements that have nothing to do with trading. The chart has no "finance costs" section at all
  (`6000` is the only expense root besides `5000`), so `6600` is the only place it can go — the chart, not
  the posting, is the root cause.

#### (h) Contra accounts: every contra used rather than netted into the parent — **mixed**

* `1190` Accumulated Depreciation — **used correctly** as a contra-asset, credited by depreciation and
  debited at disposal.
* `3300` Owner Drawings — **correct** as a contra-equity (debit-normal); the sign flip in
  `models/gl.py:166-175` is what makes it present correctly.
* `5201` Inventory Gain — **declared as a contra but never used.** Both the gain and the loss map to `5150`
  (`models/gl_account_registry.py:916-917`), so `5201` and `5202` are dead and the `5200 Inventory
  Adjustments` subtree always reports nil (§4 F-13).
* **Contra-revenue does not exist.** This is the root cause of §3.2(d): with no contra-revenue account,
  trade discounts have nowhere to go but an expense account.

---

## 4. Findings

Severity: **P0** = money lands in the wrong account (or fails to land) on a normal operation ·
**P1** = wrong only in a specific flow · **P2** = naming, presentation or a missing guardrail.

---

### F-01 · P0 · A concept code that does not exist is posted on every promotional return

**Concept / accounts:** `CAMPAIGN_DISCOUNT_REVERSAL` → (none; unknown)
**Code path:** `services/return_service.py:523-537`

```python
if promo_reversal_amount > 0 and manual_refund_amount is None:
    revenue_lines.append({
        "account": GLService.get_account_code_for_concept("CAMPAIGN_DISCOUNT_EXPENSE", ...),
        "concept_code": "CAMPAIGN_DISCOUNT_REVERSAL",     # <-- not a concept
        ...
    })
```

`CAMPAIGN_DISCOUNT_REVERSAL` is not in `GL_CONCEPT_REGISTRY` / `GL_CONCEPT_CODES`
(`models/_constants.py:75-139`), and the resolver rejects an unknown concept **unconditionally**, before
the feature flag is even consulted:

```python
if raw_concept and concept_code not in GL_CONCEPT_REGISTRY:
    raise GLMappingError(..., issue=f"Unknown GL concept code: {raw_concept}")
```
(`services/gl_service.py:194-200`)

**Consequence:** returning goods that were bought on a promotion raises `GlPostingError` and rolls the
whole return back — in *every* configuration, because the check is flag-independent. The leg is reached
whenever `sale.promotion_discount_amount > 0` and the operator did not override the refund amount
(`services/return_service.py:448-451, 523`). The unit test that covers this path mocks `post_or_fail`
outright (`tests/unit/services/test_return_promo_reversal.py:43`), so the concept code is never validated
by CI.
**Correct mapping:** register the concept (e.g. `CAMPAIGN_DISCOUNT_REVERSAL → 6131`) and add it to
`GL_CONCEPT_CODES` + the `ck_gl_account_mappings_concept_code` CHECK constraint, or post the reversal under
the existing `CAMPAIGN_DISCOUNT_EXPENSE` concept.

---

### F-02 · P0 · Nine of the ten mapping-module feature flags do not exist on the tenant model, so their concepts are never mapped

**Concepts affected:** `SHIPPING_REVENUE` (4200), `CAMPAIGN_DISCOUNT_EXPENSE` (6131),
`COMMISSION_EXPENSE` (6120), `PARTNER_CURRENT_ACCOUNT` (2150), `MERCHANT_CURRENT_ACCOUNT` (2151),
`FIXED_ASSET_GAIN` (4600), `FIXED_ASSET_LOSS` (6700), `DONATION_REVENUE` (4500),
`BANK_INTEREST_INCOME` (4300), `SHOP_SALES_REVENUE` (4103), `COUPON_EXPENSE` (6130),
`LOYALTY_LIABILITY` (2161), `SHIPPING_COST_EXPENSE` (6140), `WARRANTY_CLAIM_EXPENSE` (6400),
`AZAD_PLATFORM_PAYABLE` (2180), `AZAD_PLATFORM_FEE_ACCRUED` (2181), `AZAD_PLATFORM_FEE_PAID` (2182),
`AZAD_SUBSCRIPTION_EXPENSE` (6410), `AZAD_SUBSCRIPTION_REVENUE` (4700).
**Code path:** `services/gl_provisioning_service.py:86-90`

```python
for mod in GL_MODULE_DEFINITIONS.values():
    if not mod.required:
        flag = mod.feature_flag
        if flag and not getattr(tenant, flag, False):
            continue
```

`getattr(tenant, flag, False)` is the gate, and the `Tenant` model has **no** column named
`enable_shipments`, `enable_campaigns`, `enable_partners`, `enable_fixed_assets`, `enable_donations`,
`enable_warranty_tracking`, `enable_bank_reconciliation`, `enable_online_store` or `enable_ecommerce`
(`models/tenant.py` — the only `enable_*` columns are `multi_warehouse, multi_currency, gl, ai, reports,
api, pos, payroll, cheques, expenses, store, pos_promotions, pos_multi_tender, pos_returns, pos_shifts,
auto_backup, tax`). `enable_ecommerce` exists on `SystemSettings` (`models/system_settings.py:75`), not on
the tenant, and `getattr` does not look there.

So those ten modules are skipped for **every** tenant, and the concepts above have no
`gl_account_mappings` row. Under the production default (`ENABLE_DYNAMIC_GL_MAPPING=True`,
`config.py:226`) the resolver raises:

```python
raise GLMappingError(..., issue="No active GL account mapping exists for this concept.")
```
(`services/gl_account_resolver.py:210-217`)

**Consequence:** in production, a sale that charges shipping, a promotional sale, a partner sale, an asset
disposal, a donation, a bank reconciliation that books interest, and every Azad platform-fee posting are
rolled back — the money never reaches the ledger. Note the route-level gate uses the **opposite** default for
the same missing attribute (`getattr(tenant, f"enable_{feature_name}", True)`,
`utils/feature_guards.py:78`): the feature is treated as *on* for the page and *off* for the mapping.
**Correct mapping:** either add the flags to the `Tenant` model and set their defaults to match the
posting paths, or drop the flag gate and provision these concepts unconditionally — a concept must be mapped
whenever a service posts it.

---

### F-03 · P0 · Three concepts have no mapping in any module, so the postings that use them cannot happen

**Concepts affected:** `MISC_EXPENSE` (6500), `SUSPENSE` (2999), `ACCOUNTS_PAYABLE` (2110).
**Code path:** `models/gl_account_registry.py:867-1074` (no module lists them) →
`services/gl_provisioning_service.py:86-132` (only module concepts are created) →
`services/gl_account_resolver.py:210-217`.

Affected postings:

| Posting | File:line |
|---|---|
| POS cash pay-in / pay-out | `services/pos_cash_service.py:50, 74` |
| Cheque bounce / cancel (fee to misc expense) | `services/cheque_service.py:648, 655, 735, 748, 850, 855` |
| Expense with no category GL account | `routes/expenses.py:68, 74` (the categorised case fails differently — see F-04) |
| Unmatched bank item → suspense | `services/bank_reconciliation_service.py:557` |
| Supplier opening balance | `routes/suppliers.py:213` |

**Consequence:** the cashier's petty-cash movement, the cheque-bounce fee, the default expense posting, the
suspense routing and the supplier opening balance all fail with `GLMappingError` in production. The suspense
case is worse: the exception is swallowed and the statement line is silently marked `ignored`
(`services/bank_reconciliation_service.py:580-581`), so unmatched bank lines vanish from the reconciliation
without a trace.
**Correct mapping:** add `MISC_EXPENSE→6500`, `SUSPENSE→2999`, `ACCOUNTS_PAYABLE→2110` to a required module
(`core_expenses` / `core_payments` / `core_purchases`), or make the services post `AP` instead of the
duplicate `ACCOUNTS_PAYABLE` concept.

---

### F-04 · P0 · Manual journal entries carry no concept code, so the accountant's own entry is rejected

**Code path:** `routes/ledger.py:369-375` → `services/gl_service.py:336-342`

```python
lines.append({
    "account_code": account_code,     # no "concept_code"
    "debit": debit_value, "credit": credit_value, ...
})
```
```python
if account_code:
    raise GLMappingError(..., issue=(f"No approved GL concept was provided for legacy hardcoded account code {account_code}."))
```

Under the production default, **every** line of a manual journal entry raises before it reaches the ledger.
The UI exists (`routes/ledger.py:351-395`), the account is validated against the tenant's chart
(`services/gl_service.py:889-900`) — and then the entry is refused. The same shape appears in the expense
flow: a category that *does* carry a GL account posts with `concept_code = None`
(`routes/expenses.py:68, 86-92`), so the categorised expense is refused by the same guard.
**Consequence:** the accountant cannot post an adjusting, accrual or reclassification entry at all; the only
way to move money that the chart has no concept for is to break the code.
**Correct mapping:** either let a manual line carry a `concept_code` (chosen in the form) or allow an
explicit account on manual lines (`explicit_account_allowed=True`), since a manual entry has no concept by
definition.

---

### F-05 · P0 · The year-end closing entry cannot be posted at all — Retained Earnings (3200) is never used

**Concept / accounts:** all P&L accounts → `3200 Retained Earnings`
**Code path:** `services/gl_service.py:2029-2052` and `2075-2082`

```python
gl_lines.append({
    "account_id": acct_id,            # <-- "account_id", not "account_code"/"account"
    "debit": abs(bal), "credit": Decimal("0"), ...
})
```

The resolver reads `line.get("account_code") or line.get("account")` (`services/gl_service.py:183`), finds
neither, and falls through to:

```python
if not account_code:
    raise ValueError("GL account code is required when dynamic mapping is disabled.")
```
(`services/gl_service.py:355-356`)

This raises in **both** flag states: with the mapping on, the line has no concept and no account code; with
it off, the same guard fires. The test that covers `close_fiscal_year` mocks `post_or_fail` entirely
(`tests/unit/services/test_gl_service.py:1624`), so the failure is invisible to CI.
**Consequence:** the fiscal-year close cannot complete. The P&L is never cleared into `3200`, so retained
earnings never accumulates and every year-end balance sheet is wrong by the year's profit.
**Correct mapping:** build the closing lines with `account_code` (and, for the retained-earnings leg, the
`account_id` of `3200`) so they resolve through the same path as every other posting.

---

### F-06 · P1 · CI proves a configuration that production does not run

**Code path:** `tests/conftest.py:238` vs `config.py:226`

```python
# tests/conftest.py
ENABLE_DYNAMIC_GL_MAPPING = False
```
```python
# config.py
# When False (default): legacy hardcoded GL code lookups remain active.
ENABLE_DYNAMIC_GL_MAPPING = _bool(os.environ.get("ENABLE_DYNAMIC_GL_MAPPING"), True)
```

The comment and the code contradict each other, and the default is `True` while the entire test suite —
including all 2047 business scenarios — forces it to `False`. The scenarios therefore exercise the
**legacy hard-coded-code path** (`services/gl_service.py:39-125`), which is exactly the path that F-02,
F-03, F-04 and F-05 show to be broken and out of step with the seed. Only one unit module flips the flag on
(`tests/unit/services/test_gl_authority_model.py:17-31`) and it asserts the *provisioning scope*, not that
a posting succeeds.
**Consequence:** the green CI run is evidence about a configuration that is not the production
configuration. Every P0 above sits in the gap.
**Correct mapping:** run the scenario suite in both flag states (or default the suite to the production
value), and add one scenario that asserts a *concept → account* expectation per posting rather than only
balance.

---

### F-07 · P1 · A return never reverses the trade discount or the shipping revenue

**Concepts / accounts:** `SALES_REVENUE` (4100), `SALES_DISCOUNT` (6130), `SHIPPING_REVENUE` (4200)
**Code path:** `services/sale_service.py:692-735` (sale) vs `services/return_service.py:486-537` (return)

On sale: revenue credited **gross**; discount debited to `6130`; shipping credited to `4200`.
On return: revenue debited with `net_return_amount` (line total **minus** the discount share **plus** the
shipping share — `services/return_service.py:246-259`), the customer credited, and only the *promotional*
discount credited back (`6131`, lines 523-537).

Worked example — subtotal 100, discount 10, shipping 5, no VAT, whole line returned:

| Account | After sale | After return | Should be |
|---|---|---|---|
| 4100 revenue | +100 | **+5** | 0 |
| 6130 discount | +10 (Dr) | **+10 (Dr)** | 0 |
| 4200 shipping | +5 | **+5** | 0 |
| profit | −5 net | **0 net** | 0 |

Net profit is right, but `4100` keeps a phantom credit of the discount + shipping share and `6130`/`4200`
keep phantom balances. Over a year of returns, revenue is materially overstated and the discount and
shipping lines are materially overstated, so **gross margin is overstated** while net profit is not — the
worst kind of error to reconcile, because the trial balance still balances.
**Correct mapping:** credit the `SALES_DISCOUNT` share back to `6130` and the `SHIPPING_REVENUE` share back
to `4200` on the return, exactly as the promotional leg already does for `6131`; or (better) net discounts
and shipping against revenue at the outset and use a contra-revenue account for returns.

---

### F-08 · P1 · The hard-coded legacy account table disagrees with the seed — two charts of accounts

**Code path:** `services/gl_service.py:39-85` (`GL_ACCOUNTS`) and the literal codes in the services.

This table is the one that decides the account when the mapping feature is off (F-06) — i.e. the one CI
proves. It does not match the seed:

| Hard-coded | Used for | In the seed? | Seed equivalent |
|---|---|---|---|
| `6950` | Bank fees (`services/bank_reconciliation_service.py:224`) | **no — account does not exist** | `6260` |
| `4500` | Bank interest income (`services/bank_reconciliation_service.py:254`) | yes, but it is **Donation Revenue** | `4300` Other Revenue |
| `2120` | Deferred cheques on a cheque-paid expense (`routes/expenses.py:76`) | yes, but it is **VAT Payable** | `2130` |
| `6180` | Depreciation expense (`services/gl_service.py:65`) | **no — account does not exist** | `6300` |
| `2115` | Merchant payable (`services/gl_service.py:49, 855`) | **no — account does not exist** | `2151` |
| `3350` | Partner current account (`models/_constants.py:265`) | **no — account does not exist** | `2150` |
| `4200` | Donation credit, the vault default (`models/payment_vault.py:88`) | yes, but it is **Shipping Revenue** | `4500` |
| `4300` | Shipping revenue legacy code (`models/_constants.py:277`) | yes, but it is **Other Revenue** | `4200` |
| `6990` / `6950` | Misc expense / bank fees legacy codes (`models/_constants.py:284, 325`) | **no** | `6500` / `6260` |
| `1240` / `1290` | Fixed asset / accumulated depreciation legacy codes (`models/_constants.py:346, 359`) | **no** | (no postable FA account exists — F-12) |

**Consequence:** with the mapping feature off, a bank reconciliation charges bank fees to a non-existent
account (posting fails), bank interest is booked as donation revenue, an expense paid by cheque is credited
to the VAT payable account, a merchant's balance is posted to a non-existent account, and a donation is
booked as shipping revenue — while with the feature on the same operations land in different accounts. The
same logical event has two different answers depending on a feature flag.
The same divergence hits an owner-configurable account: `PaymentVault.donation_credit_account` is editable in
the Owner panel (`routes/payment_vault.py:569`) and defaults to `4200`
(`models/payment_vault.py:88`), but with the mapping on the donation leg resolves through
`DONATION_REVENUE → 4500` and the owner's chosen account is ignored
(`services/donation_gl_service.py:75-81`).
**Correct mapping:** delete the second table and make the concept registry the only source of account
codes; where an account is genuinely record-owned, resolve it through the tenant's own chart.

---

### F-09 · P1 · The AR reconciliation compares against accounts that are not in the chart

**Accounts:** `3350` (partner) and `2115` (merchant) — neither exists in the 98-account seed.
**Code path:** `services/ar_reconciliation_service.py:15-19`, `132-163`

```python
AR_SUBLEDGER_ACCOUNTS = (
    ("1130", lazy_gettext("ذمم مدينة"), ("regular",)),
    ("3350", lazy_gettext("جاري الشركاء"), ("partner",)),
    ("2115", lazy_gettext("ذمم التجار"), ("merchant",)),
)
...
account = acc_q.first()
gl_bal = ARReconciliationService._gl_balance(account.id, ...) if account else Decimal("0")
```

For `3350` and `2115` the account is `None`, so the GL side is forced to **0** while the operational side is
the real customer balance. The partner and merchant rows therefore always show a difference and
`all_matched` can never be true.
**Consequence:** the receivable reconciliation report — the control that proves AR agrees with the
sub-ledger — reports a permanent, false break for every partner and merchant customer.
**Correct mapping:** reconcile against `2150 Partner Current Accounts` and `2151 Partner - Merchant
Account`, i.e. the accounts the concepts actually post to.

---

### F-10 · P1 · Revenue is recognised gross of trade discounts and there is no contra-revenue account

**Concepts / accounts:** `SALES_REVENUE` (4100) and `SALES_DISCOUNT` (6130)
**Code path:** `services/sale_service.py:650-670` (revenue base), `707-720` (discount debit)

As set out in §3.2(d): revenue is credited gross of the trade discount and the discount is charged to
`6130 Store Discounts & Coupons`, an account under `6100 Sales & Marketing Expenses`. The chart contains no
contra-revenue account to put it in (`3300` is contra-equity, `1190` contra-asset, `5201` contra-expense).
**Consequence:** reported revenue overstates net sales by the total of trade discounts given, and the
discount is invisible when a reader looks at the revenue line — it is buried in marketing expense. Channel
revenue (`4101/4102/4103`) and industry revenue (`4118` etc.) are also never used, so no revenue
breakdown in the chart can be produced from the ledger at all.
**Correct mapping:** add a contra-revenue account (e.g. `4119 Sales Returns & Discounts`) and credit it for
discounts, or net the discount into revenue at source; then post returns to the same account.

---

### F-11 · P1 · Shipping, warranty, loyalty and card costs never reach the ledger

**Concepts / accounts:** `SHIPPING_COST_EXPENSE` (6140), `WARRANTY_CLAIM_EXPENSE` (6400),
`LOYALTY_LIABILITY` (2161), `CARD_PROCESSING_FEES` (6260)
**Code path:** no service posts these concepts. `services/shipment_service.py` posts nothing at all;
`services/warranty_service.py` creates a claim row and no entry; `StoreService.earn_loyalty_points`
accrues points with no liability.

The sale credits the customer for the shipping charged (`4200`, `services/sale_service.py:692-705`) and the
carrier's cost is never expensed.
**Consequence:** gross margin is overstated by the full delivery cost for every shipped order; warranty
replacement cost is never expensed; the shop issues loyalty points that will be redeemed against goods
without ever having recognised the obligation; card-processing fees are never expensed.
**Correct mapping:** post the carrier cost to `6140` when the shipment is billed, the warranty repair cost
to `6400` when the claim is settled, the points earned to `2161` when they are granted, and the card fee
to `6260` when the card is settled.

---

### F-12 · P1 · The fixed-asset cost is never capitalised, and the chart has no fixed-asset cost account

**Accounts:** `1180 Fixed Assets` (header), `1190` (the contra) — no postable asset-cost account exists.
**Code path:** `services/asset_service.py:17-54` (creation posts nothing),
`models/fixed_asset.py:255-346` (disposal credits the asset account by the gross cost).

`AssetService.create_asset` writes the `fixed_assets` row and stops. There is no `Dr fixed asset / Cr cash
or AP` anywhere in the asset flow, and no code path posts to `1180`. At disposal the asset account is
**credited** by `purchase_price` (`models/fixed_asset.py:337-346`) although it was never debited.

Consequence for a 100-asset depreciated 10 and disposed for 80: the asset account ends at **−100**, the
accumulated depreciation at +10, so the balance sheet carries a negative fixed asset of 90 for an asset that
no longer exists, while the P&L shows only the 10 depreciation and the 10 disposal loss. The asset's cost
is missing from the balance sheet by its whole value.
Separately, `templates/assets/create.html:29-31` asks the operator for three raw **account IDs** with no
validation that the depreciation account is a contra-asset (`1190`) or the expense account is an expense
(`6300`); both are optional, and a missing one makes `post_depreciation` raise `AttributeError` on
`None.code` for every monthly run (`models/fixed_asset.py:205, 213`).
**Correct mapping:** add postable fixed-asset cost accounts under `1180` (e.g. `1210 Vehicles`,
`1220 Equipment`), post the acquisition (`Dr 1210 / Cr cash or AP`) when the asset is created, and default
the depreciation and expense accounts to `1190` and `6300` with validation.

---

### F-13 · P1 · The inventory gain and loss both land in one expense account; the seeded contra pair is dead

**Concepts / accounts:** `INVENTORY_ADJUSTMENT_GAIN` and `INVENTORY_ADJUSTMENT_LOSS` → both `5150`
**Code path:** `models/gl_account_registry.py:916-917`, `services/stock_service.py:190-227`, `976-1015`

The seed provides `5200 Inventory Adjustments` (header) with `5201 Inventory Gain` (`is_contra=True`) and
`5202 Inventory Loss` — a deliberately designed contra pair. The mapping sends **both** concepts to `5150
Inventory Adjustment`, an unrelated account under `5000`. The `5200` subtree therefore always reports nil,
and `5150` carries a credit balance when a gain is posted (a credit-balance expense account is read as a
negative expense by the income statement, so the arithmetic survives — the presentation does not).
**Consequence:** inventory gains and losses are not separately visible; a stocktake variance cannot be read
off the chart as designed.
**Correct mapping:** `INVENTORY_ADJUSTMENT_GAIN → 5201`, `INVENTORY_ADJUSTMENT_LOSS → 5202`.

---

### F-14 · P2 · FX losses are an operating expense, and realized and unrealized FX share one account pair

**Concepts / accounts:** `FX_GAIN` → `4400` (revenue), `FX_LOSS` → `6600` (child of `6000 Operating Expenses`)
**Code path:** `models/gl_account_registry.py:1002-1003`, `services/fx_revaluation_service.py:252-262`,
`services/payment_service.py:119-159`

Unrealized differences (`services/fx_revaluation_service.py:250-262`) and realized differences on
settlement (`services/payment_service.py:119-159`) both post to `4400`/`6600`; nothing distinguishes them.
`6600` is a child of `6000 Operating Expenses`, so a currency movement moves operating profit.
**Consequence:** operating margin is distorted by FX, and a reader cannot tell a revaluation from a
settlement.
**Correct mapping:** a finance-cost section (`6700`-style, e.g. `6300` is taken by depreciation, so add
`6800 Financial Expenses`) with `6810 FX Losses` / `4810 FX Gains`, and separate realized from unrealized
(e.g. `4811 Unrealized FX Gains`).

---

### F-15 · P2 · `VAT Payable` (2120) is postable, empty, and used for something else entirely

**Account:** `2120 VAT Payable` — `is_header=False`, in `PROTECTED_ACCOUNT_CODES`
(`models/gl_account_registry.py:1088-1100`), parent of `2121`.
**Code path:** `routes/expenses.py:75-77`

```python
if expense.payment_method == "cheque":
    payment_account = "2120"
    payment_concept = "DEFERRED_CHEQUES_PAYABLE"
```

With the mapping on, the concept wins and the entry lands in `2130`; with the mapping off it lands in
`2120` — the VAT liability account — for an expense paid by cheque. Meanwhile `2120` itself is never
posted, so the balance sheet shows a permanently nil "VAT Payable" and the real balance in its child `2121`.
**Consequence:** a nil line where the tax liability should be, and a path that can post a cheque liability
into the VAT account.
**Correct mapping:** make `2120` a header (or a pure roll-up), and post cheque-paid expenses to `2130`.

---

### F-16 · P2 · A POS cash pay-in is credited to "Miscellaneous Expenses"

**Concept / account:** `MISC_EXPENSE` → `6500 Miscellaneous Expenses`
**Code path:** `services/pos_cash_service.py:63-79`

```python
else:   # pay_in
    lines = [
        {"account": cash_code, "concept_code": "CASH", "debit": amount, ...},
        {"account": misc_code, "concept_code": "MISC_EXPENSE", "debit": 0, "credit": amount, ...},
    ]
```

Cash placed **into** the drawer is credited to an expense account, which reduces operating expenses and
therefore increases reported profit. A competent accountant credits cash-over/short (`6550`) or a liability
(an "other payables / float" account).
**Consequence:** each drawer replenishment or owner float inflates profit by its amount.
**Correct mapping:** credit `6550 POS Cash Difference` (or a dedicated float liability) for a pay-in.

---

### F-17 · P2 · The seed's health probe cannot detect a missing concept mapping

**Code path:** `utils/seed_manifest_probe.py:110-137`

```python
required = len(GL_MODULE_DEFINITIONS)      # 16 — the number of MODULES
...
if actual < required:                     # actual = number of MAPPING ROWS
    short += 1
```

The threshold is the number of *modules* (16) applied to a count of *mapping rows*; the six required modules
alone yield 25 distinct mappings (31 with `payroll`), so the probe passes for any tenant that has the core
modules — and would also pass for a tenant that is missing every optional concept, which is exactly the
failure mode in F-02. The manifest entry itself is declared as `expected=0, check="at_most"`
(`utils/seed_manifest.py:210-223`), i.e. no mapping is ever required.
**Consequence:** the boot-time health check cannot see the defect class that produces every P0 in this
document.
**Correct mapping:** compare the tenant's mapping rows against the *expected concept set* derived from the
posting paths, not against the module count.

---

### F-18 · P2 · A second, unwired payroll posting path exists that would double-post if connected

**Concepts / accounts:** `PAYROLL_EXPENSE` (6220) → `PAYROLL_PAYABLE` (2141)
**Code path:** `services/hr_service.py:457-535` (`PayrollService.approve_batch`), versus
`services/payroll_service.py:269-326` (`PayrollService.process_payroll`)

`process_payroll` debits `6220` and credits **cash** at processing time. `approve_batch` debits `6220` and
credits `2141` for the same `PayrollTransaction` rows. No route calls `approve_batch` — only
`tests/unit/services/test_hr_service.py` and `test_hr_payroll_assurance.py` do — so it is dead code today.
**Consequence:** if it is ever wired to a screen, every payroll run is expensed twice.
**Correct mapping:** delete it, or make it the single accrual path and have `process_payroll` settle the
payable instead of cash.

---

### F-19 · P2 · The chart promises channel and industry splits the ledger never produces

**Accounts:** `4101`, `4102`, `4103`, `4105`–`4118`, `5101`–`5112`, `1141`–`1159`
**Code path:** `services/sale_service.py:680-689` (always `SALES_REVENUE` → 4100), `766-786`
(always `COGS` → 5100).

Every sale posts to `4100` and `5100` regardless of the channel (POS, online store, wholesale) or the
tenant's industry. The online store posts through the same `SaleService.create_sale`
(`services/store_checkout_service.py:241`, `services/pos_checkout_service.py:255`), so `4103 Sales - Online
Store` is never touched.
**Consequence:** the industry extension accounts and the channel split accounts are dead; no revenue or
margin report by channel or industry can be produced from the ledger. The chart's own extension mechanism
(`INDUSTRY_EXTENSIONS`) is therefore decorative.
**Correct mapping:** add a channel/industry dimension to the sale (or a `SALES_REVENUE` mapping per
channel) and resolve the revenue and COGS account from it.

---

### Findings summary

| Severity | Count | IDs |
|---|---|---|
| P0 | 5 | F-01, F-02, F-03, F-04, F-05 |
| P1 | 8 | F-06, F-07, F-08, F-09, F-10, F-11, F-12, F-13 |
| P2 | 6 | F-14, F-15, F-16, F-17, F-18, F-19 |
| **Total** | **19** | |

The five P0s share one root cause: **the concept layer and the posting layer were built independently.**
The chart is sound as a chart; the mapping table that binds concepts to accounts is not in sync with the
services that post, with the feature flags that gate it, or with the flag value production actually runs.

---

## 5. Deliberately out of scope

These are not defects in this system and must not be reported as such:

| Topic | Why it is out of scope |
|---|---|
| **IFRS 15 revenue recognition** (contract assets, performance obligations, deferred revenue, variable consideration allocation) | The system recognises revenue at invoice/point-of-sale (`services/sale_service.py:672-761`). There is no contract model, no performance obligation tracking, and no deferred revenue. That is a deliberate scope decision, not a mapping error. |
| **IFRS 16 leases** (ROU assets, lease liabilities, the single-model) | There are no lease contracts in the model; rent is an expense to `6210` (`models/gl_account_registry.py:323`). No lease accounting is attempted. |
| **Deferred tax** | The tenant model carries a VAT country and rate, not a corporate tax rate. `4100`–`6700` are pre-tax. Not attempted, by design. |
| **IFRS 9 / financial-instrument impairment** (expected credit losses on AR) | AR is carried at gross with no allowance account in the chart. The absence of a bad-debt account is a scope decision; the *gross* carrying is correct (§3.2c). |
| **Equity / share capital transactions, multi-entity consolidation** | Single-tenant books, single-entity. `3100 Capital` and `3130 Opening Balance Equity` exist; consolidation is out of scope. |
| **Cost-flow beyond moving average** (FIFO by batch, standard costing, variance analysis) | `StockService` uses a moving weighted average (`ENABLE_MWAC`) with a FIFO batch consumption path; the *valuation* method is a policy choice, not a mapping defect. |
| **Landing-page / product-level tax treatment of exports, zero-rating, tax groups** | The VAT implementation is single-rate, tenant-configured (`utils/tax_settings.py`). UAE zero-rating and Palestine tax-group mechanics are not modelled. |
| **Charity-specific funds, restricted donations, donor restrictions** | `4500 Donation Revenue` is a single unrestricted revenue line. Restricted-fund accounting is out of scope. |
| **Payroll statutory detail** (social-security contributions by employee/employer split, WPS files, pension schemes) | Only end-of-service and annual leave are accrued (`6190/2140`, `6220/2160`). A full UAE/Palestine statutory payroll is out of scope. |
| **Bank reconciliation automation** (auto-matching rules, MT940 parsing quality) | The reconciliation posts what it is given; the *matching* rules are a different subject. |
| **The balance CHECK constraint and the tolerance/plug logic** | `models/gl.py:208-211` and `services/gl_posting.py:37-73` were audited previously (D-C12/D-C18). Balance is not in question here. |

---

## 6. What could not be assessed, and why

| Gap | Why |
|---|---|
| **Which account actually lands in a live tenant's ledger** | The effective account is whichever `gl_account_mappings` row exists for the tenant and branch, and those rows are per-tenant data, not code. This audit establishes what the code *provisions* and what the services *ask for*; a live tenant's mapping table may have been edited by hand (the UI exposes it). Verifying a specific tenant requires its database. |
| **The exact behaviour under `ENABLE_DYNAMIC_GL_MAPPING=True` in a running install** | No integration or business-scenario test runs with the flag on (`tests/conftest.py:238`), and the scenario suite is too slow to run locally per `AGENTS.md`. The P0 conclusions are derived from the code paths, which are unambiguous (`services/gl_service.py:194-200`, `336-342`, `355-356`; `services/gl_account_resolver.py:210-217`), not from an observed failure. **The first thing to do is run one scenario with the flag on.** |
| **Whether tenants already have orphaned mapping rows** | Mappings are never deleted when a concept disappears, and `ensure_gl_mappings` only inserts (`services/gl_provisioning_service.py:92-93`). A tenant provisioned before a concept was renamed could still resolve a stale account. Needs a live database to check. |
| **The value of the `GLAccountMapping` rows a platform owner can edit** | The Owner panel's mapping UI was not traced in this pass; the audit covers the code path, not the admin workflow. |
| **Multi-currency revaluation completeness** | `services/fx_revaluation_service.py` revalues open AR and AP only; whether other monetary items (customer deposits `2170`, partner balances `2150`, cheques in transit `1150`) should also be revalued is a policy judgement the code does not attempt. Flagged here, not as a finding, because the omission is consistent and deliberate. |
| **The correctness of the MWAC/FIFO cost numbers themselves** | The cost *engine* (`services/stock_service.py:693-853`) was read only far enough to confirm that COGS is posted from it and that the sale relieves inventory at cost. A valuation audit (negative stock, batch consumption, retrospective cost adjustment) is a separate piece of work. |
| **Everything outside the ledger** | Bank feeds, card acquirer settlement files, the payment vault and the SaaS billing ledger are out of the scope of "chart of accounts and concept mapping" and were not reviewed. |

---

*Prepared by review of the code and the seed at `main` @ `e8095b06`. No code was changed in the course of
this audit.*
