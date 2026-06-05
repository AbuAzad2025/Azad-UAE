# Production Deployment Checklist
## ERP Accounting Master — Phase 10

### Pre-Deployment
- [ ] Database backup verified (test restore on separate server)
- [ ] Migration dry-run reviewed (`flask db upgrade --sql`)
- [ ] All QA tests passed:
  - [ ] `test_inventory_reconciliation.py`
  - [ ] `test_treasury.py`
  - [ ] `test_localization.py`
  - [ ] `test_full_regression.py`
  - [ ] `load_test.py`
- [ ] `py_compile` passes on all modified Python files
- [ ] Jinja2 templates parse without errors
- [ ] Feature flags configured per tenant in `config.py`

### Deployment Steps
1. **Stop Celery workers**
   ```bash
   celery -A app.celery control shutdown
   ```
2. **Create database restore point**
   ```bash
   pg_dump $DATABASE_URL > backup_$(date +%Y%m%d_%H%M%S).sql
   ```
3. **Apply migrations**
   ```bash
   flask db upgrade
   ```
4. **Start application**
   ```bash
   systemctl restart azad-uae
   ```
5. **Start Celery workers**
   ```bash
   celery -A app.celery worker --loglevel=info
   ```
6. **Verify health endpoints**
   ```bash
   curl /api/health
   ```

### Post-Deployment Monitoring
- [ ] Celery task success rate > 99%
- [ ] GL out-of-balance alert: zero unbalanced entries
- [ ] Inventory reconciliation mismatch alert: zero qty/value diffs
- [ ] Treasury liquidity alert: no negative balances unexpectedly

### Rollback Procedure
1. Revert feature flags to pre-deployment state
2. Restore database from backup point
3. Verify application functionality with `test_full_regression.py`
4. **NEVER rollback without database restore point verification**
