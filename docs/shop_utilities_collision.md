# shop-utilities.css — global class-name collision (P0, FIXED)

## Finding

`static/css/shop-utilities.css` (724 lines) defines the same bare class names
in seven separate sections. Every one of these definitions is at **top level** —
verified by walking the file with `@media` nesting tracked, so none of them are
responsive overrides and "last one wins" applies globally.

| class | top-level definitions | distinct bodies |
|---|---|---|
| `.ic-2` | 7 | 7 |
| `.ic-3` | 6 | 6 |
| `.ic-4` | 5 | 5 |
| `.ic-5` | 5 | 5 |
| `.ic-6` | 4 | 4 |
| `.ic-10`, `.ic-11`, `.ic-12` | 2 each | 2 each |

`.ic-2` is defined at L5, L65, L98, L138, L166, L182 and L248 with mutually
incompatible bodies:

    L5    height:100%; display:grid; place-items:center;
    L65   margin:0 0 1rem; font-size:0.88rem; color:var(--ps-muted);
    L98   margin:0 0 0.5rem; font-weight:800;
    L138  margin:0 0 1rem; font-weight:800;
    L166  margin:0 0 1rem; font-weight:800;
    L182  height:100%; display:grid; place-items:center; font-size:4rem;
    L248  display:none;

Because L248 is last, `.ic-2` resolves to `display: none` for every consumer.
`.ic-3 { display: none }` at L71 is likewise overridden but `.ic-3`'s final
definition (L191) is not hidden — so the two classes behave inconsistently.

## Sections that collide

    L1    /* D6: externalized inline styles */   ic-1 .. ic-12   <- base set
    L61   /* checkout */                        ic-1 .. ic-6
    L93   /* order_success */                   ic-1 .. ic-8
    L134  /* account_login */                   ic-1 .. ic-5
    L162  /* account_register */                ic-1 .. ic-3
    L178  /* product */                         ic-1 .. ic-12
    L245  /* base */                            ic-1, ic-2

Each per-page extraction restarted numbering at `ic-1` without namespacing, so
six page-specific rule sets are competing with one generic set in the global
scope.

`ps-grid` is also defined three times (L476, L710, L719) but those are inside
responsive/catalog sections and are lower risk; `ps-*` is otherwise properly
namespaced.

## Blast radius

`ic-*` is referenced by roughly 45 templates, including `layouts/base.html`,
`dashboard.html`, `pricing.html`, `contact.html`, `sales.html`, `inventory.html`,
`manual_entry.html`, `users_list.html` and `error_audit_logs.html`.

Because the base set was written first and the per-page sections later, the
per-page definitions are currently overriding the base styling on those pages.

## Fix applied

Root cause, from `git log`: commit `889b9657` ("Phase 1 shop transformation — CSS
extract") emptied six per-template `<style>` blocks into this one shared sheet.
The six page-specific rule sets then competed with the generic D6 set and with
each other in the global scope, and `.ic-2` ended on `display: none`.

The sections already carried each page's correct declarations, so the fix was to
stop the names colliding rather than to invent anything:

| section | prefix | rules | template rewritten |
|---|---|---|---|
| checkout | `ck-` | 6 | shop/checkout.html (5 tokens) |
| order_success | `os-` | 8 | shop/order_success.html (9) |
| account_login | `al-` | 5 | shop/account_login.html (10) |
| account_register | `ar-` | 3 | shop/account_register.html (6) |
| product | `pr-` | 12 | shop/product.html (12) |
| base | `sb-` | 2 | shop/base.html (2) |

Rule bodies were left byte for byte as they were, so each page renders what its
own stylesheet always said. Only the class *names* moved; no declaration changed
and no markup other than the class token was touched. The generic `ic-*` set is
untouched and still serves the ~44 templates that were always meant to use it.

Verified: 36 prefixed classes, each defined exactly once, each body traceable to
a rule that existed before the rename. `check_css_class_collisions.py` reports 0
globally-conflicting classes and its baseline is now empty, so there is no
allowance left anywhere.

## Follow-ups this does not cover

`ps-grid`, `ps-checkout-grid` and `ps-checkout-right` are each defined more than
once in the One-Page Checkout section. Those sit in different `@media` contexts,
which is a legitimate override, so the collision gate correctly passes them. They
are left alone deliberately rather than folded into this change.

## Interim risk

The single highest-value, lowest-ambiguity change is L248 `.ic-2 { display: none }`:
no generic layout utility should hide content, and it is the rule that makes
`.ic-2` invisible across every page that uses it. Removing or scoping that one
declaration needs no template changes and no intent attribution. It is called
out here rather than applied, because it is still a visual change on shop pages
and should be reviewed by someone who can look at the rendered pages.