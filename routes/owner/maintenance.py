"""Maintenance routes for the Owner Dashboard."""

from flask_babel import gettext

from services.logging_core import LoggingCore
from services.maintenance_service import (
    cleanup_test_databases_api,
    fix_cost_centers_index_api,
    fix_default_tenant_metadata_api,
    rebuild_gl_tree_api,
    regenerate_default_backup_api,
    run_default_tenant_maintenance_api,
)
from utils.db_safety import atomic_transaction

from .common import (
    company_admin_required,
    current_app,
    error_response,
    owner_bp,
    request,
    success_response,
)


@owner_bp.route("/maintenance/fix-cost-centers", methods=["POST"])
@company_admin_required
def maintenance_fix_cost_centers():
    """إصلاح فهارس مراكز التكلفة وإزالة السجلات المهجورة (NULL tenant_id)"""
    confirm = request.form.get("confirm")
    if confirm != "FIX_COST_CENTERS":
        return error_response(
            message=gettext("يجب كتابة FIX_COST_CENTERS للتأكيد"),
            status_code=400,
        )

    try:
        with atomic_transaction("fix_cost_centers"):
            result = fix_cost_centers_index_api()

        LoggingCore.log_audit(
            "fix_cost_centers",
            "system_maintenance",
            0,
            {"status": "completed", "result": str(result)},
        )
        return success_response(
            message=gettext("✅ تم إصلاح فهارس مراكز التكلفة بنجاح")
        )
    except Exception as e:
        current_app.logger.error("maintenance_fix_cost_centers failed: %s", e)
        LoggingCore.log_error(
            message=f"fix_cost_centers failed: {e}",
            category="MAINTENANCE",
            level="ERROR",
            source="routes.owner.maintenance_fix_cost_centers",
            exception=e,
        )
        return error_response(message=gettext(f"خطأ: {str(e)}"), status_code=500)


@owner_bp.route("/maintenance/rebuild-gl-tree", methods=["POST"])
@company_admin_required
def maintenance_rebuild_gl_tree():
    """إعادة بناء شجرة الحسابات المحاسبية لجميع المستأجرين"""
    confirm = request.form.get("confirm")
    if confirm != "REBUILD_GL_TREE":
        return error_response(
            message=gettext("يجب كتابة REBUILD_GL_TREE للتأكيد"),
            status_code=400,
        )

    cleanup_extra = request.form.get("cleanup_extra") == "on"

    try:
        with atomic_transaction("rebuild_gl_tree"):
            result = rebuild_gl_tree_api(cleanup_extra=cleanup_extra)

        LoggingCore.log_audit(
            "rebuild_gl_tree",
            "system_maintenance",
            0,
            {"cleanup_extra": cleanup_extra, "result": result},
        )
        total_created = sum(t.get("created", 0) for t in result.get("tenants", []))
        total_updated = sum(t.get("updated", 0) for t in result.get("tenants", []))
        return success_response(
            message=gettext(
                f"✅ تم إعادة بناء شجرة الحسابات - تمت إضافة {total_created} وتحديث {total_updated} حساب"
            ),
            data={"result": result},
        )
    except Exception as e:
        current_app.logger.error("maintenance_rebuild_gl_tree failed: %s", e)
        LoggingCore.log_error(
            message=f"rebuild_gl_tree failed: {e}",
            category="MAINTENANCE",
            level="ERROR",
            source="routes.owner.maintenance_rebuild_gl_tree",
            exception=e,
        )
        return error_response(message=gettext(f"خطأ: {str(e)}"), status_code=500)


@owner_bp.route("/maintenance/fix-default-tenant", methods=["POST"])
@company_admin_required
def maintenance_fix_default_tenant():
    """تصحيح بيانات المستأجر الافتراضي (patch NOT NULL columns)"""
    confirm = request.form.get("confirm")
    if confirm != "FIX_DEFAULT_TENANT":
        return error_response(
            message=gettext("يجب كتابة FIX_DEFAULT_TENANT للتأكيد"),
            status_code=400,
        )

    dry_run = request.form.get("dry_run") == "on"

    try:
        with atomic_transaction("fix_default_tenant"):
            result = fix_default_tenant_metadata_api(dry_run=dry_run)

        LoggingCore.log_audit(
            "fix_default_tenant_metadata",
            "system_maintenance",
            0,
            {"dry_run": dry_run, "result": result},
        )
        patched = len(result.get("patched", []))
        if dry_run:
            return success_response(
                message=gettext(f"🔍 تجربة جافة: سيتم تصحيح {patched} عمود"),
                data={"result": result},
            )
        return success_response(
            message=gettext(f"✅ تم تصحيح {patched} عمود في بيانات المستأجر الافتراضي"),
            data={"result": result},
        )
    except Exception as e:
        current_app.logger.error("maintenance_fix_default_tenant failed: %s", e)
        LoggingCore.log_error(
            message=f"fix_default_tenant_metadata failed: {e}",
            category="MAINTENANCE",
            level="ERROR",
            source="routes.owner.maintenance_fix_default_tenant",
            exception=e,
        )
        return error_response(message=gettext(f"خطأ: {str(e)}"), status_code=500)


@owner_bp.route("/maintenance/regenerate-default-backup", methods=["POST"])
@company_admin_required
def maintenance_regenerate_default_backup():
    """تجديد النسخة الاحتياطية للمستأجر الافتراضي"""
    confirm = request.form.get("confirm")
    if confirm != "REGENERATE_DEFAULT_BACKUP":
        return error_response(
            message=gettext("يجب كتابة REGENERATE_DEFAULT_BACKUP للتأكيد"),
            status_code=400,
        )

    dry_run = request.form.get("dry_run") == "on"

    try:
        # BackupService doesn't need atomic_transaction
        result = regenerate_default_backup_api(dry_run=dry_run)

        LoggingCore.log_audit(
            "regenerate_default_backup",
            "system_maintenance",
            0,
            {"dry_run": dry_run, "backup": result},
        )
        if dry_run:
            return success_response(
                message=gettext("🔍 تجربة جافة: ستتم إعادة إنشاء النسخة الاحتياطية"),
                data={"result": result},
            )
        return success_response(
            message=gettext(f"✅ تم تجديد النسخة الاحتياطية: {result}"),
            data={"result": result},
        )
    except Exception as e:
        current_app.logger.error("maintenance_regenerate_default_backup failed: %s", e)
        LoggingCore.log_error(
            message=f"regenerate_default_backup failed: {e}",
            category="MAINTENANCE",
            level="ERROR",
            source="routes.owner.maintenance_regenerate_default_backup",
            exception=e,
        )
        return error_response(message=gettext(f"خطأ: {str(e)}"), status_code=500)


@owner_bp.route("/maintenance/run-default-tenant-maintenance", methods=["POST"])
@company_admin_required
def maintenance_run_default_tenant_maintenance():
    """تشغيل الصيانة الكاملة للمستأجر الافتراضي (patch + backup)"""
    confirm = request.form.get("confirm")
    if confirm != "RUN_DEFAULT_TENANT_MAINTENANCE":
        return error_response(
            message=gettext("يجب كتابة RUN_DEFAULT_TENANT_MAINTENANCE للتأكيد"),
            status_code=400,
        )

    dry_run = request.form.get("dry_run") == "on"

    try:
        with atomic_transaction("run_default_tenant_maintenance"):
            result = run_default_tenant_maintenance_api(dry_run=dry_run)

        LoggingCore.log_audit(
            "run_default_tenant_maintenance",
            "system_maintenance",
            0,
            {"dry_run": dry_run, "result": result},
        )
        patched = len(result.get("patched", []))
        if dry_run:
            return success_response(
                message=gettext(f"🔍 تجربة جافة: سيتم تصحيح {patched} عمود وتجديد النسخة"),
                data={"result": result},
            )
        backup = result.get("backup_regenerated", "completed")
        return success_response(
            message=gettext(f"✅ صيانة كاملة: {patched} عمود مصحح، نسخة احتياطية: {backup}"),
            data={"result": result},
        )
    except Exception as e:
        current_app.logger.error("maintenance_run_default_tenant_maintenance failed: %s", e)
        LoggingCore.log_error(
            message=f"run_default_tenant_maintenance failed: {e}",
            category="MAINTENANCE",
            level="ERROR",
            source="routes.owner.maintenance_run_default_tenant_maintenance",
            exception=e,
        )
        return error_response(message=gettext(f"خطأ: {str(e)}"), status_code=500)


@owner_bp.route("/maintenance/cleanup-test-dbs", methods=["POST"])
@company_admin_required
def maintenance_cleanup_test_dbs():
    """تنظيف قواعد البيانات الاختبارية القديمة"""
    confirm = request.form.get("confirm")
    if confirm != "CLEANUP_TEST_DBS":
        return error_response(
            message=gettext("يجب كتابة CLEANUP_TEST_DBS للتأكيد"),
            status_code=400,
        )

    dry_run = request.form.get("dry_run") == "on"

    try:
        # This needs AUTOCOMMIT connection, not atomic_transaction
        result = cleanup_test_databases_api(dry_run=dry_run)

        LoggingCore.log_audit(
            "cleanup_test_databases",
            "system_maintenance",
            0,
            {"dry_run": dry_run, "result": result},
        )
        dropped = len(result.get("dropped", []))
        if dry_run:
            return success_response(
                message=gettext(f"🔍 تجربة جافة: سيتم حذف {dropped} قاعدة بيانات"),
                data={"result": result},
            )
        return success_response(
            message=gettext(f"✅ تم حذف {dropped} قاعدة بيانات اختبار"),
            data={"result": result},
        )
    except Exception as e:
        current_app.logger.error("maintenance_cleanup_test_dbs failed: %s", e)
        LoggingCore.log_error(
            message=f"cleanup_test_databases failed: {e}",
            category="MAINTENANCE",
            level="ERROR",
            source="routes.owner.maintenance_cleanup_test_dbs",
            exception=e,
        )
        return error_response(message=gettext(f"خطأ: {str(e)}"), status_code=500)
