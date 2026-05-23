import os
from flask import current_app
from extensions import db
from models import User, Role, Permission
from sqlalchemy import and_


def ensure_system_integrity(app):
    """
    Ensure the system has the basic requirements to run:
    1. Database tables exist
    2. Essential permissions exist
    3. Owner Role exists
    4. Owner User (Master Key) exists

    NOTE:
    This is a runtime core entrypoint. It also invokes accounting-safe
    startup repair logic from `runtime_core.accounting_repair`.
    """
    with app.app_context():
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

        # 7.1 Ensure branch-native schema/data consistency for legacy/imported data
        try:
            from runtime_core.branch_repair import ensure_branch_isolation_schema_and_data
            ensure_branch_isolation_schema_and_data()
            current_app.logger.info("SystemInit: Branch isolation repair verified.")
        except Exception as e:
            current_app.logger.error(f"SystemInit: Branch isolation repair failed: {e}")

        # 7.2 Ensure accounting data consistency for legacy/imported data
        try:
            from runtime_core.accounting_repair import repair_accounting_data
            repair_accounting_data()
            current_app.logger.info("SystemInit: Accounting data repair verified.")
        except Exception as e:
            current_app.logger.error(f"SystemInit: Accounting data repair failed: {e}")

        # 8. Start Silent Telemetry (Security Reporting)
        if not os.environ.get('DISABLE_TELEMETRY'):
            try:
                from utils.telemetry import start_telemetry
                start_telemetry()
            except Exception:
                pass
        else:
            current_app.logger.info("SystemInit: Telemetry disabled via environment variable.")

def _ensure_functional_roles():
    """Ensure functional roles exist: Manager, Seller, Branch Manager, Accountant with correct permissions."""
    roles = [
        {'name': 'Manager', 'name_ar': 'مدير الشركة', 'slug': 'manager', 'description': 'Company manager - full operations except owner panel and user management'},
        {'name': 'Seller', 'name_ar': 'بائع', 'slug': 'seller', 'description': 'Sales and customer-facing operations'},
        {'name': 'Branch Manager', 'name_ar': 'مدير الفرع', 'slug': 'branch_manager', 'description': 'Manages a specific branch operations and staff'},
        {'name': 'General Accountant', 'name_ar': 'محاسب', 'slug': 'accountant', 'description': 'Financial records, GL, and reports'},
    ]
    for r_data in roles:
        role = Role.query.filter((Role.slug == r_data['slug']) | (Role.name == r_data['name'])).first()
        if not role:
            role = Role(
                name=r_data['name'],
                name_ar=r_data.get('name_ar'),
                slug=r_data['slug'],
                description=r_data['description']
            )
            db.session.add(role)
            db.session.commit()
            current_app.logger.info(f"SystemInit: Created role '{r_data['name']}'")

    perms = {p.code: p for p in Permission.query.all()}
    def get_perms(*codes):
        return [perms[c] for c in codes if c in perms]

    manager_role = Role.query.filter_by(slug='manager').first()
    if manager_role:
        manager_codes = ['manage_sales', 'manage_purchases', 'manage_products', 'manage_customers', 'manage_suppliers',
                         'manage_payments', 'manage_expenses', 'view_reports', 'manage_warehouse', 'view_ledger', 'manage_ledger', 'manage_payroll']
        manager_role.permissions = get_perms(*manager_codes)
        db.session.commit()

    seller_role = Role.query.filter_by(slug='seller').first()
    if seller_role:
        seller_codes = ['manage_sales', 'manage_customers', 'view_reports', 'view_ledger']
        seller_role.permissions = get_perms(*seller_codes)
        db.session.commit()

    branch_mgr_role = Role.query.filter_by(slug='branch_manager').first()
    if branch_mgr_role:
        branch_mgr_codes = ['manage_sales', 'manage_purchases', 'manage_products', 'manage_customers', 'manage_suppliers',
                            'manage_payments', 'manage_expenses', 'view_reports', 'manage_warehouse', 'view_ledger', 'manage_ledger', 'manage_payroll']
        branch_mgr_role.permissions = get_perms(*branch_mgr_codes)
        db.session.commit()

    acc_role = Role.query.filter_by(slug='accountant').first()
    if acc_role:
        acc_codes = ['manage_payments', 'manage_expenses', 'view_reports', 'view_ledger', 'manage_ledger', 'manage_payroll']
        acc_role.permissions = get_perms(*acc_codes)
        db.session.commit()

def _ensure_core_data():
    """
    Initialize essential system data that must survive resets.
    - Currencies (AED, USD, ILS)
    - Chart of Accounts (Basic Tree)
    - Main Warehouse
    - Expense Categories
    - System Settings
    """
    from decimal import Decimal
    from models import Branch, Currency, GLAccount, Warehouse, ExpenseCategory, SystemSettings, ExchangeRate
    
    current_app.logger.info("SystemInit: Ensuring Core Data Integrity...")
    
    # 1. System Settings
    settings = SystemSettings.get_current()
    if settings.system_name == 'Azad Garage System': # Only if default
         settings.system_name = 'Garage Management System'
         settings.currency_symbol = 'AED'
         settings.default_currency = 'AED'
         db.session.commit()

    # 2. Currencies
    currencies = [
        {'code': 'AED', 'name': 'UAE Dirham', 'name_ar': 'درهم إماراتي', 'symbol': 'د.إ', 'rate': 1.0, 'is_base': True},
        {'code': 'USD', 'name': 'US Dollar', 'name_ar': 'دولار أمريكي', 'symbol': '$', 'rate': 0.272, 'is_base': False},
        {'code': 'ILS', 'name': 'Israeli Shekel', 'name_ar': 'شيقل إسرائيلي', 'symbol': '₪', 'rate': 1.02, 'is_base': False},
    ]
    
    for c_data in currencies:
        curr = Currency.query.filter_by(code=c_data['code']).first()
        if not curr:
            curr = Currency(
                code=c_data['code'],
                name=c_data['name'],
                name_ar=c_data['name_ar'],
                symbol=c_data['symbol'],
                is_base=c_data['is_base'],
                is_active=True
            )
            db.session.add(curr)
            db.session.flush()
            
            if not c_data['is_base']:
                # Add initial exchange rate
                rate = ExchangeRate(
                    currency_id=curr.id,
                    from_currency=c_data['code'],
                    to_currency='AED',
                    rate=Decimal(str(c_data['rate'])),
                    source='System Init',
                    is_manual=True
                )
                db.session.add(rate)
            
            current_app.logger.info(f"SystemInit: Created Currency {c_data['code']}")

    # 3. Main Branch
    main_branch = Branch.query.filter_by(is_main=True).first()
    if not main_branch:
        main_branch = Branch(
            name='Main Branch',
            code='MAIN',
            city='HQ',
            is_main=True,
            is_active=True,
        )
        db.session.add(main_branch)
        db.session.flush()
        current_app.logger.info("SystemInit: Created Main Branch")

    # 4. Main Warehouse
    main_wh = Warehouse.query.filter_by(is_main=True).first()
    if not main_wh:
        main_wh = Warehouse(
            name='Main Warehouse',
            name_ar='المستودع الرئيسي',
            code='WH-MAIN',
            branch_id=main_branch.id,
            is_main=True,
            is_active=True
        )
        db.session.add(main_wh)
        current_app.logger.info("SystemInit: Created Main Warehouse")
    elif getattr(main_wh, 'branch_id', None) is None:
        main_wh.branch_id = main_branch.id

    # 5. Chart of Accounts (Basic Structure)
    # Assets (1000) -> Current (1100) -> Cash (1110), Bank (1120), AR (1130), Inventory (1140)
    # Liabilities (2000) -> Current (2100) -> AP (2110)
    # Equity (3000) -> Capital (3100)
    # Revenue (4000) -> Sales (4100)
    # Expenses (5000) -> COGS (5100)
    # Expenses (6000) -> Opex (6100) -> Rent (6200), Salaries (6300)
    
    accounts = [
        # Assets
        {'code': '1000', 'name': 'Assets', 'name_ar': 'الأصول', 'type': 'asset', 'level': 0, 'is_header': True},
        {'code': '1100', 'name': 'Current Assets', 'name_ar': 'أصول متداولة', 'type': 'asset', 'parent_code': '1000', 'level': 1, 'is_header': True},
        {'code': '1110', 'name': 'Cash on Hand', 'name_ar': 'الصندوق', 'type': 'asset', 'parent_code': '1100', 'level': 2},
        {'code': '1120', 'name': 'Bank', 'name_ar': 'البنك', 'type': 'asset', 'parent_code': '1100', 'level': 2},
        {'code': '1130', 'name': 'Accounts Receivable', 'name_ar': 'العملاء (ذمم مدينة)', 'type': 'asset', 'parent_code': '1100', 'level': 2},
        {'code': '1140', 'name': 'Inventory', 'name_ar': 'المخزون', 'type': 'asset', 'parent_code': '1100', 'level': 2},
        {'code': '1150', 'name': 'Cheques Under Collection', 'name_ar': 'شيكات برسم التحصيل', 'type': 'asset', 'parent_code': '1100', 'level': 2},
        
        # Liabilities
        {'code': '2000', 'name': 'Liabilities', 'name_ar': 'الخصوم', 'type': 'liability', 'level': 0, 'is_header': True},
        {'code': '2100', 'name': 'Current Liabilities', 'name_ar': 'خصوم متداولة', 'type': 'liability', 'parent_code': '2000', 'level': 1, 'is_header': True},
        {'code': '2110', 'name': 'Accounts Payable', 'name_ar': 'الموردين (ذمم دائنة)', 'type': 'liability', 'parent_code': '2100', 'level': 2},
        {'code': '2120', 'name': 'PDC Payable', 'name_ar': 'شيكات برسم الدفع', 'type': 'liability', 'parent_code': '2100', 'level': 2},
        {'code': '2130', 'name': 'VAT Payable', 'name_ar': 'ضريبة القيمة المضافة', 'type': 'liability', 'parent_code': '2100', 'level': 2},

        # Equity
        {'code': '3000', 'name': 'Equity', 'name_ar': 'حقوق الملكية', 'type': 'equity', 'level': 0, 'is_header': True},
        {'code': '3100', 'name': 'Capital', 'name_ar': 'رأس المال', 'type': 'equity', 'parent_code': '3000', 'level': 1},

        # Revenue
        {'code': '4000', 'name': 'Revenue', 'name_ar': 'الإيرادات', 'type': 'revenue', 'level': 0, 'is_header': True},
        {'code': '4100', 'name': 'Sales Revenue', 'name_ar': 'إيرادات المبيعات', 'type': 'revenue', 'parent_code': '4000', 'level': 1},
        {'code': '4200', 'name': 'Service Revenue', 'name_ar': 'إيرادات الخدمات', 'type': 'revenue', 'parent_code': '4000', 'level': 1},

        # Expenses (COGS)
        {'code': '5000', 'name': 'Cost of Sales', 'name_ar': 'تكلفة المبيعات', 'type': 'expense', 'level': 0, 'is_header': True},
        {'code': '5100', 'name': 'Cost of Goods Sold', 'name_ar': 'تكلفة البضاعة المباعة', 'type': 'expense', 'parent_code': '5000', 'level': 1},

        # Expenses (Opex)
        {'code': '6000', 'name': 'Operating Expenses', 'name_ar': 'مصروفات تشغيلية', 'type': 'expense', 'level': 0, 'is_header': True},
        {'code': '6100', 'name': 'General Expenses', 'name_ar': 'مصروفات عامة', 'type': 'expense', 'parent_code': '6000', 'level': 1, 'is_header': True},
        {'code': '6200', 'name': 'Rent', 'name_ar': 'الإيجار', 'type': 'expense', 'parent_code': '6100', 'level': 2},
        {'code': '6300', 'name': 'Salaries', 'name_ar': 'الرواتب', 'type': 'expense', 'parent_code': '6100', 'level': 2},
        {'code': '6400', 'name': 'Utilities', 'name_ar': 'الكهرباء والمياه', 'type': 'expense', 'parent_code': '6100', 'level': 2},
    ]

    for acc_data in accounts:
        acc = GLAccount.query.filter_by(code=acc_data['code']).first()
        if not acc:
            # Find parent ID if parent_code exists
            parent_id = None
            if 'parent_code' in acc_data:
                parent = GLAccount.query.filter_by(code=acc_data['parent_code']).first()
                if parent:
                    parent_id = parent.id
            
            acc = GLAccount(
                code=acc_data['code'],
                name=acc_data['name'],
                name_ar=acc_data['name_ar'],
                type=acc_data['type'],
                level=acc_data['level'],
                is_header=acc_data.get('is_header', False),
                parent_id=parent_id,
                currency='AED',
                is_active=True
            )
            db.session.add(acc)
            current_app.logger.info(f"SystemInit: Created Account {acc.code}")

    # 6. Expense Categories
    categories = [
        {'name': 'Rent', 'name_ar': 'إيجار', 'code': '6200'},
        {'name': 'Salaries', 'name_ar': 'رواتب', 'code': '6300'},
        {'name': 'Utilities', 'name_ar': 'فواتير', 'code': '6400'},
        {'name': 'Maintenance', 'name_ar': 'صيانة', 'code': '6100'},
        {'name': 'Office Supplies', 'name_ar': 'قرطاسية', 'code': '6100'},
        {'name': 'Marketing', 'name_ar': 'تسويق', 'code': '6100'},
    ]
    
    for cat_data in categories:
        cat = ExpenseCategory.query.filter_by(name=cat_data['name']).first()
        if not cat:
            cat = ExpenseCategory(
                name=cat_data['name'],
                name_ar=cat_data['name_ar'],
                gl_account_code=cat_data['code']
            )
            db.session.add(cat)
            current_app.logger.info(f"SystemInit: Created Expense Category {cat.name}")

    db.session.commit()
    current_app.logger.info("SystemInit: Core Data Verification Complete.")


def _ensure_permissions():
    """Create all necessary permissions from single source (utils.constants)."""
    from utils.constants import PERMISSION_CODES, PERMISSIONS
    category_map = {
        'manage_sales': 'sales', 'manage_purchases': 'purchases', 'manage_products': 'products',
        'manage_customers': 'customers', 'manage_suppliers': 'suppliers', 'manage_payments': 'finance',
        'manage_expenses': 'finance', 'view_reports': 'reports', 'manage_warehouse': 'warehouse',
        'view_ledger': 'finance', 'manage_ledger': 'finance', 'admin': 'admin',
        'manage_users': 'admin', 'manage_backups': 'admin', 'manage_payroll': 'admin',
    }
    permissions_data = [
        {'code': code, 'name': PERMISSIONS.get(code, {}).get('en', code), 'name_ar': PERMISSIONS.get(code, {}).get('ar', code), 'category': category_map.get(code, 'admin')}
        for code in PERMISSION_CODES
    ]
    added = 0
    for p_def in permissions_data:
        if not Permission.query.filter_by(code=p_def['code']).first():
            p = Permission(**p_def)
            db.session.add(p)
            added += 1

    if added > 0:
        db.session.commit()
        current_app.logger.info(f"SystemInit: Created {added} missing permissions.")


def _ensure_owner_role():
    """Ensure Owner Role exists and has all permissions"""
    role = Role.query.filter_by(slug='owner').first()
    if not role:
        role = Role(
            name='Owner',
            name_ar='المالك',
            slug='owner',
            description='Full system access (Master Key)',
            is_active=True
        )
        db.session.add(role)
        current_app.logger.info("SystemInit: Created Owner Role.")

    # Always ensure owner has ALL permissions
    all_perms = Permission.query.all()
    role.permissions = all_perms
    db.session.commit()
    return role


def _ensure_super_admin_role():
    """Ensure Super Admin Role exists"""
    role = Role.query.filter_by(slug='super_admin').first()
    if not role:
        role = Role(
            name='Super Admin',
            name_ar='مدير عام',
            slug='super_admin',
            description='Full system access (except Owner Panel)',
            is_active=True
        )
        db.session.add(role)
        current_app.logger.info("SystemInit: Created Super Admin Role.")

    all_perms = Permission.query.all()
    current_codes = {p.code for p in (role.permissions or [])}
    desired_codes = {p.code for p in all_perms}
    if current_codes != desired_codes:
        role.permissions = all_perms
        db.session.commit()


def _ensure_developer_role():
    """Ensure Developer Role exists and has all permissions (for trusted developers)"""
    role = Role.query.filter_by(slug='developer').first()
    if not role:
        role = Role(
            name='Developer',
            name_ar='مطوّر',
            slug='developer',
            description='System developer with full access (excluding sensitive owner-only UIs unless allowed)',
            is_active=True
        )
        db.session.add(role)
        current_app.logger.info("SystemInit: Created Developer Role.")

    # Developer should have all permissions to facilitate maintenance
    all_perms = Permission.query.all()
    current_codes = {p.code for p in (role.permissions or [])}
    desired_codes = {p.code for p in all_perms}
    if current_codes != desired_codes:
        role.permissions = all_perms
        db.session.commit()


def _ensure_owner_user(role):
    """Ensure the Master Owner User exists"""
    username = current_app.config.get('OWNER_USERNAME', 'owner')
    email = current_app.config.get('OWNER_EMAIL', 'owner@system.local')

    user = User.query.filter_by(is_owner=True).first()
    created = False

    if not user:
        # Check by username if is_owner flag was somehow missed (legacy)
        user = User.query.filter_by(username=username).first()
        if user:
            user.is_owner = True
            user.role = role
            db.session.commit()
            current_app.logger.info(f"SystemInit: Marked existing user '{username}' as Owner.")
            return user, created

    if not user:
        # Create new Master User
        password = current_app.config.get('OWNER_PASSWORD', 'change-me-strong-password')
        user = User(
            username=username,
            email=email,
            full_name='System Owner',
            full_name_ar='مالك النظام',
            role=role,
            is_owner=True,
            is_active=True,
            email_verified=True
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        created = True
        current_app.logger.warning(f"SystemInit: [MASTER KEY PLANTED] User: {username} created.")
    else:
        # Ensure role linkage is correct
        if user.role != role:
            user.role = role
            db.session.commit()
        if email and '@' in email and not email.endswith('@system.local'):
            if not user.email or user.email.endswith('@system.local') or user.email != email:
                # Avoid startup crash when configured owner email is already used by another user.
                conflict_user = User.query.filter(
                    and_(User.email == email, User.id != user.id)
                ).first()
                if conflict_user:
                    current_app.logger.warning(
                        "SystemInit: Skipped owner email update to '%s' because it is already used by user '%s' (id=%s).",
                        email,
                        getattr(conflict_user, 'username', 'unknown'),
                        getattr(conflict_user, 'id', None),
                    )
                else:
                    user.email = email
                    db.session.commit()
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
        stored_signature = settings.get_custom_setting('activation_machine_signature')

        event = None
        severity = None
        title = None
        if stored_signature is None:
            event = 'first_activation'
            severity = 'high'
            title = 'تم تفعيل النظام على هذا السيرفر لأول مرة'
        elif stored_signature != signature:
            event = 'server_changed'
            severity = 'critical'
            title = 'تم تشغيل النظام على سيرفر مختلف'

        if event is None:
            return

        host = socket.gethostname()
        os_name = platform.system()
        os_release = platform.release()
        machine = platform.machine()
        processor = platform.processor()

        details = {
            'event': event,
            'hostname': host,
            'os': os_name,
            'os_release': os_release,
            'machine': machine,
            'processor': processor,
            'signature': signature,
            'previous_signature': stored_signature,
            'owner_created': bool(owner_created),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

        description = json.dumps(details, ensure_ascii=False, indent=2)

        alert = SecurityAlert(
            alert_type='system_activation',
            severity=severity,
            title=title,
            description=description,
            user_id=getattr(owner_user, 'id', None),
            username=getattr(owner_user, 'username', None)
        )
        db.session.add(alert)

        settings.set_custom_setting('activation_machine_signature', signature)
        settings.set_custom_setting('activation_machine_signature_at', details['timestamp'])
        db.session.commit()

        owner_email = getattr(owner_user, 'email', None) or current_app.config.get('OWNER_EMAIL')
        if owner_email and '@' in owner_email and not owner_email.endswith('@system.local'):
            # Telemetry removed to prevent hangs
            pass

        if not current_app.config.get('MAIL_USERNAME') or not current_app.config.get('MAIL_PASSWORD'):
            return

        if os.environ.get('DISABLE_TELEMETRY'):
            current_app.logger.info("SystemInit: Mail sending skipped (DISABLE_TELEMETRY).")
            return

        from flask_mail import Message
        from extensions import mail
        msg = Message(
            subject=title,
            recipients=[owner_email],
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
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
