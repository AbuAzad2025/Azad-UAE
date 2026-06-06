# Tests

All automated tests and QA verification scripts.

## Structure

- `regression/` — Full regression tests (`test_full_regression.py`, `test_phase10.py`, `test_gl_dimensions.py`, etc.)
- `security/` — Security boundary audits (`test_security_boundaries.py`)
- `e2e/` — End-to-end feature tests (`test_treasury.py`, `test_localization.py`, `test_landed_cost_end_to_end.py`, etc.)
- `load/` — Performance and load tests (`load_test.py`)

## Running

Most tests are standalone Python scripts and can be run directly:

```bash
python tests/security/test_security_boundaries.py
python tests/regression/test_full_regression.py
python tests/load/load_test.py
```

## Note

These are **development/QA only** — never run against production without explicit approval and backups.
