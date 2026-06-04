# Future Roadmap: Dynamic GL Account Mapping

**Status:** Planned — awaiting owner approval on DM-12  
**Recommended Priority:** HIGH (Phase 3)  
**Estimated Effort:** 4-5 sprints  
**Accounting Standard:** Concept-based GL mapping per tenant with optional branch override

---

## 1. Goal

Replace all **hardcoded GL account codes** (e.g., `'1130'`, `'2110'`, `'5100'`) across services and posting logic with a **configurable per-tenant GL Account Mapping** system. This allows each tenant to customize their chart of accounts without breaking automated posting logic, and aligns with the ERP Accounting Principles mandate that all postings use concept-based mappings.

**Key constraints from ERP Accounting Principles:**
- No hardcoded account codes in posting logic.
- Use concept mapping: `AR`, `AP`, `INVENTORY_ASSET`, `SALES_REVENUE`, `COGS`, etc.
- Tenant-level mapping as default; optional branch override as Phase 2.
- All decisions require owner approval.

---

## 2. Current Problem

### 2.1 Hardcoded Account Codes
Multiple services reference GL account codes as string literals:

| Code | Hardcoded Location | Purpose | Target Concept |
|------|-------------------|---------|----------------|
| `'1130'` | `services/gl_service.py`, `services/gl_posting.py` | Accounts Receivable (AR) | `AR` |
| `'2110'` | `services/gl_service.py` | Accounts Payable (AP) | `AP` |
| `'1140'` | `services/gl_service.py`, `runtime_core/accounting_repair.py` | Inventory Asset | `INVENTORY_ASSET` |
| `'5100'` | `services/gl_posting.py` | Revenue / Sales | `SALES_REVENUE` |
| `'5110'` | `services/gl_posting.py` | COGS | `COGS` |
| `'1200'` | `services/gl_service.py` | Cash / Bank default | `CASH` / `BANK` |

### 2.2 Tenant Customization Blocked
- Tenants cannot rename or restructure their chart of accounts without breaking automated journal entries.
- If a tenant deletes or changes code `1130`, all sales postings fail with `GLAccountNotFound`.
- The system assumes a **fixed chart template**, but real businesses have varying account numbering schemes.

### 2.3 Maintenance Burden
- Adding a new posting rule requires finding and updating every hardcoded reference.
- Refactoring is high-risk because a missed literal causes silent posting failures.

---

## 3. Business Decision Required (Requires Owner Approval)

### Decision DM-12: GL Mapping Granularity
**Question:** At what level should GL account mappings be defined?

| Option | Pros | Cons |
|--------|------|------|
| **Per tenant** ✅ | Simple; unified books; easy consolidation | All branches share same account codes |
| Per branch | Supports branch-specific accounting | More complex UI and validation |
| Per warehouse | Maximum granularity | Overkill; warehouse is operational, not accounting |

**Recommended:** **Per tenant** (Phase 1), with optional branch override (Phase 2).

**Rationale:** Most tenants use unified books. Branch override is an advanced feature for holding companies or franchises. Starting with tenant-level keeps Phase 1 simple and deliverable.

**Financial Impact:** Unified books simplify consolidation. Branch override adds flexibility later.

**Audit Impact:** Mapping changes are auditable per tenant. Branch overrides are auditable per branch.

**Technical Impact:** Tenant-level: simple `tenant_id` + `concept_code` unique constraint. Branch override: add nullable `branch_id` with fallback logic.

**Requires Owner Approval:** **Yes** 🔒

---

## 4. Technical Approach

### 4.1 Concept Registry

Standard concepts the system must support (derived from ERP Accounting Principles):

```python
# utils/gl_concepts.py
class GLConcept:
    # Core inventory & cost
    INVENTORY_ASSET = 'INVENTORY_ASSET'
    COGS = 'COGS'
    COGS_REVERSAL = 'COGS_REVERSAL'

    # Revenue
    SALES_REVENUE = 'SALES_REVENUE'
    SALES_RETURNS = 'SALES_RETURNS'
    SALES_DISCOUNT = 'SALES_DISCOUNT'

    # Receivables / Payables
    AR = 'AR'
    AP = 'AP'

    # Cash & Bank
    CASH = 'CASH'
    BANK = 'BANK'

    # VAT
    VAT_INPUT = 'VAT_INPUT'
    VAT_OUTPUT = 'VAT_OUTPUT'

    # Inventory adjustments
    INVENTORY_ADJUSTMENT_GAIN = 'INVENTORY_ADJUSTMENT_GAIN'
    INVENTORY_ADJUSTMENT_LOSS = 'INVENTORY_ADJUSTMENT_LOSS'

    # Landed costs
    FREIGHT_IN = 'FREIGHT_IN'
    CUSTOMS_DUTY = 'CUSTOMS_DUTY'

    # Purchase
    PURCHASE_DISCOUNT = 'PURCHASE_DISCOUNT'

    # FX
    FX_GAIN = 'FX_GAIN'
    FX_LOSS = 'FX_LOSS'

    # Additional concepts for future expansion
    SALARY_EXPENSE = 'SALARY_EXPENSE'
    RENT_EXPENSE = 'RENT_EXPENSE'
    SHIPPING_EXPENSE = 'SHIPPING_EXPENSE'
```

### 4.2 New Model: `GLAccountMapping`

```python
class GLAccountMapping(db.Model):
    """Maps a business concept to a tenant's GL account."""
    __tablename__ = 'gl_account_mappings'
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'concept_code', 'branch_id',
                            name='uq_gl_mapping_tenant_concept_branch'),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False, index=True)

    concept_code = db.Column(db.String(50), nullable=False, index=True)
    """
    Examples: SALES_REVENUE, COGS, AR, AP, INVENTORY_ASSET,
              CASH, BANK, VAT_OUTPUT, VAT_INPUT, INVENTORY_ADJUSTMENT_GAIN,
              INVENTORY_ADJUSTMENT_LOSS, FREIGHT_IN, CUSTOMS_DUTY,
              PURCHASE_DISCOUNT, SALES_DISCOUNT, FX_GAIN, FX_LOSS
    """

    gl_account_id = db.Column(db.Integer, db.ForeignKey('gl_accounts.id'), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True, index=True)

    is_active = db.Column(db.Boolean, default=True, nullable=False)
    notes = db.Column(db.Text)

    tenant = db.relationship('Tenant', backref='gl_mappings')
    gl_account = db.relationship('GLAccount')
    branch = db.relationship('Branch')

    @classmethod
    def get_account(cls, tenant_id, concept_code, branch_id=None):
        """Resolve a concept to a GLAccount instance. Branch override takes precedence."""
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
        raise GLMappingError(
            f"No GL mapping found for concept '{concept_code}' in tenant {tenant_id}"
        )
```

### 4.3 Service Refactoring

**Before (current):**
```python
def post_sale(sale):
    ar_account = GLAccount.query.filter_by(code='1130', tenant_id=sale.tenant_id).first()
    revenue_account = GLAccount.query.filter_by(code='5100', tenant_id=sale.tenant_id).first()
    cogs_account = GLAccount.query.filter_by(code='5110', tenant_id=sale.tenant_id).first()
    inventory_account = GLAccount.query.filter_by(code='1140', tenant_id=sale.tenant_id).first()
```

**After (target):**
```python
def post_sale(sale):
    ar_account = GLAccountMapping.get_account(
        sale.tenant_id, GLConcept.AR, sale.branch_id
    )
    revenue_account = GLAccountMapping.get_account(
        sale.tenant_id, GLConcept.SALES_REVENUE, sale.branch_id
    )
    cogs_account = GLAccountMapping.get_account(
        sale.tenant_id, GLConcept.COGS, sale.branch_id
    )
    inventory_account = GLAccountMapping.get_account(
        sale.tenant_id, GLConcept.INVENTORY_ASSET, sale.branch_id
    )
```

### 4.4 Seed / Template System

```python
class GLTemplateService:
    TEMPLATES = {
        'uae_standard': {
            'SALES_REVENUE': '5100',
            'COGS': '5110',
            'AR': '1130',
            'AP': '2110',
            'INVENTORY_ASSET': '1140',
            'CASH': '1200',
            'BANK': '1210',
            'VAT_INPUT': '1170',
            'VAT_OUTPUT': '2120',
            'INVENTORY_ADJUSTMENT_GAIN': '5200',
            'INVENTORY_ADJUSTMENT_LOSS': '6100',
            'FREIGHT_IN': '1150',
            'CUSTOMS_DUTY': '1160',
            'PURCHASE_DISCOUNT': '2100',
            'SALES_DISCOUNT': '5300',
            'FX_GAIN': '5400',
            'FX_LOSS': '6200',
        },
        'retail_simplified': {
            'SALES_REVENUE': '4000',
            'COGS': '5000',
            'AR': '1100',
            'AP': '2000',
            'INVENTORY_ASSET': '1300',
            'CASH': '1000',
            'BANK': '1010',
        },
        'manufacturing': {
            'SALES_REVENUE': '5100',
            'COGS': '5110',
            'AR': '1130',
            'AP': '2110',
            'INVENTORY_ASSET': '1140',
            'CASH': '1200',
            'BANK': '1210',
            'FREIGHT_IN': '1150',
            'CUSTOMS_DUTY': '1160',
        },
    }

    @classmethod
    def apply_template(cls, tenant_id, template_name):
        """Create GLAccountMapping rows for a tenant based on a template."""
```

### 4.5 Admin UI

- New page under Owner/Admin: **"GL Account Mapping"**
- Table showing concept → account for the current tenant.
- Dropdown to switch between templates (UAE Standard, Retail Simplified, Manufacturing).
- Validation: warn if a mapped `GLAccount` is inactive or a header account.
- Required-flag: mark mandatory concepts (`AR`, `AP`, `INVENTORY_ASSET`, `SALES_REVENUE`, `COGS`) in red if unmapped.
- Branch override section (Phase 2): show tenant-level mapping with option to override per branch.

---

## 5. Migration Risk

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Tenants with custom charts have no mapping on go-live | High | High | Auto-populate from existing hardcoded defaults during migration |
| Service code missed during refactoring | Medium | High | Use `grep` to find all hardcoded 4-digit codes; enforce via code review checklist |
| Circular import if `GLConcept` is imported everywhere | Low | Medium | Keep `GLConcept` in a lightweight `utils/gl_concepts.py`; no database imports |
| Performance overhead of mapping lookup | Low | Low | Cache mappings per tenant in `app.config` or Redis; lookups are trivial |
| Branch override logic becomes complex | Medium | Medium | Phase 1: tenant-only. Phase 2: add branch override after stabilization |

---

## 6. Testing Plan

### 6.1 Unit Tests
- `test_mapping_resolution()` — concept resolves to correct account.
- `test_mapping_branch_fallback()` — branch-specific mapping overrides tenant-level.
- `test_mapping_missing_raises()` — missing mapping raises `GLMappingError`.

### 6.2 Integration Tests
- End-to-end sale posting with dynamic mapping.
- End-to-end purchase posting with dynamic mapping.
- Template application: apply `uae_standard` and verify all concepts are mapped.

### 6.3 Regression Tests
- Run the full test suite after replacing hardcoded codes in each service.
- Compare generated journal entries before/after refactoring; assert identical output for default mappings.

### 6.4 Migration Tests
- `test_migration_populates_defaults()` — existing tenants get default mappings.
- `test_migration_preserves_posting()` — posting behavior is unchanged for tenants using default chart.

---

## 7. Rollback Strategy

1. **Feature flag:** `ENABLE_DYNAMIC_GL_MAPPING` (default `False` initially).
2. **Dual-path code:** During transition, keep a compatibility layer:
   ```python
   if app.config.get('ENABLE_DYNAMIC_GL_MAPPING'):
       account = GLAccountMapping.get_account(...)
   else:
       account = GLAccount.query.filter_by(code='1130').first()  # legacy
   ```
3. **Migration is additive:** New `gl_account_mappings` table does not alter existing data.
4. **Downgrade:** Drop `gl_account_mappings` table; revert service code to hardcoded lookups.

---

## 8. Recommended Priority

**HIGH (Phase 3)**

Rationale:
- Unblocks tenant customization — a major competitive requirement.
- Reduces long-term maintenance cost of hardcoded literals.
- Required before onboarding tenants with non-standard charts (e.g., franchises, holding companies).
- Lower urgency than MWAC because current hardcoded system "works" for default tenants, but is a prerequisite for MWAC GL integration.

**Dependencies:**
- Batch 1-5 must be stable.
- `GLAccount` model must support tenant-scoped accounts (already true).

**Suggested Start Date:** After MWAC Phase 1-2 implementation, or in parallel if resources allow.

---

*Roadmap document updated: June 4, 2026*  
*Aligned with ERP Accounting Principles v1.0*
