# Future Roadmap: Dynamic GL Account Mapping

**Status:** Approved & Scheduled (Aligned with Target ERP Architecture)  
**Date:** June 4, 2026  
**Recommended Priority:** HIGH (Phase 3)  
**Estimated Effort:** 4-5 Sprints  

---

## 1. Goal & Reference ERP Standards
Replace all hardcoded GL account code literals (e.g. `'1130'`, `'2110'`, `'1140'`, `'5100'`, `'5110'`) in posting services and background logic with a **configurable per-tenant GL Account Mapping registry**. 
- **Strategic Purpose:** Allow tenants in Palestine, GCC, and future international markets to use their own localized charts of accounts (such as standard Bisan or Al-Shamel numbers) without modifying the application code.
- **Reference Models:** SAP Business One, Oracle NetSuite, Odoo posting rules engines.
- **Decision DM-12:** **Approved.** Phase 1: Mappings resolved per tenant. Future: Optional branch overrides.

---

## 2. Core Posting Rules Engine Templates
Business logic must be completely decoupled from database account codes. Services will delegate to a Posting Rules Engine which resolves **GL Concepts** to actual account IDs via `GLAccountMapping` and generates journal lines.

### 2.1 Cash Sale Posting Template
- **Debit:** `CASH` (amount = sales total + VAT)
- **Credit:** `SALES_REVENUE` (amount = sales net value)
- **Credit:** `VAT_OUTPUT` (amount = tax value)
- **Debit:** `COGS` (amount = MWAC inventory cost)
- **Credit:** `INVENTORY_ASSET` (amount = MWAC inventory cost)

### 2.2 Credit Sale Posting Template
- **Debit:** `AR` (amount = invoice total + VAT)
- **Credit:** `SALES_REVENUE` (amount = invoice net value)
- **Credit:** `VAT_OUTPUT` (amount = tax value)
- **Debit:** `COGS` (amount = MWAC inventory cost)
- **Credit:** `INVENTORY_ASSET` (amount = MWAC inventory cost)

### 2.3 Inventory Purchase Template (On Credit)
- **Debit:** `INVENTORY_ASSET` (amount = base cost + capitalized landed cost)
- **Debit:** `VAT_INPUT` (amount = recoverable tax)
- **Credit:** `AP` (amount = total vendor invoice)

### 2.4 Incoming Cheque Template
- **Debit:** `CHEQUES_UNDER_COLLECTION` (amount = cheque face value)
- **Credit:** `AR` (amount = credit reduction)

---

## 3. Account Structure Principle: Accounts vs. Dimensions
To prevent the expansion of account trees (e.g. creating different accounts for different branches or locations), the system adopts the standard ERP dimension model:
- **Accounts** represent the financial classification (*What type of money is this?*).
- **Dimensions** represent the context (*Where, why, and for whom did it happen?*).

### 3.1 Tree Explosion Prohibited
- **Incorrect Chart Setup:** `Sales_Ramallah_Store`, `Sales_Nablus_Store`, `Inventory_Hebron_Warehouse`.
- **Correct Setup:** A single sales account (`SALES_REVENUE`) and a single stock asset account (`INVENTORY_ASSET`), with transactions tagged with financial dimensions.

### 3.2 Financial Dimensions Registry
The posting rules engine applies and validates the following dimensions on every journal line:
- `tenant_id`: Mandatory logical tenant isolation.
- `branch_id`: Branch-level identity and performance tracking.
- `warehouse_id`: Stock warehouse.
- `cost_center_id`: Expense tracking (e.g., department, project, vehicle).
- `profit_center_id`: Profitability tracking (e.g., branch, product line).
- `partner_id`: Customer or vendor sub-ledger link.
- `currency`: Base and transaction currency.
- `payment_channel`: Cashier box, payment gateway, or bank account.

---

## 4. Technical Approach & Schema Design

### 4.1 Concept Registry (Core GL Concepts)
The core mapping registry supports the following standardized GL Concepts:
1. `AR`: Accounts Receivable
2. `AP`: Accounts Payable
3. `CASH`: Cash on Hand
4. `BANK`: Bank Balances
5. `INVENTORY_ASSET`: Stock Asset Value
6. `SALES_REVENUE`: Revenue from Sales
7. `SALES_DISCOUNT`: Customer Discounts Granted
8. `PURCHASE_DISCOUNT`: Vendor Discounts Earned
9. `COGS`: Cost of Goods Sold
10. `VAT_INPUT`: Paid VAT on Procurement (Recoverable Asset)
11. `VAT_OUTPUT`: Collected VAT on Sales (Liability)
12. `FX_GAIN`: Foreign Exchange Gain (P&L Revenue)
13. `FX_LOSS`: Foreign Exchange Loss (P&L Expense)
14. `CHEQUES_UNDER_COLLECTION`: Received post-dated cheques
15. `INVENTORY_ADJUSTMENT_GAIN`: Gains from positive stock counts
16. `INVENTORY_ADJUSTMENT_LOSS`: Write-offs from stock shrinkage/obsolescence
17. `FREIGHT_IN`: Capitalized Freight/Shipping
18. `CUSTOMS_DUTY`: Capitalized Customs Duties

### 4.2 Data Model: `GLAccountMapping`
```python
class GLAccountMapping(db.Model):
    """
    Maps a business concept (e.g., INVENTORY_ASSET) to a tenant's specific GL account.
    """
    __tablename__ = 'gl_account_mappings'
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'concept_code', 'branch_id',
                            name='uq_gl_mapping_tenant_concept_branch'),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False, index=True)

    concept_code = db.Column(db.String(50), nullable=False, index=True) # e.g. 'INVENTORY_ASSET'
    gl_account_id = db.Column(db.Integer, db.ForeignKey('gl_accounts.id'), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True, index=True) # Optional override

    is_active = db.Column(db.Boolean, default=True, nullable=False)
    notes = db.Column(db.Text)

    tenant = db.relationship('Tenant', backref='gl_mappings')
    gl_account = db.relationship('GLAccount')
    branch = db.relationship('Branch')

    @classmethod
    def get_account(cls, tenant_id, concept_code, branch_id=None):
        """Resolves the active GL account for a concept, applying branch override fallback."""
        if branch_id:
            mapping = cls.query.filter_by(
                tenant_id=tenant_id, concept_code=concept_code,
                branch_id=branch_id, is_active=True
            ).first()
            if mapping:
                return mapping.gl_account
        mapping = cls.query.filter_by(
            tenant_id=tenant_id, concept_code=concept_code,
            branch_id=None, is_active=True
        ).first()
        if mapping:
            return mapping.gl_account
        raise GLMappingError(f"No GL mapping found for concept '{concept_code}' in tenant {tenant_id}")
```

---

## 5. Segmented Modeling & Controls

### 5.1 Tenant Isolation
Ledger configuration data (mappings, accounts, journal balances, cost centers) must be strictly isolated per tenant. Under no circumstances can a user of Tenant A query or view configurations or journals of Tenant B. Mappings are scoped via `tenant_id` at the database index layer.

### 5.2 Branch Model
A branch represents a reporting and operational dimension, not a separate chart of accounts. A branch is defined by:
- Branch Identity and user permissions.
- Assigned Bank Accounts and Cash registers.
- Assigned Warehouses.
- Cost/Profit Center allocations.
All branch transactions flow to the central chart of accounts but are tagged with `branch_id`.

### 5.3 Warehouse Model
- A warehouse is primarily an operational stock tracking location.
- **Enterprise Override Mapping:** Mappings support optional warehouse-level overrides. Larger enterprises can route specific warehouse stock transactions to distinct asset accounts (e.g. mapping `INVENTORY_ASSET` for Warehouse A to a separate GL account).

### 5.4 Cost Centers & Profit Centers
- **Branch = Profit Center:** The profit center dimension tracks branch performance.
- **Project/Fleet = Cost Center:** Overheads are captured under specific `cost_center_id` tags.
- Postings validate and assign cost/profit centers on a line-item basis, feeding departmental P&L reports.

### 5.5 Treasury & Cash Management
The roadmap integrates:
- **Multiple Cash Boxes:** Tracked per cashier per branch.
- **Multiple Bank Accounts:** Centrally managed, assigned to branches.
- **Employee Advances:** Tracked as temporary receivables.
- **Cash Positioning:** Real-time cash position reporting aggregates cash registers, bank balances, and cheques under collection.

---

## 6. Implementation Sprints & Phase Roadmap

### Sprint 1: Table Creation & Data Migration
- Add `gl_account_mappings` table.
- Seed default mappings for existing tenants using standard fallback mappings.

### Sprint 2: Resolution Integration
- Implement `GLAccountMapping.get_account()` query helper.
- Update `GLService` to resolve account codes dynamically via concept queries.

### Sprint 3: Core Service Refactoring
- Replace hardcoded string codes (e.g., `'1130'`, `'2110'`) in Sales, Purchase, and Payment services with concept resolutions.
- Conduct regressions to verify that generated entries match legacy codes exactly for default charts.

### Sprint 4: UI Configuration Panel & Templates
- Develop a "GL Account Mapping" admin screen for tenants to customize their mappings.
- Seed standard chart templates (e.g., UAE Standard, Palestine Standard, Manufacturing).

---

## 7. Migration Risks & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Tenant chart modifications break posting logic | High | High | Enforce database validation rules that block deleting GL accounts that have active mappings. |
| Performance overhead of mapping query lookups | Low | Low | Implement lookup caching in the application configuration context. |
| Missing mapping at posting time | Medium | High | Add validation checks in UI that prevent saving configurations if mandatory concepts (AR, AP, COGS) are unmapped. |
