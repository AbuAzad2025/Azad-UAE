import os
import uuid
import re
from datetime import datetime, timezone
from decimal import Decimal
from werkzeug.utils import secure_filename
from flask import current_app, request
from extensions import db


def _normalize_branch_code(branch_code):
    if not branch_code:
        return None
    cleaned = re.sub(r'[^A-Za-z0-9]', '', str(branch_code).upper())
    return cleaned or None


def _resolve_branch_code(branch_code=None, branch_id=None):
    normalized = _normalize_branch_code(branch_code)
    if normalized:
        return normalized

    if not branch_id:
        return None

    try:
        from models import Branch
        branch = db.session.get(Branch, int(branch_id))
        if branch and getattr(branch, 'code', None):
            normalized = _normalize_branch_code(branch.code)
            if normalized:
                return normalized
    except Exception:
        pass

    return f'BR{int(branch_id):02d}'


def generate_number(
    prefix,
    model,
    field_name='sale_number',
    date_format='%Y',
    branch_code=None,
    branch_id=None,
    tenant_id=None,
):
    year = datetime.now().strftime(date_format)

    resolved_branch_code = _resolve_branch_code(branch_code=branch_code, branch_id=branch_id)
    if resolved_branch_code:
        pattern = f'{prefix}-{resolved_branch_code}-{year}-%'
    else:
        pattern = f'{prefix}-{year}-%'

    q = db.session.query(model).filter(getattr(model, field_name).like(pattern))
    if tenant_id is not None and hasattr(model, 'tenant_id'):
        q = q.filter(model.tenant_id == tenant_id)
    latest = q.order_by(
        getattr(model, field_name).desc()
    ).first()
    
    if latest:
        try:
            last_number = int(str(getattr(latest, field_name)).split('-')[-1])
            next_number = last_number + 1
        except (TypeError, ValueError):
            next_number = 1
    else:
        next_number = 1

    if resolved_branch_code:
        return f'{prefix}-{resolved_branch_code}-{year}-{next_number:04d}'
    return f'{prefix}-{year}-{next_number:04d}'


def generate_number_and_save(
    prefix,
    model,
    field_name,
    save_func,
    date_format='%Y',
    branch_code=None,
    branch_id=None,
    tenant_id=None,
    max_attempts=20,
):
    """
    Generate a unique number and create the record via save_func().
    Retries on unique-constraint violation to handle concurrent requests.
    """
    from sqlalchemy.exc import IntegrityError
    for attempt in range(max_attempts):
        number = generate_number(
            prefix=prefix,
            model=model,
            field_name=field_name,
            date_format=date_format,
            branch_code=branch_code,
            branch_id=branch_id,
            tenant_id=tenant_id,
        )
        try:
            return save_func(number)
        except IntegrityError:
            db.session.rollback()
            continue
    raise RuntimeError(f'Could not generate unique number after {max_attempts} attempts')


def get_next_number(prefix, model_class, number_field='number', branch_code=None, branch_id=None):
    year = datetime.now().year
    resolved_branch_code = _resolve_branch_code(branch_code=branch_code, branch_id=branch_id)
    if resolved_branch_code:
        pattern = f'{prefix}-{resolved_branch_code}-{year}-%'
    else:
        pattern = f'{prefix}-{year}-%'
    
    last_record = db.session.query(model_class).filter(
        getattr(model_class, number_field).like(pattern)
    ).order_by(
        getattr(model_class, number_field).desc()
    ).first()
    
    if last_record:
        try:
            last_num = int(getattr(last_record, number_field).split('-')[-1])
        except (TypeError, ValueError):
            last_num = 0
        if resolved_branch_code:
            return f'{prefix}-{resolved_branch_code}-{year}-{last_num + 1:04d}'
        return f'{prefix}-{year}-{last_num + 1:04d}'

    if resolved_branch_code:
        return f'{prefix}-{resolved_branch_code}-{year}-0001'
    return f'{prefix}-{year}-0001'


def calculate_discount(amount, discount_percent):
    """Calculate discount amount from percentage"""
    amount = Decimal(str(amount))
    discount_percent = Decimal(str(discount_percent))
    return (amount * discount_percent / Decimal('100')).quantize(Decimal('0.01'))


def calculate_vat(amount, vat_rate):
    """Calculate VAT/Tax amount from rate"""
    amount = Decimal(str(amount))
    vat_rate = Decimal(str(vat_rate))
    return (amount * vat_rate / Decimal('100')).quantize(Decimal('0.01'))


def format_currency(amount, currency=None, lang='ar'):
    if not amount:
        return '0.00'

    try:
        if isinstance(amount, (int, float)):
            amount = Decimal(str(amount))

        settings_currency = None
        settings_symbol = None
        settings_position = None
        settings_decimals = None
        try:
            from models.system_settings import SystemSettings
            settings = SystemSettings.get_current()
            settings_currency = (getattr(settings, "default_currency", None) or "").strip() or None
            settings_symbol = (getattr(settings, "currency_symbol", None) or "").strip() or None
            settings_position = (getattr(settings, "currency_position", None) or "").strip() or None
            settings_decimals = getattr(settings, "decimal_places", None)
        except Exception:
            pass

        try:
            from models.tenant import Tenant
            tenant = Tenant.get_current()
            if tenant and tenant.default_currency:
                settings_currency = settings_currency or tenant.default_currency
        except Exception:
            pass

        from utils.currency_utils import get_system_default_currency, get_currency_symbol
        currency = (currency or settings_currency or get_system_default_currency()).upper()
        decimals = settings_decimals if isinstance(settings_decimals, int) and settings_decimals >= 0 else 2
        formatted = f'{amount:,.{decimals}f}'

        symbol = settings_symbol if settings_currency == currency and settings_symbol else get_currency_symbol(currency)
        position = settings_position if settings_currency == currency and settings_position else None
        if position not in ('before', 'after'):
            position = 'after' if lang == 'ar' else 'before'

        if position == 'before':
            return f'{symbol} {formatted}'
        return f'{formatted} {symbol}'

    except Exception:
        return str(amount)


def timeago(date):
    """Calculate time ago string"""
    if not date:
        return ''
    
    try:
        now = datetime.now(timezone.utc)
        if date.tzinfo is None:
            # Assume naive datetime is UTC or handle accordingly
            # For simplicity, let's assume it's system local time, but comparing with UTC is tricky.
            # Let's try to make it aware or just use now() naive if date is naive.
            if date.year < 1970: # Handle invalid dates
                return ''
            date = date.replace(tzinfo=timezone.utc)
            
        diff = now - date
        seconds = diff.total_seconds()
        
        if seconds < 60:
            return 'منذ لحظات'
        elif seconds < 3600:
            return f'منذ {int(seconds // 60)} دقيقة'
        elif seconds < 86400:
            return f'منذ {int(seconds // 3600)} ساعة'
        elif seconds < 604800:
            return f'منذ {int(seconds // 86400)} يوم'
        else:
            return date.strftime('%Y-%m-%d')
            
    except Exception:
        return str(date)


def create_audit_log(action, table_name=None, record_id=None, changes=None):
    from models import AuditLog
    # Ensure current_user is imported safely for scripts
    try:
        from flask_login import current_user
    except ImportError:
        current_user = None
    
    try:
        user_id = None
        # Check if we are in a request context and have a user
        if current_user:
             # Check if it's a real user object or AnonymousUserMixin
             if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
                 user_id = current_user.id
             elif hasattr(current_user, 'id'): # In case we mocked it with a simple object
                 user_id = current_user.id

        log = AuditLog(
            user_id=user_id,
            action=action,
            table_name=table_name,
            record_id=record_id,
            changes=changes,
            ip_address=request.remote_addr if request else None,
            user_agent=str(request.headers.get('User-Agent')) if request else None,
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        # Just log error but don't crash the app
        try:
            if current_app:
                current_app.logger.error(f'Failed to create audit log: {e}')
            else:
                print(f'Failed to create audit log: {e}')
        except:
             pass


def allowed_file(filename, allowed_extensions=None):
    if not filename:
        return False
    
    if allowed_extensions is None:
        config_extensions = current_app.config.get('ALLOWED_UPLOAD_EXTENSIONS', {})
        if 'all' in config_extensions:
            allowed_extensions = config_extensions['all']
        else:
            allowed_extensions = set()
            for ext_set in config_extensions.values():
                if isinstance(ext_set, set):
                    allowed_extensions.update(ext_set)
    
    return '.' in filename and \
           '.' + filename.rsplit('.', 1)[1].lower() in allowed_extensions


def save_uploaded_file(file, upload_folder='uploads', allowed_extensions=None):
    """حفظ ملف مرفوع مع فحوصات أمان"""
    if not file or not file.filename:
        return None
    
    if not allowed_file(file.filename, allowed_extensions):
        raise ValueError('File type not allowed')
    
    MAX_FILE_SIZE = 5 * 1024 * 1024
    file.seek(0, os.SEEK_END)
    file_length = file.tell()
    file.seek(0)
    
    if file_length > MAX_FILE_SIZE:
        raise ValueError('File size exceeds limit (5MB)')
    
    file_header = file.read(512)
    file.seek(0)
    
    if file_header.startswith(b'MZ') or file_header.startswith(b'\x7fELF'):
        raise ValueError('Executable files are not allowed')
    
    filename = secure_filename(file.filename)
    name, ext = os.path.splitext(filename)
    unique_filename = f'{name}_{uuid.uuid4().hex[:8]}{ext}'
    
    full_upload_folder = os.path.join(current_app.static_folder, upload_folder)
    os.makedirs(full_upload_folder, exist_ok=True)
    
    filepath = os.path.join(full_upload_folder, unique_filename)
    file.save(filepath)
    
    current_app.logger.info(f'File uploaded: {unique_filename} ({file_length} bytes)')
    
    return os.path.join(upload_folder, unique_filename).replace('\\', '/')


def convert_currency(amount, from_currency, to_currency=None):
    from services.currency_service import CurrencyService
    
    if to_currency is None:
        try:
            from models import Tenant
            tenant = Tenant.get_current()
            to_currency = tenant.default_currency if tenant else 'AED'
        except Exception:
            to_currency = 'AED'
    
    if from_currency == to_currency:
        return amount
    
    rate = CurrencyService.get_exchange_rate(from_currency, to_currency)
    return amount * Decimal(str(rate))


def generate_sku():
    return f'SKU-{uuid.uuid4().hex[:8].upper()}'


def generate_barcode():
    return f'{datetime.now().strftime("%Y%m%d")}{uuid.uuid4().hex[:6].upper()}'

