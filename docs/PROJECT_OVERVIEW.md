# نظرة عامة على المشروع — AZADEXA ERP

> مستند حقيقي مبني على الكود الفعلي. آخر تحديث: يوليو 2026.

---

## 1. الرؤية

بناء نظام ERP عربي/عالمي يعمل كـ SaaS متعدد المستأجرين، يغطي:

- التجارة (B2B, B2C, POS)
- المحاسبة المزدوجة (Double-Entry GL)
- إدارة المخزون متعدد المستودعات
- العمليات اليومية (مبيعات، مشتريات، مصروفات، شيكات)
- الموارد البشرية والرواتب
- التحليلات والتقارير
- الذكاء الاصطناعي المُضمّن

---

## 2. الحالة الحالية

النظام يحتوي على:

- **96 ملف نموذج** (`models/*.py`) يمثل 96+ جدول في PostgreSQL
- **110+ خدمة** (`services/*.py`) تحتوي على منطق الأعمال الخالص
- **55+ ملف مسارات** (`routes/*.py`) يعالج HTTP
- **80+ أداة مساعدة** (`utils/*.py`) خالصة وعديمة الحالة
- **10,000+ اختبار** يغطي الوحدات والتكامل

---

## 3. الميزات الرئيسية المُفعّلة

| الميزة | الحالة | الدليل في الكود |
|--------|--------|-----------------|
| نقاط البيع (POS) | مُفعّل | `routes/pos.py`, `services/pos_*_service.py`, `models/pos_*.py` |
| تعدد العملات | مُفعّل | `services/exchange_rate_service.py`, `services/fx_revaluation_service.py`, `utils/currency_utils.py` |
| المساعد الذكي | مُفعّل | `ai_knowledge/`, `routes/ai_routes/`, `services/ai_service.py` |
| مزامنة POS خارجي | مُفعّل | `routes/stock_sync.py`, `services/stock_sync_service.py`, `models/sync_batch.py` |
| المحركات الترويجية | مُفعّل | `services/promotion_service.py`, `models/campaign.py` |
| خزينة الدفع | مُفعّل | `routes/payment_vault.py`, `models/payment_vault.py`, `models/card_vault.py` |
| إدارة العملاء (CRM) | مُفعّل | `routes/crm.py`, `services/crm_lead_service.py`, `models/crm.py` |
| الموارد البشرية | مُفعّل | `routes/hr.py`, `routes/payroll.py`, `services/payroll_service.py`, `models/hr.py`, `models/payroll.py` |
| المشاريع | مُفعّل | `routes/projects.py`, `services/project_service.py`, `models/projects.py` |
| التذاكر | مُفعّل | `routes/tickets.py`, `services/ticket_service.py`, `models/helpdesk.py` |
| المتجر الإلكتروني | مُفعّل | `routes/shop.py`, `routes/store.py`, `services/store_*.py`, `models/shop_*.py` |
| التسويق بالبريد | مُفعّل | `routes/email_marketing.py`, `services/email_marketing_service.py`, `models/email_marketing.py` |
| الأصول الثابتة | مُفعّل | `services/depreciation_service.py`, `models/fixed_asset.py` |
| الشيكات | مُفعّل | `routes/cheques.py`, `services/cheque_service.py`, `models/cheque.py` |
| التسوية البنكية | مُفعّل | `services/bank_reconciliation_service.py`, `models/bank_reconciliation.py` |
| Webhooks | مُفعّل | `services/webhook_service.py`, `routes/billing_webhooks.py` |
| GraphQL | مُفعّل | `routes/graphql.py`, `services/graphql_service.py` |
| WebSocket | مُفعّل | `routes/websocket.py`, `services/websocket_service.py` |
| WhatsApp | مُفعّل | `services/whatsapp_service.py` |
| Celery / Background Jobs | مُفعّل | `services/celery_tasks.py` |

---

## 4. خارطة الطريق

الأعمال المنجزة حتى الآن (يوليو 2026):

1. **محرك العملات المتعددة** — FX settlement, revaluation, quantization AED
2. **تزامن POS خارجي** — API key auth, sync batches, idempotency
3. **تقوية RBAC للمساعد الذكي** — confirmation gates, per-step permissions
4. **POS متعدد القنوات (مراحل 1-4)** — promotion, parked carts, overrides, cash, RMA, split tender
5. **نظام التسوية البنكية**
6. **نظام الإهلاك والأصول الثابتة**
7. **نظام الشراكات والعمولات**

---

## 5. الفريق والملكية

- المالك يعمل مباشرة على `main`.
- لا feature branches، لا PR ceremony.
- التزامات تتبع conventional-commit style.

---
*هذا المستند مبني على الكود الفعلي. أي تغيير في المشروع يجب أن يعكس هنا.*
