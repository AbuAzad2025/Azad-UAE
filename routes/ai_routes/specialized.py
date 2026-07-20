"""AI specialized routes — automotive, external sources, genius queries."""

from flask_babel import gettext

import logging
from flask import request, jsonify
from flask_login import login_required, current_user
from extensions import csrf, limiter
from utils.decorators import permission_required
from services.ai_service import AIService
from ai_knowledge.knowledge_base import get_automotive_ecu_knowledge
from ai_knowledge.learning.external_learning import (
    get_external_learning,
    LEARNING_SOURCES_CATALOG,
)
from routes.ai_routes import ai_bp

logger = logging.getLogger(__name__)


@ai_bp.route("/neural-status", methods=["GET"])
@login_required
@permission_required("view_reports")
def neural_status():
    """🧠 API: حالة الشبكات العصبية"""
    try:
        status = AIService.get_neural_status()
        return jsonify({"success": True, "status": status})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@ai_bp.route("/automotive-ecu/<code>", methods=["GET"])
@login_required
@permission_required("view_products")
def automotive_ecu_code(code):
    """🚗 API: تشخيص كود OBD-II"""
    try:
        ecu_expert = get_automotive_ecu_knowledge()
        diagnosis = ecu_expert.diagnose_code(code.upper())

        return jsonify({"success": True, "diagnosis": diagnosis})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@ai_bp.route("/automotive-sensor/<sensor>", methods=["GET"])
@login_required
@permission_required("view_products")
def automotive_sensor(sensor):
    """🔧 API: معلومات حساس محدد"""
    try:
        ecu_expert = get_automotive_ecu_knowledge()
        info = ecu_expert.get_sensor_info(sensor)

        return jsonify({"success": True, "sensor_info": info})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@ai_bp.route("/external-sources", methods=["GET"])
@login_required
@permission_required("view_reports")
def external_sources():
    """📚 API: قائمة مصادر التعلم الخارجية"""
    try:
        learning = get_external_learning()
        sources = learning.get_knowledge_sources_list()
        stats = learning.get_statistics()

        return jsonify(
            {
                "success": True,
                "sources": sources,
                "statistics": stats,
                "catalog": LEARNING_SOURCES_CATALOG,
            }
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@ai_bp.route("/ask-genius", methods=["POST"])
@login_required
@permission_required("view_reports")
@limiter.limit("30 per minute")
def ask_genius():
    """🌟 API: اسأل العبقري - الواجهة الموحدة (JSON callers must send X-CSRFToken)."""
    try:
        data = request.get_json(silent=True)
        question = data.get("question", "")
        context = data.get("context", {})

        if not question:
            return jsonify({"success": False, "error": gettext("السؤال مطلوب")}), 400

        result = AIService.ask_genius(question=question, context=context, user_id=current_user.id)

        return jsonify({"success": True, "result": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@ai_bp.route("/quick-calc", methods=["POST"])
@csrf.exempt
@login_required
@limiter.limit("30 per minute")
def quick_calc():
    """⚡ API: حسابات سريعة — whitelist formulas only; no DB, files, or external calls."""
    try:
        data = request.get_json(silent=True)
        formula = data.get("formula", "")
        params = data.get("params", {})

        if not formula:
            return jsonify({"success": False, "error": gettext("الصيغة مطلوبة")}), 400

        result = AIService.quick_calculate(formula, **params)

        return jsonify({"success": result.get("success", False), "result": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@ai_bp.route("/transformers-understand", methods=["POST"])
@csrf.exempt
@login_required
@limiter.limit("30 per minute")
def transformers_understand():
    """🤖 API: فهم بالـ Transformers — local in-memory only; no DB, files, or ERP actions."""
    try:
        data = request.get_json(silent=True)
        text = data.get("text", "")

        if not text:
            return jsonify({"success": False, "error": gettext("النص مطلوب")}), 400

        understanding = AIService.understand_with_transformers(text)

        return jsonify({"success": True, "understanding": understanding})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
