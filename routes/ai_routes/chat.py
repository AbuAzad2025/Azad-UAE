"""Chat and quick-query AI routes."""

import logging
from collections.abc import Iterator
from typing import cast

from flask import Response, g, request, stream_with_context
from flask_babel import gettext
from flask_login import current_user, login_required

from extensions import db, limiter
from routes.ai_routes.actions import _process_user_action, _user_can_ai_execute_actions
from routes.ai_routes.shared import _sanitize_ai_prompt, _stream_ai_response
from services.ai_service import AIService
from utils.ai_access import ai_level_allows, get_ai_access_state
from utils.api_response import error_response, success_response
from utils.db_safety import atomic_transaction
from utils.decorators import permission_required
from utils.tenanting import get_active_tenant_id

from .blueprint import ai_bp

logger = logging.getLogger(__name__)


@ai_bp.route("/recommend-price", methods=["POST"])
@login_required
@permission_required("view_products")
@limiter.limit("60 per minute")
def recommend_price():
    """API: توصية السعر"""
    data = request.get_json(silent=True)
    if not data:
        return error_response(
            message="Request body must be JSON",
            status_code=400,
        )

    product_id = data.get("product_id")
    customer_id = data.get("customer_id")

    if not product_id or not customer_id:
        return error_response(
            message="Product and Customer required",
            status_code=400,
        )

    try:
        recommendation = AIService.recommend_price(product_id, customer_id)
    except TimeoutError:
        return error_response(
            message="AI service timed out, please try again",
            status_code=503,
        )
    except Exception:
        return error_response(
            message="AI service error, please try again",
            status_code=503,
        )

    if not recommendation:
        return error_response(message="Not found", status_code=404)

    return success_response(data=recommendation)


@ai_bp.route("/check-stock", methods=["POST"])
@login_required
@permission_required("view_products")
@limiter.limit("60 per minute")
def check_stock():
    """API: فحص المخزون"""
    data = request.get_json(silent=True)
    if not data:
        return error_response(
            message="Request body must be JSON",
            status_code=400,
        )

    product_id = data.get("product_id")

    if not product_id:
        return error_response(
            message="Product required",
            status_code=400,
        )

    try:
        quantity = int(data.get("quantity", 0))
    except (TypeError, ValueError):
        return error_response(
            message="Quantity must be a number",
            status_code=422,
        )

    try:
        alert = AIService.check_stock_alert(product_id, quantity)
    except TimeoutError:
        return error_response(
            message="AI service timed out, please try again",
            status_code=503,
        )
    except Exception:
        return error_response(
            message="AI service error, please try again",
            status_code=503,
        )

    if alert:
        return success_response(data=alert)

    return success_response(
        data={"type": "success", "message": gettext("المخزون كافٍ")},
    )


@ai_bp.route("/analyze-customer/<int:customer_id>", methods=["GET"])
@login_required
@permission_required("view_customers")
def analyze_customer(customer_id):
    """API: تحليل سلوك العميل"""
    try:
        analysis = AIService.analyze_customer_behavior(customer_id)
    except TimeoutError:
        return error_response(
            message="AI service timed out, please try again",
            status_code=503,
        )
    except Exception:
        return error_response(
            message="AI service error, please try again",
            status_code=503,
        )

    if not analysis:
        return error_response(message="Customer not found", status_code=404)

    return success_response(data=analysis)


@ai_bp.route("/exchange-rate/<currency>", methods=["GET"])
@login_required
@permission_required("view_reports")
def exchange_rate(currency):
    """API: اقتراح سعر الصرف"""
    suggestion = AIService.get_exchange_rate_suggestion(currency)
    return success_response(data=suggestion)


@ai_bp.route("/search-market-price/<int:product_id>", methods=["GET"])
@login_required
@permission_required("view_products")
def search_market_price(product_id):
    """API: البحث عن سعر القطعة في الأسواق العالمية"""
    from flask import abort

    from services.product_service import ProductService

    tid = get_active_tenant_id(current_user)
    product = ProductService.get_tenant_product(product_id, tid)
    if product is None:
        abort(404)

    return success_response(
        data={
            "product": product.name,
            "suggestions": [],
        },
        message=gettext("ميزة البحث العالمي قيد التطوير"),
    )


@ai_bp.route("/find-compatible/<int:product_id>", methods=["GET"])
@login_required
@permission_required("view_products")
def find_compatible(product_id):
    """API: البحث عن السيارات المتوافقة"""
    from flask import abort

    from services.product_service import ProductService

    tid = get_active_tenant_id(current_user)
    product = ProductService.get_tenant_product(product_id, tid)
    if product is None:
        abort(404)

    return success_response(
        data={
            "product": product.name,
            "compatible_vehicles": [],
        },
        message=gettext("ميزة البحث عن المركبات المتوافقة قيد التطوير"),
    )


@ai_bp.route("/chat", methods=["POST"])
@login_required
@permission_required("view_reports")
@limiter.limit("30 per minute")
def chat():
    """API: الدردشة مع المساعد الذكي"""
    data = request.get_json(silent=True)
    if not data:
        return error_response(
            message="Request body must be JSON",
            status_code=400,
        )

    message = data.get("message", "").strip()
    ai_mode = data.get("ai_mode", "groq")
    context = data.get("context", {}) or {}

    if "dialect" not in context:
        context["dialect"] = "palestinian"
    if "beginners_mode" not in context:
        context["beginners_mode"] = False

    context["current_user"] = current_user
    context["is_owner"] = current_user.is_owner if current_user else False
    context["force_local"] = ai_mode == "local"

    # Apply input validation / sanitization
    safe_message, prompt_error = _sanitize_ai_prompt(message, context)
    if prompt_error:
        return prompt_error
    message = safe_message

    # Check if client prefers SSE streaming (to prevent Gunicorn timeouts)
    prefer_stream = request.headers.get("Accept") == "text/event-stream" or data.get("stream", False)

    if prefer_stream:
        return Response(
            stream_with_context(cast(Iterator[str], _stream_ai_response(message, context, ai_mode))),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    action_result = None
    ai_state = getattr(g, "ai_access_state", None) or get_ai_access_state(current_user)
    can_execute_mutations = ai_state.get("is_platform_user") or ai_level_allows(
        ai_state.get("ai_level") or "",
        "execute",
    )

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
                elif result.needs_confirmation is True or (
                    isinstance(result.needs_permission, str) and result.needs_permission
                ):
                    # P4-1: RBAC / confirmation-gate decisions are FINAL — never
                    # re-route them through the legacy wizard (eliminates the
                    # dual-route drift where denied actions got a second chance).
                    action_result = result.message
                else:
                    # Input-validation failure only: let the interactive wizard
                    # guide the user step by step to complete the action.
                    action_result = _process_user_action(message, current_user)
        else:
            action_result = _process_user_action(message, current_user)
    elif _user_can_ai_execute_actions(current_user):
        action_result = _process_user_action(message, current_user)

    if action_result:
        return success_response(
            data={
                "response": action_result,
                "ai_enabled": True,
                "action_executed": True,
            },
        )

    import time

    t0 = time.time()
    response = AIService.chat_response(message, context)
    elapsed_ms = int((time.time() - t0) * 1000)

    try:
        from models.ai import AiInteraction

        telemetry = context.get("ai_telemetry") or {}
        try:
            confidence_value = telemetry.get("confidence")
            confidence_value = float(confidence_value) if confidence_value is not None else None
        except (TypeError, ValueError):
            confidence_value = None
        log = AiInteraction(
            tenant_id=getattr(current_user, "tenant_id", None),
            user_id=current_user.id,
            query=message[:2000],
            response=str(response)[:4000],
            intent=context.get("intent"),
            was_successful=True,
            response_time_ms=elapsed_ms,
            tool_names=(str(telemetry.get("tool_names") or "")[:2000] or None),
            fallback_path=(str(telemetry.get("fallback_path") or "local")[:50]),
            confidence=confidence_value,
        )
        with atomic_transaction("chat_interaction_log"):
            db.session.add(log)
    except Exception:
        logger.exception("Failed to log AI chat interaction to database")

    try:
        from ai_knowledge.trainer import trainer

        trainer.learn_from_interaction(
            message,
            str(response)[:500],
            current_user.id,
            success=True,
            tenant_id=getattr(current_user, "tenant_id", None),
        )
    except Exception:
        logger.exception("Failed to learn from AI chat interaction")

    state = get_ai_access_state(current_user)
    return success_response(
        data={
            "response": response,
            "ai_enabled": bool(
                state.get("allowed") and state.get("global_enabled") and state.get("tenant_enabled") is not False
            ),
            "ai_mode": ai_mode,
            "user_role": "owner" if current_user.is_owner else "user",
        },
    )
