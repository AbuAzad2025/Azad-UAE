"""AI action processor — dispatches user intents to business logic."""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
import json
import os
import re
import logging
from flask import current_app, render_template, request, jsonify
from flask_login import current_user
from sqlalchemy import func, desc, text, inspect
from extensions import db
from models import (
    User, Customer, Product, Sale, SaleLine, Purchase, Payment, Receipt,
    StockMovement, AuditLog, ProductReturn,
    InvoiceSettings, CardVault, Branch, Warehouse, Supplier,
)
from models.tenant import Tenant
from utils.tenanting import get_active_tenant_id, assign_tenant_id
from services.logging_core import LoggingCore
from services.stock_service import StockService
from routes.ai_routes import ai_bp
from routes.ai_routes.shared import smart_listener, train_local_ai, apply_smart_listeners, create_final_options, _conversation_ctx

logger = logging.getLogger(__name__)

def _user_can_ai_execute_actions(user):
    """Allow DB-mutating AI actions only for owner or users with relevant ERP permissions."""
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_owner', False):
        return True
    mutation_perms = (
        'manage_sales', 'manage_payments', 'manage_purchases',
        'manage_expenses', 'manage_customers', 'manage_products',
        'manage_cheques', 'manage_warehouse',
    )
    return any(user.has_permission(code) for code in mutation_perms)


def _process_user_action(message, user):
    """معالجة أوامر المستخدم المباشرة - جميع عمليات النظام"""
    try:
        from models import Customer, Product, Sale, SaleLine, Supplier, Purchase, PurchaseLine, Payment, Expense, Cheque, Warehouse
        from extensions import db
        from datetime import datetime, timezone
        from decimal import Decimal
        import re
        
        msg_lower = message.lower()
        user_id = user.id
        tid = get_active_tenant_id(user)
        ctx = _conversation_ctx(user_id, tid)
        
        # ========== نظام الحوار الذكي التفاعلي ==========
        
        # إذا كان المستخدم يطلب مساعدة أو خيارات
        if any(word in msg_lower for word in ['رصيد', 'رصيد العميل', 'رصيد عميل', 'تعديل رصيد']):
            if ':' not in message:
                ctx = {'last_action': 'رصيد', 'step': 0}
                return """🤖 فهمت! تريد التعامل مع رصيد العميل. إليك الخيارات:

📋 **ما الذي تريد فعله؟**
1️⃣ **تعديل رصيد العميل**
2️⃣ **استلام دفعة من العميل**
3️⃣ **إعطاء دفعة للعميل**
4️⃣ **عرض رصيد العميل**

💡 **اكتب رقم الخيار (1، 2، 3، أو 4) وسأرشدك خطوة بخطوة!**

🤖 مثال: اكتب "1" لتعديل رصيد العميل"""
        
        # ========== معالجة خيارات "رصيد" ==========
        if msg_lower.strip() == '2' and ctx.get('last_action') == 'رصيد':
            # توجيه لخيار "استلام دفعة"
            ctx = {'last_action': 'استلام', 'step': 0}
            return """🤖 تم التحويل لخيار "استلام دفعة من العميل"

اكتب "1" للمتابعة أو "عودة" للرجوع

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        if msg_lower.strip() == '3' and ctx.get('last_action') == 'رصيد':
            # توجيه لخيار "إعطاء دفعة"
            ctx = {'last_action': 'إعطاء', 'step': 0}
            return """🤖 تم التحويل لخيار "إعطاء دفعة للعميل"

اكتب "1" للمتابعة أو "عودة" للرجوع

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        if msg_lower.strip() == '4' and ctx.get('last_action') == 'رصيد':
            # عرض رصيد العميل
            from models.customer import Customer
            customers = Customer.query.filter_by(tenant_id=tid, is_active=True).all()
            if customers:
                customers_list = "\n".join([f"• {c.name}: {c.balance} درهم" for c in customers[:10]])
                del ctx
                return f"""📊 **أرصدة العملاء:**

{customers_list}

💡 **للبحث عن عميل محدد:**
اكتب: رصيد: اسم العميل

🤖 المصدر: GROQ API + التحليل المحلي"""
            else:
                del ctx
                return """❌ **لا يوجد عملاء في النظام**

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        if msg_lower.strip() == '1' and ctx.get('last_action') == 'رصيد':
            # تعديل رصيد العميل
            ctx['step'] = 1
            ctx['option'] = '1'
            ctx['data'] = {}
            return """🤖 ممتاز! اخترت تعديل رصيد العميل. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: اسم العميل**
اكتب اسم العميل

💡 **مثال:** أحمد محمد

🤖 اكتب اسم العميل الآن..."""
        
        # ========== معالجة خطوات تعديل الرصيد ==========
        if ctx.get('last_action') == 'رصيد' and ctx.get('option') == '1':
            step = ctx.get('step', 0)
            data = ctx.get('data', {})
            
            if step == 1:
                # البحث عن العميل
                from models.customer import Customer
                customer = Customer.query.filter_by(tenant_id=tid, name=message.strip(), is_active=True).first()
                if not customer:
                    return """❌ **العميل غير موجود!**

💡 **اكتب "اعرض العملاء" لعرض القائمة أو "عودة" للرجوع**

🤖 اكتب اسم العميل الصحيح..."""
                
                data['customer_id'] = customer.id
                data['customer_name'] = customer.name
                data['current_balance'] = customer.balance
                ctx['data'] = data
                ctx['step'] = 2
                return f"""✅ **تم العثور على العميل:** {customer.name}
💰 **الرصيد الحالي:** {customer.balance} درهم

📝 **الخطوة 2: الرصيد الجديد**
اكتب الرصيد الجديد للعميل

💡 **مثال:** 1000

🤖 اكتب الرصيد الجديد الآن..."""
            
            elif step == 2:
                try:
                    new_balance = float(message.strip().replace('درهم', '').strip())
                    
                    from models.customer import Customer
                    customer = Customer.query.filter_by(id=data['customer_id'], tenant_id=tid).first()
                    customer.set_balance(new_balance)
                    db.session.commit()
                    
                    train_local_ai('update_balance', data, {'success': True, 'new_balance': new_balance})
                    
                    del ctx
                    
                    return f"""✅ **تم تعديل رصيد العميل بنجاح!**

📋 **التفاصيل:**
- العميل: {data['customer_name']}
- الرصيد السابق: {data['current_balance']} درهم
- الرصيد الجديد: {new_balance} درهم

💡 **ماذا تريد أن تفعل الآن؟**
1️⃣ تعديل رصيد عميل آخر
2️⃣ العودة للقائمة الرئيسية

🤖 اكتب رقم الخيار أو اكتب "عودة"

🤖 المصدر: GROQ API + التحليل المحلي"""
                
                except:
                    return """❌ **خطأ في إدخال الرصيد!**

💡 **يرجى إدخال رقم صحيح**

🤖 أعد إدخال الرصيد..."""
        
        if any(word in msg_lower for word in ['عميل', 'عميل جديد', 'إضافة عميل', 'إنشاء عميل']):
            if ':' not in message:
                ctx = {'last_action': 'عميل', 'step': 0}
                return """🤖 فهمت! تريد إضافة عميل جديد. إليك الخيارات:

📋 **ما الذي تريد فعله؟**
1️⃣ **إضافة عميل جديد**
2️⃣ **عرض جميع العملاء**
3️⃣ **البحث عن عميل**

💡 **اكتب رقم الخيار (1، 2، أو 3) وسأرشدك خطوة بخطوة!**

🤖 مثال: اكتب "1" لإضافة عميل جديد"""
        
        if any(word in msg_lower for word in ['منتج', 'منتج جديد', 'إضافة منتج', 'إنشاء منتج']):
            if ':' not in message:
                ctx = {'last_action': 'منتج', 'step': 0}
                return """🤖 فهمت! تريد إضافة منتج جديد. إليك الخيارات:

📋 **ما الذي تريد فعله؟**
1️⃣ **إضافة منتج جديد**
2️⃣ **عرض جميع المنتجات**
3️⃣ **البحث عن منتج**
4️⃣ **رفع منتجات من Excel**

💡 **اكتب رقم الخيار (1، 2، 3، أو 4) وسأرشدك خطوة بخطوة!**

🤖 مثال: اكتب "1" لإضافة منتج جديد"""
        
        if any(word in msg_lower for word in ['فاتورة', 'بيع', 'مبيعات', 'إنشاء فاتورة']):
            if ':' not in message:
                ctx = {'last_action': 'فاتورة', 'step': 0}
                return """🤖 فهمت! تريد إنشاء فاتورة مبيعات. إليك الخيارات:

📋 **ما الذي تريد فعله؟**
1️⃣ **إنشاء فاتورة جديدة**
2️⃣ **عرض جميع الفواتير**
3️⃣ **البحث عن فاتورة**

💡 **اكتب رقم الخيار (1، 2، أو 3) وسأرشدك خطوة بخطوة!**

🤖 مثال: اكتب "1" لإنشاء فاتورة جديدة"""
        
        if any(word in msg_lower for word in ['استلام', 'استلم', 'دفعة من']):
            if ':' not in message:
                ctx = {'last_action': 'استلام', 'step': 0}
                return """🤖 فهمت! تريد استلام دفعة من عميل. إليك الخيارات:

📋 **ما الذي تريد فعله؟**
1️⃣ **استلام دفعة من عميل**
2️⃣ **عرض جميع الدفعات**
3️⃣ **البحث عن دفعة**

💡 **اكتب رقم الخيار (1، 2، أو 3) وسأرشدك خطوة بخطوة!**

🤖 مثال: اكتب "1" لاستلام دفعة من عميل"""
        
        if any(word in msg_lower for word in ['إعطاء', 'أعطى', 'دفعة لل', 'دفعة ل']):
            if ':' not in message:
                ctx = {'last_action': 'إعطاء', 'step': 0}
                return """🤖 فهمت! تريد إعطاء دفعة للعميل. إليك الخيارات:

📋 **ما الذي تريد فعله؟**
1️⃣ **إعطاء دفعة للعميل**
2️⃣ **عرض جميع الدفعات المعطاة**
3️⃣ **البحث عن دفعة معطاة**

💡 **اكتب رقم الخيار (1، 2، أو 3) وسأرشدك خطوة بخطوة!**

🤖 مثال: اكتب "1" لإعطاء دفعة للعميل"""
        
        if any(word in msg_lower for word in ['مصروف', 'إضافة مصروف', 'إنشاء مصروف']):
            if ':' not in message:
                ctx = {'last_action': 'مصروف', 'step': 0}
                return """🤖 فهمت! تريد إضافة مصروف. إليك الخيارات:

📋 **ما الذي تريد فعله؟**
1️⃣ **إضافة مصروف جديد**
2️⃣ **عرض جميع المصروفات**
3️⃣ **البحث عن مصروف**

💡 **اكتب رقم الخيار (1، 2، أو 3) وسأرشدك خطوة بخطوة!**

🤖 مثال: اكتب "1" لإضافة مصروف جديد"""
        
        # ========== نظام الحوار للموردين ==========
        if any(word in msg_lower for word in ['مورد', 'مورد جديد', 'إضافة مورد', 'إنشاء مورد']):
            if ':' not in message:
                ctx = {'last_action': 'مورد', 'step': 0}
                return """🤖 فهمت! تريد إضافة مورد جديد. إليك الخيارات:

📋 **ما الذي تريد فعله؟**
1️⃣ **إضافة مورد جديد**
2️⃣ **عرض جميع الموردين**
3️⃣ **البحث عن مورد**

💡 **اكتب رقم الخيار (1، 2، أو 3) وسأرشدك خطوة بخطوة!**

🤖 مثال: اكتب "1" لإضافة مورد جديد"""
        
        # ========== نظام الحوار للمشتريات ==========
        if any(word in msg_lower for word in ['مشتريات', 'شراء', 'إضافة مشتريات', 'إنشاء مشتريات']):
            if ':' not in message:
                ctx = {'last_action': 'مشتريات', 'step': 0}
                return """🤖 فهمت! تريد إضافة مشتريات. إليك الخيارات:

📋 **ما الذي تريد فعله؟**
1️⃣ **إضافة مشتريات جديدة**
2️⃣ **عرض جميع المشتريات**
3️⃣ **البحث عن مشتريات**

💡 **اكتب رقم الخيار (1، 2، أو 3) وسأرشدك خطوة بخطوة!**

🤖 مثال: اكتب "1" لإضافة مشتريات جديدة"""
        
        # ========== نظام الحوار للشيكات ==========
        if any(word in msg_lower for word in ['شيك', 'شيكات', 'إضافة شيك', 'إنشاء شيك']):
            if ':' not in message:
                ctx = {'last_action': 'شيك', 'step': 0}
                return """🤖 فهمت! تريد إضافة شيك. إليك الخيارات:

📋 **ما الذي تريد فعله؟**
1️⃣ **إضافة شيك جديد**
2️⃣ **عرض جميع الشيكات**
3️⃣ **البحث عن شيك**

💡 **اكتب رقم الخيار (1، 2، أو 3) وسأرشدك خطوة بخطوة!**

🤖 مثال: اكتب "1" لإضافة شيك جديد"""
        
        # ========== نظام الحوار لدفتر الأستاذ ==========
        if any(word in msg_lower for word in ['دفتر', 'دفتر الأستاذ', 'دفتر استاذ', 'قيد']):
            if ':' not in message:
                ctx = {'last_action': 'دفتر', 'step': 0}
                return """🤖 فهمت! تريد التعامل مع دفتر الأستاذ. إليك الخيارات:

📋 **ما الذي تريد فعله؟**
1️⃣ **عرض دفتر الأستاذ**
2️⃣ **البحث في القيود**

💡 **اكتب رقم الخيار (1 أو 2) وسأرشدك خطوة بخطوة!**

🤖 مثال: اكتب "1" لعرض دفتر الأستاذ"""
        
        # ========== نظام الحوار للمستودعات ==========
        if any(word in msg_lower for word in ['مستودع', 'مستودعات', 'مخزون', 'إدارة مستودعات']):
            if ':' not in message:
                ctx = {'last_action': 'مستودع', 'step': 0}
                return """🤖 فهمت! تريد إدارة المستودعات. إليك الخيارات:

📋 **ما الذي تريد فعله؟**
1️⃣ **عرض جميع المستودعات**
2️⃣ **عرض المخزون**
3️⃣ **البحث عن مستودع**

💡 **اكتب رقم الخيار (1، 2، أو 3) وسأرشدك خطوة بخطوة!**

🤖 مثال: اكتب "1" لعرض جميع المستودعات"""
        
        # ========== نظام الحوار لإدارة المستخدمين ==========
        if any(word in msg_lower for word in ['مستخدم', 'مستخدمين', 'إضافة مستخدم', 'إنشاء مستخدم']):
            if ':' not in message:
                ctx = {'last_action': 'مستخدم', 'step': 0}
                return """🤖 فهمت! تريد إدارة المستخدمين. إليك الخيارات:

📋 **ما الذي تريد فعله؟**
1️⃣ **إضافة مستخدم جديد**
2️⃣ **عرض جميع المستخدمين**
3️⃣ **البحث عن مستخدم**

💡 **اكتب رقم الخيار (1، 2، أو 3) وسأرشدك خطوة بخطوة!**

🤖 مثال: اكتب "1" لإضافة مستخدم جديد"""
        
        # ========== نظام الحوار التفاعلي للرقم 1 (إضافة عميل جديد) ==========
        if msg_lower.strip() == '1' and ctx.get('last_action') == 'عميل':
            ctx['step'] = 1
            ctx['option'] = '1'
            ctx['data'] = {}
            return """🤖 ممتاز! اخترت إضافة عميل جديد. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: اسم العميل**
اكتب اسم العميل الكامل

💡 **مثال:** أحمد محمد علي

🤖 اكتب الاسم الآن..."""
        
        # ========== معالجة الخطوات التالية (إضافة عميل) ==========
        if ctx.get('last_action') == 'عميل' and ctx.get('option') == '1':
            step = ctx.get('step', 0)
            data = ctx.get('data', {})
            
            # التحقق من المستمع الذكي
            listener_response = smart_listener(message, ctx)
            
            if listener_response == 'back':
                # العودة للقائمة الرئيسية
                del ctx
                return """🔙 **تم العودة للقائمة الرئيسية**

💡 **يمكنك البدء من جديد:**
• اكتب "عميل" لإدارة العملاء
• اكتب "منتج" لإدارة المنتجات
• اكتب "فاتورة" لإنشاء فاتورة
• اكتب "مصروف" لإضافة مصروف

🤖 المصدر: GROQ API + التحليل المحلي"""
            
            if listener_response == 'help':
                current_step_text = ""
                if step == 1:
                    current_step_text = "اسم العميل"
                elif step == 2:
                    current_step_text = "رقم الهاتف"
                elif step == 3:
                    current_step_text = "العنوان"
                
                return f"""💡 **مساعدة - الخطوة {step}:**

📝 **المطلوب حالياً:** {current_step_text}

💡 **نصائح:**
• اكتب البيانات المطلوبة فقط
• اكتب "عودة" للعودة للقائمة الرئيسية
• اكتب "إلغاء" لإلغاء العملية

🤖 المصدر: GROQ API + التحليل المحلي"""
            
            if step == 1:
                # حفظ الاسم والانتقال للخطوة التالية
                data['name'] = message.strip()
                ctx['data'] = data
                ctx['step'] = 2
                ctx['history'] = ctx.get('history', []) + [{'step': 1, 'data': message.strip()}]
                return """✅ **تم حفظ الاسم:** {name}

📝 **الخطوة 2: رقم الهاتف**
اكتب رقم هاتف العميل

💡 **مثال:** 0561234567

💬 **اكتب "عودة" للرجوع أو "مساعدة" للمساعدة**

🤖 اكتب رقم الهاتف الآن...""".format(name=data['name'])
            
            elif step == 2:
                # حفظ الهاتف والانتقال للخطوة التالية
                data['phone'] = message.strip()
                ctx['data'] = data
                ctx['step'] = 3
                return """✅ **تم حفظ رقم الهاتف:** {phone}

📝 **الخطوة 3: العنوان**
اكتب عنوان العميل

💡 **مثال:** دبي - الخليج التجاري

🤖 اكتب العنوان الآن...""".format(phone=data['phone'])
            
            elif step == 3:
                # حفظ العنوان وإنشاء العميل
                data['address'] = message.strip()
                
                try:
                    from models.customer import Customer
                    # إنشاء العميل الجديد
                    customer = Customer(
                        name=data['name'],
                        phone=data['phone'],
                        address=data['address'],
                        balance=0
                    )
                    assign_tenant_id(customer)
                    db.session.add(customer)
                    db.session.commit()
                    
                    # تدريب الذكاء المحلي
                    train_local_ai('create_customer', data, {'success': True, 'customer_id': customer.id})
                    
                    # مسح السياق
                    del ctx
                    
                    return f"""✅ **تم إنشاء العميل بنجاح!**

📋 **التفاصيل:**
- الاسم: {data['name']}
- الهاتف: {data['phone']}
- العنوان: {data['address']}
- الرصيد: 0 درهم
- الرقم: #{customer.id}

💡 **ماذا تريد أن تفعل الآن؟**
1️⃣ إضافة عميل آخر
2️⃣ عرض جميع العملاء
3️⃣ إنشاء فاتورة لهذا العميل
4️⃣ العودة للقائمة الرئيسية

🤖 اكتب رقم الخيار أو اكتب "عودة" للقائمة الرئيسية

🤖 المصدر: GROQ API + التحليل المحلي"""
                
                except Exception as e:
                    # تدريب الذكاء المحلي من الخطأ
                    train_local_ai('create_customer', data, {'success': False, 'error': str(e)})
                    
                    # مسح السياق في حالة الخطأ
                    del ctx
                    return f"""❌ **خطأ في إنشاء العميل:**

{str(e)}

💡 **حاول مرة أخرى:** اكتب "عميل" ثم "1"

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        # ========== نظام الحوار التفاعلي للرقم 1 (إضافة منتج جديد) ==========
        if msg_lower.strip() == '1' and ctx.get('last_action') == 'منتج':
            ctx['step'] = 1
            ctx['option'] = '1'
            ctx['data'] = {}
            return """🤖 ممتاز! اخترت إضافة منتج جديد. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: اسم المنتج**
اكتب اسم المنتج الكامل

💡 **مثال:** فلتر زيت كاتربلر

🤖 اكتب اسم المنتج الآن..."""
        
        # ========== معالجة الخطوات التالية (إضافة منتج) ==========
        if ctx.get('last_action') == 'منتج' and ctx.get('option') == '1':
            step = ctx.get('step', 0)
            data = ctx.get('data', {})
            
            # التحقق من المستمع الذكي
            listener_response = smart_listener(message, ctx)
            
            if listener_response == 'back':
                del ctx
                return """🔙 **تم العودة للقائمة الرئيسية**

💡 **يمكنك البدء من جديد:**
• اكتب "منتج" لإدارة المنتجات
• اكتب "عميل" لإدارة العملاء
• اكتب "فاتورة" لإنشاء فاتورة

🤖 المصدر: GROQ API + التحليل المحلي"""
            
            if listener_response == 'help':
                steps_text = {1: "اسم المنتج", 2: "رقم القطعة", 3: "السعر", 4: "الكمية"}
                return f"""💡 **مساعدة - الخطوة {step}:**

📝 **المطلوب حالياً:** {steps_text.get(step, 'غير معروف')}

💡 **نصائح:**
• اكتب البيانات المطلوبة فقط
• اكتب "عودة" للعودة للقائمة الرئيسية

🤖 المصدر: GROQ API + التحليل المحلي"""
            
            if step == 1:
                # حفظ الاسم والانتقال للخطوة التالية
                data['name'] = message.strip()
                ctx['data'] = data
                ctx['step'] = 2
                return """✅ **تم حفظ الاسم:** {name}

📝 **الخطوة 2: رقم القطعة**
اكتب رقم القطعة (Part Number)

💡 **مثال:** 1R0716

🤖 اكتب رقم القطعة الآن...""".format(name=data['name'])
            
            elif step == 2:
                # حفظ رقم القطعة والانتقال للخطوة التالية
                data['part_number'] = message.strip()
                ctx['data'] = data
                ctx['step'] = 3
                return """✅ **تم حفظ رقم القطعة:** {part_number}

📝 **الخطوة 3: السعر**
اكتب سعر البيع (بالدرهم)

💡 **مثال:** 50

🤖 اكتب السعر الآن...""".format(part_number=data['part_number'])
            
            elif step == 3:
                # حفظ السعر والانتقال للخطوة التالية
                try:
                    data['price'] = float(message.strip().replace('درهم', '').replace('د.إ', '').strip())
                    ctx['data'] = data
                    ctx['step'] = 4
                    return """✅ **تم حفظ السعر:** {price} درهم

📝 **الخطوة 4: الكمية**
اكتب الكمية المتوفرة

💡 **مثال:** 100

🤖 اكتب الكمية الآن...""".format(price=data['price'])
                except:
                    return """❌ **خطأ في إدخال السعر!**

💡 **يرجى إدخال رقم صحيح**

🤖 أعد إدخال السعر..."""
            
            elif step == 4:
                # حفظ الكمية وإنشاء المنتج
                try:
                    data['quantity'] = float(message.strip().replace('قطعة', '').strip())
                    
                    from models.product import Product
                    
                    # إنشاء المنتج الجديد
                    product = Product(
                        name=data['name'],
                        part_number=data['part_number'],
                        regular_price=data['price'],
                        current_stock=0,
                        unit='قطعة'
                    )
                    assign_tenant_id(product, user)
                    db.session.add(product)
                    db.session.flush()
                    if data['quantity'] > 0:
                        StockService.add_opening_stock(
                            product_id=product.id,
                            quantity=data['quantity'],
                        )
                    db.session.commit()
                    
                    # تدريب الذكاء المحلي
                    train_local_ai('create_product', data, {'success': True, 'product_id': product.id})
                    
                    # مسح السياق
                    del ctx
                    
                    return f"""✅ **تم إنشاء المنتج بنجاح!**

📋 **التفاصيل:**
- الاسم: {data['name']}
- رقم القطعة: {data['part_number']}
- السعر: {data['price']} درهم
- الكمية: {data['quantity']} قطعة
- الرقم: #{product.id}

💡 **ماذا تريد أن تفعل الآن؟**
1️⃣ إضافة منتج آخر
2️⃣ عرض جميع المنتجات
3️⃣ إنشاء فاتورة بهذا المنتج
4️⃣ العودة للقائمة الرئيسية

🤖 اكتب رقم الخيار أو اكتب "عودة"

🤖 المصدر: GROQ API + التحليل المحلي"""
                
                except Exception as e:
                    # تدريب الذكاء المحلي من الخطأ
                    train_local_ai('create_product', data, {'success': False, 'error': str(e)})
                    
                    # مسح السياق في حالة الخطأ
                    del ctx
                    return f"""❌ **خطأ في إنشاء المنتج:**

{str(e)}

💡 **حاول مرة أخرى:** اكتب "منتج" ثم "1"

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        # ========== نظام الحوار التفاعلي للرقم 1 (إنشاء فاتورة جديدة) ==========
        if msg_lower.strip() == '1' and ctx.get('last_action') == 'فاتورة':
            ctx['step'] = 1
            ctx['option'] = '1'
            ctx['data'] = {}
            return """🤖 ممتاز! اخترت إنشاء فاتورة جديدة. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: اسم العميل**
اكتب اسم العميل

💡 **مثال:** أحمد محمد

🤖 اكتب اسم العميل الآن..."""
        
        # ========== معالجة الخطوات التالية (إنشاء فاتورة) ==========
        if ctx.get('last_action') == 'فاتورة' and ctx.get('option') == '1':
            step = ctx.get('step', 0)
            data = ctx.get('data', {})
            
            listener_status, listener_msg = apply_smart_listeners(message, ctx, 'فاتورة')
            if listener_status in ['back', 'help']:
                if listener_status == 'back':
                    del ctx
                return listener_msg
            
            if step == 1:
                # التحقق من طلبات خاصة
                if any(word in message.lower() for word in ['عرض', 'اعرض', 'show', 'list', 'العملاء']):
                    from models.customer import Customer
                    customers = Customer.query.filter_by(tenant_id=tid, is_active=True).limit(10).all()
                    if customers:
                        customers_list = "\n".join([f"• {c.name} ({c.phone or 'لا يوجد هاتف'})" for c in customers])
                        return f"""📋 **قائمة العملاء المتاحين:**

{customers_list}

💡 **اكتب اسم أحد العملاء أعلاه، أو:**
• اكتب "عودة" للعودة للقائمة الرئيسية
• اكتب "عميل" لإضافة عميل جديد

🤖 اكتب اسم العميل الآن..."""
                    else:
                        return """❌ **لا يوجد عملاء في النظام**

💡 **اكتب "عميل" لإضافة عميل جديد**

🤖 المصدر: GROQ API + التحليل المحلي"""
                
                # البحث عن العميل
                from models.customer import Customer
                customer = Customer.query.filter_by(tenant_id=tid, name=message.strip(), is_active=True).first()
                if not customer:
                    return """❌ **العميل غير موجود!**

💡 **ماذا تريد أن تفعل؟**
• اكتب "اعرض العملاء" لعرض قائمة العملاء
• اكتب "عميل" لإضافة عميل جديد
• اكتب "عودة" للعودة للقائمة الرئيسية

🤖 اكتب اسم العميل الصحيح أو اختر أحد الخيارات..."""
                
                data['customer_id'] = customer.id
                data['customer_name'] = customer.name
                ctx['data'] = data
                ctx['step'] = 2
                return """✅ **تم العثور على العميل:** {customer_name}

📝 **الخطوة 2: اسم المنتج**
اكتب اسم المنتج

💡 **مثال:** فلتر زيت كاتربلر
💬 **اكتب "اعرض المنتجات" لعرض القائمة**

🤖 اكتب اسم المنتج الآن...""".format(customer_name=customer.name)
            
            elif step == 2:
                # التحقق من طلبات خاصة
                if any(word in message.lower() for word in ['عرض', 'اعرض', 'show', 'list', 'المنتجات']):
                    from models.product import Product
                    products = Product.query.filter_by(tenant_id=tid, is_active=True).limit(10).all()
                    if products:
                        products_list = "\n".join([f"• {p.name} - {p.regular_price} درهم (متوفر: {p.current_stock})" for p in products])
                        return f"""📋 **قائمة المنتجات المتاحة:**

{products_list}

💡 **اكتب اسم أحد المنتجات أعلاه، أو:**
• اكتب "عودة" للعودة للقائمة الرئيسية
• اكتب "منتج" لإضافة منتج جديد

🤖 اكتب اسم المنتج الآن..."""
                    else:
                        return """❌ **لا يوجد منتجات في النظام**

💡 **اكتب "منتج" لإضافة منتج جديد**

🤖 المصدر: GROQ API + التحليل المحلي"""
                
                # البحث عن المنتج
                from models.product import Product
                product = Product.query.filter_by(tenant_id=tid, name=message.strip(), is_active=True).first()
                if not product:
                    return """❌ **المنتج غير موجود!**

💡 **ماذا تريد أن تفعل؟**
• اكتب "اعرض المنتجات" لعرض قائمة المنتجات
• اكتب "منتج" لإضافة منتج جديد
• اكتب "عودة" للعودة للقائمة الرئيسية

🤖 اكتب اسم المنتج الصحيح أو اختر أحد الخيارات..."""
                
                data['product_id'] = product.id
                data['product_name'] = product.name
                data['product_price'] = product.regular_price
                ctx['data'] = data
                ctx['step'] = 3
                return """✅ **تم العثور على المنتج:** {product_name}
💰 **السعر:** {product_price} درهم

📝 **الخطوة 3: الكمية**
اكتب الكمية المطلوبة

💡 **مثال:** 2

🤖 اكتب الكمية الآن...""".format(product_name=product.name, product_price=product.regular_price)
            
            elif step == 3:
                # حفظ الكمية وإنشاء الفاتورة
                try:
                    data['quantity'] = float(message.strip())
                    total_amount = data['product_price'] * data['quantity']
                    
                    from models.sale import Sale, SaleLine
                    from utils.helpers import generate_number
                    
                    # إنشاء الفاتورة
                    sale_number = generate_number('S', Sale, 'sale_number', branch_id=getattr(current_user, 'branch_id', None))
                    sale = Sale(
                        sale_number=sale_number,
                        customer_id=data['customer_id'],
                        seller_id=user.id,
                        total_amount=total_amount,
                        checkout_payment_method='cash',
                        amount=total_amount,
                        amount_aed=total_amount,
                        currency='AED',
                        exchange_rate=1
                    )
                    assign_tenant_id(sale)
                    db.session.add(sale)
                    db.session.flush()  # للحصول على ID
                    
                    # إضافة عنصر الفاتورة
                    sale_line = SaleLine(
                        sale_id=sale.id,
                        product_id=data['product_id'],
                        quantity=data['quantity'],
                        unit_price=data['product_price'],
                        total=total_amount
                    )
                    db.session.add(sale_line)
                    
                    # تحديث المخزون عبر StockService
                    wh = Warehouse.query.filter_by(tenant_id=tid, is_active=True).first()
                    StockService.remove_stock(
                        product_id=data['product_id'],
                        quantity=data['quantity'],
                        reference_type=GLRef.SALE,
                        reference_id=sale.id,
                        warehouse_id=wh.id if wh else None,
                    )
                    
                    db.session.commit()
                    
                    # تدريب الذكاء المحلي
                    train_local_ai('create_sale', data, {'success': True, 'sale_id': sale.id})
                    
                    # مسح السياق
                    del ctx
                    
                    final_options = create_final_options('فاتورة', data['customer_name'], sale.id)
                    
                    return f"""✅ **تم إنشاء الفاتورة بنجاح!**

📋 **التفاصيل:**
- العميل: {data['customer_name']}
- المنتج: {data['product_name']}
- الكمية: {data['quantity']}
- السعر: {data['product_price']} درهم
- المجموع: {total_amount} درهم
- رقم الفاتورة: #{sale.id}

{final_options}

🤖 اكتب رقم الخيار أو اكتب "عودة"

🤖 المصدر: GROQ API + التحليل المحلي"""
                
                except Exception as e:
                    # تدريب الذكاء المحلي من الخطأ
                    train_local_ai('create_sale', data, {'success': False, 'error': str(e)})
                    
                    # مسح السياق في حالة الخطأ
                    del ctx
                    return f"""❌ **خطأ في إنشاء الفاتورة:**

{str(e)}

💡 **حاول مرة أخرى:** اكتب "فاتورة" ثم "1"

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        # ========== نظام الحوار التفاعلي للرقم 1 (استلام دفعة) ==========
        if msg_lower.strip() == '1' and ctx.get('last_action') == 'استلام':
            ctx['step'] = 1
            ctx['option'] = '1'
            ctx['data'] = {}
            return """🤖 ممتاز! اخترت استلام دفعة من عميل. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: اسم العميل**
اكتب اسم العميل

💡 **مثال:** أحمد محمد

🤖 اكتب اسم العميل الآن..."""
        
        # ========== معالجة الخطوات التالية (استلام دفعة) ==========
        if ctx.get('last_action') == 'استلام' and ctx.get('option') == '1':
            step = ctx.get('step', 0)
            data = ctx.get('data', {})
            
            listener_status, listener_msg = apply_smart_listeners(message, ctx, 'استلام')
            if listener_status in ['back', 'help']:
                if listener_status == 'back':
                    del ctx
                return listener_msg
            
            if step == 1:
                # البحث عن العميل
                from models.customer import Customer
                customer = Customer.query.filter_by(tenant_id=tid, name=message.strip(), is_active=True).first()
                if not customer:
                    return """❌ **العميل غير موجود!**

💡 **تأكد من اسم العميل أو أضف عميل جديد أولاً**

🤖 اكتب اسم العميل الصحيح أو اكتب "عميل" لإضافة عميل جديد..."""
                
                data['customer_id'] = customer.id
                data['customer_name'] = customer.name
                data['current_balance'] = customer.balance
                ctx['data'] = data
                ctx['step'] = 2
                return """✅ **تم العثور على العميل:** {customer_name}
💰 **الرصيد الحالي:** {current_balance} درهم

📝 **الخطوة 2: مبلغ الدفعة**
اكتب مبلغ الدفعة المستلمة

💡 **مثال:** 200

🤖 اكتب مبلغ الدفعة الآن...""".format(customer_name=customer.name, current_balance=customer.balance)
            
            elif step == 2:
                # حفظ المبلغ والانتقال للخطوة التالية
                try:
                    data['amount'] = float(message.strip().replace('درهم', '').replace('د.إ', '').strip())
                    ctx['data'] = data
                    ctx['step'] = 3
                    return """✅ **تم حفظ المبلغ:** {amount} درهم

📝 **الخطوة 3: طريقة الدفع**
اكتب طريقة الدفع

💡 **مثال:** نقد، بطاقة، شيك

🤖 اكتب طريقة الدفع الآن...""".format(amount=data['amount'])
                except:
                    return """❌ **خطأ في إدخال المبلغ!**

💡 **يرجى إدخال رقم صحيح**

🤖 أعد إدخال المبلغ..."""
            
            elif step == 3:
                # حفظ طريقة الدفع وتسجيل الدفعة
                data['payment_method'] = message.strip()
                
                try:
                    from models.payment import Payment
                    from models.customer import Customer
                    
                    # تسجيل الدفعة
                    from utils.helpers import generate_number
                    payment_number = generate_number('PAY', Payment, 'payment_number', branch_id=getattr(current_user, 'branch_id', None))
                    payment = Payment(
                        payment_number=payment_number,
                        customer_id=data['customer_id'],
                        amount=data['amount'],
                        amount_aed=data['amount'],
                        currency='AED',
                        exchange_rate=1,
                        payment_date=datetime.now(timezone.utc),
                        payment_method=data['payment_method'],
                        user_id=user.id,
                        direction='incoming',
                        payment_type='customer_payment'
                    )
                    assign_tenant_id(payment)
                    db.session.add(payment)
                    
                    # تحديث رصيد العميل
                    customer = Customer.query.filter_by(id=data['customer_id'], tenant_id=tid).first()
                    customer.apply_receipt(data['amount'])
                    
                    db.session.commit()
                    
                    # تدريب الذكاء المحلي
                    train_local_ai('receive_payment', data, {'success': True, 'payment_id': payment.id})
                    
                    # مسح السياق
                    del ctx
                    
                    final_options = create_final_options('استلام', data['customer_name'], payment.id)
                    
                    return f"""✅ **تم استلام الدفعة بنجاح!**

📋 **التفاصيل:**
- العميل: {data['customer_name']}
- المبلغ المستلم: {data['amount']} درهم
- طريقة الدفع: {data['payment_method']}
- الرصيد الجديد: {customer.balance} درهم
- رقم الدفعة: #{payment.id}

{final_options}

🤖 اكتب رقم الخيار أو اكتب "عودة"

🤖 المصدر: GROQ API + التحليل المحلي"""
                
                except Exception as e:
                    # تدريب الذكاء المحلي من الخطأ
                    train_local_ai('receive_payment', data, {'success': False, 'error': str(e)})
                    
                    # مسح السياق في حالة الخطأ
                    del ctx
                    return f"""❌ **خطأ في تسجيل الدفعة:**

{str(e)}

💡 **حاول مرة أخرى:** اكتب "استلام" ثم "1"

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        # ========== نظام الحوار التفاعلي للرقم 1 (إعطاء دفعة) ==========
        if msg_lower.strip() == '1' and ctx.get('last_action') == 'إعطاء':
            ctx['step'] = 1
            ctx['option'] = '1'
            ctx['data'] = {}
            return """🤖 ممتاز! اخترت إعطاء دفعة للعميل. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: اسم العميل**
اكتب اسم العميل

💡 **مثال:** أحمد محمد

🤖 اكتب اسم العميل الآن..."""
        
        # ========== معالجة الخطوات التالية (إعطاء دفعة) ==========
        if ctx.get('last_action') == 'إعطاء' and ctx.get('option') == '1':
            step = ctx.get('step', 0)
            data = ctx.get('data', {})
            
            listener_status, listener_msg = apply_smart_listeners(message, ctx, 'إعطاء')
            if listener_status in ['back', 'help']:
                if listener_status == 'back':
                    del ctx
                return listener_msg
            
            if step == 1:
                # البحث عن العميل
                from models.customer import Customer
                customer = Customer.query.filter_by(tenant_id=tid, name=message.strip(), is_active=True).first()
                if not customer:
                    return """❌ **العميل غير موجود!**

💡 **تأكد من اسم العميل أو أضف عميل جديد أولاً**

🤖 اكتب اسم العميل الصحيح أو اكتب "عميل" لإضافة عميل جديد..."""
                
                data['customer_id'] = customer.id
                data['customer_name'] = customer.name
                data['current_balance'] = customer.balance
                ctx['data'] = data
                ctx['step'] = 2
                return """✅ **تم العثور على العميل:** {customer_name}
💰 **الرصيد الحالي:** {current_balance} درهم

📝 **الخطوة 2: مبلغ الدفعة**
اكتب مبلغ الدفعة المعطاة للعميل

💡 **مثال:** 100

🤖 اكتب مبلغ الدفعة الآن...""".format(customer_name=customer.name, current_balance=customer.balance)
            
            elif step == 2:
                # حفظ المبلغ والانتقال للخطوة التالية
                try:
                    data['amount'] = float(message.strip().replace('درهم', '').replace('د.إ', '').strip())
                    ctx['data'] = data
                    ctx['step'] = 3
                    return """✅ **تم حفظ المبلغ:** {amount} درهم

📝 **الخطوة 3: السبب**
اكتب سبب إعطاء الدفعة

💡 **مثال:** استرداد، خصم، مكافأة

🤖 اكتب السبب الآن...""".format(amount=data['amount'])
                except:
                    return """❌ **خطأ في إدخال المبلغ!**

💡 **يرجى إدخال رقم صحيح**

🤖 أعد إدخال المبلغ..."""
            
            elif step == 3:
                # حفظ السبب وتسجيل الدفعة
                data['reason'] = message.strip()
                
                try:
                    from models.payment import Payment
                    from models.customer import Customer
                    
                    # تسجيل الدفعة (سالبة لأننا نعطي للعميل)
                    from utils.helpers import generate_number
                    payment_number = generate_number('PAY', Payment, 'payment_number', branch_id=getattr(current_user, 'branch_id', None))
                    payment = Payment(
                        payment_number=payment_number,
                        customer_id=data['customer_id'],
                        amount=-data['amount'],  # سالب لأننا نعطي للعميل
                        amount_aed=-data['amount'],  # سالب لأننا نعطي للعميل
                        currency='AED',
                        exchange_rate=1,
                        payment_date=datetime.now(timezone.utc),
                        payment_method='refund',
                        user_id=user.id,
                        direction='outgoing',
                        payment_type='refund'
                    )
                    assign_tenant_id(payment)
                    db.session.add(payment)
                    
                    # تحديث رصيد العميل (زيادة)
                    customer = Customer.query.filter_by(id=data['customer_id'], tenant_id=tid).first()
                    customer.adjust_balance(data['amount'])
                    
                    db.session.commit()
                    
                    # تدريب الذكاء المحلي
                    train_local_ai('give_payment', data, {'success': True, 'payment_id': payment.id})
                    
                    # مسح السياق
                    del ctx
                    
                    final_options = create_final_options('إعطاء', data['customer_name'], payment.id)
                    
                    return f"""✅ **تم إعطاء الدفعة بنجاح!**

📋 **التفاصيل:**
- العميل: {data['customer_name']}
- المبلغ المعطى: {data['amount']} درهم
- السبب: {data['reason']}
- الرصيد الجديد: {customer.balance} درهم
- رقم الدفعة: #{payment.id}

{final_options}

🤖 اكتب رقم الخيار أو اكتب "عودة"

🤖 المصدر: GROQ API + التحليل المحلي"""
                
                except Exception as e:
                    # تدريب الذكاء المحلي من الخطأ
                    train_local_ai('give_payment', data, {'success': False, 'error': str(e)})
                    
                    # مسح السياق في حالة الخطأ
                    del ctx
                    return f"""❌ **خطأ في تسجيل الدفعة:**

{str(e)}

💡 **حاول مرة أخرى:** اكتب "إعطاء" ثم "1"

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        # ========== نظام الحوار التفاعلي للرقم 1 (إضافة مصروف) ==========
        if msg_lower.strip() == '1' and ctx.get('last_action') == 'مصروف':
            ctx['step'] = 1
            ctx['option'] = '1'
            ctx['data'] = {}
            return """🤖 ممتاز! اخترت إضافة مصروف جديد. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: وصف المصروف**
اكتب وصف المصروف

💡 **مثال:** فواتير الكهرباء

🤖 اكتب وصف المصروف الآن..."""
        
        # ========== معالجة الخطوات التالية (إضافة مصروف) ==========
        if ctx.get('last_action') == 'مصروف' and ctx.get('option') == '1':
            step = ctx.get('step', 0)
            data = ctx.get('data', {})
            
            listener_status, listener_msg = apply_smart_listeners(message, ctx, 'مصروف')
            if listener_status in ['back', 'help']:
                if listener_status == 'back':
                    del ctx
                return listener_msg
            
            if step == 1:
                # حفظ الوصف والانتقال للخطوة التالية
                data['description'] = message.strip()
                ctx['data'] = data
                ctx['step'] = 2
                return """✅ **تم حفظ الوصف:** {description}

📝 **الخطوة 2: المبلغ**
اكتب مبلغ المصروف (بالدرهم)

💡 **مثال:** 200

🤖 اكتب المبلغ الآن...""".format(description=data['description'])
            
            elif step == 2:
                # حفظ المبلغ والانتقال للخطوة التالية
                try:
                    data['amount'] = float(message.strip().replace('درهم', '').replace('د.إ', '').strip())
                    ctx['data'] = data
                    ctx['step'] = 3
                    return """✅ **تم حفظ المبلغ:** {amount} درهم

📝 **الخطوة 3: الفئة**
اكتب فئة المصروف

💡 **مثال:** مرافق، صيانة، أدوات

🤖 اكتب الفئة الآن...""".format(amount=data['amount'])
                except:
                    return """❌ **خطأ في إدخال المبلغ!**

💡 **يرجى إدخال رقم صحيح**

🤖 أعد إدخال المبلغ..."""
            
            elif step == 3:
                # حفظ الفئة وإنشاء المصروف
                data['category'] = message.strip()
                
                try:
                    from models.expense import Expense
                    
                    # إنشاء المصروف الجديد
                    from utils.helpers import generate_number
                    expense_number = generate_number('EXP', Expense, 'expense_number', branch_id=getattr(current_user, 'branch_id', None))
                    expense = Expense(
                        expense_number=expense_number,
                        description=data['description'],
                        amount=data['amount'],
                        amount_aed=data['amount'],
                        currency='AED',
                        exchange_rate=1,
                        expense_date=datetime.now(timezone.utc),
                        payment_method='cash',
                        user_id=user.id
                    )
                    assign_tenant_id(expense)
                    db.session.add(expense)
                    db.session.commit()
                    
                    # تدريب الذكاء المحلي
                    train_local_ai('create_expense', data, {'success': True, 'expense_id': expense.id})
                    
                    # مسح السياق
                    del ctx
                    
                    final_options = create_final_options('مصروف', data['description'], expense.id)
                    
                    return f"""✅ **تم إنشاء المصروف بنجاح!**

📋 **التفاصيل:**
- الوصف: {data['description']}
- المبلغ: {data['amount']} درهم
- الفئة: {data['category']}
- التاريخ: {expense.expense_date.strftime('%Y-%m-%d')}
- الرقم: #{expense.id}

{final_options}

🤖 اكتب رقم الخيار أو اكتب "عودة"

🤖 المصدر: GROQ API + التحليل المحلي"""
                
                except Exception as e:
                    # تدريب الذكاء المحلي من الخطأ
                    train_local_ai('create_expense', data, {'success': False, 'error': str(e)})
                    
                    # مسح السياق في حالة الخطأ
                    del ctx
                    return f"""❌ **خطأ في إنشاء المصروف:**

{str(e)}

💡 **حاول مرة أخرى:** اكتب "مصروف" ثم "1"

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        # ========== نظام الحوار التفاعلي للرقم 1 (إضافة مورد جديد) ==========
        if msg_lower.strip() == '1' and ctx.get('last_action') == 'مورد':
            ctx['step'] = 1
            ctx['option'] = '1'
            ctx['data'] = {}
            return """🤖 ممتاز! اخترت إضافة مورد جديد. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: اسم المورد**
اكتب اسم المورد الكامل

💡 **مثال:** شركة قطع غيار دبي

💬 **اكتب "عودة" للرجوع أو "مساعدة" للمساعدة**

🤖 اكتب اسم المورد الآن..."""
        
        # ========== معالجة الخطوات التالية (إضافة مورد) ==========
        if ctx.get('last_action') == 'مورد' and ctx.get('option') == '1':
            step = ctx.get('step', 0)
            data = ctx.get('data', {})
            
            listener_status, listener_msg = apply_smart_listeners(message, ctx, 'مورد')
            if listener_status in ['back', 'help']:
                if listener_status == 'back':
                    del ctx
                return listener_msg
            
            if step == 1:
                data['name'] = message.strip()
                ctx['data'] = data
                ctx['step'] = 2
                return """✅ **تم حفظ الاسم:** {name}

📝 **الخطوة 2: رقم الهاتف**
اكتب رقم هاتف المورد

💡 **مثال:** 0561234567

💬 **اكتب "عودة" للرجوع أو "مساعدة" للمساعدة**

🤖 اكتب رقم الهاتف الآن...""".format(name=data['name'])
            
            elif step == 2:
                data['phone'] = message.strip()
                ctx['data'] = data
                ctx['step'] = 3
                return """✅ **تم حفظ رقم الهاتف:** {phone}

📝 **الخطوة 3: العنوان**
اكتب عنوان المورد

💡 **مثال:** دبي - المنطقة الصناعية

💬 **اكتب "عودة" للرجوع أو "مساعدة" للمساعدة**

🤖 اكتب العنوان الآن...""".format(phone=data['phone'])
            
            elif step == 3:
                data['address'] = message.strip()
                ctx['data'] = data
                ctx['step'] = 4
                return """✅ **تم حفظ العنوان:** {address}

📝 **الخطوة 4: الرصيد الابتدائي (المبلغ المستحق للمورد)**
اكتب الرصيد الابتدائي بالدرهم (أو اكتب "0" إذا لم يكن هناك رصيد)

💡 **مثال:** 5000 (يعني عليك للمورد 5000 درهم)

💬 **اكتب "عودة" للرجوع أو "مساعدة" للمساعدة**

🤖 اكتب الرصيد الآن...""".format(address=data['address'])
            
            elif step == 4:
                try:
                    initial_balance = float(message.strip().replace('درهم', '').strip())
                    data['initial_balance'] = initial_balance
                    ctx['data'] = data
                    ctx['step'] = 5
                    return """✅ **تم حفظ الرصيد الابتدائي:** {balance} درهم

📝 **الخطوة 5: الرقم الضريبي (اختياري)**
اكتب الرقم الضريبي للمورد أو اكتب "تخطي"

💡 **مثال:** 123456789012345

💬 **اكتب "تخطي" إذا لم يكن متوفراً**

🤖 اكتب الرقم الضريبي الآن...""".format(balance=initial_balance)
                except:
                    return """❌ **خطأ في إدخال الرصيد!**

💡 **يرجى إدخال رقم صحيح**

🤖 أعد إدخال الرصيد..."""
            
            elif step == 5:
                tax_number = message.strip() if message.strip().lower() not in ['تخطي', 'skip'] else None
                data['tax_number'] = tax_number
                
                try:
                    from models.supplier import Supplier
                    supplier = Supplier(
                        name=data['name'],
                        phone=data['phone'],
                        address=data['address'],
                        tax_number=data.get('tax_number'),
                        total_purchases_aed=data['initial_balance'],
                        total_paid_aed=0
                    )
                    assign_tenant_id(supplier)
                    db.session.add(supplier)
                    db.session.commit()
                    
                    train_local_ai('create_supplier', data, {'success': True, 'supplier_id': supplier.id})
                    
                    del ctx
                    
                    balance_info = f"- الرصيد الابتدائي: {data['initial_balance']} درهم" if data['initial_balance'] > 0 else "- لا يوجد رصيد مستحق"
                    tax_info = f"- الرقم الضريبي: {data['tax_number']}" if data.get('tax_number') else ""
                    
                    return f"""✅ **تم إنشاء المورد بنجاح!**

📋 **التفاصيل:**
- الاسم: {data['name']}
- الهاتف: {data['phone']}
- العنوان: {data['address']}
{balance_info}
{tax_info}
- الرقم: #{supplier.id}

💡 **ماذا تريد أن تفعل الآن؟**
1️⃣ إضافة مورد آخر
2️⃣ عرض جميع الموردين
3️⃣ إضافة مشتريات من هذا المورد
4️⃣ العودة للقائمة الرئيسية

🤖 اكتب رقم الخيار أو اكتب "عودة"

🤖 المصدر: GROQ API + التحليل المحلي"""
                
                except Exception as e:
                    train_local_ai('create_supplier', data, {'success': False, 'error': str(e)})
                    del ctx
                    return f"""❌ **خطأ في إنشاء المورد:** {str(e)}

💡 **حاول مرة أخرى:** اكتب "مورد" ثم "1"

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        # ========== نظام الحوار التفاعلي للرقم 1 (إضافة مشتريات جديدة) ==========
        if msg_lower.strip() == '1' and ctx.get('last_action') == 'مشتريات':
            ctx['step'] = 1
            ctx['option'] = '1'
            ctx['data'] = {}
            return """🤖 ممتاز! اخترت إضافة مشتريات جديدة. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: اسم المورد**
اكتب اسم المورد

💡 **مثال:** شركة قطع غيار دبي

🤖 اكتب اسم المورد الآن..."""
        
        # ========== معالجة الخطوات التالية (إضافة مشتريات) ==========
        if ctx.get('last_action') == 'مشتريات' and ctx.get('option') == '1':
            step = ctx.get('step', 0)
            data = ctx.get('data', {})
            
            listener_status, listener_msg = apply_smart_listeners(message, ctx, 'مشتريات')
            if listener_status in ['back', 'help']:
                if listener_status == 'back':
                    del ctx
                return listener_msg
            
            if step == 1:
                from models.supplier import Supplier
                supplier = Supplier.query.filter_by(name=message.strip(), is_active=True, tenant_id=tid).first()
                if not supplier:
                    return """❌ **المورد غير موجود!**

💡 **تأكد من اسم المورد أو أضف مورد جديد أولاً**

🤖 اكتب اسم المورد الصحيح أو اكتب "مورد" لإضافة مورد جديد..."""
                
                data['supplier_id'] = supplier.id
                data['supplier_name'] = supplier.name
                ctx['data'] = data
                ctx['step'] = 2
                return """✅ **تم العثور على المورد:** {supplier_name}

📝 **الخطوة 2: اسم المنتج**
اكتب اسم المنتج المشترى

💡 **مثال:** فلتر زيت

🤖 اكتب اسم المنتج الآن...""".format(supplier_name=supplier.name)
            
            elif step == 2:
                from models.product import Product
                product = Product.query.filter_by(tenant_id=tid, name=message.strip(), is_active=True).first()
                if not product:
                    return """❌ **المنتج غير موجود!**

💡 **تأكد من اسم المنتج أو أضف منتج جديد أولاً**

🤖 اكتب اسم المنتج الصحيح أو اكتب "منتج" لإضافة منتج جديد..."""
                
                data['product_id'] = product.id
                data['product_name'] = product.name
                ctx['data'] = data
                ctx['step'] = 3
                return """✅ **تم العثور على المنتج:** {product_name}

📝 **الخطوة 3: الكمية**
اكتب الكمية المشتراة

💡 **مثال:** 50

🤖 اكتب الكمية الآن...""".format(product_name=product.name)
            
            elif step == 3:
                try:
                    data['quantity'] = float(message.strip())
                    ctx['data'] = data
                    ctx['step'] = 4
                    return """✅ **تم حفظ الكمية:** {quantity}

📝 **الخطوة 4: سعر الشراء**
اكتب سعر الشراء (بالدرهم)

💡 **مثال:** 40

🤖 اكتب السعر الآن...""".format(quantity=data['quantity'])
                except:
                    return """❌ **خطأ في إدخال الكمية!**

💡 **يرجى إدخال رقم صحيح**

🤖 أعد إدخال الكمية..."""
            
            elif step == 4:
                try:
                    data['unit_price'] = float(message.strip().replace('درهم', '').strip())
                    total_amount = data['unit_price'] * data['quantity']
                    
                    from models.purchase import Purchase, PurchaseLine
                    from models.product import Product
                    from utils.helpers import generate_number
                    
                    purchase_number = generate_number('P', Purchase, 'purchase_number', branch_id=getattr(current_user, 'branch_id', None))
                    purchase = Purchase(
                        purchase_number=purchase_number,
                        supplier_id=data['supplier_id'],
                        supplier_name=data.get('supplier_name', ''),
                        total_amount=total_amount,
                        amount=total_amount,
                        amount_aed=total_amount,
                        currency='AED',
                        exchange_rate=1,
                        user_id=user.id
                    )
                    assign_tenant_id(purchase)
                    db.session.add(purchase)
                    db.session.flush()
                    
                    purchase_line = PurchaseLine(
                        purchase_id=purchase.id,
                        product_id=data['product_id'],
                        quantity=data['quantity'],
                        unit_cost=data['unit_price'],
                        total=total_amount
                    )
                    db.session.add(purchase_line)
                    
                    wh = Warehouse.query.filter_by(tenant_id=tid, is_active=True).first()
                    StockService.add_stock(
                        product_id=data['product_id'],
                        quantity=data['quantity'],
                        reference_type=GLRef.PURCHASE,
                        reference_id=purchase.id,
                        warehouse_id=wh.id if wh else None,
                    )
                    
                    db.session.commit()
                    
                    train_local_ai('create_purchase', data, {'success': True, 'purchase_id': purchase.id})
                    
                    del ctx
                    
                    return f"""✅ **تم إنشاء المشتريات بنجاح!**

📋 **التفاصيل:**
- المورد: {data['supplier_name']}
- المنتج: {data['product_name']}
- الكمية: {data['quantity']}
- سعر الشراء: {data['unit_price']} درهم
- المجموع: {total_amount} درهم
- رقم المشتريات: #{purchase.id}

💡 **ماذا تريد أن تفعل الآن؟**
1️⃣ إضافة مشتريات أخرى
2️⃣ عرض جميع المشتريات
3️⃣ العودة للقائمة الرئيسية

🤖 اكتب رقم الخيار أو اكتب "عودة"

🤖 المصدر: GROQ API + التحليل المحلي"""
                
                except Exception as e:
                    train_local_ai('create_purchase', data, {'success': False, 'error': str(e)})
                    del ctx
                    return f"""❌ **خطأ في إنشاء المشتريات:** {str(e)}

💡 **حاول مرة أخرى:** اكتب "مشتريات" ثم "1"

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        # ========== نظام الحوار التفاعلي للرقم 1 (إضافة شيك جديد) ==========
        if msg_lower.strip() == '1' and ctx.get('last_action') == 'شيك':
            ctx['step'] = 1
            ctx['option'] = '1'
            ctx['data'] = {}
            return """🤖 ممتاز! اخترت إضافة شيك جديد. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: نوع الشيك**
اكتب نوع الشيك (وارد أو صادر)

💡 **مثال:** وارد

🤖 اكتب نوع الشيك الآن..."""
        
        # ========== معالجة الخطوات التالية (إضافة شيك) ==========
        if ctx.get('last_action') == 'شيك' and ctx.get('option') == '1':
            step = ctx.get('step', 0)
            data = ctx.get('data', {})
            
            listener_status, listener_msg = apply_smart_listeners(message, ctx, 'شيك')
            if listener_status in ['back', 'help']:
                if listener_status == 'back':
                    del ctx
                return listener_msg
            
            if step == 1:
                cheque_type = message.strip()
                if cheque_type not in ['وارد', 'صادر', 'incoming', 'outgoing']:
                    return """❌ **نوع الشيك غير صحيح!**

💡 **اكتب "وارد" أو "صادر"**

🤖 أعد إدخال نوع الشيك..."""
                
                data['cheque_type'] = 'incoming' if 'وارد' in cheque_type else 'outgoing'
                ctx['data'] = data
                ctx['step'] = 2
                return """✅ **تم حفظ نوع الشيك:** {type}

📝 **الخطوة 2: رقم الشيك**
اكتب رقم الشيك

💡 **مثال:** 123456

🤖 اكتب رقم الشيك الآن...""".format(type=cheque_type)
            
            elif step == 2:
                data['cheque_number'] = message.strip()
                ctx['data'] = data
                ctx['step'] = 3
                return """✅ **تم حفظ رقم الشيك:** {number}

📝 **الخطوة 3: المبلغ**
اكتب مبلغ الشيك (بالدرهم)

💡 **مثال:** 5000

🤖 اكتب المبلغ الآن...""".format(number=data['cheque_number'])
            
            elif step == 3:
                try:
                    data['amount'] = float(message.strip().replace('درهم', '').strip())
                    ctx['data'] = data
                    ctx['step'] = 4
                    return """✅ **تم حفظ المبلغ:** {amount} درهم

📝 **الخطوة 4: تاريخ الاستحقاق**
اكتب تاريخ استحقاق الشيك

💡 **مثال:** 2025-12-31

🤖 اكتب التاريخ الآن...""".format(amount=data['amount'])
                except:
                    return """❌ **خطأ في إدخال المبلغ!**

💡 **يرجى إدخال رقم صحيح**

🤖 أعد إدخال المبلغ..."""
            
            elif step == 4:
                try:
                    from models.cheque import Cheque
                    from datetime import datetime as dt
                    
                    due_date = dt.strptime(message.strip(), '%Y-%m-%d')
                    
                    cheque = Cheque(
                        cheque_number=data['cheque_number'],
                        amount=data['amount'],
                        due_date=due_date,
                        cheque_type=data['cheque_type'],
                        status='pending',
                        user_id=user.id
                    )
                    db.session.add(cheque)
                    db.session.commit()
                    
                    train_local_ai('create_cheque', data, {'success': True, 'cheque_id': cheque.id})
                    
                    del ctx
                    
                    return f"""✅ **تم إنشاء الشيك بنجاح!**

📋 **التفاصيل:**
- رقم الشيك: {data['cheque_number']}
- المبلغ: {data['amount']} درهم
- النوع: {data['cheque_type']}
- تاريخ الاستحقاق: {due_date.strftime('%Y-%m-%d')}
- الرقم: #{cheque.id}

💡 **ماذا تريد أن تفعل الآن؟**
1️⃣ إضافة شيك آخر
2️⃣ عرض جميع الشيكات
3️⃣ العودة للقائمة الرئيسية

🤖 اكتب رقم الخيار أو اكتب "عودة"

🤖 المصدر: GROQ API + التحليل المحلي"""
                
                except Exception as e:
                    train_local_ai('create_cheque', data, {'success': False, 'error': str(e)})
                    del ctx
                    return f"""❌ **خطأ في إنشاء الشيك:** {str(e)}

💡 **حاول مرة أخرى:** اكتب "شيك" ثم "1"

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        # ========== نظام الحوار التفاعلي للرقم 1 (عرض دفتر الأستاذ) ==========
        if msg_lower.strip() == '1' and ctx.get('last_action') == 'دفتر':
            from models.gl import GLJournalEntry
            gl_entries = GLJournalEntry.query.filter_by(is_active=True, tenant_id=tid).order_by(GLJournalEntry.entry_date.desc()).limit(20).all()
            
            del ctx
            
            if gl_entries:
                gl_list = "\n".join([f"• #{g.id} - {g.description} - {g.debit_amount} درهم - {g.entry_date.strftime('%Y-%m-%d')}" for g in gl_entries])
                return f"""✅ **دفتر الأستاذ (آخر 20 قيد):**

{gl_list}

💡 **ماذا تريد أن تفعل الآن؟**
1️⃣ البحث في القيود
2️⃣ العودة للقائمة الرئيسية

🤖 اكتب رقم الخيار

🤖 المصدر: GROQ API + التحليل المحلي"""
            else:
                return """❌ **لا يوجد قيود في دفتر الأستاذ**

💡 **القيود تُنشأ تلقائياً من العمليات (فواتير، مصروفات، دفعات)**

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        # ========== نظام الحوار التفاعلي للرقم 1 (عرض المستودعات) ==========
        if msg_lower.strip() == '1' and ctx.get('last_action') == 'مستودع':
            warehouses = Warehouse.query.filter_by(is_active=True, tenant_id=tid).all()
            
            del ctx
            
            if warehouses:
                wh_list = "\n".join([f"• {w.name} - {w.location or 'لا يوجد موقع'}" for w in warehouses])
                return f"""✅ **جميع المستودعات ({len(warehouses)} مستودع):**

{wh_list}

💡 **ماذا تريد أن تفعل الآن؟**
1️⃣ عرض المخزون
2️⃣ البحث عن مستودع
3️⃣ العودة للقائمة الرئيسية

🤖 اكتب رقم الخيار

🤖 المصدر: GROQ API + التحليل المحلي"""
            else:
                return """❌ **لا يوجد مستودعات في النظام**

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        # ========== نظام الحوار التفاعلي للرقم 1 (إضافة مستخدم جديد) ==========
        if msg_lower.strip() == '1' and ctx.get('last_action') == 'مستخدم':
            ctx['step'] = 1
            ctx['option'] = '1'
            ctx['data'] = {}
            return """🤖 ممتاز! اخترت إضافة مستخدم جديد. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: اسم المستخدم (Username)**
اكتب اسم المستخدم للدخول

💡 **مثال:** ahmed.mohamed

🤖 اكتب اسم المستخدم الآن..."""
        
        # ========== معالجة الخطوات التالية (إضافة مستخدم) ==========
        if ctx.get('last_action') == 'مستخدم' and ctx.get('option') == '1':
            step = ctx.get('step', 0)
            data = ctx.get('data', {})
            
            listener_status, listener_msg = apply_smart_listeners(message, ctx, 'مستخدم')
            if listener_status in ['back', 'help']:
                if listener_status == 'back':
                    del ctx
                return listener_msg
            
            if step == 1:
                data['username'] = message.strip()
                ctx['data'] = data
                ctx['step'] = 2
                return """✅ **تم حفظ اسم المستخدم:** {username}

📝 **الخطوة 2: كلمة المرور**
اكتب كلمة المرور

💡 **مثال:** Pass@123

🤖 اكتب كلمة المرور الآن...""".format(username=data['username'])
            
            elif step == 2:
                data['password'] = message.strip()
                ctx['data'] = data
                ctx['step'] = 3
                return """✅ **تم حفظ كلمة المرور**

📝 **الخطوة 3: الدور (Role)**
اكتب دور المستخدم

💡 **الخيارات:** owner، admin، accountant، sales، viewer

🤖 اكتب الدور الآن..."""
            
            elif step == 3:
                role = message.strip().lower()
                if role not in ['owner', 'admin', 'accountant', 'sales', 'viewer']:
                    return """❌ **الدور غير صحيح!**

💡 **الأدوار المتاحة:**
• owner (مالك)
• admin (مدير)
• accountant (محاسب)
• sales (مبيعات)
• viewer (مشاهد)

🤖 أعد إدخال الدور..."""
                
                data['role'] = role
                ctx['data'] = data
                ctx['step'] = 4
                return """✅ **تم حفظ الدور:** {role}

📝 **الخطوة 4: البريد الإلكتروني (اختياري)**
اكتب البريد الإلكتروني أو اكتب "تخطي"

💡 **مثال:** ahmed@example.com

🤖 اكتب البريد الإلكتروني الآن...""".format(role=role)
            
            elif step == 4:
                email = message.strip() if message.strip().lower() != 'تخطي' else None
                data['email'] = email
                
                try:
                    from models.user import User
                    from werkzeug.security import generate_password_hash
                    from utils.password_validator import PasswordValidator
                    
                    is_valid, pwd_errors = PasswordValidator.validate(data.get('password', ''))
                    if not is_valid:
                        raise ValueError('; '.join(pwd_errors))
                    
                    new_user = User(
                        username=data['username'],
                        password_hash=generate_password_hash(data['password']),
                        role=data['role'],
                        email=data['email']
                    )
                    db.session.add(new_user)
                    db.session.commit()
                    
                    train_local_ai('create_user', data, {'success': True, 'user_id': new_user.id})
                    
                    del ctx
                    
                    return f"""✅ **تم إنشاء المستخدم بنجاح!**

📋 **التفاصيل:**
- اسم المستخدم: {data['username']}
- الدور: {data['role']}
- البريد الإلكتروني: {data['email'] or 'لا يوجد'}
- الرقم: #{new_user.id}

💡 **ماذا تريد أن تفعل الآن؟**
1️⃣ إضافة مستخدم آخر
2️⃣ عرض جميع المستخدمين
3️⃣ العودة للقائمة الرئيسية

🤖 اكتب رقم الخيار أو اكتب "عودة"

🤖 المصدر: GROQ API + التحليل المحلي"""
                
                except Exception as e:
                    train_local_ai('create_user', data, {'success': False, 'error': str(e)})
                    del ctx
                    return f"""❌ **خطأ في إنشاء المستخدم:** {str(e)}

💡 **حاول مرة أخرى:** اكتب "مستخدم" ثم "1"

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        # ========== نظام الحوار التفاعلي للرقم 2 (عرض جميع العناصر) ==========
        if msg_lower.strip() == '2' and ctx.get('last_action') == 'عميل':
            from models.customer import Customer
            customers = Customer.query.filter_by(tenant_id=tid, is_active=True).all()
            if customers:
                customers_list = "\n".join([f"• {c.name} - {c.phone or 'لا يوجد هاتف'}" for c in customers[:10]])
                more_text = f"\n\n... و {len(customers) - 10} عميل آخر" if len(customers) > 10 else ""
                return f"""✅ **جميع العملاء ({len(customers)} عميل):**

{customers_list}{more_text}

🤖 **للبحث عن عميل معين، اكتب اسمه أو رقم هاتفه**

🤖 المصدر: GROQ API + التحليل المحلي"""
            else:
                return """❌ **لا يوجد عملاء في النظام**

🤖 **لإضافة عميل جديد، اكتب "عميل" ثم اختر "1"**

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        if msg_lower.strip() == '2' and ctx.get('last_action') == 'منتج':
            from models.product import Product
            products = Product.query.filter_by(tenant_id=tid, is_active=True).all()
            if products:
                products_list = "\n".join([f"• {p.name} - {p.part_number} - {p.current_stock} {p.unit}" for p in products[:10]])
                more_text = f"\n\n... و {len(products) - 10} منتج آخر" if len(products) > 10 else ""
                return f"""✅ **جميع المنتجات ({len(products)} منتج):**

{products_list}{more_text}

🤖 **للبحث عن منتج معين، اكتب اسمه أو رقم القطعة**

🤖 المصدر: GROQ API + التحليل المحلي"""
            else:
                return """❌ **لا يوجد منتجات في النظام**

🤖 **لإضافة منتج جديد، اكتب "منتج" ثم اختر "1"**

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        if msg_lower.strip() == '2' and ctx.get('last_action') == 'فاتورة':
            from models.sale import Sale
            sales = Sale.query.filter_by(is_active=True).all()
            if sales:
                sales_list = "\n".join([f"• #{s.id} - {s.customer.name if s.customer else 'غير محدد'} - {s.total_amount} درهم" for s in sales[:10]])
                more_text = f"\n\n... و {len(sales) - 10} فاتورة أخرى" if len(sales) > 10 else ""
                return f"""✅ **جميع الفواتير ({len(sales)} فاتورة):**

{sales_list}{more_text}

🤖 **للبحث عن فاتورة معينة، اكتب رقم الفاتورة أو اسم العميل**

🤖 المصدر: GROQ API + التحليل المحلي"""
            else:
                return """❌ **لا يوجد فواتير في النظام**

🤖 **لإنشاء فاتورة جديدة، اكتب "فاتورة" ثم اختر "1"**

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        if msg_lower.strip() == '2' and ctx.get('last_action') == 'مصروف':
            from models.expense import Expense
            expenses = Expense.query.filter_by(is_active=True).all()
            if expenses:
                expenses_list = "\n".join([f"• {e.description} - {e.amount} درهم - {e.category}" for e in expenses[:10]])
                more_text = f"\n\n... و {len(expenses) - 10} مصروف آخر" if len(expenses) > 10 else ""
                return f"""✅ **جميع المصروفات ({len(expenses)} مصروف):**

{expenses_list}{more_text}

🤖 **للبحث عن مصروف معين، اكتب وصفه أو فئته**

🤖 المصدر: GROQ API + التحليل المحلي"""
            else:
                return """❌ **لا يوجد مصروفات في النظام**

🤖 **لإضافة مصروف جديد، اكتب "مصروف" ثم اختر "1"**

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        if msg_lower.strip() == '2' and ctx.get('last_action') == 'مورد':
            from models.supplier import Supplier
            suppliers = Supplier.query.filter_by(is_active=True, tenant_id=tid).all()
            del ctx
            if suppliers:
                suppliers_list = "\n".join([f"• {s.name} - {s.phone or 'لا يوجد هاتف'}" for s in suppliers[:10]])
                more_text = f"\n\n... و {len(suppliers) - 10} مورد آخر" if len(suppliers) > 10 else ""
                return f"""✅ **جميع الموردين ({len(suppliers)} مورد):**

{suppliers_list}{more_text}

🤖 المصدر: GROQ API + التحليل المحلي"""
            else:
                return """❌ **لا يوجد موردين في النظام**

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        if msg_lower.strip() == '2' and ctx.get('last_action') == 'مشتريات':
            from models.purchase import Purchase
            purchases = Purchase.query.filter_by(is_active=True).all()
            del ctx
            if purchases:
                purchases_list = "\n".join([f"• #{p.id} - {p.supplier.name if p.supplier else 'غير محدد'} - {p.total_amount} درهم" for p in purchases[:10]])
                more_text = f"\n\n... و {len(purchases) - 10} مشتريات أخرى" if len(purchases) > 10 else ""
                return f"""✅ **جميع المشتريات ({len(purchases)} مشتريات):**

{purchases_list}{more_text}

🤖 المصدر: GROQ API + التحليل المحلي"""
            else:
                return """❌ **لا يوجد مشتريات في النظام**

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        if msg_lower.strip() == '2' and ctx.get('last_action') == 'شيك':
            from models.cheque import Cheque
            cheques = Cheque.query.filter_by(is_active=True).all()
            del ctx
            if cheques:
                cheques_list = "\n".join([f"• #{c.id} - {c.cheque_number} - {c.amount} درهم - {c.status}" for c in cheques[:10]])
                more_text = f"\n\n... و {len(cheques) - 10} شيك آخر" if len(cheques) > 10 else ""
                return f"""✅ **جميع الشيكات ({len(cheques)} شيك):**

{cheques_list}{more_text}

🤖 المصدر: GROQ API + التحليل المحلي"""
            else:
                return """❌ **لا يوجد شيكات في النظام**

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        if msg_lower.strip() == '2' and ctx.get('last_action') == 'مستخدم':
            from models.user import User
            from utils.tenanting import scoped_user_query
            users = scoped_user_query(active_only=True).all()
            del ctx
            if users:
                users_list = "\n".join([f"• {u.username} - {u.role}" for u in users[:10]])
                more_text = f"\n\n... و {len(users) - 10} مستخدم آخر" if len(users) > 10 else ""
                return f"""✅ **جميع المستخدمين ({len(users)} مستخدم):**

{users_list}{more_text}

🤖 المصدر: GROQ API + التحليل المحلي"""
            else:
                return """❌ **لا يوجد مستخدمين في النظام**

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        if msg_lower.strip() == '2' and ctx.get('last_action') == 'دفتر':
            from models.gl import GLJournalEntry
            gl_entries = GLJournalEntry.query.filter_by(is_active=True, tenant_id=tid).order_by(GLJournalEntry.entry_date.desc()).limit(20).all()
            del ctx
            if gl_entries:
                gl_list = "\n".join([f"• #{g.id} - {g.description} - {g.debit_amount} درهم - {g.entry_date.strftime('%Y-%m-%d')}" for g in gl_entries])
                return f"""✅ **القيود المحاسبية (آخر 20 قيد):**

{gl_list}

🤖 المصدر: GROQ API + التحليل المحلي"""
            else:
                return """❌ **لا يوجد قيود في النظام**

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        if msg_lower.strip() == '2' and ctx.get('last_action') == 'مستودع':
            from models.product import Product
            products = Product.query.filter_by(tenant_id=tid, is_active=True).all()
            del ctx
            if products:
                stock_list = "\n".join([f"• {p.name} - {p.current_stock} {p.unit}" for p in products[:15]])
                more_text = f"\n\n... و {len(products) - 15} منتج آخر" if len(products) > 15 else ""
                return f"""✅ **المخزون الكامل ({len(products)} منتج):**

{stock_list}{more_text}

🤖 المصدر: GROQ API + التحليل المحلي"""
            else:
                return """❌ **لا يوجد منتجات في المخزون**

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        # ========== نظام الحوار التفاعلي للرقم 3 (البحث عن العناصر) ==========
        if msg_lower.strip() == '3' and ctx.get('last_action') == 'عميل':
            ctx['step'] = 1
            ctx['option'] = '3'
            return """🤖 ممتاز! اخترت البحث عن عميل. سأرشدك خطوة بخطوة:

📝 **اكتب اسم العميل أو رقم هاتفه**
اكتب اسم العميل أو رقم هاتفه للبحث

💡 **أمثلة:**
• "أحمد محمد"
• "0561234567"
• "أحمد"

🤖 اكتب اسم العميل أو رقم هاتفه الآن..."""
        
        if msg_lower.strip() == '3' and ctx.get('last_action') == 'منتج':
            ctx['step'] = 1
            ctx['option'] = '3'
            return """🤖 ممتاز! اخترت البحث عن منتج. سأرشدك خطوة بخطوة:

📝 **اكتب اسم المنتج أو رقم القطعة**
اكتب اسم المنتج أو رقم القطعة للبحث

💡 **أمثلة:**
• "فلتر زيت"
• "12345"
• "كاتربلر"

🤖 اكتب اسم المنتج أو رقم القطعة الآن..."""
        
        if msg_lower.strip() == '3' and ctx.get('last_action') == 'فاتورة':
            return """🤖 ممتاز! اخترت البحث عن فاتورة. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: اكتب رقم الفاتورة أو اسم العميل**
اكتب رقم الفاتورة أو اسم العميل للبحث

💡 **أمثلة:**
• "123"
• "أحمد محمد"
• "فاتورة 123"

🤖 اكتب رقم الفاتورة أو اسم العميل الآن..."""
        
        if msg_lower.strip() == '3' and ctx.get('last_action') == 'مصروف':
            return """🤖 ممتاز! اخترت البحث عن مصروف. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: اكتب وصف المصروف أو فئته**
اكتب وصف المصروف أو فئته للبحث

💡 **أمثلة:**
• "فواتير الكهرباء"
• "صيانة"
• "مرافق"

🤖 اكتب وصف المصروف أو فئته الآن..."""
        
        if msg_lower.strip() == '3' and ctx.get('last_action') == 'مورد':
            return """🤖 ممتاز! اخترت البحث عن مورد. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: اكتب اسم المورد أو رقم هاتفه**
اكتب اسم المورد أو رقم هاتفه للبحث

💡 **أمثلة:**
• "شركة قطع غيار"
• "0561234567"
• "دبي"

🤖 اكتب اسم المورد أو رقم هاتفه الآن..."""
        
        if msg_lower.strip() == '3' and ctx.get('last_action') == 'مشتريات':
            return """🤖 ممتاز! اخترت البحث عن مشتريات. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: اكتب رقم المشتريات أو اسم المورد**
اكتب رقم المشتريات أو اسم المورد للبحث

💡 **أمثلة:**
• "123"
• "شركة قطع غيار"
• "مشتريات 123"

🤖 اكتب رقم المشتريات أو اسم المورد الآن..."""
        
        if msg_lower.strip() == '3' and ctx.get('last_action') == 'شيك':
            return """🤖 ممتاز! اخترت البحث عن شيك. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: اكتب رقم الشيك أو المبلغ**
اكتب رقم الشيك أو المبلغ للبحث

💡 **أمثلة:**
• "123"
• "1000"
• "شيك 123"

🤖 اكتب رقم الشيك أو المبلغ الآن..."""
        
        if msg_lower.strip() == '3' and ctx.get('last_action') == 'دفتر':
            return """🤖 ممتاز! اخترت البحث عن قيد. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: اكتب وصف القيد أو رقمه**
اكتب وصف القيد أو رقمه للبحث

💡 **أمثلة:**
• "قيد مبيعات"
• "123"
• "مبيعات اليوم"

🤖 اكتب وصف القيد أو رقمه الآن..."""
        
        if msg_lower.strip() == '3' and ctx.get('last_action') == 'مستودع':
            return """🤖 ممتاز! اخترت البحث عن مستودع. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: اكتب اسم المستودع أو موقعه**
اكتب اسم المستودع أو موقعه للبحث

💡 **أمثلة:**
• "المستودع الرئيسي"
• "دبي"
• "الشارقة"

🤖 اكتب اسم المستودع أو موقعه الآن..."""
        
        if msg_lower.strip() == '3' and ctx.get('last_action') == 'مستخدم':
            return """🤖 ممتاز! اخترت البحث عن مستخدم. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: اكتب اسم المستخدم أو إيميله**
اكتب اسم المستخدم أو إيميله للبحث

💡 **أمثلة:**
• "أحمد محمد"
• "ahmed@example.com"
• "admin"

🤖 اكتب اسم المستخدم أو إيميله الآن..."""
        
        # ========== نظام الحوار التفاعلي للرقم 4 (إدارة المخزون) ==========
        if msg_lower.strip() == '4' and ctx.get('last_action') == 'مستودع':
            return """🤖 ممتاز! اخترت إدارة المخزون. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: اكتب اسم المستودع**
اكتب اسم المستودع لإدارة مخزونه

💡 **أمثلة:**
• "المستودع الرئيسي"
• "مستودع دبي"
• "مخزن الشارقة"

🤖 اكتب اسم المستودع الآن..."""
        
        # ========== نظام الحوار التفاعلي للرقم 4 (تعديل صلاحيات المستخدمين) ==========
        if msg_lower.strip() == '4' and ctx.get('last_action') == 'مستخدم':
            return """🤖 ممتاز! اخترت تعديل صلاحيات مستخدم. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: اكتب اسم المستخدم**
اكتب اسم المستخدم لتعديل صلاحياته

💡 **أمثلة:**
• "أحمد محمد"
• "admin"
• "user1"

🤖 اكتب اسم المستخدم الآن..."""
        
        # ========== نظام الحوار التفاعلي للرقم 4 (رفع منتجات من Excel) ==========
        if msg_lower.strip() == '4' and ctx.get('last_action') == 'منتج':
            del ctx
            return """🤖 ممتاز! اخترت رفع منتجات من Excel.

📂 **قم بتحميل ملف Excel:**
1. افتح صفحة المساعد في المتصفح
2. اضغط على زر "فتح ملف Excel" لتحرير القالب
3. أدخل بيانات المنتجات في الملف
4. احفظ الملف
5. ارفع الملف من خلال الزر "رفع منتجات من Excel"

💡 **أو اذهب مباشرة إلى:**
http://localhost:5000/ai/assistant

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        if 'عميل' in msg_lower and ':' in message:
            match = re.search(r':(.*)', message)
            if match:
                data_str = match.group(1).strip()
                parts = re.split(r'[،,.]', data_str)
                parts = [p.strip() for p in parts if p.strip()]
                
                if len(parts) >= 2:
                    name = parts[0]
                    phone = parts[1]
                    address = parts[2] if len(parts) > 2 else ''
                    
                    customer = Customer(
                        name=name,
                        phone=phone,
                        address=address,
                        is_active=True
                    )
                    assign_tenant_id(customer, user)
                    db.session.add(customer)
                    db.session.commit()
                    
                    return f"""✅ تم إنشاء العميل بنجاح!

📋 التفاصيل:
- الاسم: {name}
- الهاتف: {phone}
- العنوان: {address or 'غير محدد'}
- الرقم: #{customer.id}

💡 يمكنك الآن إنشاء فاتورة لهذا العميل!

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        if 'منتج' in msg_lower and ':' in message:
            match = re.search(r':(.*)', message)
            if match:
                data_str = match.group(1).strip()
                parts = re.split(r'[،,.]', data_str)
                parts = [p.strip() for p in parts if p.strip()]
                
                if len(parts) >= 3:
                    name = parts[0]
                    part_number = parts[1]
                    price_str = parts[2].replace('درهم', '').replace('د.إ', '').strip()
                    quantity = int(parts[3].replace('قطعة', '').replace('قطعه', '').strip()) if len(parts) > 3 else 0
                    
                    product = Product(
                        name=name,
                        part_number=part_number,
                        regular_price=float(price_str),
                        current_stock=0,
                        is_active=True
                    )
                    assign_tenant_id(product, user)
                    db.session.add(product)
                    db.session.flush()
                    if quantity > 0:
                        StockService.add_opening_stock(
                            product_id=product.id,
                            quantity=quantity,
                        )
                    db.session.commit()
                    
                    return f"""✅ تم إنشاء المنتج بنجاح!

📋 التفاصيل:
- الاسم: {name}
- رقم القطعة: {part_number}
- السعر: {price_str} درهم
- الكمية: {quantity}
- الرقم: #{product.id}

💡 الآن يمكنك بيع هذا المنتج!

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        if 'مورد' in msg_lower and ':' in message:
            match = re.search(r':(.*)', message)
            if match:
                data_str = match.group(1).strip()
                parts = re.split(r'[،,.]', data_str)
                parts = [p.strip() for p in parts if p.strip()]
                
                if len(parts) >= 2:
                    name = parts[0]
                    phone = parts[1]
                    email = parts[2] if len(parts) > 2 else ''
                    address = parts[3] if len(parts) > 3 else ''
                    
                    supplier = Supplier(
                        name=name,
                        phone=phone,
                        email=email,
                        address=address,
                        is_active=True
                    )
                    assign_tenant_id(supplier)
                    db.session.add(supplier)
                    db.session.commit()
                    
                    return f"""✅ تم إنشاء المورد بنجاح!

📋 التفاصيل:
- الاسم: {name}
- الهاتف: {phone}
- البريد: {email or 'غير محدد'}
- العنوان: {address or 'غير محدد'}
- الرقم: #{supplier.id}

💡 يمكنك الآن شراء من هذا المورد!

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        if any(word in msg_lower for word in ['فاتورة', 'بيع', 'مبيعات']) and ':' in message:
            match = re.search(r':(.*)', message)
            if match:
                data_str = match.group(1).strip()
                parts = re.split(r'[،,.]', data_str)
                parts = [p.strip() for p in parts if p.strip()]
                
                if len(parts) >= 3:
                    customer_name = parts[0]
                    product_name = parts[1]
                    quantity = int(parts[2]) if parts[2].isdigit() else 1
                    payment_method = parts[3] if len(parts) > 3 else 'cash'
                    
                    customer = Customer.query.filter_by(tenant_id=tid, name=customer_name, is_active=True).first()
                    if not customer:
                        return f"❌ العميل '{customer_name}' غير موجود. أنشئه أولاً!"
                    
                    product = Product.query.filter_by(tenant_id=tid, name=product_name, is_active=True).first()
                    if not product:
                        return f"❌ المنتج '{product_name}' غير موجود. أنشئه أولاً!"
                    
                    sale = Sale(
                        sale_number=f"INV-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                        customer_id=customer.id,
                        seller_id=user.id,
                        sale_date=datetime.now(timezone.utc),
                        subtotal=product.regular_price * quantity,
                        total_amount=product.regular_price * quantity,
                        amount=product.regular_price * quantity,
                        amount_aed=product.regular_price * quantity,
                        currency='AED',
                        exchange_rate=1,
                        payment_status='paid' if payment_method == 'cash' else 'unpaid',
                        status='confirmed'
                    )
                    assign_tenant_id(sale, user)
                    db.session.add(sale)
                    db.session.flush()
                    
                    sale_line = SaleLine(
                        sale_id=sale.id,
                        product_id=product.id,
                        quantity=quantity,
                        unit_price=product.regular_price,
                        line_total=product.regular_price * quantity
                    )
                    assign_tenant_id(sale_line, user)
                    db.session.add(sale_line)
                    
                    wh_l3 = Warehouse.query.filter_by(tenant_id=tid, is_active=True).first()
                    StockService.remove_stock(
                        product_id=product.id,
                        quantity=quantity,
                        reference_type=GLRef.SALE,
                        reference_id=sale.id,
                        warehouse_id=wh_l3.id if wh_l3 else None,
                    )
                    
                    db.session.commit()
                    
                    return f"""✅ تم إنشاء الفاتورة بنجاح!

📋 تفاصيل الفاتورة:
- رقم الفاتورة: {sale.sale_number}
- العميل: {customer.name}
- المنتج: {product.name} x {quantity}
- المبلغ الإجمالي: {sale.total_amount} درهم
- طريقة الدفع: {payment_method}
- المخزون المتبقي: {product.current_stock}

💡 تم خصم {quantity} قطعة من المخزون!

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        if 'مصروف' in msg_lower and ':' in message:
            match = re.search(r':(.*)', message)
            if match:
                data_str = match.group(1).strip()
                parts = re.split(r'[،,.]', data_str)
                parts = [p.strip() for p in parts if p.strip()]
                
                if len(parts) >= 2:
                    description = parts[0]
                    amount = float(parts[1].replace('درهم', '').replace('د.إ', '').strip())
                    category = parts[2] if len(parts) > 2 else 'عام'
                    
                    from utils.helpers import generate_number
                    expense_number = generate_number('EXP', Expense, 'expense_number', branch_id=getattr(current_user, 'branch_id', None))
                    expense = Expense(
                        expense_number=expense_number,
                        description=description,
                        amount=amount,
                        amount_aed=amount,
                        currency='AED',
                        exchange_rate=1,
                        expense_date=datetime.now(timezone.utc),
                        payment_method='cash',
                        user_id=user.id
                    )
                    assign_tenant_id(expense)
                    db.session.add(expense)
                    db.session.commit()
                    
                    return f"""✅ تم إضافة المصروف بنجاح!

📋 التفاصيل:
- الوصف: {description}
- المبلغ: {amount} درهم
- الفئة: {category}
- التاريخ: {expense.expense_date.strftime('%Y-%m-%d %H:%M')}
- الرقم: #{expense.id}

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        if 'دفعة' in msg_lower and ':' in message:
            match = re.search(r':(.*)', message)
            if match:
                data_str = match.group(1).strip()
                parts = re.split(r'[،,.]', data_str)
                parts = [p.strip() for p in parts if p.strip()]
                
                if len(parts) >= 3:
                    customer_name = parts[0]
                    amount = float(parts[1].replace('درهم', '').replace('د.إ', '').strip())
                    payment_method = parts[2]
                    
                    customer = Customer.query.filter_by(tenant_id=tid, name=customer_name, is_active=True).first()
                    if not customer:
                        return f"❌ العميل '{customer_name}' غير موجود!"
                    
                    from utils.helpers import generate_number
                    payment_number = generate_number('PAY', Payment, 'payment_number', branch_id=getattr(current_user, 'branch_id', None))
                    payment = Payment(
                        payment_number=payment_number,
                        customer_id=customer.id,
                        amount=amount,
                        amount_aed=amount,
                        currency='AED',
                        exchange_rate=1,
                        payment_date=datetime.now(timezone.utc),
                        payment_method=payment_method,
                        user_id=user.id,
                        direction='incoming',
                        payment_type='customer_payment'
                    )
                    assign_tenant_id(payment)
                    db.session.add(payment)
                    
                    customer.apply_receipt(amount)
                    
                    db.session.commit()
                    
                    return f"""✅ تم تسجيل الدفعة بنجاح!

📋 التفاصيل:
- العميل: {customer.name}
- المبلغ: {amount} درهم
- طريقة الدفع: {payment_method}
- الرصيد الجديد: {customer.balance} درهم
- الرقم: #{payment.id}

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        # ========== تعديل رصيد العميل ==========
        if any(word in msg_lower for word in ['رصيد', 'تعديل رصيد', 'تغيير رصيد']) and ':' in message:
            match = re.search(r':(.*)', message)
            if match:
                data_str = match.group(1).strip()
                parts = re.split(r'[،,.]', data_str)
                parts = [p.strip() for p in parts if p.strip()]
                
                if len(parts) >= 2:
                    customer_name = parts[0]
                    new_balance = float(parts[1].replace('درهم', '').replace('د.إ', '').strip())
                    
                    customer = Customer.query.filter_by(tenant_id=tid, name=customer_name, is_active=True).first()
                    if not customer:
                        return f"❌ العميل '{customer_name}' غير موجود!"
                    
                    old_balance = customer.balance
                    customer.set_balance(new_balance)
                    
                    db.session.commit()
                    
                    return f"""✅ تم تعديل رصيد العميل بنجاح!

📋 التفاصيل:
- العميل: {customer.name}
- الرصيد السابق: {old_balance} درهم
- الرصيد الجديد: {new_balance} درهم
- الفرق: {new_balance - float(old_balance)} درهم

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        # ========== استلام دفعة من العميل ==========
        if any(word in msg_lower for word in ['استلام', 'استلم', 'دفعة من']) and ':' in message:
            match = re.search(r':(.*)', message)
            if match:
                data_str = match.group(1).strip()
                parts = re.split(r'[،,.]', data_str)
                parts = [p.strip() for p in parts if p.strip()]
                
                if len(parts) >= 3:
                    customer_name = parts[0]
                    amount = float(parts[1].replace('درهم', '').replace('د.إ', '').strip())
                    payment_method = parts[2]
                    
                    customer = Customer.query.filter_by(tenant_id=tid, name=customer_name, is_active=True).first()
                    if not customer:
                        return f"❌ العميل '{customer_name}' غير موجود!"
                    
                    from utils.helpers import generate_number
                    payment_number = generate_number('PAY', Payment, 'payment_number', branch_id=getattr(current_user, 'branch_id', None))
                    payment = Payment(
                        payment_number=payment_number,
                        customer_id=customer.id,
                        amount=amount,
                        amount_aed=amount,
                        currency='AED',
                        exchange_rate=1,
                        payment_date=datetime.now(timezone.utc),
                        payment_method=payment_method,
                        user_id=user.id,
                        direction='incoming',
                        payment_type='customer_payment'
                    )
                    assign_tenant_id(payment)
                    db.session.add(payment)
                    
                    customer.apply_receipt(amount)
                    
                    db.session.commit()
                    
                    return f"""✅ تم استلام الدفعة بنجاح!

📋 التفاصيل:
- العميل: {customer.name}
- المبلغ المستلم: {amount} درهم
- طريقة الدفع: {payment_method}
- الرصيد الجديد: {customer.balance} درهم
- الرقم: #{payment.id}

💡 تم خصم المبلغ من رصيد العميل!

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        # ========== عرض رصيد العميل ==========
        if any(word in msg_lower for word in ['عرض رصيد', 'رصيد العميل', 'رصيد عميل']) and ':' in message:
            match = re.search(r':(.*)', message)
            if match:
                customer_name = match.group(1).strip()
                
                customer = Customer.query.filter_by(tenant_id=tid, name=customer_name, is_active=True).first()
                if not customer:
                    return f"❌ العميل '{customer_name}' غير موجود!"
                
                # جلب آخر 5 دفعات
                recent_payments = Payment.query.filter_by(customer_id=customer.id)\
                    .order_by(Payment.payment_date.desc()).limit(5).all()
                
                payments_info = ""
                if recent_payments:
                    payments_info = "\n\n📋 **آخر 5 دفعات:**\n"
                    for payment in recent_payments:
                        payments_info += f"• {payment.payment_date.strftime('%Y-%m-%d')}: {payment.amount_aed} درهم ({payment.payment_method})\n"
                
                return f"""✅ رصيد العميل:

📋 **التفاصيل:**
- العميل: {customer.name}
- الرصيد الحالي: {customer.balance} درهم
- الهاتف: {customer.phone or 'غير محدد'}
- العنوان: {customer.address or 'غير محدد'}{payments_info}

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        # ========== إعطاء دفعة للعميل ==========
        if any(word in msg_lower for word in ['إعطاء', 'أعطى', 'دفعة لل', 'دفعة ل']) and ':' in message:
            match = re.search(r':(.*)', message)
            if match:
                data_str = match.group(1).strip()
                parts = re.split(r'[،,.]', data_str)
                parts = [p.strip() for p in parts if p.strip()]
                
                if len(parts) >= 3:
                    customer_name = parts[0]
                    amount = float(parts[1].replace('درهم', '').replace('د.إ', '').strip())
                    reason = parts[2]
                    
                    customer = Customer.query.filter_by(tenant_id=tid, name=customer_name, is_active=True).first()
                    if not customer:
                        return f"❌ العميل '{customer_name}' غير موجود!"
                    
                    # إضافة المبلغ للرصيد (زيادة)
                    customer.adjust_balance(amount)
                    
                    # تسجيل العملية كدفعة سالبة
                    from utils.helpers import generate_number
                    payment_number = generate_number('PAY', Payment, 'payment_number', branch_id=getattr(current_user, 'branch_id', None))
                    payment = Payment(
                        payment_number=payment_number,
                        customer_id=customer.id,
                        amount=-amount,  # سالب لأننا نعطي للعميل
                        amount_aed=-amount,  # سالب لأننا نعطي للعميل
                        currency='AED',
                        exchange_rate=1,
                        payment_date=datetime.now(timezone.utc),
                        payment_method='refund',
                        user_id=user.id,
                        direction='outgoing',
                        payment_type='refund'
                    )
                    assign_tenant_id(payment)
                    db.session.add(payment)
                    
                    db.session.commit()
                    
                    return f"""✅ تم إعطاء الدفعة للعميل بنجاح!

📋 التفاصيل:
- العميل: {customer.name}
- المبلغ المعطى: {amount} درهم
- السبب: {reason}
- الرصيد الجديد: {customer.balance} درهم
- الرقم: #{payment.id}

💡 تم إضافة المبلغ لرصيد العميل!

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        return None
        
    except Exception as e:
        try:
            LoggingCore.log_error(
                message=str(e) or "AI processing error",
                category="AI",
                level="ERROR",
                source="routes.ai._process_user_action",
                exception=e,
            )
        except Exception:
            pass
        return f"❌ خطأ في التنفيذ: {str(e)}"


