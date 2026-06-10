# تقرير تدقيق صفحات تسجيل الدخول — Azad ERP Login Audit

تاريخ: 2026-06-10

## ملخص تنفيذي

اكتشفت **7 أخطاء HTML/أمنية حرجة** في صفحات تسجيل الدخول + **15+ ثغرة أمنية وتكدسات UX**. النظام يحتوي على نظامي مصادقة منفصلين (app vs shop) بدون تكامل.

---

## 1. أخطاء HTML حرجة (Bugs)

### 1.1 duplicate `crossorigin` — auth/login.html:11

```html
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css"
  integrity="sha384-t1nt8BQoYMLFN5p42tRAtuAAFQaCQODekUVeKKZrEnEyp4H2R0RHFz0KWpmj7i8g"
  crossorigin="anonymous" crossorigin="anonymous">
```

**crossorigin="anonymous" مكررة مرتين.**

### 1.2 duplicate `class` attribute — auth/login.html:117

```html
<form class="needs-validation" method="POST" action="{{ url_for('auth.login') }}"
  id="azadLoginForm" class="azad-login-form" autocomplete="on">
```

**class="azad-login-form" لا تعمل أبداً** — المتصفح يستخدم class الأول فقط (`needs-validation`). كل CSS تستهدف `.azad-login-form` غير مُطبق.

### 1.3 inline CSS anti-pattern — 4 قوالب shop

| القالب | الأسطر |
|---|---|
| shop/account_login.html | 5 أسطر inline CSS (ic-1..ic-5) |
| shop/account_register.html | 3 أسطر inline CSS (ic-1..ic-3) |
| shop/account_forgot_password.html | 2 أسطر inline CSS (ic-1..ic-2) |
| shop/order_success.html | 8 أسطر inline CSS (ic-1..ic-8) |

**التعليق "D6: externalized inline styles" خاطئ** — الـ styles ما زالت inline.

### 1.4 جميع حقول التسجيل في سطر واحد — shop/account_register.html:16-20

```html
<div class="ps-form-group"><label for="reg_name">{{ t('name') }} *</label><input type="text" id="reg_name" name="name" required minlength="2" aria-label="name" maxlength="100"></div>
```

كل حقل في سطر واحد — غير قابل للصيانة.

---

## 2. ثغرات أمنية Critical

### 2.1 لا يوجد CAPTCHA

لا reCAPTCHA ولا hCaptcha ولا Turnstile في أي من:
- auth/login (main app)
- shop/account_login
- shop/account_register
- shop/account_forgot_password

**التأثير**: Brute force attack سهل جداً.

### 2.2 لا يوجد account lockout

حقل `login_attempts` موجود في `User` model لكن:
- لا يُزداد عند فشل الدخول
- لا يُفحص قبل محاولة الدخول
- لا يوجد lockout duration

```python
# routes/auth.py:241
user.login_attempts = 0  # يُصفّر فقط عند النجاح
# لكن لا يوجد: user.login_attempts += 1 عند الفشل
```

**التأثير**: هجوم brute force غير محدود.

### 2.3 Rate limit ضعيف جداً

```python
@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("100 per hour; 50 per minute")
```

**50 محاولة/دقيقة = هجوم brute force مريح.**

**المقارنة**: Google 5/15min، AWS 5/5min.

### 2.4 لا يوجد 2FA / MFA

لا TOTP، لا SMS، لا WebAuthn/passkeys.

### 2.5 لا يوجد forced password change

لا يوجد:
- Expired password detection
- Compromised password check (HaveIBeenPwned)
- First-login password change requirement

### 2.6 لا يوجد device fingerprinting

لا يتم تسجيل:
- الجهاز المستخدم
- الموقع الجغرافي
- الوقت الاعتيادي للدخول

**التأثير**: لا يمكن اكتشاف الدخول المشبوه.

### 2.7 لا يوجد suspicious login alerts

لا يتم إرسال:
- بريد "دخول من جهاز جديد"
- بريد "دخول من موقع جغرافي غير معتاد"
- إشعار push

### 2.8 Password strength ضعيف — Shop customers

```python
# services/shop_customer_auth_service.py:65
if not password or len(password) < 6:
    raise ValueError('كلمة المرور 6 أحرف على الأقل.')
```

**6 أحرف فقط** — لا يُفحص:
- الأحرف الكبيرة/الصغيرة
- الأرقام
- الرموز
- التسلسلات الشائعة (123456, password)

### 2.9 Password reset للـ main app غير موجود

رابط "نسيت كلمة المرور؟" في auth/login.html يذهب إلى:
```html
<a href="{{ url_for('auth.support') }}">نسيت كلمة المرور؟</a>
```

وهذا هو `auth.support` — **صفحة شراء/دعم، ليس إعادة تعيين كلمة المرور.**

**التأثير**: مستخدمي المنصة لا يمكنهم استعادة كلمة المرور.

### 2.10 لا يوجد email verification — Shop registration

```python
# services/shop_customer_auth_service.py:58
def register(tenant_id, name, email, phone, password, address=None):
    # ... ينشئ الحساب مباشرة بدون تأكيد البريد
```

**التأثير**: أي بريد وهمي يمكنه التسجيل.

### 2.11 لا يوجد confirm password field

shop/account_register.html لا يحتوي على حقل "تأكيد كلمة المرور":
```html
<input type="password" id="reg_password" name="password" required minlength="6">
```

**التأثير**: أخطاء كتابة كلمة المرور لا يتم اكتشافها.

### 2.12 لا يوجد terms of service checkbox

shop/account_register.html لا يتطلب قبول الشروط.

### 2.13 Master login يُسجّل في session عادي

```python
# routes/auth.py:210
login_user(user, remember=remember)
```

Master key login يُعامل كدخول عادي — لا يوجد:
- Session shorter expiry
- Additional audit trail
- Forced 2FA after master login

---

## 3. تكدسات UX (User Experience Clutter)

### 3.1 صفحة تسجيل الدخول الرئيسية (auth/login.html — 264 سطر)

| المشكلة | الوصف |
|---|---|
| **Heavy** | 264 سطر HTML لصفحة تسجيل دخول |
| **CSS 923 سطر** | azad-login.css كبير جداً لصفحة واحدة |
| **Animations** | particles floating, grid background, glow effects — كلها animations CPU-intensive |
| **No loading on validation** | الزر يُظهر spinner فقط عند submit، ليس عند validation |
| **No inline validation** | لا feedback فوري للمستخدم |
| **Two login modes** | Tabs لـ "دخول الشركات" و "دخول المنصة" — يُربك المستخدم |
| **No email login** | فقط username (مثال: HZM_ahmad) — صعب التذكر |
| **No social login** | لا Google، لا Apple، لا OAuth |
| **No QR login** | لا يمكن تسجيل الدخول بالموبايل |

### 3.2 صفحة تسجيل الدخول للمتجر (shop/account_login.html — 37 سطر)

| المشكلة | الوصف |
|---|---|
| **Basic جداً** | فقط email + password |
| **No password toggle** | لا زر "إظهار كلمة المرور" |
| **No remember me** | لا يمكن البقاء مسجلاً |
| **No loading state** | لا spinner على الزر |
| **No inline CSS** — wait, YES | 5 أسطر inline CSS |
| **No "login with Google"** | — |

### 3.3 صفحة التسجيل (shop/account_register.html — 26 سطر)

| المشكلة | الوصف |
|---|---|
| **Compressed HTML** | كل الحقول في سطر واحد |
| **No password strength** | لا يُظهر قوة كلمة المرور |
| **No email verification** | يُنشئ الحساب فوراً |
| **No confirm password** | أخطاء الكتابة غير مكتشفة |
| **No terms checkbox** | غير قانوني في بعض الدول |
| **No loading state** | — |

### 3.4 صفحة استعادة كلمة المرور (shop/account_forgot_password.html — 41 سطر)

| المشكلة | الوصف |
|---|---|
| **Only email** | لا يُطلب أي verification إضافي |
| **No rate limit visible** | لا يوجد limiter decorator على forgot password route |
| **No success message template** | لا يُظهر "تم إرسال الرابط" |
| **Inline CSS** | ic-1, ic-2 |

---

## 4. تكدسات Architecture

### 4.1 نظامان مصادقة منفصلان

| | Main App (ERP) | Shop (Storefront) |
|---|---|---|
| **Method** | flask-login | Session-based (custom) |
| **Identifier** | username | email |
| **Password hash** | werkzeug (pbkdf2:sha256) | werkzeug (pbkdf2:sha256) |
| **Session** | flask-login session | `shop_account_{tenant_id}` |
| **Remember me** | ✅ | ❌ |
| **Logout** | GET /auth/logout | POST /s/<slug>/account/logout |
| **Password reset** | ❌ غير موجود | Partial (token exists) |
| **2FA** | ❌ | ❌ |
| **CAPTCHA** | ❌ | ❌ |

**التأثير**: مستخدمي المنصة لا يمكنهم تسجيل الدخول في المتجر والعكس.

### 4.2 Password reset للمتجر — ناقص

`ShopCustomerAuthService.request_password_reset()` تنشئ token لكن:
- لا يوجد route لإرسال البريد
- لا يوجد email template
- لا يوجد route لإعادة التعيين

```python
# services/shop_customer_auth_service.py:127
def request_password_reset(tenant_id, email):
    account.password_reset_token = secrets.token_urlsafe(32)
    account.password_reset_expires_at = datetime.now(timezone.utc) + timedelta(hours=2)
    # ... but NO EMAIL IS SENT
```

---

## 5. القوالب المتأثرة

| القالب | الأسطر | المشكلة |
|---|---|---|
| `templates/auth/login.html` | 264 | dupe class, dupe crossorigin, heavy, no password reset |
| `templates/shop/account_login.html` | 37 | inline CSS, basic UX, no remember me |
| `templates/shop/account_register.html` | 26 | inline CSS, compressed HTML, no verification |
| `templates/shop/account_forgot_password.html` | 41 | inline CSS, no email sending |
| `templates/shop/account_reset_password.html` | 13 | لم تُفحص (802 bytes) |
| `templates/shop/account_orders.html` | 66 | لم تُفحص |
| `templates/shop/account_order_detail.html` | 131 | لم تُفحص |

---

## 6. المسارات (Routes) المتأثرة

| Route | Blueprint | المشكلة |
|---|---|---|
| `/auth/login` | auth_bp | No CAPTCHA, weak rate limit, no lockout |
| `/auth/logout` | auth_bp | GET method (CSRF risk) |
| `/auth/support` | auth_bp | Returns purchase page, not support |
| `/s/<slug>/account/login` | shop_bp | No CAPTCHA, no lockout |
| `/s/<slug>/account/register` | shop_bp | No CAPTCHA, no email verification |
| `/s/<slug>/account/forgot` | shop_bp | No rate limit, no email sending |
| `/s/<slug>/account/logout` | shop_bp | POST (good) |

---

## 7. التوصيات العاجلة

### Priority 1: Critical Security (تنفيذ فوري)

| # | المهمة | الملفات |
|---|---|---|
| 1 | **إصلاح dupe crossorigin** | `templates/auth/login.html:11` |
| 2 | **إصلاح dupe class attribute** | `templates/auth/login.html:117` |
| 3 | **إضافة CAPTCHA** | `templates/auth/login.html`, `templates/shop/account_login.html`, `templates/shop/account_register.html` |
| 4 | **تشديد rate limit** | `routes/auth.py` — 5/15min بدلاً من 50/min |
| 5 | **إضافة account lockout** | `routes/auth.py`, `routes/shop.py` — 5 محاولات = 30 دقيقة lockout |
| 6 | **إضافة forced password reset** | `routes/auth.py` — route حقيقي لإعادة التعيين |
| 7 | **إضافة email verification** | `services/shop_customer_auth_service.py` |
| 8 | **إضافة confirm password** | `templates/shop/account_register.html` |
| 9 | **إضافة terms checkbox** | `templates/shop/account_register.html` |
| 10 | **إرسال بريد استعادة كلمة المرور** | `routes/shop.py` forgot_password route |

### Priority 2: UX & Performance

| # | المهمة | الملفات |
|---|---|---|
| 11 | **استخراج inline CSS** | 4 قوالب shop |
| 12 | **تنسيق HTML account_register** | `templates/shop/account_register.html` |
| 13 | **إضافة password toggle للمتجر** | `templates/shop/account_login.html` |
| 14 | **إضافة loading state للمتجر** | `templates/shop/account_login.html`, `templates/shop/account_register.html` |
| 15 | **إضافة password strength indicator** | `templates/shop/account_register.html` |
| 16 | **تخفيف animations في login.css** | `static/css/azad-login.css` |
| 17 | **إضافة inline validation** | `templates/auth/login.html` |
| 18 | **إضافة "Remember me" للمتجر** | `templates/shop/account_login.html`, `services/shop_customer_auth_service.py` |

### Priority 3: Architecture

| # | المهمة | الملفات |
|---|---|---|
| 19 | **تصميم SSO موحد** | app ↔ shop (flask-login للجميع) |
| 20 | **إضافة 2FA/TOTP** | `models/`, `routes/`, `templates/` |
| 21 | **إضافة WebAuthn/passkeys** | `routes/`, `templates/` |
| 22 | **إضافة social login** | `routes/`, `services/` |
| 23 | **إضافة suspicious login detection** | `routes/auth.py`, `services/` |
| 24 | **إضافة device management** | `models/`, `routes/`, `templates/` |
