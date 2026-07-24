# الوحدات النظامية — AZADEXA ERP System Modules

> مستند حقيقي مبني على الكود الفعلي. آخر تحديث: يوليو 2026.

---

## 1. نظرة عامة

النظام يتكون من 96+ نموذج (Model)، 110+ خدمة (Service)، و55+ ملف مسارات (Route). هذا المستند يصنّفها حسب الوحدات الوظيفية.

---

## 2. الوحدة الأساسية — المستأجر والمستخدم

### النماذج
- `Tenant` — المستأجر (slug, name, business_type, industry)
- `User` — المستخدم (username, tenant_id, branch_id, role_id, is_owner)
- `Role` — الدور
- `Permission` — الصلاحية
- `Branch` — الفرع (tenant_id, code, city, is_main)
- `LoginHistory` — سجل الدخول

### الخدمات
- `tenant_service.py` — إدارة المستأجرين
- `user_service.py` — إدارة المستخدمين
- `role_service.py` — إدارة الأدوار
- `saas_provisioning_service.py` — توفير SaaS

### المسارات
- `routes/auth.py` — تسجيل الدخول/الخروج
- `routes/users.py` — إدارة المستخدمين
- `routes/branches.py` — إدارة الفروع
- `routes/owner/tenants.py` — إدارة المستأجرين (owner)
- `routes/owner/users.py` — إدارة المستخدمين (owner)

---

## 3. الوحدة المحاسبية — دفتر الأستاذ العام (GL)

### النماذج
- `GLAccount` — حساب الأستاذ (code, name, type, parent_id)
- `GLJournalEntry` — قيد يومية
- `GLJournalLine` — سطر القيد (debit, credit, account_id)
- `GLPeriod` — الفترة المحاسبية
- `GLAccountMapping` — تعيين الحسابات
- `CostCenter` — مركز التكلفة
- `Budget` / `BudgetLine` — الميزانية

### الخدمات
- `gl_service.py` — GL core
- `gl_posting.py` — `post_or_fail()`
- `gl_tree_builder.py` — بناء شجرة الحسابات
- `gl_account_resolver.py` — فك الحسابات
- `gl_mapping_validation.py` — التحقق من التعيين
- `gl_accounting_setup.py` — إعداد المحاسبة لكل مستأجر
- `gl_helpers.py` — مساعدات GL
- `gl_provisioning_service.py` — توفير GL
- `gl_auto_service.py` — GL الآلي

### المسارات
- `routes/ledger.py` — دفتر الأستاذ
- `routes/admin_ledger.py` — إدارة الأستاذ
- `routes/advanced_ledger.py` — ميزات متقدمة

---

## 4. الوحدة المالية — المدفوعات والشيكات والتسوية البنكية

### النماذج
- `Payment` — الدفع
- `Receipt` — السند
- `Cheque` — الشيك (cheque_number, status, amount, due_date)
- `BankReconciliation` — التسوية البنكية
- `BankReconciliationItem` — عنصر التسوية
- `BankStatementLine` — سطر كشف الحساب
- `CardVault` — خزينة البطاقات
- `CardPayment` — دفع البطاقة
- `PaymentVault` — خزينة الدفع
- `PaymentTransaction` — معاملة الدفع
- `PaymentLog` — سجل الدفع

### الخدمات
- `payment_service.py` — إنشاء المدفوعات والسندات
- `cheque_service.py` — دورة حياة الشيك (receive, deposit, clear, bounce, cancel)
- `cheque_accounting_integration.py` — تكامل الشيك مع GL
- `bank_reconciliation_service.py` — التسوية البنكية
- `bank_import_service.py` — استيراد كشف الحساب
- `nowpayments_service.py` — تكامل NOWPayments (crypto)

### المسارات
- `routes/payments.py` — المدفوعات والسندات
- `routes/cheques.py` — إدارة الشيكات
- `routes/payment_vault.py` — خزينة الدفع

---

## 5. الوحدة التجارية — المبيعات والمشتريات

### النماذج
- `Sale` / `SaleLine` — المبيعات
- `Purchase` / `PurchaseLine` — المشتريات
- `PurchaseReturn` / `PurchaseReturnLine` — إرجاع المشتريات
- `ProductReturn` / `ProductReturnLine` — إرجاع المنتجات
- `SalesRepCommission` — عمولة مندوب المبيعات

### الخدمات
- `sale_service.py` — إنشاء/تنفيذ/دفع المبيعات
- `purchase_service.py` — إنشاء/إرجاع المشتريات
- `return_service.py` — إدارة الإرجاعات
- `commission_gl_service.py` — ترحيل العمولات

### المسارات
- `routes/sales.py` — المبيعات
- `routes/purchases.py` — المشتريات
- `routes/returns.py` — الإرجاعات

---

## 6. الوحدة المخزونية — المنتجات والمستودعات

### النماذج
- `Product` — المنتج (sku, category_id, regular_price, cost_price, current_stock)
- `ProductCategory` — فئة المنتج
- `ProductPartner` — شريك المنتج
- `Warehouse` — المستودع
- `ProductWarehouseStock` — مخزون المستودع
- `ProductWarehouseCost` — تكلفة المستودع (cost_method, average_cost)
- `ProductCostHistory` — تاريخ التكاليف
- `ProductPriceTier` — شرائح الأسعار
- `ProductSerial` — التتبع التسلسلي
- `ProductImage` — صورة المنتج
- `Shipment` — الشحنة

### الخدمات
- `stock_service.py` — حركة المخزون، COGS، WAC
- `serial_tracking_service.py` — التتبع التسلسلي
- `inventory_reconciliation_service.py` — التسوية المخزونية
- `label_print_service.py` — طباعة الملصقات
- `product_image_service.py` — إدارة صور المنتجات
- `shipment_service.py` — إدارة الشحن

### المسارات
- `routes/products.py` — المنتجات
- `routes/warehouse.py` — المستودعات
- `routes/unified_inventory.py` — المخزون الموحّد

---

## 7. الوحدة العملاتية — العملات المتعددة

### النماذج
- `Currency` — العملة (code, symbol)
- `ExchangeRate` — سعر الصرف
- `ExchangeRateRecord` — سجل سعر الصرف

### الخدمات
- `exchange_rate_service.py` — جلب وإدارة أسعار الصرف
- `fx_revaluation_service.py` — إعادة تقييم المراكز المفتوحة
- `currency_service.py` — خدمة العملات

### الأدوات
- `utils/currency_utils.py` — `convert_and_quantize_aed()`, `_AED_QUANTUM = Decimal("0.001")`

---

## 8. وحدة نقاط البيع (POS)

### النماذج
- `PosSession` — جلسة POS
- `PosShift` — وردية POS
- `PosCart` — السلة المؤجلة
- `PosFloor` / `PosTable` / `PosTableOrder` — طاولات المطعم
- `PosKdsOrder` — مطبخ KDS
- `PosOrderType` — نوع الطلب
- `PosOverrideToken` — رمز التجاوز
- `PosCashMovement` — حركة الخزينة

### الخدمات
- `pos_cart_service.py` — السلات المؤجلة
- `pos_cash_service.py` — حركات الخزينة (cash-in/out)
- `pos_override_service.py` — رموز تجاوز المدير
- `pos_rma_service.py` — إرجاعات POS (RMA)
- `promotion_service.py` — العروض (tiered, BOGO, bundle, combo)
- `pricing_service.py` — التسعير

### المسارات
- `routes/pos.py` — كل وظائف POS

---

## 9. وحدة مزامنة المخزون الخارجي

### النماذج
- `SyncBatch` — دفعة المزامنة
- `APIKey` — مفتاح API (key, secret, tenant_id)

### الخدمات
- `stock_sync_service.py` — معالجة حمولة المزامنة

### المسارات
- `routes/stock_sync.py` — `POST /api/v2/stock/sync`, `GET /api/v2/stock/sync/status/<batch_id>`

### الديكورات
- `@api_key_required` في `utils/decorators.py` — يضبط `g.active_tenant_id`

---

## 10. وحدة العملاء والموردين وCRM

### النماذج
- `Customer` — العميل (balance, customer_type)
- `Supplier` — المورد (balance)
- `CRMStage` — مرحلة CRM
- `CRMTeam` / `CRMTeamMember` — فريق CRM
- `CRMLead` — العميل المحتمل
- `CRMActivity` — النشاط

### الخدمات
- `crm_lead_service.py` — إدارة العملاء المحتملين
- `partner_service.py` — الشراكات والعمولات

### المسارات
- `routes/customers.py` — العملاء
- `routes/suppliers.py` — الموردين
- `routes/crm.py` — CRM
- `routes/partners.py` — الشراكات

---

## 11. وحدة الموارد البشرية والرواتب

### النماذج
- `Department` — القسم
- `JobPosition` — الوظيفة
- `HRContract` — العقد
- `Attendance` — الحضور
- `LeaveType` / `LeaveRequest` — الإجازات
- `Employee` — الموظف
- `PayrollTransaction` — معاملة الرواتب
- `SalaryAdvance` — السلفة
- `PayrollSettings` — إعدادات الرواتب
- `EmployeeLeave` — إجازة الموظف

### الخدمات
- `hr_service.py` — HR
- `payroll_service.py` — معالجة الرواتب

### المسارات
- `routes/hr.py` — الموارد البشرية
- `routes/payroll.py` — الرواتب

---

## 12. وحدة المشاريع

### النماذج
- `Project` — المشروع
- `TaskStage` — مرحلة المهمة
- `Task` — المهمة
- `Timesheet` — جدول العمل
- `ProjectMember` — عضو المشروع

### الخدمات
- `project_service.py` — إدارة المشاريع

### المسارات
- `routes/projects.py` — المشاريع

---

## 13. وحدة التذاكر وخدمة العملاء

### النماذج
- `TicketCategory` — فئة التذكرة
- `TicketPriority` — الأولوية
- `Ticket` — التذكرة
- `TicketComment` — التعليق

### الخدمات
- `ticket_service.py` — إدارة التذاكر

### المسارات
- `routes/tickets.py` — التذاكر

---

## 14. وحدة المصروفات

### النماذج
- `ExpenseCategory` — فئة المصروف
- `Expense` — المصروف (amount, amount_aed, payment_method)
- `AdvancedExpense` — مصروف متقدم

### المسارات
- `routes/expenses.py` — المصروفات

---

## 15. وحدة المتجر الإلكتروني

### النماذج
- `TenantStore` — المتجر
- `ShopCustomerAccount` — حساب العميل
- `ShopAbandonedCart` — السلة المهجورة
- `ShopWishlist` — قائمة الأمنيات
- `ShopReview` — التقييم
- `ShopSavedPayment` — طريقة الدفع المحفوظة
- `ShopProductVariant` — متغير المنتج
- `ShopStockAlert` — تنبيه المخزون
- `ShopNewsletter` — النشرة البريدية
- `ShopLoyalty` / `ShopLoyaltyTransaction` — الولاء
- `StoreCoupon` — القسيمة
- `StorePaymentMethod` — طريقة الدفع

### الخدمات
- `store_service.py` — إدارة المتجر
- `store_order_service.py` — الطلبات
- `store_checkout_service.py` — الدفع
- `store_coupon_service.py` — القسائم
- `store_payment_method_service.py` — طرق الدفع
- `store_online_payment_service.py` — الدفع الإلكتروني
- `store_analytics_service.py` — تحليلات المتجر
- `store_notification_service.py` — إشعارات المتجر
- `shop_customer_auth_service.py` — مصادقة العملاء

### المسارات
- `routes/shop.py` — واجهة المتجر
- `routes/store.py` — إعدادات المتجر

---

## 16. وحدة التسويق بالبريد

### النماذج
- `EmailList` — القائمة البريدية
- `EmailSubscriber` — المشترك
- `EmailTemplate` — القالب
- `EmailCampaign` — الحملة
- `CampaignLog` — السجل

### الخدمات
- `email_marketing_service.py` — التسويق
- `campaign_service.py` — الحملات

### المسارات
- `routes/email_marketing.py` — التسويق

---

## 17. وحدة الأصول الثابتة والإهلاك

### النماذج
- `FixedAsset` — الأصل الثابت
- `DepreciationSchedule` — جدول الإهلاك

### الخدمات
- `depreciation_service.py` — الإهلاك

---

## 18. وحدة الذكاء الاصطناعي

### النماذج
- `AiMemory` — ذاكرة AI
- `AiInteraction` — التفاعل
- `AiExpertise` — الخبرة

### الحزمة
- `ai_knowledge/` — كامل النظام العصبي
  - `action_dispatcher.py` — ActionDispatcher مع RBAC + confirmation gates
  - `agents/intelligent_assistant.py` — المساعد الذكي
  - `agents/master_brain.py` — الدماغ الرئيسي
  - `core/reasoning_engine.py` — محرك الاستدلال
  - `neural/neural_engine.py` — المحرك العصبي

### الخدمات
- `ai_service.py` — منطق AI
- `ai_executor.py` — المنفذ

### المسارات
- `routes/ai_routes/actions.py` — الإجراءات
- `routes/ai_routes/chat.py` — المحادثة
- `routes/ai_routes/assistant.py` — المساعد
- `routes/ai_routes/analytics.py` — التحليلات
- `routes/ai_routes/knowledge.py` — المعرفة
- `routes/ai_routes/system.py` — النظام

---

## 19. وحدة التقارير والتحليلات

### الخدمات
- `analytics_service.py` — التحليلات
- `advanced_analytics.py` — التحليلات المتقدمة
- `financial_service.py` — التقارير المالية
- `cash_flow_service.py` — تدفق النقد
- `aging_analysis_service.py` — تحليل العمر
- `treasury_service.py` — الخزينة
- `monitoring_service.py` — المراقبة
- `export_service.py` — التصدير (PDF, Excel)

### المسارات
- `routes/reports.py` — التقارير
- `routes/owner/monitoring.py` — المراقبة

---

## 20. وحدة الأمان والمراقبة

### النماذج
- `AuditLog` — سجل التدقيق
- `SecurityAlert` — تنبيه الأمان
- `ErrorAuditLog` — سجل الأخطاء
- `ArchivedRecord` — السجل المؤرشف
- `DocumentSnapshot` — لقطة المستند
- `DocumentVerification` — التحقق

### الخدمات
- `audit_service.py` — التدقيق
- `error_audit_service.py` — تدقيق الأخطاء
- `error_log_service.py` — سجل الأخطاء
- `logging_core.py` — التسجيل

### المسارات
- `routes/owner/monitoring.py` — المراقبة

---

## 21. وحدة التكاملات

| التكامل | الملفات |
|---------|---------|
| Stripe | `routes/billing_webhooks.py` |
| NOWPayments | `services/nowpayments_service.py` |
| WhatsApp | `services/whatsapp_service.py` |
| Webhooks عامة | `services/webhook_service.py` |
| GraphQL | `routes/graphql.py`, `services/graphql_service.py` |
| WebSocket | `routes/websocket.py`, `services/websocket_service.py` |
| POS خارجي | `routes/stock_sync.py`, `services/stock_sync_service.py` |
| مزامنة العملات | `services/celery_tasks.py` (update_exchange_rates) |

---

## 22. ملخص الأرقام

| البعد | العدد |
|-------|-------|
| نماذج ORM | 96+ |
| ملفات خدمات | 110+ |
| ملفات مسارات | 55+ |
| أدوات مساعدة | 80+ |
| اختبارات الوحدة | ~10,000 |
| اختبارات التكامل | 28 |
| migrations | 7 |

---
*هذا المستند مبني على الكود الفعلي. أي تغيير في المشروع يجب أن يعكس هنا.*
