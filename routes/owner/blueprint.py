"""Blueprint definition for the owner package — extracted to avoid circular imports."""

from flask import Blueprint

owner_bp = Blueprint("owner", __name__, url_prefix="/owner")
