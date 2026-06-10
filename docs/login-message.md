Subject: Login Pages — Critical HTML Bugs + Security Holes + UX Clutter Found

Dr. AI,

I have manually audited all login pages and authentication flows in the Azad ERP codebase. The full technical report is documented in:

  docs/login-audit-report.md

This is in addition to:
  docs/system-audit-report-v2.md
  docs/large-templates-audit.md
  docs/shop-audit-report.md

You are assigned to fix login pages immediately. I found 7 critical HTML bugs and 15+ security/UX issues.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE A — Fix Critical HTML Bugs (Execute First)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

A1  FIX DUPLICATE crossorigin — templates/auth/login.html:11
    Current:
      crossorigin="anonymous" crossorigin="anonymous"
    Remove the duplicate.

A2  FIX DUPLICATE class attribute — templates/auth/login.html:117
    Current:
      <form class="needs-validation" ... class="azad-login-form" ...>
    The second class NEVER applies. Merge into one:
      <form class="needs-validation azad-login-form" ...>
    Then verify azad-login-form CSS selectors actually work.

A3  REMOVE inline CSS from 4 shop templates
    Files: shop/account_login.html, shop/account_register.html,
           shop/account_forgot_password.html, shop/order_success.html
    Move all ic-* rules to static/css/shop-utilities.css
    Replace ic-* with semantic class names.

A4  FORMAT shop/account_register.html:16-20
    Current: every field on a single line (unreadable)
    Split each field to multi-line, properly indented.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE B — Security Hardening (Critical)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

B1  ADD CAPTCHA to all login/register forms
    Add reCAPTCHA v2 (or hCaptcha) to:
      - templates/auth/login.html
      - templates/shop/account_login.html
      - templates/shop/account_register.html
      - templates/shop/account_forgot_password.html
    Verify CAPTCHA server-side in routes.

B2  TIGHTEN rate limits
    Current: @limiter.limit("100 per hour; 50 per minute")
    Target:  @limiter.limit("20 per hour; 5 per minute")
    Apply to both /auth/login and /s/<slug>/account/login.

B3  ADD account lockout
    In routes/auth.py login():
      - On failed login: user.login_attempts += 1
      - If user.login_attempts >= 5: lock account for 30 minutes
      - Log lockout to LoginHistory with failure_reason='account_locked'
    In routes/shop.py account_login():
      - Same logic for ShopCustomerAccount
    Add flash message: "Account locked. Try again in X minutes."

B4  ADD real password reset for MAIN APP
    Current: "Forgot password?" links to /auth/support (purchase page!)
    Build:
      - GET  /auth/forgot-password  → template with email field
      - POST /auth/forgot-password  → send reset token email
      - GET  /auth/reset/<token>   → validate token, show form
      - POST /auth/reset/<token>   → update password
    Use URLSafeTimedSerializer (already imported in auth.py).
    Token expiry: 2 hours.

B5  ADD email verification for SHOP registration
    In services/shop_customer_auth_service.py:
      - On register: set is_active=False, generate verification_token
      - Send email with /s/<slug>/verify/<token> link
      - On click: is_active=True
    Update shop/account_register.html to show "Check your email" message.

B6  ADD confirm password field — shop/account_register.html
    Add: <input type="password" name="confirm_password" required>
    Server-side: reject if password != confirm_password

B7  ADD terms of service checkbox — shop/account_register.html
    Add: <input type="checkbox" name="agree_terms" required>
    Server-side: reject if not checked

B8  STRENGTHEN password requirements — shop
    Current: minimum 6 characters
    Target: minimum 8, with at least:
      - 1 uppercase
      - 1 lowercase
      - 1 number
      - 1 special character (!@#$%^&*)
    Add server-side validation + client-side indicator.

B9  FIX shop forgot password email sending
    In routes/shop.py:
      - POST /s/<slug>/account/forgot → call ShopCustomerAuthService.request_password_reset()
      - Send email with reset link /s/<slug>/reset/<token>
      - Add flash "If this email exists, a reset link has been sent."
    Add template: shop/reset_password.html (already exists at 802 bytes)
    Verify the full flow works end-to-end.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE C — UX Improvements (After Phase B)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

C1  ADD password visibility toggle — shop/account_login.html
    Mirror auth/login.html togglePassword functionality.

C2  ADD "Remember me" — shop/account_login.html
    Add checkbox + extend session expiry in ShopCustomerAuthService.login()

C3  ADD loading state to shop forms
    On submit: disable button, show spinner, change text to "جاري..."
    On error: re-enable button, show original text

C4  ADD password strength indicator — shop/account_register.html
    Real-time strength meter (weak/medium/strong) with colors.

C5  ADD inline validation feedback
    Show green checkmark for valid fields, red X for invalid.
    Validate on blur (not just on submit).

C6  REDUCE login page animations
    In static/css/azad-login.css:
      - Reduce particle count (6 → 3)
      - Reduce animation complexity
      - Add prefers-reduced-motion support
    Goal: improve LCP (Largest Contentful Paint).

C7  ADD "Login with Google" button (optional but recommended)
    OAuth2 integration for both main app and shop.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE D — Architecture (After Phase C)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

D1  UNIFIED AUTH SESSION
    Currently: flask-login for app, custom session for shop
    Target: Single auth system. Shop customers use flask-login with
            a custom UserMixin that wraps ShopCustomerAccount.
    Or: Implement JWT/OAuth2 for shop ↔ app integration.

D2  ADD 2FA/TOTP support
    New model: user_totp_secrets (user_id, secret, enabled)
    New templates: setup_2fa.html, verify_2fa.html
    New routes: /auth/2fa/setup, /auth/2fa/verify
    Use pyotp library.

D3  ADD suspicious login detection
    Compare: IP, geolocation, device, time of previous logins
    If anomaly: require email verification or block login
    Log to SecurityAlert model.

D4  ADD device management page
    Show all active sessions per user
    Allow "Log out all other devices"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FILES TO MODIFY (in priority order)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Templates:
  templates/auth/login.html
  templates/auth/forgot_password.html          (NEW)
  templates/auth/reset_password.html             (NEW)
  templates/auth/verify_email.html               (NEW)
  templates/shop/account_login.html
  templates/shop/account_register.html
  templates/shop/account_forgot_password.html
  templates/shop/account_reset_password.html     (verify existing)
  templates/shop/verify_email.html               (NEW)

Routes:
  routes/auth.py
  routes/shop.py

Services:
  services/shop_customer_auth_service.py

Models:
  models/shop_customer_account.py              (add fields if needed)

Static:
  static/css/azad-login.css
  static/css/shop-utilities.css                (NEW or extend)
  static/js/login.js                           (NEW or extend)

Config:
  config.py                                    (add RECAPTCHA keys)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DELIVERABLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. All code changes with tests (unit + integration)
2. No inline CSS/JS in any login template
3. All login/register/forgot flows tested end-to-end
4. Security: CAPTCHA, rate limit, lockout, password strength
5. Updated docs/login-audit-report.md with completion status
6. Report any NEW issues discovered during implementation

Execute Phase A first. Do not start Phase B until Phase A tests pass.
Report completion status per phase.

Proceed.
