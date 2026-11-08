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

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_babel import gettext
from flask_login import current_user, login_required

from extensions import db
from models import Partner
from services.partner_service import PartnerService
from utils.api_response import success_response
from utils.db_safety import atomic_transaction
from utils.decorators import permission_required
from utils.tenanting import get_active_tenant_id, tenant_query

partners_bp = Blueprint("partners", __name__, url_prefix="/partners")


# ── Helpers ───────────────────────────────────────────────────


def _tenant_id():
    return get_active_tenant_id(current_user)


def _parse_date(s: str | None) -> date:
    if not s:
        return datetime.now(UTC).date()
    return datetime.strptime(s, "%Y-%m-%d").date()


def _parse_partner_financials(form, existing=None):
    """Parse and range-check the financial columns of a partner.

    The tenant super admin (or the owner) may set any percentage, but a
    share must stay a percentage: each of profit share, expense share and
    loss share sits in [0, 100]; investment, fixed and threshold are
    non-negative amounts. ``existing`` lets edits re-read untouched fields.
    """

    def _field(name, default="0"):
        raw = form.get(name, None)
        if raw is None or raw == "":
            raw = getattr(existing, name, default) if existing is not None else default
        try:
            return Decimal(str(raw))
        except Exception:
            return Decimal(default)

    try:
        investment = _field("investment_amount")
        share = _field("share_percentage")
        fixed = _field("fixed_monthly_amount")
        expense = _field("expense_share_percentage")
        loss = _field("loss_share_percentage")
        threshold = _field("min_profit_threshold")
    except Exception:
        return None, gettext("قيمة مالية غير صحيحة.")
    if not (Decimal("0") <= share <= Decimal("100")):
        return None, gettext("نسبة الربح يجب أن تكون بين 0 و 100.")
    if not (Decimal("0") <= expense <= Decimal("100")):
        return None, gettext("نسبة تحمل المصاريف يجب أن تكون بين 0 و 100.")
    if not (Decimal("0") <= loss <= Decimal("100")):
        return None, gettext("نسبة تحمل الخسارة يجب أن تكون بين 0 و 100.")
    if investment < Decimal("0") or fixed < Decimal("0") or threshold < Decimal("0"):
        return None, gettext("المبالغ يجب ألا تكون سالبة.")
    return {
        "investment_amount": investment,
        "share_percentage": share,
        "fixed_monthly_amount": fixed,
        "expense_share_percentage": expense,
        "loss_share_percentage": loss,
        "min_profit_threshold": threshold,
    }, None


def _scope_share_total_exceeds(tenant_id, scope_type, scope_id, new_share, exclude_id=None) -> bool:
    """True when one more partner would push a scope's shares past 100%."""
    q = Partner.query.filter_by(tenant_id=tenant_id, is_active=True, scope_type=scope_type)
    if scope_type in ("company",):
        q = q.filter(Partner.scope_id.is_(None))
    elif scope_id is not None:
        q = q.filter_by(scope_id=scope_id)
    if exclude_id is not None:
        q = q.filter(Partner.id != exclude_id)
    total = sum(Decimal(str(p.share_percentage or 0)) for p in q.all())
    return total + Decimal(str(new_share or 0)) > Decimal("100")


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
            financials, error = _parse_partner_financials(request.form)
            if error:
                flash(gettext(f"❌ خطأ: {error}"), "danger")
                return render_template("partners/create.html", branches=branches, warehouses=warehouses)
            scope_type = request.form.get("scope_type", "company")
            scope_id = request.form.get("scope_id", type=int) or None
            if scope_type == "company":
                scope_id = None
            if _scope_share_total_exceeds(tid, scope_type, scope_id, financials["share_percentage"]):
                flash(gettext("❌ مجموع نسب أرباح الشركاء في هذا النطاق يتجاوز 100%."), "danger")
                return render_template("partners/create.html", branches=branches, warehouses=warehouses)

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
                investment_amount=financials["investment_amount"],
                share_percentage=financials["share_percentage"],
                fixed_monthly_amount=financials["fixed_monthly_amount"],
                expense_share_percentage=financials["expense_share_percentage"],
                loss_share_percentage=financials["loss_share_percentage"],
                min_profit_threshold=financials["min_profit_threshold"],
                notes=request.form.get("notes", "").strip() or None,
                is_active=True,
            )
            with atomic_transaction("partner_create"):
                db.session.add(partner)
            flash(gettext("✅ تم إضافة الشريك بنجاح."), "success")
            return redirect(url_for("partners.index"))
        except Exception as e:
            flash(gettext(f"❌ خطأ: {e}"), "danger")

    return render_template("partners/create.html", branches=branches, warehouses=warehouses)


# ── Detail & Edit ─────────────────────────────────────────────


@partners_bp.route("/<int:id>")
@login_required
@permission_required("view_reports")
def view(**kwargs):
    record_id = kwargs.pop("id")
    partner = tenant_query(Partner).filter_by(id=record_id).first_or_404()
    tid = _tenant_id()

    latest_dists, latest_txs = PartnerService.get_partner_activity(record_id, tid)

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
    tid = _tenant_id()
    from models import Branch, Warehouse

    branches = tenant_query(Branch).all()
    warehouses = tenant_query(Warehouse).all()

    if request.method == "POST":
        try:
            financials, error = _parse_partner_financials(request.form, existing=partner)
            if error:
                flash(gettext(f"❌ خطأ: {error}"), "danger")
                return render_template("partners/edit.html", partner=partner, branches=branches, warehouses=warehouses)
            scope_type = request.form.get("scope_type", partner.scope_type)
            scope_id = request.form.get("scope_id", type=int) or None
            if scope_type == "company":
                scope_id = None
            if _scope_share_total_exceeds(
                tid, scope_type, scope_id, financials["share_percentage"], exclude_id=record_id
            ):
                flash(gettext("❌ مجموع نسب أرباح الشركاء في هذا النطاق يتجاوز 100%."), "danger")
                return render_template("partners/edit.html", partner=partner, branches=branches, warehouses=warehouses)

            partner.name = request.form.get("name", partner.name).strip()
            partner.name_en = request.form.get("name_en", partner.name_en).strip() or None
            partner.code = request.form.get("code", partner.code).strip() or None
            partner.scope_type = scope_type
            partner.scope_id = scope_id
            partner.partner_type = request.form.get("partner_type", partner.partner_type)
            partner.phone = request.form.get("phone", "").strip() or None
            partner.email = request.form.get("email", "").strip() or None
            partner.address = request.form.get("address", "").strip() or None
            partner.id_number = request.form.get("id_number", "").strip() or None
            partner.investment_amount = financials["investment_amount"]
            partner.share_percentage = financials["share_percentage"]
            partner.fixed_monthly_amount = financials["fixed_monthly_amount"]
            partner.expense_share_percentage = financials["expense_share_percentage"]
            partner.loss_share_percentage = financials["loss_share_percentage"]
            partner.min_profit_threshold = financials["min_profit_threshold"]
            partner.is_active = request.form.get("is_active") == "on"
            partner.notes = request.form.get("notes", "").strip() or None
            partner.updated_at = datetime.now(UTC)

            with atomic_transaction("partner_edit"):
                db.session.flush()
            flash(gettext("✅ تم تحديث بيانات الشريك."), "success")
            return redirect(url_for("partners.view", id=record_id))
        except Exception as e:
            flash(gettext(f"❌ خطأ: {e}"), "danger")

    return render_template("partners/edit.html", partner=partner, branches=branches, warehouses=warehouses)


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
    status = request.args.get("status", "")
    dists = PartnerService.list_distributions(tid, status=status)
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

    today = datetime.now(UTC).date()
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
            ok = PartnerService.approve_distribution(dist_id, current_user.id, tenant_id=_tenant_id())
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
        amount = Decimal(str(request.form.get("amount", "0") or "0"))
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
    return redirect(url_for("partners.view", id=record_id))


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

    pnl = PartnerService.calculate_scope_profit(int(tid or 0), start, end, scope, scope_id)
    return success_response(data=pnl)


# ── API: dual-role (company partner + product partner) ────────


@partners_bp.route("/<int:id>/unified")
@login_required
@permission_required("view_reports")
def api_unified(**kwargs):
    """Combined one-person statement: company distributions + product commissions."""
    record_id = kwargs.pop("id")
    partner = tenant_query(Partner).filter_by(id=record_id).first_or_404()
    tid = _tenant_id()
    unified = PartnerService.get_unified_statement(partner.id, tid)
    payload = {
        "partner_id": unified["partner"].id,
        "partner_name": unified["partner"].name,
        "current_balance": unified["current_balance"],
        "company_total": unified["company_total"],
        "product_commissions_total": unified["product_commissions_total"],
        "combined_total": unified["combined_total"],
        "linked_customers": unified["linked_customers"],
        "distributions": [
            {
                "id": d.id,
                "period_start": str(d.period_start),
                "period_end": str(d.period_end),
                "scope_type": d.scope_type,
                "net_profit": float(d.net_profit or 0),
                "share_amount": float(d.share_amount or 0),
                "net_due": float(d.net_due or 0),
                "status": d.status,
            }
            for d in unified["distributions"]
        ],
    }
    return success_response(data=payload)


@partners_bp.route("/<int:id>/link-customer", methods=["POST"])
@login_required
@permission_required("manage_users")
def link_customer(**kwargs):
    """Link a product-level partner (Customer) to this company-level Partner."""
    record_id = kwargs.pop("id")
    partner = tenant_query(Partner).filter_by(id=record_id).first_or_404()
    customer_id = request.form.get("customer_id", type=int) or request.get_json(silent=True, force=False)
    if isinstance(customer_id, dict):
        customer_id = customer_id.get("customer_id")
    if not customer_id:
        flash(gettext("❌ حدّد العميل الشريك أولاً."), "danger")
        return redirect(url_for("partners.view", id=record_id))
    try:
        with atomic_transaction("partner_link_customer"):
            ok = PartnerService.link_product_partner(partner.id, int(customer_id), tenant_id=_tenant_id())
        if ok:
            flash(gettext("✅ تم ربط الشريك المنتجي بشريك الشركة."), "success")
        else:
            flash(gettext("❌ تعذر الربط (النطاق أو النوع غير صالح)."), "danger")
    except Exception as e:
        flash(gettext(f"❌ خطأ: {e}"), "danger")
    return redirect(url_for("partners.view", id=record_id))


@partners_bp.route("/<int:id>/unlink-customer", methods=["POST"])
@login_required
@permission_required("manage_users")
def unlink_customer(**kwargs):
    """Remove a product-level partner link (documents stay untouched)."""
    record_id = kwargs.pop("id")
    tenant_query(Partner).filter_by(id=record_id).first_or_404()
    customer_id = request.form.get("customer_id", type=int)
    if not customer_id:
        flash(gettext("❌ حدّد العميل الشريك أولاً."), "danger")
        return redirect(url_for("partners.view", id=record_id))
    try:
        with atomic_transaction("partner_unlink_customer"):
            ok = PartnerService.unlink_product_partner(int(customer_id), tenant_id=_tenant_id())
        if ok:
            flash(gettext("✅ تم فك الربط."), "success")
        else:
            flash(gettext("❌ تعذر فك الربط."), "danger")
    except Exception as e:
        flash(gettext(f"❌ خطأ: {e}"), "danger")
    return redirect(url_for("partners.view", id=record_id))
