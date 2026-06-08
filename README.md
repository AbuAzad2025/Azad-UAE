# نظام إدارة المبيعات والمحاسبة متعدد الفروع
# Multi-Branch Sales & Accounting System

**Repository:** [https://github.com/AbuAzad2025/Azad-UAE](https://github.com/AbuAzad2025/Azad-UAE)

---

## ⚡ Quick Start

| Env | Command |
|-----|---------|
| **Dev (local)** | `cp env.example .env` → `python -m venv .venv` → `.venv\Scripts\activate` → `pip install -r requirements.txt` → `python app.py` |
| **Run tests** | `pytest tests/unit -v --tb=short` |
| **Production deploy** | See [DEPLOY.md](DEPLOY.md) |
| **Migrations** | `flask db migrate -m "msg"` → `flask db upgrade` |
| **Backup** | `pg_dump $DATABASE_URL > backup.sql` |

---

## العربية

هذا المشروع نظام تشغيلي فعلي لإدارة:

- المبيعات والمشتريات والمخزون.
- المحاسبة والقيود اليومية والتقارير المالية.
- الفروع والصلاحيات والعمليات اليومية.
- العزل بين الشركات/المستأجرين (tenants) والمتاجر.
- المتجر الإلكتروني وعمليات checkout عند تفعيله.

**الهدف:** توفير نسخة إنتاجية مستقرة، نظيفة، وآمنة للنشر على PythonAnywhere مع PostgreSQL.

> **تنبيه:** هذا المشروع **مملوك حصريًا** — جميع الحقوق محفوظة. وجود الكود على GitHub **لا يمنح** أي رخصة استخدام عامة. راجع `LICENSE`.

---

### 1. المكونات الأساسية

| المسار | الوظيفة |
|--------|---------|
| `app.py` | Application factory — نقطة تشغيل التطبيق (`create_app()`) |
| `routes/` | صفحات النظام وواجهات API (مبيعات، محاسبة، متجر، owner، …) |
| `models/` | نماذج SQLAlchemy لقاعدة البيانات |
| `services/` | منطق الأعمال (مبيعات، GL، متجر، مدفوعات، …) |
| `templates/` | واجهات HTML (Jinja2) |
| `static/` | أصول CSS/JS والملفات الثابتة |
| `migrations/` | ترحيلات Alembic (head: `store_init_005`) |
| `runtime_core/` | إصلاحات idempotent عند startup |
| `utils/system_init.py` | تهيئة owner، الأدوار، COA، tenant افتراضي |
| `utils/tenanting.py` / `utils/tenant_orm.py` | عزل المستأجرين على مستوى ORM والاستعلامات |
| `services/gl_posting.py` + خدمات GL | ترحيل القيود المحاسبية |
| `routes/shop.py` / `routes/store.py` | واجهة المتجر الإلكتروني ولوحة إدارته |
| `tools/qa/` | أدوات QA/UAT للتطوير (انظر القسم 9) |

---

### 2. متطلبات التشغيل

| البند | القيمة |
|-------|--------|
| Python | **3.11** (موصى به على PythonAnywhere) |
| قاعدة البيانات | **PostgreSQL** (مطلوب للإنتاج) |
| الإعداد | ملف `.env` مبني على `env.example` أو `.env.production.example` |
| الإنتاج | **WSGI** عبر PythonAnywhere — **لا** `python app.py` |
| التطوير المحلي | `python app.py` أو Flask dev server للاختبار السريع فقط |

---

### 3. متغيرات البيئة المهمة

استخدم **placeholders** فقط — لا تضع أسرارًا حقيقية في الكود أو Git:

```bash
# أساسي
SECRET_KEY=CHANGE_ME
CARD_ENCRYPTION_KEY=CHANGE_ME
OWNER_PASSWORD=CHANGE_ME
DATABASE_URL=postgresql+psycopg2://USER:PASS@HOST:5432/DBNAME

# بيئة الإنتاج
DEBUG=false
APP_ENV=production
FLASK_ENV=production
BASE_URL=https://YOUR-DOMAIN.pythonanywhere.com
PREFERRED_URL_SCHEME=https

# تسجيل دخول owner الاحتياطي (break-glass) — اختر أحد الخيارين:
AZAD_MASTER_DAILY_SEED=CHANGE_ME
# أو تعطيل master login:
# AZAD_MASTER_LOGIN_DISABLED=1

# اختياري
AZAD_MASTER_KEY_SHA256=
AZAD_MASTER_LOGIN_ALLOWLIST=127.0.0.1,::1
NOWPAYMENTS_IPN_SECRET=CHANGE_ME
```

> **مهم:** `DEBUG=false` يفعّل `SESSION_COOKIE_SECURE=True` — يتطلب **HTTPS** في الإنتاج.

> **ممنوع في الإنتاج:** `SKIP_SYSTEM_INTEGRITY=1`

> **NOWPayments IPN (canonical):** `https://YOUR-DOMAIN/payment-vault/webhook/nowpayments` — سجّل **URL واحد فقط** في لوحة NOWPayments. الكود يُرسل `ipn_callback_url` canonical لكل دفعة جديدة. `/auth/payment/callback` legacy fallback مؤقت فقط.

> **AI ORM listeners:** معطّلة افتراضيًا في الإنتاج (`AI_ORM_LISTENERS_ENABLED=false`). للتطوير يمكن تفعيلها.

---

### 4. النشر على PythonAnywhere + PostgreSQL

الدليل الكامل: [`DEPLOYMENT_PYTHONANYWHERE.md`](DEPLOYMENT_PYTHONANYWHERE.md)

**ملخص:**

1. حساب PythonAnywhere مدفوع + Python **3.11** virtualenv.
2. `git clone https://github.com/AbuAzad2025/Azad-UAE.git`
3. `pip install -r requirements.txt`
4. إنشاء PostgreSQL من تبويب Databases.
5. إنشاء `.env` على الخادم فقط (`chmod 600`).
6. `flask db upgrade` → التحقق من head: `store_init_005`.
7. ضبط **WSGI** → `application = create_app()`.
8. ربط `/static/` في تبويب Web.
9. **Reload** — لا تستخدم `python app.py` في الإنتاج.

---

### 5. تشغيل قاعدة بيانات نظيفة (تطوير محلي)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS
pip install -r requirements.txt

# انسخ env.example إلى .env وعدّل DATABASE_URL
python -m flask db upgrade
python -m flask db current      # store_init_005 (head)
python app.py                   # تطوير محلي فقط
```

---

### 6. ما يحدث تلقائيًا عند أول تشغيل

| العنصر | المصدر |
|--------|--------|
| الجداول، الصلاحيات، حساب owner | `ensure_system_integrity` في `app.py` |
| عملات، COA أساسي، مستودع | `_ensure_core_data()` |
| tenant افتراضي | `Tenant.get_current()` |
| COA كامل لكل tenant | `GLService.ensure_core_accounts()` عند أول قيد |
| ترحيل GL | `post_or_fail` في services |
| استهلاك الأصول | واجهة `/ledger/run-depreciation` |

بعد أول تشغيل: سجّل دخول `owner` بكلمة المرور من `OWNER_PASSWORD` في `.env`، أو استخدم **master login** اليومي إذا كان مفعّلًا (`AZAD_MASTER_DAILY_SEED`). ثم أنشئ الشركات والفروع والمستخدمين من الواجهة.

---

### 7. سياسة الأمان

- **لا أسرار في Git** — `.env`، `instance/`، uploads، وملفات DB مستبعدة عبر `.gitignore`.
- **عزل المستأجرين:** طبقات ORM + `tenant_query` + اختبارات UAT/storefront.
- **GraphQL، webhooks، master login:** مُحكّمة للإنتاج.
- **لا** `SKIP_SYSTEM_INTEGRITY=1` في الإنتاج.
- جميع الأسرار عبر متغيرات البيئة فقط.

---

### 8. حالة الفحوصات الحالية

| الفحص | النتيجة |
|-------|---------|
| Final Status | **PASS** |
| UAT (operational) | **59/59 PASS** |
| pip_audit | **Clean** |
| create_app | **OK** |
| Jinja2 templates compile | **275/275 PASS** |
| Accessibility (WCAG) | **0 errors on disk** |
| CSS externalization | **961 styles moved, 0 issues** |
| Form validation | **149 templates covered** |
| Critical / High مفتوح | **لا يوجد** |
| Cross-tenant leak مثبت | **لا يوجد** |
| Tenant isolation | **مُختبر** |
| Storefront isolation | **مُختبر** |

---

### 9. أدوات QA/UAT

موجودة في [`tools/qa/`](tools/qa/) — **للتطوير و staging فقط**:

| السكربت | الغرض |
|---------|-------|
| `uat_operational_check.py` | UAT شامل للنظام (59/59) |
| `storefront_isolation_check.py` | عزل المتجر بين tenants |
| `storefront_verify_cleanup_check.py` | تحقق + تنظيف بيانات `[TEST-STORE]` |

```bash
python tools/qa/uat_operational_check.py
python tools/qa/storefront_isolation_check.py
python tools/qa/storefront_verify_cleanup_check.py
```

**لا تُشغّل على production DB مباشرة.** بعض الاختبارات تنشئ بيانات مؤقتة وتنظفها.

### 9.1 أدوات الصيانة والتحسين

موجودة في [`tools/`](tools/) — **آمنة للتشغيل على أي بيئة** (read-only أو safe edits):

| السكربت | الغرض |
|---------|-------|
| `fix_accessibility.py` | إصلاح أخطاء WCAG تلقائياً |
| `count_a11y.py` | عدّاد أخطاء accessibility على القرص |
| `fix_viewport.py` | إضافة viewport meta لقوالب الطباعة |
| `externalize_inline_css.py` | نقل CSS inline إلى classes |
| `analyze_inline_styles.py` | تحليل styles المطلوب نقلها |
| `check_templates_compile.py` | التحقق من Jinja2 syntax |
| `check_jinja_nesting.py` | فحص nesting errors في Jinja2 |
| `verify_d6_integrity.py` | التحقق من صحة CSS المُ_externalized |
| `verify_css_validity.py` | parse CSS blocks بـ tinycss2 |
| `verify_js_toggles.py` | التأكد من بقاء JS display toggles |
| `apply_form_validation.py` | إضافة needs-validation للنماذج |
| `enhance_form_fields.py` | إضافة attributes للحقول تلقائياً |
| `permission_audit.py` | تدقيق صلاحيات الروابط والمسارات |
| `apply_permission_fixes.py` | إصلاح ثغرات الصلاحيات تلقائياً |
| `generate_sri.py` | توليد SRI hashes لـ CDN |
| `check_mobile_issues.py` | فحص مشاكل responsiveness (btn-sm, tables) |
| `fix_mobile_issues.py` | إصلاح batch للموبايل (btn-sm → btn, table-responsive) |

### 9.2 وثائق التصميم

| الوثيقة | الغرض |
|---------|-------|
| [`docs/UI_VISUAL_AUDIT.md`](docs/UI_VISUAL_AUDIT.md) | تقرير تدقيق UI — الوضع الحالي والمقترحات |
| [`docs/UI_DESIGN_SYSTEM.md`](docs/UI_DESIGN_SYSTEM.md) | نظام التصميم — tokens, ألوان, مكونات, RTL, موبايل |

---

### 10. حقوق النشر والاستخدام

- المشروع **مملوك حصريًا** لـ Azad Smart Systems.
- **جميع الحقوق محفوظة** — All Rights Reserved.
- يُمنع النسخ، التعديل، إعادة التوزيع، الاستخدام التجاري، أو إنشاء أعمال مشتقة بدون **إذن خطي صريح**.
- التفاصيل القانونية الكاملة في [`LICENSE`](LICENSE).

---

## English

This repository contains a **production-grade** multi-branch sales and accounting system for:

- sales, purchases, and inventory;
- accounting entries and financial reporting;
- branch-aware permissions and daily operations;
- tenant/company isolation;
- storefront and checkout workflows when enabled.

**Purpose:** maintain a stable, clean, deployment-ready codebase for PythonAnywhere + PostgreSQL.

> **Notice:** This project is **proprietary** — All Rights Reserved. Presence on GitHub does **not** grant any public license. See `LICENSE`.

---

### 1. Core Components

See the Arabic table above — same layout: `app.py`, `routes/`, `models/`, `services/`, `templates/`, `static/`, `migrations/` (head: `store_init_005`), `runtime_core/`, tenant isolation utils, GL posting, shop/store routes, and `tools/qa/`.

---

### 2. Runtime Requirements

- Python **3.11** (recommended on PythonAnywhere)
- **PostgreSQL** (required for production)
- `.env` based on `env.example`
- Production: **WSGI** on PythonAnywhere — **not** `python app.py`
- Local dev: `python app.py` for smoke testing only

---

### 3. Important Environment Variables

Use placeholders only — never commit real secrets:

```bash
SECRET_KEY=CHANGE_ME
CARD_ENCRYPTION_KEY=CHANGE_ME
OWNER_PASSWORD=CHANGE_ME
DATABASE_URL=postgresql+psycopg2://USER:PASS@HOST:5432/DBNAME
DEBUG=false
APP_ENV=production
AZAD_MASTER_DAILY_SEED=CHANGE_ME
# AZAD_MASTER_LOGIN_DISABLED=1
```

`DEBUG=false` requires **HTTPS** (`SESSION_COOKIE_SECURE=True`). Never set `SKIP_SYSTEM_INTEGRITY=1` in production.

**NOWPayments IPN (canonical):** `https://YOUR-DOMAIN/payment-vault/webhook/nowpayments` — register **one** URL in the NOWPayments dashboard only. New payments embed this canonical `ipn_callback_url` per request (`order_id`: `DONATION_*`, `PURCHASE_*`, `STORE_*`). `/auth/payment/callback` is a temporary legacy fallback.

**AI ORM listeners:** disabled by default in production (`AI_ORM_LISTENERS_ENABLED=false`).

---

### 4. PythonAnywhere + PostgreSQL Deployment

Full guide: [`DEPLOYMENT_PYTHONANYWHERE.md`](DEPLOYMENT_PYTHONANYWHERE.md)

Clone → virtualenv (3.11) → `pip install` → PostgreSQL → `.env` on server → `flask db upgrade` → WSGI `application = create_app()` → static mapping → reload.

---

### 5. Clean Database (Local Dev)

```bash
python -m venv .venv && pip install -r requirements.txt
# configure .env from env.example
python -m flask db upgrade
python app.py   # local dev only
```

---

### 6. First-Run Bootstrap

The app auto-creates owner, roles, core COA, default tenant, and runs idempotent repairs via `ensure_system_integrity`. Sign in as `owner` with `OWNER_PASSWORD` or daily master login (`AZAD_MASTER_DAILY_SEED`), then configure companies, branches, and users in the UI.

---

### 7. Security Policy

- No secrets in Git; env-only configuration.
- Multi-layer tenant isolation (ORM + query scoping + QA tests).
- Hardened GraphQL, webhooks, and master login for production.
- No `SKIP_SYSTEM_INTEGRITY=1` in production.

---

### 8. Current Verification Status

| Check | Result |
|-------|--------|
| Final Status | **PASS** |
| UAT | **59/59 PASS** |
| pip_audit | **Clean** |
| create_app | **OK** |
| Jinja2 templates compile | **275/275 PASS** |
| Accessibility (WCAG) | **0 errors on disk** |
| CSS externalization | **961 styles moved, 0 issues** |
| Form validation | **149 templates covered** |
| Open Critical/High | **None** |
| Proven cross-tenant leak | **None** |

---

### 9. QA/UAT Tools

In [`tools/qa/`](tools/qa/) — **dev/staging only**. Do not run against production databases. See `tools/qa/README.md`.

---

### 10. Copyright and Usage

Proprietary software — **All Rights Reserved**. No copying, modification, redistribution, commercial use, or derivative works without explicit written permission. Full terms in [`LICENSE`](LICENSE).

---

© 2025 Azad Smart Systems — All Rights Reserved
