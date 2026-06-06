# Scripts

Operational scripts for production use: seeding, backfilling, verification, and maintenance.

## Structure

- `seed/` — Initial data seeding (`fill_profit_centers.py`, `seed_opening_wac.py`, `run_gl_accounting_setup.py`)
- `backfill/` — Data backfill and reconciliation (`backfill_inventory_gl_reconciliation.py`, `backfill_pwc_opening_balances.py`)
- `verify/` — Verification and health checks (`verify_db.py`, `verify_migrations.py`, `check_inventory.py`, `check_payroll.py`, etc.)
- `maintenance/` — Cleanup and repair (`cleanup_orphaned_data.py`, `fix_unbalanced_entries.py`, `delete_fake_entries.py`, etc.)

## Safety

All scripts in `verify/` are read-only by design.
Scripts in `seed/` and `backfill/` write to the database — run with caution and always back up first.
Scripts in `maintenance/` delete or modify data — require explicit approval before production use.

## Running

```bash
python scripts/verify/verify_db.py
python scripts/verify/check_inventory.py
```
