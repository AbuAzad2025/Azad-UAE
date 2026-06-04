# Future Roadmap: Dynamic GL Account Mapping

**Status:** Planned — awaiting business approval  
**Recommended Priority:** HIGH (Phase 3)  
**Estimated Effort:** 4-5 sprints

---

## 1. Goal

Replace all **hardcoded GL account codes** (e.g., `'1130'`, `'2110'`, `'5100'`) across services and posting logic with a **configurable per-tenant GL Account Mapping** system. This allows each tenant to customize their chart of accounts without breaking automated posting logic.

---

## 2. Current Problem

### 2.1 Hardcoded Account Codes
Multiple services reference GL account codes as string literals:

| Code | Hardcoded Location | Purpose |
|------|-------------------|---------|
| `'1130'` | `services/gl_service.py`, `services/gl_posting.py` | Accounts Receivable (AR) |
| `'2110'` | `services/gl_service.py` | Accounts Payable (AP) |
| `'1140'` | `services/gl_service.py`, `runtime_core/accounting_repair.py` | Inventory Asset |
| `'5100'` | `services/gl_posting.py` | Revenue / Sales |
| `'5110'` | `services/gl_posting.py` | COGS |
| `'1200'` | `services/gl_service.py` | Cash / Bank default |

### 2.2 Tenant Customization Blocked
- Tenants cannot rename or restructure their chart of accounts without breaking automated journal entries.
- If a tenant deletes or changes code `1130`, all sales postings fail with `GLAccountNotFound`.
- The system assumes a **fixed chart template**, but real businesses have varying account numbering schemes.

### 2.3 Maintenance Burden
- Adding a new posting rule requires finding and updating every hardcoded reference.
- Refactoring is high-risk because a missed literal causes silent posting failures.

---

## 3. Business Decision Required

### Decision 1: Mapping Granularity
**Question:** Should the mapping be per **tenant** or per **branch**?

| Option | Pros | Cons |
|--------|------|------|
| Per-tenant mapping | Simple; one mapping table per tenant | All branches share the same account codes |
| Per-branch mapping | Supports branch-specific accounting (e.g., separate books per branch) | More complex UI and validation |

**Recommended:** Per-tenant mapping with **optional branch override**. Most tenants use unified books; branch overrides are an advanced feature.

### Decision 2: Mapping Entity Scope
**Question:** Should the system map **business concepts** (e.g., `SALES_REVENUE`) or **specific posting rules** (e.g., `SALE_POSTING_DEBIT`, `SALE_POSTING_CREDIT`)?

| Option | Pros | Cons |
|--------|------|------|
| Concept mapping (e.g., `SALES_REVENUE` → account) | Simple; ~20 concepts to map | Less flexible for complex multi-account rules |
| Rule-level mapping (e.g., `SALE_POSTING_DEBIT` → account) | Maximum flexibility | Larger mapping table; harder UI |

**Recommended:** Concept mapping for Phase 1, with a path to rule-level mapping in Phase 2. Start with the 15-20 most common concepts.

### Decision 3: Default Chart Templates
**Question:** Should the system ship with **pre-built chart templates** (e.g., UAE GAAP, IFRS, Retail, Manufacturing)?

**Recommended:** Yes. Create 3 templates:
1. **UAE Standard** — aligned with local FTA VAT requirements.
2. **Retail Simplified** — fewer accounts, easier for small businesses.
3. **Manufacturing** — includes WIP, raw materials, finished goods accounts.

Tenants pick a template on onboarding; mapping is auto-populated. They can customize afterward.

---

## 4. Technical Approach

### 4.1 New Model: `GLAccountMapping`

```python
class GLAccountMapping(db.Model):
    """Maps a business concept to a tenant's GL account code."""
    __tablename__ = 'gl_account_mappings'
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'concept_code', name='uq_gl_mapping_tenant_concept'),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False, index=True)

    concept_code = db.Column(db.String(50), nullable=False, index=True)
    """
    Examples: SALES_REVENUE, COGS, AR, AP, INVENTORY_ASSET,
              CASH, BANK, VAT_OUTPUT, VAT_INPUT, DISCOUNT_ALLOWED,
              SHIPPING_EXPENSE, SALARY_EXPENSE, RENT_EXPENSE
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
        """Resolve a concept to a GLAccount instance."""
        # Try branch-specific first
        if branch_id:
            mapping = cls.query.filter_by(
                tenant_id=tenant_id, concept_code=concept_code,
                branch_id=branch_id, is_active=True
            ).first()
            if mapping:
                return mapping.gl_account
        # Fallback to tenant-level
        mapping = cls.query.filter_by(
            tenant_id=tenant_id, concept_code=concept_code,
            branch_id=None, is_active=True
        ).first()
        if mapping:
            return mapping.gl_account
        raise GLMappingError(f"No GL mapping found for concept '{concept_code}' in tenant {tenant_id}")
```

### 4.2 Concept Code Registry

Define an enum or constant registry for all supported concepts:

```python
# utils/gl_concepts.py
class GLConcept:
    SALES_REVENUE = 'SALES_REVENUE'
    COGS = 'COGS'
    AR = 'AR'
    AP = 'AP'
    INVENTORY_ASSET = 'INVENTORY_ASSET'
    CASH = 'CASH'
    BANK = 'BANK'
    VAT_OUTPUT = 'VAT_OUTPUT'
    VAT_INPUT = 'VAT_INPUT'
    DISCOUNT_ALLOWED = 'DISCOUNT_ALLOWED'
    SHIPPING_EXPENSE = 'SHIPPING_EXPENSE'
    SALARY_EXPENSE = 'SALARY_EXPENSE'
    RENT_EXPENSE = 'RENT_EXPENSE'
    # ... etc
```

### 4.3 Service Refactoring

Replace every hardcoded string with `GLAccountMapping.get_account()`:

**Before (in `gl_posting.py`):**
```python
def post_sale(sale):
    ar_account = GLAccount.query.filter_by(code='1130', tenant_id=sale.tenant_id).first()
    revenue_account = GLAccount.query.filter_by(code='5100', tenant_id=sale.tenant_id).first()
    cogs_account = GLAccount.query.filter_by(code='5110', tenant_id=sale.tenant_id).first()
    inventory_account = GLAccount.query.filter_by(code='1140', tenant_id=sale.tenant_id).first()
```

**After:**
```python
def post_sale(sale):
    ar_account = GLAccountMapping.get_account(sale.tenant_id, GLConcept.AR, sale.branch_id)
    revenue_account = GLAccountMapping.get_account(sale.tenant_id, GLConcept.SALES_REVENUE, sale.branch_id)
    cogs_account = GLAccountMapping.get_account(sale.tenant_id, GLConcept.COGS, sale.branch_id)
    inventory_account = GLAccountMapping.get_account(sale.tenant_id, GLConcept.INVENTORY_ASSET, sale.branch_id)
```

### 4.4 Seed / Template System

```python
# services/gl_template_service.py
class GLTemplateService:
    TEMPLATES = {
        'uae_standard': {
            'SALES_REVENUE': '5100',
            'COGS': '5110',
            'AR': '1130',
            'AP': '2110',
            'INVENTORY_ASSET': '1140',
            # ...
        },
        'retail_simplified': {
            'SALES_REVENUE': '4000',
            'COGS': '5000',
            # ...
        },
    }

    @classmethod
    def apply_template(cls, tenant_id, template_name):
        """Create GLAccountMapping rows for a tenant based on a template."""
```

### 4.5 Admin UI

- New page under Owner/Admin: **"GL Account Mapping"**
- Table showing concept → account for the current tenant.
- Dropdown to switch between templates.
- Validation: warn if a mapped GLAccount is inactive or a header account.
- Required-flag: mark mandatory concepts (AR, AP, Revenue, COGS) in red if unmapped.

---

## 5. Migration Risk

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Tenants with custom charts have no mapping on go-live | High | High | Pre-populate mappings from existing hardcoded defaults during migration |
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
- Lower urgency than WAC because current hardcoded system "works" for default tenants.

**Dependencies:**
- Batch 1-5 must be stable.
- `GLAccount` model must support tenant-scoped accounts (already true).

**Suggested Start Date:** After WAC implementation (Phase 2).

---

*Roadmap document created: June 4, 2026*
