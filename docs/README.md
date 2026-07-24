# دليل المشروع — AZADEXA ERP

> مستند حقيقي مبني على الكود الفعلي. آخر تحديث: يوليو 2026.

---

## 1. ما هو AZADEXA؟

نظام ERP SaaS متعدد المستأجرين (multi-tenant) مبني على Flask + SQLAlchemy + PostgreSQL. يدير:

- المبيعات والمشتريات والفواتير
- المخزون والمستودعات والتتبع التسلسلي
- المحاسبة العامة (GL) والشجرة المحاسبية
- نقاط البيع (POS) متعدد القنوات
- العملاء والموردين وعلاقاتهم (CRM)
- الموارد البشرية والرواتب
- المشاريع والمهام وجداول العمل (Timesheet)
- التذاكر وخدمة العملاء
- المتجر الإلكتروني
- التسويق بالبريد الإلكتروني
- المساعد الذكي المُعزز بالذكاء الاصطناعي
- التكامل مع أنظمة خارجية (POS sync, webhooks, GraphQL)

---

## 2. نقاط الدخول

| الملف | الدور |
|-------|--------|
| `app.py` | نقطة الدخول المحلية — يستدعي `create_app()` ويشغل الخادم |
| `wsgi.py` | نقطة الدخول الإنتاجية — يستخدمها Gunicorn/Docker |
| `config.py` | إعدادات البيئة (PostgreSQL, Redis, Celery, mail, مفاتيح API) |
| `extensions.py` | تهيئة الإضافات (SQLAlchemy, Login, CSRF, Cache, Limiter, Mail, Babel) |
| `cli_commands.py` | أوامر CLI (`build-assets`, `reconcile-stock`, `backup`, `seed-demo`) |

---

## 3. المتطلبات

- Python 3.11+
- PostgreSQL 15+ (مفضل)
- Redis (للـ Cache و Celery Broker)
- Node.js (لبناء الأصول الثابتة)

---

## 4. التشغيل السريع

```bash
# تثبيت الاعتماديات
python -m venv .venv
source .venv/bin/activate  # أو .venv\Scripts\activate على Windows
pip install -r requirements.txt

# تهيئة قاعدة البيانات
flask db upgrade

# تشغيل
python app.py
```

---

## 5. الاختبارات

```bash
pytest tests/unit -q
pytest tests/integration -q
```

أكثر من **10,000** اختبار وحدة و28 اختبار تكامل.

---

## 6. الوثائق الفنية

| المستند | الموضوع |
|---------|---------|
| `docs/PROJECT_OVERVIEW.md` | رؤية المشروع والأهداف |
| `docs/ARCHITECTURE.md` | البنية الطبقية والتدفقات |
| `docs/SYSTEM_MODULES.md` | الوحدات النظامية والموديلات |
| `docs/SECURITY_AND_TENANCY.md` | الأمان وعزل المستأجرين |
| `docs/ACCOUNTING_AND_INVENTORY_RULES.md` | قواعد المحاسبة والمخزون |
| `docs/OPERATIONS_RUNBOOK.md` | دليل التشغيل والصيانة |
| `docs/GRIMOIRE.md` | القواعد الهندسية غير القابلة للتفاوض |
| `docs/USER_GUIDE.md` | دليل المستخدم الشامل (عربي) |

---

## 7. الاتصال والدعم

- البريد: عبر إعدادات النظام (`mail`)
- الواتساب: دمج `WhatsAppService`
- WebSocket: `routes/websocket.py`
- GraphQL: `routes/graphql.py`

---
*هذا المستند مبني على الكود الفعلي. أي تغيير في المشروع يجب أن يعكس هنا.*
