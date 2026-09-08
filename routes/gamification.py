from flask import Blueprint, render_template
from flask_login import current_user, login_required

from services.gamification_service import GamificationService
from utils.api_response import error_response, success_response
from utils.decorators import permission_required
from utils.gamification_service_safe import is_valid_award_action

gamification_bp = Blueprint("gamification", __name__, url_prefix="/gamification")


@gamification_bp.route("/leaderboard")
@login_required
@permission_required("view_reports")
def leaderboard():
    board = GamificationService.get_leaderboard(limit=20)
    return render_template("gamification/leaderboard.html", leaderboard=board)


@gamification_bp.route("/my-stats")
@login_required
@permission_required("view_reports")
def my_stats():
    stats = GamificationService.get_user_stats(current_user.id)
    return success_response(data=stats)


@gamification_bp.route("/award/<action>")
@login_required
@permission_required("admin")
def award_points(action):
    """Server-side curation: only allow whitelisted award actions."""
    if not is_valid_award_action(action):
        return error_response(message="award action not allowed", status_code=400)
    result = GamificationService.award_points(current_user.id, action)
    return success_response(data=result)
