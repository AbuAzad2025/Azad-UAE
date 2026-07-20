"""Email marketing lists, templates, campaigns, and delivery."""

from __future__ import annotations

from datetime import datetime, timezone

from extensions import db
from models import (
    CampaignLog,
    EmailCampaign,
    EmailList,
    EmailSubscriber,
    EmailTemplate,
)
from utils.auth_helpers import is_global_owner_user
from utils.tenanting import get_active_tenant_id


class EmailMarketingService:
    @staticmethod
    def _tid(user):
        return get_active_tenant_id(user)

    @staticmethod
    def create_list(data, user):
        tid = EmailMarketingService._tid(user)
        if not tid:
            raise ValueError("لا توجد شركة نشطة.")
        if not data.get("name"):
            raise ValueError("اسم القائمة مطلوب.")
        lst = EmailList(
            tenant_id=int(tid),
            name=data["name"],
            description=data.get("description"),
        )
        db.session.add(lst)
        try:
            db.session.flush()
        except Exception:
            raise
        return lst

    @staticmethod
    def list_lists(user):
        tid = EmailMarketingService._tid(user)
        if not tid:
            return []
        return (
            EmailList.query.filter(
                EmailList.tenant_id == tid,
                EmailList.is_active,
            )
            .order_by(EmailList.name)
            .all()
        )

    @staticmethod
    def subscribe(list_id, email, name=None, customer_id=None, user=None):
        lst = db.session.get(EmailList, int(list_id))
        if not lst:
            raise ValueError("القائمة غير موجودة.")
        tid = lst.tenant_id
        if user and not is_global_owner_user(user):
            user_tid = EmailMarketingService._tid(user)
            if user_tid is not None and int(tid) != int(user_tid):
                raise ValueError("القائمة لا تنتمي إلى شركتك.")
        existing = EmailSubscriber.query.filter_by(list_id=lst.id, email=email).first()
        if existing:
            if existing.status == "unsubscribed":
                existing.status = "subscribed"
                existing.unsubscribed_at = None
                try:
                    db.session.flush()
                except Exception:
                    raise
            return existing
        sub = EmailSubscriber(
            tenant_id=tid,
            list_id=lst.id,
            email=email,
            name=name,
            customer_id=int(customer_id) if customer_id else None,
            status="subscribed",
        )
        db.session.add(sub)
        try:
            db.session.flush()
        except Exception:
            raise
        return sub

    @staticmethod
    def unsubscribe(email, list_id=None, tenant_id=None):
        query = EmailSubscriber.query.filter_by(email=email)
        if list_id:
            query = query.filter_by(list_id=int(list_id))
        if tenant_id:
            from models.email_marketing import EmailList

            query = query.join(
                EmailList,
                EmailSubscriber.list_id == EmailList.id,
            ).filter(EmailList.tenant_id == int(tenant_id))
        subs = query.all()
        now = datetime.now(timezone.utc)
        for sub in subs:
            sub.status = "unsubscribed"
            sub.unsubscribed_at = now
        try:
            db.session.flush()
        except Exception:
            raise
        return len(subs)

    @staticmethod
    def create_template(data, user):
        tid = EmailMarketingService._tid(user)
        if not tid:
            raise ValueError("لا توجد شركة نشطة.")
        if not data.get("name") or not data.get("subject") or not data.get("body_html"):
            raise ValueError("اسم القالب والموضوع والمحتوى مطلوبون.")
        tpl = EmailTemplate(
            tenant_id=int(tid),
            name=data["name"],
            subject=data["subject"],
            body_html=data["body_html"],
            from_email=data.get("from_email"),
        )
        db.session.add(tpl)
        try:
            db.session.flush()
        except Exception:
            raise
        return tpl

    @staticmethod
    def list_templates(user):
        tid = EmailMarketingService._tid(user)
        if not tid:
            return []
        return (
            EmailTemplate.query.filter(
                EmailTemplate.tenant_id == tid,
                EmailTemplate.is_active,
            )
            .order_by(EmailTemplate.name)
            .all()
        )

    @staticmethod
    def create_campaign(data, user):
        tid = EmailMarketingService._tid(user)
        if not tid:
            raise ValueError("لا توجد شركة نشطة.")
        if not data.get("name"):
            raise ValueError("اسم الحملة مطلوب.")
        campaign = EmailCampaign(
            tenant_id=int(tid),
            name=data["name"],
            list_id=int(data["list_id"]) if data.get("list_id") else None,
            template_id=int(data["template_id"]) if data.get("template_id") else None,
            scheduled_date=(datetime.fromisoformat(data["scheduled_date"]) if data.get("scheduled_date") else None),
            status="draft",
        )
        db.session.add(campaign)
        try:
            db.session.flush()
        except Exception:
            raise
        return campaign

    @staticmethod
    def send_campaign(campaign_id, user):
        campaign = db.session.get(EmailCampaign, int(campaign_id))
        if not campaign:
            raise ValueError("الحملة غير موجودة.")
        tid = EmailMarketingService._tid(user)
        if tid is not None and int(campaign.tenant_id) != int(tid):
            raise ValueError("الحملة لا تنتمي إلى شركتك.")
        if campaign.status != "draft":
            raise ValueError("يمكن إرسال الحملات في حالة المسودة فقط.")
        if not campaign.list_id:
            raise ValueError("الحملة لا تحتوي على قائمة بريدية.")
        if not campaign.template_id:
            raise ValueError("الحملة لا تحتوي على قالب بريد إلكتروني.")
        subscribers = EmailSubscriber.query.filter_by(
            list_id=campaign.list_id,
            status="subscribed",
        ).all()
        if not subscribers:
            raise ValueError("لا يوجد مشتركون نشطون في القائمة.")
        from flask import current_app

        mail = current_app.extensions.get("mail")
        if not mail:
            raise ValueError("خدمة البريد الإلكتروني غير مهيأة.")
        from flask_mail import Message

        template = campaign.template
        sent = 0
        for sub in subscribers:
            try:
                msg = Message(
                    subject=template.subject,
                    recipients=[sub.email],
                    html=template.body_html,
                    sender=template.from_email or current_app.config.get("MAIL_DEFAULT_SENDER"),
                )
                mail.send(msg)
                log = CampaignLog(
                    tenant_id=campaign.tenant_id,
                    campaign_id=campaign.id,
                    subscriber_id=sub.id,
                    status="sent",
                    sent_at=datetime.now(timezone.utc),
                )
                db.session.add(log)
                sent += 1
            except Exception as e:
                log = CampaignLog(
                    tenant_id=campaign.tenant_id,
                    campaign_id=campaign.id,
                    subscriber_id=sub.id,
                    status="bounced",
                    error_message=str(e),
                )
                db.session.add(log)
        campaign.status = "sent"
        campaign.sent_date = datetime.now(timezone.utc)
        campaign.sent_count = sent
        campaign.bounce_count = len(subscribers) - sent
        try:
            db.session.flush()
        except Exception:
            raise
        return campaign

    @staticmethod
    def get_campaign_stats(campaign_id, user):
        campaign = db.session.get(EmailCampaign, int(campaign_id))
        if not campaign:
            raise ValueError("الحملة غير موجودة.")
        tid = EmailMarketingService._tid(user)
        if tid is not None and int(campaign.tenant_id) != int(tid):
            raise ValueError("الحملة لا تنتمي إلى شركتك.")
        logs = CampaignLog.query.filter_by(campaign_id=campaign.id).all()
        return {
            "campaign": {
                "id": campaign.id,
                "name": campaign.name,
                "status": campaign.status,
                "sent_count": campaign.sent_count,
                "open_count": campaign.open_count,
                "click_count": campaign.click_count,
                "bounce_count": campaign.bounce_count,
            },
            "logs": [
                {
                    "id": log.id,
                    "subscriber_id": log.subscriber_id,
                    "status": log.status,
                    "sent_at": log.sent_at.isoformat() if log.sent_at else None,
                    "opened_at": log.opened_at.isoformat() if log.opened_at else None,
                }
                for log in logs
            ],
        }

    @staticmethod
    def list_campaigns(user):
        tid = EmailMarketingService._tid(user)
        if not tid:
            return []
        return (
            EmailCampaign.query.filter(
                EmailCampaign.tenant_id == tid,
                EmailCampaign.is_active,
            )
            .order_by(EmailCampaign.created_at.desc())
            .all()
        )
