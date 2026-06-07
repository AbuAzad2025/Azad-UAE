# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in this project, **do not open a public issue**.

Instead, please report it privately to:

- **Email:** `security@azadsystems.com` (or contact the repository owner directly)

We will acknowledge receipt within **48 hours** and aim to provide a resolution timeline within **7 days**.

## Supported Versions

| Version | Supported |
|---------|-----------|
| main    | ✅ Active |

## Security Measures in Place

- **Multi-tenant data isolation** — `tenant_id` scoping on all queries
- **CSRF protection** — Flask-WTF on all forms
- **Rate limiting** — Flask-Limiter configured
- **SQL injection prevention** — SQLAlchemy ORM + parameterized queries
- **XSS protection** — Jinja2 auto-escaping + CSP headers
- **Card encryption** — Sensitive card data encrypted with `CARD_ENCRYPTION_KEY`
- **Input validation** — WTForms validators on all inputs
- **Security audit scripts** — `tests/security/test_security_boundaries.py` runs per-session

## Known Limitations

- **flake8 enforcement** is currently non-blocking in CI (pending codebase cleanup)
- **Permission consistency audit** (Phase 7.5c) is deferred to post-launch
- See `AUDIT_REPORT.md` for historical findings and remediation status

---

*This is a proprietary project. All rights reserved.*
