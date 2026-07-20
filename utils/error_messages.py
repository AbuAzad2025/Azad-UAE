"""
Error Messages - رسائل الأخطاء الموحدة والواضحة
جميع الرسائل بالعربية مع hints ومساعدة
"""


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
    def user_update_failed(err):
        return f"فشل تحديث بيانات المستخدم.\nالخطأ: {err}\nتحقق من البيانات المدخلة وحاول مرة أخرى."

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
    def file_upload_failed(err):
        return f"فشل رفع الملف.\nالسبب: {err}\nتأكد من الملف وحاول مرة أخرى."

    @staticmethod
    def database_error():
        return "خطأ في قاعدة البيانات.\nإذا استمرت المشكلة، اتصل بالدعم الفني."

    @staticmethod
    def unexpected_error(error_id=None):
        if error_id:
            return f"حدث خطأ غير متوقع. رقم المرجع: {error_id}"
        return "حدث خطأ غير متوقع.\nإذا استمرت المشكلة، اتصل بالدعم الفني."

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
