from flask import Blueprint, jsonify, render_template
from flask_login import login_required, current_user
from services.gamification_service import GamificationService

gamification_bp = Blueprint('gamification', __name__, url_prefix='/gamification')


@gamification_bp.route('/leaderboard')
@login_required
def leaderboard():
    board = GamificationService.get_leaderboard(limit=20)
    return render_template('gamification/leaderboard.html', leaderboard=board)


@gamification_bp.route('/my-stats')
@login_required
def my_stats():
    stats = GamificationService.get_user_stats(current_user.id)
    return jsonify(stats)


@gamification_bp.route('/award/<action>')
@login_required
def award_points(action):
    result = GamificationService.award_points(current_user.id, action)
    return jsonify(result)

