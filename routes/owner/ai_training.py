"""Owner AI-training routes — browser-based memory management per tenant."""

import logging

from flask_babel import gettext
from flask_login import current_user

from services.ai_training_service import (
    add_qa,
    count_memories,
    list_memories,
    submit_correction,
    toggle_memory,
)
from services.owner_ops_service import OwnerOpsService
from utils.db_safety import atomic_transaction

from .common import (
    abort,
    flash,
    owner_bp,
    owner_required,
    redirect,
    render_template,
    request,
    url_for,
)

logger = logging.getLogger(__name__)


def _resolve_training_tenant():
    """Validate the ?tenant_id= parameter against active tenants."""
    tid = request.args.get("tenant_id", type=int) or request.form.get("tenant_id", type=int)
    if not tid:
        return None
    tenant = OwnerOpsService.get_tenant(int(tid))
    if not tenant or not getattr(tenant, "is_active", False):
        abort(404)
    return tenant


def _redirect_back(tenant_id):
    return redirect(url_for("owner.ai_training", tenant_id=tenant_id))


@owner_bp.route("/ai-training")
@owner_required
def ai_training():
    """Owner training dashboard — memory table, Q&A form, corrections."""
    tenant = _resolve_training_tenant()
    tenants = OwnerOpsService.active_ai_tenants()
    memories = []
    stats = {"total": 0, "active": 0, "corrected": 0}
    if tenant is not None:
        search = request.args.get("q", "")
        category = request.args.get("category", "")
        show_all = request.args.get("show_all") == "1"
        memories = list_memories(tenant.id, search=search, category=category, include_inactive=show_all)
        stats = count_memories(tenant.id)
    return render_template(
        "owner/ai_training.html",
        tenant=tenant,
        tenants=tenants,
        memories=memories,
        stats=stats,
    )


@owner_bp.route("/ai-training/qa", methods=["POST"])
@owner_required
def ai_training_qa():
    """Add or refresh one tenant-scoped Q&A pair."""
    tenant = _resolve_training_tenant()
    if tenant is None:
        abort(404)
    try:
        with atomic_transaction("ai_training_qa"):
            add_qa(
                request.form.get("question", ""),
                request.form.get("answer", ""),
                request.form.get("category", "general"),
                tenant.id,
            )
        flash(gettext("تم حفظ الزوج التدريبي بنجاح."), "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    except Exception:
        logger.exception("Owner AI training QA failed")
        flash(gettext("تعذر حفظ الزوج التدريبي."), "danger")
    return _redirect_back(tenant.id)


@owner_bp.route("/ai-training/<int:memory_id>/toggle", methods=["POST"])
@owner_required
def ai_training_toggle(memory_id):
    """Activate or deactivate one memory row (ownership-checked)."""
    tenant = _resolve_training_tenant()
    if tenant is None:
        abort(404)
    try:
        active = request.form.get("active") == "1"
        with atomic_transaction("ai_training_toggle"):
            toggle_memory(memory_id, tenant.id, active)
        flash(gettext("تم تحديث حالة الذاكرة."), "success")
    except Exception:
        logger.exception("Owner AI training toggle failed")
        flash(gettext("تعذر تحديث الذاكرة."), "danger")
    return _redirect_back(tenant.id)


@owner_bp.route("/ai-training/correct", methods=["POST"])
@owner_required
def ai_training_correct():
    """Submit an owner correction for a wrong assistant answer."""
    tenant = _resolve_training_tenant()
    if tenant is None:
        abort(404)
    try:
        with atomic_transaction("ai_training_correct"):
            submit_correction(
                request.form.get("question", ""),
                request.form.get("correct_answer", ""),
                tenant.id,
                current_user.id,
            )
        flash(gettext("تم حفظ التصحيح وسيستخدمه المساعد."), "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    except Exception:
        logger.exception("Owner AI training correction failed")
        flash(gettext("تعذر حفظ التصحيح."), "danger")
    return _redirect_back(tenant.id)
