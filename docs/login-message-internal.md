Subject: Login Pages — Internal-Only Fixes (No External Dependencies)

Dr. AI,

I have manually audited all login pages and authentication flows in the Azad ERP codebase. The full technical report is documented in:

  docs/login-audit-report.md

IMPORTANT CONSTRAINT: The system has NO email service integration. Do NOT propose any feature that requires sending email, external CAPTCHA APIs, OAuth providers, or any third-party integration. All fixes must be 100% internal/self-contained.

You are assigned to fix login pages immediately. I found 7 critical HTML bugs and 15+ security/UX issues.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE A — Fix Critical HTML Bugs (Execute First)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

A1  FIX DUPLICATE crossorigin — templates/auth/login.html:11
    crossorigin="anonymous" appears twice. Remove one.

A2  FIX DUPLICATE class attribute — templates/auth/login.html:117
    <form class="needs-validation" ... class="azad-login-form" ...>
    The second class NEVER applies. Merge into one class attribute:
      <form class="needs-validation azad-login-form" ...>
    Then verify .azad-login-form CSS selectors actually work.

A3  REMOVE inline CSS from 4 shop templates
    Files: shop/account_login.html, shop/account_register.html,
           shop/account_forgot_password.html, shop/order_success.html
    Move all ic-* rules to static/css/shop-utilities.css
    Replace ic-* with semantic class names.

A4  FORMAT shop/account_register.html:16-20
    Every field is on a single line (unreadable). Split to multi-line.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE B — Security Hardening (Internal Only, No External Services)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

B1  TIGHTEN rate limits
    Current: @limiter.limit("100 per hour; 50 per minute")
    Target:  @limiter.limit("20 per hour; 5 per minute")
    Apply to both /auth/login and /s/<slug>/account/login.

B2  ADD account lockout
    In routes/auth.py login():
      - On failed login: user.login_attempts += 1
      - If >= 5: lock for 30 minutes
      - Log to LoginHistory with failure_reason='account_locked'
    In routes/shop.py account_login():
      - Same logic for ShopCustomerAccount
    Store lockout_until timestamp in DB.
    Flash: "Account locked. Try again in X minutes."

B3  ADD confirm password field — shop/account_register.html
    Add <input type="password" name="confirm_password" required>
    Server-side: reject if password != confirm_password

B4  ADD terms of service checkbox — shop/account_register.html
    Add <input type="checkbox" name="agree_terms" required>
    Server-side: reject if not checked

B5  STRENGTHEN password requirements — shop
    Current: minimum 6 characters
    Target: minimum 8, with at least 1 uppercase, 1 lowercase, 1 number, 1 special character
    Add server-side validation + client-side JS indicator.

B6  FIX "Forgot password" for MAIN APP (no email)
    Current: links to /auth/support (purchase page!)
    Solution:
      - Show page: "Contact your system administrator to reset your password."
      - Add "Reset user password" button in owner/users_list.html
      - Admin sets temporary password -> user must change on first login

B7  FIX shop forgot password (no email)
    POST /s/<slug>/account/forgot -> show:
      "Please contact the store owner to reset your password."
    Admin resets password from store admin panel.
    Remove unused token generation code or convert to admin-initiated.

B8  ADD security questions (internal password recovery backup)
    New table: shop_security_questions (account_id, question, answer_hash)
    Example questions: mother's name, city of birth
    Answer hashed with bcrypt.
    Forgot password flow: answer correctly -> allow reset.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE C — UX Improvements (Internal Only)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

C1  ADD password visibility toggle — shop/account_login.html
    Mirror auth/login.html togglePassword functionality.

C2  ADD "Remember me" — shop/account_login.html
    Add checkbox + extend session expiry in ShopCustomerAuthService.login()

C3  ADD loading state to shop forms
    On submit: disable button, show spinner, change text to "جاري..."
    On error: re-enable button, show original text

C4  ADD password strength indicator — shop/account_register.html
    Real-time JS meter (weak/medium/strong) with colors.

C5  ADD inline validation feedback
    Green checkmark for valid, red X for invalid. Validate on blur.

C6  REDUCE login page animations
    In static/css/azad-login.css:
      - Reduce particle count (6 -> 3)
      - Add prefers-reduced-motion support
    Goal: improve LCP.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE D — Architecture (Internal Only)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

D1  ADD 2FA/TOTP support (internal, no SMS/email)
    New model: user_totp_secrets (user_id, secret, enabled)
    Use pyotp library. QR code generated locally with qrcode library.
    Backup codes stored hashed in DB.
    Routes: /auth/2fa/setup, /auth/2fa/verify

D2  ADD device/session management (internal)
    New model: user_sessions (user_id, session_token, ip, user_agent, created_at, last_active)
    Page: /auth/sessions -> show all devices, allow "Log out this device".

D3  UNIFIED AUTH SESSION (internal refactor only)
    Currently: flask-login for app, custom session for shop
    Target: Single auth system. Shop customers use flask-login with
            a custom UserMixin that wraps ShopCustomerAccount.
    Pure refactoring, no external dependencies.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FILES TO MODIFY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Templates:
  templates/auth/login.html
  templates/shop/account_login.html
  templates/shop/account_register.html
  templates/shop/account_forgot_password.html
  templates/shop/account_reset_password.html

Routes:
  routes/auth.py
  routes/shop.py

Services:
  services/shop_customer_auth_service.py

Models:
  models/shop_customer_account.py
  models/shop_security_questions.py            (NEW)
  models/user_totp_secrets.py                 (NEW)
  models/user_sessions.py                     (NEW)

Static:
  static/css/azad-login.css
  static/css/shop-utilities.css               (NEW or extend)
  static/js/login.js                            (NEW or extend)
  static/js/shop-auth.js                        (NEW)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DELIVERABLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. All code changes with tests (unit + integration)
2. No inline CSS/JS in any login template
3. No external service dependencies (email, CAPTCHA, OAuth, SMS)
4. All login/register flows tested end-to-end
5. Security: rate limit, lockout, password strength, 2FA
6. Updated docs/login-audit-report.md with completion status
7. Report any NEW issues discovered during implementation

Execute Phase A first. Do not start Phase B until Phase A tests pass.
Report completion status per phase.

Proceed.
