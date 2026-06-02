# Manual Migrations

This directory contains manual database migrations that were performed outside of Alembic.

## Available Migrations

### migrate_cost_centers.py
- **Date**: 2026-06-02
- **Purpose**: Add tenant_id to cost_centers table for proper multi-tenant isolation
- **Usage**: `python migrations/manual/migrate_cost_centers.py`

### fix_cost_centers_index.py
- **Date**: 2026-06-02
- **Purpose**: Cleanup old indexes and data after tenant_id migration
- **Usage**: `python migrations/manual/fix_cost_centers_index.py`

## Important Notes

- Always document manual migrations in the project's `MIGRATIONS.md` file
- Include rollback instructions in the documentation
- Test migrations on a development database first
- Backup database before running manual migrations

## Adding New Manual Migrations

1. Create the migration script in this directory
2. Document it in `MIGRATIONS.md` at the project root
3. Include:
   - Date
   - Purpose
   - Changes made
   - Verification steps
   - Rollback instructions
