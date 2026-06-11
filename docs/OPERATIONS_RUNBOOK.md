# Azadexa Operations Runbook

This runbook provides operational guidance for **Azadexa**, the proprietary multi-tenant ERP and commerce platform by **AZAD Intelligent Systems**.

Use it for local development, staging checks, production deployment, backup planning, and incident handling.

---

## Environment types

| Environment | Purpose | Data rules |
|------------|---------|------------|
| Local development | Fast development and smoke testing | Use fake or disposable data |
| Staging | Release validation and production-like testing | Use sanitized copies only |
| Production | Real tenant and platform operations | Protect secrets, backups, and customer data |

Do not run destructive tests or data-generation scripts directly against production.

---

## Local setup

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate    # Linux/macOS
pip install -r requirements.txt
cp env.example .env
python -m flask db upgrade
python app.py
```

Local development can use the Flask development server for smoke testing only.

---

## Production setup summary

Production should use:

- Python 3.11 virtual environment;
- PostgreSQL database;
- WSGI application entrypoint;
- HTTPS;
- secure `.env` stored only on the server;
- static file mapping;
- scheduled backups;
- separate staging validation before risky changes.

The expected WSGI pattern is:

```python
from app import create_app
application = create_app()
```

---

## Required production checks

Before go-live or after a major deployment:

- Confirm `.env` exists only on the server.
- Confirm `DEBUG=false`.
- Confirm `SKIP_SYSTEM_INTEGRITY` is not enabled.
- Confirm PostgreSQL connection works.
- Run database migrations.
- Reload WSGI app.
- Check login.
- Check owner login.
- Check one tenant admin login.
- Check tenant isolation with at least two tenants.
- Check sales, purchases, inventory, and customer flows.
- Check accounting/ledger posting.
- Check tenant store behavior if enabled.
- Check public donation/package pages if enabled.
- Check payment webhook URL configuration.
- Check backups.

---

## Safe deployment flow

1. Commit and push code.
2. Pull code on staging.
3. Install/update dependencies.
4. Run migrations on staging.
5. Run smoke tests.
6. Validate tenant isolation.
7. Validate accounting and inventory workflows.
8. Validate payment flows using sandbox/test mode where possible.
9. Backup production database.
10. Pull code on production.
11. Install/update dependencies.
12. Run migrations.
13. Reload WSGI app.
14. Verify critical workflows.
15. Monitor logs.

---

## Backup policy

Backups should include:

- PostgreSQL database dump;
- uploaded files if used;
- environment configuration inventory without revealing secret values;
- current Git commit SHA;
- migration head;
- deployment timestamp.

Backups must not be stored in the public web root and must not be committed to Git.

Example PostgreSQL backup pattern:

```bash
pg_dump "$DATABASE_URL" > backup_azadexa_YYYYMMDD_HHMM.sql
```

Use server-specific secure storage for real backups.

---

## Restore policy

Before restoring:

- Confirm the target environment.
- Confirm whether this is staging or production.
- Stop or isolate write traffic if needed.
- Take a backup of the current state first.
- Restore database.
- Run migrations if required.
- Verify tenant records.
- Verify owner access.
- Verify accounting and inventory samples.
- Verify payment records are not duplicated.

Never test restore procedures first on production.

---

## Migration checklist

Before running migrations:

- Know the current migration head.
- Know the target migration head.
- Backup the database.
- Read migration contents if it touches financial, tenant, user, payment, or inventory tables.
- Run on staging first.
- Confirm app starts after migration.
- Confirm tenant isolation still works.

---

## Incident handling

For a production incident:

1. Preserve logs and current commit SHA.
2. Identify affected module: auth, tenant, accounting, inventory, payment, UI, deployment, or database.
3. Stop risky actions if data corruption is possible.
4. Take a backup before applying fixes.
5. Reproduce on staging when possible.
6. Patch with minimal targeted changes.
7. Verify affected workflow.
8. Document root cause and prevention.

---

## Tenant leak response

If a cross-tenant data leak is suspected:

1. Treat it as high severity.
2. Identify exact route/API/template/query.
3. Disable or restrict the affected endpoint if needed.
4. Preserve logs.
5. Confirm affected tenants and data types.
6. Patch tenant filters and route permissions.
7. Add or update a regression test.
8. Review similar routes for the same pattern.

---

## Accounting incident response

If balances or ledger entries look wrong:

1. Stop further automated posting on the affected flow if possible.
2. Identify source documents.
3. Compare document totals, ledger entries, payments, returns, and inventory effects.
4. Avoid manual database edits unless a documented correction script is prepared.
5. Apply corrections with an audit trail.
6. Add regression coverage for the broken calculation.

---

## Inventory incident response

If stock quantities look wrong:

1. Identify product, warehouse, tenant, and branch.
2. Review movement records.
3. Review source documents: sales, purchases, returns, adjustments.
4. Avoid direct quantity edits unless documented as an administrative correction.
5. Correct via movement/adjustment workflows where possible.
6. Verify accounting side effects if inventory value is posted.

---

## Payment incident response

If payment state is wrong:

1. Identify provider transaction id and internal order/payment id.
2. Confirm whether it is tenant revenue or platform-owner revenue.
3. Check webhook logs and provider status.
4. Avoid double-crediting tenant or platform balances.
5. Reconcile with accounting entries.
6. Mask sensitive values in all reports and logs.

---

## Post-deployment smoke checklist

- Home/login loads.
- Owner login works.
- Tenant login works.
- Dashboard loads.
- Sales list and create flow load.
- Purchase flow loads.
- Product and stock screens load.
- Ledger/accounting pages load.
- Storefront route loads if enabled.
- Public package/donation page loads if enabled.
- No server error in logs.
- Static assets load correctly.
- Timezone/date formatting is acceptable.

---

## Documentation update rule

When core behavior changes, update the relevant docs:

- product/brand change → `AZADEXA_BRAND.md`;
- module/business scope change → `PROJECT_OVERVIEW.md`;
- route/service/data-flow change → `ARCHITECTURE.md`;
- tenant/security/payment change → `SECURITY_AND_TENANCY.md`;
- deployment/backup/process change → `OPERATIONS_RUNBOOK.md`.
