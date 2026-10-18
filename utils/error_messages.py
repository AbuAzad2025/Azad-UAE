"""
Error Messages - رسائل الأخطاء الموحدة والوضيحة
جميع الرسائل بالعربية مع hints ومساعدة

Governance (see also ``report_system_error`` at the bottom of this module):

* A SYSTEM failure - database error, timeout, unhandled exception - is logged
  with its full traceback and shown to the user only as a clean, reassuring
  sentence plus a short reference they can quote to support. The database
  message, the SQL and the Python exception never reach the page.
* A BUSINESS or VALIDATION failure is not a crash. It is guidance: what went
  wrong in business terms, and what to do about it next.
"""

import logging
import uuid

from flask import current_app, flash


class ErrorCategory:
    """How a failure is classified, which decides who sees what."""

    SYSTEM = "system"
    BUSINESS = "business"
    VALIDATION = "validation"
    SECURITY = "security"
    STATE = "state"


class ErrorMessages:
    """رسائل خطأ موحدة وواضحة"""

    @staticmethod
    def user_required_fields():
        return "اسم المستخدم وكلمة المرور مطلوبان.\nتأكد من ملء جميع الحقول المطلوبة."

    @staticmethod
    def user_exists(username):
        from datetime import datetime

        year = datetime.now().year
        return (
            f'اسم المستخدم "{username}" موجود مسبقاً.\n'
            "جرب أحد هذه البدائل:\n"
            f"   • {username}_{year}\n"
            f"   • {username}_admin\n"
            f"   • {username}123"
        )

    @staticmethod
    def weak_password(errors):
        hints = "\n   • ".join(errors)
        return (
            f"كلمة المرور لا تستوفي المتطلبات:\n   • {hints}\n\n"
            "مثال على كلمة مرور قوية: Ahmed@2024!\n"
            "استخدم مزيجاً من الحروف الكبيرة والصغيرة والأرقام والرموز"
        )

    @staticmethod
    def password_mismatch():
        return "كلمتا المرور غير متطابقتين.\nتأكد من كتابة نفس كلمة المرور في الحقلين."

    @staticmethod
    def user_update_failed(err=None):
        # ``err`` is accepted for call-site compatibility but deliberately NOT
        # rendered: it is a raw exception, and interpolating one puts SQL,
        # table names and constraint names on the page. The trace belongs in the
        # log - use report_system_error() at the call site to record it.
        return (
            "تعذّر تحديث بيانات المستخدم.\n"
            "تحقق من الحقول المعدّلة ثم أعد المحاولة. إن تكرّر الخطأ، تواصل مع الدعم واذكر رقم المرجع."
        )

    @staticmethod
    def user_delete_self():
        return "لا يمكنك حذف حسابك الخاص.\nاطلب من مستخدم آخر أن يقوم بذلك."

    @staticmethod
    def user_delete_owner():
        return "لا يمكن حذف حساب المالك.\nحساب المالك محمي بشكل دائم للأمان."

    @staticmethod
    def customer_required_fields():
        return "الاسم ورقم الهاتف مطلوبان.\nأدخل على الأقل اسم العميل ورقم هاتفه."

    @staticmethod
    def customer_phone_invalid():
        return "رقم الهاتف غير صحيح.\nأدخل رقم هاتف صالح مثل: 0501234567 أو +971501234567"

    @staticmethod
    def customer_email_invalid():
        return "البريد الإلكتروني غير صحيح.\nتأكد من وجود @ ونطاق مثل: ahmed@example.com"

    @staticmethod
    def customer_has_transactions(name):
        return (
            f'لا يمكن حذف العميل "{name}" لأن لديه معاملات مسجلة.\nسيتم إلغاء تفعيله بدلاً من حذفه للحفاظ على السجلات.'
        )

    @staticmethod
    def product_required_fields():
        return "اسم المنتج والسعر مطلوبان.\nأدخل على الأقل اسم المنتج وسعر البيع."

    @staticmethod
    def product_sku_exists(sku):
        return f'رمز المنتج (SKU) "{sku}" موجود مسبقاً.\nاستخدم رمزاً فريداً أو اترك الحقل فارغاً للتوليد التلقائي.'

    @staticmethod
    def product_negative_stock():
        return "لا يمكن أن يكون المخزون سالباً.\nتأكد من إدخال كمية صحيحة أو اضبط على صفر."

    @staticmethod
    def product_low_stock(name, current, min_required):
        return (
            f'المنتج "{name}" مخزونه منخفض.\n'
            f"المتوفر: {current} | الحد الأدنى: {min_required}\n"
            "ينصح بطلب كمية جديدة من المورد."
        )

    @staticmethod
    def product_out_of_stock(name):
        return f'المنتج "{name}" نفد من المخزون.\nلا يمكن البيع. اطلب كمية جديدة من المورد.'

    @staticmethod
    def sale_no_lines():
        return 'يجب إضافة منتج واحد على الأقل للفاتورة.\nاضغط زر "إضافة صف" واختر منتجاً.'

    @staticmethod
    def sale_no_customer():
        return "يجب اختيار عميل للفاتورة.\nاختر عميل من القائمة أو أضف عميلاً جديداً."

    @staticmethod
    def sale_insufficient_stock(product_name, available, requested):
        return (
            f'كمية غير كافية للمنتج "{product_name}".\n'
            f"المتوفر: {available} | المطلوب: {requested}\n"
            "قلل الكمية أو اطلب مخزوناً جديداً."
        )

    @staticmethod
    def sale_invalid_quantity():
        return "الكمية يجب أن تكون أكبر من صفر.\nأدخل كمية صحيحة مثل: 1, 2, 5, 10"

    @staticmethod
    def sale_invalid_price():
        return "السعر يجب أن يكون أكبر من صفر.\nأدخل سعراً صحيحاً بالعملة الأساسية."

    @staticmethod
    def payment_amount_zero():
        return "المبلغ يجب أن يكون أكبر من صفر.\nأدخل المبلغ المدفوع فعلياً."

    @staticmethod
    def payment_exceeds_due(amount, due):
        return f"المبلغ المدفوع ({amount:.2f}) أكبر من المستحق ({due:.2f}).\nالمبلغ المستحق هو {due:.2f} فقط."

    @staticmethod
    def payment_method_required():
        return "يجب اختيار طريقة الدفع.\nاختر: نقدي، بطاقة، تحويل بنكي، أو شيك."

    @staticmethod
    def cheque_number_required():
        return "رقم الشيك مطلوب عند الدفع بشيك.\nأدخل رقم الشيك وتاريخ الاستحقاق."

    @staticmethod
    def reference_required():
        return "الرقم المرجعي مطلوب للتحويل البنكي.\nأدخل رقم الحوالة أو المعاملة."

    @staticmethod
    def warehouse_not_found():
        return "المستودع غير موجود.\nتأكد من اختيار مستودع صحيح من القائمة."

    @staticmethod
    def stock_adjustment_invalid():
        return "نوع التعديل غير صحيح.\nاختر: إضافة، طرح، أو ضبط الكمية."

    @staticmethod
    def permission_denied(action):
        return f'ليس لديك صلاحية للقيام بـ "{action}".\nاتصل بالمدير لطلب الصلاحية.'

    @staticmethod
    def owner_only_message():
        return "هذه الصفحة للمالك فقط.\nفقط مالك النظام يمكنه الوصول لهذه الميزة."

    @staticmethod
    def admin_only():
        return "هذه الصفحة للمديرين فقط.\nيجب أن تكون مديراً أو أعلى للوصول."

    @staticmethod
    def file_type_not_allowed(allowed_types):
        types_str = ", ".join(allowed_types)
        return f"نوع الملف غير مسموح.\nالأنواع المسموحة: {types_str}"

    @staticmethod
    def file_too_large(max_size_mb=5):
        return f"حجم الملف كبير جداً.\nالحد الأقصى: {max_size_mb}MB\nقم بضغط الملف أو اختر ملفاً أصغر."

    @staticmethod
    def file_upload_failed(err=None):
        # See user_update_failed(): the raw exception is not rendered. An
        # upload failure is usually a size, type or permissions problem, so the
        # guidance names those rather than echoing the server's error text.
        return (
            "فشل رفع الملف.\n"
            "تحقق من نوع الملف وحجمه وصلاحيات المجلد، ثم أعد المحاولة. "
            "إن تكرّر الخطأ، تواصل مع الدعم واذكر رقم المرجع."
        )

    @staticmethod
    def database_error():
        return "خطأ في قاعدة البيانات.\nإذا استمرت المشكلة، اتصل بالدعم الفني."

    # ── Cheque lifecycle ─────────────────────────────────────────────────────
    # A cheque is a state machine: pending -> deposited -> cleared, with
    # cancelled and bounced as terminal states. Almost every user mistake here
    # is an illegal transition on a document that has already moved, so the
    # message names the current state and the transition that is allowed.

    @staticmethod
    def cheque_wrong_state(action, current_status, allowed):
        return (
            f"لا يمكن {action} الشيك في حالته الحالية ({current_status}).\n"
            f"الحالات التي تسمح بهذه العملية: {allowed}.\n"
            f'راجع حالة الشيك، أو نفّذ "{allowed}" أولاً ثم أعد المحاولة.'
        )

    @staticmethod
    def cheque_bounce_requires_deposit():
        return (
            "لا يمكن رفض شيك وارد ما زال قيد التحصيل.\n"
            "يجب إيداع الشيك في البنك أولاً، ثم يمكن رفضه عند رده من البنك.\n"
            'افتح الشيك، نفّذ "إيداع في البنك"، ثم "رفض الشيك".'
        )

    @staticmethod
    def cheque_missing_fields(fields):
        listed = "، ".join(fields)
        return f"الحقول التالية مطلوبة لإتمام العملية: {listed}.\nأدخل هذه الحقول ثم أعد المحاولة."

    @staticmethod
    def cheque_invalid_value(field, expected):
        return f'القيمة المدخلة في "{field}" غير صحيحة. المتوقع: {expected}.\nصحّح "{field}" ثم أعد المحاولة.'

    @staticmethod
    def unexpected_error(error_id=None):
        # With a reference it is actionable AND traceable: the user knows what to do
        # next and can quote a code that ties the page to the log entry.
        if error_id:
            return (
                "حدث خطأ تقني غير متوقع أثناء تنفيذ العملية.\n"
                "لم يتم إتمام العملية، ولم يتأثر أي سجل آخر. "
                "يرجى المحاولة مرة أخرى، وإن تكرّر الخطأ تواصل مع الدعم الفني واذكر رقم المرجع: "
                f"{error_id}"
            )
        return (
            "حدث خطأ تقني غير متوقع أثناء تنفيذ العملية.\n"
            "لم يتم إتمام العملية. يرجى المحاولة مرة أخرى، وإن تكرّر الخطأ تواصل مع الدعم الفني."
        )

    @staticmethod
    def create_failed(entity_type):
        entities = {
            "customer": "العميل",
            "product": "المنتج",
            "sale": "الفاتورة",
            "user": "المستخدم",
            "supplier": "المورد",
            "warehouse": "المستودع",
            "cheque": "الشيك",
            "ledger": "القيد",
        }
        entity_ar = entities.get(entity_type, entity_type)
        return f"فشل إنشاء {entity_ar}.\nتحقق من البيانات وحاول مرة أخرى."

    @staticmethod
    def update_failed(entity_type):
        entities = {
            "customer": "العميل",
            "product": "المنتج",
            "sale": "الفاتورة",
            "user": "المستخدم",
            "supplier": "المورد",
            "warehouse": "المستودع",
            "cheque": "الشيك",
            "ledger": "القيد",
        }
        entity_ar = entities.get(entity_type, entity_type)
        return f"فشل تعديل {entity_ar}.\nتحقق من البيانات وحاول مرة أخرى."

    @staticmethod
    def delete_failed(entity_type):
        entities = {
            "customer": "العميل",
            "product": "المنتج",
            "sale": "الفاتورة",
            "user": "المستخدم",
            "supplier": "المورد",
            "warehouse": "المستودع",
            "cheque": "الشيك",
            "ledger": "القيد",
        }
        entity_ar = entities.get(entity_type, entity_type)
        return f"فشل حذف {entity_ar}.\nقد يكون لديه ارتباطات في النظام."

    @staticmethod
    def action_failed(action_name):
        return f"فشل {action_name}.\nتحقق من البيانات وحاول مرة أخرى."

    @staticmethod
    def whatsapp_failed():
        return "فشل إرسال الرسالة عبر WhatsApp.\nتحقق من الاتصال وحاول مرة أخرى."

    @staticmethod
    def record_not_found(entity_type):
        entities = {
            "customer": "العميل",
            "product": "المنتج",
            "sale": "الفاتورة",
            "user": "المستخدم",
        }
        entity_ar = entities.get(entity_type, entity_type)
        return f"{entity_ar} غير موجود.\nقد يكون تم حذفه. تحقق من القائمة."

    @staticmethod
    def duplicate_entry(field, value):
        return f'القيمة "{value}" موجودة مسبقاً في حقل "{field}".\nكل قيمة يجب أن تكون فريدة. جرب قيمة مختلفة.'

    @staticmethod
    def invalid_email():
        return "البريد الإلكتروني غير صحيح.\nالصيغة الصحيحة: name@example.com"

    @staticmethod
    def invalid_phone():
        return "رقم الهاتف غير صحيح.\nأمثلة: 0501234567 أو +971501234567"

    @staticmethod
    def invalid_number(field):
        return f'القيمة في "{field}" يجب أن تكون رقماً.\nأدخل رقماً صحيحاً مثل: 100 أو 99.50'

    @staticmethod
    def invalid_date():
        return "التاريخ غير صحيح.\nالصيغة الصحيحة: YYYY-MM-DD مثل: 2025-10-28"

    @staticmethod
    def invalid_currency():
        return "العملة غير صحيحة.\nاختر من: AED, USD, EUR, SAR, KWD"

    @staticmethod
    def backup_wrong_password():
        return "كلمة المرور غير صحيحة.\nأدخل كلمة مرور المالك الصحيحة."

    @staticmethod
    def backup_corrupted():
        return "النسخة الاحتياطية تالفة أو غير صالحة.\nتأكد من الملف أو جرب نسخة احتياطية أخرى."

    @staticmethod
    def backup_not_found():
        return "النسخة الاحتياطية غير موجودة.\nقد تكون تم حذفها. تحقق من القائمة."

    @staticmethod
    def backup_failed(reason):
        return f"فشل إنشاء النسخة الاحتياطية.\nالسبب: {reason}\nتأكد من مساحة القرص وصلاحيات الكتابة."

    @staticmethod
    def rate_limit_exceeded():
        return "تم تجاوز الحد المسموح من الطلبات. حاول لاحقاً."

    @staticmethod
    def session_expired():
        return "انتهت الجلسة بسبب عدم النشاط. يرجى تسجيل الدخول مرة أخرى."

    @staticmethod
    def csrf_error():
        return "خطأ في التحقق الأمني (CSRF).\nقد تكون الجلسة انتهت. حدّث الصفحة وحاول مرة أخرى."

    @staticmethod
    def required_field(field_name):
        return f'حقل "{field_name}" مطلوب.\nلا يمكن تركه فارغاً.'

    @staticmethod
    def invalid_format(field_name, example):
        return f'صيغة "{field_name}" غير صحيحة.\nمثال: {example}'

    @staticmethod
    def success_create(entity_type):
        entities = {
            "customer": "العميل",
            "product": "المنتج",
            "sale": "الفاتورة",
            "user": "المستخدم",
            "payment": "السند",
            "expense": "المصروف",
        }
        entity_ar = entities.get(entity_type, entity_type)
        return f"تمت إضافة {entity_ar} بنجاح."

    @staticmethod
    def success_update(entity_type):
        entities = {
            "customer": "العميل",
            "product": "المنتج",
            "sale": "الفاتورة",
            "user": "المستخدم",
        }
        entity_ar = entities.get(entity_type, entity_type)
        return f"تم تحديث بيانات {entity_ar} بنجاح."

    @staticmethod
    def success_delete(entity_type):
        entities = {"customer": "العميل", "product": "المنتج", "user": "المستخدم"}
        entity_ar = entities.get(entity_type, entity_type)
        return f"تم حذف {entity_ar} بنجاح."


def error(msg):
    return f"{msg}"


def warning(msg):
    return f"{msg}"


def hint(msg):
    return f"{msg}"


def success(msg):
    return f"{msg}"


# ── System-failure reporting ──────────────────────────────────────────────────
#
# The one rule: an unexpected exception is a system failure, so it is logged in
# full and reported to the user as a calm sentence plus a reference. Call sites
# used to build that sentence by hand - uuid4().hex[:8] passed to
# unexpected_error() - which guaranteed nothing: the trace was often never
# logged, and several routes interpolated str(e) straight into the flash, which
# put "duplicate key value violates unique constraint \"uq_...\"" and similar
# straight onto the page. report_system_error() makes both halves one call.


def new_error_reference() -> str:
    """A short reference a user can read out to support."""
    return uuid.uuid4().hex[:8].upper()


def report_system_error(
    exception: BaseException,
    *,
    context: str = "",
    logger=None,
) -> str:
    """Log the technical truth, return only what is safe to show a user.

    The traceback and the exception repr go to the log. The returned string is
    the clean user-facing text: no database message, no SQL, no Python
    exception, no stack trace - just what happened and what to do next, with a
    reference that ties the page back to the log entry.

    ``context`` should name the operation ("payment archive", "delete receipt")
    so the log entry is searchable without reading the traceback.
    """
    reference = new_error_reference()
    entry = logger if logger is not None else _default_logger()
    entry.error(
        "system_error ref=%s context=%s",
        reference,
        context or "-",
        exc_info=(type(exception), exception, exception.__traceback__),
    )
    return ErrorMessages.unexpected_error(reference)


def _default_logger():
    """The app logger inside a request, the module logger outside one."""
    try:
        return current_app.logger
    except RuntimeError:
        return logging.getLogger(__name__)


def refuse(error, *, context: str = "", category: str | None = None) -> str:
    """Flash the right message for this failure, and log it the right way.

    The one call a route needs in an ``except`` block. It draws the line the
    governance layer exists to enforce:

    * BusinessRuleError is the system's deliberate answer - an invalid field, or
      a state the document may not move from. Its message is written for a human
      and is shown as-is, logged at info with its category, never dressed up as a
      crash.
    * Everything else is a system failure: full traceback to the log behind a
      reference, calm sentence to the page.

    ``category`` lets a caller mark a non-typed failure as a business one when it
    knows better - a malformed date in a form, for example, is the user's
    mistake, not ours, and showing them a reference code for it would be noise.

    Returns the flash category it used, which keeps the caller honest about what
    the user was actually told.
    """
    entry = current_app.logger if current_app else _default_logger()

    if isinstance(error, BusinessRuleError):
        entry.info(
            "refusal category=%s field=%s context=%s: %s",
            error.category,
            error.field or "-",
            context or "-",
            error.message,
        )
        flash(error.message, "warning")
        return "warning"

    if category:
        # A known non-crash failure from a route that does not raise a typed
        # error. Shown as guidance, but logged so it is still traceable.
        entry.info(
            "refusal category=%s context=%s: %s",
            category,
            context or "-",
            str(error),
        )
        flash(str(error), "warning")
        return "warning"

    flash(report_system_error(error, context=context, logger=entry), "danger")
    return "danger"


# ── Typed business errors ─────────────────────────────────────────────────────


class BusinessRuleError(ValueError):
    """A refusal that is the system's answer, not a crash.

    Services raise this instead of a bare ``ValueError`` so the route layer can
    tell the two cases apart with an ``except`` clause instead of guessing from
    the exception type. It subclasses ValueError on purpose: every existing
    ``except ValueError`` in the routes keeps working unchanged, so adopting it
    is additive rather than a rewrite.

    ``category`` records why the operation was refused, which is what decides
    the guidance shown. ``message`` is already written for a human - it is
    rendered as-is, never combined with the exception repr.
    """

    def __init__(
        self,
        message: str,
        *,
        category: str = ErrorCategory.BUSINESS,
        field: str | None = None,
        status_code: int = 400,
    ):
        super().__init__(message)
        self.message = message
        self.category = category
        self.field = field
        self.status_code = status_code
