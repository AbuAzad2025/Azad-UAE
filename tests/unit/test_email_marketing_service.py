"""Email Marketing Service unit tests."""
import pytest
from datetime import datetime, timezone
from services.email_marketing_service import EmailMarketingService


class TestEmailMarketingService:
    def test_create_list(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            lst = EmailMarketingService.create_list({'name': 'Newsletter'}, sample_user)
            assert lst.id is not None
            assert lst.name == 'Newsletter'
            assert lst.tenant_id == sample_tenant.id

    def test_create_list_no_name_raises(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            with pytest.raises(ValueError):
                EmailMarketingService.create_list({}, sample_user)

    def test_list_lists(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            EmailMarketingService.create_list({'name': 'L1'}, sample_user)
            result = EmailMarketingService.list_lists(sample_user)
            assert len(result) >= 1

    def test_subscribe(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            lst = EmailMarketingService.create_list({'name': 'L1'}, sample_user)
            sub = EmailMarketingService.subscribe(lst.id, 'a@test.com', name='Ali')
            assert sub.id is not None
            assert sub.email == 'a@test.com'
            assert sub.status == 'subscribed'

    def test_subscribe_existing_resubscribe(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            lst = EmailMarketingService.create_list({'name': 'L1'}, sample_user)
            EmailMarketingService.subscribe(lst.id, 'a@test.com')
            sub = EmailMarketingService.subscribe(lst.id, 'a@test.com')
            assert sub.status == 'subscribed'

    def test_unsubscribe(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            lst = EmailMarketingService.create_list({'name': 'L1'}, sample_user)
            EmailMarketingService.subscribe(lst.id, 'a@test.com')
            count = EmailMarketingService.unsubscribe('a@test.com', list_id=lst.id)
            assert count == 1
            from models import EmailSubscriber
            sub = EmailSubscriber.query.filter_by(list_id=lst.id, email='a@test.com').first()
            assert sub.status == 'unsubscribed'

    def test_create_template(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            tpl = EmailMarketingService.create_template({
                'name': 'Welcome',
                'subject': 'Welcome!',
                'body_html': '<p>Hello</p>',
            }, sample_user)
            assert tpl.id is not None
            assert tpl.name == 'Welcome'

    def test_create_template_missing_fields_raises(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            with pytest.raises(ValueError):
                EmailMarketingService.create_template({'name': 'X'}, sample_user)

    def test_list_templates(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            EmailMarketingService.create_template({
                'name': 'T1', 'subject': 'S', 'body_html': '<p>H</p>',
            }, sample_user)
            result = EmailMarketingService.list_templates(sample_user)
            assert len(result) >= 1

    def test_create_campaign(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            campaign = EmailMarketingService.create_campaign({'name': 'C1'}, sample_user)
            assert campaign.id is not None
            assert campaign.status == 'draft'

    def test_create_campaign_no_name_raises(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            with pytest.raises(ValueError):
                EmailMarketingService.create_campaign({}, sample_user)
