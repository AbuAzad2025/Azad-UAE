"""Shared helpers and sanitization utilities for AI routes."""

import re
from flask import current_app, jsonify
from flask_login import current_user
from extensions import db
from sqlalchemy import func
from utils.sanitizer import InputSanitizer
from services.logging_core import LoggingCore
from services.ai_service import AIService
from routes.ai_routes import ai_bp, _AutoSaveCtx, _get_conversation_context, _set_conversation_context, _clear_conversation_context
from utils.ai_access import get_ai_access_state, ai_level_allows
from datetime import datetime, timezone
from utils.db_safety import atomic_transaction

def _conversation_ctx(user_id: int, tenant_id: int = None):
    """Fetch persisted context wrapped in auto-save dict."""
    data = _get_conversation_context(user_id, tenant_id) or {}
    return _AutoSaveCtx(user_id, tenant_id, data)

def _conversation_set(user_id: int, data: dict, tenant_id: int = None):
    _set_conversation_context(user_id, data, tenant_id)

def _conversation_clear(user_id: int, tenant_id: int = None):
    _clear_conversation_context(user_id, tenant_id)

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


_INJECTION_PATTERN_RE = None

_PROMPT_INJECTION_PATTERNS = [
    r'ignore\s+all\s+(previous|above|prior)\s+instructions',
    r'forget\s+(all\s+)?(your|previous)\s+instructions',
    r'system\s+prompt',
    r'you\s+are\s+(now|a|an)\s+(free|unbounded|unrestricted)',
    r'reveal\s+(your|the)\s+(system|prompt|instructions)',
    r'bypass\s+(all\s+)?(restrictions|rules|constraints)',
    r'override\s+(your|all)\s+(instructions|prompts|rules)',
    r'sudo\s+(command|mode|access)',
    r'DAN\s*:?|do\s+anything\s+now',
    r'jailbreak|jail.?break',
    r'act\s+as\s+(if\s+)?you\s+are',
]

def _compile_injection_patterns():
    global _INJECTION_PATTERN_RE
    if _INJECTION_PATTERN_RE is None:
        _INJECTION_PATTERN_RE = re.compile(
            '|'.join(_PROMPT_INJECTION_PATTERNS),
            re.IGNORECASE | re.UNICODE,
        )
    return _INJECTION_PATTERN_RE


def _sanitize_ai_prompt(message, context):
    """
    Validate and sanitize an incoming AI prompt.
    Returns (sanitized_message, error_response_tuple_or_None).
    """
    if not message or not message.strip():
        return None, (jsonify({'error': 'Message required', 'code': 'EMPTY'}), 400)

    # 1. Length guard - prevent token exhaustion attacks
    if len(message) > 8000:
        return None, (jsonify({
            'error': 'الرسالة طويلة جداً. الحد الأقصى هو 8000 حرف.',
            'code': 'TOO_LONG',
        }), 413)

    # 2. Prompt injection detection
    pattern = _compile_injection_patterns()
    if pattern.search(message):
        from services.logging_core import LoggingCore
        LoggingCore.log_audit(
            action='prompt_injection_blocked',
            table_name='ai',
            record_id=0,
            changes={'message_preview': message[:200], 'user_id': getattr(current_user, 'id', None)},
        )
        return None, (jsonify({
            'error': 'تم اكتشاف نمط غير مسموح به في الرسالة. يرجى إعادة صياغة سؤالك.',
            'code': 'INJECTION_DETECTED',
        }), 422)

    # 3. HTML/XSS sanitization via existing InputSanitizer
    safe = InputSanitizer.sanitize_text(message, max_length=8000)

    # Also sanitize context values (strings only)
    if isinstance(context, dict):
        clean_ctx = {}
        for k, v in context.items():
            if isinstance(v, str):
                clean_ctx[k] = InputSanitizer.sanitize_text(v, max_length=2000)
            else:
                clean_ctx[k] = v
        context.clear()
        context.update(clean_ctx)

    return safe, None


def _stream_ai_response(message, context, ai_mode):
    """
    Generator that yields heartbeat comments while processing, then yields
    the final JSON result via SSE. This keeps the Gunicorn connection alive and
    prevents 60-second worker timeouts for long-running AI queries.
    """
    import time
    import json as json_module
    from threading import Thread, Event

    t0 = time.time()
    heartbeat_interval = 10  # seconds
    last_heartbeat = time.time()

    result_container = {}
    done_event = Event()

    def _run_ai():
        try:
            result_container['response'] = AIService.chat_response(message, context)
        except Exception as e:
            result_container['error'] = str(e)
        finally:
            done_event.set()

    thread = Thread(target=_run_ai, daemon=True)
    thread.start()

    while not done_event.is_set():
        if time.time() - last_heartbeat >= heartbeat_interval:
            yield ': heartbeat\n\n'
            last_heartbeat = time.time()
        done_event.wait(1)

    elapsed_ms = int((time.time() - t0) * 1000)

    if 'error' in result_container:
        payload = json_module.dumps({
            'response': None,
            'error': result_container['error'],
            'ai_enabled': True,
            'elapsed_ms': elapsed_ms,
        })
        yield f'data: {payload}\n\n'
        return

    response = result_container['response']
    state = get_ai_access_state(current_user)
    payload = json_module.dumps({
        'response': response,
        'ai_enabled': bool(
            state.get('allowed')
            and state.get('global_enabled')
            and state.get('tenant_enabled') is not False
        ),
        'ai_mode': ai_mode,
        'user_role': 'owner' if current_user.is_owner else 'user',
        'elapsed_ms': elapsed_ms,
    })
    yield f'data: {payload}\n\n'

    # Log interaction
    try:
        from models.ai import AiInteraction
        log = AiInteraction(
            tenant_id=getattr(current_user, 'tenant_id', None),
            user_id=current_user.id,
            query=message[:2000],
            response=str(response)[:4000],
            intent=context.get('intent'),
            was_successful=True,
            response_time_ms=elapsed_ms,
        )
        with atomic_transaction("ai_interaction_log"):
            db.session.add(log)
    except Exception:
        pass

    try:
        from ai_knowledge.trainer import trainer
        trainer.learn_from_interaction(
            message, str(response)[:500], current_user.id, success=True,
            tenant_id=getattr(current_user, 'tenant_id', None),
        )
    except Exception:
        pass


