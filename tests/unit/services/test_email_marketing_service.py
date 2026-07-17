"""Unit tests for EmailMarketingService."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from extensions import db
from models import (
    CampaignLog,
    EmailCampaign,
    EmailList,
    EmailSubscriber,
    EmailTemplate,
    Tenant,
)
from services.email_marketing_service import EmailMarketingService


@pytest.fixture(autouse=True)
def _app_context(app):
    with app.app_context():
        yield


@pytest.fixture(autouse=True)
def _transaction_rollback(db_session):
    yield
    db_session.rollback()


@pytest.fixture
def tenant_user(sample_user, mocker):
    mocker.patch(
        "services.email_marketing_service.get_active_tenant_id",
        return_value=sample_user.tenant_id,
    )
    return sample_user


def _email_list(db_session, tenant_id, name=None):
    row = EmailList(
        tenant_id=tenant_id,
        name=name or f"List {uuid.uuid4().hex[:6]}",
        description="desc",
    )
    db_session.add(row)
    db_session.flush()
    return row


def _template(db_session, tenant_id):
    row = EmailTemplate(
        tenant_id=tenant_id,
        name=f"Tpl {uuid.uuid4().hex[:6]}",
        subject="Hello",
        body_html="<p>Hi</p>",
        from_email="noreply@example.com",
    )
    db_session.add(row)
    db_session.flush()
    return row


def _subscriber(db_session, lst, email=None, status="subscribed"):
    row = EmailSubscriber(
        tenant_id=lst.tenant_id,
        list_id=lst.id,
        email=email or f"{uuid.uuid4().hex[:8]}@example.com",
        status=status,
    )
    db_session.add(row)
    db_session.flush()
    return row


def _campaign(db_session, tenant_id, lst, tpl, **kwargs):
    row = EmailCampaign(
        tenant_id=tenant_id,
        name=kwargs.get("name", f"Camp {uuid.uuid4().hex[:6]}"),
        list_id=lst.id,
        template_id=tpl.id,
        status=kwargs.get("status", "draft"),
    )
    db_session.add(row)
    db_session.flush()
    return row


def _other_tenant(db_session):
    unique = uuid.uuid4().hex[:8]
    row = Tenant(
        name=f"Other Co {unique}",
        name_ar="شركة أخرى",
        slug=f"other-{unique}",
        email=f"other-{unique}@example.com",
        country="AE",
        default_currency="AED",
        base_currency="AED",
    )
    db_session.add(row)
    db_session.flush()
    return row


class TestCreateList:
    def test_no_tenant_raises(self, sample_user, mocker):
        mocker.patch(
            "services.email_marketing_service.get_active_tenant_id", return_value=None
        )
        with pytest.raises(ValueError, match="شركة نشطة"):
            EmailMarketingService.create_list({"name": "X"}, sample_user)

    def test_missing_name_raises(self, tenant_user):
        with pytest.raises(ValueError, match="اسم القائمة"):
            EmailMarketingService.create_list({}, tenant_user)

    def test_creates_list(self, tenant_user, db_session):
        lst = EmailMarketingService.create_list(
            {"name": "News", "description": "D"}, tenant_user
        )
        assert lst.id is not None
        assert lst.name == "News"

    def test_commit_failure_raises(self, tenant_user, mocker):
        mocker.patch.object(db.session, "flush", side_effect=RuntimeError("db"))
        with pytest.raises(RuntimeError, match="db"):
            EmailMarketingService.create_list({"name": "News"}, tenant_user)


class TestListLists:
    def test_no_tenant_returns_empty(self, sample_user, mocker):
        mocker.patch(
            "services.email_marketing_service.get_active_tenant_id", return_value=None
        )
        assert EmailMarketingService.list_lists(sample_user) == []

    def test_returns_active_only(self, tenant_user, db_session, sample_tenant):
        active = _email_list(db_session, sample_tenant.id, name="Active")
        inactive = _email_list(db_session, sample_tenant.id, name="Inactive")
        inactive.is_active = False
        db_session.flush()
        names = {r.name for r in EmailMarketingService.list_lists(tenant_user)}
        assert "Active" in names
        assert "Inactive" not in names
        assert active.id is not None


class TestSubscribe:
    def test_list_not_found(self, tenant_user):
        with pytest.raises(ValueError, match="غير موجودة"):
            EmailMarketingService.subscribe(999999999, "a@b.com", user=tenant_user)

    def test_wrong_tenant_raises(self, tenant_user, db_session, mocker):
        other = _other_tenant(db_session)
        lst = _email_list(db_session, other.id)
        mocker.patch(
            "services.email_marketing_service.is_global_owner_user", return_value=False
        )
        with pytest.raises(ValueError, match="لا تنتمي"):
            EmailMarketingService.subscribe(lst.id, "x@y.com", user=tenant_user)

    def test_global_owner_other_tenant(self, tenant_user, db_session, mocker):
        other = _other_tenant(db_session)
        lst = _email_list(db_session, other.id)
        mocker.patch(
            "services.email_marketing_service.is_global_owner_user", return_value=True
        )
        sub = EmailMarketingService.subscribe(
            lst.id, "owner@example.com", user=tenant_user
        )
        assert sub.email == "owner@example.com"

    def test_without_user(self, db_session, sample_tenant):
        lst = _email_list(db_session, sample_tenant.id)
        sub = EmailMarketingService.subscribe(lst.id, "public@example.com")
        assert sub.status == "subscribed"

    def test_new_subscriber_with_customer(
        self, tenant_user, db_session, sample_tenant, sample_customer
    ):
        lst = _email_list(db_session, sample_tenant.id)
        sub = EmailMarketingService.subscribe(
            lst.id,
            "cust@example.com",
            name="Cust",
            customer_id=sample_customer.id,
            user=tenant_user,
        )
        assert sub.customer_id == sample_customer.id

    def test_resubscribes_unsubscribed(self, tenant_user, db_session, sample_tenant):
        lst = _email_list(db_session, sample_tenant.id)
        email = "back@example.com"
        existing = _subscriber(db_session, lst, email=email, status="unsubscribed")
        existing.unsubscribed_at = datetime.now(timezone.utc)
        db_session.flush()
        sub = EmailMarketingService.subscribe(lst.id, email, user=tenant_user)
        assert sub.id == existing.id
        assert sub.status == "subscribed"
        assert sub.unsubscribed_at is None

    def test_existing_subscribed_returns_as_is(
        self, tenant_user, db_session, sample_tenant
    ):
        lst = _email_list(db_session, sample_tenant.id)
        existing = _subscriber(db_session, lst, email="same@example.com")
        sub = EmailMarketingService.subscribe(
            lst.id, "same@example.com", user=tenant_user
        )
        assert sub.id == existing.id

    def test_commit_failure_on_new(
        self, tenant_user, db_session, sample_tenant, mocker
    ):
        lst = _email_list(db_session, sample_tenant.id)
        mocker.patch.object(db.session, "flush", side_effect=RuntimeError("sub fail"))
        with pytest.raises(RuntimeError, match="sub fail"):
            EmailMarketingService.subscribe(
                lst.id, "fail@example.com", user=tenant_user
            )

    def test_commit_failure_on_resubscribe(
        self, tenant_user, db_session, sample_tenant, mocker
    ):
        lst = _email_list(db_session, sample_tenant.id)
        _subscriber(db_session, lst, email="old@example.com", status="unsubscribed")
        mocker.patch.object(db.session, "flush", side_effect=RuntimeError("resub fail"))
        with pytest.raises(RuntimeError, match="resub fail"):
            EmailMarketingService.subscribe(lst.id, "old@example.com", user=tenant_user)


class TestUnsubscribe:
    def test_by_email(self, db_session, sample_tenant):
        import uuid

        email = f"leave-{uuid.uuid4().hex[:12]}@example.com"
        lst = _email_list(db_session, sample_tenant.id)
        sub = _subscriber(db_session, lst, email=email)
        count = EmailMarketingService.unsubscribe(email)
        assert count == 1
        db_session.refresh(sub)
        assert sub.status == "unsubscribed"

    def test_by_list_id(self, db_session, sample_tenant):
        lst = _email_list(db_session, sample_tenant.id)
        sub = _subscriber(db_session, lst, email="scoped@example.com")
        count = EmailMarketingService.unsubscribe("scoped@example.com", list_id=lst.id)
        assert count == 1
        db_session.refresh(sub)
        assert sub.status == "unsubscribed"

    def test_by_tenant_id(self, db_session, sample_tenant):
        lst = _email_list(db_session, sample_tenant.id)
        sub = _subscriber(db_session, lst, email="tenant@example.com")
        count = EmailMarketingService.unsubscribe(
            "tenant@example.com", tenant_id=sample_tenant.id
        )
        assert count == 1
        db_session.refresh(sub)
        assert sub.status == "unsubscribed"

    def test_commit_failure_raises(self, db_session, sample_tenant, mocker):
        lst = _email_list(db_session, sample_tenant.id)
        _subscriber(db_session, lst, email="err@example.com")
        mocker.patch.object(db.session, "flush", side_effect=RuntimeError("unsub fail"))
        with pytest.raises(RuntimeError, match="unsub fail"):
            EmailMarketingService.unsubscribe("err@example.com")


class TestCreateTemplate:
    def test_no_tenant_raises(self, sample_user, mocker):
        mocker.patch(
            "services.email_marketing_service.get_active_tenant_id", return_value=None
        )
        with pytest.raises(ValueError, match="شركة نشطة"):
            EmailMarketingService.create_template({"name": "T"}, sample_user)

    def test_missing_fields_raises(self, tenant_user):
        with pytest.raises(ValueError, match="القالب"):
            EmailMarketingService.create_template({"name": "T"}, tenant_user)

    def test_creates_template(self, tenant_user):
        tpl = EmailMarketingService.create_template(
            {
                "name": "Welcome",
                "subject": "Hi",
                "body_html": "<b>Hi</b>",
                "from_email": "a@b.com",
            },
            tenant_user,
        )
        assert tpl.subject == "Hi"

    def test_commit_failure_raises(self, tenant_user, mocker):
        mocker.patch.object(db.session, "flush", side_effect=RuntimeError("tpl fail"))
        with pytest.raises(RuntimeError, match="tpl fail"):
            EmailMarketingService.create_template(
                {
                    "name": "W",
                    "subject": "S",
                    "body_html": "<p>x</p>",
                },
                tenant_user,
            )


class TestListTemplates:
    def test_no_tenant_returns_empty(self, sample_user, mocker):
        mocker.patch(
            "services.email_marketing_service.get_active_tenant_id", return_value=None
        )
        assert EmailMarketingService.list_templates(sample_user) == []

    def test_returns_active_templates(self, tenant_user, db_session, sample_tenant):
        active = _template(db_session, sample_tenant.id)
        inactive = _template(db_session, sample_tenant.id)
        inactive.is_active = False
        db_session.flush()
        ids = {t.id for t in EmailMarketingService.list_templates(tenant_user)}
        assert active.id in ids
        assert inactive.id not in ids


class TestCreateCampaign:
    def test_no_tenant_raises(self, sample_user, mocker):
        mocker.patch(
            "services.email_marketing_service.get_active_tenant_id", return_value=None
        )
        with pytest.raises(ValueError, match="شركة نشطة"):
            EmailMarketingService.create_campaign({"name": "C"}, sample_user)

    def test_missing_name_raises(self, tenant_user):
        with pytest.raises(ValueError, match="اسم الحملة"):
            EmailMarketingService.create_campaign({}, tenant_user)

    def test_creates_with_optional_fields(self, tenant_user, db_session, sample_tenant):
        lst = _email_list(db_session, sample_tenant.id)
        tpl = _template(db_session, sample_tenant.id)
        camp = EmailMarketingService.create_campaign(
            {
                "name": "Launch",
                "list_id": lst.id,
                "template_id": tpl.id,
                "scheduled_date": "2026-07-01T10:00:00",
            },
            tenant_user,
        )
        assert camp.list_id == lst.id
        assert camp.scheduled_date is not None

    def test_commit_failure_raises(self, tenant_user, mocker):
        mocker.patch.object(db.session, "flush", side_effect=RuntimeError("camp fail"))
        with pytest.raises(RuntimeError, match="camp fail"):
            EmailMarketingService.create_campaign({"name": "X"}, tenant_user)


class TestSendCampaign:
    @staticmethod
    def _ready_campaign(db_session, sample_tenant):
        lst = _email_list(db_session, sample_tenant.id)
        tpl = _template(db_session, sample_tenant.id)
        camp = _campaign(db_session, sample_tenant.id, lst, tpl)
        _subscriber(db_session, lst)
        return camp

    def test_not_found(self, tenant_user):
        with pytest.raises(ValueError, match="غير موجودة"):
            EmailMarketingService.send_campaign(999999999, tenant_user)

    def test_wrong_tenant(self, tenant_user, db_session, mocker):
        other = _other_tenant(db_session)
        lst = _email_list(db_session, other.id)
        tpl = _template(db_session, other.id)
        camp = _campaign(db_session, other.id, lst, tpl)
        mocker.patch(
            "services.email_marketing_service.is_global_owner_user", return_value=False
        )
        with pytest.raises(ValueError, match="لا تنتمي"):
            EmailMarketingService.send_campaign(camp.id, tenant_user)

    def test_not_draft(self, tenant_user, db_session, sample_tenant):
        camp = TestSendCampaign._ready_campaign(db_session, sample_tenant)
        camp.status = "sent"
        db_session.flush()
        with pytest.raises(ValueError, match="المسودة"):
            EmailMarketingService.send_campaign(camp.id, tenant_user)

    def test_no_list(self, tenant_user, db_session, sample_tenant):
        lst = _email_list(db_session, sample_tenant.id)
        tpl = _template(db_session, sample_tenant.id)
        camp = EmailCampaign(
            tenant_id=sample_tenant.id,
            name="No list",
            template_id=tpl.id,
            status="draft",
        )
        db_session.add(camp)
        db_session.flush()
        with pytest.raises(ValueError, match="قائمة بريدية"):
            EmailMarketingService.send_campaign(camp.id, tenant_user)

    def test_no_template(self, tenant_user, db_session, sample_tenant):
        lst = _email_list(db_session, sample_tenant.id)
        camp = EmailCampaign(
            tenant_id=sample_tenant.id, name="No tpl", list_id=lst.id, status="draft"
        )
        db_session.add(camp)
        db_session.flush()
        with pytest.raises(ValueError, match="قالب"):
            EmailMarketingService.send_campaign(camp.id, tenant_user)

    def test_no_subscribers(self, tenant_user, db_session, sample_tenant):
        lst = _email_list(db_session, sample_tenant.id)
        tpl = _template(db_session, sample_tenant.id)
        camp = _campaign(db_session, sample_tenant.id, lst, tpl)
        with pytest.raises(ValueError, match="مشتركون"):
            EmailMarketingService.send_campaign(camp.id, tenant_user)

    def test_mail_not_configured(self, tenant_user, db_session, sample_tenant, app):
        camp = TestSendCampaign._ready_campaign(db_session, sample_tenant)
        app.extensions.pop("mail", None)
        with pytest.raises(ValueError, match="البريد"):
            EmailMarketingService.send_campaign(camp.id, tenant_user)

    def test_sends_and_logs_bounces(
        self, tenant_user, db_session, sample_tenant, app, mocker
    ):
        lst = _email_list(db_session, sample_tenant.id)
        tpl = _template(db_session, sample_tenant.id)
        camp = _campaign(db_session, sample_tenant.id, lst, tpl)
        ok = _subscriber(db_session, lst, email="ok@example.com")
        bad = _subscriber(db_session, lst, email="bad@example.com")

        mail = MagicMock()
        mail.send.side_effect = [None, RuntimeError("smtp fail")]
        app.extensions["mail"] = mail
        app.config["MAIL_DEFAULT_SENDER"] = "sender@example.com"

        result = EmailMarketingService.send_campaign(camp.id, tenant_user)
        assert result.status == "sent"
        assert result.sent_count == 1
        assert result.bounce_count == 1
        logs = CampaignLog.query.filter_by(campaign_id=camp.id).all()
        assert len(logs) == 2
        assert {ok.id, bad.id} == {log.subscriber_id for log in logs}

    def test_uses_template_from_email(
        self, tenant_user, db_session, sample_tenant, app, mocker
    ):
        camp = TestSendCampaign._ready_campaign(db_session, sample_tenant)
        mail = MagicMock()
        app.extensions["mail"] = mail
        captured = {}

        def capture_send(msg):
            captured["sender"] = msg.sender

        mail.send.side_effect = capture_send
        EmailMarketingService.send_campaign(camp.id, tenant_user)
        assert captured["sender"] == "noreply@example.com"

    def test_commit_failure_raises(
        self, tenant_user, db_session, sample_tenant, app, mocker
    ):
        camp = TestSendCampaign._ready_campaign(db_session, sample_tenant)
        app.extensions["mail"] = MagicMock()
        mocker.patch.object(db.session, "flush", side_effect=RuntimeError("send fail"))
        with pytest.raises(RuntimeError, match="send fail"):
            EmailMarketingService.send_campaign(camp.id, tenant_user)


class TestGetCampaignStats:
    def test_not_found(self, tenant_user):
        with pytest.raises(ValueError, match="غير موجودة"):
            EmailMarketingService.get_campaign_stats(999999999, tenant_user)

    def test_wrong_tenant(self, tenant_user, db_session, mocker):
        other = _other_tenant(db_session)
        lst = _email_list(db_session, other.id)
        tpl = _template(db_session, other.id)
        camp = _campaign(db_session, other.id, lst, tpl, status="sent")
        mocker.patch(
            "services.email_marketing_service.is_global_owner_user", return_value=False
        )
        with pytest.raises(ValueError, match="لا تنتمي"):
            EmailMarketingService.get_campaign_stats(camp.id, tenant_user)

    def test_returns_stats_and_logs(self, tenant_user, db_session, sample_tenant):
        lst = _email_list(db_session, sample_tenant.id)
        tpl = _template(db_session, sample_tenant.id)
        camp = _campaign(db_session, sample_tenant.id, lst, tpl, status="sent")
        sub = _subscriber(db_session, lst)
        sent_log = CampaignLog(
            tenant_id=sample_tenant.id,
            campaign_id=camp.id,
            subscriber_id=sub.id,
            status="sent",
            sent_at=datetime.now(timezone.utc),
        )
        db_session.add(sent_log)
        db_session.flush()

        stats = EmailMarketingService.get_campaign_stats(camp.id, tenant_user)
        assert stats["campaign"]["id"] == camp.id
        assert len(stats["logs"]) == 1
        assert stats["logs"][0]["sent_at"] is not None
        assert stats["logs"][0]["opened_at"] is None


class TestListCampaigns:
    def test_no_tenant_returns_empty(self, sample_user, mocker):
        mocker.patch(
            "services.email_marketing_service.get_active_tenant_id", return_value=None
        )
        assert EmailMarketingService.list_campaigns(sample_user) == []

    def test_returns_active_campaigns(self, tenant_user, db_session, sample_tenant):
        lst = _email_list(db_session, sample_tenant.id)
        tpl = _template(db_session, sample_tenant.id)
        active = _campaign(db_session, sample_tenant.id, lst, tpl)
        inactive = _campaign(db_session, sample_tenant.id, lst, tpl)
        inactive.is_active = False
        db_session.flush()
        ids = {c.id for c in EmailMarketingService.list_campaigns(tenant_user)}
        assert active.id in ids
        assert inactive.id not in ids
