# Contributing

## ⚠️ Important Notice

This is a **proprietary project**. All rights reserved. This repository is **not open source**.

- **Do not fork** without explicit written permission.
- **Do not submit pull requests** from external contributors.
- **Do not redistribute** the code or any portion of it.

## For Internal Contributors

### Before You Start

1. **Read the Master Blueprint:** `docs/ERP_ACCOUNTING_MASTER_BLUEPRINT.md`
2. **Check CI status:** Ensure the latest `main` branch run is green
3. **Read tests:** Understand existing coverage in `tests/unit/`

### Workflow

1. Create a feature branch from `main`
2. Run tests locally: `pytest tests/unit -v --tb=short`
3. Commit with **Arabic messages** describing the change
4. Ensure CI passes before merging

### Code Standards

- **Python 3.11+** syntax
- **UTF-8** encoding for all files
- Add tests to **existing** test files (do not create new ones unless necessary)
- Follow existing patterns for Flask blueprints, SQLAlchemy models, and service layers
- **Never** hardcode secrets or API keys

### Testing

```bash
# Unit tests
pytest tests/unit -v --tb=short

# With coverage
pytest tests/unit -v --tb=short --cov=. --cov-report=term-missing

# Security audit
python tests/security/test_security_boundaries.py
```

### Reporting Issues

Use the repository's internal issue tracker. For security issues, see `SECURITY.md`.

---

*Azad Smart Systems — All rights reserved.*
