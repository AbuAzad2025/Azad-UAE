"""AI Routes Package — Modular sub-blueprint structure."""

from flask_babel import gettext

from flask import (
    render_template,
    request,
    jsonify,
    g,
    flash,
    redirect,
    url_for,
)
from flask_login import current_user
from extensions import db, limiter
from services.logging_core import LoggingCore
from services.ai_service import AIService
from services.stock_service import StockService
from utils.ai_access import get_ai_access_state, ai_level_allows
from utils.tenanting import get_active_tenant_id, assign_tenant_id

from .blueprint import ai_bp

from ai_knowledge.core.conversation_store import (
    get_context as _get_conversation_context,
    set_context as _set_conversation_context,
    clear_context as _clear_conversation_context,
)
from utils.context_managers import AutoSaveCtx as _AutoSaveCtx

# ── Sub-module imports ───────────────────────────────────────────
# Each sub-module registers its routes on the shared ai_bp.
from . import shared  # helpers loaded first
from . import chat
from . import actions
from . import assistant
from . import analytics
from . import knowledge
from . import system
from . import specialized

# Re-export symbols for backward compatibility with routes.ai namespace
from .shared import (
    smart_listener,
    train_local_ai,
    apply_smart_listeners,
    create_final_options,
    _conversation_ctx,
)
from .actions import _process_user_action, _user_can_ai_execute_actions
from .assistant import (
    _intelligent_column_detector,
    _process_excel_intelligently,
    _train_ai_from_excel,
)

_conversation_set = _set_conversation_context
_conversation_clear = _clear_conversation_context

# ── Request lifecycle hooks ──────────────────────────────────────


@ai_bp.before_request
def _enforce_ai_access_policy():
    """Apply effective AI availability (global + tenant) before serving AI routes."""
    state = get_ai_access_state(current_user)
    g.ai_access_state = state

    # Keep assistant/config UI reachable so we can display exact disable reason.
    if request.endpoint in ("ai.config", "ai.assistant_page"):
        return None

    if state.get("allowed"):
        endpoint_caps = {
            "ai.chat": "basic",
            "ai.predict_sales": "advanced",
            "ai.analyze_margins": "advanced",
            "ai.detect_patterns": "advanced",
            "ai.inventory_health": "advanced",
            "ai.business_insights": "advanced",
            "ai.deep_analysis": "advanced",
            "ai.cash_flow_prediction": "advanced",
            "ai.churn_prediction": "advanced",
            "ai.optimize_inventory": "advanced",
            "ai.ask_genius": "advanced",
            "ai.upload_excel": "execute",
            "ai.add_customer": "execute",
            "ai.system_add_customer": "execute",
        }
        required_cap = endpoint_caps.get(request.endpoint or "", "basic")
        if not state.get("is_platform_user") and not ai_level_allows(state.get("ai_level") or "", required_cap):
            msg = gettext(f"مستوى AI الحالي ({state.get('ai_level')}) لا يسمح بهذه العملية.")
            wants_json = request.path.startswith("/ai/") and (
                request.is_json or "application/json" in (request.headers.get("Accept") or "")
            )
            if wants_json:
                return (
                    jsonify({"success": False, "error": msg, "required": required_cap}),
                    403,
                )
            flash(msg, "warning")
            return redirect(url_for("ai.assistant_page"))
        return None

    reason = state.get("reason")
    message = gettext("المساعد الذكي غير متاح لهذا الحساب حالياً.")
    if reason == "global_disabled":
        message = gettext("تم إيقاف المساعد الذكي من إعدادات المنصة.")
    elif reason == "tenant_disabled":
        message = gettext("تم إيقاف المساعد الذكي لهذا التينانت من لوحة المنصة.")
    elif reason == "missing_tenant":
        message = gettext("لا يوجد تينانت نشط مرتبط بهذا الحساب.")

    wants_json = request.path.startswith("/ai/") and (
        request.is_json or "application/json" in (request.headers.get("Accept") or "")
    )
    if wants_json:
        return jsonify({"success": False, "error": message, "reason": reason}), 403

    flash(message, "warning")
    return redirect(url_for("ai.assistant_page"))


@ai_bp.after_request
def _audit_ai_requests(response):
    """Unified AI audit trail: endpoint, tenant context, status, success/failure."""
    try:
        endpoint = request.endpoint or ""
        if not endpoint.startswith("ai."):
            return response
        state = getattr(g, "ai_access_state", None) or get_ai_access_state(current_user)
        status = int(getattr(response, "status_code", 0) or 0)
        LoggingCore.log_audit(
            action="ai_request",
            table_name="ai",
            record_id=0,
            changes={
                "endpoint": endpoint,
                "method": request.method,
                "path": request.path,
                "status_code": status,
                "ok": status < 400,
                "tenant_id": state.get("tenant_id"),
                "global_enabled": state.get("global_enabled"),
                "tenant_enabled": state.get("tenant_enabled"),
                "ai_level": state.get("ai_level"),
                "is_platform_user": state.get("is_platform_user"),
            },
        )
    except Exception:
        LoggingCore.log_error(
            message="Failed to write AI audit trail",
            category="AI",
            source="routes.ai._audit_ai_requests",
            level="WARNING",
        )
    return response


__all__ = [
    "ai_bp",
    "shared",
    "chat",
    "actions",
    "assistant",
    "analytics",
    "knowledge",
    "system",
    "specialized",
    "smart_listener",
    "train_local_ai",
    "apply_smart_listeners",
    "create_final_options",
    "_AutoSaveCtx",
    "_conversation_ctx",
    "_get_conversation_context",
    "_process_user_action",
    "_user_can_ai_execute_actions",
    "_intelligent_column_detector",
    "_process_excel_intelligently",
    "_train_ai_from_excel",
    "render_template",
    "db",
    "limiter",
    "get_active_tenant_id",
    "assign_tenant_id",
    "LoggingCore",
    "AIService",
    "StockService",
]
