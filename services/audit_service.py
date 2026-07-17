from extensions import db
from models import AuditLog, User


class AuditService:
    @staticmethod
    def get_audit_logs_data(tid, page, per_page, action, user_id):
        query = AuditLog.query.filter_by(tenant_id=tid)

        # فلترة حسب العملية
        if action:
            query = query.filter_by(action=action)

        # فلترة حسب المستخدم
        if user_id:
            query = query.filter_by(user_id=user_id)

        # الترتيب والتقسيم
        pagination = query.order_by(AuditLog.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )

        # إحصائيات سريعة
        stats = {
            "total": AuditLog.query.filter_by(tenant_id=tid).count(),
            "today": AuditLog.query.filter(
                db.func.date(AuditLog.created_at) == db.func.current_date(),
                AuditLog.tenant_id == tid,
            ).count(),
            "creates": AuditLog.query.filter_by(action="create", tenant_id=tid).count(),
            "updates": AuditLog.query.filter_by(action="update", tenant_id=tid).count(),
            "deletes": AuditLog.query.filter_by(action="delete", tenant_id=tid).count(),
        }

        # قائمة المستخدمين للفلتر
        users = User.query.filter_by(is_active=True, tenant_id=tid).all()

        return pagination.items, pagination, stats, users
