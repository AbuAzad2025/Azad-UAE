"""AI learning, improvement, and knowledge management routes."""

from flask_babel import gettext

import logging
from flask import request, jsonify
from flask_login import login_required, current_user
from utils.decorators import admin_required, permission_required
from services.ai_service import AIService
from ai_knowledge.core.learning_system import learning_system
from ai_knowledge.expansion.global_knowledge import global_connector, expertise_updater
from ai_knowledge.expansion.knowledge_expansion import knowledge_expander
from ai_knowledge.improvement.self_improvement import self_improvement
from routes.ai_routes import ai_bp

logger = logging.getLogger(__name__)


@ai_bp.route("/contextual-help/<page>", methods=["GET"])
@login_required
@permission_required("view_reports")
def contextual_help(page):
    """❓ API: مساعدة سياقية"""
    user_role = current_user.role.name if current_user.role else "user"
    help_content = AIService.contextual_help(page, user_role)
    return jsonify(help_content)


@ai_bp.route("/learning/status")
@login_required
@permission_required("view_reports")
def learning_status():
    """حالة التعلم الذاتي"""
    try:
        insights = learning_system.get_learning_insights()
        return jsonify({"success": True, "learning_insights": insights})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@ai_bp.route("/learning/evolve", methods=["POST"])
@login_required
@admin_required
def evolve_knowledge():
    """تطوير المعرفة تلقائياً"""
    try:
        evolution = learning_system.evolve_knowledge()
        return jsonify({"success": True, "evolution": evolution})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@ai_bp.route("/improvement/status")
@login_required
@permission_required("view_reports")
def improvement_status():
    """حالة التحسين الذاتي"""
    try:
        status = self_improvement.get_improvement_status()
        return jsonify({"success": True, "improvement_status": status})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@ai_bp.route("/improvement/auto-improve", methods=["POST"])
@login_required
@admin_required
def auto_improve():
    """التحسين التلقائي"""
    try:
        improvements = self_improvement.auto_improve()
        return jsonify({"success": True, "improvements": improvements})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@ai_bp.route("/improvement/progress")
@login_required
@permission_required("view_reports")
def improvement_progress():
    """تتبع تقدم التحسين"""
    try:
        progress = self_improvement.track_progress()
        return jsonify({"success": True, "progress": progress})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@ai_bp.route("/improvement/set-goal", methods=["POST"])
@login_required
@admin_required
def set_improvement_goal():
    """تعيين هدف تحسين"""
    try:
        data = request.get_json(silent=True)
        area = data.get("area")
        target_score = data.get("target_score")
        timeframe = data.get("timeframe", "30_days")

        if not area or not target_score:
            return jsonify(
                {"success": False, "error": gettext("المجال والهدف مطلوبان")}
            ), 400

        result = self_improvement.set_improvement_goal(area, target_score, timeframe)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@ai_bp.route("/global/insights")
@login_required
@permission_required("view_reports")
def global_insights():
    """رؤى عالمية"""
    try:
        insights = global_connector.get_global_insights()
        return jsonify({"success": True, "global_insights": insights})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@ai_bp.route("/global/expertise-update")
@login_required
@admin_required
def update_global_expertise():
    """تحديث الخبرة العالمية"""
    try:
        updates = expertise_updater.update_expertise()
        return jsonify({"success": True, "expertise_updates": updates})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@ai_bp.route("/performance/analysis")
@login_required
@permission_required("view_reports")
def performance_analysis():
    """تحليل الأداء الشامل"""
    try:
        performance = self_improvement.analyze_performance()

        learning_insights = learning_system.get_learning_insights()

        evolution = self_improvement.evolve_capabilities()

        global_insights_data = global_connector.get_global_insights()

        return jsonify(
            {
                "success": True,
                "performance_analysis": {
                    "performance": performance,
                    "learning": learning_insights,
                    "evolution": evolution,
                    "global": global_insights_data,
                },
            }
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@ai_bp.route("/knowledge/add-website", methods=["POST"])
@login_required
@admin_required
def add_knowledge_website():
    """إضافة موقع ويب للمعرفة"""
    try:
        data = request.get_json(silent=True)
        url = data.get("url")
        category = data.get("category", "general")
        description = data.get("description", "")

        if not url:
            return jsonify({"success": False, "error": gettext("الرابط مطلوب")}), 400

        result = knowledge_expander.add_website(url, category, description)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@ai_bp.route("/knowledge/add-document", methods=["POST"])
@login_required
@admin_required
def add_knowledge_document():
    """إضافة مستند للمعرفة"""
    try:
        data = request.get_json(silent=True)
        content = data.get("content")
        title = data.get("title")
        category = data.get("category", "general")
        description = data.get("description", "")

        if not content or not title:
            return jsonify(
                {"success": False, "error": gettext("المحتوى والعنوان مطلوبان")}
            ), 400

        result = knowledge_expander.add_document(content, title, category, description)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@ai_bp.route("/knowledge/search")
@login_required
@permission_required("view_reports")
def search_knowledge():
    """البحث في المعرفة الموسعة"""
    try:
        query = request.args.get("q", "")
        category = request.args.get("category")

        if not query:
            return jsonify(
                {"success": False, "error": gettext("كلمة البحث مطلوبة")}
            ), 400

        result = knowledge_expander.search_knowledge(query, category)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@ai_bp.route("/knowledge/summary")
@login_required
@permission_required("view_reports")
def get_knowledge_summary():
    """📚 API: ملخص المعرفة الموسعة"""
    try:
        result = knowledge_expander.get_knowledge_summary()
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
