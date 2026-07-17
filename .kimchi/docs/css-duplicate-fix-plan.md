# CSS Duplicate Property Fix Plan

## Goal
Eliminate IDE warnings about overwritten/duplicated CSS properties in invoice, receipt, and payment templates by restructuring Jinja2-conditional dimension declarations so each CSS rule contains only one `width`, `height`, `min-height`, or `max-height` declaration.

## Root Cause
The templates use Jinja2 `{% if %}`/`{% elif %}`/`{% else %}` blocks inside a single CSS rule to set page dimensions based on `settings.paper_size`. Static CSS analyzers see every branch at once and report that `width`, `height`, etc. are declared multiple times within the same rule.

## Fix Strategy
Replace the repeated dimension declarations with CSS custom properties (`--page-width`, `--page-height`, etc.) inside the conditional branches, then apply a single `width: var(--page-width);` (and matching height/min-height/max-height) declaration after the conditional. This preserves runtime behavior while giving static analyzers only one property declaration per rule.

## Files & Changes

### 1. `templates/invoices/classic.html`
Selector: `.invoice`
Current: `width` and `height` declared in A5, Letter, and else branches.
Change: Set `--page-width` and `--page-height` per branch; add `width: var(--page-width); height: var(--page-height);` after `{% endif %}`.

### 2. `templates/invoices/gulf.html`
Selector: `.invoice`
Current: `width` and `max-height` declared in A5, Letter, and else branches.
Change: Set `--page-width` and `--page-max-height` per branch; add `width: var(--page-width); max-height: var(--page-max-height);` after `{% endif %}`.

### 3. `templates/invoices/minimal.html`
Selector: `.invoice`
Current: `width` and `height` declared in A5, Letter, and else branches.
Change: Same as classic.html.

### 4. `templates/invoices/modern.html`
Selector: `.invoice`
Current: `width` and `height` declared in A5, Letter, and else branches.
Change: Same as classic.html.

### 5. `templates/payments/print_receipt.html`
Selector: `.receipt`
Current: `width` and `min-height` declared in A5, Letter, and else branches.
Change: Set `--page-width` and `--page-min-height` per branch; add `width: var(--page-width); min-height: var(--page-min-height);` after `{% endif %}`.

### 6. `templates/receipts/classic.html`
Selector: `.receipt`
Current: `width` and `height` declared in A5, Letter, and else branches.
Change: Same as invoice classic.html.

### 7. `templates/receipts/gulf.html`
Selector: `.receipt`
Current: `width` and `height` declared in A5, Letter, and else branches.
Change: Same as invoice classic.html.

### 8. `templates/receipts/minimal.html`
Selector: `.receipt`
Current: `width` and `height` declared in A5, Letter, and else branches.
Change: Same as invoice classic.html.

### 9. `templates/receipts/modern.html`
Selector: `.receipt`
Current: `width` and `height` declared in A5, Letter, and else branches.
Change: Same as invoice classic.html.

### 10. `templates/partials/support/purchase.html`
Selector: inline style on `.erp-badge-gradient`
Current: The `else` branch duplicates `#667eea 0%, #764ba2` already present in the `primary` branch.
Change: Refactor the inline gradient expression to avoid repeating the same color-stop pair. Use a single Jinja2 variable for the gradient colors or merge the `primary` and `else` branches.

## Acceptance Criteria
1. Each affected `.invoice`/`.receipt` rule contains exactly one `width` declaration and exactly one matching height/min-height/max-height declaration.
2. The rendered CSS dimensions for A5, Letter, and A4/portrait/landscape remain unchanged.
3. `templates/partials/support/purchase.html` no longer contains the duplicated `#667eea 0%, #764ba2` color-stop pair.
4. No other functional changes are introduced.

## Complexity
All chunks are **simple** — straightforward refactoring of existing template CSS using CSS custom properties. No concurrency, state machines, or algorithms are involved.

## Chunking
Because the transformations are identical across invoice/receipt templates, this can be implemented as one logical change set covering all 10 files.
