# GRIMOIRE — Azadexa ERP Non-Negotiable Engineering Rules

> Enforced by `scripts/ops/enforce_grimoire.py` (AST static analysis) + `tests/unit/test_grimoire_compliance.py`.
> Violations fail CI. No exceptions, no suppressions without written justification.

---

## 1. TRANSACTION ATOMICITY

| Rule | Detail |
|------|--------|
| **Single commit point** | `db.session.commit()` exists **only** inside `utils/db_safety.py` (`atomic_transaction` + `safe_commit`). |
| **Single rollback point** | `db.session.rollback()` exists **only** inside `utils/db_safety.py` and the `gl_accounting_setup.py` dry-run branch. |
| **Services use flush only** | `db.session.flush()` is the only session mutation allowed in `services/`. Never `commit()` / `rollback()`. |
| **Wrap multi-step writes** | Every multi-model write MUST be inside `with atomic_transaction("description"):`. |
| **No bare adds outside atomic** | `db.session.add()` / `db.session.delete()` are permitted only inside an `atomic_transaction` boundary. |

## 2. TENANT ISOLATION

| Rule | Detail |
|------|--------|
| **Scope every query** | All DB reads/writes MUST use `tenant_query()`, `apply_tenant_scope()`, or `tenant_get_or_404()`. |
| **Single-record lookup** | Use `tenant_get_or_404(Model, id)` — auto-aborts 404 on cross-tenant access. |
| **Multi-record query** | Use `tenant_query(Model)` — applies tenant filter automatically. |
| **Raw SQL** | Resolve tenant via `get_active_tenant_id()` and append `tenant_id=<tid>`. |
| **Cross-tenant = P0** | Any cross-tenant data exposure is a P0 security defect — fix immediately. |
| **Celery / background jobs** | Scope per tenant (`g.active_tenant_id` per iteration) — never unscoped batch queries. |

## 3. INPUT VALIDATION & TYPE SAFETY

| Rule | Detail |
|------|--------|
| **silent=True** | Every `request.get_json()` call MUST pass `silent=True`. |
| **Null-check pattern** | `data = request.get_json(silent=True)` → `if data is None: return ..., 400`. |
| **Decimal guard** | `Decimal(str(data.get('field') or '0'))` — never pass `None` to `Decimal()`. |
| **Schema validation** | Use `validate_positive_amount`, `validate_required_string`, etc. for domain checks. |

## 4. ARCHITECTURE BOUNDARIES

| Layer | Allowed | Forbidden |
|-------|---------|-----------|
| `routes/` | HTTP handlers, request parsing, response formatting | Business logic, direct `db.session` queries, model creation logic |
| `services/` | Pure business logic, `db.session.flush()`, `atomic_transaction` | Imports from `routes/`, HTTP concepts (`request`, `jsonify`, `flash`) |
| `models/` | ORM definitions, scoped query helpers | HTTP concepts, business logic, service imports |
| `utils/` | Pure stateless functions, context managers | Imports from `routes/` or `services/` (except `db_safety`, `tenanting`) |
| `forms/` | WTForms definitions, validation rules | Business logic, DB queries |

## 5. AUTHENTICATION & AUTHORIZATION

| Rule | Detail |
|------|--------|
| `@login_required` | Every route requiring authentication. |
| `@permission_required('code')` | Fine-grained access control. |
| `@owner_required` | Owner panel routes only. |
| **No tenant data to unauth** | Never expose tenant-scoped data without auth. |

## 6. ERROR HANDLING

| Rule | Detail |
|------|--------|
| **No bare `except: pass`** | Always log: `logger.error(...)` or `current_app.logger.error(...)`. |
| **No redundant try/except in atomic** | `atomic_transaction` auto-rolls-back — don't double-wrap. |
| **API errors** | `jsonify({'error': 'message'}), 400/500`. |
| **HTML errors** | `flash(...)` + `redirect(...)`. |

## 7. CODE QUALITY

| Rule | Detail |
|------|--------|
| **No `# type: ignore`** | Use proper type annotations instead. |
| **No `# noqa`** | Fix the issue, don't suppress the warning. |
| **No commented-out code** | Delete dead code. Git remembers. |
| **No duplicate helpers** | DRY — one function, one purpose, one location. |
| **Function length** | Functions > 80 lines must be refactored (extract helpers). |
| **Python 3.12+ idioms** | `str | None` over `Optional[str]`, `match/case` where appropriate, `from __future__ import annotations`. |

## 8. TESTING DISCIPLINE

| Rule | Detail |
|------|--------|
| **Location** | `tests/unit/routes/`, `tests/unit/services/`, `tests/unit/utils/`, `tests/unit/models/`. |
| **Mock boundary** | Mock at the route boundary, never inside services. |
| **Every route module** | Must have a corresponding test file. |
| **Integration tests** | Stay flat in `tests/integration/`. |

## 9. FILE STRUCTURE

| Rule | Detail |
|------|--------|
| **Root directory** | Only entrypoints (`app.py`, `wsgi.py`, `config.py`, `extensions.py`, `cli_commands.py`), docs (`README.md`, `LICENSE`, `AGENTS.md`), and config files (`.env`, `.flake8`, `pytest.ini`, etc.). |
| **No orphaned scripts** | All tooling scripts go in `scripts/ops/`, `scripts/lint/`, or `scripts/backup/`. |
| **No dead monolithic files** | Split large modules into subpackages (`routes/owner/`, `routes/ai_routes/`). |
| **Service subdirectories** | Large domains may use `services/gl/`, `services/store/`, etc. |

## 10. TESTING INTEGRITY, AST AUDITING & ZERO-FLAKINESS

| Rule | Detail |
|------|--------|
| **AST enforcement** | All GRIMOIRE rules are enforced by `scripts/ops/enforce_grimoire.py` using Python AST parsing — never regex. Zero false positives. |
| **Savepoint isolation** | DB test fixtures MUST use `session.begin_nested()` (savepoints) or explicit rollback teardown. No test may leak committed state to another test. |
| **Dynamic DB binding** | Test DB URIs MUST resolve from `app.config['SQLALCHEMY_DATABASE_URI']` — never hardcoded database names in fixture code. |
| **Contract-based testing** | Tests verify inputs/outputs at layer boundaries (route → service). Mock at the route boundary, never inside services. |
| **No flaky patterns** | No `time.sleep()`, no `random` without seed, no order-dependent test logic, no shared mutable state across tests. |
| **Enforcement suite** | `tests/unit/test_grimoire_compliance.py` runs the AST checker in CI — 0 errors required, warnings tracked. |

---
*Enforced by AST static analysis — not regex. Violations fail CI.*
