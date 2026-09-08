from flask import Blueprint, render_template
from flask_login import current_user, login_required

from services.gamification_service import GamificationService
from utils.api_response import success_response
from utils.decorators import permission_required

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
    """Server-side curation of gamification rewards.

    Only users with the ``admin`` permission (super_admin, manager,
    owner) can hand out points. The action string is forwarded to
    ``GamificationService.award_points`` which is the authoritative
    validator for the award type — invalid action types are rejected
    there with a domain exception rather than leaking this far up.
    """
    result = GamificationService.award_points(current_user.id, action)
    return success_response(data=result)
