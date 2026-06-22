# Tests — اختبارات Azadexa

## Structure

| Directory | Purpose |
|-----------|---------|
| `unit/` | اختبارات الوحدة (Unit Tests) — سريعة، بدون DB حقيقي أو بـ test DB |
| `e2e/` | اختبارات نهاية لنهاية (End-to-End) — تتضمن تدفقات كاملة |
| `integration/` | فارغ حالياً — للاختبارات التي تربط عدة وحدات معاً |
| `regression/` | فارغ حالياً — لاختبارات الانحدار (Regression) |
| `security/` | فارغ حالياً — لاختبارات الأمان |
| `load/` | فارغ حالياً — لاختبارات الأداء والتحمل |

## Running Tests

```bash
# Run all unit tests
pytest tests/unit -v

# Run a specific test file
pytest tests/unit/test_negative_inventory_ils_sale.py -v

# Run e2e tests
pytest tests/e2e -v
```

## Keep List — اختبارات محفوظة (Working)

| File | What it tests |
|------|--------------|
| `test_negative_inventory_ils_sale.py` | MWAC + negative inventory + ILS currency |
| `test_services_comprehensive.py` | Print, User, Tenant, Role, Stock, Purchase, Sale services |
| `test_purchase_return.py` | Purchase return validations |
| `test_purchase_service.py` | Purchase service (create, cancel, return) |
| `test_sale_service.py` | Sale service (create, fulfill, cancel, payments) |
| `test_gl_authority_model.py` | GL authority / chart of accounts model |
| `test_api_balance_isolation.py` | API balance isolation between tenants |
| `test_tenant_isolation_hardening.py` | Tenant isolation enforcement |
| `test_depreciation_schedule_tenant.py` | Tenant-scoped depreciation |
| `test_pos_refactored.py` | POS refactored routes |
| `test_purchase_cancel.py` | Purchase cancel flow |
| `test_mwac_end_to_end.py` | MWAC full cycle (purchase → sale → COGS) |
| `test_landed_cost_end_to_end.py` | Landed cost capitalisation |
| `test_treasury.py` | Treasury / cash management |

## Notes

- Old tests that were brittle or outdated have been archived to `../archive/tests/`.
- New tests should follow the existing `conftest.py` fixtures and use `pytest` best practices.
- Every test must enforce `tenant_id` scoping where applicable.
