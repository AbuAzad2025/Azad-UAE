from datetime import datetime, timezone
from decimal import Decimal
from extensions import db
from models import CRMLead, CRMStage, CRMTeam, CRMActivity, Customer
from utils.tenanting import get_active_tenant_id
from utils.branching import branch_scope_id_for
from utils.auth_helpers import is_global_owner_user


class CRMLeadService:

    @staticmethod
    def _validate_tenant(lead, user):
        tid = get_active_tenant_id(user)
        if tid is not None and int(lead.tenant_id) != int(tid):
            raise ValueError('العميل المتوقع لا ينتمي إلى شركتك النشطة.')

    @staticmethod
    def _branch_scope_check(user, branch_id=None):
        if is_global_owner_user(user):
            return
        scoped = branch_scope_id_for(user)
        if scoped is not None and branch_id is not None and int(branch_id) != int(scoped):
            raise ValueError('لا يمكنك التعامل مع عميل متوقع من فرع آخر.')

    @staticmethod
    def create_lead(data, user):
        tid = get_active_tenant_id(user)
        if not tid and not is_global_owner_user(user):
            raise ValueError('لا توجد شركة نشطة.')
        from models.branch import Branch
        branch_id = data.get('branch_id')
        CRMLeadService._branch_scope_check(user, branch_id)
        if branch_id:
            branch = db.session.get(Branch, int(branch_id))
            if branch and tid is None:
                tid = int(branch.tenant_id)
        stage_id = data.get('stage_id')
        if stage_id:
            stage = db.session.get(CRMStage, int(stage_id))
            if stage and int(stage.tenant_id) != int(tid or 0):
                raise ValueError('المرحلة لا تنتمي إلى شركتك.')
        lead = CRMLead(
            tenant_id=int(tid) if tid else 0,
            branch_id=int(branch_id) if branch_id else None,
            name=data.get('name'),
            email=data.get('email'),
            phone=data.get('phone'),
            company=data.get('company'),
            customer_id=int(data['customer_id']) if data.get('customer_id') else None,
            stage_id=int(stage_id) if stage_id else None,
            team_id=int(data['team_id']) if data.get('team_id') else None,
            assigned_user_id=int(data['assigned_user_id']) if data.get('assigned_user_id') else None,
            expected_revenue=Decimal(str(data.get('expected_revenue', 0))),
            priority=data.get('priority', 'medium'),
            source=data.get('source'),
            description=data.get('description'),
            status='open',
        )
        db.session.add(lead)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        return lead

    @staticmethod
    def update_lead(lead_id, data, user):
        lead = db.session.get(CRMLead, int(lead_id))
        if not lead:
            raise ValueError('العميل المتوقع غير موجود.')
        CRMLeadService._validate_tenant(lead, user)
        CRMLeadService._branch_scope_check(user, lead.branch_id)
        for field in ('name', 'email', 'phone', 'company', 'description', 'source'):
            if field in data:
                setattr(lead, field, data[field])
        if 'expected_revenue' in data:
            lead.expected_revenue = Decimal(str(data['expected_revenue']))
        if 'priority' in data:
            lead.priority = data['priority']
        if 'customer_id' in data:
            lead.customer_id = int(data['customer_id']) if data['customer_id'] else None
        if 'assigned_user_id' in data:
            lead.assigned_user_id = int(data['assigned_user_id']) if data['assigned_user_id'] else None
        if data.get('stage_id'):
            stage = db.session.get(CRMStage, int(data['stage_id']))
            if stage and int(stage.tenant_id) != int(lead.tenant_id):
                raise ValueError('المرحلة لا تنتمي إلى شركتك.')
            lead.stage_id = int(data['stage_id'])
            if stage and stage.is_won:
                lead.status = 'won'
                lead.closed_at = datetime.now(timezone.utc)
            elif stage and stage.is_lost:
                lead.status = 'lost'
                lead.closed_at = datetime.now(timezone.utc)
        lead.updated_at = datetime.now(timezone.utc)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        return lead

    @staticmethod
    def move_stage(lead_id, stage_id, user):
        lead = db.session.get(CRMLead, int(lead_id))
        if not lead:
            raise ValueError('العميل المتوقع غير موجود.')
        CRMLeadService._validate_tenant(lead, user)
        stage = db.session.get(CRMStage, int(stage_id))
        if not stage or int(stage.tenant_id) != int(lead.tenant_id):
            raise ValueError('المرحلة غير صالحة.')
        lead.stage_id = int(stage_id)
        if stage.is_won:
            lead.status = 'won'
            lead.closed_at = datetime.now(timezone.utc)
        elif stage.is_lost:
            lead.status = 'lost'
            lead.closed_at = datetime.now(timezone.utc)
        else:
            lead.status = 'open'
        lead.updated_at = datetime.now(timezone.utc)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        return lead

    @staticmethod
    def get_lead(lead_id, user):
        lead = db.session.get(CRMLead, int(lead_id))
        if not lead:
            raise ValueError('العميل المتوقع غير موجود.')
        CRMLeadService._validate_tenant(lead, user)
        return lead

    @staticmethod
    def search_leads(filters, user):
        tid = get_active_tenant_id(user)
        query = CRMLead.query.filter(CRMLead.is_active == True)
        if tid is not None:
            query = query.filter(CRMLead.tenant_id == tid)
        if not is_global_owner_user(user):
            scoped = branch_scope_id_for(user)
            if scoped is not None:
                query = query.filter(CRMLead.branch_id == scoped)
        if filters.get('stage_id'):
            query = query.filter(CRMLead.stage_id == int(filters['stage_id']))
        if filters.get('status'):
            query = query.filter(CRMLead.status == filters['status'])
        if filters.get('assigned_user_id'):
            query = query.filter(CRMLead.assigned_user_id == int(filters['assigned_user_id']))
        if filters.get('search'):
            q = f"%{filters['search']}%"
            query = query.filter(
                db.or_(CRMLead.name.ilike(q), CRMLead.email.ilike(q), CRMLead.phone.ilike(q))
            )
        return query.order_by(CRMLead.created_at.desc()).all()

    @staticmethod
    def get_pipeline_stats(user):
        tid = get_active_tenant_id(user)
        stages = CRMStage.query.filter(
            CRMStage.is_active == True,
            CRMStage.tenant_id == tid,
        ).order_by(CRMStage.sequence).all() if tid else []
        stats = []
        for stage in stages:
            q = CRMLead.query.filter(
                CRMLead.stage_id == stage.id,
                CRMLead.is_active == True,
            )
            if tid is not None:
                q = q.filter(CRMLead.tenant_id == tid)
            total = q.count()
            revenue = db.session.query(db.func.sum(CRMLead.expected_revenue)).filter(
                CRMLead.stage_id == stage.id,
                CRMLead.is_active == True,
                CRMLead.tenant_id == tid,
            ).scalar() or 0 if tid else 0
            stats.append({
                'stage': stage.to_dict(),
                'count': total,
                'revenue': float(revenue),
            })
        return stats

    @staticmethod
    def add_activity(lead_id, data, user):
        lead = db.session.get(CRMLead, int(lead_id))
        if not lead:
            raise ValueError('العميل المتوقع غير موجود.')
        CRMLeadService._validate_tenant(lead, user)
        activity = CRMActivity(
            tenant_id=lead.tenant_id,
            lead_id=lead.id,
            user_id=user.id,
            activity_type=data.get('activity_type', 'call'),
            summary=data.get('summary'),
            date_deadline=datetime.fromisoformat(data['date_deadline']) if data.get('date_deadline') else None,
        )
        db.session.add(activity)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        return activity
