# نظام إدارة المبيعات والمحاسبة متعدد الفروع
# Multi-Branch Sales & Accounting System

## العربية

هذا المشروع نظام تشغيلي فعلي لإدارة:
- المبيعات والمشتريات والمخزون.
- المحاسبة والقيود اليومية والتقارير.
- الفروع والصلاحيات والعمليات التشغيلية اليومية.

الهدف من هذا المستودع هو توفير نسخة إنتاجية مستقرة، نظيفة، وآمنة للنشر.

### المكونات الأساسية

- `app.py`: نقطة تشغيل التطبيق.
- `routes/`: واجهات النظام (API + صفحات).
- `models/`: نماذج قاعدة البيانات.
- `services/`: منطق الأعمال والخدمات.
- `templates/`: واجهات HTML.
- `static/`: الأصول الأمامية (CSS/JS).
- `migrations/`: ترحيلات Alembic (head: `accounting_scope_001`).
- `runtime_core/`: إصلاحات idempotent عند startup.
- `utils/system_init.py`: تهيئة owner، أدوار، COA، tenant افتراضي.

### متطلبات التشغيل

- Python 3.11+
- PostgreSQL
- ملف إعدادات بيئة مبني على `env.example`

### النشر (قاعدة بيانات نظيفة)

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

```bash
# .env من env.example — DATABASE_URL, MASTER_KEY, APP_ENV=production
python -m flask db upgrade
python -m flask db current    # accounting_scope_001 (head)
python app.py
```

**لا تضبط `SKIP_SYSTEM_INTEGRITY=1` في الإنتاج.**

### ما يحدث تلقائياً عند التشغيل

| العنصر | المصدر |
|--------|--------|
| الجداول، الصلاحيات، owner | `ensure_system_integrity` في `app.py` |
| عملات، COA أساسي، مستودع | `_ensure_core_data()` |
| tenant افتراضي | `Tenant.get_current()` |
| COA كامل per tenant | `GLService.ensure_core_accounts()` عند أول قيد |
| ترحيل GL | `post_or_fail` في services |
| استهلاك الأصول | واجهة `/ledger/run-depreciation` |

بعد أول تشغيل: سجّل دخول `owner` بـ `MASTER_KEY`، ثم أنشئ الشركات والفروع والمستخدمين من الواجهة.

**لا سكriptات CLI خارجية** — أي تجهيز إضاف يُبنى داخل النظام (routes/services).

### سياسة الأمان

- لا يتم رفع أسرار أو بيانات نشر حساسة.
- أي أسرار يجب أن تُدار عبر متغيرات البيئة فقط.
- يُمنع تضمين مفاتيح API أو كلمات مرور حقيقية داخل الكود.

### حقوق النشر والاستخدام

- هذا المشروع **مملوك حصريًا** لصاحب الحقوق.
- جميع الحقوق محفوظة.
- يُمنع النسخ أو التعديل أو إعادة التوزيع أو التشغيل التجاري أو إنشاء أعمال مشتقة بدون إذن خطي صريح.
- التفاصيل القانونية الكاملة في ملف `LICENSE`.

---

## English

This repository contains a production-grade system for:
- sales, purchases, and inventory operations;
- accounting entries and reporting;
- branch-aware permissions and day-to-day workflows.

The purpose of this repository is to maintain a stable, clean, and deployment-ready production codebase.

### Core Components

- `app.py`: application entry point.
- `routes/`: API and page endpoints.
- `models/`: database models.
- `services/`: business logic layer.
- `templates/`: HTML views.
- `static/`: frontend assets (CSS/JS).
- `migrations/`: Alembic migrations (head: `accounting_scope_001`).
- `runtime_core/`: idempotent startup repairs.
- `utils/system_init.py`: owner, roles, COA, default tenant bootstrap.

### Runtime Requirements

- Python 3.11+
- PostgreSQL
- environment configuration based on `env.example`

### Deployment (clean database)

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

```bash
# .env from env.example — DATABASE_URL, MASTER_KEY, APP_ENV=production
python -m flask db upgrade
python -m flask db current
python app.py
```

Do **not** set `SKIP_SYSTEM_INTEGRITY=1` in production.

On first start the app creates owner, roles, core COA, and default tenant automatically. Sign in as `owner` with `MASTER_KEY`, then configure companies, branches, and users in the UI.

No external CLI scripts — extend via routes/services inside the codebase.

### Security Policy

- no secrets or deployment credentials are committed;
- all secrets must be provided through environment variables;
- real API keys/passwords must never be embedded in source code.

### Copyright and Usage

- this project is **exclusively owned** by the rights holder;
- all rights are reserved;
- copying, modification, redistribution, commercial use, and derivative works are prohibited without explicit written permission.
- see `LICENSE` for full legal terms.
