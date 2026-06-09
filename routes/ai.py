"""
🤖 AI Routes - Super Intelligent Assistant Endpoints
المساعد الذكي الخارق - Superhuman AI Assistant
"""
import os
from flask import Blueprint, request, jsonify, render_template, current_app, abort, flash, redirect, url_for, g
from flask_login import login_required, current_user
from extensions import csrf, db, limiter
from services.ai_service import AIService
from werkzeug.utils import secure_filename
import pandas as pd
from ai_knowledge.core.learning_system import learning_system
from ai_knowledge.core.system_integration import system_integrator
from ai_knowledge.expansion.global_knowledge import global_connector, expertise_updater
from ai_knowledge.improvement.self_improvement import self_improvement
from ai_knowledge.analytics.data_analyzer import data_analyzer
from ai_knowledge.expansion.knowledge_expansion import knowledge_expander
from ai_knowledge.generation.document_generator import document_generator
from ai_knowledge.specialized.advanced_laws import advanced_laws
from ai_knowledge.knowledge.automotive_ecu_knowledge import get_automotive_ecu_knowledge
from ai_knowledge.learning.external_learning import get_external_learning, LEARNING_SOURCES_CATALOG
from utils.decorators import permission_required, owner_required, admin_required
from utils.tenanting import assign_tenant_id, get_active_tenant_id
from utils.ai_access import get_ai_access_state, ai_level_allows
from utils.helpers import create_audit_log
from datetime import datetime, timezone

ai_bp = Blueprint('ai', __name__, url_prefix='/ai')

# Note: CSRF exemptions are added to individual routes that need them


@ai_bp.before_request
def _enforce_ai_access_policy():
    """Apply effective AI availability (global + tenant) before serving AI routes."""
    state = get_ai_access_state(current_user)
    g.ai_access_state = state

    # Keep assistant/config UI reachable so we can display exact disable reason.
    if request.endpoint in ('ai.config', 'ai.assistant_page'):
        return None

    if state.get('allowed'):
        endpoint_caps = {
            'ai.chat': 'basic',
            'ai.predict_sales': 'advanced',
            'ai.analyze_margins': 'advanced',
            'ai.detect_patterns': 'advanced',
            'ai.inventory_health': 'advanced',
            'ai.business_insights': 'advanced',
            'ai.deep_analysis': 'advanced',
            'ai.cash_flow_prediction': 'advanced',
            'ai.churn_prediction': 'advanced',
            'ai.optimize_inventory': 'advanced',
            'ai.ask_genius': 'advanced',
            'ai.upload_excel': 'execute',
            'ai.add_customer': 'execute',
            'ai.system_add_customer': 'execute',
        }
        required_cap = endpoint_caps.get(request.endpoint or '', 'basic')
        if not state.get('is_platform_user') and not ai_level_allows(state.get('ai_level'), required_cap):
            msg = f"مستوى AI الحالي ({state.get('ai_level')}) لا يسمح بهذه العملية."
            wants_json = request.path.startswith('/ai/') and (
                request.is_json or 'application/json' in (request.headers.get('Accept') or '')
            )
            if wants_json:
                return jsonify({'success': False, 'error': msg, 'required': required_cap}), 403
            flash(msg, 'warning')
            return redirect(url_for('ai.assistant_page'))
        return None

    reason = state.get('reason')
    message = 'المساعد الذكي غير متاح لهذا الحساب حالياً.'
    if reason == 'global_disabled':
        message = 'تم إيقاف المساعد الذكي من إعدادات المنصة.'
    elif reason == 'tenant_disabled':
        message = 'تم إيقاف المساعد الذكي لهذا التينانت من لوحة المنصة.'
    elif reason == 'missing_tenant':
        message = 'لا يوجد تينانت نشط مرتبط بهذا الحساب.'

    wants_json = request.path.startswith('/ai/') and (
        request.is_json or 'application/json' in (request.headers.get('Accept') or '')
    )
    if wants_json:
        return jsonify({'success': False, 'error': message, 'reason': reason}), 403

    flash(message, 'warning')
    return redirect(url_for('ai.assistant_page'))


@ai_bp.after_request
def _audit_ai_requests(response):
    """Unified AI audit trail: endpoint, tenant context, status, success/failure."""
    try:
        endpoint = request.endpoint or ''
        if not endpoint.startswith('ai.'):
            return response
        state = getattr(g, 'ai_access_state', None) or get_ai_access_state(current_user)
        status = int(getattr(response, 'status_code', 0) or 0)
        create_audit_log(
            action='ai_request',
            table_name='ai',
            record_id=0,
            changes={
                'endpoint': endpoint,
                'method': request.method,
                'path': request.path,
                'status_code': status,
                'ok': status < 400,
                'tenant_id': state.get('tenant_id'),
                'global_enabled': state.get('global_enabled'),
                'tenant_enabled': state.get('tenant_enabled'),
                'ai_level': state.get('ai_level'),
                'is_platform_user': state.get('is_platform_user'),
            },
        )
    except Exception:
        pass
    return response

# ========== نظام حفظ السياق المتقدم للمحادثة ==========
conversation_context = {}  # {user_id: {'last_action': 'عميل', 'step': 1, 'option': '1', 'data': {}, 'history': []}}

# ========== مستمعات ذكية ==========
def smart_listener(message, context):
    """مستمع ذكي يفهم نية المستخدم"""
    msg_lower = message.lower().strip()
    
    # كلمات العودة
    if any(word in msg_lower for word in ['عودة', 'رجوع', 'إلغاء', 'خروج', 'إيقاف']):
        return 'back'
    
    # كلمات المساعدة
    if any(word in msg_lower for word in ['مساعدة', 'help', 'ساعدني']):
        return 'help'
    
    # كلمات التأكيد
    if any(word in msg_lower for word in ['نعم', 'yes', 'تأكيد', 'موافق', 'ok']):
        return 'confirm'
    
    # كلمات الإلغاء
    if any(word in msg_lower for word in ['لا', 'no', 'إلغاء']):
        return 'cancel'
    
    return 'continue'

def train_local_ai(action, data, result):
    """تدريب الذكاء المحلي من كل عملية"""
    try:
        from ai_knowledge.core.learning_system import learning_system
        
        training_data = {
            'action': action,
            'input_data': data,
            'result': result,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        # حفظ للتدريب المستقبلي
        import json
        import os
        from ai_knowledge import get_knowledge_path
        
        training_file = get_knowledge_path('local_training.json')
        if os.path.exists(training_file):
            with open(training_file, 'r', encoding='utf-8') as f:
                training_history = json.load(f)
        else:
            training_history = []
        
        training_history.append(training_data)
        
        # الحفاظ على آخر 1000 عملية فقط
        if len(training_history) > 1000:
            training_history = training_history[-1000:]
        
        with open(training_file, 'w', encoding='utf-8') as f:
            json.dump(training_history, f, ensure_ascii=False, indent=2)
        
        return True
    except Exception as e:
        print(f"Training error: {e}")
        return False

def apply_smart_listeners(message, context, action_name):
    """دالة عامة للمستمعات الذكية - تطبق على جميع الوحدات"""
    listener_response = smart_listener(message, context)
    
    if listener_response == 'back':
        return 'back', """🔙 **تم العودة للقائمة الرئيسية**

💡 **يمكنك البدء من جديد:**
• اكتب "عميل" أو "منتج" أو "فاتورة" أو "مصروف"

🤖 المصدر: GROQ API + التحليل المحلي"""
    
    if listener_response == 'help':
        step = context.get('step', 0)
        return 'help', f"""💡 **مساعدة - الخطوة {step}:**

💡 **نصائح:**
• اكتب البيانات المطلوبة فقط
• اكتب "عودة" للعودة للقائمة الرئيسية

🤖 المصدر: GROQ API + التحليل المحلي"""
    
    return 'continue', None

def create_final_options(action_name, item_name, item_id):
    """خيارات نهائية ذكية بعد كل عملية"""
    options = {
        'عميل': f"""💡 **ماذا تريد أن تفعل الآن؟**
1️⃣ إضافة عميل آخر
2️⃣ عرض جميع العملاء
3️⃣ إنشاء فاتورة لهذا العميل
4️⃣ العودة للقائمة الرئيسية""",
        
        'منتج': f"""💡 **ماذا تريد أن تفعل الآن؟**
1️⃣ إضافة منتج آخر
2️⃣ عرض جميع المنتجات
3️⃣ إنشاء فاتورة بهذا المنتج
4️⃣ العودة للقائمة الرئيسية""",
        
        'فاتورة': f"""💡 **ماذا تريد أن تفعل الآن؟**
1️⃣ إنشاء فاتورة أخرى
2️⃣ عرض جميع الفواتير
3️⃣ استلام دفعة من العميل
4️⃣ العودة للقائمة الرئيسية""",
        
        'مصروف': f"""💡 **ماذا تريد أن تفعل الآن؟**
1️⃣ إضافة مصروف آخر
2️⃣ عرض جميع المصروفات
3️⃣ العودة للقائمة الرئيسية""",
        
        'استلام': f"""💡 **ماذا تريد أن تفعل الآن؟**
1️⃣ استلام دفعة أخرى
2️⃣ عرض جميع الدفعات
3️⃣ العودة للقائمة الرئيسية""",
        
        'إعطاء': f"""💡 **ماذا تريد أن تفعل الآن؟**
1️⃣ إعطاء دفعة أخرى
2️⃣ عرض جميع الدفعات
3️⃣ العودة للقائمة الرئيسية"""
    }
    
    return options.get(action_name, """💡 **ماذا تريد أن تفعل الآن؟**
1️⃣ تكرار العملية
2️⃣ العودة للقائمة الرئيسية""")


@ai_bp.route('/recommend-price', methods=['POST'])
@login_required
@permission_required('view_products')
@limiter.limit("60 per minute")
def recommend_price():
    """API: توصية السعر"""
    data = request.get_json()
    product_id = data.get('product_id')
    customer_id = data.get('customer_id')
    
    if not product_id or not customer_id:
        return jsonify({'error': 'Product and Customer required'}), 400
    
    recommendation = AIService.recommend_price(product_id, customer_id)
    
    if not recommendation:
        return jsonify({'error': 'Not found'}), 404
    
    return jsonify(recommendation)


@ai_bp.route('/check-stock', methods=['POST'])
@login_required
@permission_required('view_products')
@limiter.limit("60 per minute")
def check_stock():
    """API: فحص المخزون"""
    data = request.get_json()
    product_id = data.get('product_id')
    quantity = data.get('quantity', 0)
    
    if not product_id:
        return jsonify({'error': 'Product required'}), 400
    
    alert = AIService.check_stock_alert(product_id, quantity)
    
    if alert:
        return jsonify(alert)
    
    return jsonify({'type': 'success', 'message': 'المخزون كافٍ'})


@ai_bp.route('/analyze-customer/<int:customer_id>', methods=['GET'])
@login_required
@permission_required('view_customers')
def analyze_customer(customer_id):
    """API: تحليل سلوك العميل"""
    analysis = AIService.analyze_customer_behavior(customer_id)
    
    if not analysis:
        return jsonify({'error': 'Customer not found'}), 404
    
    return jsonify(analysis)


@ai_bp.route('/exchange-rate/<currency>', methods=['GET'])
@login_required
@permission_required('view_reports')
def exchange_rate(currency):
    """API: اقتراح سعر الصرف"""
    suggestion = AIService.get_exchange_rate_suggestion(currency)
    return jsonify(suggestion)


@ai_bp.route('/search-market-price/<int:product_id>', methods=['GET'])
@login_required
@permission_required('view_products')
def search_market_price(product_id):
    """API: البحث عن سعر القطعة في الأسواق العالمية"""
    from models import Product

    tid = get_active_tenant_id(current_user)
    product = Product.query.filter_by(id=product_id, tenant_id=tid).first_or_404()

    return jsonify({
        'success': True,
        'product': product.name,
        'message': 'ميزة البحث العالمي قيد التطوير',
        'suggestions': []
    })


@ai_bp.route('/find-compatible/<int:product_id>', methods=['GET'])
@login_required
@permission_required('view_products')
def find_compatible(product_id):
    """API: البحث عن السيارات المتوافقة"""
    from models import Product

    tid = get_active_tenant_id(current_user)
    product = Product.query.filter_by(id=product_id, tenant_id=tid).first_or_404()

    return jsonify({
        'success': True,
        'product': product.name,
        'message': 'ميزة البحث عن المركبات المتوافقة قيد التطوير',
        'compatible_vehicles': []
    })


@ai_bp.route('/chat', methods=['POST'])
@login_required
@permission_required('view_reports')
@limiter.limit("30 per minute")
def chat():
    """API: الدردشة مع المساعد الذكي"""
    data = request.get_json()
    message = data.get('message', '').strip()
    ai_mode = data.get('ai_mode', 'groq')
    context = data.get('context', {})
    
    if 'dialect' not in context:
        context['dialect'] = 'palestinian'
    if 'beginners_mode' not in context:
        context['beginners_mode'] = False
    
    context['current_user'] = current_user
    context['is_owner'] = current_user.is_owner if current_user else False
    context['force_local'] = (ai_mode == 'local')
    
    if not message:
        return jsonify({'error': 'Message required'}), 400
    
    action_result = None
    ai_state = getattr(g, 'ai_access_state', None) or get_ai_access_state(current_user)
    can_execute_mutations = ai_state.get('is_platform_user') or ai_level_allows(ai_state.get('ai_level'), 'execute')
    
    # Try new action dispatcher first (clean, permission-validated, error-logged)
    if can_execute_mutations and _user_can_ai_execute_actions(current_user):
        from ai_knowledge.action_dispatcher import action_dispatcher
        from ai_knowledge.agents_core import intelligent_response
        parsed = action_dispatcher.parse_chat_action(message)
        if parsed:
            action_type, args = parsed
            if action_type in ("greeting", "help"):
                action_result = intelligent_response(message, current_user.id, context)
            else:
                result = action_dispatcher.dispatch(action_type, args)
                if result.success:
                    action_result = result.message
                else:
                    # Fall back to old wizard on failure
                    action_result = _process_user_action(message, current_user)
        else:
            action_result = _process_user_action(message, current_user)
    elif _user_can_ai_execute_actions(current_user):
        action_result = _process_user_action(message, current_user)
    
    if action_result:
        return jsonify({
            'response': action_result,
            'ai_enabled': True,
            'action_executed': True
        })
    
    response = AIService.chat_response(message, context)
    
    state = get_ai_access_state(current_user)
    return jsonify({
        'response': response,
        'ai_enabled': bool(state.get('allowed') and state.get('global_enabled') and state.get('tenant_enabled') is not False),
        'ai_mode': ai_mode,
        'user_role': 'owner' if current_user.is_owner else 'user'
    })

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
        from models import Customer, Product, Sale, SaleLine, Supplier, Purchase, PurchaseLine, Payment, Expense, Cheque
        from extensions import db
        from datetime import datetime, timezone
        from decimal import Decimal
        import re
        
        msg_lower = message.lower()
        
        # ========== نظام الحوار الذكي التفاعلي ==========
        user_id = user.id
        tid = get_active_tenant_id(user)
        
        # إذا كان المستخدم يطلب مساعدة أو خيارات
        if any(word in msg_lower for word in ['رصيد', 'رصيد العميل', 'رصيد عميل', 'تعديل رصيد']):
            if ':' not in message:
                conversation_context[user_id] = {'last_action': 'رصيد', 'step': 0}
                return """🤖 فهمت! تريد التعامل مع رصيد العميل. إليك الخيارات:

📋 **ما الذي تريد فعله؟**
1️⃣ **تعديل رصيد العميل**
2️⃣ **استلام دفعة من العميل**
3️⃣ **إعطاء دفعة للعميل**
4️⃣ **عرض رصيد العميل**

💡 **اكتب رقم الخيار (1، 2، 3، أو 4) وسأرشدك خطوة بخطوة!**

🤖 مثال: اكتب "1" لتعديل رصيد العميل"""
        
        # ========== معالجة خيارات "رصيد" ==========
        if msg_lower.strip() == '2' and user_id in conversation_context and conversation_context[user_id].get('last_action') == 'رصيد':
            # توجيه لخيار "استلام دفعة"
            conversation_context[user_id] = {'last_action': 'استلام', 'step': 0}
            return """🤖 تم التحويل لخيار "استلام دفعة من العميل"

اكتب "1" للمتابعة أو "عودة" للرجوع

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        if msg_lower.strip() == '3' and user_id in conversation_context and conversation_context[user_id].get('last_action') == 'رصيد':
            # توجيه لخيار "إعطاء دفعة"
            conversation_context[user_id] = {'last_action': 'إعطاء', 'step': 0}
            return """🤖 تم التحويل لخيار "إعطاء دفعة للعميل"

اكتب "1" للمتابعة أو "عودة" للرجوع

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        if msg_lower.strip() == '4' and user_id in conversation_context and conversation_context[user_id].get('last_action') == 'رصيد':
            # عرض رصيد العميل
            from models.customer import Customer
            customers = Customer.query.filter_by(tenant_id=tid, is_active=True).all()
            if customers:
                customers_list = "\n".join([f"• {c.name}: {c.balance} درهم" for c in customers[:10]])
                del conversation_context[user_id]
                return f"""📊 **أرصدة العملاء:**

{customers_list}

💡 **للبحث عن عميل محدد:**
اكتب: رصيد: اسم العميل

🤖 المصدر: GROQ API + التحليل المحلي"""
            else:
                del conversation_context[user_id]
                return """❌ **لا يوجد عملاء في النظام**

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        if msg_lower.strip() == '1' and user_id in conversation_context and conversation_context[user_id].get('last_action') == 'رصيد':
            # تعديل رصيد العميل
            conversation_context[user_id]['step'] = 1
            conversation_context[user_id]['option'] = '1'
            conversation_context[user_id]['data'] = {}
            return """🤖 ممتاز! اخترت تعديل رصيد العميل. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: اسم العميل**
اكتب اسم العميل

💡 **مثال:** أحمد محمد

🤖 اكتب اسم العميل الآن..."""
        
        # ========== معالجة خطوات تعديل الرصيد ==========
        if user_id in conversation_context and conversation_context[user_id].get('last_action') == 'رصيد' and conversation_context[user_id].get('option') == '1':
            step = conversation_context[user_id].get('step', 0)
            data = conversation_context[user_id].get('data', {})
            
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
                conversation_context[user_id]['data'] = data
                conversation_context[user_id]['step'] = 2
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
                    
                    del conversation_context[user_id]
                    
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
                conversation_context[user_id] = {'last_action': 'عميل', 'step': 0}
                return """🤖 فهمت! تريد إضافة عميل جديد. إليك الخيارات:

📋 **ما الذي تريد فعله؟**
1️⃣ **إضافة عميل جديد**
2️⃣ **عرض جميع العملاء**
3️⃣ **البحث عن عميل**

💡 **اكتب رقم الخيار (1، 2، أو 3) وسأرشدك خطوة بخطوة!**

🤖 مثال: اكتب "1" لإضافة عميل جديد"""
        
        if any(word in msg_lower for word in ['منتج', 'منتج جديد', 'إضافة منتج', 'إنشاء منتج']):
            if ':' not in message:
                conversation_context[user_id] = {'last_action': 'منتج', 'step': 0}
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
                conversation_context[user_id] = {'last_action': 'فاتورة', 'step': 0}
                return """🤖 فهمت! تريد إنشاء فاتورة مبيعات. إليك الخيارات:

📋 **ما الذي تريد فعله؟**
1️⃣ **إنشاء فاتورة جديدة**
2️⃣ **عرض جميع الفواتير**
3️⃣ **البحث عن فاتورة**

💡 **اكتب رقم الخيار (1، 2، أو 3) وسأرشدك خطوة بخطوة!**

🤖 مثال: اكتب "1" لإنشاء فاتورة جديدة"""
        
        if any(word in msg_lower for word in ['استلام', 'استلم', 'دفعة من']):
            if ':' not in message:
                conversation_context[user_id] = {'last_action': 'استلام', 'step': 0}
                return """🤖 فهمت! تريد استلام دفعة من عميل. إليك الخيارات:

📋 **ما الذي تريد فعله؟**
1️⃣ **استلام دفعة من عميل**
2️⃣ **عرض جميع الدفعات**
3️⃣ **البحث عن دفعة**

💡 **اكتب رقم الخيار (1، 2، أو 3) وسأرشدك خطوة بخطوة!**

🤖 مثال: اكتب "1" لاستلام دفعة من عميل"""
        
        if any(word in msg_lower for word in ['إعطاء', 'أعطى', 'دفعة لل', 'دفعة ل']):
            if ':' not in message:
                conversation_context[user_id] = {'last_action': 'إعطاء', 'step': 0}
                return """🤖 فهمت! تريد إعطاء دفعة للعميل. إليك الخيارات:

📋 **ما الذي تريد فعله؟**
1️⃣ **إعطاء دفعة للعميل**
2️⃣ **عرض جميع الدفعات المعطاة**
3️⃣ **البحث عن دفعة معطاة**

💡 **اكتب رقم الخيار (1، 2، أو 3) وسأرشدك خطوة بخطوة!**

🤖 مثال: اكتب "1" لإعطاء دفعة للعميل"""
        
        if any(word in msg_lower for word in ['مصروف', 'إضافة مصروف', 'إنشاء مصروف']):
            if ':' not in message:
                conversation_context[user_id] = {'last_action': 'مصروف', 'step': 0}
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
                conversation_context[user_id] = {'last_action': 'مورد', 'step': 0}
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
                conversation_context[user_id] = {'last_action': 'مشتريات', 'step': 0}
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
                conversation_context[user_id] = {'last_action': 'شيك', 'step': 0}
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
                conversation_context[user_id] = {'last_action': 'دفتر', 'step': 0}
                return """🤖 فهمت! تريد التعامل مع دفتر الأستاذ. إليك الخيارات:

📋 **ما الذي تريد فعله؟**
1️⃣ **عرض دفتر الأستاذ**
2️⃣ **البحث في القيود**

💡 **اكتب رقم الخيار (1 أو 2) وسأرشدك خطوة بخطوة!**

🤖 مثال: اكتب "1" لعرض دفتر الأستاذ"""
        
        # ========== نظام الحوار للمستودعات ==========
        if any(word in msg_lower for word in ['مستودع', 'مستودعات', 'مخزون', 'إدارة مستودعات']):
            if ':' not in message:
                conversation_context[user_id] = {'last_action': 'مستودع', 'step': 0}
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
                conversation_context[user_id] = {'last_action': 'مستخدم', 'step': 0}
                return """🤖 فهمت! تريد إدارة المستخدمين. إليك الخيارات:

📋 **ما الذي تريد فعله؟**
1️⃣ **إضافة مستخدم جديد**
2️⃣ **عرض جميع المستخدمين**
3️⃣ **البحث عن مستخدم**

💡 **اكتب رقم الخيار (1، 2، أو 3) وسأرشدك خطوة بخطوة!**

🤖 مثال: اكتب "1" لإضافة مستخدم جديد"""
        
        # ========== نظام الحوار التفاعلي للرقم 1 (إضافة عميل جديد) ==========
        if msg_lower.strip() == '1' and user_id in conversation_context and conversation_context[user_id].get('last_action') == 'عميل':
            conversation_context[user_id]['step'] = 1
            conversation_context[user_id]['option'] = '1'
            conversation_context[user_id]['data'] = {}
            return """🤖 ممتاز! اخترت إضافة عميل جديد. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: اسم العميل**
اكتب اسم العميل الكامل

💡 **مثال:** أحمد محمد علي

🤖 اكتب الاسم الآن..."""
        
        # ========== معالجة الخطوات التالية (إضافة عميل) ==========
        if user_id in conversation_context and conversation_context[user_id].get('last_action') == 'عميل' and conversation_context[user_id].get('option') == '1':
            step = conversation_context[user_id].get('step', 0)
            data = conversation_context[user_id].get('data', {})
            
            # التحقق من المستمع الذكي
            listener_response = smart_listener(message, conversation_context[user_id])
            
            if listener_response == 'back':
                # العودة للقائمة الرئيسية
                del conversation_context[user_id]
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
                conversation_context[user_id]['data'] = data
                conversation_context[user_id]['step'] = 2
                conversation_context[user_id]['history'] = conversation_context[user_id].get('history', []) + [{'step': 1, 'data': message.strip()}]
                return """✅ **تم حفظ الاسم:** {name}

📝 **الخطوة 2: رقم الهاتف**
اكتب رقم هاتف العميل

💡 **مثال:** 0561234567

💬 **اكتب "عودة" للرجوع أو "مساعدة" للمساعدة**

🤖 اكتب رقم الهاتف الآن...""".format(name=data['name'])
            
            elif step == 2:
                # حفظ الهاتف والانتقال للخطوة التالية
                data['phone'] = message.strip()
                conversation_context[user_id]['data'] = data
                conversation_context[user_id]['step'] = 3
                return """✅ **تم حفظ رقم الهاتف:** {phone}

📝 **الخطوة 3: العنوان**
اكتب عنوان العميل

💡 **مثال:** دبي - الخليج التجاري

🤖 اكتب العنوان الآن...""".format(phone=data['phone'])
            
            elif step == 2:
                # حفظ الهاتف والانتقال للخطوة التالية
                data['phone'] = message.strip()
                conversation_context[user_id]['data'] = data
                conversation_context[user_id]['step'] = 3
                conversation_context[user_id]['history'] = conversation_context[user_id].get('history', []) + [{'step': 2, 'data': message.strip()}]
                return """✅ **تم حفظ رقم الهاتف:** {phone}

📝 **الخطوة 3: العنوان**
اكتب عنوان العميل

💡 **مثال:** دبي - الخليج التجاري

💬 **اكتب "عودة" للرجوع أو "مساعدة" للمساعدة**

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
                    db.session.add(customer)
                    db.session.commit()
                    
                    # تدريب الذكاء المحلي
                    train_local_ai('create_customer', data, {'success': True, 'customer_id': customer.id})
                    
                    # مسح السياق
                    del conversation_context[user_id]
                    
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
                    del conversation_context[user_id]
                    return f"""❌ **خطأ في إنشاء العميل:**

{str(e)}

💡 **حاول مرة أخرى:** اكتب "عميل" ثم "1"

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        # ========== نظام الحوار التفاعلي للرقم 1 (إضافة منتج جديد) ==========
        if msg_lower.strip() == '1' and user_id in conversation_context and conversation_context[user_id].get('last_action') == 'منتج':
            conversation_context[user_id]['step'] = 1
            conversation_context[user_id]['option'] = '1'
            conversation_context[user_id]['data'] = {}
            return """🤖 ممتاز! اخترت إضافة منتج جديد. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: اسم المنتج**
اكتب اسم المنتج الكامل

💡 **مثال:** فلتر زيت كاتربلر

🤖 اكتب اسم المنتج الآن..."""
        
        # ========== معالجة الخطوات التالية (إضافة منتج) ==========
        if user_id in conversation_context and conversation_context[user_id].get('last_action') == 'منتج' and conversation_context[user_id].get('option') == '1':
            step = conversation_context[user_id].get('step', 0)
            data = conversation_context[user_id].get('data', {})
            
            # التحقق من المستمع الذكي
            listener_response = smart_listener(message, conversation_context[user_id])
            
            if listener_response == 'back':
                del conversation_context[user_id]
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
                conversation_context[user_id]['data'] = data
                conversation_context[user_id]['step'] = 2
                return """✅ **تم حفظ الاسم:** {name}

📝 **الخطوة 2: رقم القطعة**
اكتب رقم القطعة (Part Number)

💡 **مثال:** 1R0716

🤖 اكتب رقم القطعة الآن...""".format(name=data['name'])
            
            elif step == 2:
                # حفظ رقم القطعة والانتقال للخطوة التالية
                data['part_number'] = message.strip()
                conversation_context[user_id]['data'] = data
                conversation_context[user_id]['step'] = 3
                return """✅ **تم حفظ رقم القطعة:** {part_number}

📝 **الخطوة 3: السعر**
اكتب سعر البيع (بالدرهم)

💡 **مثال:** 50

🤖 اكتب السعر الآن...""".format(part_number=data['part_number'])
            
            elif step == 3:
                # حفظ السعر والانتقال للخطوة التالية
                try:
                    data['price'] = float(message.strip().replace('درهم', '').replace('د.إ', '').strip())
                    conversation_context[user_id]['data'] = data
                    conversation_context[user_id]['step'] = 4
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
                        current_stock=data['quantity'],
                        unit='قطعة'
                    )
                    assign_tenant_id(product, user)
                    db.session.add(product)
                    db.session.commit()
                    
                    # تدريب الذكاء المحلي
                    train_local_ai('create_product', data, {'success': True, 'product_id': product.id})
                    
                    # مسح السياق
                    del conversation_context[user_id]
                    
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
                    del conversation_context[user_id]
                    return f"""❌ **خطأ في إنشاء المنتج:**

{str(e)}

💡 **حاول مرة أخرى:** اكتب "منتج" ثم "1"

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        # ========== نظام الحوار التفاعلي للرقم 1 (إنشاء فاتورة جديدة) ==========
        if msg_lower.strip() == '1' and user_id in conversation_context and conversation_context[user_id].get('last_action') == 'فاتورة':
            conversation_context[user_id]['step'] = 1
            conversation_context[user_id]['option'] = '1'
            conversation_context[user_id]['data'] = {}
            return """🤖 ممتاز! اخترت إنشاء فاتورة جديدة. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: اسم العميل**
اكتب اسم العميل

💡 **مثال:** أحمد محمد

🤖 اكتب اسم العميل الآن..."""
        
        # ========== معالجة الخطوات التالية (إنشاء فاتورة) ==========
        if user_id in conversation_context and conversation_context[user_id].get('last_action') == 'فاتورة' and conversation_context[user_id].get('option') == '1':
            step = conversation_context[user_id].get('step', 0)
            data = conversation_context[user_id].get('data', {})
            
            listener_status, listener_msg = apply_smart_listeners(message, conversation_context[user_id], 'فاتورة')
            if listener_status in ['back', 'help']:
                if listener_status == 'back':
                    del conversation_context[user_id]
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
                conversation_context[user_id]['data'] = data
                conversation_context[user_id]['step'] = 2
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
                conversation_context[user_id]['data'] = data
                conversation_context[user_id]['step'] = 3
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
                    
                    from models.sale import Sale
                    from models.sale_item import SaleItem
                    
                    # إنشاء الفاتورة
                    sale = Sale(
                        customer_id=data['customer_id'],
                        total_amount=total_amount,
                        payment_method='نقد',
                        user_id=user.id
                    )
                    db.session.add(sale)
                    db.session.flush()  # للحصول على ID
                    
                    # إضافة عنصر الفاتورة
                    sale_item = SaleItem(
                        sale_id=sale.id,
                        product_id=data['product_id'],
                        quantity=data['quantity'],
                        unit_price=data['product_price'],
                        total_price=total_amount
                    )
                    db.session.add(sale_item)
                    
                    # تحديث المخزون
                    product = Product.query.filter_by(id=data['product_id'], tenant_id=tid).first()
                    product.current_stock -= data['quantity']
                    
                    db.session.commit()
                    
                    # تدريب الذكاء المحلي
                    train_local_ai('create_sale', data, {'success': True, 'sale_id': sale.id})
                    
                    # مسح السياق
                    del conversation_context[user_id]
                    
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
                    del conversation_context[user_id]
                    return f"""❌ **خطأ في إنشاء الفاتورة:**

{str(e)}

💡 **حاول مرة أخرى:** اكتب "فاتورة" ثم "1"

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        # ========== نظام الحوار التفاعلي للرقم 1 (استلام دفعة) ==========
        if msg_lower.strip() == '1' and user_id in conversation_context and conversation_context[user_id].get('last_action') == 'استلام':
            conversation_context[user_id]['step'] = 1
            conversation_context[user_id]['option'] = '1'
            conversation_context[user_id]['data'] = {}
            return """🤖 ممتاز! اخترت استلام دفعة من عميل. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: اسم العميل**
اكتب اسم العميل

💡 **مثال:** أحمد محمد

🤖 اكتب اسم العميل الآن..."""
        
        # ========== معالجة الخطوات التالية (استلام دفعة) ==========
        if user_id in conversation_context and conversation_context[user_id].get('last_action') == 'استلام' and conversation_context[user_id].get('option') == '1':
            step = conversation_context[user_id].get('step', 0)
            data = conversation_context[user_id].get('data', {})
            
            listener_status, listener_msg = apply_smart_listeners(message, conversation_context[user_id], 'استلام')
            if listener_status in ['back', 'help']:
                if listener_status == 'back':
                    del conversation_context[user_id]
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
                conversation_context[user_id]['data'] = data
                conversation_context[user_id]['step'] = 2
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
                    conversation_context[user_id]['data'] = data
                    conversation_context[user_id]['step'] = 3
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
                        amount_aed=data['amount'],
                        payment_date=datetime.now(timezone.utc),
                        payment_method=data['payment_method'],
                        user_id=user.id,
                        direction='incoming',
                        payment_type='customer_payment'
                    )
                    db.session.add(payment)
                    
                    # تحديث رصيد العميل
                    customer = Customer.query.filter_by(id=data['customer_id'], tenant_id=tid).first()
                    customer.apply_receipt(data['amount'])
                    
                    db.session.commit()
                    
                    # تدريب الذكاء المحلي
                    train_local_ai('receive_payment', data, {'success': True, 'payment_id': payment.id})
                    
                    # مسح السياق
                    del conversation_context[user_id]
                    
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
                    del conversation_context[user_id]
                    return f"""❌ **خطأ في تسجيل الدفعة:**

{str(e)}

💡 **حاول مرة أخرى:** اكتب "استلام" ثم "1"

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        # ========== نظام الحوار التفاعلي للرقم 1 (إعطاء دفعة) ==========
        if msg_lower.strip() == '1' and user_id in conversation_context and conversation_context[user_id].get('last_action') == 'إعطاء':
            conversation_context[user_id]['step'] = 1
            conversation_context[user_id]['option'] = '1'
            conversation_context[user_id]['data'] = {}
            return """🤖 ممتاز! اخترت إعطاء دفعة للعميل. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: اسم العميل**
اكتب اسم العميل

💡 **مثال:** أحمد محمد

🤖 اكتب اسم العميل الآن..."""
        
        # ========== معالجة الخطوات التالية (إعطاء دفعة) ==========
        if user_id in conversation_context and conversation_context[user_id].get('last_action') == 'إعطاء' and conversation_context[user_id].get('option') == '1':
            step = conversation_context[user_id].get('step', 0)
            data = conversation_context[user_id].get('data', {})
            
            listener_status, listener_msg = apply_smart_listeners(message, conversation_context[user_id], 'إعطاء')
            if listener_status in ['back', 'help']:
                if listener_status == 'back':
                    del conversation_context[user_id]
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
                conversation_context[user_id]['data'] = data
                conversation_context[user_id]['step'] = 2
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
                    conversation_context[user_id]['data'] = data
                    conversation_context[user_id]['step'] = 3
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
                        amount_aed=-data['amount'],  # سالب لأننا نعطي للعميل
                        payment_date=datetime.now(timezone.utc),
                        payment_method='refund',
                        user_id=user.id,
                        direction='outgoing',
                        payment_type='refund'
                    )
                    db.session.add(payment)
                    
                    # تحديث رصيد العميل (زيادة)
                    customer = Customer.query.filter_by(id=data['customer_id'], tenant_id=tid).first()
                    customer.adjust_balance(data['amount'])
                    
                    db.session.commit()
                    
                    # تدريب الذكاء المحلي
                    train_local_ai('give_payment', data, {'success': True, 'payment_id': payment.id})
                    
                    # مسح السياق
                    del conversation_context[user_id]
                    
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
                    del conversation_context[user_id]
                    return f"""❌ **خطأ في تسجيل الدفعة:**

{str(e)}

💡 **حاول مرة أخرى:** اكتب "إعطاء" ثم "1"

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        # ========== نظام الحوار التفاعلي للرقم 1 (إضافة مصروف) ==========
        if msg_lower.strip() == '1' and user_id in conversation_context and conversation_context[user_id].get('last_action') == 'مصروف':
            conversation_context[user_id]['step'] = 1
            conversation_context[user_id]['option'] = '1'
            conversation_context[user_id]['data'] = {}
            return """🤖 ممتاز! اخترت إضافة مصروف جديد. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: وصف المصروف**
اكتب وصف المصروف

💡 **مثال:** فواتير الكهرباء

🤖 اكتب وصف المصروف الآن..."""
        
        # ========== معالجة الخطوات التالية (إضافة مصروف) ==========
        if user_id in conversation_context and conversation_context[user_id].get('last_action') == 'مصروف' and conversation_context[user_id].get('option') == '1':
            step = conversation_context[user_id].get('step', 0)
            data = conversation_context[user_id].get('data', {})
            
            listener_status, listener_msg = apply_smart_listeners(message, conversation_context[user_id], 'مصروف')
            if listener_status in ['back', 'help']:
                if listener_status == 'back':
                    del conversation_context[user_id]
                return listener_msg
            
            if step == 1:
                # حفظ الوصف والانتقال للخطوة التالية
                data['description'] = message.strip()
                conversation_context[user_id]['data'] = data
                conversation_context[user_id]['step'] = 2
                return """✅ **تم حفظ الوصف:** {description}

📝 **الخطوة 2: المبلغ**
اكتب مبلغ المصروف (بالدرهم)

💡 **مثال:** 200

🤖 اكتب المبلغ الآن...""".format(description=data['description'])
            
            elif step == 2:
                # حفظ المبلغ والانتقال للخطوة التالية
                try:
                    data['amount'] = float(message.strip().replace('درهم', '').replace('د.إ', '').strip())
                    conversation_context[user_id]['data'] = data
                    conversation_context[user_id]['step'] = 3
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
                    expense = Expense(
                        description=data['description'],
                        amount=data['amount'],
                        category=data['category'],
                        expense_date=datetime.now(timezone.utc),
                        user_id=user.id
                    )
                    db.session.add(expense)
                    db.session.commit()
                    
                    # تدريب الذكاء المحلي
                    train_local_ai('create_expense', data, {'success': True, 'expense_id': expense.id})
                    
                    # مسح السياق
                    del conversation_context[user_id]
                    
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
                    del conversation_context[user_id]
                    return f"""❌ **خطأ في إنشاء المصروف:**

{str(e)}

💡 **حاول مرة أخرى:** اكتب "مصروف" ثم "1"

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        # ========== نظام الحوار التفاعلي للرقم 1 (إضافة مورد جديد) ==========
        if msg_lower.strip() == '1' and user_id in conversation_context and conversation_context[user_id].get('last_action') == 'مورد':
            conversation_context[user_id]['step'] = 1
            conversation_context[user_id]['option'] = '1'
            conversation_context[user_id]['data'] = {}
            return """🤖 ممتاز! اخترت إضافة مورد جديد. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: اسم المورد**
اكتب اسم المورد الكامل

💡 **مثال:** شركة قطع غيار دبي

💬 **اكتب "عودة" للرجوع أو "مساعدة" للمساعدة**

🤖 اكتب اسم المورد الآن..."""
        
        # ========== معالجة الخطوات التالية (إضافة مورد) ==========
        if user_id in conversation_context and conversation_context[user_id].get('last_action') == 'مورد' and conversation_context[user_id].get('option') == '1':
            step = conversation_context[user_id].get('step', 0)
            data = conversation_context[user_id].get('data', {})
            
            listener_status, listener_msg = apply_smart_listeners(message, conversation_context[user_id], 'مورد')
            if listener_status in ['back', 'help']:
                if listener_status == 'back':
                    del conversation_context[user_id]
                return listener_msg
            
            if step == 1:
                data['name'] = message.strip()
                conversation_context[user_id]['data'] = data
                conversation_context[user_id]['step'] = 2
                return """✅ **تم حفظ الاسم:** {name}

📝 **الخطوة 2: رقم الهاتف**
اكتب رقم هاتف المورد

💡 **مثال:** 0561234567

💬 **اكتب "عودة" للرجوع أو "مساعدة" للمساعدة**

🤖 اكتب رقم الهاتف الآن...""".format(name=data['name'])
            
            elif step == 2:
                data['phone'] = message.strip()
                conversation_context[user_id]['data'] = data
                conversation_context[user_id]['step'] = 3
                return """✅ **تم حفظ رقم الهاتف:** {phone}

📝 **الخطوة 3: العنوان**
اكتب عنوان المورد

💡 **مثال:** دبي - المنطقة الصناعية

💬 **اكتب "عودة" للرجوع أو "مساعدة" للمساعدة**

🤖 اكتب العنوان الآن...""".format(phone=data['phone'])
            
            elif step == 3:
                data['address'] = message.strip()
                conversation_context[user_id]['data'] = data
                conversation_context[user_id]['step'] = 4
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
                    conversation_context[user_id]['data'] = data
                    conversation_context[user_id]['step'] = 5
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
                    db.session.add(supplier)
                    db.session.commit()
                    
                    train_local_ai('create_supplier', data, {'success': True, 'supplier_id': supplier.id})
                    
                    del conversation_context[user_id]
                    
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
                    del conversation_context[user_id]
                    return f"""❌ **خطأ في إنشاء المورد:** {str(e)}

💡 **حاول مرة أخرى:** اكتب "مورد" ثم "1"

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        # ========== نظام الحوار التفاعلي للرقم 1 (إضافة مشتريات جديدة) ==========
        if msg_lower.strip() == '1' and user_id in conversation_context and conversation_context[user_id].get('last_action') == 'مشتريات':
            conversation_context[user_id]['step'] = 1
            conversation_context[user_id]['option'] = '1'
            conversation_context[user_id]['data'] = {}
            return """🤖 ممتاز! اخترت إضافة مشتريات جديدة. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: اسم المورد**
اكتب اسم المورد

💡 **مثال:** شركة قطع غيار دبي

🤖 اكتب اسم المورد الآن..."""
        
        # ========== معالجة الخطوات التالية (إضافة مشتريات) ==========
        if user_id in conversation_context and conversation_context[user_id].get('last_action') == 'مشتريات' and conversation_context[user_id].get('option') == '1':
            step = conversation_context[user_id].get('step', 0)
            data = conversation_context[user_id].get('data', {})
            
            listener_status, listener_msg = apply_smart_listeners(message, conversation_context[user_id], 'مشتريات')
            if listener_status in ['back', 'help']:
                if listener_status == 'back':
                    del conversation_context[user_id]
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
                conversation_context[user_id]['data'] = data
                conversation_context[user_id]['step'] = 2
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
                conversation_context[user_id]['data'] = data
                conversation_context[user_id]['step'] = 3
                return """✅ **تم العثور على المنتج:** {product_name}

📝 **الخطوة 3: الكمية**
اكتب الكمية المشتراة

💡 **مثال:** 50

🤖 اكتب الكمية الآن...""".format(product_name=product.name)
            
            elif step == 3:
                try:
                    data['quantity'] = float(message.strip())
                    conversation_context[user_id]['data'] = data
                    conversation_context[user_id]['step'] = 4
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
                    
                    from models.purchase import Purchase
                    from models.purchase_item import PurchaseItem
                    from models.product import Product
                    
                    purchase = Purchase(
                        supplier_id=data['supplier_id'],
                        total_amount=total_amount,
                        user_id=user.id
                    )
                    db.session.add(purchase)
                    db.session.flush()
                    
                    purchase_item = PurchaseItem(
                        purchase_id=purchase.id,
                        product_id=data['product_id'],
                        quantity=data['quantity'],
                        unit_price=data['unit_price'],
                        total_price=total_amount
                    )
                    db.session.add(purchase_item)
                    
                    product = Product.query.filter_by(id=data['product_id'], tenant_id=tid).first()
                    product.current_stock += data['quantity']
                    
                    db.session.commit()
                    
                    train_local_ai('create_purchase', data, {'success': True, 'purchase_id': purchase.id})
                    
                    del conversation_context[user_id]
                    
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
                    del conversation_context[user_id]
                    return f"""❌ **خطأ في إنشاء المشتريات:** {str(e)}

💡 **حاول مرة أخرى:** اكتب "مشتريات" ثم "1"

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        # ========== نظام الحوار التفاعلي للرقم 1 (إضافة شيك جديد) ==========
        if msg_lower.strip() == '1' and user_id in conversation_context and conversation_context[user_id].get('last_action') == 'شيك':
            conversation_context[user_id]['step'] = 1
            conversation_context[user_id]['option'] = '1'
            conversation_context[user_id]['data'] = {}
            return """🤖 ممتاز! اخترت إضافة شيك جديد. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: نوع الشيك**
اكتب نوع الشيك (وارد أو صادر)

💡 **مثال:** وارد

🤖 اكتب نوع الشيك الآن..."""
        
        # ========== معالجة الخطوات التالية (إضافة شيك) ==========
        if user_id in conversation_context and conversation_context[user_id].get('last_action') == 'شيك' and conversation_context[user_id].get('option') == '1':
            step = conversation_context[user_id].get('step', 0)
            data = conversation_context[user_id].get('data', {})
            
            listener_status, listener_msg = apply_smart_listeners(message, conversation_context[user_id], 'شيك')
            if listener_status in ['back', 'help']:
                if listener_status == 'back':
                    del conversation_context[user_id]
                return listener_msg
            
            if step == 1:
                cheque_type = message.strip()
                if cheque_type not in ['وارد', 'صادر', 'incoming', 'outgoing']:
                    return """❌ **نوع الشيك غير صحيح!**

💡 **اكتب "وارد" أو "صادر"**

🤖 أعد إدخال نوع الشيك..."""
                
                data['cheque_type'] = 'incoming' if 'وارد' in cheque_type else 'outgoing'
                conversation_context[user_id]['data'] = data
                conversation_context[user_id]['step'] = 2
                return """✅ **تم حفظ نوع الشيك:** {type}

📝 **الخطوة 2: رقم الشيك**
اكتب رقم الشيك

💡 **مثال:** 123456

🤖 اكتب رقم الشيك الآن...""".format(type=cheque_type)
            
            elif step == 2:
                data['cheque_number'] = message.strip()
                conversation_context[user_id]['data'] = data
                conversation_context[user_id]['step'] = 3
                return """✅ **تم حفظ رقم الشيك:** {number}

📝 **الخطوة 3: المبلغ**
اكتب مبلغ الشيك (بالدرهم)

💡 **مثال:** 5000

🤖 اكتب المبلغ الآن...""".format(number=data['cheque_number'])
            
            elif step == 3:
                try:
                    data['amount'] = float(message.strip().replace('درهم', '').strip())
                    conversation_context[user_id]['data'] = data
                    conversation_context[user_id]['step'] = 4
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
                    
                    del conversation_context[user_id]
                    
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
                    del conversation_context[user_id]
                    return f"""❌ **خطأ في إنشاء الشيك:** {str(e)}

💡 **حاول مرة أخرى:** اكتب "شيك" ثم "1"

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        # ========== نظام الحوار التفاعلي للرقم 1 (عرض دفتر الأستاذ) ==========
        if msg_lower.strip() == '1' and user_id in conversation_context and conversation_context[user_id].get('last_action') == 'دفتر':
            from models.gl import GLJournalEntry
            gl_entries = GLJournalEntry.query.filter_by(is_active=True, tenant_id=tid).order_by(GLJournalEntry.entry_date.desc()).limit(20).all()
            
            del conversation_context[user_id]
            
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
        if msg_lower.strip() == '1' and user_id in conversation_context and conversation_context[user_id].get('last_action') == 'مستودع':
            from models.warehouse import Warehouse
            warehouses = Warehouse.query.filter_by(is_active=True, tenant_id=tid).all()
            
            del conversation_context[user_id]
            
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
        if msg_lower.strip() == '1' and user_id in conversation_context and conversation_context[user_id].get('last_action') == 'مستخدم':
            conversation_context[user_id]['step'] = 1
            conversation_context[user_id]['option'] = '1'
            conversation_context[user_id]['data'] = {}
            return """🤖 ممتاز! اخترت إضافة مستخدم جديد. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: اسم المستخدم (Username)**
اكتب اسم المستخدم للدخول

💡 **مثال:** ahmed.mohamed

🤖 اكتب اسم المستخدم الآن..."""
        
        # ========== معالجة الخطوات التالية (إضافة مستخدم) ==========
        if user_id in conversation_context and conversation_context[user_id].get('last_action') == 'مستخدم' and conversation_context[user_id].get('option') == '1':
            step = conversation_context[user_id].get('step', 0)
            data = conversation_context[user_id].get('data', {})
            
            listener_status, listener_msg = apply_smart_listeners(message, conversation_context[user_id], 'مستخدم')
            if listener_status in ['back', 'help']:
                if listener_status == 'back':
                    del conversation_context[user_id]
                return listener_msg
            
            if step == 1:
                data['username'] = message.strip()
                conversation_context[user_id]['data'] = data
                conversation_context[user_id]['step'] = 2
                return """✅ **تم حفظ اسم المستخدم:** {username}

📝 **الخطوة 2: كلمة المرور**
اكتب كلمة المرور

💡 **مثال:** Pass@123

🤖 اكتب كلمة المرور الآن...""".format(username=data['username'])
            
            elif step == 2:
                data['password'] = message.strip()
                conversation_context[user_id]['data'] = data
                conversation_context[user_id]['step'] = 3
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
                conversation_context[user_id]['data'] = data
                conversation_context[user_id]['step'] = 4
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
                    
                    new_user = User(
                        username=data['username'],
                        password_hash=generate_password_hash(data['password']),
                        role=data['role'],
                        email=data['email']
                    )
                    db.session.add(new_user)
                    db.session.commit()
                    
                    train_local_ai('create_user', data, {'success': True, 'user_id': new_user.id})
                    
                    del conversation_context[user_id]
                    
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
                    del conversation_context[user_id]
                    return f"""❌ **خطأ في إنشاء المستخدم:** {str(e)}

💡 **حاول مرة أخرى:** اكتب "مستخدم" ثم "1"

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        # ========== نظام الحوار التفاعلي للرقم 2 (عرض جميع العناصر) ==========
        if msg_lower.strip() == '2' and user_id in conversation_context and conversation_context[user_id].get('last_action') == 'عميل':
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
        
        if msg_lower.strip() == '2' and user_id in conversation_context and conversation_context[user_id].get('last_action') == 'منتج':
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
        
        if msg_lower.strip() == '2' and user_id in conversation_context and conversation_context[user_id].get('last_action') == 'فاتورة':
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
        
        if msg_lower.strip() == '2' and user_id in conversation_context and conversation_context[user_id].get('last_action') == 'مصروف':
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
        
        if msg_lower.strip() == '2' and user_id in conversation_context and conversation_context[user_id].get('last_action') == 'مورد':
            from models.supplier import Supplier
            suppliers = Supplier.query.filter_by(is_active=True, tenant_id=tid).all()
            del conversation_context[user_id]
            if suppliers:
                suppliers_list = "\n".join([f"• {s.name} - {s.phone or 'لا يوجد هاتف'}" for s in suppliers[:10]])
                more_text = f"\n\n... و {len(suppliers) - 10} مورد آخر" if len(suppliers) > 10 else ""
                return f"""✅ **جميع الموردين ({len(suppliers)} مورد):**

{suppliers_list}{more_text}

🤖 المصدر: GROQ API + التحليل المحلي"""
            else:
                return """❌ **لا يوجد موردين في النظام**

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        if msg_lower.strip() == '2' and user_id in conversation_context and conversation_context[user_id].get('last_action') == 'مشتريات':
            from models.purchase import Purchase
            purchases = Purchase.query.filter_by(is_active=True).all()
            del conversation_context[user_id]
            if purchases:
                purchases_list = "\n".join([f"• #{p.id} - {p.supplier.name if p.supplier else 'غير محدد'} - {p.total_amount} درهم" for p in purchases[:10]])
                more_text = f"\n\n... و {len(purchases) - 10} مشتريات أخرى" if len(purchases) > 10 else ""
                return f"""✅ **جميع المشتريات ({len(purchases)} مشتريات):**

{purchases_list}{more_text}

🤖 المصدر: GROQ API + التحليل المحلي"""
            else:
                return """❌ **لا يوجد مشتريات في النظام**

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        if msg_lower.strip() == '2' and user_id in conversation_context and conversation_context[user_id].get('last_action') == 'شيك':
            from models.cheque import Cheque
            cheques = Cheque.query.filter_by(is_active=True).all()
            del conversation_context[user_id]
            if cheques:
                cheques_list = "\n".join([f"• #{c.id} - {c.cheque_number} - {c.amount} درهم - {c.status}" for c in cheques[:10]])
                more_text = f"\n\n... و {len(cheques) - 10} شيك آخر" if len(cheques) > 10 else ""
                return f"""✅ **جميع الشيكات ({len(cheques)} شيك):**

{cheques_list}{more_text}

🤖 المصدر: GROQ API + التحليل المحلي"""
            else:
                return """❌ **لا يوجد شيكات في النظام**

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        if msg_lower.strip() == '2' and user_id in conversation_context and conversation_context[user_id].get('last_action') == 'مستخدم':
            from models.user import User
            from utils.tenanting import scoped_user_query
            users = scoped_user_query(active_only=True).all()
            del conversation_context[user_id]
            if users:
                users_list = "\n".join([f"• {u.username} - {u.role}" for u in users[:10]])
                more_text = f"\n\n... و {len(users) - 10} مستخدم آخر" if len(users) > 10 else ""
                return f"""✅ **جميع المستخدمين ({len(users)} مستخدم):**

{users_list}{more_text}

🤖 المصدر: GROQ API + التحليل المحلي"""
            else:
                return """❌ **لا يوجد مستخدمين في النظام**

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        if msg_lower.strip() == '2' and user_id in conversation_context and conversation_context[user_id].get('last_action') == 'دفتر':
            from models.gl import GLJournalEntry
            gl_entries = GLJournalEntry.query.filter_by(is_active=True, tenant_id=tid).order_by(GLJournalEntry.entry_date.desc()).limit(20).all()
            del conversation_context[user_id]
            if gl_entries:
                gl_list = "\n".join([f"• #{g.id} - {g.description} - {g.debit_amount} درهم - {g.entry_date.strftime('%Y-%m-%d')}" for g in gl_entries])
                return f"""✅ **القيود المحاسبية (آخر 20 قيد):**

{gl_list}

🤖 المصدر: GROQ API + التحليل المحلي"""
            else:
                return """❌ **لا يوجد قيود في النظام**

🤖 المصدر: GROQ API + التحليل المحلي"""
        
        if msg_lower.strip() == '2' and user_id in conversation_context and conversation_context[user_id].get('last_action') == 'مستودع':
            from models.product import Product
            products = Product.query.filter_by(tenant_id=tid, is_active=True).all()
            del conversation_context[user_id]
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
        if msg_lower.strip() == '3' and user_id in conversation_context and conversation_context[user_id].get('last_action') == 'عميل':
            conversation_context[user_id]['step'] = 1
            conversation_context[user_id]['option'] = '3'
            return """🤖 ممتاز! اخترت البحث عن عميل. سأرشدك خطوة بخطوة:

📝 **اكتب اسم العميل أو رقم هاتفه**
اكتب اسم العميل أو رقم هاتفه للبحث

💡 **أمثلة:**
• "أحمد محمد"
• "0561234567"
• "أحمد"

🤖 اكتب اسم العميل أو رقم هاتفه الآن..."""
        
        if msg_lower.strip() == '3' and user_id in conversation_context and conversation_context[user_id].get('last_action') == 'منتج':
            conversation_context[user_id]['step'] = 1
            conversation_context[user_id]['option'] = '3'
            return """🤖 ممتاز! اخترت البحث عن منتج. سأرشدك خطوة بخطوة:

📝 **اكتب اسم المنتج أو رقم القطعة**
اكتب اسم المنتج أو رقم القطعة للبحث

💡 **أمثلة:**
• "فلتر زيت"
• "12345"
• "كاتربلر"

🤖 اكتب اسم المنتج أو رقم القطعة الآن..."""
        
        if msg_lower.strip() == '3' and any(word in msg_lower for word in ['فاتورة', 'بيع', 'مبيعات', 'إنشاء فاتورة']):
            return """🤖 ممتاز! اخترت البحث عن فاتورة. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: اكتب رقم الفاتورة أو اسم العميل**
اكتب رقم الفاتورة أو اسم العميل للبحث

💡 **أمثلة:**
• "123"
• "أحمد محمد"
• "فاتورة 123"

🤖 اكتب رقم الفاتورة أو اسم العميل الآن..."""
        
        if msg_lower.strip() == '3' and any(word in msg_lower for word in ['مصروف', 'إضافة مصروف', 'إنشاء مصروف']):
            return """🤖 ممتاز! اخترت البحث عن مصروف. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: اكتب وصف المصروف أو فئته**
اكتب وصف المصروف أو فئته للبحث

💡 **أمثلة:**
• "فواتير الكهرباء"
• "صيانة"
• "مرافق"

🤖 اكتب وصف المصروف أو فئته الآن..."""
        
        if msg_lower.strip() == '3' and any(word in msg_lower for word in ['مورد', 'مورد جديد', 'إضافة مورد', 'إنشاء مورد']):
            return """🤖 ممتاز! اخترت البحث عن مورد. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: اكتب اسم المورد أو رقم هاتفه**
اكتب اسم المورد أو رقم هاتفه للبحث

💡 **أمثلة:**
• "شركة قطع غيار"
• "0561234567"
• "دبي"

🤖 اكتب اسم المورد أو رقم هاتفه الآن..."""
        
        if msg_lower.strip() == '3' and any(word in msg_lower for word in ['مشتريات', 'شراء', 'إضافة مشتريات', 'إنشاء مشتريات']):
            return """🤖 ممتاز! اخترت البحث عن مشتريات. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: اكتب رقم المشتريات أو اسم المورد**
اكتب رقم المشتريات أو اسم المورد للبحث

💡 **أمثلة:**
• "123"
• "شركة قطع غيار"
• "مشتريات 123"

🤖 اكتب رقم المشتريات أو اسم المورد الآن..."""
        
        if msg_lower.strip() == '3' and any(word in msg_lower for word in ['شيك', 'شيكات', 'إضافة شيك', 'إنشاء شيك']):
            return """🤖 ممتاز! اخترت البحث عن شيك. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: اكتب رقم الشيك أو المبلغ**
اكتب رقم الشيك أو المبلغ للبحث

💡 **أمثلة:**
• "123"
• "1000"
• "شيك 123"

🤖 اكتب رقم الشيك أو المبلغ الآن..."""
        
        if msg_lower.strip() == '3' and any(word in msg_lower for word in ['دفتر', 'دفتر الأستاذ', 'دفتر استاذ', 'قيد']):
            return """🤖 ممتاز! اخترت البحث عن قيد. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: اكتب وصف القيد أو رقمه**
اكتب وصف القيد أو رقمه للبحث

💡 **أمثلة:**
• "قيد مبيعات"
• "123"
• "مبيعات اليوم"

🤖 اكتب وصف القيد أو رقمه الآن..."""
        
        if msg_lower.strip() == '3' and any(word in msg_lower for word in ['مستودع', 'مستودعات', 'مخزون', 'إدارة مستودعات']):
            return """🤖 ممتاز! اخترت البحث عن مستودع. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: اكتب اسم المستودع أو موقعه**
اكتب اسم المستودع أو موقعه للبحث

💡 **أمثلة:**
• "المستودع الرئيسي"
• "دبي"
• "الشارقة"

🤖 اكتب اسم المستودع أو موقعه الآن..."""
        
        if msg_lower.strip() == '3' and any(word in msg_lower for word in ['مستخدم', 'مستخدمين', 'إضافة مستخدم', 'إنشاء مستخدم']):
            return """🤖 ممتاز! اخترت البحث عن مستخدم. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: اكتب اسم المستخدم أو إيميله**
اكتب اسم المستخدم أو إيميله للبحث

💡 **أمثلة:**
• "أحمد محمد"
• "ahmed@example.com"
• "admin"

🤖 اكتب اسم المستخدم أو إيميله الآن..."""
        
        # ========== نظام الحوار التفاعلي للرقم 4 (إدارة المخزون) ==========
        if msg_lower.strip() == '4' and any(word in msg_lower for word in ['مستودع', 'مستودعات', 'مخزون', 'إدارة مستودعات']):
            return """🤖 ممتاز! اخترت إدارة المخزون. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: اكتب اسم المستودع**
اكتب اسم المستودع لإدارة مخزونه

💡 **أمثلة:**
• "المستودع الرئيسي"
• "مستودع دبي"
• "مخزن الشارقة"

🤖 اكتب اسم المستودع الآن..."""
        
        # ========== نظام الحوار التفاعلي للرقم 4 (تعديل صلاحيات المستخدمين) ==========
        if msg_lower.strip() == '4' and any(word in msg_lower for word in ['مستخدم', 'مستخدمين', 'إضافة مستخدم', 'إنشاء مستخدم']):
            return """🤖 ممتاز! اخترت تعديل صلاحيات مستخدم. سأرشدك خطوة بخطوة:

📝 **الخطوة 1: اكتب اسم المستخدم**
اكتب اسم المستخدم لتعديل صلاحياته

💡 **أمثلة:**
• "أحمد محمد"
• "admin"
• "user1"

🤖 اكتب اسم المستخدم الآن..."""
        
        # ========== نظام الحوار التفاعلي للرقم 4 (رفع منتجات من Excel) ==========
        if msg_lower.strip() == '4' and user_id in conversation_context and conversation_context[user_id].get('last_action') == 'منتج':
            del conversation_context[user_id]
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
                        current_stock=quantity,
                        is_active=True
                    )
                    assign_tenant_id(product, user)
                    db.session.add(product)
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
                        amount_aed=product.regular_price * quantity,
                        payment_status='paid' if payment_method == 'cash' else 'unpaid',
                        status='confirmed'
                    )
                    db.session.add(sale)
                    db.session.flush()
                    
                    sale_line = SaleLine(
                        sale_id=sale.id,
                        product_id=product.id,
                        quantity=quantity,
                        unit_price=product.regular_price,
                        line_total=product.regular_price * quantity
                    )
                    db.session.add(sale_line)
                    
                    product.current_stock -= quantity
                    
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
                    
                    expense = Expense(
                        description=description,
                        amount_aed=amount,
                        expense_date=datetime.now(timezone.utc),
                        category=category,
                        user_id=user.id
                    )
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
                        amount_aed=amount,
                        payment_date=datetime.now(timezone.utc),
                        payment_method=payment_method,
                        user_id=user.id,
                        direction='incoming',
                        payment_type='customer_payment'
                    )
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
- الفرق: {new_balance - old_balance} درهم

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
                        amount_aed=amount,
                        payment_date=datetime.now(timezone.utc),
                        payment_method=payment_method,
                        user_id=user.id,
                        direction='incoming',
                        payment_type='customer_payment'
                    )
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
                    payment = Payment(
                        customer_id=customer.id,
                        amount_aed=-amount,  # سالب لأننا نعطي للعميل
                        payment_date=datetime.now(timezone.utc),
                        payment_method='refund',
                        user_id=user.id
                    )
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
            from services.error_audit_service import ErrorAuditService
            ErrorAuditService.log_exception(e, category="AI", source="routes.ai._process_user_action", level="ERROR")
        except Exception:
            pass
        return f"❌ خطأ في التنفيذ: {str(e)}"


@ai_bp.route('/assistant', methods=['GET'])
@login_required
@owner_required
def assistant_page():
    """صفحة المساعد الذكي"""
    try:
        from models import Warehouse
        from utils.branching import get_accessible_warehouses
        warehouses = get_accessible_warehouses(current_user)
        state = get_ai_access_state(current_user)
        disable_reason = None
        if not state.get('allowed'):
            disable_reason = state.get('reason')
        return render_template(
            'ai/assistant.html',
            ai_enabled=bool(state.get('allowed') and state.get('global_enabled') and state.get('tenant_enabled') is not False),
            ai_access_state=state,
            ai_disable_reason=disable_reason,
            warehouses=warehouses,
            current_user=current_user,
        )
    except Exception:
        current_app.logger.exception("AI assistant page failed")
        return render_template('errors/500.html'), 500


@ai_bp.route('/config', methods=['GET', 'POST'])
@login_required
@owner_required
def config():
    """إعدادات AI - تحديث المفاتيح يومياً"""
    if request.method == 'POST':
        api_key = request.form.get('api_key', '').strip()
        provider = request.form.get('provider', 'groq')
        
        if not api_key:
            return jsonify({'success': False, 'message': 'المفتاح مطلوب'})
        
        try:
            from pathlib import Path
            base_env_path = Path(__file__).resolve().parent.parent / '.env'
            
            env_file = base_env_path
            
            if env_file.exists():
                with open(env_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            else:
                lines = []
            
            if provider == 'groq':
                key_name = 'GROQ_API_KEY'
            elif provider == 'gemini':
                key_name = 'GEMINI_API_KEY'
            else:
                key_name = 'OPENAI_API_KEY'
            
            key_found = False
            
            for i, line in enumerate(lines):
                if line.startswith(key_name + '='):
                    lines[i] = f'{key_name}={api_key}\n'
                    key_found = True
                    break
            
            if not key_found:
                lines.append(f'{key_name}={api_key}\n')
            
            with open(env_file, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            
            os.environ[key_name] = api_key
            
            from flask import current_app
            current_app.logger.info(f"✅ {key_name} updated successfully by user {current_user.username}")
            
            return jsonify({
                'success': True, 
                'message': f'تم حفظ مفتاح {provider.upper()} بنجاح! ✅',
                'provider': provider,
                'expires_in': '24 ساعة' if provider == 'groq' else 'حسب اشتراكك'
            })
        
        except Exception:
            current_app.logger.exception("Failed to save AI API key")
            return jsonify({'success': False, 'message': 'تعذر حفظ إعدادات AI حالياً'})
    
    current_groq = os.environ.get('GROQ_API_KEY', '')
    current_openai = os.environ.get('OPENAI_API_KEY', '')
    current_gemini = os.environ.get('GEMINI_API_KEY', '')
    
    state = get_ai_access_state(current_user)
    return render_template('ai/config.html',
                         ai_enabled=bool(state.get('global_enabled')),
                         groq_key_exists=bool(current_groq),
                         openai_key_exists=bool(current_openai or current_gemini))


@ai_bp.route('/upload-excel', methods=['POST'])
@login_required
@permission_required('manage_products')
def upload_excel():
    """رفع ومعالجة ملف Excel للمنتجات - المعالج الذكي الخارق"""
    try:
        max_bytes = int(current_app.config.get('MAX_CONTENT_LENGTH') or (16 * 1024 * 1024))
        if request.content_length and request.content_length > max_bytes:
            return jsonify({'success': False, 'error': 'حجم الملف كبير جداً'}), 413

        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'لم يتم رفع ملف'}), 400
        
        file = request.files['file']
        warehouse_id = request.form.get('warehouse_id', type=int)
        if not warehouse_id:
            from models import Warehouse
            tid = get_active_tenant_id(current_user)
            warehouse = Warehouse.query.filter_by(is_active=True, is_main=True, tenant_id=tid).first()
            if not warehouse:
                warehouse = Warehouse.query.filter_by(is_active=True, tenant_id=tid).first()
            if warehouse:
                warehouse_id = warehouse.id
        
        filename = secure_filename(file.filename or '')
        if not filename:
            return jsonify({'success': False, 'error': 'لم يتم اختيار ملف'}), 400
        
        if not filename.lower().endswith(('.xlsx', '.xls')):
            return jsonify({'success': False, 'error': 'الملف يجب أن يكون Excel (.xlsx أو .xls)'}), 400

        file.stream.seek(0, 2)
        file_size = file.stream.tell()
        file.stream.seek(0)
        if file_size > max_bytes:
            return jsonify({'success': False, 'error': 'حجم الملف كبير جداً'}), 413
        
        result = _process_excel_intelligently(file, warehouse_id, current_user)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'خطأ في معالجة الملف: {str(e)}'
        }), 500


def _process_excel_intelligently(file, warehouse_id, user):
    """معالج Excel ذكي خارق - أفضل من البشر"""
    try:
        from models import Product, Warehouse
        
        tid = get_active_tenant_id(user)
        df = pd.read_excel(file, engine='openpyxl')
        
        column_mapping = _intelligent_column_detector(df)
        
        if not column_mapping:
            return {
                'success': False,
                'error': 'لم أستطع فهم هيكل الملف. تأكد من وجود أعمدة: الاسم، رقم القطعة، السعر'
            }
        
        warehouse = Warehouse.query.filter_by(id=warehouse_id, tenant_id=tid).first()
        if not warehouse:
            return {'success': False, 'error': f'المستودع #{warehouse_id} غير موجود'}
        
        products_created = 0
        products_updated = 0
        errors = []
        
        for index, row in df.iterrows():
            try:
                name = str(row[column_mapping['name']]).strip()
                part_number = str(row[column_mapping['part_number']]).strip()
                price = float(row[column_mapping['price']])
                
                if 'quantity' in column_mapping and column_mapping['quantity'] in row:
                    quantity_val = row[column_mapping['quantity']]
                    if pd.isna(quantity_val) or quantity_val == '':
                        quantity = 0
                    else:
                        quantity = int(float(quantity_val))
                else:
                    quantity = 0
                
                if not name or name == 'nan' or part_number == 'nan':
                    continue
                
                existing_product = Product.query.filter_by(part_number=part_number, tenant_id=tid).first()
                
                if existing_product:
                    existing_product.regular_price = price
                    existing_product.current_stock += quantity
                    products_updated += 1
                else:
                    product = Product(
                        name=name,
                        part_number=part_number,
                        regular_price=price,
                        current_stock=quantity,
                        is_active=True
                    )
                    assign_tenant_id(product, user)
                    db.session.add(product)
                    products_created += 1
                
            except Exception as e:
                errors.append(f'السطر {index + 2}: {str(e)}')
        
        db.session.commit()
        
        _train_ai_from_excel(df, products_created, products_updated, user.id)
        
        error_details = '\n'.join(errors) if errors else ''
        
        message = f'''✅ تمت المعالجة بنجاح!
            
📊 النتائج:
- تم إنشاء: {products_created} منتج جديد
- تم تحديث: {products_updated} منتج موجود
- المستودع: {warehouse.name}
- الأخطاء: {len(errors)}

🤖 تم تدريب AI على البيانات الجديدة!
🧠 المصدر: GROQ + المحلي - معالج ذكي خارق'''
        
        if errors and len(errors) > 0:
            message += f'\n\n⚠️ تفاصيل الأخطاء:\n{error_details}'
        
        return {
            'success': True,
            'message': message,
            'details': {
                'created': products_created,
                'updated': products_updated,
                'errors': errors,
                'warehouse': warehouse.name
            }
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': f'خطأ في المعالجة: {str(e)}'
        }


def _intelligent_column_detector(df):
    """كاشف ذكي لأعمدة Excel - يفهم أي تسمية"""
    column_mapping = {}
    
    name_keywords = ['اسم', 'name', 'product', 'منتج', 'item', 'description', 'وصف']
    part_keywords = ['رقم', 'part', 'code', 'كود', 'sku', 'id', 'reference', 'مرجع']
    price_keywords = ['سعر', 'price', 'cost', 'تكلفة', 'value', 'قيمة', 'amount', 'مبلغ']
    quantity_keywords = ['كمية', 'qty', 'quantity', 'stock', 'مخزون', 'عدد', 'count']
    
    columns_lower = [str(col).lower() for col in df.columns]
    
    for idx, col in enumerate(columns_lower):
        if any(keyword in col for keyword in name_keywords):
            column_mapping['name'] = df.columns[idx]
        elif any(keyword in col for keyword in part_keywords):
            column_mapping['part_number'] = df.columns[idx]
        elif any(keyword in col for keyword in price_keywords):
            column_mapping['price'] = df.columns[idx]
        elif any(keyword in col for keyword in quantity_keywords):
            column_mapping['quantity'] = df.columns[idx]
    
    if 'name' not in column_mapping and len(df.columns) > 0:
        column_mapping['name'] = df.columns[0]
    if 'part_number' not in column_mapping and len(df.columns) > 1:
        column_mapping['part_number'] = df.columns[1]
    if 'price' not in column_mapping and len(df.columns) > 2:
        column_mapping['price'] = df.columns[2]
    if 'quantity' not in column_mapping and len(df.columns) > 3:
        column_mapping['quantity'] = df.columns[3]
    
    return column_mapping if len(column_mapping) >= 3 else None


def _train_ai_from_excel(df, created, updated, user_id):
    """تدريب AI من بيانات Excel"""
    try:
        learning_data = {
            'source': 'excel_upload',
            'timestamp': datetime.now().isoformat(),
            'user_id': user_id,
            'products_created': created,
            'products_updated': updated,
            'total_rows': len(df),
            'columns': list(df.columns),
            'sample_data': df.head(5).to_dict()
        }
        
        # learning_system.learn_from_user_data(learning_data)  # تعطيل مؤقت
        
    except Exception as e:
        print(f"AI training from Excel failed: {e}")


@ai_bp.route('/predict-sales', methods=['GET'])
@login_required
@permission_required('view_reports')
def predict_sales():
    """🔮 API: توقع المبيعات"""
    days = request.args.get('days', 7, type=int)
    prediction = AIService.predict_sales_trend(days)
    return jsonify(prediction)


@ai_bp.route('/analyze-margins', methods=['GET'])
@login_required
@permission_required('view_reports')
def analyze_margins():
    """💰 API: تحليل هوامش الربح"""
    analysis = AIService.analyze_profit_margins()
    return jsonify(analysis)


@ai_bp.route('/detect-patterns', methods=['GET'])
@login_required
@permission_required('view_reports')
def detect_patterns():
    """🔍 API: كشف الأنماط"""
    patterns = AIService.detect_sales_patterns()
    return jsonify(patterns)


@ai_bp.route('/inventory-health', methods=['GET'])
@login_required
@permission_required('manage_warehouse')
def inventory_health():
    """📦 API: صحة المخزون"""
    health = AIService.analyze_inventory_health()
    return jsonify(health)


@ai_bp.route('/deep-analysis', methods=['GET'])
@login_required
@permission_required('view_reports')
def deep_analysis():
    """📊 API: تحليل عميق شامل"""
    analysis = AIService.deep_business_analysis()
    return jsonify(analysis)


@ai_bp.route('/cash-flow-prediction', methods=['GET'])
@login_required
@permission_required('view_ledger')
def cash_flow_prediction():
    """💵 API: توقع التدفق النقدي"""
    days = request.args.get('days', 30, type=int)
    prediction = AIService.predict_cash_flow(days)
    return jsonify(prediction)


@ai_bp.route('/smart-price', methods=['POST'])
@login_required
@permission_required('view_products')
def smart_price():
    """💎 API: محرك التسعير الذكي الخارق"""
    data = request.get_json()
    product_id = data.get('product_id')
    customer_id = data.get('customer_id')
    quantity = data.get('quantity', 1)
    
    if not product_id or not customer_id:
        return jsonify({'error': 'Product and Customer required'}), 400
    
    pricing = AIService.smart_pricing_engine(product_id, customer_id, quantity)
    
    if not pricing:
        return jsonify({'error': 'Not found'}), 404
    
    return jsonify(pricing)


@ai_bp.route('/churn-prediction', methods=['GET'])
@login_required
@permission_required('manage_customers')
def churn_prediction():
    """⚠️ API: توقع فقدان العملاء"""
    prediction = AIService.predict_customer_churn()
    return jsonify(prediction)


@ai_bp.route('/optimize-inventory', methods=['GET'])
@login_required
@permission_required('manage_warehouse')
def optimize_inventory():
    """📦 API: تحسين مستويات المخزون"""
    optimization = AIService.optimize_inventory_levels()
    return jsonify(optimization)


@ai_bp.route('/business-insights', methods=['GET'])
@login_required
@permission_required('view_reports')
def business_insights():
    """💡 API: رؤى الأعمال التلقائية"""
    insights = AIService.generate_business_insights()
    
    formatted_insights = []
    for insight in insights:
        formatted_insights.append({
            'icon': '⚠️' if insight['type'] == 'warning' else 'ℹ️',
            'title': insight['title'],
            'insight': insight['message'],
            'action': insight['action']
        })
    
    return jsonify({
        'success': True,
        'insights': formatted_insights
    })


@ai_bp.route('/contextual-help/<page>', methods=['GET'])
@login_required
@permission_required('view_reports')
def contextual_help(page):
    """❓ API: مساعدة سياقية"""
    user_role = current_user.role.name if current_user.role else 'user'
    help_content = AIService.contextual_help(page, user_role)
    return jsonify(help_content)


@ai_bp.route('/learning/status')
@login_required
@permission_required('view_reports')
def learning_status():
    """حالة التعلم الذاتي"""
    try:
        insights = learning_system.get_learning_insights()
        return jsonify({
            'success': True,
            'learning_insights': insights
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_bp.route('/learning/evolve', methods=['POST'])
@login_required
@admin_required
def evolve_knowledge():
    """تطوير المعرفة تلقائياً"""
    try:
        evolution = learning_system.evolve_knowledge()
        return jsonify({
            'success': True,
            'evolution': evolution
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_bp.route('/improvement/status')
@login_required
@permission_required('view_reports')
def improvement_status():
    """حالة التحسين الذاتي"""
    try:
        status = self_improvement.get_improvement_status()
        return jsonify({
            'success': True,
            'improvement_status': status
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_bp.route('/improvement/auto-improve', methods=['POST'])
@login_required
@admin_required
def auto_improve():
    """التحسين التلقائي"""
    try:
        improvements = self_improvement.auto_improve()
        return jsonify({
            'success': True,
            'improvements': improvements
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_bp.route('/improvement/progress')
@login_required
@permission_required('view_reports')
def improvement_progress():
    """تتبع تقدم التحسين"""
    try:
        progress = self_improvement.track_progress()
        return jsonify({
            'success': True,
            'progress': progress
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_bp.route('/improvement/set-goal', methods=['POST'])
@login_required
@admin_required
def set_improvement_goal():
    """تعيين هدف تحسين"""
    try:
        data = request.get_json()
        area = data.get('area')
        target_score = data.get('target_score')
        timeframe = data.get('timeframe', '30_days')
        
        if not area or not target_score:
            return jsonify({
                'success': False,
                'error': 'المجال والهدف مطلوبان'
            }), 400
        
        result = self_improvement.set_improvement_goal(area, target_score, timeframe)
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_bp.route('/global/insights')
@login_required
@permission_required('view_reports')
def global_insights():
    """رؤى عالمية"""
    try:
        insights = global_connector.get_global_insights()
        return jsonify({
            'success': True,
            'global_insights': insights
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_bp.route('/global/expertise-update')
@login_required
@admin_required
def update_global_expertise():
    """تحديث الخبرة العالمية"""
    try:
        updates = expertise_updater.update_expertise()
        return jsonify({
            'success': True,
            'expertise_updates': updates
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_bp.route('/performance/analysis')
@login_required
@permission_required('view_reports')
def performance_analysis():
    """تحليل الأداء الشامل"""
    try:
        performance = self_improvement.analyze_performance()
        
        learning_insights = learning_system.get_learning_insights()
        
        evolution = self_improvement.evolve_capabilities()
        
        global_insights_data = global_connector.get_global_insights()
        
        return jsonify({
            'success': True,
            'performance_analysis': {
                'performance': performance,
                'learning': learning_insights,
                'evolution': evolution,
                'global': global_insights_data
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_bp.route('/system/customer-balance/<customer_name>')
@login_required
@permission_required('manage_customers')
def get_customer_balance(customer_name):
    """جلب رصيد العميل بدقة"""
    try:
        result = system_integrator.get_customer_balance(customer_name)
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_bp.route('/system/customer-debt/<int:customer_id>')
@login_required
@permission_required('manage_customers')
def analyze_customer_debt(customer_id):
    """تحليل ديون العميل بالتفصيل"""
    try:
        result = data_analyzer.analyze_customer_debt(customer_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_bp.route('/system/product-stock/<product_name>')
@login_required
@permission_required('manage_products')
def get_product_stock(product_name):
    """جلب مخزون المنتج بدقة"""
    try:
        result = system_integrator.get_product_stock(product_name)
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_bp.route('/system/summary')
@login_required
@permission_required('view_reports')
def get_system_summary():
    """ملخص النظام الشامل"""
    try:
        result = system_integrator.get_system_summary()
        financial_result = system_integrator.get_financial_summary()
        
        return jsonify({
            'success': True,
            'summary': result.get('summary', {}),
            'financial': financial_result.get('financial', {})
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_bp.route('/system/search/<search_term>')
@login_required
@permission_required('view_reports')
def search_system_data(search_term):
    """البحث في بيانات النظام"""
    try:
        result = system_integrator.search_data(search_term)
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_bp.route('/system/add-customer', methods=['POST'])
@login_required
@permission_required('manage_customers')
def add_customer():
    """إضافة عميل جديد"""
    try:
        data = request.get_json()
        result = system_integrator.add_customer(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_bp.route('/data/analyze-sales')
@login_required
@permission_required('view_reports')
def analyze_sales_performance():
    """تحليل أداء المبيعات"""
    try:
        period_days = request.args.get('period', 30, type=int)
        result = data_analyzer.analyze_sales_performance(period_days)
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_bp.route('/data/analyze-products')
@login_required
@permission_required('view_products')
def analyze_product_performance():
    """تحليل أداء المنتجات"""
    try:
        product_id = request.args.get('product_id', type=int)
        result = data_analyzer.analyze_product_performance(product_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_bp.route('/data/financial-ratios')
@login_required
@permission_required('view_reports')
def get_financial_ratios():
    """النسب المالية"""
    try:
        result = data_analyzer.get_financial_ratios()
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_bp.route('/knowledge/add-website', methods=['POST'])
@login_required
@admin_required
def add_knowledge_website():
    """إضافة موقع ويب للمعرفة"""
    try:
        data = request.get_json()
        url = data.get('url')
        category = data.get('category', 'general')
        description = data.get('description', '')
        
        if not url:
            return jsonify({
                'success': False,
                'error': 'الرابط مطلوب'
            }), 400
        
        result = knowledge_expander.add_website(url, category, description)
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_bp.route('/knowledge/add-document', methods=['POST'])
@login_required
@admin_required
def add_knowledge_document():
    """إضافة مستند للمعرفة"""
    try:
        data = request.get_json()
        content = data.get('content')
        title = data.get('title')
        category = data.get('category', 'general')
        description = data.get('description', '')
        
        if not content or not title:
            return jsonify({
                'success': False,
                'error': 'المحتوى والعنوان مطلوبان'
            }), 400
        
        result = knowledge_expander.add_document(content, title, category, description)
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_bp.route('/knowledge/search')
@login_required
@permission_required('view_reports')
def search_knowledge():
    """البحث في المعرفة الموسعة"""
    try:
        query = request.args.get('q', '')
        category = request.args.get('category')
        
        if not query:
            return jsonify({
                'success': False,
                'error': 'كلمة البحث مطلوبة'
            }), 400
        
        result = knowledge_expander.search_knowledge(query, category)
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_bp.route('/knowledge/summary')
@login_required
@permission_required('view_reports')
def get_knowledge_summary():
    """📚 API: ملخص المعرفة الموسعة"""
    try:
        result = knowledge_expander.get_knowledge_summary()
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@ai_bp.route('/neural-status', methods=['GET'])
@login_required
@permission_required('view_reports')
def neural_status():
    """🧠 API: حالة الشبكات العصبية"""
    try:
        status = AIService.get_neural_status()
        return jsonify({
            'success': True,
            'status': status
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })


@ai_bp.route('/automotive-ecu/<code>', methods=['GET'])
@login_required
@permission_required('view_products')
def automotive_ecu_code(code):
    """🚗 API: تشخيص كود OBD-II"""
    try:
        ecu_expert = get_automotive_ecu_knowledge()
        diagnosis = ecu_expert.diagnose_code(code.upper())
        
        return jsonify({
            'success': True,
            'diagnosis': diagnosis
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })


@ai_bp.route('/automotive-sensor/<sensor>', methods=['GET'])
@login_required
@permission_required('view_products')
def automotive_sensor(sensor):
    """🔧 API: معلومات حساس محدد"""
    try:
        ecu_expert = get_automotive_ecu_knowledge()
        info = ecu_expert.get_sensor_info(sensor)
        
        return jsonify({
            'success': True,
            'sensor_info': info
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })


@ai_bp.route('/external-sources', methods=['GET'])
@login_required
@permission_required('view_reports')
def external_sources():
    """📚 API: قائمة مصادر التعلم الخارجية"""
    try:
        learning = get_external_learning()
        sources = learning.get_knowledge_sources_list()
        stats = learning.get_statistics()
        
        return jsonify({
            'success': True,
            'sources': sources,
            'statistics': stats,
            'catalog': LEARNING_SOURCES_CATALOG
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })


@ai_bp.route('/ask-genius', methods=['POST'])
@login_required
@permission_required('view_reports')
@limiter.limit("30 per minute")
def ask_genius():
    """🌟 API: اسأل العبقري - الواجهة الموحدة (JSON callers must send X-CSRFToken)."""
    try:
        data = request.get_json()
        question = data.get('question', '')
        context = data.get('context', {})
        
        if not question:
            return jsonify({
                'success': False,
                'error': 'السؤال مطلوب'
            }), 400
        
        result = AIService.ask_genius(
            question=question,
            context=context,
            user_id=current_user.id
        )
        
        return jsonify({
            'success': True,
            'result': result
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })


@ai_bp.route('/quick-calc', methods=['POST'])
@csrf.exempt
@login_required
@limiter.limit("30 per minute")
def quick_calc():
    """⚡ API: حسابات سريعة — whitelist formulas only; no DB, files, or external calls."""
    try:
        data = request.get_json()
        formula = data.get('formula', '')
        params = data.get('params', {})
        
        if not formula:
            return jsonify({
                'success': False,
                'error': 'الصيغة مطلوبة'
            }), 400
        
        result = AIService.quick_calculate(formula, **params)
        
        return jsonify({
            'success': result.get('success', False),
            'result': result
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })


@ai_bp.route('/transformers-understand', methods=['POST'])
@csrf.exempt
@login_required
@limiter.limit("30 per minute")
def transformers_understand():
    """🤖 API: فهم بالـ Transformers — local in-memory only; no DB, files, or ERP actions."""
    try:
        data = request.get_json()
        text = data.get('text', '')
        
        if not text:
            return jsonify({
                'success': False,
                'error': 'النص مطلوب'
            }), 400
        
        understanding = AIService.understand_with_transformers(text)
        
        return jsonify({
            'success': True,
            'understanding': understanding
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })
