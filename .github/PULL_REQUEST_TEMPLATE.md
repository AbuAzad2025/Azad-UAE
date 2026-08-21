<!-- عربي | English below -->

## نوع التغيير / Change Type
- [ ] 🐞 إصلاح خطأ / Bug fix
- [ ] ✨ ميزة جديدة / New feature
- [ ] ♻️ إعادة هيكلة / Refactor
- [ ] ⚡ أداء / Performance
- [ ] 🔒 أمان / Security
- [ ] 📝 وثائق / Docs
- [ ] 🧪 اختبارات / Tests

## تصنيف نطاق التغيير / Change Scope (إلزامي — AGENTS.md)
- [ ] tenant-scoped
- [ ] branch-scoped
- [ ] tenant-store-scoped
- [ ] platform-owner-scoped
- [ ] public

## الوصف / Description
<!-- ماذا ولماذا — What and why -->

## الأنظمة المحمية / Protected Systems Touched?
<!-- علّم أي نظام محمي تم تعديله / Check any protected system modified -->
- [ ] فلاتر المستأجرين وحواجز المالك / Tenant filters & owner guards
- [ ] حدود خزنة الدفع / Payment vault boundaries
- [ ] منطق أرصدة العملاء/الموردين / Customer/supplier balances
- [ ] ترحيل GL مدين/دائن / GL debit-credit posting
- [ ] حركة المخزون وتكلفة المستودع / Stock movements & warehouse cost
- [ ] ملكية تبرعات/باقات الدفع العامة / Public payment ownership
- [ ] لا شيء / None

## الاختبارات / Testing
- [ ] أضفت/حدّثت اختبارات / Tests added or updated
- [ ] `pytest` يمر كاملاً / pytest passes locally
- [ ] `npx vitest run` يمر (لو تغير frontend) / vitest passes if frontend touched

## قائمة الفحص / Checklist
- [ ] كل كتابة DB داخل `atomic_transaction` / All DB writes use atomic_transaction
- [ ] قراءة/كتابة عبر `tenant_query()` / Reads-writes use tenant scoping
- [ ] لا منطق أعمال في routes / No business logic in routes
- [ ] `request.get_json(silent=True)` + حماية Decimal / Validation conventions followed

---
## (English) Summary
<!-- Brief English summary for reviewers -->
