"""Blueprint definition for the ai_routes package — extracted to avoid circular imports."""

from flask import Blueprint

ai_bp: Blueprint = Blueprint("ai", __name__, url_prefix="/ai")
