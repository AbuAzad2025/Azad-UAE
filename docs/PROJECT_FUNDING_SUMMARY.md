# Project & Funding Summary Report

**Product:** Azadexa (أزاديكسا) — Intelligent ERP, Accounting & Commerce Platform
**Company:** AZAD Intelligent Systems
**Report Date:** July 2026
**Repository:** `AbuAzad2025/Azad-UAE`

---

## 1. Sponsorship & Funding Setup

### Current FUNDING.yml Configuration

```yaml
github: AbuAzad2025

custom:
  - "[WhatsApp — IBAN Sponsorship](https://wa.me/972562150193?text=Hello%20AZAD%20Team,%20I%20want%20to%20support/sponsor%20the%20GitHub%20repository%20via%20IBAN)"
  - "[Email — IBAN Sponsorship](mailto:rafideen.ahmadghannam@gmail.com?subject=GitHub%20Repository%20Sponsorship%20%26%20IBAN)"
```

### Verified Direct Channels

| Channel | Configuration | Purpose |
|---------|--------------|---------|
| **GitHub Sponsors** | `AbuAzad2025` | Native GitHub Sponsors page for one-time and recurring sponsorships |
| **WhatsApp** | `+972 56 215 0193` | Pre-filled message directing to IBAN bank transfer sponsorship |
| **Email** | `rafideen.ahmadghannam@gmail.com` | Pre-filled subject line for IBAN bank transfer sponsorship inquiries |

### Visitor Interaction Flow

1. Repository visitor clicks the **"Sponsor"** button on the GitHub repository page.
2. GitHub renders the `FUNDING.yml` configuration as a funding card with three options:
   - **"Sponsor AbuAzad2025"** — Opens the GitHub Sponsors profile for direct platform sponsorship.
   - **"WhatsApp"** — Opens WhatsApp with a pre-filled message: *"Hello AZAD Team, I want to support/sponsor the GitHub repository via IBAN"*.
   - **"Email"** — Opens the default mail client with subject: *"GitHub Repository Sponsorship & IBAN"*.
3. All channels route directly to AZAD Intelligent Systems — no third-party intermediaries.

---

## 2. Repository & Product Overview

### Platform Purpose

Azadexa is a multi-tenant SaaS ERP platform designed for SMEs in the UAE and GCC region. It provides end-to-end business management across sales, purchasing, inventory, accounting, HR, payroll, e-commerce, and payments — with full tenant isolation and bilingual (Arabic/English) support.

### High-Level Architecture

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.14, Flask 3.1, SQLAlchemy 2.0 |
| Database | PostgreSQL with connection pooling |
| Caching | Redis |
| Task Queue | Celery |
| Real-time | WebSocket (SocketIO) |
| API | REST + GraphQL + OpenAPI |
| Payments | NOWPayments (crypto), Stripe, encrypted card vault |
| Testing | 10,000+ unit tests, integration & E2E suites |
| Security | CSRF, rate limiting, CSP headers, tenant ORM isolation |

### Key Presentation Files

| File | Status | Description |
|------|--------|-------------|
| `README.md` | ✅ Updated | B2B commercial presentation — product capabilities, pricing, architecture, and contact information |
| `AGENTS.md` | ✅ Updated | Internal AZAD Engineering Guidelines — transaction safety, tenant isolation, architecture layers, code style |
| `LICENSE` | ✅ Current | Proprietary — All Rights Reserved |
| `.github/FUNDING.yml` | ✅ Updated | GitHub Sponsors + WhatsApp IBAN + Email IBAN channels |
| `docs/GRIMOIRE.md` | ✅ Current | Full engineering standards reference |

### Target Audience

- **Primary:** B2B enterprise clients — auto parts dealers, retail chains, supermarkets, restaurants, and workshops in UAE/GCC.
- **Secondary:** Platform investors and technology partners evaluating the SaaS architecture.
- **Tenant Storefronts:** Each tenant receives a dedicated e-commerce storefront tied to its own inventory and accounting.

---

## 3. Commercial & Go-To-Market (GTM) Readiness

### Enterprise Features Ready for Presentation

| Category | Features |
|----------|----------|
| **Core ERP** | Multi-tenant isolation, branch-aware workflows, role-based access control |
| **Accounting** | Double-entry GL with dynamic mapping, journal entries, trial balance, balance sheet, income statement, cost centers, budgets, fixed asset depreciation |
| **Inventory** | Multi-warehouse, barcode/QR scanning, batch & serial tracking, MWAC/WAC costing, expiry alerts, stock transfers |
| **POS** | Touch-optimized interface, split tender, parked carts, manager overrides, promotions engine, e-invoicing with QR |
| **E-Commerce** | Per-tenant storefront with cart, checkout, coupons, loyalty, reviews, wishlist, stock alerts |
| **Payments** | NOWPayments (crypto), Stripe, encrypted card vault, cheque lifecycle, bank reconciliation |
| **HR & Payroll** | Employee profiles, attendance, leave management, payroll processing, loans & overtime |
| **AI Analytics** | Native AI assistant with Arabic language support, sales forecasting, anomaly detection |
| **Integrations** | REST API, GraphQL, WhatsApp, webhooks, OpenAPI documentation |
| **Multi-Currency** | Live exchange rates, FX revaluation, AED base currency |
| **Bilingual** | Full Arabic/English with RTL layout support |

### Pricing Structure

| Plan | Monthly | Users | Key Inclusions |
|------|---------|-------|----------------|
| Starter | $29 | Up to 3 | Sales, purchases, inventory, e-invoices, basic reports |
| Professional | $79 | Up to 10 | All Starter + GL, POS, online store, AI features, advanced reports |
| Enterprise | $249 | Unlimited | All features + HR/payroll, AI insights, daily backups, 24/7 support |

### License & Repository Privacy

- **License:** Proprietary — All Rights Reserved
- **Repository visibility:** Public (for project tracking and continuity)
- **No public license granted** for copying, modification, redistribution, hosting, or commercialization
- **Source code access:** Controlled — available only to authorized AZAD engineers and approved partners

### Recommended Next Steps

| Priority | Action | Purpose |
|----------|--------|---------|
| **P1** | Activate GitHub Sponsors profile with tiered sponsorship plans | Enable recurring sponsorship revenue directly from the repository |
| **P1** | Create a live demo environment using the existing `seed-demo` CLI command | Provide investor and client walkthroughs with realistic GCC enterprise data |
| **P2** | Publish `docs/architecture.md`, `docs/user-guide.md`, `docs/api.md` | Enable self-service technical evaluation by enterprise prospects |
| **P2** | Set up a public-facing landing page at `azadsystems.com` with pricing and trial signup | Drive organic inbound leads for the sales team |
| **P3** | Register the repository on relevant SaaS directories (Capterra, G2, Product Hunt) | Increase discoverability for UAE/GCC SME buyers |
| **P3** | Create a short product demo video (2-3 minutes) for the repository and landing page | Provide a quick visual overview for investors and clients |

---

## Contact

**AZAD Intelligent Systems** | شركة أزاد للأنظمة الذكية

| Channel | Contact Info |
|---|---|
| Direct Email | rafideen.ahmadghannam@gmail.com |
| Phone / WhatsApp | +972 56 215 0193 |
| WhatsApp Direct | [Message Us](https://wa.me/972562150193) |

© 2026 AZAD Intelligent Systems — All Rights Reserved.
