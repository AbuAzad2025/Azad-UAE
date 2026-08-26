"""AI specialized routes — automotive, external sources, genius queries."""

import logging

from flask import request
from flask_babel import gettext
from flask_login import current_user, login_required

from ai_knowledge.knowledge_base import get_automotive_ecu_knowledge
from ai_knowledge.learning.external_learning import (
    LEARNING_SOURCES_CATALOG,
    get_external_learning,
)
from extensions import limiter
from services.ai_service import AIService
from utils.api_response import error_response, success_response
from utils.decorators import permission_required

from .blueprint import ai_bp

logger = logging.getLogger(__name__)


@ai_bp.route("/neural-status", methods=["GET"])
@login_required
@permission_required("view_reports")
def neural_status():
    """🧠 API: حالة الشبكات العصبية"""
    try:
        status = AIService.get_neural_status()
        return success_response(data={"status": status})
    except Exception as e:
        return error_response(message=str(e), status_code=200)


@ai_bp.route("/automotive-ecu/<code>", methods=["GET"])
@login_required
@permission_required("view_products")
def automotive_ecu_code(code):
    """🚗 API: تشخيص كود OBD-II"""
    try:
        ecu_expert = get_automotive_ecu_knowledge()
        diagnosis = ecu_expert.diagnose_code(code.upper())

        return success_response(data={"diagnosis": diagnosis})
    except Exception as e:
        return error_response(message=str(e), status_code=200)


@ai_bp.route("/automotive-sensor/<sensor>", methods=["GET"])
@login_required
@permission_required("view_products")
def automotive_sensor(sensor):
    """🔧 API: معلومات حساس محدد"""
    try:
        ecu_expert = get_automotive_ecu_knowledge()
        info = ecu_expert.get_sensor_info(sensor)

        return success_response(data={"sensor_info": info})
    except Exception as e:
        return error_response(message=str(e), status_code=200)


@ai_bp.route("/external-sources", methods=["GET"])
@login_required
@permission_required("view_reports")
def external_sources():
    """📚 API: قائمة مصادر التعلم الخارجية"""
    try:
        learning = get_external_learning()
        sources = learning.get_knowledge_sources_list()
        stats = learning.get_statistics()

        return success_response(
            data={
                "sources": sources,
                "statistics": stats,
                "catalog": LEARNING_SOURCES_CATALOG,
            },
        )
    except Exception as e:
        return error_response(message=str(e), status_code=200)


@ai_bp.route("/ask-genius", methods=["POST"])
@login_required
@permission_required("view_reports")
@limiter.limit("30 per minute")
def ask_genius():
    """🌟 API: اسأل العبقري - الواجهة الموحدة (JSON callers must send X-CSRFToken)."""
    try:
        data = request.get_json(silent=True)
        if not data:
            return error_response(
                message="Request body must be JSON",
                status_code=400,
            )
        question = data.get("question", "")
        context = data.get("context", {})

        if not question:
            return error_response(
                message=gettext("السؤال مطلوب"),
                status_code=400,
            )

        result = AIService.ask_genius(question=question, context=context, user_id=current_user.id)

        return success_response(data={"result": result})
    except Exception as e:
        return error_response(message=str(e), status_code=200)


@ai_bp.route("/quick-calc", methods=["POST"])
@login_required
@limiter.limit("30 per minute")
def quick_calc():
    """⚡ API: حسابات سريعة — whitelist formulas only; no DB, files, or external calls."""
    try:
        data = request.get_json(silent=True)
        if not data:
            return error_response(
                message="Request body must be JSON",
                status_code=400,
            )
        formula = data.get("formula", "")
        params = data.get("params", {})

        if not formula:
            return error_response(
                message=gettext("الصيغة مطلوبة"),
                status_code=400,
            )

        result = AIService.quick_calculate(formula, **params)

        return success_response(
            data={"success": result.get("success", False), "result": result},
        )
    except Exception as e:
        return error_response(message=str(e), status_code=200)


@ai_bp.route("/transformers-understand", methods=["POST"])
@login_required
@limiter.limit("30 per minute")
def transformers_understand():
    """🤖 API: فهم بالـ Transformers — local in-memory only; no DB, files, or ERP actions."""
    try:
        data = request.get_json(silent=True)
        if not data:
            return error_response(
                message="Request body must be JSON",
                status_code=400,
            )
        text = data.get("text", "")

        if not text:
            return error_response(
                message=gettext("النص مطلوب"),
                status_code=400,
            )

        understanding = AIService.understand_with_transformers(text)

        return success_response(data={"understanding": understanding})
    except Exception as e:
        return error_response(message=str(e), status_code=200)
