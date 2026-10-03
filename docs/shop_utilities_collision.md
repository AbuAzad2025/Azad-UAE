# shop-utilities.css — global class-name collision (P0, diagnosed, NOT auto-fixed)

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

## Why this was not auto-fixed

Renaming requires knowing **which definition each usage was written against**.
For the ~40 templates that only ever wanted the base set, the fix is to leave
their markup alone and namespace the six page sections. But for the five shop
templates that have a matching section — `shop/checkout.html`,
`shop/order_success.html`, `shop/account_login.html`,
`shop/account_register.html`, `shop/product.html` — each one uses the same
`ic-N` tokens for both intents, and nothing in the repository records which
section an individual usage came from.

Renaming those five mechanically would either

* leave them on the generic set and lose their page-specific spacing, or
* move them to the section set and change spacing on a customer-facing page,

and neither can be verified from tests, because no test renders these pages and
no screenshot exists in the repo. These are shop checkout and login pages, so a
wrong guess is visible to customers.

## Remediation plan

1. Prefix each per-page section and rewrite only its own template:
   `checkout -> ck-`, `order_success -> os-`, `account_login -> al-`,
   `account_register -> ar-`, `product -> pr-`, `base (L245) -> sb-`.
2. For each of the five shop templates, decide per usage which intent it was,
   using git history of the extraction commits (`git log -S'ic-2' -- <file>`)
   to attribute each class to the commit that introduced it. That attribution is
   the only evidence available; it must not be guessed.
3. Add a gate that fails when one CSS file defines the same bare class twice with
   different bodies at top level, so this cannot recur. It must be
   `@media`-aware or it will flag every legitimate responsive override —
   a naive version of this check flags 41 classes in `erp-theme-unified.css` and
   42 in `landing.css`, which are almost certainly media-query overrides, not
   defects.
4. Re-verify with `check_utility_reachability.py`, `test_no_duplicate_static_assets`
   and the inline budget.

## Interim risk

The single highest-value, lowest-ambiguity change is L248 `.ic-2 { display: none }`:
no generic layout utility should hide content, and it is the rule that makes
`.ic-2` invisible across every page that uses it. Removing or scoping that one
declaration needs no template changes and no intent attribution. It is called
out here rather than applied, because it is still a visual change on shop pages
and should be reviewed by someone who can look at the rendered pages.