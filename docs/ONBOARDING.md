# Onboarding Guide | دليل الانضمام

## 1. Pre-Arrival | قبل الوصول

| Task (EN) | المهمة (AR) | Owner | المسؤول | Timing | التوقيت |
|-----------|-------------|-------|---------|--------|---------|
| Issue GitHub access | منح وصول GitHub | CTO | CTO | Before day 1 | قبل اليوم الأول |
| Issue Slack invite | إرسال دعوة Slack | CTO | CTO | Before day 1 | قبل اليوم الأول |
| Prepare workstation | تجهيز محطة العمل | HR / CTO | الموارد البشرية / CTO | Before day 1 | قبل اليوم الأول |
| Send welcome email with handbook link | إرسال بريد ترحيبي مع رابط الدليل | HR | الموارد البشرية | Before day 1 | قبل اليوم الأول |
| Assign buddy (senior engineer) | تعيين رفيق (مهندس أول) | CTO | CTO | Before day 1 | قبل اليوم الأول |

## 2. Day 1 — Orientation | اليوم الأول — التوجيه

| Time (EN) | الوقت (AR) | Activity | النشاط | Owner | المسؤول |
|-----------|-----------|----------|--------|-------|---------|
| 09:00 | 09:00 | Welcome, office tour, introductions | ترحيب، جولة في المكتب، مقدمات | Buddy | الرفيق |
| 10:00 | 10:00 | Handbook review + Q&A | مراجعة الدليل + أسئلة وأجوبة | HR | الموارد البشرية |
| 11:00 | 11:00 | Account setup: GitHub, Slack, email, VPN | إعداد الحساب: GitHub، Slack، البريد، VPN | DevOps | DevOps |
| 12:00 | 12:00 | Lunch with team | الغداء مع الفريق | — | — |
| 13:00 | 13:00 | GRIMOIRE deep dive (engineering standards) | الغوص العميق في GRIMOIRE (معايير الهندسة) | CTO | CTO |
| 14:00 | 14:00 | Security policy + tenant isolation rules | سياسة الأمان + قواعد عزل المستأجرين | Security Officer | مسؤول الأمان |
| 15:00 | 15:00 | Environment setup: clone repo, install dependencies, run tests | إعداد البيئة: استنساخ repo، تثبيت الاعتماديات، تشغيل الاختبارات | Buddy | الرفيق |
| 16:00 | 16:00 | First commit: fix a typo or documentation issue | أول commit: إصلاح خطأ مطبعي أو مشكلة توثيق | New hire | الموظف الجديد |

## 3. Week 1 — Environment & Codebase | الأسبوع الأول — البيئة وقاعدة الكود

| Day (EN) | اليوم (AR) | Task | المهمة | Goal | الهدف |
|----------|-----------|------|--------|------|-------|
| 1 | 1 | GRIMOIRE + Security + First commit | GRIMOIRE + الأمان + أول commit | Understand non-negotiables | فهم غير القابلة للتفاوض |
| 2 | 2 | Read `docs/TECHNICAL_REFERENCE.md` and `docs/ARCHITECTURE.md` | قراءة `docs/TECHNICAL_REFERENCE.md` و `docs/ARCHITECTURE.md` | Understand system architecture | فهم بنية النظام |
| 3 | 3 | Trace a sale from `routes/sales.py` → `services/sale_service.py` → `models/sale.py` | تتبع مبيعة من `routes/sales.py` → `services/sale_service.py` → `models/sale.py` | Understand request flow | فهم تدفق الطلب |
| 4 | 4 | Run full test suite: `pytest tests/unit -q` | تشغيل مجموعة الاختبارات الكاملة | Verify environment | التحقق من البيئة |
| 5 | 5 | Review open PRs and ask questions | مراجعة PRs المفتوحة وطرح الأسئلة | Learn review culture | تعلم ثقافة المراجعة |

## 4. Week 2 — First Feature | الأسبوع الثاني — الميزة الأولى

| Day (EN) | اليوم (AR) | Task | المهمة |
|----------|-----------|------|--------|
| 1 | 1 | Pick a "good first issue" from backlog | اختر "good first issue" من المخزون |
| 2 | 2 | Write failing test first (TDD) | اكتب اختبار فاشل أولاً (TDD) |
| 3 | 3 | Implement feature in `services/` and `routes/` | نفذ الميزة في `services/` و `routes/` |
| 4 | 4 | Run tests, fix lint, fix type checks | شغّل الاختبارات، أصلح lint، أصلح فحوصات الأنواع |
| 5 | 5 | Submit for review; address feedback | أرسل للمراجعة؛ عالج الملاحظات |

## 5. Month 1 — Independence | الشهر الأول — الاستقلالية

| Week (EN) | الأسبوع (AR) | Milestone | المعالم |
|-----------|-------------|-----------|---------|
| 3 | 3 | Complete first feature independently (end-to-end) | أكمل الميزة الأولى بشكل مستقل (من البداية إلى النهاية) |
| 4 | 4 | Participate in on-call rotation shadowing | شارك في تظليل دورة on-call |

## 6. Tools and Access | الأدوات والوصول

| Tool (EN) | الأداة (AR) | Purpose | الغرض | URL / Command | URL / الأمر |
|-----------|-------------|---------|-------|---------------|-------------|
| GitHub | GitHub | Source control | التحكم بالمصادر | https://github.com/AbuAzad2025/Azad-UAE | https://github.com/AbuAzad2025/Azad-UAE |
| Slack | Slack | Team communication | التواصل الفريقي | #engineering, #support, #general | #engineering، #support، #general |
| CI/CD | CI/CD | GitHub Actions | GitHub Actions | `.github/workflows/ci.yml` | `.github/workflows/ci.yml` |
| Monitoring | المراقبة | Application health | صحة التطبيق | `routes/owner/monitoring.py` | `routes/owner/monitoring.py` |
| Error tracking | تتبع الأخطاء | Sentry (roadmap) | Sentry (خارطة الطريق) | — | — |

## 7. Buddy System | نظام الرفيق

| Buddy Responsibility (EN) | مسؤولية الرفيق (AR) | Frequency | التكرار |
|---------------------------|---------------------|-----------|---------|
| Daily check-in | التحقق اليومي | Every day for week 1 | كل يوم للأسبوع الأول |
| Weekly 1:1 | 1:1 أسبوعي | Weeks 2–4 | الأسابيع 2–4 |
| Code review pairing | إقران مراجعة الكود | First 2 PRs | أول PRين |
| Career path discussion | مناقشة مسار المسار | End of month 1 | نهاية الشهر الأول |

## 8. Checklist — First 30 Days | قائمة التحقق — أول 30 يوماً

- [ ] Read `docs/GRIMOIRE.md` and sign acknowledgment | قراءة `docs/GRIMOIRE.md` وتوقيع الإقرار
- [ ] Read `docs/POLICY_SECURITY.md` and `docs/POLICY_DATA_PROTECTION.md` | قراءة `docs/POLICY_SECURITY.md` و `docs/POLICY_DATA_PROTECTION.md`
- [ ] Set up local environment and run tests | إعداد البيئة المحلية وتشغيل الاختبارات
- [ ] Complete security training (phishing, password manager) | إتمام التدريب الأمني (التصيد، مدير كلمات المرور)
- [ ] Attend product demo (walkthrough of all modules) | حضور عرض المنتج (جولة في جميع الوحدات)
- [ ] Complete first end-to-end feature | إتمام الميزة الأولى من البداية إلى النهاية
- [ ] Shadow support ticket resolution (2 tickets) | تظليل حل تذكرة دعم (2 تذاكر)
- [ ] Attend team retrospective | حضور استرجاع الفريق
- [ ] Receive first performance feedback | استلام أول ردود فعل على الأداء

## 9. Contact | التواصل

AZAD Intelligent Systems | شركة أزاد للأنظمة الذكية
Email: rafideen.ahmadghannam@gmail.com
