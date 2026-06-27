from __future__ import annotations

from contextlib import ExitStack, contextmanager
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.routes.conftest import app_factory, bypass_permission_auth, unauthenticated_client


@contextmanager
def _marketing_patches(**kwargs):
    with ExitStack() as stack:
        stack.enter_context(patch('routes.email_marketing.render_template', return_value='ok'))
        stack.enter_context(
            patch(
                'routes.email_marketing.EmailMarketingService.list_campaigns',
                return_value=kwargs.get('campaigns', []),
            )
        )
        stack.enter_context(
            patch(
                'routes.email_marketing.EmailMarketingService.list_lists',
                return_value=kwargs.get('lists', []),
            )
        )
        stack.enter_context(
            patch(
                'routes.email_marketing.EmailMarketingService.list_templates',
                return_value=kwargs.get('templates', []),
            )
        )
        stack.enter_context(
            patch(
                'routes.email_marketing.EmailMarketingService.get_campaign_stats',
                return_value=kwargs.get('stats', {'sent': 0}),
            )
        )
        stack.enter_context(
            patch('routes.email_marketing.EmailMarketingService.create_campaign')
        )
        stack.enter_context(
            patch('routes.email_marketing.EmailMarketingService.send_campaign')
        )
        stack.enter_context(
            patch('routes.email_marketing.EmailMarketingService.create_list')
        )
        stack.enter_context(
            patch('routes.email_marketing.EmailMarketingService.create_template')
        )
        yield


@pytest.fixture
def marketing_client(app_factory, bypass_permission_auth):
    from routes.email_marketing import email_marketing_bp

    app = app_factory(email_marketing_bp)
    return app.test_client()


class TestEmailMarketingAuth:
    def test_campaigns_requires_login(self, marketing_client):
        with _marketing_patches(), unauthenticated_client(marketing_client):
            resp = marketing_client.get('/marketing/')
        assert resp.status_code == 401

    def test_campaigns_forbidden_without_permission(self, marketing_client, bypass_permission_auth):
        bypass_permission_auth.has_permission.return_value = False
        with _marketing_patches(), patch('utils.decorators.is_global_owner_user', return_value=False):
            resp = marketing_client.get('/marketing/')
        assert resp.status_code == 403


class TestCampaigns:
    def test_campaigns_list(self, marketing_client):
        with _marketing_patches(campaigns=[MagicMock(id=1)]):
            resp = marketing_client.get('/marketing/')
        assert resp.status_code == 200

    def test_create_campaign_get(self, marketing_client):
        with _marketing_patches():
            resp = marketing_client.get('/marketing/campaigns/create')
        assert resp.status_code == 200

    def test_create_campaign_post_success(self, marketing_client):
        with _marketing_patches():
            resp = marketing_client.post(
                '/marketing/campaigns/create',
                data={'name': 'Summer', 'list_id': '1', 'template_id': '1'},
            )
        assert resp.status_code == 302
        assert '/marketing/' in resp.headers['Location']

    def test_create_campaign_post_error(self, marketing_client):
        with _marketing_patches():
            with patch(
                'routes.email_marketing.EmailMarketingService.create_campaign',
                side_effect=RuntimeError('fail'),
            ):
                resp = marketing_client.post(
                    '/marketing/campaigns/create',
                    data={'name': 'Bad'},
                )
        assert resp.status_code == 200

    def test_campaign_detail(self, marketing_client):
        with _marketing_patches(stats={'opens': 5}):
            resp = marketing_client.get('/marketing/campaigns/7')
        assert resp.status_code == 200

    def test_campaign_detail_not_found(self, marketing_client):
        with _marketing_patches():
            with patch(
                'routes.email_marketing.EmailMarketingService.get_campaign_stats',
                side_effect=ValueError('missing'),
            ):
                resp = marketing_client.get('/marketing/campaigns/99')
        assert resp.status_code == 302

    def test_send_campaign_success(self, marketing_client):
        with _marketing_patches():
            resp = marketing_client.post('/marketing/campaigns/3/send')
        assert resp.status_code == 302

    def test_send_campaign_error(self, marketing_client):
        with _marketing_patches():
            with patch(
                'routes.email_marketing.EmailMarketingService.send_campaign',
                side_effect=ValueError('not draft'),
            ):
                resp = marketing_client.post('/marketing/campaigns/3/send')
        assert resp.status_code == 302


class TestLists:
    def test_lists_page(self, marketing_client):
        with _marketing_patches(lists=[MagicMock(id=2)]):
            resp = marketing_client.get('/marketing/lists')
        assert resp.status_code == 200

    def test_create_list_success(self, marketing_client):
        with _marketing_patches():
            resp = marketing_client.post(
                '/marketing/lists/create',
                data={'name': 'VIP'},
            )
        assert resp.status_code == 302

    def test_create_list_value_error(self, marketing_client):
        with _marketing_patches():
            with patch(
                'routes.email_marketing.EmailMarketingService.create_list',
                side_effect=ValueError('duplicate'),
            ):
                resp = marketing_client.post(
                    '/marketing/lists/create',
                    data={'name': ''},
                )
        assert resp.status_code == 302

    def test_create_list_key_error(self, marketing_client):
        with _marketing_patches():
            with patch(
                'routes.email_marketing.EmailMarketingService.create_list',
                side_effect=KeyError('name'),
            ):
                resp = marketing_client.post('/marketing/lists/create', data={})
        assert resp.status_code == 302


class TestTemplates:
    def test_templates_page(self, marketing_client):
        with _marketing_patches(templates=[MagicMock(id=3)]):
            resp = marketing_client.get('/marketing/templates')
        assert resp.status_code == 200

    def test_create_template_success(self, marketing_client):
        with _marketing_patches():
            resp = marketing_client.post(
                '/marketing/templates/create',
                data={'name': 'Welcome', 'subject': 'Hi', 'body': '<p>Hi</p>'},
            )
        assert resp.status_code == 302

    def test_create_template_value_error(self, marketing_client):
        with _marketing_patches():
            with patch(
                'routes.email_marketing.EmailMarketingService.create_template',
                side_effect=ValueError('invalid'),
            ):
                resp = marketing_client.post(
                    '/marketing/templates/create',
                    data={'name': 'x'},
                )
        assert resp.status_code == 302

    def test_create_template_key_error(self, marketing_client):
        with _marketing_patches():
            with patch(
                'routes.email_marketing.EmailMarketingService.create_template',
                side_effect=KeyError('subject'),
            ):
                resp = marketing_client.post('/marketing/templates/create', data={})
        assert resp.status_code == 302
