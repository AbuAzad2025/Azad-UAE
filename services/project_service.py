import logging
from datetime import datetime, timezone, date
from decimal import Decimal
from extensions import db
from models import Project, TaskStage, Task, Timesheet, ProjectMember
from utils.tenanting import get_active_tenant_id
from utils.branching import branch_scope_id_for
from utils.auth_helpers import is_global_owner_user

logger = logging.getLogger(__name__)


class ProjectService:
    @staticmethod
    def _validate_tenant(record, user):
        tid = get_active_tenant_id(user)
        if tid is not None and int(record.tenant_id) != int(tid):
            raise ValueError("السجل لا ينتمي إلى شركتك النشطة.")

    @staticmethod
    def create_project(data, user):
        tid = get_active_tenant_id(user)
        if not tid and not is_global_owner_user(user):
            raise ValueError("لا توجد شركة نشطة.")
        if not data.get("name"):
            raise ValueError("اسم المشروع مطلوب.")
        project = Project(
            tenant_id=int(tid) if tid else 0,
            name=data["name"],
            name_ar=data.get("name_ar"),
            description=data.get("description"),
            customer_id=int(data["customer_id"]) if data.get("customer_id") else None,
            status=data.get("status", "planning"),
            date_start=(
                datetime.fromisoformat(data["date_start"])
                if data.get("date_start")
                else None
            ),
            date_end=(
                datetime.fromisoformat(data["date_end"])
                if data.get("date_end")
                else None
            ),
            color=data.get("color", "#10b981"),
        )
        db.session.add(project)
        try:
            db.session.flush()
        except Exception:
            logger.exception("Failed to flush project creation")
            raise
        default_stages = [
            ("To Do", "للتنفيذ", 0, "#6b7280"),
            ("In Progress", "قيد التنفيذ", 1, "#3b82f6"),
            ("Done", "منجز", 2, "#10b981"),
        ]
        for sname, sname_ar, seq, color in default_stages:
            stage = TaskStage(
                tenant_id=project.tenant_id,
                project_id=project.id,
                name=sname,
                name_ar=sname_ar,
                sequence=seq,
                is_closed=(sname == "Done"),
                color=color,
            )
            db.session.add(stage)
        try:
            db.session.flush()
        except Exception:
            logger.exception("Failed to flush project default stages")
            raise
        return project

    @staticmethod
    def get_project(project_id, user):
        project = db.session.get(Project, int(project_id))
        if not project:
            raise ValueError("المشروع غير موجود.")
        ProjectService._validate_tenant(project, user)
        return project

    @staticmethod
    def update_project(project_id, data, user):
        project = ProjectService.get_project(project_id, user)
        for field in ("name", "name_ar", "description", "status", "color"):
            if field in data:
                setattr(project, field, data[field])
        if "date_start" in data:
            project.date_start = (
                datetime.fromisoformat(data["date_start"])
                if data["date_start"]
                else None
            )
        if "date_end" in data:
            project.date_end = (
                datetime.fromisoformat(data["date_end"]) if data["date_end"] else None
            )
        if "customer_id" in data:
            project.customer_id = (
                int(data["customer_id"]) if data["customer_id"] else None
            )
        project.updated_at = datetime.now(timezone.utc)
        try:
            db.session.flush()
        except Exception:
            logger.exception("Failed to flush project update")
            raise
        return project

    @staticmethod
    def list_projects(user):
        tid = get_active_tenant_id(user)
        query = Project.query.filter(Project.is_active)
        if tid is not None:
            query = query.filter(Project.tenant_id == tid)
        if not is_global_owner_user(user):
            scoped = branch_scope_id_for(user)
            if scoped is not None:
                query = query.filter(Project.branch_id == scoped)
        return query.order_by(Project.created_at.desc()).all()

    @staticmethod
    def create_task(project_id, data, user):
        project = ProjectService.get_project(project_id, user)
        if not data.get("name"):
            raise ValueError("اسم المهمة مطلوب.")
        stage_id = data.get("stage_id")
        if stage_id:
            stage = db.session.get(TaskStage, int(stage_id))
            if not stage or int(stage.project_id) != int(project_id):
                raise ValueError("المرحلة غير صالحة لهذا المشروع.")
        task = Task(
            tenant_id=project.tenant_id,
            project_id=project.id,
            stage_id=int(stage_id) if stage_id else None,
            parent_id=int(data["parent_id"]) if data.get("parent_id") else None,
            name=data["name"],
            description=data.get("description"),
            assigned_user_id=(
                int(data["assigned_user_id"]) if data.get("assigned_user_id") else None
            ),
            priority=data.get("priority", "medium"),
            date_deadline=(
                datetime.fromisoformat(data["date_deadline"])
                if data.get("date_deadline")
                else None
            ),
            planned_hours=Decimal(str(data.get("planned_hours", 0))),
        )
        db.session.add(task)
        try:
            db.session.flush()
        except Exception:
            logger.exception("Failed to flush task creation")
            raise
        return task

    @staticmethod
    def move_task(task_id, stage_id, user):
        task = db.session.get(Task, int(task_id))
        if not task:
            raise ValueError("المهمة غير موجودة.")
        ProjectService._validate_tenant(task, user)
        stage = db.session.get(TaskStage, int(stage_id))
        if not stage or int(stage.project_id) != int(task.project_id):
            raise ValueError("المرحلة غير صالحة لهذا المشروع.")
        task.stage_id = int(stage_id)
        task.updated_at = datetime.now(timezone.utc)
        try:
            db.session.flush()
        except Exception:
            logger.exception("Failed to flush task stage change")
            raise
        return task

    @staticmethod
    def log_timesheet(task_id, data, user):
        task = db.session.get(Task, int(task_id))
        if not task:
            raise ValueError("المهمة غير موجودة.")
        ProjectService._validate_tenant(task, user)
        hours = Decimal(str(data.get("hours", 0)))
        if hours <= 0:
            raise ValueError("عدد الساعات يجب أن يكون أكبر من صفر.")
        ts = Timesheet(
            tenant_id=task.tenant_id,
            task_id=task.id,
            user_id=user.id,
            date=data.get("date") or date.today(),
            hours=hours,
            description=data.get("description"),
        )
        task.effective_hours = Decimal(str(task.effective_hours or 0)) + hours
        db.session.add(ts)
        try:
            db.session.flush()
        except Exception:
            logger.exception("Failed to flush timesheet entry")
            raise
        return ts

    @staticmethod
    def get_gantt_data(project_id, user):
        project = ProjectService.get_project(project_id, user)
        stages = (
            TaskStage.query.filter(
                TaskStage.project_id == project.id,
            )
            .order_by(TaskStage.sequence)
            .all()
        )
        tasks = (
            Task.query.filter(
                Task.project_id == project.id,
                Task.is_active,
            )
            .order_by(Task.sort_order)
            .all()
        )
        return {
            "project": project.to_dict(),
            "stages": [{"id": s.id, "name": s.name} for s in stages],
            "tasks": [
                {
                    "id": t.id,
                    "name": t.name,
                    "stage_id": t.stage_id,
                    "assigned_user_id": t.assigned_user_id,
                    "date_deadline": (
                        t.date_deadline.isoformat() if t.date_deadline else None
                    ),
                    "planned_hours": float(t.planned_hours or 0),
                    "effective_hours": float(t.effective_hours or 0),
                    "priority": t.priority,
                }
                for t in tasks
            ],
        }

    @staticmethod
    def add_member(project_id, user_id, role, user):
        project = ProjectService.get_project(project_id, user)
        existing = ProjectMember.query.filter_by(
            project_id=project.id, user_id=int(user_id)
        ).first()
        if existing:
            raise ValueError("المستخدم مضاف بالفعل للمشروع.")
        member = ProjectMember(
            tenant_id=project.tenant_id,
            project_id=project.id,
            user_id=int(user_id),
            role=role or "member",
        )
        db.session.add(member)
        try:
            db.session.flush()
        except Exception:
            logger.exception("Failed to flush project member addition")
            raise
        return member
