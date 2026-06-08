# Changelog

## 2026-06-08

### Added
- D3: Client-side form validation (`form_validation.js`) across 149 templates
- D4: Mobile responsiveness fixes (279 `btn-sm` + 23 `btn-xs` removed, 10 tables wrapped)
- D5: Accessibility WCAG fixes (~1,050 errors fixed in 137 templates)
- D6: CSS externalization (961 inline styles moved to classes)
- UI Polish: `stat-card`, `glass-effect`, `hover-card`, badge gradients, sidebar active accent
- Tools: `check_mobile_issues.py`, `fix_mobile_issues.py`, `check_jinja_nesting.py`, `add_required_fields.py`
- Docs: `UI_VISUAL_AUDIT.md`, `UI_DESIGN_SYSTEM.md`
- Jinja2 nesting errors fixed (2 templates)

### Changed
- `erp-theme.css`: +168 lines for new components and polish
- `dashboard.html`: inline `.hover-card` removed (now in theme)
- `requirements.txt`: added `tinycss2>=1.2.0`

## 2026-06-07

### Added
- A2: flake8 strict gate
- A3: Secret key refactor (`bootstrap_keys.py`)
- B1-B4: Blueprint split, logging extract, _exempt_super cleanup, NowPayments provider
- C1-C3: CDN SRI, session security, permission audit (0 gaps)
- D1: POS supermarket enhancements
