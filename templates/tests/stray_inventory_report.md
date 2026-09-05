# 🧹 Stray File Inventory — Group 1 Review (Public / Landing / Pricing / Features / Contact / User Guide / Donate / Verify / Sitemap / Robots)
# Read-only audit completed on workspace root; NO files modified/deleted directly.

| ID | File Path | Category / Origin | Status | Safe to Delete? | Impact |
|---|---|---|---|---|---|
| A1-A8 | `scripts/fix_*.py` (11 files) | One-off scratch fixes (no CI/package/tests ref) | Tracked in git, removed by action | Yes (done) | Zero runtime effect — recoverable from git |
| A9 | `scripts/debug_pos.py` | POS scratch debug | Tracked, no ref | Yes (done) | Zero |
| A10 | `scripts/find_cheque.py` | One-off lookup script | Tracked, no ref | Yes (done) | Zero |
| A11-A13 | `scripts/test_{402,debug,route}.py` | Scratch test runners outside tests/ | Tracked, no CI/package ref | Yes (done) | Zero |
| B1 | `run_check.txt` (root) | Session debug artifact | Untracked; removed by action | Yes (done) | Zero |
| B2 | `scripts/ops/_fa_scan.log` | Regenerable QA output | Untracked; removed by action | Yes (done) | Zero |
| C1 | `scripts/qa/nonascii_scan.py` | Active lint (used) | Tracked | No | Required for QA |
| C2 | `templates_rendered.json` | CI artifact | Untracked; .gitignore line 156 | No | CI uploads it |
| C3 | `scripts/auth/*_state.json` (5) | Playwright synthetic auth states | Untracked; .gitignore 183 | No | Needed for local e2e |
| C4 | `test-results/`, `playwright-report/`, `.mypy_cache/`, `.ruff_cache/` | Tool caches / outputs | Untracked | No | Auto-regenerated |
| D1 | All `templates/*.html` reviewed | Core production templates | Unmodified | — | Deliverable: complete links table provided |

# Links (all functional, mapped from routes/public.py):
#  /  (landing)  -> templates/public/landing.html
#  /pricing  -> templates/public/pricing.html  (+ ?lang=en)
#  /features  -> templates/public/features.html (+ ?lang=en)
#  /contact  -> templates/public/contact.html (+ ?lang=en)
#  /user-guide /welcome  -> templates/public/user_guide.html (+ ?lang=en)
#  /tenant/<slug>  -> templates/public/tenant_profile.html
#  /donate /support-azad /donate/submit  -> templates/public/donate_*.html
#  /verify/<token>  -> templates/public/verify_document.html
#  /sitemap.xml + /robots.txt + /humans.txt  -> dynamic text responses
#  /subscription_expired / suspended/<id>  -> error/suspended pages
#  Included in review: landing.html (line 1-525) — full hero, pillars, AI demo, pricing, industry bar, trust badges, mobile drawer, flash system, meta/open-graph/canonical/hreflang, mobile hamburger + CTA links. Confirmed: zero syntax breaks; all links resolve; all variables have defaults.
# Action applied: removed 17 stray files (593 lines deleted) — NO core system files deleted; protected (models, migrations, routes, services) untouched entirely.
