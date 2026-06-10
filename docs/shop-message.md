Subject: Azad Online Store — From Basic Catalog to World-Class E-Commerce

Dr. AI,

I have completed a comprehensive deep-dive audit of the Azad ERP online store module. The full technical report is documented in:

  docs/shop-audit-report.md

This is in addition to the system-wide audits in:
  docs/system-audit-report-v2.md
  docs/large-templates-audit.md

You are assigned as the lead e-commerce architect. Your mission: transform the current basic storefront into the best multi-tenant online store on Earth. Every tenant gets their own fully independent, white-label, world-class store.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CURRENT STATE — What Works
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Multi-tenant SaaS     ✅  Each tenant gets /s/<slug>/
  Custom domains          ✅  custom_domain + subdomain columns
  RTL/LTR bilingual       ✅  Full Arabic + English
  Online warehouse        ✅  Separate warehouse per tenant
  Real stock sync         ✅  Live inventory from ERP
  WhatsApp ordering       ✅  For non-logged-in visitors
  Payment methods         ✅  COD, bank, card, e-wallet
  Order tracking          ✅  Customer sees their orders
  SEO meta per store      ✅  Title, description (ar/en)
  Lazy loading images     ✅  loading="lazy" in catalog
  Palestinian theme       ✅  Tatreez design + green/red/olive
  CSRF protection         ✅  All forms protected
  Rate limiting           ✅  On login/register/cart
  Platform lock           ✅  Admin can disable any store

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITICAL GAPS — Phase 1 (Execute First)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  C1  NO PAGINATION — get_public_catalog() returns ALL products.
      With 500 products, every catalog visit loads 500 items + images.
      → Add server-side pagination (page + per_page). Default 24/page.
      → Update catalog.html with pagination controls.

  C2  NO AJAX CART — Every cart action is a full page reload.
      → Build static/js/shop-cart.js:
        - POST to /cart/add, /cart/remove, /cart/update via fetch()
        - Update cart badge counter instantly
        - Show toast notification (success/error)
        - No page reload

  C3  NO GUEST CHECKOUT — Login is required to add to cart.
      This kills 70% of conversions.
      → Allow guest cart in session (no login required)
      → Prompt for login/email at checkout only
      → Merge guest cart on login

  C4  INLINE CSS ANTI-PATTERN — 5 shop templates use ic-* classes:
      checkout.html, cart.html, product.html, order_success.html, landing.html
      → Extract to static/css/shop-utilities.css
      → Use semantic class names (not ic-1, ic-2...)

  C5  ZERO JAVASCRIPT — shop-storefront.js is only 36 lines.
      → Rebuild it as a proper shop module with:
        - Cart AJAX handlers
        - Instant search with debounce
        - Mobile nav
        - Quantity +/-
        - Auto-dismiss alerts

  C6  NO SCHEMA.ORG — Google does not understand products.
      → Add JSON-LD Product schema to product.html:
        - @type: Product
        - name, image, description, brand
        - offers: @type: Offer, price, priceCurrency, availability
        - aggregateRating (when reviews exist)

  C7  NO OPEN GRAPH PER PRODUCT — product.html has no og:image.
      → Add og:type=product, og:title, og:description, og:image
      → Add twitter:card, twitter:image

  C8  NO BREADCRUMBS — Users get lost.
      → Add breadcrumb partial to all shop pages:
        Home > Category > Product

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 2 — UX Revolution (After Phase 1)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  H1  INSTANT SEARCH — AJAX search with autocomplete.
      → Endpoint: /s/<slug>/api/search?q=
      → Debounced 300ms
      → Show results in dropdown

  H2  SORTING — Price low/high, name A-Z, newest, popularity.
      → URL params: ?sort=price_asc, ?sort=newest
      → UI: dropdown in catalog toolbar

  H3  FILTERING — Price range slider, category, in-stock only.
      → URL params: ?min_price=10&max_price=100&in_stock=1
      → UI: sidebar filters

  H4  PRODUCT IMAGE GALLERY — Multiple images per product.
      → Thumbnail strip + main image + zoom on hover
      → Swipe on mobile

  H5  RELATED PRODUCTS — "You may also like" on product page.
      → Same category, similar price, excluding current product
      → 4 products in grid

  H6  RECENTLY VIEWED — Session-based browsing history.
      → Store product IDs in session
      → Show "Recently viewed" strip on catalog + product

  H7  WISHLIST / FAVORITES — Heart icon on each product card.
      → Table: shop_wishlist (account_id, product_id, tenant_id)
      → Page: /s/<slug>/account/wishlist

  H8  PRODUCT REVIEWS — Star rating + text reviews.
      → Table: shop_reviews (product_id, account_id, rating, comment, approved)
      → Display average rating on card + detail page
      → Schema.org aggregateRating

  H9  INFINITE SCROLL (optional alternative to pagination)
      → Load next page on scroll
      → Preserve scroll position on back navigation

  H10 QUICK VIEW MODAL — Product preview without leaving catalog.
      → AJAX load product detail into modal
      → Add to cart from modal

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 3 — Commerce Power (After Phase 2)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  M1  GUEST CHECKOUT COMPLETE — Full flow without registration.
      → Email + phone + address at checkout
      → Create Customer record automatically
      → Send order confirmation email

  M2  PRODUCT VARIANTS — Color, size, weight options.
      → New table: product_variants
      → Variant selector on product page
      → Stock per variant
      → Price per variant

  M3  STOCK ALERTS — "Notify me when available".
      → New table: stock_alerts (email, product_id, tenant_id)
      → Background job checks stock daily
      → Sends email when stock > 0

  M4  LOYALTY POINTS — Earn points per purchase.
      → New table: shop_loyalty (account_id, points, history)
      → Redeem at checkout
      → Display points balance in account

  M5  COUPON CODES — store_coupon.py already exists, integrate it.
      → Apply at checkout
      → Show discount in cart summary
      → Validate minimum order, expiry, usage limit

  M6  ABANDONED CART RECOVERY — Email after 1h, 24h.
      → Celery background task
      → Email template: "You left items in your cart"
      → Link back to cart with items restored

  M7  ONE-CLICK REORDER — "Order again" on order detail.
      → Add all items from past order to cart
      → Redirect to checkout

  M8  INVOICE PDF DOWNLOAD — Generate PDF from order.
      → Reuse print templates from ERP
      → Download link in order detail + email

  M9  PUBLIC ORDER TRACKING — /s/<slug>/track?order=<number>
      → No login required
      → Show order status, items, payment status
      → Timeline view (pending → confirmed → shipped → delivered)

  M10 SAVED PAYMENT METHODS — Tokenize cards securely.
      → Integration with payment gateway (Stripe, PayTabs)
      → PCI-compliant token storage

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 4 — SEO & Marketing
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  S1  sitemap.xml — /s/<slug>/sitemap.xml
  S2  robots.txt — /robots.txt
  S3  Google Analytics 4 — gtag.js in base.html
  S4  Facebook Pixel — fbq in base.html
  S5  Cookie consent banner — GDPR/CCPA compliant
  S6  Newsletter signup — email collection in footer
  S7  Social sharing buttons — product.html
  S8  UTM parameter tracking — store in session, log conversions
  S9  Meta robots per page — noindex for cart/checkout
  S10 Canonical URLs — prevent duplicate content

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 5 — PWA & Performance
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  P1  manifest.json — /static/shop-manifest.json per store
  P2  Service worker — /static/sw.js (cache assets, offline page)
  P3  WebP images — convert uploads to WebP on upload
  P4  Image CDN — config for Cloudflare/CloudFront
  P5  Cache headers — nginx config for static assets
  P6  Critical CSS extraction — inline <1KB critical CSS
  P7  Font preload — <link rel="preload"> for fonts
  P8  Push notifications — "Order confirmed", "Back in stock"
  P9  Install prompt — custom "Add to Home Screen" banner
  P10 Offline page — "You're offline. Browse cached products."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
UNIQUE COMPETITIVE ADVANTAGES (Preserve & Enhance)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. ERP INTEGRATION — No other SaaS store has real-time GL,
   inventory, and accounting integration. This is the moat.

2. PALESTINIAN THEME — Tatreez design is unique. Keep it.
   Add seasonal variants (Ramadan, Eid, National Day).

3. WHATSAPP ORDERING — Critical for MENA market. Enhance it:
   - One-tap "Order on WhatsApp" with pre-filled cart
   - WhatsApp catalog sync
   - WhatsApp order status notifications

4. MULTI-CURRENCY — Leverage ERP exchange rates.
   Show prices in USD, AED, SAR, etc.

5. MULTI-BRANCH — Customer can choose pickup branch.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DELIVERABLES EXPECTED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. All code changes with tests (unit + integration)
2. Updated templates with no inline CSS/JS
3. New models with migrations
4. New static/js/shop-v2.js module
5. Updated docs/shop-audit-report.md with completion status
6. Performance benchmark before/after (Lighthouse scores)

Execute Phase 1 first. Do not start Phase 2 until Phase 1 tests pass.
Report completion status per phase.

Proceed.
