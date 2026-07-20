from flask_babel import gettext
from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    request,
    current_app,
)
from flask_login import login_required, current_user
from extensions import db, limiter
from models import Purchase, PurchaseReturn, PurchaseReturnLine
from services.currency_service import CurrencyService
from services.purchase_service import PurchaseService
from utils.decorators import permission_required
from utils.branching import (
    ensure_warehouse_access,
    get_accessible_warehouses,
    should_show_all_branch_columns,
    get_active_branch_id,
)
from services.logging_core import LoggingCore
from utils.currency_utils import resolve_default_currency, get_system_default_currency
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from utils.tenanting import tenant_query, tenant_get_or_404, get_active_tenant_id
from utils.db_safety import atomic_transaction
from utils.gl_reference_types import GLRef

purchases_bp = Blueprint("purchases", __name__, url_prefix="/purchases")


@purchases_bp.route("/")
@login_required
@permission_required("manage_purchases")
def index():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    search = request.args.get("search", "", type=str)

    query = tenant_query(Purchase)
    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            db.or_(
                Purchase.purchase_number.ilike(search_filter),
                Purchase.supplier_name.ilike(search_filter),
            )
        )
    query = query.filter_by(status="confirmed")
    from utils.decorators import branch_scope_id

    branch_id = branch_scope_id()
    if branch_id is not None:
        query = query.filter(Purchase.branch_id == branch_id)
    pagination = query.order_by(Purchase.purchase_date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return render_template(
        "purchases/index.html",
        purchases=pagination.items,
        pagination=pagination,
        show_branch_columns=should_show_all_branch_columns(current_user),
    )


@purchases_bp.route("/create", methods=["GET", "POST"])
@login_required
@permission_required("manage_purchases")
@limiter.limit("10 per minute", methods=["POST"])
def create():
    warehouse_id_val = (
        request.form.get("warehouse_id", type=int) if request.method == "POST" else None
    )

    if request.method == "POST":
        try:
            current_app.logger.info("POST request received for purchase creation")

            warehouse_id_val = request.form.get("warehouse_id", type=int)
            if not warehouse_id_val:
                flash(
                    gettext("⚠️ يجب اختيار المستودع الذي ستُضاف إليه البضاعة."), "danger"
                )
                return redirect(url_for("purchases.create"))
            ensure_warehouse_access(warehouse_id_val, user=current_user)

            # Parse Lines
            lines_data = []
            line_count = int(request.form.get("line_count", 0))

            for i in range(line_count):
                product_id = request.form.get(f"lines[{i}][product_id]", type=int)
                quantity = request.form.get(f"lines[{i}][quantity]", type=float)
                unit_cost = request.form.get(f"lines[{i}][unit_cost]", type=float)
                discount_percent = request.form.get(
                    f"lines[{i}][discount_percent]", type=float, default=0
                )
                serials_raw = request.form.get(f"lines[{i}][serials]", "")
                serials = (
                    [s.strip() for s in serials_raw.split("\n") if s.strip()]
                    if serials_raw
                    else []
                )
                if product_id and quantity and quantity > 0:
                    lines_data.append(
                        {
                            "product_id": product_id,
                            "quantity": quantity,
                            "unit_cost": unit_cost,
                            "discount_percent": discount_percent,
                            "serials": serials,
                        }
                    )

            # Create Purchase via Service
            try:
                from models import Tenant

                default_currency = resolve_default_currency()
            except Exception:
                default_currency = get_system_default_currency()

            with atomic_transaction("purchase_creation"):
                purchase = PurchaseService.create_purchase(
                    user=current_user,
                    supplier_data={
                        "supplier_id": request.form.get("supplier_id", type=int),
                        "supplier_name": request.form.get("supplier_name", ""),
                        "phone": request.form.get("supplier_phone", ""),
                        "email": request.form.get("supplier_email", ""),
                    },
                    lines_data=lines_data,
                    warehouse_id=warehouse_id_val,
                    currency=request.form.get("currency") or default_currency,
                    user_exchange_rate=request.form.get("exchange_rate", type=float),
                    discount_amount=request.form.get(
                        "discount_amount", type=float, default=0
                    ),
                    tax_rate=request.form.get("tax_rate", type=float, default=0),
                    notes=request.form.get("notes"),
                    freight=request.form.get("freight", type=float, default=0),
                    insurance=request.form.get("insurance", type=float, default=0),
                    customs_duty=request.form.get(
                        "customs_duty", type=float, default=0
                    ),
                    other_landed_cost=request.form.get(
                        "other_landed_cost", type=float, default=0
                    ),
                )

            flash(gettext("✅ تم إنشاء فاتورة الشراء بنجاح!"), "success")
            return redirect(url_for("purchases.view", id=purchase.id))

        except ValueError as e:
            flash(f"⚠️ {str(e)}", "warning")
        except Exception as e:
            current_app.logger.error(f"Error in purchase creation: {str(e)}")
            current_app.logger.error(f"Error type: {type(e).__name__}")
            import traceback

            current_app.logger.error(f"Traceback: {traceback.format_exc()}")
            flash(
                gettext(
                    f"❌ حدث خطأ: {str(e)}\n💡 تحقق من البيانات المدخلة وحاول مرة أخرى."
                ),
                "danger",
            )

    try:
        from models import Tenant

        tenant = Tenant.get_current()
        base_currency = resolve_default_currency(tenant)
    except Exception:
        base_currency = get_system_default_currency()
    exchange_rates = CurrencyService.get_all_rates(base_currency)
    warehouses = get_accessible_warehouses(current_user)

    from utils.tax_settings import get_prices_include_vat

    prices_include_vat = get_prices_include_vat(
        tenant_id=get_active_tenant_id(current_user), branch_id=get_active_branch_id()
    )
    tenant_currency_symbol = base_currency

    return render_template(
        "purchases/create.html",
        exchange_rates=exchange_rates,
        warehouses=warehouses,
        prices_include_vat=prices_include_vat,
        tenant_currency_symbol=tenant_currency_symbol,
    )


@purchases_bp.route("/<int:id>")
@login_required
@permission_required("manage_purchases")
def view(**kwargs):
    record_id = kwargs.pop("id")
    purchase = tenant_get_or_404(Purchase, record_id)
    from utils.decorators import branch_scope_id

    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None and purchase.branch_id != scoped_branch_id:
        return render_template("errors/403.html"), 403
    return render_template("purchases/view.html", purchase=purchase)


@purchases_bp.route("/<int:id>/print")
@login_required
@permission_required("manage_purchases")
def print_purchase(**kwargs):
    record_id = kwargs.pop("id")
    purchase = tenant_get_or_404(Purchase, record_id)
    from utils.decorators import branch_scope_id

    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None and purchase.branch_id != scoped_branch_id:
        return render_template("errors/403.html"), 403
    from models.invoice_settings import InvoiceSettings
    from utils.tenant_branding import get_print_header_context
    from utils.qr_generator import generate_qr_data_url

    tid = purchase.tenant_id
    tenant, settings, company = InvoiceSettings.company_print_context(tid)
    print_branding = get_print_header_context(tid)
    qr_data_url = ""
    if settings and settings.enable_qr_code:
        from services.document_verification_service import DocumentVerificationService

        ver = DocumentVerificationService.get_or_create_verification(
            "purchase", purchase.id, tid
        )
        if ver:
            ver_url = url_for(
                "public.verify_document", token=ver.public_token, _external=True
            )
            qr_data_url = generate_qr_data_url(ver_url)
    return render_template(
        "purchases/print.html",
        purchase=purchase,
        company=company,
        settings=settings,
        print_branding=print_branding,
        print_tenant_id=tid,
        qr_data_url=qr_data_url,
    )


@purchases_bp.route("/<int:id>/edit", methods=["GET", "POST"])
@login_required
@permission_required("manage_purchases")
def edit(**kwargs):
    """تعديل فاتورة شراء - الملاحظات والخصم فقط"""
    record_id = kwargs.pop("id")
    purchase = tenant_get_or_404(Purchase, record_id)
    from utils.decorators import branch_scope_id

    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None and purchase.branch_id != scoped_branch_id:
        return render_template("errors/403.html"), 403

    if purchase.get_paid_amount() > 0:
        flash(
            gettext(
                "⚠️ لا يمكن تعديل فاتورة شراء تم الدفع عليها.\n💡 للحفاظ على السجلات المحاسبية."
            ),
            "danger",
        )
        return redirect(url_for("purchases.view", id=record_id))

    if request.method == "POST":
        try:
            purchase.notes = request.form.get("notes", "")

            with atomic_transaction("purchase_edit"):
                db.session.flush()
            LoggingCore.log_audit("update", "purchases", record_id)

            flash(gettext("✅ تم تحديث فاتورة الشراء بنجاح!"), "success")
            return redirect(url_for("purchases.view", id=record_id))

        except Exception as e:
            flash(gettext(f"❌ حدث خطأ: {str(e)}\n💡 تحقق من البيانات."), "danger")

    return render_template("purchases/edit.html", purchase=purchase)


@purchases_bp.route("/<int:id>/delete", methods=["POST"])
@login_required
@permission_required("manage_purchases")
def delete(**kwargs):
    """حذف (أرشفة) فاتورة شراء"""
    from services.archive_service import ArchiveService
    from models import Cheque, PurchaseLine

    record_id = kwargs.pop("id")
    purchase = tenant_get_or_404(Purchase, record_id)
    from utils.decorators import branch_scope_id

    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None and purchase.branch_id != scoped_branch_id:
        return render_template("errors/403.html"), 403

    has_links = False

    if purchase.get_paid_amount() > 0:
        has_links = True

    linked_cheques = Cheque.query.filter_by(
        purchase_id=purchase.id, tenant_id=purchase.tenant_id
    ).count()
    if linked_cheques > 0:
        has_links = True

    from models.warehouse import StockMovement

    has_stock = (
        StockMovement.query.filter_by(
            reference_type=GLRef.PURCHASE,
            reference_id=purchase.id,
        ).count()
        > 0
    )

    try:
        if has_links:
            archive_service = ArchiveService()
            archive_service.archive_record(
                "purchases",
                purchase,
                reason=gettext("تم أرشفة الفاتورة لوجود مدفوعات أو شيكات"),
            )

            LoggingCore.log_audit("archive", "purchases", record_id)
            with atomic_transaction("purchase_archive"):
                db.session.flush()
            flash(
                gettext(
                    f'✅ تم أرشفة فاتورة الشراء "{purchase.purchase_number}" (لوجود ارتباطات مالية)'
                ),
                "warning",
            )
        elif has_stock:
            flash(
                gettext(
                    f'⚠️ لا يمكن حذف فاتورة الشراء "{purchase.purchase_number}" لأنها أثرت على المخزون. يمكنك أرشفتها بدلاً من ذلك.'
                ),
                "warning",
            )
            archive_service = ArchiveService()
            archive_service.archive_record(
                "purchases",
                purchase,
                reason=gettext("تم أرشفة الفاتورة لوجود حركة مخزون"),
            )
            LoggingCore.log_audit("archive", "purchases", record_id)
            with atomic_transaction("purchase_archive_fallback"):
                db.session.flush()
        else:
            with atomic_transaction("purchase_delete"):
                from services.gl_service import GLService

                GLService.reverse_entry(
                    reference_type=GLRef.PURCHASE,
                    reference_id=purchase.id,
                    description=f"Reverse Purchase {purchase.purchase_number} (Deleted)",
                    tenant_id=purchase.tenant_id,
                )

                if purchase.supplier_id:
                    from models import Supplier

                    supplier = Supplier.query.filter_by(
                        id=purchase.supplier_id, tenant_id=purchase.tenant_id
                    ).first()
                    if supplier:
                        from decimal import Decimal

                        supplier.apply_payment(-Decimal(str(purchase.amount_aed or 0)))

                PurchaseLine.query.filter_by(
                    purchase_id=purchase.id, tenant_id=purchase.tenant_id
                ).delete()
                db.session.delete(purchase)
                LoggingCore.log_audit("delete", "purchases", record_id)
            flash(
                gettext(f'✅ تم حذف فاتورة الشراء "{purchase.purchase_number}" نهائياً'),
                "success",
            )

        return redirect(url_for("purchases.index"))

    except Exception as e:
        flash(gettext(f"❌ حدث خطأ: {str(e)}"), "danger")
        return redirect(url_for("purchases.view", id=record_id))


@purchases_bp.route("/<int:id>/cancel", methods=["POST"])
@login_required
@permission_required("manage_purchases")
def cancel(**kwargs):
    """إلغاء فاتورة شراء مع عكس القيد المحاسبي والمخزون ورصيد المورد"""
    record_id = kwargs.pop("id")
    purchase = tenant_get_or_404(Purchase, record_id)
    from utils.decorators import branch_scope_id

    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None and purchase.branch_id != scoped_branch_id:
        return render_template("errors/403.html"), 403

    try:
        with atomic_transaction("purchase_cancel"):
            PurchaseService.cancel_purchase(purchase)
        LoggingCore.log_audit("cancel", "purchases", purchase.id)
        flash(gettext("✅ تم إلغاء فاتورة الشراء بنجاح!"), "success")
    except ValueError as e:
        flash(f"❌ {str(e)}", "danger")
    except Exception as e:
        flash(gettext(f"❌ حدث خطأ: {str(e)}"), "danger")

    return redirect(url_for("purchases.view", id=record_id))


@purchases_bp.route("/<int:id>/return", methods=["GET", "POST"])
@login_required
@permission_required("manage_purchases")
def purchase_return(**kwargs):
    """إنشاء مرتجع مشتريات"""
    record_id = kwargs.pop("id")
    purchase = tenant_get_or_404(Purchase, record_id)
    from utils.decorators import branch_scope_id

    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None and purchase.branch_id != scoped_branch_id:
        return render_template("errors/403.html"), 403

    if purchase.status in ("draft", "cancelled"):
        flash(
            gettext("❌ لا يمكن عمل مرتجع لفاتورة شراء في حالة مسودة أو ملغاة"),
            "danger",
        )
        return redirect(url_for("purchases.view", id=record_id))

    if request.method == "POST":
        lines_data = (
            request.json.get("lines", [])
            if request.is_json
            else request.form.getlist("lines")
        )
        reason = request.form.get("reason", "")
        notes = request.form.get("notes", "")

        if not lines_data:
            flash(gettext("❌ يجب تحديد منتج واحد على الأقل للإرجاع"), "danger")
            return redirect(url_for("purchases.purchase_return", id=record_id))

        try:
            with atomic_transaction("purchase_return"):
                result = PurchaseService.create_purchase_return(
                    purchase,
                    current_user,
                    lines_data,
                    reason=reason,
                    notes=notes,
                )
            flash(
                gettext(
                    f"✅ تم إنشاء مرتجع المشتريات رقم {result.return_number} بنجاح!"
                ),
                "success",
            )
            return redirect(url_for("purchases.view", id=record_id))
        except ValueError as e:
            flash(f"❌ {str(e)}", "danger")
        except Exception as e:
            flash(gettext(f"❌ حدث خطأ: {str(e)}"), "danger")
            current_app.logger.exception("Purchase return error")

    tid = get_active_tenant_id(current_user)
    returns_query = PurchaseReturn.query.filter(
        PurchaseReturn.purchase_id == purchase.id,
    )
    if tid is not None:
        returns_query = returns_query.filter(PurchaseReturn.tenant_id == tid)
    returns = returns_query.order_by(PurchaseReturn.created_at.desc()).all()
    return_lines = (
        PurchaseReturnLine.query.filter(
            PurchaseReturnLine.return_id.in_([r.id for r in returns])
        ).all()
        if returns
        else []
    )
    return render_template(
        "purchases/return.html",
        purchase=purchase,
        returns=returns,
        return_lines=return_lines,
    )


@purchases_bp.route("/api/calculate-totals", methods=["POST"])
@login_required
@permission_required("manage_purchases")
def api_calculate_purchase_totals():
    """API لحساب إجماليات فاتورة المشتريات - Backend Calculation"""
    from flask import jsonify

    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({"success": False, "error": "No data provided"}), 400

        lines = data.get("lines", [])
        tax_rate = Decimal(str(data.get("tax_rate", 0)))
        from utils.tax_settings import normalize_tax_rate

        tax_rate = normalize_tax_rate(tax_rate)

        subtotal = Decimal("0")
        for line in lines:
            try:
                qty = Decimal(str(line.get("quantity", 0)))
                cost = Decimal(str(line.get("unit_cost", 0)))
                discount_percent = Decimal(str(line.get("discount_percent", 0)))

                if qty > 0 and cost > 0:
                    line_subtotal = qty * cost
                    line_discount = line_subtotal * (discount_percent / Decimal("100"))
                    line_total = line_subtotal - line_discount
                    subtotal += line_total
            except (ValueError, TypeError, KeyError, InvalidOperation):
                continue

        freight = Decimal(str(data.get("freight", 0) or 0))
        insurance = Decimal(str(data.get("insurance", 0) or 0))
        customs_duty = Decimal(str(data.get("customs_duty", 0) or 0))
        other_landed_cost = Decimal(str(data.get("other_landed_cost", 0) or 0))
        landed_total = freight + insurance + customs_duty + other_landed_cost

        prices_include_vat = bool(data.get("prices_include_vat", False))
        if prices_include_vat:
            if tax_rate > 0:
                taxable_amount = (
                    subtotal / (Decimal("1") + (tax_rate / Decimal("100")))
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                tax_amount = subtotal - taxable_amount
            else:
                taxable_amount = subtotal
                tax_amount = Decimal("0")
            total = subtotal + landed_total
        else:
            tax_amount = subtotal * (tax_rate / Decimal("100"))
            total = subtotal + tax_amount + landed_total

        positive_lines = 0
        for line in lines:
            try:
                if Decimal(str(line.get("quantity", 0))) > 0:
                    positive_lines += 1
            except (ValueError, TypeError, InvalidOperation):
                continue

        return (
            jsonify(
                {
                    "success": True,
                    "subtotal": float(subtotal),
                    "tax_rate": float(tax_rate),
                    "tax_amount": float(tax_amount),
                    "landed_cost": float(landed_total),
                    "total": float(total),
                    "prices_include_vat": prices_include_vat,
                    "line_count": positive_lines,
                }
            ),
            200,
        )

    except Exception:
        current_app.logger.exception("calculate_purchase_totals failed")
        return jsonify(
            {"success": False, "error": gettext("تعذر حساب الإجماليات حالياً")}
        ), 500
