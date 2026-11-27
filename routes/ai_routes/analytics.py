"""AI analytics and prediction routes."""

import logging
from functools import wraps

from flask import request
from flask_login import current_user, login_required

from services.ai_service import AIService
from utils.api_response import error_response, success_response
from utils.auth_helpers import is_platform_authority
from utils.decorators import permission_required
from utils.tenanting import get_active_tenant_id

from .blueprint import ai_bp

logger = logging.getLogger(__name__)


def _tenant_guard():
    """Fail closed when a tenant-scoped caller has no active company."""

    tenant_id = get_active_tenant_id(current_user)
    if tenant_id is None and not is_platform_authority(current_user):
        return None, error_response(message="No active tenant context", status_code=403)
    return tenant_id, None


def tenant_scoped(view):
    """Decorator: require an active tenant for non-platform callers."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        _tid, error = _tenant_guard()
        if error is not None:
            return error
        return view(*args, **kwargs)

    return wrapped


def _can_see_costs() -> bool:
    """Cost/profit figures require explicit cost visibility."""

    check = getattr(current_user, "can_see_costs", None)
    if callable(check):
        try:
            if bool(check()):
                return True
        except Exception:
            logger.debug("can_see_costs check failed", exc_info=True)
    has_permission = getattr(current_user, "has_permission", None)
    if callable(has_permission):
        try:
            return bool(has_permission("view_costs"))
        except Exception:
            logger.debug("view_costs check failed", exc_info=True)
    return False


@ai_bp.route("/predict-sales", methods=["GET"])
@login_required
@permission_required("view_reports")
@tenant_scoped
def predict_sales():
    """🔮 API: توقع المبيعات"""
    days = request.args.get("days", 7, type=int)
    prediction = AIService.predict_sales_trend(days)
    return success_response(data=prediction)


@ai_bp.route("/analyze-margins", methods=["GET"])
@login_required
@permission_required("view_reports")
@tenant_scoped
def analyze_margins():
    """💰 API: تحليل هوامش الربح — cost visibility required."""
    if not _can_see_costs():
        return error_response(message="Cost visibility required (view_costs)", status_code=403)
    analysis = AIService.analyze_profit_margins()
    # Empty data is a valid grounded answer, not an HTTP error: preserve the
    # envelope and let the UI render the service's own empty-state message.
    return success_response(data=analysis)


@ai_bp.route("/detect-patterns", methods=["GET"])
@login_required
@permission_required("view_reports")
@tenant_scoped
def detect_patterns():
    """🔍 API: كشف الأنماط"""
    patterns = AIService.detect_sales_patterns()
    return success_response(data=patterns)


@ai_bp.route("/inventory-health", methods=["GET"])
@login_required
@permission_required("manage_warehouse")
@tenant_scoped
def inventory_health():
    """📦 API: صحة المخزون"""
    health = AIService.analyze_inventory_health()
    return success_response(data=health)


@ai_bp.route("/deep-analysis", methods=["GET"])
@login_required
@permission_required("view_reports")
@tenant_scoped
def deep_analysis():
    """📊 API: تحليل عميق شامل"""
    analysis = AIService.deep_business_analysis()
    return success_response(data=analysis)


@ai_bp.route("/cash-flow-prediction", methods=["GET"])
@login_required
@permission_required("view_ledger")
@tenant_scoped
def cash_flow_prediction():
    """💵 API: توقع التدفق النقدي"""
    days = request.args.get("days", 30, type=int)
    prediction = AIService.predict_cash_flow(days)
    return success_response(data=prediction)


@ai_bp.route("/smart-price", methods=["POST"])
@login_required
@permission_required("view_products")
@tenant_scoped
def smart_price():
    """💎 API: محرك التسعير الذكي الخارق"""
    data = request.get_json(silent=True) or {}
    product_id = data.get("product_id")
    customer_id = data.get("customer_id")
    quantity = data.get("quantity", 1)

    if not product_id or not customer_id:
        return error_response(
            message="Product and Customer required",
            status_code=400,
        )

    pricing = AIService.smart_pricing_engine(product_id, customer_id, quantity)

    if not pricing:
        return error_response(message="Not found", status_code=404)

    return success_response(data=pricing)


@ai_bp.route("/churn-prediction", methods=["GET"])
@login_required
@permission_required("manage_customers")
@tenant_scoped
def churn_prediction():
    """⚠️ API: توقع فقدان العملاء"""
    prediction = AIService.predict_customer_churn()
    return success_response(data=prediction)


@ai_bp.route("/optimize-inventory", methods=["GET"])
@login_required
@permission_required("manage_warehouse")
@tenant_scoped
def optimize_inventory():
    """📦 API: تحسين مستويات المخزون"""
    optimization = AIService.optimize_inventory_levels()
    return success_response(data=optimization)


@ai_bp.route("/business-insights", methods=["GET"])
@login_required
@permission_required("view_reports")
@tenant_scoped
def business_insights():
    """💡 API: رؤى الأعمال التلقائية"""
    insights = AIService.generate_business_insights() or []
    if isinstance(insights, dict) and insights.get("success") is False:
        return error_response(message=insights.get("message") or "No data", status_code=404)

    formatted_insights = []
    for insight in insights:
        if not isinstance(insight, dict):
            continue
        formatted_insights.append(
            {
                "icon": "⚠️" if insight.get("type") == "warning" else "ℹ️",
                "title": str(insight.get("title") or ""),
                "insight": str(insight.get("message") or ""),
                "action": str(insight.get("action") or ""),
            }
        )

    return success_response(data={"insights": formatted_insights})
