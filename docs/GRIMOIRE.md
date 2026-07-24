# GRIMOIRE — معايير أزاد الهندسية — Azadexa Engineering Standards

## 1. Transaction Safety | سلامة المعاملات

1.1 `db.session.commit()` MUST exist only in `utils/db_safety.py`.
    يجب أن يكون `db.session.commit()` موجوداً فقط في `utils/db_safety.py`.

1.2 `db.session.rollback()` MUST exist only in `utils/db_safety.py` and in `services/gl_accounting_setup.py` for dry-run branches.
    يجب أن يكون `db.session.rollback()` موجوداً فقط في `utils/db_safety.py` وفي `services/gl_accounting_setup.py` للفروع الجافة.

1.3 `services/` MUST use `db.session.flush()` exclusively. `commit()` and `rollback()` are forbidden in this layer.
    يجب أن تستخدم `services/` حصراً `db.session.flush()`. يُمنع `commit()` و `rollback()` في هذه الطبقة.

1.4 Every write touching more than one model MUST be wrapped in `with atomic_transaction("description"):`.
    كل عملية كتابة تلامس أكثر من موديل واحد يجب أن تُغلّف بـ `with atomic_transaction("description"):`.

1.5 `db.session.add()` and `db.session.delete()` MUST occur only inside an `atomic_transaction` boundary.
    يجب أن يحدث `db.session.add()` و `db.session.delete()` فقط داخل حدود `atomic_transaction`.

## 2. Tenant Isolation | عزل المستأجرين

2.1 All database reads and writes MUST use `tenant_query()`, `apply_tenant_scope()`, or `tenant_get_or_404()`.
    يجب أن تستخدم كل عمليات القراءة والكتابة في قاعدة البيانات `tenant_query()` أو `apply_tenant_scope()` أو `tenant_get_or_404()`.

2.2 Single-record lookups MUST use `tenant_get_or_404(Model, id)`. This aborts with 404 on cross-tenant access.
    يجب أن تستخدم عمليات البحث عن سجل واحد `tenant_get_or_404(Model, id)`. هذا يُجهض بـ 404 عند الوصول عبر المستأجرين.

2.3 Multi-record queries MUST use `tenant_query(Model)`.
    يجب أن تستخدم الاستعلامات متعددة السجلات `tenant_query(Model)`.

2.4 Raw SQL MUST append `tenant_id=<tid>` after resolving the active tenant via `get_active_tenant_id()`.
    يجب أن يلحق SQL الخام `tenant_id=<tid>` بعد حل المستأجر النشط عبر `get_active_tenant_id()`.

2.5 Cross-tenant data exposure is a P0 security defect and MUST be fixed immediately.
    الكشف عن بيانات عبر المستأجرين هو خلل أمني من الدرجة P0 ويجب إصلاحه فوراً.

2.6 Celery tasks and background jobs MUST scope per iteration. Unscoped batch queries are forbidden.
    يجب أن تُحدّد مهام Celery والوظائف الخلفية النطاق لكل تكرار. يُمنع الاستعلامات الدفعية غير المُحدّدة النطاق.

## 3. Input Validation | التحقق من المدخلات

3.1 Every `request.get_json()` call MUST pass `silent=True`.
    يجب أن تمرر كل استدعاء `request.get_json()` `silent=True`.

3.2 After `data = request.get_json(silent=True)`, the handler MUST check `if data is None:` and return 400.
    بعد `data = request.get_json(silent=True)`، يجب أن يتحقق المعالج من `if data is None:` ويرجع 400.

3.3 `Decimal()` conversions MUST guard against `None` using `Decimal(str(data.get('field') or '0'))`.
    يجب أن تحمي تحويلات `Decimal()` من `None` باستخدام `Decimal(str(data.get('field') or '0'))`.

3.4 Domain validation MUST use dedicated helpers such as `validate_positive_amount` and `validate_required_string`.
    يجب أن تستخدم التحقق المجالي مساعدات مخصصة مثل `validate_positive_amount` و `validate_required_string`.

## 4. Architecture Boundaries | حدود البنية

4.1 `routes/` — HTTP handlers only. No business logic. No direct `db.session` queries. No model creation logic.
    `routes/` — معالجات HTTP فقط. لا منطق أعمال. لا استعلامات `db.session` مباشرة. لا منطق إنشاء موديل.

4.2 `services/` — Pure business logic only. No imports from `routes/`. No HTTP concepts (`request`, `jsonify`, `flash`).
    `services/` — منطق أعمال خالص فقط. لا استيرادات من `routes/`. لا مفاهيم HTTP (`request`، `jsonify`، `flash`).

4.3 `models/` — ORM definitions and scoped query helpers only. No HTTP concepts. No business logic. No service imports.
    `models/` — تعريفات ORM ومساعدات الاستعلام المُحدّدة النطاق فقط. لا مفاهيم HTTP. لا منطق أعمال. لا استيرادات خدمات.

4.4 `utils/` — Pure stateless functions and context managers only. No imports from `routes/` or `services/` except `db_safety` and `tenanting`.
    `utils/` — دوال خالصة عديمة الحالة ومديرات السياق فقط. لا استيرادات من `routes/` أو `services/` باستثناء `db_safety` و `tenanting`.

4.5 `forms/` — WTForms definitions and validation rules only. No business logic. No database queries.
    `forms/` — تعريفات WTForms وقواعد التحقق فقط. لا منطق أعمال. لا استعلامات قاعدة بيانات.

## 5. Authentication & Authorization | الاستيثاق والتفويض

5.1 Every route requiring a logged-in user MUST carry `@login_required`.
    يجب أن تحمل كل مسار يتطلب مستخدمًا مسجل الدخول `@login_required`.

5.2 Fine-grained access control MUST use `@permission_required('code')`.
    يجب أن يستخدم التحكم الدقيق بالوصول `@permission_required('code')`.

5.3 Owner-panel routes MUST carry `@owner_required`.
    يجب أن تحمل مسارات لوحة المالك `@owner_required`.

5.4 Tenant-scoped data MUST NOT be exposed to unauthenticated or unauthorized requests.
    يجب ألا تُكشف البيانات المُحدّدة النطاق للمستأجر لطلبات غير مصرّح بها أو غير مصادّق عليها.

## 6. Error Handling | معالجة الأخطاء

6.1 Bare `except:` clauses are forbidden. Every exception handler MUST log via `logger.error(...)` or `current_app.logger.error(...)`.
    يُمنع عبارات `except:` العارية. يجب أن يسجل كل معالج استثناء عبر `logger.error(...)` أو `current_app.logger.error(...)`.

6.2 Do not wrap `atomic_transaction` in an outer `try/except` that performs rollback. `atomic_transaction` handles rollback automatically.
    لا تُغلّف `atomic_transaction` في `try/except` خارجي يُجري rollback. `atomic_transaction` تتولى rollback تلقائياً.

6.3 API error responses MUST return `jsonify({'error': 'message'}), <status>`.
    يجب أن تُرجع استجابات أخطاء API `jsonify({'error': 'message'}), <status>`.

6.4 HTML error responses MUST use `flash(...)` followed by `redirect(...)`.
    يجب أن تستخدم استجابات أخطاء HTML `flash(...)` متبوعاً بـ `redirect(...)`.

## 7. Code Quality | جودة الكود

7.1 `# type: ignore`, `# noqa`, and commented-out code are forbidden.
    يُمنع `# type: ignore` و `# noqa` والكود المُعلّق.

7.2 Duplicated helpers are forbidden. One function, one purpose, one location. If a similar helper already exists, refactor and extend it. Do not reinvent from scratch.
    يُمنع المساعدات المكررة. دالة واحدة، غرض واحد، موقع واحد. إذا وجدتَ مساعد مشابه، أعد هيكلته ووسّعه. لا تُعيد الاختراع من الصفر.

7.3 Functions exceeding 80 lines MUST be refactored by extracting helpers.
    يجب إعادة هيكلة الدوال التي تتجاوز 80 سطراً باستخراج مساعدات.

7.4 Python 3.12 idioms SHOULD be used: `str | None` instead of `Optional[str]`, `match/case` where appropriate, and `from __future__ import annotations`.
    يجب استخدام أسلوب Python 3.12: `str | None` بدلاً من `Optional[str]`، و `match/case` حيثما يكون مناسباً، و `from __future__ import annotations`.

## 8. Testing | الاختبارات

8.1 Unit tests MUST reside in `tests/unit/routes/`, `tests/unit/services/`, `tests/unit/utils/`, and `tests/unit/models/`.
    يجب أن تقيم اختبارات الوحدة في `tests/unit/routes/` و `tests/unit/services/` و `tests/unit/utils/` و `tests/unit/models/`.

8.2 Mocking MUST occur at the route boundary. Mocking inside services is forbidden.
    يجب أن يحدث الـ Mocking على حدود المسارات. يُمنع الـ Mocking داخل الخدمات.

8.3 Every route module MUST have a corresponding test file.
    يجب أن يكون لكل موديل مسارات ملف اختبار مقابل.

8.4 Integration tests MUST stay flat in `tests/integration/`.
    يجب أن تبقى اختبارات التكامل مسطحة في `tests/integration/`.

## 9. File Organization | تنظيم الملفات

9.1 The repository root MUST contain only entrypoints, configuration files, and top-level documentation.
    يجب أن يحتوي جذر المستودع فقط على نقاط دخول وملفات إعداد ومستندات على المستوى الأعلى.

9.2 Scripts MUST live in `scripts/ops/`, `scripts/lint/`, or `scripts/backup/`. No orphaned scripts in the root.
    يجب أن تتواجد السكربتات في `scripts/ops/` أو `scripts/lint/` أو `scripts/backup/`. لا سكربتات يتيمة في الجذر.

9.3 Large modules MUST split into subpackages (e.g. `routes/owner/`, `routes/ai_routes/`).
    يجب أن تُقسّم الموديلات الكبيرة إلى حزم فرعية (مثل `routes/owner/` و `routes/ai_routes/`).

9.4 Large service domains MAY use subdirectories (e.g. `services/gl/`, `services/store/`).
    يجوز لمجالات الخدمات الكبيرة استخدام أدلة فرعية (مثل `services/gl/` و `services/store/`).

## 10. Testing Integrity & Enforcement | سلامة الاختبارات والإنفاذ

10.1 `scripts/ops/enforce_grimoire.py` enforces these rules via AST static analysis. Regex-based checks are forbidden.
    يُنفّذ `scripts/ops/enforce_grimoire.py` هذه القواعد عبر تحليل AST الساكن. يُمنع الفحوصات المبنية على regex.

10.2 Database test fixtures MUST use `session.begin_nested()` (savepoints) or explicit rollback teardown. Tests MUST NOT leak committed state to other tests.
    يجب أن تستخدم تجهيزات اختبار قاعدة البيانات `session.begin_nested()` (نقاط حفظ) أو تفكيك rollback صريح. يجب ألا تتسرب الاختبارات الحالة المُلتزمة إلى اختبارات أخرى.

10.3 Test database URIs MUST resolve from `app.config['SQLALCHEMY_DATABASE_URI']`. Hardcoded database names in fixtures are forbidden.
    يجب أن تُحل URIs قاعدة بيانات الاختبار من `app.config['SQLALCHEMY_DATABASE_URI']`. يُمنع أسماء قواعد البيانات المُكتوبة بشكل ثابت في التجهيزات.

10.4 Tests MUST verify inputs and outputs at layer boundaries (route to service). Mock at the route boundary, never inside services.
    يجب أن تتحقق الاختبارات من المدخلات والمخرجات على حدود الطبقات (من المسارات إلى الخدمات). Mock على حدود المسارات، وليس داخل الخدمات أبداً.

10.5 Flaky patterns are forbidden: `time.sleep()`, unseeded `random`, order-dependent logic, and shared mutable state across tests.
    يُمنع الأنماط الهشة: `time.sleep()`، و `random` غير المُبذر، والمنطق المعتمد على الترتيب، والحالة القابلة للتغيير المشتركة عبر الاختبارات.

10.6 `tests/unit/test_grimoire_compliance.py` runs the AST checker in CI. Zero errors are required. Warnings are tracked and must trend downward.
    يُشغّل `tests/unit/test_grimoire_compliance.py` الفاحص AST في CI. يُتطلّب صفر أخطاء. يتم تتبع التحذيرات ويجب أن تتجه نحو الانخفاض.
