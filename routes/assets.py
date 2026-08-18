from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_babel import gettext
from flask_login import login_required

from services.asset_service import AssetService
from utils.decorators import permission_required
from utils.tenanting import tenant_get_or_404

assets_bp = Blueprint("assets", __name__, url_prefix="/assets")


@assets_bp.route("/")
@login_required
@permission_required("assets:view")
def index():
    filters = {k: v for k, v in request.args.items() if v}
    assets = AssetService.list_assets(None, filters)
    summary = AssetService.get_asset_summary(None)
    return render_template("assets/index.html", assets=assets, summary=summary)


@assets_bp.route("/create", methods=["GET", "POST"])
@login_required
@permission_required("assets:manage")
def create():
    if request.method == "POST":
        try:
            asset = AssetService.create_asset(request.form, None)
            flash(gettext("تم إنشاء الأصل"), "success")
            return redirect(url_for("assets.detail", asset_id=asset.id))
        except (ValueError, KeyError) as e:
            flash(str(e), "danger")
    return render_template("assets/create.html")


@assets_bp.route("/<int:asset_id>")
@login_required
@permission_required("assets:view")
def detail(asset_id):
    from models import FixedAsset

    asset = tenant_get_or_404(FixedAsset, asset_id)
    schedule = AssetService.get_depreciation_schedule(asset_id, None)
    return render_template("assets/detail.html", asset=asset, schedule=schedule)


@assets_bp.route("/<int:asset_id>/edit", methods=["GET", "POST"])
@login_required
@permission_required("assets:manage")
def edit(asset_id):
    from models import FixedAsset

    asset = tenant_get_or_404(FixedAsset, asset_id)
    if request.method == "POST":
        try:
            AssetService.update_asset(asset, request.form)
            flash(gettext("تم تحديث الأصل"), "success")
            return redirect(url_for("assets.detail", asset_id=asset.id))
        except (ValueError, KeyError) as e:
            flash(str(e), "danger")
    return render_template("assets/create.html", asset=asset)


@assets_bp.route("/<int:asset_id>/depreciate", methods=["POST"])
@login_required
@permission_required("assets:depreciate")
def depreciate(asset_id):
    from models import FixedAsset

    asset = tenant_get_or_404(FixedAsset, asset_id)
    try:
        AssetService.post_manual_depreciation(asset)
        flash(gettext("تم ترحيل الاستهلاك"), "success")
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("assets.detail", asset_id=asset.id))


@assets_bp.route("/<int:asset_id>/dispose", methods=["GET", "POST"])
@login_required
@permission_required("assets:manage")
def dispose(asset_id):
    from models import FixedAsset

    asset = tenant_get_or_404(FixedAsset, asset_id)
    if request.method == "POST":
        try:
            from datetime import date as date_type

            disposal_date_str = request.form.get("disposal_date", "")
            disposal_date = date_type.fromisoformat(disposal_date_str) if disposal_date_str else date_type.today()
            disposal_price = request.form.get("disposal_price", "0")
            notes = request.form.get("notes")
            AssetService.dispose_asset(asset, disposal_date, float(disposal_price), notes=notes)
            flash(gettext("تم التخلص من الأصل"), "success")
            return redirect(url_for("assets.detail", asset_id=asset.id))
        except (ValueError, KeyError) as e:
            flash(str(e), "danger")
    return render_template("assets/disposal.html", asset=asset)


@assets_bp.route("/depreciation-schedule")
@login_required
@permission_required("assets:view")
def depreciation_schedule():
    assets = AssetService.list_assets(None, {"status": "active"})
    return render_template("assets/depreciation.html", assets=assets)
