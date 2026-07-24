# Product Brochure — Azadexa ERP

## 1. Value Proposition

Azadexa ERP is a multi-tenant, AI-powered SaaS platform that replaces fragmented business tools with one unified system for accounting, inventory, sales, HR, and operations.

**For the business owner:** Real-time visibility into every dirham, every unit of stock, and every employee hour.

**For the accountant:** Automated GL postings, bank reconciliation, and month-end closing.

**For the cashier:** Fast POS checkout with promotions, split payments, and manager overrides.

**For the warehouse manager:** Accurate stock levels, transfers, and serial tracking.

## 2. Modules

### 2.1 Accounting & Financial Management

- Double-entry general ledger with dynamic account mapping.
- Automated journal entries from sales, purchases, payments, and payroll.
- Bank reconciliation with automatic orphan matching.
- Multi-currency support with FX rate resolution and month-end revaluation.
- Cheque lifecycle: receive, deposit, clear, bounce, cancel — all GL-integrated.
- Fixed assets and depreciation schedules.

### 2.2 Inventory & Warehouses

- Multi-warehouse, multi-branch stock tracking.
- Weighted average cost (WAC) and moving WAC.
- Serial number tracking per unit.
- Automated stock deduction on sale, receipt on purchase.
- Inventory reconciliation and discrepancy reports.
- Landed cost capitalization (optional).

### 2.3 Sales & Purchases

- Sales invoices, quotations, and delivery notes.
- Purchase orders, goods receipts, and supplier returns.
- Customer and supplier balance tracking.
- Sales representative commissions with GL posting.
- Multi-price tiers per product.

### 2.4 Point of Sale (POS)

- Multi-channel POS: in-store, mobile, online.
- Promotion engine: tiered discounts, BOGO, bundle, combo.
- Parked carts and order retrieval.
- Manager override tokens for discounts and returns.
- Cash-in/cash-out movements per shift.
- Split tender: cash, card, cheque, credit.
- Return Merchandise Authorization (RMA).
- Kitchen Display System (KDS) for restaurants.

### 2.5 Human Resources & Payroll

- Employee profiles, contracts, and documents.
- Attendance tracking with check-in/check-out.
- Leave requests and approvals.
- Payroll calculation: basic, allowances, deductions, tax, insurance.
- Automated GL accruals for payroll.
- Salary advances and repayment tracking.

### 2.6 CRM & Projects

- Lead pipeline with stages, probabilities, and expected revenue.
- Team assignments and activity tracking.
- Project creation with tasks, timesheets, and billing.
- Task stages and progress tracking.

### 2.7 E-commerce

- Branded storefront per tenant.
- Product catalog with variants and reviews.
- Abandoned cart recovery.
- Loyalty points and transactions.
- Saved payment methods (PCI-compliant tokenization).
- Stock alerts and newsletter subscriptions.

### 2.8 AI Assistant

- Intelligent chat with natural language understanding.
- Pricing recommendations based on margin and demand.
- Sales forecasting and demand prediction.
- Customer behavior analysis.
- RBAC-hardened: every action requires permission; sensitive actions require confirmation.

### 2.9 Reporting & Analytics

- Financial reports: income statement, balance sheet, trial balance, cash flow.
- Inventory reports: stock valuation, movement log, reconciliation.
- Sales reports: by product, customer, branch, period.
- Custom dashboards with widget configuration.
- Export to PDF and Excel.

## 3. Technical Architecture

| Layer | Technology |
|-------|------------|
| Backend | Python 3.11, Flask, SQLAlchemy |
| Database | PostgreSQL 15 |
| Cache / Broker | Redis |
| Tasks | Celery |
| Frontend | AdminLTE, Bootstrap, Tajawal font |
| AI | Custom neural engine, reasoning engine |
| Hosting | Docker-ready, cloud VPS |

## 4. Security & Compliance

- Tenant isolation enforced at the ORM level.
- Role-based access control (RBAC) with fine-grained permissions.
- AES-256 encryption for backups and card data.
- TLS 1.3 for all data in transit.
- Audit logs for every transaction.
- UAE PDPL compliant. PCI DSS and ISO 27001 in progress.

## 5. Pricing

| Plan | Users | Branches | Price (AED/month) |
|------|-------|----------|-------------------|
| Starter | 3 | 1 | 299 |
| Professional | 10 | 3 | 799 |
| Enterprise | Unlimited | Unlimited | 1,999 |

Add-ons: Extra user (+49 AED), Extra branch (+149 AED), AI credits (pay-as-you-go).

All plans include: free onboarding, data migration assistance, 24/7 support, and automatic updates.

## 6. Getting Started

1. **Book a free demo** — 30-minute guided tour.
2. **Choose your plan** — Starter, Professional, or Enterprise.
3. **Start immediately** — Tenant provisioning takes under 5 minutes.
4. **Import your data** — We assist with Excel/CSV migration.
5. **Train your team** — Free training sessions for up to 5 users.

## 7. Contact

AZAD Intelligent Systems
Eng. Ahmad Ghannam, Founder & CTO
Email: rafideen.ahmadghannam@gmail.com
Phone: +972 56 215 0193 / 056 215 0193
