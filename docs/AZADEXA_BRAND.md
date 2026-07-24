# هوية AZADEXA — Brand & Identity

> مستند حقيقي مبني على الكود الفعلي. آخر تحديث: يوليو 2026.

---

## 1. الاسم

**AZADEXA ERP** — نظام تخطيط موارد المؤسسات.

---

## 2. الشعار

- النظام موجّه للسوق العربي والعالمي.
- يدعم التعريب الكامل (`Babel`, `utils/localization/`).
- يدعم تعدد العملات (AED, ILS, USD, EUR, +).
- يدعم تعدد الفروع والمستودعات.

---

## 3. التوطين (Localization)

### 3.1 المناطق المدعومة

| المنطقة | الملف | الميزات |
|---------|-------|---------|
| الإمارات | `utils/localization/uae.py` | VAT, ضريبة القيمة المضافة |
| السعودية | `utils/localization/ksa.py` | Zakat, ضريبة القيمة المضافة |
| فلسطين | `utils/localization/palestine.py` | ضريبة محلية |
| عام | `utils/localization/engine.py` | الإطار العام |

### 3.2 اللغة

- الواجهة: عربي/إنجليزي (قابل للتوسع).
- التقارير: عربي.
- المستندات المحاسبية: عربي.

---

## 4. الصناعة المستهدفة

- التجارة والتجزئة (POS + e-commerce)
- الخدمات (CRM + Projects + Tickets)
- التصنيع (Inventory + BOM + Serial Tracking)
- المقاولات (Projects + Payroll)
- التبرعات (Donations + Payment Vault)

---

## 5. الميزات التنافسية

| الميزة | الوصف |
|--------|-------|
| SaaS متعدد المستأجرين | كل عميل معزول تمامًا |
| POS متعدد القنوات | فروع + متجر إلكتروني + مزامنة خارجية |
| محرك العملات المتعددة | FX settlement + revaluation + quantization |
| مساعد ذكي مُدمج | RBAC + confirmation gates + neural engine |
| محاسبة GL مزدوجة | Double-entry + dynamic mapping |
| تتبع تسلسلي | Serial tracking per unit |

---

## 6. الاتصال

- الدعم داخلي: `Ticket` + `WhatsAppService`
- الوثائق: `docs/`
- API: `routes/api_docs.py` → OpenAPI / ReDoc

---
*هذا المستند مبني على الكود الفعلي. أي تغيير في المشروع يجب أن يعكس هنا.*
