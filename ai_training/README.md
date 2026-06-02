# AI Training Data — تنظيم بيانات تدريب الذكاء الاصطناعي

## الهيكل التنظيمي

```
ai_training/
├── README.md                          # هذا الملف
├── seed_ai_from_training.py           # سكريبت التهيئة الرئيسي
├── config.json                        # إعدادات التدريب
├── GLOBAL/                            # بيانات عامة لجميع التينانتس
│   ├── interactions/
│   │   └── interactions_log.json      # تفاعلات المستخدمين (1000+)
│   ├── expertise/
│   │   └── system_expertise.json      # خبرات النظام المحاسبي
│   ├── memories/
│   │   └── learned_knowledge.json     # المعرفة المستفادة
│   └── documents/
│       └── user_guide_summary.json    # ملخص دليل المستخدم
│
├── <tenant_slug>/                     # بيانات خاصة بكل تينانت
│   ├── interactions/                  # تفاعلات هذا التينانت
│   ├── expertise/                     # خبرات هذا التينانت
│   ├── memories/                      # ذكريات هذا التينانت
│   └── documents/                     # مستندات هذا التينانت
│
└── (tenants: alhazem, nasrallah, dubai_electronics, abudhabi_construction, sharjah_trading)
```

## التينانتس المدعومة

| Slug | الاسم | النشاط | الحالة |
|------|-------|--------|--------|
| alhazem | كراج الحازم | garage | نشط |
| nasrallah | شركة نصر الله للتجارة | trading | نشط |
| dubai_electronics | دبي إلكترونيات | retail | نشط |
| abudhabi_construction | أبوظبي للإنشاءات | construction | نشط |
| sharjah_trading | الشارقة للتجارة | trading | نشط |

## أنواع البيانات

| النوع | الوصف | الموقع |
|-------|-------|--------|
| **interactions** | سجل المحادثات Q&A | `*/interactions/*.json` |
| **expertise** | مجالات الخبرة | `*/expertise/*.json` |
| **memories** | حقائق ومعرفة مستفادة | `*/memories/*.json` |
| **documents** | مستندات وملفات مساعدة | `*/documents/*.json` |

## الاستخدام

### تهيئة الجداول (Run once)
```bash
python ai_training/seed_ai_from_training.py
```

### إضافة تدريب جديد
1. أنشئ ملف JSON في المجلد المناسب
2. شغل سكريبت التهيئة
3. البيانات الجديدة تُضاف تلقائياً

## الأمان
- `GLOBAL/` — متاح لجميع التينانتس
- `<tenant_slug>/` — خاص بذلك التينانت فقط
- لا يتم تسريب بيانات عميل أو مبيعات

## Git
- المجلد مُتتبع في Git
- ملفات JSON فقط (لا نماذج ثقيلة)
- `.gitignore` لا يُستثني هذا المجلد
