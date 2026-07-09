"""Backup management routes for the owner blueprint."""

from routes.owner import (
    render_template, request, jsonify, flash, redirect, url_for, current_app, abort,
    login_required, current_user, db, Tenant,
    owner_required, is_global_owner_user, get_active_tenant_id,
    safe_redirect_target,
)
from services.logging_core import LoggingCore
from services.backup_service import BackupService
from routes.owner import owner_bp
from routes.owner.shared import _invalidate_owner_changes, _audit_owner_db_action, _owner_backup_filename, _backup_created_by_payload, _mask_db_uri

import logging
import os

logger = logging.getLogger(__name__)

@owner_bp.route('/backup-now', methods=['POST'])
@owner_required
def backup_now():
    """نسخة نظام كاملة — platform owner/developer فقط."""
    from services.backup_service import BackupService

    payload = request.get_json(silent=True) if request.is_json else None
    description = (
        (payload or {}).get('description')
        or request.form.get('description')
        or f'System backup by {getattr(current_user, "username", "user")}'
    )

    backup = BackupService.create_backup(
        manual=True,
        description=description,
        scope='system',
        created_by=_backup_created_by_payload(),
    )
    if backup:
        _audit_owner_db_action(
            'create_backup',
            {
                'filename': backup.get('filename'),
                'size_mb': backup.get('size_mb'),
                'backup_scope': 'system',
            },
        )

    if request.is_json:
        if backup:
            return jsonify({
                'success': True,
                'filename': backup.get('filename'),
                'size_mb': backup.get('size_mb'),
            })
        return jsonify({'success': False, 'message': 'فشل إنشاء النسخة الاحتياطية'}), 400
    else:
        if backup:
            flash(f'✅ تم إنشاء نسخة احتياطية: {backup["filename"]} ({backup["size_mb"]} MB)', 'success')
        else:
            flash('❌ فشل إنشاء النسخة الاحتياطية', 'danger')
        return redirect(safe_redirect_target(request.referrer, 'owner.dashboard'))

@owner_bp.route('/backups/create', methods=['POST'])
@owner_required
def create_scoped_backup():
    """إنشاء نسخة حسب النطاق: system | tenant | branch | store."""
    from services.backup_service import BackupService
    from utils.auth_helpers import is_global_owner_user
    from utils.tenanting import get_active_tenant_id
    from models.tenant import Tenant

    scope = (request.form.get('scope') or 'system').strip().lower()
    tenant_id = request.form.get('tenant_id', type=int)
    branch_id = request.form.get('branch_id', type=int)
    store_id = request.form.get('store_id', type=int)
    description = request.form.get('description') or ''

    if scope == 'system':
        if not is_global_owner_user(current_user):
            _audit_owner_db_action('create_backup_denied', {'scope': scope, 'reason': 'not_global_owner'})
            abort(403)
    elif scope in ('tenant', 'branch', 'store'):
        if is_global_owner_user(current_user):
            if not tenant_id:
                flash('اختر الشركة (tenant) للنسخة', 'warning')
                return redirect(url_for('owner.list_backups'))
        else:
            active_tid = get_active_tenant_id(current_user)
            if not active_tid:
                abort(403)
            if tenant_id and int(tenant_id) != int(active_tid):
                _audit_owner_db_action(
                    'create_backup_denied',
                    {'scope': scope, 'requested_tenant_id': tenant_id, 'active_tenant_id': active_tid},
                )
                abort(403)
            tenant_id = active_tid
        if scope == 'branch':
            if not branch_id:
                flash('اختر الفرع', 'warning')
                return redirect(url_for('owner.list_backups'))
            if not is_global_owner_user(current_user):
                if getattr(current_user, 'branch_id', None) != branch_id:
                    _audit_owner_db_action(
                        'create_backup_denied',
                        {'scope': scope, 'branch_id': branch_id},
                    )
                    abort(403)
        if scope == 'store' and not store_id:
            flash('اختر المتجر', 'warning')
            return redirect(url_for('owner.list_backups'))
    else:
        flash('نطاق النسخ غير مدعوم', 'warning')
        return redirect(url_for('owner.list_backups'))

    backup = BackupService.create_backup(
        manual=True,
        description=description or f'{scope} backup',
        scope=scope,
        tenant_id=tenant_id,
        branch_id=branch_id,
        store_id=store_id,
        created_by=_backup_created_by_payload(),
    )
    if backup:
        _audit_owner_db_action(
            'create_backup',
            {
                'filename': backup.get('filename'),
                'backup_scope': scope,
                'tenant_id': tenant_id,
            },
        )
        flash(f'تم إنشاء النسخة: {backup["filename"]}', 'success')
    else:
        flash('فشل إنشاء النسخة الاحتياطية', 'danger')
    return redirect(url_for('owner.list_backups'))

@owner_bp.route('/backups/list')
@owner_required
def list_backups():
    """قائمة النسخ الاحتياطية (مفلترة حسب الصلاحية)."""
    from services.backup_service import BackupService

    ctx = BackupService.get_list_backups_context(current_user)

    return render_template('owner/backups_list.html',
                         backups=ctx['backups'],
                         stats=ctx['stats'],
                         schedule_settings=ctx['schedule_settings'],
                         schedule_state=ctx['schedule_state'],
                         backup_dir=ctx['backup_dir'],
                         pg_tools=ctx['pg_tools'],
                         tenants=ctx['tenants'],
                         branches=ctx['branches'],
                         stores=ctx['stores'],
                         is_platform_owner=ctx['is_platform_owner'],
                         now=ctx['now'])

@owner_bp.route('/backups/info/<filename>')
@owner_required
def backup_info(filename):
    from services.backup_service import BackupService

    safe = _owner_backup_filename(filename)
    if not safe or not BackupService.user_may_access_backup(current_user, safe):
        return jsonify({'success': False, 'message': 'Invalid filename'}), 400
    info = BackupService.get_backup_info(safe)
    if not info:
        return jsonify({'success': False, 'message': 'Backup not found'}), 404
    return jsonify({'success': True, 'info': info})

@owner_bp.route('/backups/verify/<filename>', methods=['POST'])
@owner_required
def verify_backup(filename):
    """التحقق من سلامة نسخة احتياطية"""
    from services.backup_service import BackupService

    safe = _owner_backup_filename(filename)
    if not safe or not BackupService.user_may_access_backup(current_user, safe):
        return jsonify({'success': False, 'message': 'Invalid filename'}), 403

    result = BackupService.verify_backup(safe)
    if result.get('valid'):
        _audit_owner_db_action('verify_backup', {'filename': safe, 'format': result.get('format')})
        return jsonify({'success': True, 'verified': True, 'result': result})
    return jsonify({'success': True, 'verified': False, 'result': result}), 200

@owner_bp.route('/backups/prepare-restore/<filename>', methods=['GET', 'POST'])
@owner_required
def prepare_restore_backup(filename):
    """عرض أوامر الاستعادة الآمنة — لا يكتب على DB الحالية."""
    from services.backup_service import BackupService

    safe = _owner_backup_filename(filename)
    if not safe or not BackupService.user_may_access_backup(current_user, safe):
        flash('❌ غير مصرح بالوصول لهذه النسخة', 'danger')
        return redirect(url_for('owner.list_backups'))

    target_hint = (request.form.get('target_database_url') or '').strip()
    target_tenant_id = request.form.get('target_tenant_id', type=int)
    remap = request.form.get('remap') == '1'
    payload = BackupService.prepare_restore(
        safe,
        target_database_url=target_hint or None,
        target_tenant_id=target_tenant_id,
        remap=remap,
    )
    if request.method == 'POST' or request.args.get('format') == 'json':
        return jsonify(payload)
    if not payload.get('ok'):
        flash(payload.get('error', 'فشل تجهيز الأوامر'), 'danger')
        return redirect(url_for('owner.list_backups'))
    return render_template(
        'owner/backup_restore_instructions.html',
        filename=safe,
        commands=payload.get('commands', []),
        warning=payload.get('warning'),
        info=BackupService.get_backup_info(safe),
    )

@owner_bp.route('/backups/restore-target/<filename>', methods=['POST'])
@owner_required
def restore_backup_target(filename):
    """استعادة system backup إلى قاعدة بيانات جديدة فقط."""
    from services.backup_service import BackupService
    from utils.auth_helpers import is_global_owner_user

    safe = _owner_backup_filename(filename)
    if not safe or not is_global_owner_user(current_user):
        flash('❌ غير مصرح', 'danger')
        return redirect(url_for('owner.list_backups'))

    info = BackupService.get_backup_info(safe) or {}
    manifest = info.get('manifest') or {}
    scope = manifest.get('backup_scope') or 'system'
    target_url = (request.form.get('target_database_url') or '').strip()
    if not target_url:
        target_url = (os.environ.get('TARGET_TEST_DATABASE_URL') or '').strip()
    if not target_url:
        flash('❌ حدد TARGET_DATABASE_URL لقاعدة اختبار جديدة', 'danger')
        return redirect(url_for('owner.list_backups'))

    confirmation = (request.form.get('restore_confirm') or '').strip()
    remap = request.form.get('remap') == '1'
    target_tenant_id = request.form.get('target_tenant_id', type=int)
    dry_run = request.form.get('dry_run') == '1'
    if scope in ('tenant', 'branch', 'store'):
        result = BackupService.restore_scoped_backup_to_target_db(
            safe,
            target_url,
            confirmation=confirmation,
            remap=remap,
            target_tenant_id=target_tenant_id,
            restore_uploads=request.form.get('restore_uploads') == '1',
            dry_run=dry_run,
        )
    else:
        result = BackupService.restore_backup_to_target_db(
            safe,
            target_url,
            confirmation=confirmation,
            restore_uploads=request.form.get('restore_uploads') == '1',
        )
    if result.get('ok'):
        _audit_owner_db_action(
            'restore_backup_target',
            {
                'filename': safe,
                'target_db': result.get('target_db'),
                'masked_host': result.get('masked_host'),
            },
        )
        flash('✅ تمت الاستعادة إلى قاعدة الهدف', 'success')
    else:
        err = '; '.join(result.get('errors') or ['restore failed'])
        flash(f'❌ فشلت الاستعادة: {err[:300]}', 'danger')
    return redirect(url_for('owner.list_backups'))

@owner_bp.route('/backups/delete', methods=['POST'])
@owner_required
def delete_backup():
    """حذف نسخة احتياطية - يدوية فقط"""
    from services.backup_service import BackupService

    filename = request.form.get('filename')
    safe = _owner_backup_filename(filename or '')
    if not safe or not BackupService.user_may_access_backup(current_user, safe):
        flash('❌ اسم الملف مطلوب أو غير صالح!', 'danger')
        return redirect(url_for('owner.list_backups'))

    backups = BackupService.list_backups_for_user(current_user)
    backup_exists = any(b['filename'] == safe for b in backups)

    if not backup_exists:
        flash('❌ النسخة الاحتياطية غير موجودة!', 'danger')
        return redirect(url_for('owner.list_backups'))

    success = BackupService.delete_backup(safe)

    if success:
        _audit_owner_db_action('delete_backup', {'filename': safe})
        flash(f'✅ تم حذف النسخة الاحتياطية: {safe}', 'success')
    else:
        flash('❌ فشل حذف النسخة الاحتياطية!', 'danger')

    return redirect(url_for('owner.list_backups'))

@owner_bp.route('/backups/download/<filename>')
@owner_required
def download_backup(filename):
    """تحميل نسخة احتياطية"""
    from services.backup_service import BackupService
    from flask import send_file
    import os

    safe = _owner_backup_filename(filename)
    if not safe or not BackupService.user_may_access_backup(current_user, safe):
        _audit_owner_db_action('download_backup_denied', {'filename': filename})
        flash('❌ غير مصرح', 'danger')
        return redirect(url_for('owner.list_backups'))
    backup_path = os.path.join(BackupService.BACKUP_DIR, safe)

    if not os.path.exists(backup_path):
        flash('❌ النسخة الاحتياطية غير موجودة!', 'danger')
        return redirect(url_for('owner.list_backups'))

    try:
        mimetype = 'application/gzip' if safe.endswith('.gz') else 'application/octet-stream'
        _audit_owner_db_action('download_backup', {'filename': safe})
        return send_file(
            backup_path,
            as_attachment=True,
            download_name=safe,
            mimetype=mimetype
        )
    except Exception as e:
        flash(f'❌ فشل التحميل: {str(e)}', 'danger')
        return redirect(url_for('owner.list_backups'))

@owner_bp.route('/scheduled-backups', methods=['GET', 'POST'])
@owner_required
def scheduled_backups():
    """النسخ الاحتياطي المجدول"""
    from services.backup_service import BackupService

    if request.method == 'POST':
        # حفظ إعدادات الجدولة
        settings = {
            'enabled': request.form.get('enabled') == 'on',
            'frequency': request.form.get('frequency', 'daily'),
            'backup_time': request.form.get('backup_time', '02:00'),
            'keep_count': int(request.form.get('keep_count', 5)),
        }
        BackupService.save_schedule_settings(settings)

        flash('✅ تم حفظ إعدادات النسخ الاحتياطي', 'success')
        return redirect(url_for('owner.scheduled_backups'))

    # قراءة الإعدادات الحالية
    settings = BackupService.get_schedule_settings()
    schedule_state = BackupService.get_schedule_state()

    # قائمة النسخ التلقائية
    backups = BackupService.list_backups(auto_only=True)
    stats = BackupService.get_backup_stats()

    return render_template('owner/scheduled_backups.html',
                         settings=settings,
                         schedule_state=schedule_state,
                         backups=backups,
                         stats=stats)

