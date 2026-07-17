from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from services.email_marketing_service import EmailMarketingService
from utils.decorators import permission_required

email_marketing_bp = Blueprint("email_marketing", __name__, url_prefix="/marketing")


@email_marketing_bp.route("/")
@login_required
@permission_required("marketing.manage")
def campaigns():
    campaign_list = EmailMarketingService.list_campaigns(current_user)
    return render_template("marketing/campaign_list.html", campaigns=campaign_list)


@email_marketing_bp.route("/campaigns/create", methods=["GET", "POST"])
@login_required
@permission_required("marketing.manage")
def create_campaign():
    if request.method == "POST":
        try:
            EmailMarketingService.create_campaign(request.form, current_user)
            flash("تم إنشاء الحملة", "success")
            return redirect(url_for("email_marketing.campaigns"))
        except Exception as e:
            flash(f"حدث خطأ: {e}", "danger")
    list_data = EmailMarketingService.list_lists(current_user)
    template_data = EmailMarketingService.list_templates(current_user)
    return render_template(
        "marketing/campaign_form.html", lists=list_data, templates=template_data
    )


@email_marketing_bp.route("/campaigns/<int:campaign_id>")
@login_required
@permission_required("marketing.manage")
def campaign_detail(campaign_id):
    try:
        stats = EmailMarketingService.get_campaign_stats(campaign_id, current_user)
    except ValueError as e:
        flash(str(e), "danger")
        return redirect(url_for("email_marketing.campaigns"))
    return render_template("marketing/stats.html", stats=stats)


@email_marketing_bp.route("/campaigns/<int:campaign_id>/send", methods=["POST"])
@login_required
@permission_required("marketing.manage")
def send_campaign(campaign_id):
    try:
        EmailMarketingService.send_campaign(campaign_id, current_user)
        flash("تم إرسال الحملة", "success")
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("email_marketing.campaign_detail", campaign_id=campaign_id))


@email_marketing_bp.route("/lists")
@login_required
@permission_required("marketing.manage")
def lists():
    list_data = EmailMarketingService.list_lists(current_user)
    return render_template("marketing/campaign_form.html", lists=list_data, tab="lists")


@email_marketing_bp.route("/lists/create", methods=["POST"])
@login_required
@permission_required("marketing.manage")
def create_list():
    try:
        EmailMarketingService.create_list(request.form, current_user)
        flash("تم إنشاء القائمة", "success")
    except (ValueError, KeyError) as e:
        flash(str(e), "danger")
    return redirect(url_for("email_marketing.lists"))


@email_marketing_bp.route("/templates")
@login_required
@permission_required("marketing.manage")
def templates():
    template_data = EmailMarketingService.list_templates(current_user)
    return render_template(
        "marketing/campaign_form.html", templates=template_data, tab="templates"
    )


@email_marketing_bp.route("/templates/create", methods=["POST"])
@login_required
@permission_required("marketing.manage")
def create_template():
    try:
        EmailMarketingService.create_template(request.form, current_user)
        flash("تم إنشاء القالب", "success")
    except (ValueError, KeyError) as e:
        flash(str(e), "danger")
    return redirect(url_for("email_marketing.templates"))
