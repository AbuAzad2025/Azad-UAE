# var → let/const Conversion Plan

## Goal
Replace all `var` declarations with `let` or `const` per ES6 best practices, preserving exact runtime behavior.

## Strategy
- **Use `const`** for variables never reassigned after initialization (majority of cases).
- **Use `let`** for variables that are reassigned (loop counters, accumulators, values updated in callbacks).

## Per-File Decisions

### 1. `static/js/app.js` (11 occurrences) — all `const`
| Line | Declaration | Reassigned? | Target |
|------|-------------|-------------|--------|
| 45 | `var $root = root && root.nodeType ? $(root) : $(document);` | No | `const` |
| 55 | `var $modal = $(this);` | No | `const` |
| 109 | `var $root = root && root.nodeType ? $(root) : $(document);` | No | `const` |
| 112 | `var $el = $(this);` | No | `const` |
| 119 | `var $el = $(this);` | No | `const` |
| 126 | `var $el = $(this);` | No | `const` |
| 133 | `var $btn = $(this);` | No | `const` |
| 249 | `var $root = root && root.nodeType ? $(root) : $(document);` | No | `const` |
| 251 | `var $el = $(this);` | No | `const` |
| 605 | `var $el = $(selector);` | No | `const` |
| 607 | `var $clone = $el.clone();` | No | `const` |
| 608 | `var $printWin = window.open(...)` | No | `const` |

### 2. `static/js/shop-storefront.js` (2 occurrences)
| Line | Declaration | Reassigned? | Target |
|------|-------------|-------------|--------|
| 55 | `var searchTimer;` | Yes (in setTimeout callback) | `let` |
| 80 | `var deferredPrompt;` | Yes (in event handler) | `let` |

### 3. `templates/ai/assistant.html` (4 occurrences) — all `const`
| Line | Declaration | Reassigned? | Target |
|------|-------------|-------------|--------|
| 337 | `var btn = $('#beginnersBtn');` | No | `const` |
| 381 | `var file = $('#excelFile')[0];` | No | `const` |
| 383 | `var fd = new FormData();` | No | `const` |
| 386 | `var csrf = $(this).find('input[name="csrf_token"]').val();` | No | `const` |

### 4. `templates/auth/login.html` (1 occurrence) — `const`
| Line | Declaration | Reassigned? | Target |
|------|-------------|-------------|--------|
| 143 | `var active = tab.getAttribute('data-access-mode') === mode;` | No | `const` |

### 5. `templates/expenses/archived.html` (2 occurrences) — both `const`
| Line | Declaration | Reassigned? | Target |
|------|-------------|-------------|--------|
| 77 | `var id = $(this).data('id');` | No | `const` |
| 78 | `var csrfToken = $('meta[name="csrf-token"]').attr('content');` | No | `const` |

### 6. `templates/owner/error_audit_logs.html` (5 occurrences) — all `const`
| Line | Declaration | Reassigned? | Target |
|------|-------------|-------------|--------|
| 268 | `var div = document.createElement('div');` | No | `const` |
| 274 | `var html = '<dl class="row small">' + ...` | No | `const` |
| 318 | `var btn = e.relatedTarget;` | No | `const` |
| 320 | `var $modal = $(this);` | No | `const` |
| 321 | `var data = $(btn).data('error-detail');` | No | `const` |

### 7. `templates/owner/tax_settings.html` (2 occurrences) — both `const`
| Line | Declaration | Reassigned? | Target |
|------|-------------|-------------|--------|
| 91 | `var fields = document.getElementById('tax-fields');` | No | `const` |
| 92 | `var countryRates = { AE: 5, IL: 17, PS: 16 };` | No | `const` |

### 8. `templates/payments/archived.html` (5 occurrences) — all `const`
| Line | Declaration | Reassigned? | Target |
|------|-------------|-------------|--------|
| 284 | `var type = $(this).data('type');` | No | `const` |
| 286 | `var id = $(this).data('id');` | No | `const` |
| 288 | `var endpoint = ...` | No | `const` |
| 290 | `var url = endpoint + id + '/restore';` | No | `const` |
| 292 | `var csrfToken = ...` | No | `const` |

### 9. `templates/payments/voucher.html` (15 occurrences)
| Line | Declaration | Reassigned? | Target |
|------|-------------|-------------|--------|
| 222 | `var customers = JSON.parse(...)` | No | `const` |
| 223 | `var suppliers = JSON.parse(...)` | No | `const` |
| 226 | `var type = $('#party_type').val();` | No | `const` |
| 227 | `var select = $('#party_id');` | No | `const` |
| 231 | `var list = (type === 'customer') ? customers : suppliers;` | No | `const` |
| 234 | `var typeLabel = '';` | Yes (inside if) | `let` |
| 249 | `var currency = $('#currency').val() || 'AED';` | No | `const` |
| 256 | `var response = await fetch(...)` | No | `const` |
| 257 | `var data = await response.json();` | No | `const` |
| 273 | `var preDirection = ...` | No | `const` |
| 274 | `var prePartyType = ...` | No | `const` |
| 275 | `var prePartyId = ...` | No | `const` |
| 276 | `var preAmount = ...` | No | `const` |
| 277 | `var preCurrency = ...` | No | `const` |
| 278 | `var preExchangeRate = ...` | No | `const` |

### 10. `templates/public/landing.html` (8 occurrences) — all `const`
| Line | Declaration | Reassigned? | Target |
|------|-------------|-------------|--------|
| 704 | `var tierSlider = document.getElementById('tierSlider');` | No | `const` |
| 706 | `var tierNav = document.getElementById('tierNav');` | No | `const` |
| 707 | `var tierBtns = tierNav.querySelectorAll('.azad-tier-btn');` | No | `const` |
| 708 | `var tierCards = document.querySelectorAll('.azad-tier-card');` | No | `const` |
| 725 | `var item = this.parentElement;` | No | `const` |
| 726 | `var isOpen = item.classList.contains('open');` | No | `const` |
| 734 | `var target = document.querySelector(this.getAttribute('href'));` | No | `const` |
| 742 | `var observer = new IntersectionObserver(...)` | No | `const` |

### 11. `templates/sales/archived.html` (2 occurrences) — both `const`
| Line | Declaration | Reassigned? | Target |
|------|-------------|-------------|--------|
| 222 | `var id = $(this).data('id');` | No | `const` |
| 224 | `var csrfToken = ...` | No | `const` |

### 12. `templates/store/admin_transfer.html` (8 occurrences)
| Line | Declaration | Reassigned? | Target |
|------|-------------|-------------|--------|
| 98 | `var wh = document.getElementById('source_warehouse_id');` | No | `const` |
| 99 | `var whId = parseInt(wh.value) || 0;` | No | `const` |
| 100 | `var detail = document.getElementById('product_stock_detail');` | No | `const` |
| 101 | `var whCount = document.getElementById('wh_count');` | No | `const` |
| 102 | `var count = 0;` | Yes (count++) | `let` |
| 104 | `var i = 0;` (loop counter) | Yes (i++) | `let` |
| 105 | `var opt = sel.options[i];` | Yes (reassigned each iteration) | `let` |
| 113 | `var stock = parseFloat(...)` | No | `const` |

## Total
- `const`: ~56
- `let`: ~8

## Acceptance Criteria
1. All `var` keywords replaced with `let` or `const` as specified.
2. No runtime behavior changes (block-scoping differences don't affect these usages).
3. IDE warnings for "var used instead of let/const" eliminated.