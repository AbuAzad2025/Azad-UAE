"""Owner Advanced AI-Training routes — file upload, progress dashboard, analytics."""

import logging
import os
from datetime import UTC, datetime

from flask import abort, flash, jsonify, redirect, render_template, request, url_for
from flask_babel import gettext
from flask_login import current_user

from services.advanced_trainer import AdvancedTrainer
from services.owner_ops_service import OwnerOpsService
from services.training_importer import training_importer
from services.training_progress import (
    get_concept_details,
    get_knowledge_graph_relationships,
    get_learning_velocity,
    get_training_health_report,
    get_training_metrics,
    get_training_progress,
)
from utils.db_safety import atomic_transaction

from .common import (
    owner_bp,
    owner_required,
)

logger = logging.getLogger(__name__)

UPLOAD_FOLDER = "uploads/training"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {".json", ".xlsx", ".xls"}


def _resolve_training_tenant():
    """Validate the ?tenant_id= parameter against active tenants."""
    tid = request.args.get("tenant_id", type=int) or request.form.get("tenant_id", type=int)
    if not tid:
        return None
    tenant = OwnerOpsService.get_tenant(int(tid))
    if not tenant or not getattr(tenant, "is_active", False):
        abort(404)
    return tenant


def _allowed_file(filename: str) -> bool:
    """Check if file extension is allowed."""
    ext = os.path.splitext(filename.lower())[1]
    return ext in ALLOWED_EXTENSIONS


@owner_bp.route("/ai-training/upload", methods=["GET", "POST"])
@owner_required
def ai_training_upload():
    """Upload training data from JSON or Excel files."""
    tenant = _resolve_training_tenant()
    tenants = OwnerOpsService.active_ai_tenants()

    if request.method == "GET":
        return render_template(
            "owner/ai_training_upload.html",
            tenant=tenant,
            tenants=tenants,
        )

    # POST - Handle file upload
    if "file" not in request.files:
        flash(gettext("لم يتم اختيار ملف."), "danger")
        return redirect(request.url)

    file = request.files["file"]
    if file.filename == "":
        flash(gettext("لم يتم اختيار ملف."), "danger")
        return redirect(request.url)

    if not _allowed_file(file.filename):
        flash(gettext("نوع الملف غير مدعوم. مسموح: JSON, XLSX, XLS"), "danger")
        return redirect(request.url)

    if not tenant:
        flash(gettext("يرجى اختيار مستأجر أولاً."), "danger")
        return redirect(request.url)

    try:
        # Save file securely
        safe_name = training_importer.get_safe_filename(file.filename)
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        filename = f"{tenant.id}_{timestamp}_{safe_name}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        # Process based on file type (flush-only service; commit via atomic_transaction)
        ext = os.path.splitext(filename.lower())[1]
        with atomic_transaction("ai_training_upload"):
            if ext == ".json":
                result = training_importer.import_from_json(filepath, tenant.id, current_user.id)
            else:  # .xlsx or .xls
                result = training_importer.import_from_excel(filepath, tenant.id, current_user.id)

        if result["success"]:
            flash(
                gettext(
                    "تم استيراد %(count)d سجل تدريبي بنجاح من %(total)d سجل.",
                    count=result["processed"],
                    total=result["total"],
                ),
                "success",
            )
        else:
            flash(gettext("فشل الاستيراد: %(error)s", error=result.get("error", "Unknown error")), "danger")

        return redirect(url_for("owner.ai_training_upload", tenant_id=tenant.id))

    except Exception:
        logger.exception("Training file upload failed")
        flash(gettext("حدث خطأ أثناء معالجة الملف."), "danger")
        return redirect(request.url)


@owner_bp.route("/ai-training/progress")
@owner_required
def ai_training_progress():
    """Training progress dashboard with KPIs and charts."""
    tenant = _resolve_training_tenant()
    tenants = OwnerOpsService.active_ai_tenants()

    progress_data = {}
    metrics_data = {}
    health_report = {}
    velocity_data = {}

    if tenant:
        domain = request.args.get("domain", "")
        progress_data = get_training_progress(tenant.id, domain)
        metrics_data = get_training_metrics(tenant.id)
        health_report = get_training_health_report(tenant.id)
        velocity_data = get_learning_velocity(tenant.id)

    return render_template(
        "owner/ai_training_progress.html",
        tenant=tenant,
        tenants=tenants,
        progress_data=progress_data,
        metrics_data=metrics_data,
        health_report=health_report,
        velocity_data=velocity_data,
        selected_domain=request.args.get("domain", ""),
    )


@owner_bp.route("/ai-training/metrics")
@owner_required
def ai_training_metrics():
    """Detailed training metrics API."""
    tenant = _resolve_training_tenant()
    if not tenant:
        abort(404)

    metrics = get_training_metrics(tenant.id)
    return jsonify(metrics)


@owner_bp.route("/ai-training/concept/<concept_name>")
@owner_required
def ai_training_concept(concept_name):
    """Detailed concept information."""
    tenant = _resolve_training_tenant()
    if not tenant:
        abort(404)

    details = get_concept_details(tenant.id, concept_name)
    return jsonify(details)


@owner_bp.route("/ai-training/knowledge-graph")
@owner_required
def ai_training_knowledge_graph():
    """Knowledge graph relationships."""
    tenant = _resolve_training_tenant()
    if not tenant:
        abort(404)

    concept = request.args.get("concept", "")
    relationships = get_knowledge_graph_relationships(tenant.id, concept)
    return jsonify({"relationships": relationships})


@owner_bp.route("/ai-training/health")
@owner_required
def ai_training_health():
    """Training health report."""
    tenant = _resolve_training_tenant()
    if not tenant:
        abort(404)

    health = get_training_health_report(tenant.id)
    return jsonify(health)


@owner_bp.route("/ai-training/batches")
@owner_required
def ai_training_batches():
    """List training batches."""
    tenant = _resolve_training_tenant()
    if not tenant:
        abort(404)

    from models.ai_training_advanced import AiTrainingBatch
    from utils.tenanting import tenant_query

    batches = (
        tenant_query(AiTrainingBatch)
        .filter(AiTrainingBatch.tenant_id == tenant.id)
        .order_by(AiTrainingBatch.created_at.desc())
        .limit(50)
        .all()
    )

    return render_template(
        "owner/ai_training_batches.html",
        tenant=tenant,
        batches=[b.to_dict() for b in batches],
    )


@owner_bp.route("/ai-training/semantic-train", methods=["POST"])
@owner_required
def ai_semantic_train():
    """Train from semantic Q&A pair."""
    tenant = _resolve_training_tenant()
    if not tenant:
        abort(404)

    question = request.form.get("question", "").strip()
    answer = request.form.get("answer", "").strip()

    if not question or not answer:
        flash(gettext("السؤال والإجابة مطلوبان."), "danger")
        return redirect(url_for("owner.ai_training_progress", tenant_id=tenant.id))

    try:
        with atomic_transaction("semantic_train"):
            result = AdvancedTrainer().train_semantic_model(tenant.id, question, answer)
        flash(
            gettext(
                "تم التدريب الدلالي بنجاح: %(concepts)d مفاهيم مستخلصة.",
                concepts=result["concepts_extracted"],
            ),
            "success",
        )
    except Exception:
        logger.exception("Semantic training failed")
        flash(gettext("فشل التدريب الدلالي."), "danger")

    return redirect(url_for("owner.ai_training_progress", tenant_id=tenant.id))
