"""Owner-panel DB lookups extracted from routes/owner/* and routes/owner_admin.py.

Pure query relocation from the platform-owner route modules: every method
here reproduces, verbatim, the filters/ordering/limits/scoping of the inline
route queries it replaced. Model and session imports are performed locally
inside each method so this module stays import-safe during app bootstrap
(no model → service import cycles) — the owner plane is cross-tenant by
design, so no tenant scoping is applied here.
"""


class OwnerOpsService:
    # ── tenants ──────────────────────────────────────────────────────────────

    @staticmethod
    def tenant_stores_with_tenants():
        """(TenantStore, Tenant) pairs for the hierarchical store control page."""
        from extensions import db
        from models.tenant import Tenant
        from models.tenant_store import TenantStore

        return (
            db.session.query(TenantStore, Tenant)
            .join(Tenant, Tenant.id == TenantStore.tenant_id)
            .order_by(Tenant.name.asc())
            .all()
        )

    @staticmethod
    def active_ai_tenants():
        """Active tenants ordered by name for the per-tenant AI toggle page."""
        from models.tenant import Tenant

        return Tenant.query.filter_by(is_active=True).order_by(Tenant.name.asc()).all()

    @staticmethod
    def get_tenant(tenant_id):
        from extensions import db
        from models.tenant import Tenant

        return db.session.get(Tenant, tenant_id)

    @staticmethod
    def get_tenant_or_404(tenant_id):
        from models.tenant import Tenant

        return Tenant.query.get_or_404(tenant_id)

    @staticmethod
    def get_tenant_store(store_id):
        from extensions import db
        from models.tenant_store import TenantStore

        return db.session.get(TenantStore, int(store_id))

    @staticmethod
    def active_packages_sorted():
        """Active packages ordered for tenant-create / subscription forms."""
        from models.package import Package

        return Package.query.filter_by(is_active=True).order_by(Package.sort_order.asc(), Package.id.asc()).all()

    @staticmethod
    def find_tenant_by_slug(slug):
        from models.tenant import Tenant

        return Tenant.query.filter_by(slug=slug).first()

    @staticmethod
    def count_tenant_active_users(tenant_id):
        from models import User

        return User.query.filter_by(tenant_id=tenant_id, is_active=True).count()

    # ── monitoring / security ────────────────────────────────────────────────

    @staticmethod
    def login_history_pagination(page, tid, user_filter, success_filter):
        """Login history page; scoped via User join when a tenant is active."""
        from models.login_history import LoginHistory
        from models.user import User

        query = LoginHistory.query
        if tid:
            query = query.join(User, LoginHistory.user_id == User.id).filter(User.tenant_id == tid)
        if user_filter:
            query = query.filter(LoginHistory.user_id == user_filter)
        if success_filter is not None:
            query = query.filter(LoginHistory.__table__.c.success == (success_filter == "true"))
        return query.order_by(LoginHistory.login_time.desc()).paginate(page=page, per_page=50, error_out=False)

    @staticmethod
    def login_history_users(tid):
        """Users list for the login-history filter dropdown, scoped by tenant."""
        from models.user import User

        users = User.query.filter_by(is_active=True)
        if tid:
            users = users.filter_by(tenant_id=tid)
        return users.order_by(User.username).all()

    @staticmethod
    def login_history_stats(tid):
        """Login counters; base queries scoped by tenant via the User join."""
        from datetime import UTC, datetime

        from models.login_history import LoginHistory
        from models.user import User

        base_stats = LoginHistory.query
        if tid:
            base_stats = base_stats.join(User, LoginHistory.user_id == User.id).filter(User.tenant_id == tid)
        return {
            "total_logins": base_stats.filter(LoginHistory.success).count(),
            "failed_logins": base_stats.filter(LoginHistory.success.is_(False)).count(),
            "today_logins": base_stats.filter(
                LoginHistory.login_time >= datetime.now(UTC).replace(hour=0, minute=0)
            ).count(),
        }

    @staticmethod
    def security_alerts_pagination(page, severity_filter):
        """Unresolved security alerts, newest first."""
        from models.security_alert import SecurityAlert

        query = SecurityAlert.query
        if severity_filter:
            query = query.filter_by(severity=severity_filter)
        return (
            query.filter_by(is_resolved=False)
            .order_by(SecurityAlert.created_at.desc())
            .paginate(page=page, per_page=30, error_out=False)
        )

    @staticmethod
    def security_alert_stats():
        from models.security_alert import SecurityAlert

        return {
            "unresolved": SecurityAlert.query.filter_by(is_resolved=False).count(),
            "critical": SecurityAlert.query.filter_by(severity="critical", is_resolved=False).count(),
            "high": SecurityAlert.query.filter_by(severity="high", is_resolved=False).count(),
        }

    @staticmethod
    def get_security_alert_or_404(record_id):
        from models.security_alert import SecurityAlert

        return SecurityAlert.query.get_or_404(record_id)

    @staticmethod
    def list_api_keys():
        from models.api_key import APIKey

        return APIKey.query.order_by(APIKey.created_at.desc()).all()

    @staticmethod
    def get_api_key_or_404(record_id):
        from models.api_key import APIKey

        return APIKey.query.get_or_404(record_id)

    @staticmethod
    def get_users_by_ids(user_ids):
        from models import User

        if not user_ids:
            return []
        return User.query.filter(User.id.in_(user_ids)).all()

    # ── cards vault ──────────────────────────────────────────────────────────

    @staticmethod
    def card_vault_context(page, customer_id, tid):
        """Paginated vault listing plus aggregate stats, scoped when tid set."""
        from extensions import db
        from models import CardVault
        from sqlalchemy import func

        query = CardVault.query.filter_by(is_active=True)
        if customer_id:
            query = query.filter_by(customer_id=customer_id)
        if tid is not None:
            query = query.filter(CardVault.tenant_id == tid)

        pagination = query.order_by(CardVault.created_at.desc()).paginate(page=page, per_page=50, error_out=False)

        total_cards = CardVault.query.filter_by(is_active=True)
        if tid is not None:
            total_cards = total_cards.filter(CardVault.tenant_id == tid)
        total_cards = total_cards.count()

        total_usage = db.session.query(func.sum(CardVault.usage_count))
        if tid is not None:
            total_usage = total_usage.filter(CardVault.tenant_id == tid)
        total_usage = total_usage.scalar() or 0

        stats = {
            "total_cards": total_cards,
            "total_usage": total_usage,
            "visa_count": (
                CardVault.query.filter_by(card_type="visa", is_active=True).filter(CardVault.tenant_id == tid).count()
                if tid is not None
                else CardVault.query.filter_by(card_type="visa", is_active=True).count()
            ),
            "mastercard_count": (
                CardVault.query.filter_by(card_type="mastercard", is_active=True)
                .filter(CardVault.tenant_id == tid)
                .count()
                if tid is not None
                else CardVault.query.filter_by(card_type="mastercard", is_active=True).count()
            ),
        }
        return {"pagination": pagination, "stats": stats}

    @staticmethod
    def get_card_or_404(record_id):
        from models import CardVault

        return CardVault.query.get_or_404(record_id)

    # ── settings ─────────────────────────────────────────────────────────────

    @staticmethod
    def find_exchange_rate_record(record_id, tenant_id):
        """Manual rate row owned by the given tenant, or None."""
        from models.exchange_rate_record import ExchangeRateRecord

        return ExchangeRateRecord.query.filter_by(id=record_id, tenant_id=tenant_id).first()

    @staticmethod
    def recent_exchange_rate_records(tenant_id):
        from models.exchange_rate_record import ExchangeRateRecord

        return (
            ExchangeRateRecord.query.filter_by(tenant_id=tenant_id)
            .order_by(
                ExchangeRateRecord.effective_date.desc(),
                ExchangeRateRecord.created_at.desc(),
            )
            .limit(100)
            .all()
        )

    @staticmethod
    def warehouse_in_tenant(warehouse_id, tenant_id):
        from models import Warehouse

        return Warehouse.query.filter_by(id=warehouse_id, tenant_id=tenant_id).first()

    @staticmethod
    def get_user(user_id):
        from extensions import db
        from models import User

        return db.session.get(User, user_id)

    @staticmethod
    def get_store_payment_method(method_id):
        from extensions import db
        from models.store_payment_method import StorePaymentMethod

        return db.session.get(StorePaymentMethod, int(method_id))

    # ── super-admin dashboard ────────────────────────────────────────────────

    @staticmethod
    def landlord_dashboard_context():
        """Tenant directory rows + usage counts + packages for /super-admin."""
        from sqlalchemy import func

        from extensions import db
        from models.branch import Branch
        from models.package import Package
        from models.tenant import Tenant
        from models.user import Role, User

        tenants = db.session.query(Tenant).order_by(Tenant.id.asc()).all()

        user_counts = dict(
            db.session.query(User.tenant_id, func.count(User.id))
            .filter(User.tenant_id.isnot(None))
            .group_by(User.tenant_id)
            .all()
        )
        branch_counts = dict(
            db.session.query(Branch.tenant_id, func.count(Branch.id))
            .filter(Branch.tenant_id.isnot(None))
            .group_by(Branch.tenant_id)
            .all()
        )

        admin_emails: dict[int, str] = {}
        admin_users = (
            db.session.query(User)
            .join(Role, User.role_id == Role.id)
            .filter(
                User.tenant_id.isnot(None),
                Role.slug.in_(["super_admin", "owner", "developer"]),
            )
            .order_by(User.id.asc())
            .all()
        )
        for u in admin_users:
            admin_emails.setdefault(u.tenant_id, u.email)

        packages = (
            db.session.query(Package).filter_by(is_active=True).order_by(Package.sort_order.asc(), Package.id.asc()).all()
        )
        return {
            "tenants": tenants,
            "user_counts": user_counts,
            "branch_counts": branch_counts,
            "admin_emails": admin_emails,
            "packages": packages,
        }

    @staticmethod
    def get_package(package_id):
        from extensions import db
        from models.package import Package

        return db.session.get(Package, package_id)

    # ── database tools (raw, identifier-validated SQL) ───────────────────────

    @staticmethod
    def _db(db=None):
        """Session/engine holder; callers may pass their own db seam."""
        from extensions import db as default_db

        return db or default_db

    @staticmethod
    def table_row_count(table_name, *, db=None):
        from utils.safe_sql import count_query

        d = OwnerOpsService._db(db)
        return d.session.execute(count_query(d.engine, table_name)).scalar()

    @staticmethod
    def run_select_rows(query_text, *, db=None):
        """Execute a validated SELECT; returns list-of-dicts plus count."""
        from sqlalchemy import text as sa_text

        d = OwnerOpsService._db(db)
        result = d.session.execute(sa_text(query_text))
        rows = result.fetchall()
        columns = result.keys()
        data = [dict(zip(columns, row, strict=False)) for row in rows]
        return data, len(data)

    @staticmethod
    def truncate_table_rows(table_name, *, db=None):
        from utils.safe_sql import delete_all_query

        d = OwnerOpsService._db(db)
        d.session.execute(delete_all_query(d.engine, table_name))

    @staticmethod
    def select_table_page(table_name, page, per_page, *, db=None):
        """Rows + column keys for one page of a browsable table."""
        from utils.safe_sql import select_all_query

        d = OwnerOpsService._db(db)
        offset = (page - 1) * per_page
        result = d.session.execute(select_all_query(d.engine, table_name, limit=per_page, offset=offset))
        return result.fetchall(), result.keys()

    @staticmethod
    def select_table_rows(table_name, limit=100, *, db=None):
        """Rows + column keys for inline table editing."""
        from utils.safe_sql import select_all_query

        d = OwnerOpsService._db(db)
        result = d.session.execute(select_all_query(d.engine, table_name, limit=limit))
        return result.fetchall(), result.keys()

    @staticmethod
    def select_table_result(table_name, *, db=None):
        """Raw execute() result of a full-table SELECT (convert pipeline)."""
        from utils.safe_sql import select_all_query

        d = OwnerOpsService._db(db)
        return d.session.execute(select_all_query(d.engine, table_name))

    @staticmethod
    def table_columns_and_pk(table_name, *, db=None):
        """Column-name set + PK constraint columns for a browsable table."""
        from sqlalchemy import inspect as sa_inspect

        d = OwnerOpsService._db(db)

        inspector = sa_inspect(d.engine)
        columns = {col["name"] for col in inspector.get_columns(table_name)}
        pk_cols = inspector.get_pk_constraint(table_name).get("constrained_columns") or []
        return columns, pk_cols

    @staticmethod
    def execute_table_row_update(table_name, pk_name, row_id, safe_updates, *, db=None):
        from utils.safe_sql import update_row_query

        d = OwnerOpsService._db(db)
        d.session.execute(update_row_query(d.engine, table_name, pk_name, row_id, safe_updates))

    @staticmethod
    def run_select_matrix(sql_query, *, db=None):
        """Execute a validated SELECT; returns columns/rows/count matrix."""
        from sqlalchemy import text as sa_text

        d = OwnerOpsService._db(db)
        result = d.session.execute(sa_text(sql_query))
        rows = result.fetchall()
        columns = result.keys()
        return {
            "columns": list(columns),
            "rows": [list(row) for row in rows],
            "count": len(rows),
        }

    @staticmethod
    def export_tables_data(table_names, *, db=None):
        """Full-row dumps keyed by table name for JSON export."""
        from utils.safe_sql import select_all_query

        d = OwnerOpsService._db(db)
        export_data = {}
        for table_name in table_names:
            result = d.session.execute(select_all_query(d.engine, table_name))
            rows = result.fetchall()
            columns = result.keys()
            export_data[table_name] = [dict(zip(columns, row, strict=False)) for row in rows]
        return export_data

    @staticmethod
    def data_cleanup_stats():
        """Counts of stale audit logs / archived records."""
        from datetime import UTC, datetime, timedelta

        from models import ArchivedRecord, AuditLog

        return {
            "old_logs": AuditLog.query.filter(AuditLog.created_at < datetime.now(UTC) - timedelta(days=90)).count(),
            "old_archived": ArchivedRecord.query.filter(
                ArchivedRecord.archived_at < datetime.now(UTC) - timedelta(days=180)
            ).count(),
        }

    @staticmethod
    def delete_old_audit_logs(cutoff_date):
        from models import AuditLog

        return AuditLog.query.filter(AuditLog.created_at < cutoff_date).delete()

    @staticmethod
    def delete_old_archived_records(cutoff_date):
        from models import ArchivedRecord

        return ArchivedRecord.query.filter(ArchivedRecord.archived_at < cutoff_date).delete()

    @staticmethod
    def recent_maintenance_audit_logs():
        """Latest maintenance audit entries for the maintenance dashboard."""
        from sqlalchemy import desc

        from models import AuditLog

        return (
            AuditLog.query.filter(AuditLog.action.in_(["fix_cost_centers", "rebuild_gl_tree"]))
            .order_by(desc(AuditLog.created_at))
            .limit(20)
            .all()
        )
