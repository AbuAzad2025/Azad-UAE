from flask import Blueprint, render_template
from flask_login import current_user, login_required

from services.gamification_service import GamificationService
from utils.api_response import success_response

gamification_bp = Blueprint("gamification", __name__, url_prefix="/gamification")


@gamification_bp.route("/leaderboard")
@login_required
def leaderboard():
    board = GamificationService.get_leaderboard(limit=20)
    return render_template("gamification/leaderboard.html", leaderboard=board)


@gamification_bp.route("/my-stats")
@login_required
def my_stats():
    stats = GamificationService.get_user_stats(current_user.id)
    return success_response(data=stats)


@gamification_bp.route("/award/<action>")
@login_required
def award_points(action):
    result = GamificationService.award_points(current_user.id, action)
    return success_response(data=result)
