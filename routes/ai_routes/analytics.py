"""AI analytics and prediction routes."""

import logging
from flask import request, jsonify
from flask_login import login_required
from utils.decorators import permission_required
from services.ai_service import AIService
from routes.ai_routes import ai_bp

logger = logging.getLogger(__name__)


@ai_bp.route("/predict-sales", methods=["GET"])
@login_required
@permission_required("view_reports")
def predict_sales():
    """🔮 API: توقع المبيعات"""
    days = request.args.get("days", 7, type=int)
    prediction = AIService.predict_sales_trend(days)
    return jsonify(prediction)


@ai_bp.route("/analyze-margins", methods=["GET"])
@login_required
@permission_required("view_reports")
def analyze_margins():
    """💰 API: تحليل هوامش الربح"""
    analysis = AIService.analyze_profit_margins()
    return jsonify(analysis)


@ai_bp.route("/detect-patterns", methods=["GET"])
@login_required
@permission_required("view_reports")
def detect_patterns():
    """🔍 API: كشف الأنماط"""
    patterns = AIService.detect_sales_patterns()
    return jsonify(patterns)


@ai_bp.route("/inventory-health", methods=["GET"])
@login_required
@permission_required("manage_warehouse")
def inventory_health():
    """📦 API: صحة المخزون"""
    health = AIService.analyze_inventory_health()
    return jsonify(health)


@ai_bp.route("/deep-analysis", methods=["GET"])
@login_required
@permission_required("view_reports")
def deep_analysis():
    """📊 API: تحليل عميق شامل"""
    analysis = AIService.deep_business_analysis()
    return jsonify(analysis)


@ai_bp.route("/cash-flow-prediction", methods=["GET"])
@login_required
@permission_required("view_ledger")
def cash_flow_prediction():
    """💵 API: توقع التدفق النقدي"""
    days = request.args.get("days", 30, type=int)
    prediction = AIService.predict_cash_flow(days)
    return jsonify(prediction)


@ai_bp.route("/smart-price", methods=["POST"])
@login_required
@permission_required("view_products")
def smart_price():
    """💎 API: محرك التسعير الذكي الخارق"""
    data = request.get_json(silent=True) or {}
    product_id = data.get("product_id")
    customer_id = data.get("customer_id")
    quantity = data.get("quantity", 1)

    if not product_id or not customer_id:
        return jsonify({"error": "Product and Customer required"}), 400

    pricing = AIService.smart_pricing_engine(product_id, customer_id, quantity)

    if not pricing:
        return jsonify({"error": "Not found"}), 404

    return jsonify(pricing)


@ai_bp.route("/churn-prediction", methods=["GET"])
@login_required
@permission_required("manage_customers")
def churn_prediction():
    """⚠️ API: توقع فقدان العملاء"""
    prediction = AIService.predict_customer_churn()
    return jsonify(prediction)


@ai_bp.route("/optimize-inventory", methods=["GET"])
@login_required
@permission_required("manage_warehouse")
def optimize_inventory():
    """📦 API: تحسين مستويات المخزون"""
    optimization = AIService.optimize_inventory_levels()
    return jsonify(optimization)


@ai_bp.route("/business-insights", methods=["GET"])
@login_required
@permission_required("view_reports")
def business_insights():
    """💡 API: رؤى الأعمال التلقائية"""
    insights = AIService.generate_business_insights()

    formatted_insights = []
    for insight in insights:
        formatted_insights.append(
            {
                "icon": "⚠️" if insight["type"] == "warning" else "ℹ️",
                "title": insight["title"],
                "insight": insight["message"],
                "action": insight["action"],
            }
        )

    return jsonify({"success": True, "insights": formatted_insights})
