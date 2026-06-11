# Azadexa System Modules

This document reflects the actual system shape observed in the repository code.

**Azadexa** is not a single shop or a simple accounting app. It is a multi-tenant ERP and commerce platform with tenant operations, branch controls, inventory, GL accounting, storefronts, public platform-owner flows, payment vault, monitoring, APIs, and optional AI/automation modules.

---

## Blueprint map

The application registers a large set of Flask blueprints through `bootstrap/blueprints.py`. The active system surface includes:

| Blueprint / route area | System role |
|------------------------|-------------|
| `auth` | authentication, login/logout, payment callback compatibility |
| `main` | dashboard and core authenticated UI |
| `public` | public landing and public platform pages |
| `sales` | tenant sales invoices and sales workflows |
| `pos` | point-of-sale workflows |
| `returns` | product returns and reversal-related flows |
| `customers` | customer profiles, balances, history, statements |
| `partners` | partner/customer-related commercial logic |
| `suppliers` | supplier profiles and purchase-side balances |
| `purchases` | purchase invoices and supplier workflows |
| `products` | catalog, categories, pricing, serial/warranty-related product data |
| `warehouse` | warehouses, stock movements, stock operations |
| `unified_inventory` | unified inventory surface |
| `branches` | branch records and branch-aware operations |
| `payments` | tenant operational payments and receipts |
| `cheques` | cheque lifecycle and pending/confirmed/rejected payment state |
| `expenses` | tenant expenses and categories |
| `ledger` | accounting ledger surfaces |
| `advanced_ledger` | advanced accounting/reporting surfaces |
| `admin_ledger` | administrative ledger tools |
| `payroll` | employees, advances, payroll transactions |
| `reports` | business and financial reports |
| `treasury` | treasury/cash management surfaces |
| `store` | tenant store administration |
| `shop` | public tenant storefronts by slug/domain |
| `payment_vault` | platform/owner payment vault and payment-provider settings |
| `tenants` | tenant context and platform tenant controls |
| `language` | language switching |
| `whatsapp` | WhatsApp integration surface |
| `monitoring` | monitoring and operational visibility |
| `api`, `api_enhanced` | internal/API endpoints |
| `api_analytics` | analytics API surface |
| `api_docs` | API documentation surface |
| `graphql` | GraphQL API surface |
| `gamification` | gamification/engagement features |
| `ai` | AI assistant/features with safe fallback when unavailable |
| `users` | user management |
| `owner` | platform-owner control panel |

---

## Domain model families

The repository imports many model families from `models/__init__.py`. They form these business domains:

### Identity and access

- `User`
- `Role`
- `Permission`
- `LoginHistory`
- `SecurityAlert`
- `APIKey`

### Tenant and branch structure

- `Tenant`
- `Branch`
- `InvoiceSettings`
- `SystemSettings`
- `IntegrationSettings`

### Trading operations

- `Customer`
- `Supplier`
- `Sale`, `SaleLine`
- `Purchase`, `PurchaseLine`
- `Payment`, `Receipt`
- `Cheque`
- `ProductReturn`, `ProductReturnLine`

### Products and inventory

- `Product`
- `ProductCategory`
- `ProductPartner`
- `ProductPriceTier`
- `ProductImage`
- `ProductSerial`
- `Warehouse`
- `StockMovement`
- `ProductWarehouseStock`
- `ProductWarehouseCost`
- `ProductCostHistory`

### General ledger and accounting

- `GLAccount`
- `GLJournalEntry`
- `GLJournalLine`
- `GLPeriod`
- `GLAccountMapping`
- `JournalEntryAudit`
- `BankReconciliation`, `BankReconciliationItem`
- `Budget`, `BudgetLine`
- `CostCenter`
- `ProfitCenter`
- `FixedAsset`, `DepreciationSchedule`
- `CustomsTax`, `AdvancedExpense`, `TaxCalculationRule`
- `ExchangeRateRecord`
- `CashBox`

### Platform-owner and payment vault

- `PaymentVault`
- `PaymentTransaction`
- `PaymentLog`
- `CardVault`
- `CardPayment`
- `Donation`
- `Package`
- `PackagePurchase`
- `AzadPlatformFee`

### Storefront and commerce extension

- `TenantStore`
- `StorePaymentMethod`
- `ShopCustomerAccount`
- `ShopWishlist`
- `ShopReview`
- `ShopAbandonedCart`
- `ShopSavedPayment`
- `ShopProductVariant`
- `ShopStockAlert`
- `ShopNewsletter`
- `ShopLoyalty`, `ShopLoyaltyTransaction`
- `StoreCoupon`
- `Campaign`, `SaleCampaign`
- `Shipment`
- `WarrantyClaim`

### Payroll and partner economy

- `Employee`
- `SalaryAdvance`
- `PayrollTransaction`
- `Partner`
- `PartnerCommissionEntry`
- `PartnerProfitDistribution`
- `PartnerTransaction`

---

## What this means

Azadexa should be documented as a business operating system with these major surfaces:

1. **Tenant ERP core** — sales, purchases, inventory, customers, suppliers, payments, branches, reports.
2. **Accounting core** — GL accounts, journal entries, periods, cost/profit centers, budgets, assets, reconciliation, tax rules.
3. **Commerce layer** — tenant store setup, public catalog, checkout, coupons, loyalty, reviews, variants, saved accounts.
4. **Platform-owner layer** — packages, public donations, owner vault, payment-provider configuration, tenant/platform control.
5. **Control and automation layer** — monitoring, APIs, GraphQL, AI, analytics, WhatsApp, gamification.

Any future documentation should preserve this layered identity.
