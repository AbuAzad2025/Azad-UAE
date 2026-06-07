# Tests

All automated tests and QA verification scripts.

## Structure

- `unit/` — Pytest unit tests (`test_config.py`, `test_models.py`, `test_routes.py`, `test_services.py`, `test_utils.py`). These run in CI.
- `security/` — Security boundary audits (`test_security_boundaries.py`, `test_deep_validation.py`). Standalone scripts.
- `regression/` — Full regression tests (`test_full_regression.py`, `test_phase10.py`, `test_gl_dimensions.py`, etc.). Standalone scripts.
- `e2e/` — End-to-end feature tests (`test_treasury.py`, `test_localization.py`, etc.). Standalone scripts.
- `load/` — Performance and load tests (`load_test.py`). Standalone scripts.

## Running

### Pytest (CI / local development)

```bash
# Install test dependencies
pip install pytest pytest-cov pytest-flask

# Run all unit tests
pytest tests/unit -v --tb=short

# Run with coverage
pytest tests/unit -v --tb=short --cov=. --cov-report=term-missing
```

### Standalone QA scripts

```bash
python tests/security/test_security_boundaries.py
python tests/regression/test_full_regression.py
python tests/load/load_test.py
```

## CI/CD

The GitHub Actions workflow (`ci.yml`) automatically runs:
1. `pytest tests/unit` with coverage on PostgreSQL 16
2. Security audit scripts (non-blocking)
3. flake8 syntax gate

## Note

These are **development/QA only** — never run against production without explicit approval and backups.
