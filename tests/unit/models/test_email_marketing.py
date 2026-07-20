"""Unit tests for models/email_marketing.py — lists, subscribers, templates,
campaigns, and campaign logs."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError


@pytest.fixture
def email_list(db_session, sample_tenant):
    from models.email_marketing import EmailList

    lst = EmailList(tenant_id=sample_tenant.id, name="Newsletter")
    db_session.add(lst)
    db_session.commit()
    return lst


@pytest.fixture
def subscriber(db_session, sample_tenant, email_list):
    from models.email_marketing import EmailSubscriber

    sub = EmailSubscriber(
        tenant_id=sample_tenant.id,
        list_id=email_list.id,
        email="fan@example.com",
        name="Fan One",
    )
    db_session.add(sub)
    db_session.commit()
    return sub


class TestEmailList:
    def test_create_with_defaults(self, email_list):
        assert email_list.id is not None
        assert email_list.is_active is True
        assert email_list.created_at is not None
        assert repr(email_list) == "<EmailList Newsletter>"

    def test_name_required(self, db_session, sample_tenant):
        from models.email_marketing import EmailList

        db_session.add(EmailList(tenant_id=sample_tenant.id, name=None))
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()


class TestEmailSubscriber:
    def test_create_with_defaults(self, subscriber):
        assert subscriber.id is not None
        assert subscriber.status == "subscribed"
        assert subscriber.unsubscribed_at is None
        assert subscriber.customer_id is None
        assert repr(subscriber) == "<EmailSubscriber fan@example.com>"

    def test_email_unique_per_list(
        self, db_session, sample_tenant, email_list, subscriber
    ):
        from models.email_marketing import EmailSubscriber

        db_session.add(
            EmailSubscriber(
                tenant_id=sample_tenant.id,
                list_id=email_list.id,
                email="fan@example.com",
            )
        )
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

    def test_same_email_allowed_in_other_list(
        self, db_session, sample_tenant, email_list, subscriber
    ):
        from models.email_marketing import EmailList, EmailSubscriber

        other = EmailList(tenant_id=sample_tenant.id, name="Promos")
        db_session.add(other)
        db_session.flush()
        db_session.add(
            EmailSubscriber(
                tenant_id=sample_tenant.id,
                list_id=other.id,
                email="fan@example.com",
            )
        )
        db_session.commit()

    def test_list_relationship(self, subscriber, email_list):
        assert subscriber.list is not None
        assert subscriber.list.id == email_list.id

    def test_deleting_list_cascades_to_subscribers(
        self, db_session, email_list, subscriber
    ):
        from models.email_marketing import EmailSubscriber

        db_session.delete(email_list)
        db_session.commit()
        assert EmailSubscriber.query.filter_by(list_id=email_list.id).count() == 0


class TestEmailTemplate:
    def test_create_with_defaults(self, db_session, sample_tenant):
        from models.email_marketing import EmailTemplate

        tpl = EmailTemplate(
            tenant_id=sample_tenant.id,
            name="Welcome",
            subject="أهلاً بك",
            body_html="<p>Hello</p>",
        )
        db_session.add(tpl)
        db_session.commit()

        assert tpl.id is not None
        assert tpl.is_active is True
        assert tpl.from_email is None
        assert repr(tpl) == "<EmailTemplate Welcome>"

    def test_body_html_required(self, db_session, sample_tenant):
        from models.email_marketing import EmailTemplate

        db_session.add(
            EmailTemplate(
                tenant_id=sample_tenant.id,
                name="Broken",
                subject="s",
                body_html=None,
            )
        )
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()


class TestEmailCampaign:
    def test_create_with_defaults(self, db_session, sample_tenant, email_list):
        from models.email_marketing import EmailCampaign

        camp = EmailCampaign(
            tenant_id=sample_tenant.id, name="June Promo", list_id=email_list.id
        )
        db_session.add(camp)
        db_session.commit()

        assert camp.status == "draft"
        assert camp.sent_count == 0
        assert camp.open_count == 0
        assert camp.click_count == 0
        assert camp.bounce_count == 0
        assert camp.is_active is True
        assert camp.scheduled_date is None
        assert camp.sent_date is None
        assert camp.list.id == email_list.id
        assert repr(camp) == "<EmailCampaign June Promo>"

    def test_list_is_optional(self, db_session, sample_tenant):
        from models.email_marketing import EmailCampaign

        camp = EmailCampaign(tenant_id=sample_tenant.id, name="No List")
        db_session.add(camp)
        db_session.commit()
        assert camp.list_id is None
        assert camp.template_id is None


class TestCampaignLog:
    def test_create_and_relationships(
        self, db_session, sample_tenant, email_list, subscriber
    ):
        from models.email_marketing import CampaignLog, EmailCampaign

        camp = EmailCampaign(
            tenant_id=sample_tenant.id, name="Log Camp", list_id=email_list.id
        )
        db_session.add(camp)
        db_session.flush()

        log = CampaignLog(
            tenant_id=sample_tenant.id,
            campaign_id=camp.id,
            subscriber_id=subscriber.id,
            status="queued",
        )
        db_session.add(log)
        db_session.commit()

        assert log.id is not None
        assert log.created_at is not None
        assert log.sent_at is None
        assert log.opened_at is None
        assert log.clicked_at is None
        assert log.campaign.id == camp.id
        assert log.subscriber.id == subscriber.id
        assert repr(log) == f"<CampaignLog C{camp.id} queued>"

    def test_status_required(self, db_session, sample_tenant):
        from models.email_marketing import CampaignLog

        db_session.add(
            CampaignLog(
                tenant_id=sample_tenant.id,
                campaign_id=1,
                subscriber_id=1,
                status=None,
            )
        )
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()
