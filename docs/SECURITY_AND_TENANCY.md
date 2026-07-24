# الأمان وعزل المستأجرين — AZADEXA ERP Security & Tenancy

> مستند حقيقي مبني على الكود الفعلي. آخر تحديث: يوليو 2026.

---

## 1. المبدأ الأساسي

كل مستأجر (Tenant) يعزل بياناته على مستوى قاعدة البيانات عبر العمود `tenant_id` الموجود في كل جدول تقريباً. الكشف عن بيانات مستأجر لآخر هو **خلل أمني من الدرجة P0**.

---

## 2. آلية العزل

### 2.1 الأدوات

| الأداة | الموقع | الوظيفة |
|--------|--------|---------|
| `tenant_query(Model)` | `utils/tenanting.py` | يُنشئ استعلامًا مُصفّى تلقائيًا بـ `tenant_id` |
| `tenant_get_or_404(Model, id)` | `utils/tenanting.py` | يبحث عن سجل واحد + يتحقق من `tenant_id` |
| `apply_tenant_scope(query)` | `utils/tenanting.py` | يُلحق شرط `tenant_id` على استعلام موجود |
| `get_active_tenant_id()` | `utils/tenanting.py` | يُرجع `tenant_id` النشط من `g.active_tenant_id` |

### 2.2 ORM Auto-Scoping

في `utils/tenant_orm.py`، يُسجّل `register_tenant_orm_scoping(app)` مستمع `before_query` يُلحق `tenant_id` تلقائيًا على كل استعلام.

```python
# utils/tenant_orm.py
@event.listens_for(db.session, "before_query")
def _auto_scope_queries(...):
    # يُلحق tenant_id على الاستعلامات
```

### 2.3 للطلبات المجهولة (API Key)

الديكور `@api_key_required` (في `utils/decorators.py`) يتحقق من مفتاح API ويضبط `g.active_tenant_id` لتفعيل العزل التلقائي.

```python
@api_key_required
def api_stock_sync():
    # g.active_tenant_id مضبوط تلقائيًا
    pass
```

---

## 3. الاستيثاق (Authentication)

### 3.1 المستويات

| المستوى | الديكور | الاستخدام |
|---------|---------|-----------|
| تسجيل الدخول | `@login_required` | أي مسار يتطلب مستخدمًا مسجلًا |
| الصلاحيات الدقيقة | `@permission_required('code')` | التحكم بالوصول المفصّل |
| لوحة المالك | `@owner_required` | مسارات لوحة المالك |
| المشرف | `@admin_required` | مسارات الإدارة |
| API Key | `@api_key_required` | طلبات خارجية بدون جلسة |

### 3.2 الجلسات

- `Flask-Login` يدير الجلسات.
- `CSRFProtect` يحمي من CSRF.
- `LoginHistory` يسجل كل محاولة دخول (IP، user-agent، النجاح/الفشل).

---

## 4. التحقق من المدخلات

### 4.1 JSON

كل استدعاء `request.get_json()` **يجب** أن يمرر `silent=True`.

```python
data = request.get_json(silent=True)
if data is None:
    return jsonify({'error': 'Invalid JSON'}), 400
```

### 4.2 Decimal

تحويلات `Decimal()` يجب أن تُحمّى بـ `str(data.get('field') or '0')`.

```python
amount = Decimal(str(data.get('amount') or '0'))
```

### 4.3 المُحقّقات

- `validate_positive_amount` — مبلغ موجب
- `validate_required_string` — نص مطلوب
- `validate_email` — بريد إلكتروني

---

## 5. الأمان على مستوى قاعدة البيانات

### 5.1 الذرية (Atomicity)

كل كتابة متعددة النماذج تُغلّف بـ `atomic_transaction` من `utils/db_safety.py`.

```python
from utils.db_safety import atomic_transaction

with atomic_transaction("create_sale"):
    db.session.add(sale)
    db.session.add(lines)
    db.session.flush()
    # commit يحدث فقط داخل db_safety.py
```

### 5.2 القواعد المطبّقة

| القاعدة | الواقع |
|---------|--------|
| `db.session.commit()` | موجود فقط في `utils/db_safety.py` و CLI commands |
| `db.session.rollback()` | موجود فقط في `utils/db_safety.py` و `gl_accounting_setup.py` (dry-run) |
| `db.session.flush()` | الوحيد المسموح به في `services/` |
| `db.session.add()` / `delete()` | يجب أن يكون داخل `atomic_transaction` |

### 5.3 حماية البطاقات

- `CardVault` يخزّن `card_hash` و `last_four` فقط — لا CVV، لا رقم كامل.
- التشفير باستخدام `CARD_ENCRYPTION_KEY`.
- `ALLOW_CARD_DECRYPTION` يتحكم في السماح بالفك.

---

## 6. Rate Limiting

`Flask-Limiter` مُفعّل على المسارات الحساسة.

---

## 7. تدقيق الأمان (Audit)

### 7.1 النماذج

- `AuditLog` — كل إجراء على جدول (action, table_name, record_id)
- `SecurityAlert` — تنبيهات الأمان (alert_type, severity)
- `LoginHistory` — سجل الدخول

### 7.2 المسارات

- `routes/owner/monitoring.py` — `system-health`, `security-alerts`, `login-history`

---

## 8. إعدادات الأمان في config.py

| المتغير | الغرض |
|---------|-------|
| `SECRET_KEY` | تشفير الجلسات |
| `CARD_ENCRYPTION_KEY` | تشفير البطاقات |
| `CSRF_ENABLED` | حماية CSRF |
| `PAYMENT_VAULT_TRUSTED_ORIGINS` | CORS للخزينة |
| `SQLALCHEMY_ISOLATION_LEVEL` | `REPEATABLE READ` |

---

## 9. ملاحظات تشغيلية

- **لا تُعدّل** فلاتر `tenant_id` يدويًا.
- **لا تُلغِ** `@login_required` أو `@permission_required` دون موافقة.
- **لا تُضِف** `db.session.commit()` خارج `db_safety.py`.
- كل API key يُولّد مع `tenant_id` ولا يمكنه الوصول إلى بيانات مستأجر آخر.

---
*هذا المستند مبني على الكود الفعلي. أي تغيير في المشروع يجب أن يعكس هنا.*
