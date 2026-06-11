"""Tests for Email Marketing module"""
import pytest
from models import EmailList, EmailSubscriber, EmailTemplate, EmailCampaign, CampaignLog


class TestEmailMarketingModels:
    def test_email_list_creation(self, app, db_session, sample_tenant):
        lst = EmailList(tenant_id=sample_tenant.id, name='Newsletter')
        db_session.add(lst)
        db_session.commit()
        assert lst.id

    def test_subscriber_creation(self, app, db_session, sample_tenant):
        lst = EmailList(tenant_id=sample_tenant.id, name='Test List')
        db_session.add(lst)
        db_session.flush()
        sub = EmailSubscriber(
            tenant_id=sample_tenant.id,
            list_id=lst.id,
            email='test@example.com',
            status='subscribed',
        )
        db_session.add(sub)
        db_session.commit()
        assert sub.id
        assert len(lst.subscribers) == 1

    def test_unique_subscriber_constraint(self, app, db_session, sample_tenant):
        lst = EmailList(tenant_id=sample_tenant.id, name='Unique List')
        db_session.add(lst)
        db_session.flush()
        sub1 = EmailSubscriber(tenant_id=sample_tenant.id, list_id=lst.id, email='dup@example.com')
        db_session.add(sub1)
        db_session.commit()
        sub2 = EmailSubscriber(tenant_id=sample_tenant.id, list_id=lst.id, email='dup@example.com')
        db_session.add(sub2)
        with pytest.raises(Exception):
            db_session.commit()
        db_session.rollback()

    def test_unsubscribe(self, app, db_session, sample_tenant):
        lst = EmailList(tenant_id=sample_tenant.id, name='Unsub List')
        db_session.add(lst)
        db_session.flush()
        sub = EmailSubscriber(
            tenant_id=sample_tenant.id,
            list_id=lst.id,
            email='unsub@example.com',
            status='subscribed',
        )
        db_session.add(sub)
        db_session.commit()
        sub.status = 'unsubscribed'
        db_session.commit()
        assert sub.status == 'unsubscribed'

    def test_template_creation(self, app, db_session, sample_tenant):
        tpl = EmailTemplate(
            tenant_id=sample_tenant.id,
            name='Welcome',
            subject='Welcome!',
            body_html='<h1>Welcome</h1>',
        )
        db_session.add(tpl)
        db_session.commit()
        assert tpl.id

    def test_campaign_creation(self, app, db_session, sample_tenant):
        lst = EmailList(tenant_id=sample_tenant.id, name='Campaign List')
        db_session.add(lst)
        db_session.flush()
        tpl = EmailTemplate(
            tenant_id=sample_tenant.id,
            name='Camp Tpl',
            subject='Campaign',
            body_html='<p>Campaign</p>',
        )
        db_session.add(tpl)
        db_session.flush()
        c = EmailCampaign(
            tenant_id=sample_tenant.id,
            name='Test Campaign',
            list_id=lst.id,
            template_id=tpl.id,
            status='draft',
        )
        db_session.add(c)
        db_session.commit()
        assert c.id
        assert c.status == 'draft'

    def test_campaign_log(self, app, db_session, sample_tenant):
        lst = EmailList(tenant_id=sample_tenant.id, name='Log List')
        db_session.add(lst)
        db_session.flush()
        sub = EmailSubscriber(tenant_id=sample_tenant.id, list_id=lst.id, email='log@example.com')
        db_session.add(sub)
        db_session.flush()
        c = EmailCampaign(tenant_id=sample_tenant.id, name='Log Campaign', status='sent')
        db_session.add(c)
        db_session.flush()
        log = CampaignLog(
            tenant_id=sample_tenant.id,
            campaign_id=c.id,
            subscriber_id=sub.id,
            status='sent',
        )
        db_session.add(log)
        db_session.commit()
        assert len(c.logs) == 1
