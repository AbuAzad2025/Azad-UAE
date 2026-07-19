"""
Partners Routes — إدارة الشركاء والمساهمين

Endpoints:
  • /partners/               — قائمة الشركاء
  • /partners/create         — إضافة شريك جديد
  • /partners/<id>           — تفاصيل الشريك
  • /partners/<id>/edit      — تعديل الشريك
  • /partners/<id>/statement — كشف حساب الشريك
  • /partners/distribute     — توزيع أرباح فترة
  • /partners/distributions  — قائمة التوزيعات
  • /partners/<id>/tx        — إضافة حركة يدوية
"""

from flask_babel import gettext

from datetime import date, datetime, timezone, timedelta
from decimal import Decimal

from extensions import db
from utils.db_safety import atomic_transaction
from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    request,
    jsonify,
)
from flask_login import login_required, current_user

from models import Partner, PartnerProfitDistribution, PartnerTransaction
from services.partner_service import PartnerService
from utils.decorators import permission_required
from utils.tenanting import get_active_tenant_id, tenant_query

partners_bp = Blueprint("partners", __name__, url_prefix="/partners")


# ── Helpers ───────────────────────────────────────────────────


def _tenant_id():
    return get_active_tenant_id(current_user)


def _parse_date(s: str | None) -> date:
    if not s:
        return datetime.now(timezone.utc).date()
    return datetime.strptime(s, "%Y-%m-%d").date()


# ── List ─────────────────────────────────────────────────────


@partners_bp.route("/")
@login_required
@permission_required("view_reports")
def index():
    """قائمة الشركاء"""
    q = tenant_query(Partner)
    scope = request.args.get("scope", "")
    if scope:
        q = q.filter_by(scope_type=scope)
    partners = q.order_by(Partner.is_active.desc(), Partner.name).all()
    return render_template("partners/index.html", partners=partners)


# ── Create ────────────────────────────────────────────────────


@partners_bp.route("/create", methods=["GET", "POST"])
@login_required
@permission_required("manage_users")
def create():
    """إضافة شريك جديد"""
    tid = _tenant_id()
    from models import Branch, Warehouse

    branches = tenant_query(Branch).all() if tid else []
    warehouses = tenant_query(Warehouse).all() if tid else []

    if request.method == "POST":
        try:
            scope_type = request.form.get("scope_type", "company")
            scope_id = request.form.get("scope_id", type=int) or None
            if scope_type == "company":
                scope_id = None

            partner = Partner(
                tenant_id=tid,
                name=request.form.get("name", "").strip(),
                name_en=request.form.get("name_en", "").strip() or None,
                code=request.form.get("code", "").strip() or None,
                scope_type=scope_type,
                scope_id=scope_id,
                partner_type=request.form.get("partner_type", "investor"),
                phone=request.form.get("phone", "").strip() or None,
                email=request.form.get("email", "").strip() or None,
                address=request.form.get("address", "").strip() or None,
                id_number=request.form.get("id_number", "").strip() or None,
                investment_amount=Decimal(
                    request.form.get("investment_amount", "0") or "0"
                ),
                share_percentage=Decimal(
                    request.form.get("share_percentage", "0") or "0"
                ),
                fixed_monthly_amount=Decimal(
                    request.form.get("fixed_monthly_amount", "0") or "0"
                ),
                expense_share_percentage=Decimal(
                    request.form.get("expense_share_percentage", "0") or "0"
                ),
                loss_share_percentage=Decimal(
                    request.form.get("loss_share_percentage", "0") or "0"
                ),
                min_profit_threshold=Decimal(
                    request.form.get("min_profit_threshold", "0") or "0"
                ),
                notes=request.form.get("notes", "").strip() or None,
                is_active=True,
            )
            with atomic_transaction("partner_create"):
                db.session.add(partner)
            flash(gettext("✅ تم إضافة الشريك بنجاح."), "success")
            return redirect(url_for("partners.index"))
        except Exception as e:
            flash(gettext(f"❌ خطأ: {e}"), "danger")

    return render_template(
        "partners/create.html", branches=branches, warehouses=warehouses
    )


# ── Detail & Edit ─────────────────────────────────────────────


@partners_bp.route("/<int:id>")
@login_required
@permission_required("view_reports")
def view(**kwargs):
    record_id = kwargs.pop("id")
    partner = tenant_query(Partner).filter_by(id=record_id).first_or_404()
    tid = _tenant_id()

    # Latest distributions
    latest_dists = PartnerProfitDistribution.query.filter_by(partner_id=record_id)
    if tid is not None:
        latest_dists = latest_dists.filter(PartnerProfitDistribution.tenant_id == tid)
    latest_dists = (
        latest_dists.order_by(PartnerProfitDistribution.period_end.desc())
        .limit(12)
        .all()
    )

    # Latest transactions
    latest_txs = PartnerTransaction.query.filter_by(partner_id=record_id)
    if tid is not None:
        latest_txs = latest_txs.filter(PartnerTransaction.tenant_id == tid)
    latest_txs = (
        latest_txs.order_by(PartnerTransaction.transaction_date.desc()).limit(20).all()
    )

    return render_template(
        "partners/view.html",
        partner=partner,
        latest_distributions=latest_dists,
        latest_transactions=latest_txs,
        balance_summary=partner.get_balance_summary(),
    )


@partners_bp.route("/<int:id>/edit", methods=["GET", "POST"])
@login_required
@permission_required("manage_users")
def edit(**kwargs):
    record_id = kwargs.pop("id")
    partner = tenant_query(Partner).filter_by(id=record_id).first_or_404()
    from models import Branch, Warehouse

    branches = tenant_query(Branch).all()
    warehouses = tenant_query(Warehouse).all()

    if request.method == "POST":
        try:
            scope_type = request.form.get("scope_type", partner.scope_type)
            scope_id = request.form.get("scope_id", type=int) or None
            if scope_type == "company":
                scope_id = None

            partner.name = request.form.get("name", partner.name).strip()
            partner.name_en = (
                request.form.get("name_en", partner.name_en).strip() or None
            )
            partner.code = request.form.get("code", partner.code).strip() or None
            partner.scope_type = scope_type
            partner.scope_id = scope_id
            partner.partner_type = request.form.get(
                "partner_type", partner.partner_type
            )
            partner.phone = request.form.get("phone", "").strip() or None
            partner.email = request.form.get("email", "").strip() or None
            partner.address = request.form.get("address", "").strip() or None
            partner.id_number = request.form.get("id_number", "").strip() or None
            partner.investment_amount = Decimal(
                request.form.get("investment_amount", "0") or "0"
            )
            partner.share_percentage = Decimal(
                request.form.get("share_percentage", "0") or "0"
            )
            partner.fixed_monthly_amount = Decimal(
                request.form.get("fixed_monthly_amount", "0") or "0"
            )
            partner.expense_share_percentage = Decimal(
                request.form.get("expense_share_percentage", "0") or "0"
            )
            partner.loss_share_percentage = Decimal(
                request.form.get("loss_share_percentage", "0") or "0"
            )
            partner.min_profit_threshold = Decimal(
                request.form.get("min_profit_threshold", "0") or "0"
            )
            partner.is_active = request.form.get("is_active") == "on"
            partner.notes = request.form.get("notes", "").strip() or None
            partner.updated_at = datetime.now(timezone.utc)

            with atomic_transaction("partner_edit"):
                db.session.flush()
            flash(gettext("✅ تم تحديث بيانات الشريك."), "success")
            return redirect(url_for("partners.view", id=record_id))
        except Exception as e:
            flash(gettext(f"❌ خطأ: {e}"), "danger")

    return render_template(
        "partners/edit.html", partner=partner, branches=branches, warehouses=warehouses
    )


# ── Statement ─────────────────────────────────────────────────


@partners_bp.route("/<int:id>/statement")
@login_required
@permission_required("view_reports")
def statement(**kwargs):
    record_id = kwargs.pop("id")
    partner = tenant_query(Partner).filter_by(id=record_id).first_or_404()

    end_date = _parse_date(request.args.get("end_date"))
    start_date = _parse_date(request.args.get("start_date"))
    if not request.args.get("start_date"):
        start_date = end_date.replace(day=1)

    stmt = PartnerService.get_partner_statement(partner.id, start_date, end_date)
    return render_template(
        "partners/statement.html",
        partner=partner,
        statement=stmt,
        start_date=start_date,
        end_date=end_date,
    )


# ── Distributions ─────────────────────────────────────────────


@partners_bp.route("/distributions")
@login_required
@permission_required("view_reports")
def distributions():
    tid = _tenant_id()
    q = PartnerProfitDistribution.query.filter_by(tenant_id=tid)
    status = request.args.get("status", "")
    if status:
        q = q.filter_by(status=status)
    dists = q.order_by(PartnerProfitDistribution.period_end.desc()).limit(200).all()
    return render_template("partners/distributions.html", distributions=dists)


@partners_bp.route("/distribute", methods=["GET", "POST"])
@login_required
@permission_required("manage_users")
def distribute():
    """توزيع أرباح فترة"""
    tid = _tenant_id()

    if request.method == "POST":
        try:
            period_start = _parse_date(request.form.get("period_start"))
            period_end = _parse_date(request.form.get("period_end"))
            with atomic_transaction("partner_distribute"):
                dist_ids = PartnerService.create_distributions(
                    tenant_id=int(tid or 0),
                    period_start=period_start,
                    period_end=period_end,
                    created_by=current_user.id,
                )
            flash(gettext(f"✅ تم إنشاء {len(dist_ids)} توزيع مسودة."), "success")
            return redirect(url_for("partners.distributions"))
        except Exception as e:
            flash(gettext(f"❌ خطأ: {e}"), "danger")

    today = datetime.now(timezone.utc).date()
    last_month_end = today.replace(day=1) - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    return render_template(
        "partners/distribute.html",
        default_start=last_month_start,
        default_end=last_month_end,
    )


@partners_bp.route("/distributions/<int:dist_id>/approve", methods=["POST"])
@login_required
@permission_required("manage_users")
def approve_distribution(dist_id):
    try:
        with atomic_transaction("partner_approve_distribution"):
            ok = PartnerService.approve_distribution(
                dist_id, current_user.id, tenant_id=_tenant_id()
            )
        if ok:
            flash(gettext("✅ تم اعتماد التوزيع."), "success")
        else:
            flash(gettext("❌ لم يتم اعتماد التوزيع."), "danger")
    except Exception as e:
        flash(gettext(f"❌ خطأ: {e}"), "danger")
    return redirect(url_for("partners.distributions"))


@partners_bp.route("/distributions/<int:dist_id>/pay", methods=["POST"])
@login_required
@permission_required("manage_payments")
def pay_distribution(dist_id):
    try:
        with atomic_transaction("partner_pay_distribution"):
            ok = PartnerService.pay_distribution(dist_id, tenant_id=_tenant_id())
        if ok:
            flash(gettext("✅ تم تسجيل الدفع."), "success")
        else:
            flash(gettext("❌ لم يتم تسجيل الدفع."), "danger")
    except Exception as e:
        flash(gettext(f"❌ خطأ: {e}"), "danger")
    return redirect(url_for("partners.distributions"))


# ── Manual Transaction ──────────────────────────────────────


@partners_bp.route("/<int:id>/tx", methods=["POST"])
@login_required
@permission_required("manage_payments")
def add_transaction(**kwargs):
    """إضافة حركة يدوية (مسحوبات / استثمار إضافي / تسوية)"""
    record_id = kwargs.pop("id")
    try:
        tx_type = request.form.get("transaction_type")
        amount = Decimal(request.form.get("amount", "0") or "0")
        notes = request.form.get("notes", "").strip()

        if tx_type == "withdrawal":
            amount = -abs(amount)

        with atomic_transaction("partner_add_transaction"):
            tx_id = PartnerService.add_transaction(
                partner_id=record_id,
                transaction_type=tx_type or "",
                amount=amount,
                notes=notes,
                created_by=current_user.id,
                tenant_id=_tenant_id(),
            )
        if tx_id is None:
            flash(gettext("❌ الشريك غير موجود أو خارج نطاق المستأجر."), "danger")
            return redirect(url_for("partners.index"))
        flash(gettext("✅ تم تسجيل الحركة."), "success")
    except Exception as e:
        flash(gettext(f"❌ خطأ: {e}"), "danger")
    return redirect(url_for("partners.view", id=id))


# ── API: Scope P&L preview ──────────────────────────────────


@partners_bp.route("/api/preview-pnl")
@login_required
@permission_required("view_reports")
def api_preview_pnl():
    """AJAX: preview P&L for a scope + period."""
    tid = _tenant_id()
    start = _parse_date(request.args.get("start"))
    end = _parse_date(request.args.get("end"))
    scope = request.args.get("scope_type", "company")
    scope_id = request.args.get("scope_id", type=int)

    pnl = PartnerService.calculate_scope_profit(
        int(tid or 0), start, end, scope, scope_id
    )
    return jsonify(pnl)
