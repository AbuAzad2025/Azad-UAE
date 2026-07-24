# دليل تقني شامل — AZADEXA ERP

## الجزء 1: نظرة عامة

AZADEXA هو نظام ERP SaaS متعدد المستأجرين (multi-tenant) مبني على Flask + SQLAlchemy + PostgreSQL. يدير: المبيعات والمشتريات والفواتير، المخزون والمستودعات والتتبع التسلسلي، المحاسبة العامة (GL) والشجرة المحاسبية، نقاط البيع (POS) متعدد القنوات، العملاء والموردين وCRM، الموارد البشرية والرواتب، المشاريع والمهام وجداول العمل، التذاكر وخدمة العملاء، المتجر الإلكتروني، التسويق بالبريد الإلكتروني، المساعد الذكي المُعزز بالذكاء الاصطناعي، التكامل مع أنظمة خارجية (POS sync، webhooks، GraphQL).

النظام يحتوي على 96 ملف نموذج (models/*.py)، 110+ خدمة (services/*.py)، 55+ ملف مسارات (routes/*.py)، 80+ أداة مساعدة (utils/*.py)، و10,000+ اختبار.

الميزات الرئيسية المُفعّلة حالياً:
- POS متعدد القنوات (promotion engine، parked carts، manager overrides، cash movements، RMA، split tender)
- تعدد العملات (FX settlement، revaluation، AED quantization)
- المساعد الذكي (RBAC + confirmation gates + neural engine)
- مزامنة POS خارجي (API key auth، sync batches، idempotency)
- خزينة الدفع (CardVault، PaymentVault)
- CRM (leads، stages، teams)
- الموارد البشرية والرواتب
- المشاريع والمهام
- التذاكر
- المتجر الإلكتروني
- التسويق بالبريد
- الأصول الثابتة والإهلاك
- الشيكات (receive، deposit، clear، bounce، cancel)
- التسوية البنكية
- Webhooks، GraphQL، WebSocket، WhatsApp

## الجزء 2: البنية والهيكل

التصميم: تطبيق Flask أحادي العملية (monolith) منظم حسب الطبقات. كل مستأجر يعزل بياناته عبر `tenant_id`.

الهيكل الدليلي:
- `app.py` — Entrypoint محلي
- `wsgi.py` — Entrypoint إنتاجي
- `config.py` — Config classes (PostgreSQL، Redis، Celery، mail، API keys)
- `extensions.py` — Flask extensions (SQLAlchemy، Login، CSRF، Cache، Limiter، Mail، Babel)
- `cli_commands.py` — CLI commands (build-assets، reconcile-stock، backup، seed-demo)
- `app/factory.py` — `create_app()`
- `app/handlers.py` — Error handlers
- `app/context.py` — Template context processors
- `bootstrap/blueprints.py` — Blueprint registration
- `models/*.py` — 96+ ORM model files
- `services/*.py` — 110+ business logic files
- `routes/*.py` — 55+ HTTP handler files
- `utils/*.py` — 80+ utilities
- `tests/unit/` — Unit tests
- `tests/integration/` — Integration tests
- `migrations/versions/` — Alembic migrations

### الطبقات

**Routes**: فقط معالجة HTTP — قراءة request، استدعاء service، تنسيق response. ممنوع: منطق الأعمال، استعلامات DB مباشرة.

**Services**: منطق الأعمال الخالص. ممنوع: استيراد `routes/`، `commit()` / `rollback()` — فقط `flush()` داخل `atomic_transaction()`.

**Models**: ORM + scoped helpers. ممنوع: HTTP concepts، business logic.

**Utils**: دوال خالصة، عديمة الحالة. ممنوع: استيراد `routes/` أو `services/` (باستثناء `db_safety`، `tenanting`).

### أبرز المسارات

| الملف | المجال |
|-------|--------|
| `routes/pos.py` | POS (2726 سطر) |
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
| `routes/email_marketing.py` | التسويق بالبريد |
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

### أبرز الخدمات

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
| `promotion_service.py` | العروض (tiered، BOGO، bundle، combo) |
| `pos_cart_service.py` | السلات المؤجلة |
| `pos_cash_service.py` | حركات الخزينة |
| `pos_rma_service.py` | إرجاعات POS |
| `stock_sync_service.py` | مزامنة المخزون الخارجي |
| `ai_service.py` | منطق المساعد الذكي |
| `cheque_service.py` | دورة حياة الشيك |
| `bank_reconciliation_service.py` | التسوية البنكية |
| `payroll_service.py` | معالجة الرواتب |
| `project_service.py` | إدارة المشاريع |
| `webhook_service.py` | Webhooks |

### أبرز الأدوات المساعدة

| الأداة | الدور |
|--------|-------|
| `utils/db_safety.py` | `atomic_transaction`، `safe_commit` |
| `utils/tenanting.py` | `tenant_query`، `apply_tenant_scope`، `tenant_get_or_404` |
| `utils/tenant_orm.py` | تسجيل ORM scoping تلقائيًا |
| `utils/currency_utils.py` | `convert_and_quantize_aed`، `get_currency_symbol` |
| `utils/decorators.py` | `@permission_required`، `@api_key_required`، `@owner_required` |
| `utils/validators.py` | `validate_positive_amount`، `validate_required_string` |
| `utils/ai_permissions.py` | `get_ai_permission`، `user_has_ai_permission` |
| `utils/branching.py` | `get_active_branch_id`، `get_accessible_branches` |
| `utils/enhanced_logging.py` | `SecurityLogger`، `PerformanceLogger` |

### أبرز النماذج

| النموذج | العمود الرئيسي |
|---------|----------------|
| `Tenant` | `slug`، `name`، `business_type` |
| `User` | `username`، `tenant_id`، `role_id` |
| `Product` | `sku`، `category_id`، `current_stock` |
| `Sale` / `SaleLine` | `customer_id`، `warehouse_id`، `status` |
| `Purchase` / `PurchaseLine` | `supplier_id`، `warehouse_id` |
| `Payment` / `Receipt` | `amount`، `currency`، `payment_method` |
| `GLAccount` / `GLJournalEntry` / `GLJournalLine` | `code`، `type`، `debit`، `credit` |
| `Warehouse` / `ProductWarehouseStock` | `branch_id`، `warehouse_type` |
| `Customer` / `Supplier` | `balance`، `tenant_id` |
| `Expense` / `ExpenseCategory` | `amount`، `amount_aed` |
| `Cheque` | `cheque_number`، `status`، `amount` |
| `Employee` / `PayrollTransaction` | `net_salary`، `status` |
| `Project` / `Task` | `status`، `start_date`، `end_date` |
| `Ticket` / `TicketComment` | `status`، `priority_id` |
| `CRMLead` / `CRMStage` | `stage_id`، `probability` |
| `PosSession` / `PosShift` / `PosCart` | `branch_id`، `user_id`، `status` |
| `SyncBatch` | `batch_type`، `status`، `record_count` |
| `APIKey` | `key`، `secret`، `tenant_id` |
| `CardVault` / `PaymentVault` | `card_hash`، `provider` |
| `EmailCampaign` / `EmailTemplate` | `subject`، `sent_at` |
| `ShopCustomerAccount` / `ShopAbandonedCart` | `email`، `cart_data` |

## الجزء 3: الوحدات النظامية

### المستأجر والمستخدم
- النماذج: `Tenant`، `User`، `Role`، `Permission`، `Branch`، `LoginHistory`
- الخدمات: `tenant_service.py`، `user_service.py`، `role_service.py`، `saas_provisioning_service.py`
- المسارات: `routes/auth.py`، `routes/users.py`، `routes/branches.py`، `routes/owner/tenants.py`، `routes/owner/users.py`

### المحاسبة العامة (GL)
- النماذج: `GLAccount`، `GLJournalEntry`، `GLJournalLine`، `GLPeriod`، `GLAccountMapping`، `CostCenter`، `Budget` / `BudgetLine`
- الخدمات: `gl_service.py`، `gl_posting.py`، `gl_tree_builder.py`، `gl_account_resolver.py`، `gl_mapping_validation.py`، `gl_accounting_setup.py`، `gl_helpers.py`، `gl_provisioning_service.py`، `gl_auto_service.py`
- المسارات: `routes/ledger.py`، `routes/admin_ledger.py`، `routes/advanced_ledger.py`

### المدفوعات والشيكات والتسوية البنكية
- النماذج: `Payment`، `Receipt`، `Cheque`، `BankReconciliation`، `BankReconciliationItem`، `BankStatementLine`، `CardVault`، `CardPayment`، `PaymentVault`، `PaymentTransaction`، `PaymentLog`
- الخدمات: `payment_service.py`، `cheque_service.py`، `cheque_accounting_integration.py`، `bank_reconciliation_service.py`، `bank_import_service.py`، `nowpayments_service.py`
- المسارات: `routes/payments.py`، `routes/cheques.py`، `routes/payment_vault.py`

### المبيعات والمشتريات
- النماذج: `Sale` / `SaleLine`، `Purchase` / `PurchaseLine`، `PurchaseReturn` / `PurchaseReturnLine`، `ProductReturn` / `ProductReturnLine`، `SalesRepCommission`
- الخدمات: `sale_service.py`، `purchase_service.py`، `return_service.py`، `commission_gl_service.py`
- المسارات: `routes/sales.py`، `routes/purchases.py`، `routes/returns.py`

### المخزون
- النماذج: `Product`، `ProductCategory`، `ProductPartner`، `Warehouse`، `ProductWarehouseStock`، `ProductWarehouseCost`، `ProductCostHistory`، `ProductPriceTier`، `ProductSerial`، `ProductImage`، `Shipment`
- الخدمات: `stock_service.py`، `serial_tracking_service.py`، `inventory_reconciliation_service.py`، `label_print_service.py`، `product_image_service.py`، `shipment_service.py`
- المسارات: `routes/products.py`، `routes/warehouse.py`، `routes/unified_inventory.py`

### العملات المتعددة
- النماذج: `Currency`، `ExchangeRate`، `ExchangeRateRecord`
- الخدمات: `exchange_rate_service.py`، `fx_revaluation_service.py`، `currency_service.py`
- الأدوات: `utils/currency_utils.py` — `convert_and_quantize_aed()`، `_AED_QUANTUM = Decimal("0.001")`

### نقاط البيع (POS)
- النماذج: `PosSession`، `PosShift`، `PosCart`، `PosFloor` / `PosTable` / `PosTableOrder`، `PosKdsOrder`، `PosOrderType`، `PosOverrideToken`، `PosCashMovement`
- الخدمات: `pos_cart_service.py`، `pos_cash_service.py`، `pos_override_service.py`، `pos_rma_service.py`، `promotion_service.py`، `pricing_service.py`
- المسارات: `routes/pos.py`

### مزامنة المخزون الخارجي
- النماذج: `SyncBatch`، `APIKey`
- الخدمات: `stock_sync_service.py`
- المسارات: `routes/stock_sync.py` — `POST /api/v2/stock/sync`، `GET /api/v2/stock/sync/status/<batch_id>`
- الديكور: `@api_key_required` في `utils/decorators.py`

### العملاء والموردين وCRM
- النماذج: `Customer`، `Supplier`، `CRMStage`، `CRMTeam` / `CRMTeamMember`، `CRMLead`، `CRMActivity`
- الخدمات: `crm_lead_service.py`، `partner_service.py`
- المسارات: `routes/customers.py`، `routes/suppliers.py`، `routes/crm.py`، `routes/partners.py`

### الموارد البشرية والرواتب
- النماذج: `Department`، `JobPosition`، `HRContract`، `Attendance`، `LeaveType` / `LeaveRequest`، `Employee`، `PayrollTransaction`، `SalaryAdvance`، `PayrollSettings`، `EmployeeLeave`
- الخدمات: `hr_service.py`، `payroll_service.py`
- المسارات: `routes/hr.py`، `routes/payroll.py`

### المشاريع
- النماذج: `Project`، `TaskStage`، `Task`، `Timesheet`، `ProjectMember`
- الخدمات: `project_service.py`
- المسارات: `routes/projects.py`

### التذاكر
- النماذج: `TicketCategory`، `TicketPriority`، `Ticket`، `TicketComment`
- الخدمات: `ticket_service.py`
- المسارات: `routes/tickets.py`

### المصروفات
- النماذج: `ExpenseCategory`، `Expense`، `AdvancedExpense`
- المسارات: `routes/expenses.py`

### المتجر الإلكتروني
- النماذج: `TenantStore`، `ShopCustomerAccount`، `ShopAbandonedCart`، `ShopWishlist`، `ShopReview`، `ShopSavedPayment`، `ShopProductVariant`، `ShopStockAlert`، `ShopNewsletter`، `ShopLoyalty` / `ShopLoyaltyTransaction`، `StoreCoupon`، `StorePaymentMethod`
- الخدمات: `store_service.py`، `store_order_service.py`، `store_checkout_service.py`، `store_coupon_service.py`، `store_payment_method_service.py`، `store_online_payment_service.py`، `store_analytics_service.py`، `store_notification_service.py`، `shop_customer_auth_service.py`
- المسارات: `routes/shop.py`، `routes/store.py`

### التسويق بالبريد
- النماذج: `EmailList`، `EmailSubscriber`، `EmailTemplate`، `EmailCampaign`، `CampaignLog`
- الخدمات: `email_marketing_service.py`، `campaign_service.py`
- المسارات: `routes/email_marketing.py`

### الأصول الثابتة
- النماذج: `FixedAsset`، `DepreciationSchedule`
- الخدمات: `depreciation_service.py`

### الذكاء الاصطناعي
- النماذج: `AiMemory`، `AiInteraction`، `AiExpertise`
- الحزمة: `ai_knowledge/` — `action_dispatcher.py`، `agents/intelligent_assistant.py`، `agents/master_brain.py`، `core/reasoning_engine.py`، `neural/neural_engine.py`
- الخدمات: `ai_service.py`، `ai_executor.py`
- المسارات: `routes/ai_routes/actions.py`، `routes/ai_routes/chat.py`، `routes/ai_routes/assistant.py`، `routes/ai_routes/analytics.py`، `routes/ai_routes/knowledge.py`، `routes/ai_routes/system.py`

### التقارير والتحليلات
- الخدمات: `analytics_service.py`، `advanced_analytics.py`، `financial_service.py`، `cash_flow_service.py`، `aging_analysis_service.py`، `treasury_service.py`، `monitoring_service.py`، `export_service.py`
- المسارات: `routes/reports.py`، `routes/owner/monitoring.py`

### الأمان والمراقبة
- النماذج: `AuditLog`، `SecurityAlert`، `ErrorAuditLog`، `ArchivedRecord`، `DocumentSnapshot`، `DocumentVerification`
- الخدمات: `audit_service.py`، `error_audit_service.py`، `error_log_service.py`، `logging_core.py`
- المسارات: `routes/owner/monitoring.py`

### التكاملات
| التكامل | الملفات |
|---------|---------|
| Stripe | `routes/billing_webhooks.py` |
| NOWPayments | `services/nowpayments_service.py` |
| WhatsApp | `services/whatsapp_service.py` |
| Webhooks | `services/webhook_service.py` |
| GraphQL | `routes/graphql.py`، `services/graphql_service.py` |
| WebSocket | `routes/websocket.py`، `services/websocket_service.py` |
| POS خارجي | `routes/stock_sync.py`، `services/stock_sync_service.py` |

## الجزء 4: الأمان وعزل المستأجرين

### مبدأ العزل
كل مستأجر يعزل بياناته عبر `tenant_id` في كل جدول تقريباً.

### الأدوات
- `tenant_query(Model)` — استعلام مُصفّى تلقائيًا
- `tenant_get_or_404(Model, id)` — بحث + تحقق
- `apply_tenant_scope(query)` — إلحاق شرط
- `get_active_tenant_id()` — `tenant_id` النشط من `g.active_tenant_id`
- `register_tenant_orm_scoping(app)` — مستمع `before_query` يلحق `tenant_id` تلقائيًا

### الاستيثاق
- `@login_required` — جلسة مستخدم
- `@permission_required('code')` — صلاحية دقيقة
- `@owner_required` — لوحة المالك
- `@admin_required` — إدارة
- `@api_key_required` — طلبات خارجية (يضبط `g.active_tenant_id`)

### التحقق من المدخلات
- `request.get_json(silent=True)` — إجباري
- `Decimal(str(data.get('field') or '0'))` — حماية Decimal
- `validate_positive_amount`، `validate_required_string`

### أمان قاعدة البيانات
- `atomic_transaction` — كل كتابة متعددة النماذج
- `db.session.commit()` — فقط في `utils/db_safety.py` و CLI
- `db.session.rollback()` — فقط في `utils/db_safety.py`
- `db.session.flush()` — الوحيد المسموح به في `services/`
- `CardVault` — تخزين `card_hash` + `last_four` فقط

## الجزء 5: قواعد المحاسبة والمخزون

### المحاسبة العامة
- `GLAccount` — شجرة الحسابات (code، name، type، parent_id)
- `GLJournalEntry` + `GLJournalLine` — debit == credit
- `GLPostingService.post_or_fail()` — الترحيل
- `GLAccountingSetup` — إعداد GL افتراضي للمستأجر الجديد

### المخزون
- `Warehouse` — مستودع رئيسي/فرعي/نقطة بيع
- `ProductWarehouseStock` — الكمية
- `ProductWarehouseCost` — التكلفة (cost_method، average_cost)
- WAC / MWAC / Landed Cost — طرق التكلفة
- `StockService.create_movement()` — حركة المخزون
- `calculate_sale_cogs_and_deduct()` — COGS عند البيع
- `_update_wac_on_receipt()` — تحديث المتوسط عند الشراء
- `ProductSerial` — تتبع تسلسلي
- `InventoryReconciliationService` — تسوية مخزونية

### العملات المتعددة
- التكميم: `Decimal("0.001")` + `ROUND_HALF_UP`
- `convert_and_quantize_aed()` — التحويل والتكميم
- `ExchangeRateService` — يُرجع `rate` كـ string
- `fx_revaluation_service.py` — إعادة تقييم شهري للمراكز المفتوحة

### المدفوعات
- `Customer.balance` — مستحقات العملاء
- `Supplier.balance` — مستحقات الموردين
- `Payment` / `Receipt` — المدفوعات والسندات
- الشيكات: receive → deposit → clear / bounce / cancel (مع قيود GL تلقائية)
- `PaymentVault` / `CardVault` — خزينة آمنة

### الرواتب
- `PayrollService.process_payroll()` — صافي الراتب، الضريبة، التأمينات
- `post_payroll_accruals()` — قيود الاستحقاقات
- `PayrollSettings` — أيام العمل، معدل الovertime

### الإهلاك
- `DepreciationService` — straight-line، declining balance
- `DepreciationSchedule` — جدول لكل أصل
- `FixedAsset.dispose()` — قيد بيع/تكهين

### محظور التعديل
- فلاتر `tenant_id`
- حمايات `owner-only`
- حدود `payment vault`
- منطق `customer/supplier balance`
- ترحيل GL debit/credit
- حركة المخزون وتكلفة المستودع
- ملكية `public donation/package payment`

## الجزء 6: دليل التشغيل

### الإعداد الأولي
```bash
flask db upgrade          # تهيئة قاعدة البيانات
flask seed-demo           # بيانات تجريبية
```

### التشغيل اليومي
```bash
python app.py             # خادم
# أو
flask run

# Celery
celery -A app.celery worker --loglevel=info
celery -A app.celery beat --loglevel=info
```

### CLI Commands
| الأمر | الوظيفة |
|-------|---------|
| `flask build-assets` | بناء الأصول الثابتة |
| `flask reconcile-stock` | تسوية المخزون |
| `flask backup` | نسخ احتياطي |
| `flask reset-platform-db` | إعادة تعيين قاعدة المنصة |
| `flask seed-demo` | زرع بيانات تجريبية |
| `flask sanitize-legacy-industries` | تنظيف الصناعات |

### Alembic Migrations
| الملف | الموضوع |
|-------|---------|
| `squash_001_baseline` | Baseline شامل |
| `e75de4aeafea_add_subscription_plan_duration` | مدة الاشتراك |
| `d4a2b8c91e07_add_pos_phase4_omnichannel` | POS Phase 4 |
| `c9f1e07b3a24_add_pos_phase3_security` | أمان POS Phase 3 |
| `b4e8d3f02a16_add_pos_phase2_parked_carts` | السلات المؤجلة |

### الصيانة
```bash
flask maintenance rebuild-gl-tree
flask maintenance fix-cost-centers
flask maintenance cleanup-test-dbs
flask database-optimize
```

### النسخ الاحتياطي
- `flask backup` — يدوي
- Celery `auto_backup_database` — تلقائي
- استعادة نطاقية (tenant-scoped restore) عبر `services/backup_scoped_restore.py`

### المراقبة
- `routes/owner/monitoring.py` — `/system-health`، `/security-alerts`، `/login-history`
- `services/health_service.py` — فحص DB، Redis، Celery

### استكشاف الأخطاء
```bash
pytest tests/unit -x --tb=short -q
python scripts/ops/enforce_grimoire.py
ruff check .
ruff format .
mypy services/ routes/ utils/ models/
```

### التكاملات الخارجية
| التكامل | Endpoint |
|---------|----------|
| Stripe | `/stripe` |
| NOWPayments | `services/nowpayments_service.py` |
| WhatsApp | `services/whatsapp_service.py` |
| POS خارجي | `POST /api/v2/stock/sync` |

## الجزء 7: الهوية والتوطين

### الاسم
AZADEXA ERP

### المناطق المدعومة
| المنطقة | الملف | الميزات |
|---------|-------|---------|
| الإمارات | `utils/localization/uae.py` | VAT |
| السعودية | `utils/localization/ksa.py` | Zakat، VAT |
| فلسطين | `utils/localization/palestine.py` | ضريبة محلية |
| عام | `utils/localization/engine.py` | الإطار العام |

### اللغة
- الواجهة: عربي/إنجليزي
- التقارير: عربي
- المستندات المحاسبية: عربي

### الصناعة المستهدفة
- التجارة والتجزئة
- الخدمات
- التصنيع
- المقاولات
- التبرعات

## الجزء 8: ملخص الأرقام

| البعد | العدد |
|-------|-------|
| نماذج ORM | 96+ |
| ملفات خدمات | 110+ |
| ملفات مسارات | 55+ |
| أدوات مساعدة | 80+ |
| اختبارات الوحدة | ~10,000 |
| اختبارات التكامل | 28 |
| Migrations | 7 |

## الجزء 9: التدفقات الرئيسية

### تدفق البيع
```
Client → routes/sales.py → SaleService.create_sale()
   → stock_service.calculate_sale_cogs_and_deduct()
   → gl_posting.post_or_fail()
   → db.session.flush() (داخل atomic_transaction)
```

### تدفق POS Checkout
```
Client → routes/pos.py → PromotionService.apply_promotions()
   → PosCartService
   → SaleService.create_sale()
   → StockService (deduct)
   → PaymentService.create_payment_for_sale()
   → GL posting
```

### تدفق مزامنة المخزون الخارجي
```
External POS → POST /api/v2/stock/sync
   → @api_key_required (sets g.active_tenant_id)
   → StockSyncService.process_sync_payload()
   → SyncBatch (idempotency)
   → StockService.create_movement()
   → broadcast_stock_alert()
```

### تدفق العملات المتعددة
```
Transaction → ExchangeRateService.resolve_exchange_rate_for_transaction()
   → convert_and_quantize_aed() (Decimal("0.001")، ROUND_HALF_UP)
   → FX revaluation (month-end)
```
