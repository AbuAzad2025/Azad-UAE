# Company Profile — AZAD Intelligent Systems

## 1. Overview

| Attribute | Value |
|-----------|-------|
| Legal name | AZAD Intelligent Systems |
| Arabic name | شركة أزاد للأنظمة الذكية |
| Trade name | Azadexa |
| Industry | Enterprise Software / SaaS |
| Founded | 2024 |
| Headquarters | Ramallah, Palestine |
| Primary market | United Arab Emirates |
| Product | Azadexa ERP — Multi-tenant SaaS platform |
| Founder & CTO | Eng. Ahmad Ghannam |
| Contact | rafideen.ahmadghannam@gmail.com |
| Phone | +972 56 215 0193 |

## 2. Mission

Build intelligent, secure, and scalable ERP systems that empower businesses in the Arab world to operate with precision, efficiency, and data-driven confidence.

## 3. Vision

Become the leading ERP provider for SMEs and enterprises across the Middle East and North Africa by 2030, powered by AI and multi-tenant cloud architecture.

## 4. Core Values

| Value | Definition |
|-------|------------|
| Precision | Every transaction is accurate. Every number is trustworthy. |
| Security | Tenant isolation and data protection are non-negotiable. |
| Intelligence | AI is not a feature — it is a foundation. |
| Simplicity | Complex operations should feel intuitive. |
| Ownership | We own our code, our uptime, and our customer's success. |

## 5. Product: Azadexa ERP

Azadexa is a comprehensive multi-tenant ERP built on Flask + SQLAlchemy + PostgreSQL. It currently includes:

| Module | Key Capabilities |
|--------|-----------------|
| General Ledger | Double-entry accounting, dynamic GL mapping, trial balance, financial statements |
| Accounts Payable / Receivable | Aging analysis, reconciliation, automated reminders |
| Inventory | Multi-warehouse, WAC/MWAC, serial tracking, reconciliation |
| Sales & Purchases | Invoicing, quotations, returns, commissions |
| POS | Multi-channel POS, promotions (tiered/BOGO/bundle/combo), split tender, RMA |
| HR & Payroll | Attendance, leave, contracts, payroll processing, accruals |
| CRM | Lead pipeline, stages, teams, activities |
| Projects | Tasks, timesheets, billing, member management |
| E-commerce | Storefront, abandoned cart, wishlist, reviews, loyalty |
| AI Assistant | RBAC-hardened action dispatcher, pricing recommendations, forecasting |
| Treasury | Cash flow, liquidity position, bank reconciliation |
| Fixed Assets | Depreciation schedules (straight-line, declining balance) |
| Cheques | Full lifecycle: receive, deposit, clear, bounce, cancel |
| Multi-currency | FX rates, AED quantization, unrealized revaluation |
| External Sync | API-key authenticated stock sync for external POS systems |

## 6. Technology Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.11, Flask, SQLAlchemy |
| Database | PostgreSQL 15 (REPEATABLE READ isolation) |
| Cache / Broker | Redis |
| Task Queue | Celery |
| Frontend | AdminLTE, Bootstrap, vanilla JS |
| AI Engine | Custom neural engine in `ai_knowledge/` |
| Search | Full-text search via PostgreSQL + custom indexing |
| Hosting | Cloud VPS / Docker-ready |

## 7. Competitive Differentiation

| Feature | Azadexa | Typical Competitor |
|---------|---------|-------------------|
| Multi-tenant SaaS | Built-in, ORM-enforced | Often single-tenant or add-on |
| AI integration | RBAC + confirmation gates | Generic chatbot |
| POS sync | Native API with idempotency | Manual import or third-party |
| FX revaluation | Automated month-end | Manual spreadsheet |
| Tenant branding | Per-tenant logo, favicon, letterhead | Platform-branded only |
| Arabic-first UI | Native RTL, Arabic reports, UAE VAT | Translated overlay |
| OpenAPI docs | Auto-generated | Often missing |

## 8. Target Customer Segments

| Segment | Size | Needs |
|---------|------|-------|
| Retail & Wholesale | 5–50 employees | POS, inventory, multi-branch |
| Auto Parts | 3–30 employees | Serial tracking, compatibility, 3 price tiers |
| Supermarkets | 10–100 employees | Fast POS, promotions, shelf labels |
| Restaurants | 5–40 employees | Table management, KDS, split bills |
| Trading Companies | 5–20 employees | Purchases, sales, GL, cheques |
| Service Firms | 3–15 employees | Projects, CRM, invoicing |
| Construction | 10–50 employees | Projects, payroll, multi-warehouse |

## 9. Pricing Model

| Plan | Users | Branches | Modules | Price (AED/month) |
|------|-------|----------|---------|-------------------|
| Starter | 3 | 1 | Core + Sales + Inventory | 299 |
| Professional | 10 | 3 | All except AI + E-commerce | 799 |
| Enterprise | Unlimited | Unlimited | All modules + API + AI | 1,999 |

Add-ons: Extra user (+49 AED), Extra branch (+149 AED), AI credits (pay-as-you-go).

## 10. Contact

AZAD Intelligent Systems
Eng. Ahmad Ghannam, Founder & CTO
Email: rafideen.ahmadghannam@gmail.com
Phone: +972 56 215 0193 / 056 215 0193
Location: Ramallah, Palestine — Serving the UAE and MENA region.
