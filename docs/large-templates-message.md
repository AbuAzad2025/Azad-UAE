Subject: Large Templates Refactoring — 4 Monoliths Found (2561→1385 lines each)

Dr. AI,

I have manually audited the largest templates in the Azad ERP codebase. The full report is documented in:

  docs/large-templates-audit.md

This is in addition to the system-wide audit in docs/system-audit-report-v2.md.

Four templates are structural monoliths requiring immediate intervention:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. support.html — 2561 lines, 113.9 KB (STANDALONE, no extends)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Structure:
  head (~20 lines)
    Font Awesome 6.4.0, Bootstrap 4.6.2 RTL, Cairo font
    accessibility.css
    <style> ... </style>  ← 970 lines of inline CSS
  body (~1550 lines)
    Hero section, quick contact cards, tab system
    purchase tab (600 lines): package selection + payment methods
    donation tab (400 lines): amounts + crypto wallets
  <script> ... </script>  ← 500 lines of inline JS
    switchTab(), selectPackage(), processCardPayment()
    Hard-coded API: /payment-vault/api/purchase, /payment-vault/api/donation
  footer

Critical issues:
  — 970 lines of uncacheable inline CSS
  — 500 lines of uncacheable inline JS with payment logic
  — 96 auto-generated class names: ic-1, ic-2 ... ic-96 (unmaintainable)
  — Inline event handlers: onclick="openWhatsApp(...)" in multiple places
  — Duplicate integrity attribute on Font Awesome CDN tag

Action:
  Extract CSS → static/css/support.css
  Extract JS  → static/js/support.js
  Rename ic-* classes to semantic names
  Remove inline event handlers, use addEventListener
  Remove duplicate integrity from CDN link

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
2. purchases/create.html — 1797 lines, 36.4 KB (extends base.html)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Structure:
  {% block extra_css %}  ← 320 lines inline CSS
    purchase-create-form styling (heavily customized form)
  {% block content %}    ← 600 lines HTML form
    Dynamic product lines with jQuery append
  {% block extra_js %}   ← 700 lines inline JS
    addLine(), removeLine(), calculateTotals(), debugTotals(), forceCalculate()
    SmartSelectors integration for product dropdowns
    Template literals generating HTML inside JS strings

Critical issues:
  — 320 lines inline CSS (form-specific styling)
  — 700 lines inline JS (entire purchase line management)
  — DEBUG BUTTON IN PRODUCTION: onclick="debugTotals()"
  — FORCE CALCULATE BUTTON: onclick="forceCalculate()" (workaround, not fix)
  — Excessive blank lines (every line followed by a blank line)
  — jQuery-heavy dynamic form generation

Action:
  Extract CSS → static/css/purchases.css
  Extract JS  → static/js/purchases/create.js
  Remove debugTotals() and forceCalculate() buttons (or make dev-only)
  Clean blank lines throughout
  Consider moving to vanilla JS modules

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
3. public/landing.html — 1448 lines, 55.3 KB (STANDALONE, no extends)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Structure:
  head (~120 lines)
    Rich SEO: meta, JSON-LD SoftwareApplication schema
    JSON-LD FAQPage schema (7 Q&A pairs)
    Font Awesome 5.15.4 (dupe integrity attribute)
    accessibility.css, landing.css
    <style> (~50 lines critical CSS)
  body (~1200 lines)
    Navbar, hero, features grid (6 cards), pricing (3 plans)
    Testimonials, FAQ section, footer
  <script> (~100 lines)

Issues:
  — Standalone template (does not inherit base.html)
  — Duplicate integrity attribute on Font Awesome CDN
  — Hard-coded pricing ($299, $599) in HTML
  — 120+ lines of JSON-LD structured data in template

Action:
  Fix dupe integrity on Font Awesome CDN link
  Extract JSON-LD → partials/seo-landing.html
  Move pricing to database/settings
  Keep critical CSS inline (acceptable for landing page LCP)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
4. pos/index.html — 1385 lines, 29.3 KB (extends base.html)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Structure:
  {% block extra_css %}: loads pos.css (good — external)
  {% block content %}: ~1000 lines
    Customer search, product search, barcode scanner
    Cart table, payment section, discount/tax controls
  {% block extra_js %}: ~300 lines
    Barcode scanner integration, keyboard shortcuts (F2, F4, F8, Esc)
    AJAX product search, cart calculations

Issues:
  — 1000 lines of HTML for POS interface in one template
  — 300 lines inline JS (acceptable but should be extracted)

Action:
  Extract JS → static/js/pos/index.js
  Consider splitting into partials: pos_header, pos_cart, pos_payment

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OTHER LARGE TEMPLATES (>500 lines, quick notes)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

sales/view.html            1039 lines — large inline JS
payments/create_receipt    1017 lines — inline CSS + JS
owner/invoice_settings    889 lines — inline CSS
owner/backups_list        605 lines — complex UI
suppliers/view            604 lines — needs review
owner/company_info        581 lines — needs review
customers/statement       577 lines — inline CSS
products/create           565 lines — inline CSS

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GENERAL PATTERNS OBSERVED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Every major form template (purchases/create, sales/create, payments/*)
   contains 300-700 lines of inline CSS and 300-700 lines of inline JS.

2. Blank lines are excessive throughout: many files have a blank line
   after EVERY single line, doubling file size without benefit.

3. Font Awesome CDN links across the codebase have duplicate
   integrity attributes (landing.html, support.html, and likely others).

4. Two standalone base templates exist alongside base.html:
   — support.html (completely independent, 113.9 KB)
   — landing.html (completely independent, 55.3 KB)
   — shop/base.html (previously known, independent)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INSTRUCTIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Execute in this order:

Phase A — support.html (highest priority, standalone)
  1. Extract inline CSS → static/css/support.css
  2. Extract inline JS → static/js/support.js
  3. Rename ic-1...ic-96 to semantic class names
  4. Replace inline onclick handlers with addEventListener
  5. Fix dupe integrity on Font Awesome CDN
  6. Add tests for JS functionality

Phase B — purchases/create.html (extends base.html)
  1. Extract inline CSS → static/css/purchases.css
  2. Extract inline JS → static/js/purchases/create.js
  3. Remove debugTotals() and forceCalculate() production buttons
  4. Clean blank lines
  5. Add tests

Phase C — landing.html (standalone)
  1. Fix dupe integrity
  2. Extract JSON-LD to partial
  3. Move pricing to config

Phase D — pos/index.html
  1. Extract inline JS → static/js/pos/index.js
  2. Split into partials if beneficial

Report completion status per phase. Include test coverage.
Proceed.
