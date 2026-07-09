from models.dashboard import DashboardWidget, UserDashboardLayout
from extensions import db
from utils.db_safety import atomic_transaction
from flask import current_app
from sqlalchemy.exc import IntegrityError

class DashboardService:
    @staticmethod
    def get_available_widgets(user):
        """
        Get widgets available to the user based on permissions and roles
        """
        widgets = DashboardWidget.query.filter_by(is_enabled=True).all()
        # TODO: Implement permission/role filtering
        return widgets

    @staticmethod
    def get_user_layout(tenant_id, user_id):
        """
        Get the saved layout for a user, or a default layout if none exists
        """
        layout = UserDashboardLayout.query.filter_by(tenant_id=tenant_id, user_id=user_id).first()
        if layout:
            return layout.layout_json
        return DashboardService.get_default_layout()

    @staticmethod
    def get_default_layout():
        """
        Define a safe default layout
        """
        return {
            "widgets": [
                {"key": "sales_summary", "x": 0, "y": 0, "w": 6, "h": 2},
                {"key": "cash_summary", "x": 6, "y": 0, "w": 6, "h": 2}
            ]
        }

    @staticmethod
    def save_user_layout(tenant_id, user_id, layout_json):
        """
        Save a user's custom layout
        """
        if not isinstance(layout_json, dict) or len(str(layout_json)) > 10000:
            raise ValueError("Invalid layout format or size")

        layout = UserDashboardLayout.query.filter_by(tenant_id=tenant_id, user_id=user_id).first()
        if layout:
            layout.layout_json = layout_json
        else:
            layout = UserDashboardLayout(tenant_id=tenant_id, user_id=user_id, layout_json=layout_json)
            db.session.add(layout)
        
        try:
            db.session.flush()
        except IntegrityError:
            db.session.rollback()
            raise
        return layout
