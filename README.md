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
- `migrations/`: ملفات ترحيل قاعدة البيانات.
- `seed_comprehensive.py`: بذور بيانات تشغيلية للتجهيز الأولي.

### متطلبات التشغيل

- Python 3.11+
- PostgreSQL
- ملف إعدادات بيئة مبني على `env.example`

### تشغيل سريع (تهيئة أولية)

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

ثم:
- اضبط متغيرات البيئة عبر نسخة من `env.example`.
- شغّل migrations.
- شغّل `seed_comprehensive.py` عند الحاجة.

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
- `migrations/`: database migration files.
- `seed_comprehensive.py`: initial operational seed data.

### Runtime Requirements

- Python 3.11+
- PostgreSQL
- environment configuration based on `env.example`

### Quick Start (initial setup)

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Then:
- configure environment variables from `env.example`;
- run migrations;
- run `seed_comprehensive.py` if seed data is needed.

### Security Policy

- no secrets or deployment credentials are committed;
- all secrets must be provided through environment variables;
- real API keys/passwords must never be embedded in source code.

### Copyright and Usage

- this project is **exclusively owned** by the rights holder;
- all rights are reserved;
- copying, modification, redistribution, commercial use, and derivative works are prohibited without explicit written permission.
- see `LICENSE` for full legal terms.
