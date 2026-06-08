# UI Visual Audit Report

## 1. Current State Summary

The ERP uses Bootstrap 4.6.2 + AdminLTE 3.2 with a custom theme file `static/css/erp-theme.css` (1466 lines). The theme has a solid design token system with 4 variants (Palestinian/Gulf x Light/Dark) and good RTL support.

## 2. Existing Frontend Architecture

| Layer | File | Role |
|-------|------|------|
| Global layout | `templates/base.html` | AdminLTE wrapper, sidebar, navbar, footer |
| Theme CSS | `static/css/erp-theme.css` | Design tokens + component overrides |
| Dashboard | `templates/dashboard.html` | KPI cards, financial cards, recent sales table, quick actions |
| Print templates | `templates/invoices/`, `templates/receipts/` | Standalone pages with viewport meta |

## 3. What Is Already Good

- Design token system with `--ui-*` variables
- 4 variant/mode combinations
- RTL support via logical properties
- Touch-friendly 44px min-height on buttons/forms
- Card, button, form, table, pagination, Select2 styling
- Sidebar gradient, navbar gradient
- Login page polished
- Mobile nav component exists
- Content wrapper background and padding
- Footer with brand/actions pattern

## 4. What Still Needs Polish

### Critical Gaps

| Class | Used In | Status |
|-------|---------|--------|
| `.stat-card` | `dashboard.html` | **NOT DEFINED** — falls back to raw HTML |
| `.glass-effect` | `dashboard.html` | **NOT DEFINED** — no glass morphism |
| `.hover-card` | `dashboard.html` | Inline `<style>` only — not in theme |

### Missing Polish

- **Badges**: Only Bootstrap defaults, no custom sizing/padding
- **Sidebar active item**: Subtle background, needs stronger teal/emerald accent
- **Table**: Basic styling, needs cleaner header and row separators
- **KPI card values**: No typography hierarchy for large numbers
- **Dashboard financial cards**: No visual distinction between types

### Inline CSS Remaining

- `dashboard.html` lines 310-318: `.hover-card` inline styles
- `dashboard.html` lines 320-333: `.ic-*` externalized classes (safe, in `<style>` block)

### Mobile Issues

- `btn-group-sm` still present in recent sales table actions
- Dashboard KPI cards: `col-lg-3 col-md-6` stacks at md but no `col-sm-12` explicit
- Financial cards: `col-md-4` stacks at md but could use better mobile spacing

## 5. Proposed Files to Edit

### Must Edit

1. `static/css/erp-theme.css` — add `.stat-card`, `.glass-effect`, `.hover-card`, badge polish, table polish, sidebar active enhancement
2. `templates/dashboard.html` — remove inline `.hover-card` styles, fix `btn-group-sm`

### May Edit

3. `templates/base.html` — only if sidebar active state needs template-level changes

### Will NOT Touch

- `models/`, `services/`, `routes/`, `migrations/`
- Security/payment vault files
- Permission decorators
- Tenant isolation helpers
- GL posting logic

## 6. Risk List

| Risk | Mitigation |
|------|------------|
| Adding CSS could conflict with AdminLTE | Use higher specificity or `!important` sparingly |
| Removing inline styles breaks dashboard | Move to erp-theme.css first, then remove inline |
| Dark mode regression | Test both `data-ui-mode` values |
| RTL regression | Use logical properties (`margin-inline-*`) |
| Mobile breakpoint conflicts | Use `@media (max-width: 767.98px)` for phone-specific |

## 7. Attached Image Guidance

The image shows:
- Deep navy sidebar with teal active items
- White cards on soft gray background
- Clean KPI cards with large readable numbers
- Subtle shadows, modern radius
- Compact mobile layout with stacked cards
- Simplified mobile table/list view

These will guide token values and component styling without copying fake data.
