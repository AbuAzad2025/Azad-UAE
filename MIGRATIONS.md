# Manual Migrations Documentation

This document tracks manual database migrations that were performed outside of Alembic.

## Cost Centers Tenant Migration

### Date: 2026-06-02
### Migration: Add tenant_id to cost_centers table

### Reason
Cost centers were global (not tenant-specific), which caused data isolation issues in a multi-tenant system. Each tenant should have its own cost centers.

### Changes Made
1. **Model Changes** (`models/cost_center.py`):
   - Added `tenant_id` column with FK to `tenants` table
   - Changed `code` from unique to indexed
   - Added unique constraint on `(tenant_id, code)`
   - Added `tenant` relationship

2. **Database Changes**:
   - Added `tenant_id` column to `cost_centers` table
   - Created index `ix_cost_centers_tenant_id`
   - Dropped old unique constraint on `code` (if existed)
   - Added unique constraint `uq_cost_centers_tenant_code` on `(tenant_id, code)`

### Migration Script
File: `migrations/manual/migrate_cost_centers.py`
```python
# Adds tenant_id column and constraints
# Drops old unique constraint on code
# Adds new unique constraint on (tenant_id, code)
```

### Cleanup Script
File: `migrations/manual/fix_cost_centers_index.py`
```python
# Drops old unique index on code
# Deletes cost centers with NULL tenant_id
```

### No Seed Required
Seed scripts were removed from the permanent application path. Tenant-linked
cost center corrections should be handled through migrations or the manual
repair script under `migrations/manual/`, not through demo seed data.

### Verification
```bash
python migrations/manual/migrate_cost_centers.py
```

### Rollback Instructions (if needed)
```sql
-- Remove new constraint
ALTER TABLE cost_centers DROP CONSTRAINT uq_cost_centers_tenant_code;

-- Remove tenant_id column
ALTER TABLE cost_centers DROP COLUMN tenant_id;

-- Drop index
DROP INDEX IF EXISTS ix_cost_centers_tenant_id;

-- Restore old unique constraint
ALTER TABLE cost_centers ADD CONSTRAINT cost_centers_code_key UNIQUE (code);
```

---

## Future Migrations

When adding manual migrations, document them here following the same format:

### Date: YYYY-MM-DD
### Migration: [Brief description]

### Reason
[Why this migration was needed]

### Changes Made
[Model and database changes]

### Migration Script
[Script filename and description]

### Verification
[How to verify the migration worked]

### Rollback Instructions
[SQL to rollback if needed]
