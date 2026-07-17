import os
from flask import current_app
from extensions import db
from models import User, Role, Permission
from sqlalchemy import and_
from utils.db_safety import atomic_transaction


def ensure_clean_platform(app):
    """Bootstrap empty SaaS platform: schema metadata + owner only — no tenants."""
    with app.app_context():
        from utils.tenanting import without_tenant_scope

        with without_tenant_scope():
            db.create_all()
            _ensure_permissions()
            owner_role = _ensure_owner_role()
            owner_user, owner_created = _ensure_owner_user(owner_role)
            _record_server_activation(owner_user, owner_created)
            _ensure_super_admin_role()
            _ensure_developer_role()
            _ensure_functional_roles()
            _ensure_platform_reference_data()
            current_app.logger.info(
                "SystemInit: Clean platform bootstrap complete (no tenants seeded)."
            )


def ensure_system_integrity(app):
    """
    Ensure the system has the basic requirements to run:
    1. Database tables exist
    2. Essential permissions exist
    3. Owner Role exists
    4. Owner User (Master Key) exists

    NOTE:
    This is a runtime core entrypoint. It also invokes accounting-safe
    startup repair logic from `app.runtime.accounting_repair`.
    """
    with app.app_context():
        from utils.tenanting import without_tenant_scope

        with without_tenant_scope():
            _ensure_system_integrity_inner(app)


def _ensure_system_integrity_inner(app):
    # 1. Ensure Tables Exist
    # This is critical if the DB file was deleted
    db.create_all()

    # 2. Ensure Permissions
    _ensure_permissions()

    # 3. Ensure Owner Role
    owner_role = _ensure_owner_role()

    # 4. Ensure Owner User (The Master Key)
    owner_user, owner_created = _ensure_owner_user(owner_role)
    _record_server_activation(owner_user, owner_created)

    # 5. Ensure Super Admin Role (optional but good for consistency)
    _ensure_super_admin_role()

    # 6. Ensure Developer Role (grants full system permissions, used for trusted developers)
    _ensure_developer_role()

    # 6.1 Ensure Branch Manager & Accountant Roles
    _ensure_functional_roles()

    # 7. Ensure Core Data (Currencies, Accounts, Warehouses, Settings)
    _ensure_core_data()

    # 7.1 Branch isolation repair (no-op — schema migration handles this)
    current_app.logger.info(
        "SystemInit: Branch isolation skipped (handled by migration)."
    )

    # 7.2 Ensure tenant GL trees and branch liquidity accounts
    try:
        _ensure_tenant_gl_trees()
        current_app.logger.info("SystemInit: Tenant GL trees verified.")
    except Exception as e:
        from services.logging_core import LoggingCore

        LoggingCore.log_error(
            message=f"Tenant GL tree verification failed: {e}",
            category="SYSTEM_INIT",
            level="ERROR",
            source="utils.system_init.ensure_system_integrity.gl_tree",
            exception=e,
        )

    # 7.3 Accounting data repair (no-op — schema migration handles this)
    current_app.logger.info(
        "SystemInit: Accounting data repair skipped (handled by migration)."
    )

    # 8. Start Silent Telemetry (Security Reporting)
    if not os.environ.get("DISABLE_TELEMETRY"):
        try:
            from utils.telemetry import start_telemetry

            start_telemetry()
        except Exception as e:
            import sys
            import traceback

            sys.stderr.write(f"[SYSTEM_INIT_WARNING] Telemetry start failed: {e}\n")
            traceback.print_exc()
            try:
                from services.logging_core import LoggingCore

                LoggingCore.log_error(
                    message=str(e),
                    category="SYSTEM_INIT",
                    source="utils.system_init.ensure_system_integrity.start_telemetry",
                    level="WARNING",
                    exception=e,
                )
            except Exception:
                pass
    else:
        current_app.logger.info(
            "SystemInit: Telemetry disabled via environment variable."
        )


def _ensure_tenant_gl_trees():
    from models.tenant import Tenant
    from services.gl_service import GLService

    tenants = Tenant.query.filter_by(is_active=True).order_by(Tenant.id.asc()).all()
    for tenant in tenants:
        GLService.ensure_core_accounts(tenant_id=tenant.id, cleanup_extra=False)


def _ensure_functional_roles():
    """Ensure functional roles exist: Manager, Seller, Branch Manager, Accountant with correct permissions."""
    with atomic_transaction("ensure_functional_roles"):
        roles = [
            {
                "name": "Manager",
                "name_ar": "مدير الشركة",
                "slug": "manager",
                "description": "Company manager - full operations except owner panel and user management",
            },
            {
                "name": "Seller",
                "name_ar": "بائع",
                "slug": "seller",
                "description": "Sales and customer-facing operations",
            },
            {
                "name": "Branch Manager",
                "name_ar": "مدير الفرع",
                "slug": "branch_manager",
                "description": "Manages a specific branch operations and staff",
            },
            {
                "name": "General Accountant",
                "name_ar": "محاسب",
                "slug": "accountant",
                "description": "Financial records, GL, and reports",
            },
            {
                "name": "Kitchen Staff",
                "name_ar": "طاقم المطبخ",
                "slug": "kitchen",
                "description": "Kitchen display (KDS) viewer - sees live kitchen orders only",
            },
        ]
        for r_data in roles:
            role = Role.query.filter(
                (Role.slug == r_data["slug"]) | (Role.name == r_data["name"])
            ).first()
            if not role:
                role = Role(
                    name=r_data["name"],
                    name_ar=r_data.get("name_ar"),
                    slug=r_data["slug"],
                    description=r_data["description"],
                )
                db.session.add(role)
                current_app.logger.info(f"SystemInit: Created role '{r_data['name']}'")

        perms = {p.code: p for p in Permission.query.all()}

        def get_perms(*codes):
            return [perms[c] for c in codes if c in perms]

        manager_role = Role.query.filter_by(slug="manager").first()
        if manager_role:
            manager_codes = [
                "manage_sales",
                "manage_purchases",
                "manage_products",
                "manage_customers",
                "manage_suppliers",
                "manage_payments",
                "manage_expenses",
                "view_reports",
                "manage_warehouse",
                "manage_store",
                "view_ledger",
                "manage_ledger",
                "manage_payroll",
                "view_kds",
            ]
            manager_role.permissions = get_perms(*manager_codes)

        seller_role = Role.query.filter_by(slug="seller").first()
        if seller_role:
            seller_codes = [
                "manage_sales",
                "manage_customers",
                "view_reports",
                "view_ledger",
                "view_kds",
            ]
            seller_role.permissions = get_perms(*seller_codes)

        branch_mgr_role = Role.query.filter_by(slug="branch_manager").first()
        if branch_mgr_role:
            branch_mgr_codes = [
                "manage_sales",
                "manage_purchases",
                "manage_products",
                "manage_customers",
                "manage_suppliers",
                "manage_payments",
                "manage_expenses",
                "view_reports",
                "manage_warehouse",
                "manage_store",
                "view_ledger",
                "manage_ledger",
                "manage_payroll",
                "view_kds",
            ]
            branch_mgr_role.permissions = get_perms(*branch_mgr_codes)

        acc_role = Role.query.filter_by(slug="accountant").first()
        if acc_role:
            acc_codes = [
                "manage_payments",
                "manage_expenses",
                "view_reports",
                "view_ledger",
                "manage_ledger",
                "manage_payroll",
            ]
            acc_role.permissions = get_perms(*acc_codes)

        kitchen_role = Role.query.filter_by(slug="kitchen").first()
        if kitchen_role:
            kitchen_codes = ["view_kds"]
            kitchen_role.permissions = get_perms(*kitchen_codes)


def _ensure_platform_reference_data():
    """Platform-wide reference data only — no tenant, branch, or warehouse."""
    with atomic_transaction("ensure_platform_reference_data"):
        from decimal import Decimal
        from models import Currency, SystemSettings, ExchangeRate

        settings = SystemSettings.get_current()
        if settings.system_name in ("Azad Garage System", "Garage Management System"):
            settings.system_name = "Azad ERP System"
            settings.currency_symbol = "AED"
            settings.default_currency = "AED"

        currencies = [
            {
                "code": "AED",
                "name": "UAE Dirham",
                "name_ar": "درهم إماراتي",
                "symbol": "د.إ",
                "rate": 1.0,
                "is_base": True,
            },
            {
                "code": "USD",
                "name": "US Dollar",
                "name_ar": "دولار أمريكي",
                "symbol": "$",
                "rate": 0.272,
                "is_base": False,
            },
            {
                "code": "ILS",
                "name": "Israeli Shekel",
                "name_ar": "شيقل إسرائيلي",
                "symbol": "₪",
                "rate": 1.02,
                "is_base": False,
            },
        ]
        for c_data in currencies:
            curr = Currency.query.filter_by(code=c_data["code"]).first()
            if not curr:
                curr = Currency(
                    code=c_data["code"],
                    name=c_data["name"],
                    name_ar=c_data["name_ar"],
                    symbol=c_data["symbol"],
                    is_base=c_data["is_base"],
                    is_active=True,
                )
                db.session.add(curr)
                db.session.flush()
                if not c_data["is_base"]:
                    db.session.add(
                        ExchangeRate(
                            currency_id=curr.id,
                            from_currency=c_data["code"],
                            to_currency="AED",
                            rate=Decimal(str(c_data["rate"])),
                            source="System Init",
                            is_manual=True,
                        )
                    )


def _ensure_core_data():
    """Platform reference data only. Tenants/branches are created via Owner panel."""
    current_app.logger.info("SystemInit: Ensuring platform reference data...")
    _ensure_platform_reference_data()
    current_app.logger.info("SystemInit: Core Data Verification Complete.")

    try:
        from services.store_payment_method_service import StorePaymentMethodService

        StorePaymentMethodService.ensure_defaults()
    except Exception as e:
        current_app.logger.warning(
            f"SystemInit: store payment methods seed skipped: {e}"
        )

    try:
        from utils.seed_industry_fields import seed_industry_fields

        seed_industry_fields()
        current_app.logger.info("SystemInit: Industry fields seeded.")
    except Exception as e:
        current_app.logger.warning(f"SystemInit: industry fields seed skipped: {e}")


def _ensure_permissions():
    """Create all necessary permissions from single source (utils.constants)."""
    with atomic_transaction("ensure_permissions"):
        from utils.constants import PERMISSION_CODES, PERMISSIONS

        category_map = {
            "manage_sales": "sales",
            "manage_purchases": "purchases",
            "manage_products": "products",
            "manage_customers": "customers",
            "manage_suppliers": "suppliers",
            "manage_payments": "finance",
            "manage_expenses": "finance",
            "view_reports": "reports",
            "manage_warehouse": "warehouse",
            "manage_store": "store",
            "view_ledger": "finance",
            "manage_ledger": "finance",
            "admin": "admin",
            "manage_users": "admin",
            "manage_backups": "admin",
            "manage_payroll": "admin",
        }
        permissions_data = [
            {
                "code": code,
                "name": PERMISSIONS.get(code, {}).get("en", code),
                "name_ar": PERMISSIONS.get(code, {}).get("ar", code),
                "category": category_map.get(code, "admin"),
            }
            for code in PERMISSION_CODES
        ]
        added = 0
        for p_def in permissions_data:
            if not Permission.query.filter_by(code=p_def["code"]).first():
                p = Permission(**p_def)
                db.session.add(p)
                added += 1

        if added > 0:
            current_app.logger.info(f"SystemInit: Created {added} missing permissions.")


def _ensure_owner_role():
    """Ensure Owner Role exists and has all permissions"""
    with atomic_transaction("ensure_owner_role"):
        role = Role.query.filter_by(slug="owner").first()
        if not role:
            role = Role(
                name="Owner",
                name_ar="المالك",
                slug="owner",
                description="Full system access (Master Key)",
                is_active=True,
            )
            db.session.add(role)
            current_app.logger.info("SystemInit: Created Owner Role.")

        # Always ensure owner has ALL permissions
        all_perms = Permission.query.all()
        role.permissions = all_perms
        return role


def _ensure_super_admin_role():
    """Ensure Super Admin Role exists"""
    with atomic_transaction("ensure_super_admin_role"):
        role = Role.query.filter_by(slug="super_admin").first()
        if not role:
            role = Role(
                name="Super Admin",
                name_ar="مدير عام",
                slug="super_admin",
                description="Full system access (except Owner Panel)",
                is_active=True,
            )
            db.session.add(role)
            current_app.logger.info("SystemInit: Created Super Admin Role.")

        all_perms = Permission.query.all()
        current_codes = {p.code for p in (role.permissions or [])}
        desired_codes = {p.code for p in all_perms}
        if current_codes != desired_codes:
            role.permissions = all_perms


def _ensure_developer_role():
    """Ensure Developer Role exists and has all permissions (for trusted developers)"""
    with atomic_transaction("ensure_developer_role"):
        role = Role.query.filter_by(slug="developer").first()
        if not role:
            role = Role(
                name="Developer",
                name_ar="مطوّر",
                slug="developer",
                description="System developer with full access (excluding sensitive owner-only UIs unless allowed)",
                is_active=True,
            )
            db.session.add(role)
            current_app.logger.info("SystemInit: Created Developer Role.")

        # Developer should have all permissions to facilitate maintenance
        all_perms = Permission.query.all()
        current_codes = {p.code for p in (role.permissions or [])}
        desired_codes = {p.code for p in all_perms}
        if current_codes != desired_codes:
            role.permissions = all_perms


def _ensure_owner_user(role):
    """Ensure the Master Owner User exists"""
    with atomic_transaction("ensure_owner_user"):
        username = current_app.config.get("OWNER_USERNAME", "owner")
        email = current_app.config.get("OWNER_EMAIL", "owner@system.local")

        user = User.query.filter_by(is_owner=True).first()
        created = False

        if not user:
            user = User.query.filter_by(username=username).first()
            if user:
                user.is_owner = True
                user.role = role
                current_app.logger.info(
                    f"SystemInit: Marked existing user '{username}' as Owner."
                )
                return user, created

        if not user:
            password = current_app.config.get(
                "OWNER_PASSWORD", "change-me-strong-password"
            )
            user = User(
                username=username,
                email=email,
                full_name="System Owner",
                full_name_ar="مالك النظام",
                role=role,
                is_owner=True,
                is_active=True,
                email_verified=True,
            )
            user.set_password(password)
            db.session.add(user)
            created = True
            current_app.logger.warning(
                f"SystemInit: [MASTER KEY PLANTED] User: {username} created."
            )
        else:
            if user.role != role:
                user.role = role
            if email and "@" in email and not email.endswith("@system.local"):
                if (
                    not user.email
                    or user.email.endswith("@system.local")
                    or user.email != email
                ):
                    conflict_user = User.query.filter(
                        and_(User.email == email, User.id != user.id)
                    ).first()
                    if conflict_user:
                        current_app.logger.warning(
                            "SystemInit: Skipped owner email update to '%s' because it is already used by user '%s' (id=%s).",
                            email,
                            getattr(conflict_user, "username", "unknown"),
                            getattr(conflict_user, "id", None),
                        )
                    else:
                        user.email = email
        return user, created


def _record_server_activation(owner_user, owner_created: bool):
    try:
        from datetime import datetime, timezone
        import json
        from models import SystemSettings, SecurityAlert
        from utils.telemetry import get_machine_signature
        import socket
        import platform

        settings = SystemSettings.get_current()
        signature = get_machine_signature()
        stored_signature = settings.get_custom_setting("activation_machine_signature")

        event = None
        severity = None
        title = None
        if stored_signature is None:
            event = "first_activation"
            severity = "high"
            title = "تم تفعيل النظام على هذا السيرفر لأول مرة"
        elif stored_signature != signature:
            event = "server_changed"
            severity = "critical"
            title = "تم تشغيل النظام على سيرفر مختلف"

        if event is None:
            return

        host = socket.gethostname()
        os_name = platform.system()
        os_release = platform.release()
        machine = platform.machine()
        processor = platform.processor()

        details = {
            "event": event,
            "hostname": host,
            "os": os_name,
            "os_release": os_release,
            "machine": machine,
            "processor": processor,
            "signature": signature,
            "previous_signature": stored_signature,
            "owner_created": bool(owner_created),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        description = json.dumps(details, ensure_ascii=False, indent=2)

        alert = SecurityAlert(
            alert_type="system_activation",
            severity=severity,
            title=title,
            description=description,
            user_id=getattr(owner_user, "id", None),
            username=getattr(owner_user, "username", None),
        )
        with atomic_transaction("record_server_activation"):
            db.session.add(alert)

            settings.set_custom_setting("activation_machine_signature", signature)
            settings.set_custom_setting(
                "activation_machine_signature_at", details["timestamp"]
            )

        owner_email = getattr(owner_user, "email", None) or current_app.config.get(
            "OWNER_EMAIL"
        )
        if (
            owner_email
            and "@" in owner_email
            and not owner_email.endswith("@system.local")
        ):
            # Telemetry removed to prevent hangs
            pass

        if not current_app.config.get("MAIL_USERNAME") or not current_app.config.get(
            "MAIL_PASSWORD"
        ):
            return

        if os.environ.get("DISABLE_TELEMETRY"):
            current_app.logger.info(
                "SystemInit: Mail sending skipped (DISABLE_TELEMETRY)."
            )
            return

        from flask_mail import Message
        from extensions import mail

        msg = Message(
            subject=title or "",
            recipients=[owner_email or ""],
            body=(
                f"{title}\n\n"
                f"Hostname: {host}\n"
                f"OS: {os_name} {os_release}\n"
                f"Machine: {machine}\n"
                f"Signature: {signature}\n"
                f"Previous: {stored_signature or '-'}\n"
                f"Time: {details['timestamp']}\n"
            ),
        )
        mail.send(msg)
    except Exception as e:
        import sys
        import traceback

        sys.stderr.write(f"[SYSTEM_INIT_ERROR] _record_server_activation failed: {e}\n")
        traceback.print_exc()
        try:
            from services.logging_core import LoggingCore

            LoggingCore.log_error(
                message=str(e),
                category="SYSTEM_INIT",
                source="utils.system_init._record_server_activation",
                level="ERROR",
                exception=e,
            )
        except Exception:
            pass
