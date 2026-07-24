# بنية النظام — AZADEXA ERP Architecture

> مستند حقيقي مبني على الكود الفعلي. آخر تحديث: يوليو 2026.

---

## 1. التصميم العام

تطبيق Flask أحادي العملية (monolith) منظم حسب الطبقات (layered architecture). لا microservices. كل مستأجر (tenant) يعزل بياناته على مستوى قاعدة البيانات عبر `tenant_id`.

```
┌─────────────────────────────────────────┐
│              HTTP Layer                  │
│  routes/  →  @login_required, @api_key  │
│  forms/   →  WTForms validation         │
├─────────────────────────────────────────┤
│           Service Layer                │
│  services/  →  pure business logic     │
│  atomic_transaction + db.session.flush   │
├─────────────────────────────────────────┤
│           Model Layer                  │
│  models/  →  ORM + scoped helpers      │
├─────────────────────────────────────────┤
│           Utilities                    │
│  utils/  →  stateless pure functions   │
├─────────────────────────────────────────┤
│           Infrastructure               │
│  PostgreSQL, Redis, Celery, Mail, WS   │
└─────────────────────────────────────────┘
```

---

## 2. الهيكل الدليلي

```
D:\Data\karaj\UAE\Azad-UAE/
├── app.py                    # Entrypoint محلي
├── wsgi.py                   # Entrypoint إنتاجي
├── config.py                 # Config classes
├── extensions.py             # Flask extensions init
├── cli_commands.py           # CLI commands
├── app/
│   ├── factory.py            # create_app()
│   ├── handlers.py           # Error handlers
│   ├── context.py            # Template context processors
│   └── runtime/              # Runtime repair scripts
├── bootstrap/
│   └── blueprints.py         # Blueprint registration
├── models/
│   ├── *.py                  # 96+ ORM model files
│   └── events.py             # ORM event listeners
├── services/
│   ├── *.py                  # 110+ business logic files
│   └── celery_tasks.py       # Background tasks
├── routes/
│   ├── *.py                  # 55+ HTTP handler files
│   ├── owner/                # Owner panel routes
│   └── ai_routes/            # AI assistant routes
├── utils/
│   ├── *.py                  # 80+ utilities
│   └── localization/         # Region-specific logic
├── tests/
│   ├── unit/                 # Unit tests (app, models, routes, services, utils, forms, ai_knowledge)
│   ├── integration/          # Integration tests
│   └── e2e/                  # End-to-end tests
├── scripts/
│   ├── ops/                  # enforce_grimoire.py, smoke tests
│   └── lint/                 # CI helpers
├── migrations/
│   └── versions/             # Alembic migrations
└── docs/                     # Documentation
```

---

## 3. طبقة المسارات (Routes)

- **فقط** معالجة HTTP: قراءة request، استدعاء service، تنسيق response.
- **ممنوع**: منطق الأعمال، استعلامات DB مباشرة، إنشاء نماذج.
- يتم تسجيل الـ blueprints في `bootstrap/blueprints.py`.

الملفات الرئيسية:

| الملف | المجال |
|-------|--------|
| `routes/pos.py` | POS (2726 سطر — الأكبر) |
| `routes/payments.py` | المدفوعات والسندات |
| `routes/sales.py` | المبيعات والفواتير |
| `routes/purchases.py` | المشتريات |
| `routes/products.py` | المنتجات والمخزون |
| `routes/shop.py` | المتجر الإلكتروني |
| `routes/store.py` | إعدادات المتجر |
| `routes/crm.py` | CRM |
| `routes/hr.py` | الموارد البشرية |
| `routes/payroll.py` | الرواتب |
| `routes/projects.py` | المشاريع |
| `routes/tickets.py` | التذاكر |
| `routes/ledger.py` | المحاسبة العامة |
| `routes/cheques.py` | الشيكات |
| `routes/email_marketing.py` | التسويق |
| `routes/api.py` | API عام |
| `routes/api_enhanced.py` | API محسّن |
| `routes/api_analytics.py` | تحليلات API |
| `routes/stock_sync.py` | مزامنة المخزون الخارجي |
| `routes/ai_routes/actions.py` | إجراءات المساعد الذكي |
| `routes/ai_routes/chat.py` | محادثة AI |
| `routes/ai_routes/assistant.py` | مساعد AI |
| `routes/ai_routes/analytics.py` | تحليلات AI |
| `routes/owner/core.py` | لوحة المالك |
| `routes/owner/settings.py` | إعدادات النظام |
| `routes/owner/tenants.py` | إدارة المستأجرين |
| `routes/owner/users.py` | إدارة المستخدمين |
| `routes/owner/database.py` | أدوات قاعدة البيانات |
| `routes/owner/monitoring.py` | المراقبة والصحة |
| `routes/owner/backups.py` | النسخ الاحتياطي |

---

## 4. طبقة الخدمات (Services)

- منطق الأعمال الخالص.
- **ممنوع** استيراد أي شيء من `routes/`.
- **ممنوع** `commit()` أو `rollback()` — فقط `flush()`.
- التعديلات متعددة النماذج تُغلّف بـ `atomic_transaction()`.

أبرز الخدمات:

| الخدمة | الدور |
|--------|-------|
| `sale_service.py` | إنشاء/تنفيذ/دفع المبيعات |
| `purchase_service.py` | إنشاء/إرجاع المشتريات |
| `stock_service.py` | حركة المخزون، COGS، WAC |
| `payment_service.py` | إنشاء المدفوعات والسندات |
| `gl_service.py` | دفتر الأستاذ العام |
| `gl_posting.py` | ترحيل القيود المحاسبية |
| `exchange_rate_service.py` | أسعار الصرف |
| `fx_revaluation_service.py` | إعادة تقييم المراكز المفتوحة |
| `promotion_service.py` | العروض (tiered, BOGO, bundle, combo) |
| `pos_cart_service.py` | السلات المؤجلة |
| `pos_cash_service.py` | حركات الخزينة |
| `pos_rma_service.py` | إرجاعات POS |
| `stock_sync_service.py` | مزامنة المخزون الخارجي |
| `ai_service.py` | منطق المساعد الذكي |
| `cheque_service.py` | دورة حياة الشيك |
| `bank_reconciliation_service.py` | التسوية البنكية |
| `payroll_service.py` | معالجة الرواتب |
| `project_service.py` | إدارة المشاريع والمهام |
| `webhook_service.py` | Webhooks |

---

## 5. طبقة النماذج (Models)

- تعريف ORM + مساعدات نطقية (scoped helpers).
- **ممنوع** مفاهيم HTTP أو منطق الأعمال.
- كل نموذج يحتوي على `tenant_id` (ما عدا الجداول العامة).

أبرز النماذج:

| النموذج | الجدول | العمود الرئيسي |
|---------|--------|----------------|
| `Tenant` | المستأجر | `slug`, `name`, `business_type` |
| `User` | المستخدم | `username`, `tenant_id`, `role_id` |
| `Product` | المنتج | `sku`, `category_id`, `current_stock` |
| `Sale` / `SaleLine` | المبيعات | `customer_id`, `warehouse_id`, `status` |
| `Purchase` / `PurchaseLine` | المشتريات | `supplier_id`, `warehouse_id` |
| `Payment` / `Receipt` | المدفوعات | `amount`, `currency`, `payment_method` |
| `GLAccount` / `GLJournalEntry` / `GLJournalLine` | المحاسبة | `code`, `type`, `debit`, `credit` |
| `Warehouse` / `ProductWarehouseStock` | المستودعات | `branch_id`, `warehouse_type` |
| `Customer` / `Supplier` | العملاء والموردين | `balance`, `tenant_id` |
| `Expense` / `ExpenseCategory` | المصروفات | `amount`, `amount_aed` |
| `Cheque` | الشيكات | `cheque_number`, `status`, `amount` |
| `Employee` / `PayrollTransaction` | الموارد البشرية | `net_salary`, `status` |
| `Project` / `Task` | المشاريع | `status`, `start_date`, `end_date` |
| `Ticket` / `TicketComment` | التذاكر | `status`, `priority_id` |
| `CRMLead` / `CRMStage` | CRM | `stage_id`, `probability` |
| `PosSession` / `PosShift` / `PosCart` | POS | `branch_id`, `user_id`, `status` |
| `SyncBatch` | المزامنة | `batch_type`, `status`, `record_count` |
| `APIKey` | مفاتيح API | `key`, `secret`, `tenant_id` |
| `CardVault` / `PaymentVault` | خزينة الدفع | `card_hash`, `provider` |
| `EmailCampaign` / `EmailTemplate` | التسويق | `subject`, `sent_at` |
| `ShopCustomerAccount` / `ShopAbandonedCart` | المتجر | `email`, `cart_data` |

---

## 6. الأدوات المساعدة (Utils)

- دوال خالصة، عديمة الحالة.
- **ممنوع** استيراد `routes/` أو `services/` (باستثناء `db_safety`, `tenanting`).

أبرز الأدوات:

| الأداة | الدور |
|--------|-------|
| `utils/db_safety.py` | `atomic_transaction`, `safe_commit` |
| `utils/tenanting.py` | `tenant_query`, `apply_tenant_scope`, `tenant_get_or_404` |
| `utils/tenant_orm.py` | تسجيل ORM scoping تلقائيًا |
| `utils/currency_utils.py` | `convert_and_quantize_aed`, `get_currency_symbol` |
| `utils/decorators.py` | `@permission_required`, `@api_key_required`, `@owner_required` |
| `utils/validators.py` | `validate_positive_amount`, `validate_required_string` |
| `utils/ai_permissions.py` | `get_ai_permission`, `user_has_ai_permission` |
| `utils/branching.py` | `get_active_branch_id`, `get_accessible_branches` |
| `utils/enhanced_logging.py` | `SecurityLogger`, `PerformanceLogger` |

---

## 7. التدفقات الرئيسية

### 7.1 تدفق البيع

```
Client → routes/sales.py → SaleService.create_sale()
   → stock_service.calculate_sale_cogs_and_deduct()
   → gl_posting.post_or_fail()
   → db.session.flush() (داخل atomic_transaction)
```

### 7.2 تدفق POS Checkout

```
Client → routes/pos.py → PromotionService.apply_promotions()
   → PosCartService (parked carts)
   → SaleService.create_sale()
   → StockService (deduct)
   → PaymentService.create_payment_for_sale()
   → GL posting
```

### 7.3 تدفق مزامنة المخزون الخارجي

```
External POS → POST /api/v2/stock/sync
   → @api_key_required (sets g.active_tenant_id)
   → StockSyncService.process_sync_payload()
   → SyncBatch (idempotency)
   → StockService.create_movement()
   → broadcast_stock_alert()
```

### 7.4 تدفق العملات المتعددة

```
Transaction → ExchangeRateService.resolve_exchange_rate_for_transaction()
   → convert_and_quantize_aed() (Decimal("0.001"), ROUND_HALF_UP)
   → FX revaluation (month-end)
```

---

## 8. البنية تحتية

| المكون | الاستخدام |
|--------|-----------|
| PostgreSQL | قاعدة البيانات الرئيسية. `REPEATABLE READ` isolation |
| Redis | Cache (null fallback)، Celery broker |
| Celery | Background jobs: reconciliation, reports, backups, exchange rates, AI training |
| SQLAlchemy | ORM + Alembic migrations |
| Flask-Login | إدارة الجلسات |
| Flask-Mail / SMTP | إرسال البريد |
| Flask-Caching | تخزين مؤقت (Redis أو null) |
| Flask-Limiter | Rate limiting |
| CSRFProtect | حماية CSRF |

---

## 9. التهيئة والتشغيل

```python
# app/factory.py
from app.factory import create_app
app = create_app()

# Bootstrap
init_extensions(app)
register_blueprints(app)
register_tenant_orm_scoping(app)
register_error_handlers(app)
register_context_processors(app)
```

---
*هذا المستند مبني على الكود الفعلي. أي تغيير في المشروع يجب أن يعكس هنا.*
