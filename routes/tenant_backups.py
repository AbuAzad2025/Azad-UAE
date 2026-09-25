"""Tenant self-service backups — own company only.

Platform boundary: tenant admins may create / list / download / verify /
delete backups scoped to their own tenant. Restore paths stay owner-only
(separate database), and system backups are never visible here.
"""

import logging
import os

from flask import Blueprint, flash, redirect, render_template, send_file, url_for
from flask_babel import gettext
from flask_login import current_user, login_required

from extensions import limiter
from services.backup_service import BackupService
from utils.decorators import permission_required
from utils.tenanting import get_active_tenant_id

logger = logging.getLogger(__name__)

tenant_backups_bp = Blueprint("tenant_backups", __name__, url_prefix="/backups")


@tenant_backups_bp.route("/")
@login_required
@permission_required("manage_backups")
def index():
    """List this tenant's own backups plus the manual-create form."""
    tid = get_active_tenant_id(current_user)
    if tid is None:
        flash(gettext("اختر الشركة أولاً."), "warning")
        return redirect(url_for("main.dashboard"))
    backups = BackupService.list_backups_for_user(current_user)
    return render_template("backups/list.html", backups=backups)


@tenant_backups_bp.route("/create", methods=["POST"])
@login_required
@permission_required("manage_backups")
@limiter.limit("5 per hour")
def create():
    """Create a manual backup of the user's own company (rate-limited)."""
    result = BackupService.create_tenant_manual_backup(current_user)
    if result.get("ok"):
        flash(
            gettext("تم إنشاء النسخة الاحتياطية: %(filename)s", filename=result.get("filename")),
            "success",
        )
    elif result.get("error") == "rate_limited":
        flash(
            gettext(
                "لديك نسخة حديثة. حاول بعد %(mins)s دقيقة.",
                mins=result.get("retry_after_minutes", 60),
            ),
            "warning",
        )
    else:
        logger.warning("Tenant manual backup failed: %s", result.get("error"))
        flash(gettext("تعذر إنشاء النسخة الاحتياطية."), "danger")
    return redirect(url_for("tenant_backups.index"))


def _owned_or_deny(filename):
    """Sanitize + verify the file belongs to the user's tenant."""
    safe = BackupService.sanitize_filename(filename)
    if not safe or not BackupService.user_may_access_backup(current_user, safe):
        return None
    return safe


@tenant_backups_bp.route("/download/<filename>")
@login_required
@permission_required("manage_backups")
def download(filename):
    """Download one of this tenant's own backup files."""
    safe = _owned_or_deny(filename)
    if not safe:
        flash(gettext("غير مصرح بالوصول إلى هذا الملف."), "danger")
        return redirect(url_for("tenant_backups.index"))
    path = os.path.join(BackupService.BACKUP_DIR, safe)
    return send_file(path, as_attachment=True, download_name=safe)


@tenant_backups_bp.route("/verify/<filename>", methods=["POST"])
@login_required
@permission_required("manage_backups")
def verify(filename):
    """Verify the integrity of one of this tenant's own backups (read-only)."""
    safe = _owned_or_deny(filename)
    if not safe:
        flash(gettext("غير مصرح بالوصول إلى هذا الملف."), "danger")
        return redirect(url_for("tenant_backups.index"))
    result = BackupService.verify_backup(safe)
    if result.get("valid"):
        flash(gettext("النسخة سليمة وتم التحقق منها."), "success")
    else:
        flash(gettext("فشل التحقق من النسخة."), "danger")
    return redirect(url_for("tenant_backups.index"))


@tenant_backups_bp.route("/delete/<filename>", methods=["POST"])
@login_required
@permission_required("manage_backups")
def delete(filename):
    """Delete one of this tenant's own backup files."""
    safe = _owned_or_deny(filename)
    if not safe:
        flash(gettext("غير مصرح بالوصول إلى هذا الملف."), "danger")
        return redirect(url_for("tenant_backups.index"))
    if BackupService.delete_backup(safe):
        flash(gettext("تم حذف النسخة."), "success")
    else:
        flash(gettext("تعذر حذف النسخة."), "danger")
    return redirect(url_for("tenant_backups.index"))
