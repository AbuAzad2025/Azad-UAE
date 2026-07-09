"""Chat and quick-query AI routes."""

from flask import render_template, request, jsonify, flash, redirect, url_for, current_app, Response, stream_with_context, g
from flask_login import login_required, current_user
from utils.decorators import permission_required
from utils.tenanting import get_active_tenant_id
from utils.ai_access import get_ai_access_state, ai_level_allows
from werkzeug.utils import secure_filename
from extensions import db, limiter
from models import Product
from services.ai_service import AIService
from services.logging_core import LoggingCore
from routes.ai_routes import ai_bp
from routes.ai_routes.shared import _sanitize_ai_prompt, _stream_ai_response, _INJECTION_PATTERN_RE, _PROMPT_INJECTION_PATTERNS
from routes.ai_routes.actions import _process_user_action, _user_can_ai_execute_actions
from utils.db_safety import atomic_transaction

import logging
import json

logger = logging.getLogger(__name__)

@ai_bp.route('/recommend-price', methods=['POST'])
@login_required
@permission_required('view_products')
@limiter.limit("60 per minute")
def recommend_price():
    """API: توصية السعر"""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Request body must be JSON'}), 400

    product_id = data.get('product_id')
    customer_id = data.get('customer_id')

    if not product_id or not customer_id:
        return jsonify({'error': 'Product and Customer required'}), 400

    try:
        recommendation = AIService.recommend_price(product_id, customer_id)
    except TimeoutError:
        return jsonify({'error': 'AI service timed out, please try again'}), 503
    except Exception:
        return jsonify({'error': 'AI service error, please try again'}), 503

    if not recommendation:
        return jsonify({'error': 'Not found'}), 404

    return jsonify(recommendation)


@ai_bp.route('/check-stock', methods=['POST'])
@login_required
@permission_required('view_products')
@limiter.limit("60 per minute")
def check_stock():
    """API: فحص المخزون"""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Request body must be JSON'}), 400

    product_id = data.get('product_id')

    if not product_id:
        return jsonify({'error': 'Product required'}), 400

    try:
        quantity = int(data.get('quantity', 0))
    except (TypeError, ValueError):
        return jsonify({'error': 'Quantity must be a number'}), 422

    try:
        alert = AIService.check_stock_alert(product_id, quantity)
    except TimeoutError:
        return jsonify({'error': 'AI service timed out, please try again'}), 503
    except Exception:
        return jsonify({'error': 'AI service error, please try again'}), 503

    if alert:
        return jsonify(alert)

    return jsonify({'type': 'success', 'message': 'المخزون كافٍ'})


@ai_bp.route('/analyze-customer/<int:customer_id>', methods=['GET'])
@login_required
@permission_required('view_customers')
def analyze_customer(customer_id):
    """API: تحليل سلوك العميل"""
    try:
        analysis = AIService.analyze_customer_behavior(customer_id)
    except TimeoutError:
        return jsonify({'error': 'AI service timed out, please try again'}), 503
    except Exception:
        return jsonify({'error': 'AI service error, please try again'}), 503

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
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Request body must be JSON'}), 400

    message = data.get('message', '').strip()
    ai_mode = data.get('ai_mode', 'groq')
    context = data.get('context', {}) or {}
    
    if 'dialect' not in context:
        context['dialect'] = 'palestinian'
    if 'beginners_mode' not in context:
        context['beginners_mode'] = False
    
    context['current_user'] = current_user
    context['is_owner'] = current_user.is_owner if current_user else False
    context['force_local'] = (ai_mode == 'local')
    
    # Apply input validation / sanitization
    safe_message, error_response = _sanitize_ai_prompt(message, context)
    if error_response:
        return error_response
    message = safe_message

    # Check if client prefers SSE streaming (to prevent Gunicorn timeouts)
    prefer_stream = (
        request.headers.get('Accept') == 'text/event-stream'
        or data.get('stream', False)
    )

    if prefer_stream:
        return Response(
            stream_with_context(_stream_ai_response(message, context, ai_mode)),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
                'Connection': 'keep-alive',
            },
        )

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
    
    import time
    t0 = time.time()
    response = AIService.chat_response(message, context)
    elapsed_ms = int((time.time() - t0) * 1000)

    try:
        from models.ai import AiInteraction
        from extensions import db
        log = AiInteraction(
            tenant_id=getattr(current_user, 'tenant_id', None),
            user_id=current_user.id,
            query=message[:2000],
            response=str(response)[:4000],
            intent=context.get('intent'),
            was_successful=True,
            response_time_ms=elapsed_ms,
        )
        with atomic_transaction("chat_interaction_log"):
            db.session.add(log)
    except Exception:
        pass

    try:
        from ai_knowledge.trainer import trainer
        trainer.learn_from_interaction(message, str(response)[:500], current_user.id, success=True,
                                        tenant_id=getattr(current_user, 'tenant_id', None))
    except Exception:
        pass

    state = get_ai_access_state(current_user)
    return jsonify({
        'response': response,
        'ai_enabled': bool(state.get('allowed') and state.get('global_enabled') and state.get('tenant_enabled') is not False),
        'ai_mode': ai_mode,
        'user_role': 'owner' if current_user.is_owner else 'user'
    })

