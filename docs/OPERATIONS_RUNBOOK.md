# دليل التشغيل — AZADEXA ERP Operations Runbook

> مستند حقيقي مبني على الكود الفعلي. آخر تحديث: يوليو 2026.

---

## 1. الإعداد الأولي

### 1.1 تهيئة قاعدة البيانات

```bash
flask db upgrade
```

### 1.2 زرع بيانات تجريبية

```bash
flask seed-demo
```

### 1.3 إنشاء مستأجر أول

- عبر لوحة المالك: `/master-login-info`
- ثم `/tenants/create`

### 1.4 إعداد GL

- `GLAccountingSetup` يُشغّل تلقائيًا عند إنشاء مستأجر.
- `ENABLE_DYNAMIC_GL_MAPPING = True` في `config.py`.

---

## 2. العمليات اليومية

### 2.1 تشغيل الخادم

```bash
python app.py
# أو
flask run
```

### 2.2 Celery Worker

```bash
celery -A app.celery worker --loglevel=info
celery -A app.celery beat --loglevel=info  # للمهام المجدولة
```

### 2.3 تحديث أسعار الصرف

```bash
# تلقائي عبر Celery beat
# أو يدوي:
flask update-exchange-rates
```

### 2.4 تسوية المخزون

```bash
flask reconcile-stock
```

---

## 3. النسخ الاحتياطي

### 3.1 يدوي

```bash
flask backup
```

### 3.2 تلقائي

- Celery task: `auto_backup_database`
- إعدادات في `routes/owner/backups.py`

### 3.3 استعادة نطاقية (Scoped Restore)

```bash
# استعادة بيانات مستأجر واحد فقط
# عبر services/backup_scoped_restore.py
```

---

## 4. المراقبة

### 4.1 صحة النظام

- `routes/owner/monitoring.py` → `/system-health`
- `services/health_service.py` — فحص DB, Redis, Celery.

### 4.2 تنبيهات الأمان

- `SecurityAlert` — تنبيهات الأمان.
- `/security-alerts` في لوحة المالك.

### 4.3 سجل الأخطاء

- `ErrorAuditLog` — تدقيق الأخطاء.
- `/error-audit-logs` في لوحة المالك.

---

## 5. الصيانة

### 5.1 إصلاح شجرة GL

```bash
flask maintenance rebuild-gl-tree
```

### 5.2 إصلاح مراكز التكلفة

```bash
flask maintenance fix-cost-centers
```

### 5.3 تنظيف قواعد البيانات التجريبية

```bash
flask maintenance cleanup-test-dbs
```

### 5.4 تحسين قاعدة البيانات

```bash
flask database-optimize
```

---

## 6. CLI Commands الكاملة

| الأمر | الوظيفة | الملف |
|-------|---------|-------|
| `flask build-assets` | بناء الأصول الثابتة | `cli_commands.py` |
| `flask reconcile-stock` | تسوية المخزون | `cli_commands.py` |
| `flask backup` | نسخ احتياطي | `cli_commands.py` |
| `flask reset-platform-db` | إعادة تعيين قاعدة المنصة | `cli_commands.py` |
| `flask seed-demo` | زرع بيانات تجريبية | `cli_commands.py` |
| `flask sanitize-legacy-industries` | تنظيف الصناعات القديمة | `cli_commands.py` |

---

## 7. تحديثات Alembic

### 7.1 إنشاء migration

```bash
flask db migrate -m "add_new_table"
```

### 7.2 آخر migrations

| الملف | الموضوع |
|-------|---------|
| `squash_001_baseline` | Baseline شامل |
| `e75de4aeafea_add_subscription_plan_duration` | مدة خطة الاشتراك |
| `d4a2b8c91e07_add_pos_phase4_omnichannel` | POS Phase 4 |
| `c9f1e07b3a24_add_pos_phase3_security` | أمان POS Phase 3 |
| `b4e8d3f02a16_add_pos_phase2_parked_carts` | السلات المؤجلة |

---

## 8. تكاملات خارجية

### 8.1 Stripe
- Webhook endpoint: `/stripe`
- `routes/billing_webhooks.py`

### 8.2 NOWPayments
- `services/nowpayments_service.py`
- `routes/auth.py` — `/payment/status/<id>`

### 8.3 WhatsApp
- `services/whatsapp_service.py`
- إعدادات في `routes/owner/settings.py`

### 8.4 POS خارجي
- `POST /api/v2/stock/sync`
- `GET /api/v2/stock/sync/status/<batch_id>`
- يتطلب `APIKey` مع `tenant_id`.

---

## 9. استكشاف الأخطاء

### 9.1 فشل الاختبارات

```bash
pytest tests/unit -x --tb=short -q
```

### 9.2 GRIMOIRE violations

```bash
python scripts/ops/enforce_grimoire.py
```

### 9.3 Lint

```bash
ruff check .
ruff format .
```

### 9.4 Type checking

```bash
mypy services/ routes/ utils/ models/
```

---

## 10. اتصالات الدعم

- الدعم الفني: `routes/auth.py` → `/support`
- التذاكر: `routes/tickets.py`
- الواتساب: `services/whatsapp_service.py`

---
*هذا المستند مبني على الكود الفعلي. أي تغيير في المشروع يجب أن يعكس هنا.*
