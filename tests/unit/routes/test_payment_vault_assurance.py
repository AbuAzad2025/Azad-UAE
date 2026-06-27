"""Payment vault routes — assurance tests for helper gaps and error paths."""
from __future__ import annotations

pytest_plugins = ['tests.unit.conftest']

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from tests.unit.conftest import app_factory, bypass_owner_auth, mock_db

import routes.payment_vault as pv_mod


def _patch_package_query(mocker, **query_attrs):
    pkg_q = MagicMock()
    for attr, value in query_attrs.items():
        getattr(pkg_q, attr).return_value = value
    mocker.patch.object(pv_mod, 'Package', MagicMock(query=pkg_q))
    return pkg_q


def _patch_purchase_query(mocker, **query_attrs):
    purchase_q = MagicMock()
    for attr, value in query_attrs.items():
        getattr(purchase_q, attr).return_value = value
    mocker.patch.object(pv_mod, 'PackagePurchase', MagicMock(query=purchase_q))
    return purchase_q


@pytest.fixture(autouse=True)
def _patch_db(mock_db):
    pass


@pytest.fixture(autouse=True)
def _patch_render(mocker):
    mocker.patch('routes.payment_vault.render_template', return_value='ok')


@pytest.fixture
def mock_unlocked_vault(mocker):
    vault = MagicMock()
    vault.id = 1
    vault.is_locked = False
    vault.is_vault_accessible.return_value = True
    vault.unlock_vault.return_value = True
    vault.is_locked_out.return_value = False
    vault.check_vault_password.return_value = True
    vault.nowpayments_api_key = ''
    vault.nowpayments_ipn_secret = 'sec'
    vault.stripe_webhook_secret = 'whsec'
    mocker.patch('routes.payment_vault._get_vault_for_current_tenant', return_value=vault)
    mocker.patch('routes.payment_vault.PaymentVault.get_platform_vault', return_value=vault)
    return vault


@pytest.fixture
def mock_locked_vault(mocker):
    vault = MagicMock()
    vault.id = 1
    vault.is_locked = True
    vault.is_vault_accessible.return_value = False
    mocker.patch('routes.payment_vault._get_vault_for_current_tenant', return_value=vault)
    return vault


@pytest.fixture
def vault_anon_client(app_factory, mocker):
    user = MagicMock()
    user.is_authenticated = False
    user.is_owner = False
    mocker.patch('flask_login.utils._get_user', return_value=user)
    mocker.patch('extensions.limiter.limit', return_value=lambda f: f)
    from routes.payment_vault import payment_vault_bp
    return app_factory(payment_vault_bp).test_client()


class TestProtectOwnerVaultPages:
    def test_non_owner_redirects_to_dashboard(self, app_factory, mocker):
        from routes.payment_vault import payment_vault_bp, _protect_owner_vault_pages

        user = MagicMock(is_authenticated=True, is_owner=False)
        mocker.patch('routes.payment_vault.current_user', user)
        mocker.patch('routes.payment_vault.url_for', return_value='/main/dashboard')
        app = app_factory(payment_vault_bp)
        with app.test_request_context('/payment-vault/dashboard'):
            resp = _protect_owner_vault_pages()
        assert resp is not None
        assert resp.status_code == 302
        assert resp.location.endswith('/main/dashboard')

    def test_unauthenticated_redirects_to_login(self, app_factory, mocker):
        from routes.payment_vault import payment_vault_bp, _protect_owner_vault_pages

        user = MagicMock(is_authenticated=False, is_owner=False)
        mocker.patch('routes.payment_vault.current_user', user)
        mocker.patch('routes.payment_vault.url_for', return_value='/auth/login')
        app = app_factory(payment_vault_bp)
        with app.test_request_context('/payment-vault/'):
            resp = _protect_owner_vault_pages()
        assert resp is not None
        assert resp.status_code == 302
        assert resp.location.endswith('/auth/login')

    def test_api_path_skips_page_guard(self, vault_anon_client, mocker):
        mocker.patch(
            'routes.payment_vault._validate_public_api_origin',
            return_value=({'success': False, 'error': 'Origin'}, 403),
        )
        resp = vault_anon_client.post(
            '/payment-vault/api/donation',
            json={'amount': 50, 'payment_method': 'crypto'},
        )
        assert resp.status_code == 403
        assert resp.get_json()['success'] is False


class TestSecurityHelperGaps:
    def test_is_production_env_default_app_env(self, app_factory, monkeypatch):
        from routes.payment_vault import payment_vault_bp, _is_production_env

        monkeypatch.delenv('APP_ENV', raising=False)
        monkeypatch.delenv('DEBUG', raising=False)
        app = app_factory(payment_vault_bp)
        with app.app_context():
            assert _is_production_env() is True

    def test_is_production_env_development(self, app_factory, monkeypatch):
        from routes.payment_vault import payment_vault_bp, _is_production_env

        monkeypatch.setenv('APP_ENV', 'development')
        monkeypatch.delenv('DEBUG', raising=False)
        app = app_factory(payment_vault_bp)
        with app.app_context():
            assert _is_production_env() is False

    def test_trusted_origins_production_empty_base_url(self, app_factory, monkeypatch):
        from routes.payment_vault import payment_vault_bp, _payment_vault_trusted_origins

        monkeypatch.setenv('APP_ENV', 'production')
        monkeypatch.delenv('DEBUG', raising=False)
        app = app_factory(payment_vault_bp, {'BASE_URL': ''})
        with app.app_context():
            assert _payment_vault_trusted_origins() == frozenset()

    def test_origin_from_referer_parse_exception(self, mocker):
        from routes.payment_vault import _origin_from_referer

        mocker.patch('routes.payment_vault.urlparse', side_effect=ValueError('bad'))
        assert _origin_from_referer('http://localhost:5000/x') is None

    def test_validate_public_api_origin_trusted_origin_header(self, app_factory, mocker):
        from routes.payment_vault import payment_vault_bp, _validate_public_api_origin

        mocker.patch(
            'routes.payment_vault._payment_vault_trusted_origins',
            return_value=frozenset({'http://localhost:5000'}),
        )
        app = app_factory(payment_vault_bp)
        with app.test_request_context('/', headers={'Origin': 'http://localhost:5000'}):
            assert _validate_public_api_origin() is None

    def test_validate_public_api_origin_untrusted_referer(self, app_factory, mocker):
        from routes.payment_vault import payment_vault_bp, _validate_public_api_origin

        mocker.patch(
            'routes.payment_vault._payment_vault_trusted_origins',
            return_value=frozenset({'http://localhost:5000'}),
        )
        app = app_factory(payment_vault_bp)
        with app.test_request_context('/', headers={'Referer': 'https://evil.example/pay'}):
            resp, code = _validate_public_api_origin()
        assert code == 403
        assert 'Referer' in resp.get_json()['error']

    def test_validate_api_key_commit_rollback(self, app_factory, mock_db, mocker):
        from routes.payment_vault import payment_vault_bp, _validate_api_key

        mock_key = MagicMock(scope='write', last_used=None, usage_count=0)
        mock_query = MagicMock()
        mock_query.filter_by.return_value.first.return_value = mock_key
        mocker.patch('models.APIKey', MagicMock(query=mock_query))
        mock_db.commit.side_effect = RuntimeError('db down')

        app = app_factory(payment_vault_bp)
        with app.test_request_context(headers={'X-API-Key': 'write-key'}):
            assert _validate_api_key(required_scope='write') is None
        mock_db.rollback.assert_called()

    def test_reject_stale_webhook_created_at_with_app(self, app_factory):
        from routes.payment_vault import payment_vault_bp, _reject_stale_webhook_timestamp

        app = app_factory(payment_vault_bp)
        old = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        with app.app_context():
            resp, code = _reject_stale_webhook_timestamp({'created_at': old})
        assert code == 401


class TestLockedVaultErrorPaths:
    def test_delete_package_locked_returns_403(self, vault_owner_client, mock_locked_vault):
        resp = vault_owner_client.post('/payment-vault/package/1/delete')
        assert resp.status_code == 403

    def test_decrypt_card_locked_returns_403(self, vault_owner_client, mock_locked_vault):
        resp = vault_owner_client.post('/payment-vault/card/1/decrypt')
        assert resp.status_code == 403

    def test_purchase_detail_locked_redirects(self, vault_owner_client, mock_locked_vault):
        resp = vault_owner_client.get('/payment-vault/purchase/1', follow_redirects=False)
        assert resp.status_code == 302

    def test_purchases_locked_redirects(self, vault_owner_client, mock_locked_vault):
        resp = vault_owner_client.get('/payment-vault/purchases', follow_redirects=False)
        assert resp.status_code == 302

    def test_donation_detail_locked_redirects(self, vault_owner_client, mock_locked_vault):
        resp = vault_owner_client.get('/payment-vault/donation/1', follow_redirects=False)
        assert resp.status_code == 302


class TestMutationErrorPaths:
    def test_delete_package_db_error_returns_400(
        self, vault_owner_client, mock_unlocked_vault, mock_db, mocker,
    ):
        pkg = MagicMock()
        _patch_package_query(mocker, get_or_404=pkg)
        mock_db.commit.side_effect = RuntimeError('fk')
        resp = vault_owner_client.post('/payment-vault/package/9/delete')
        assert resp.status_code == 400
        assert resp.get_json()['success'] is False

    def test_create_package_exception_rolls_back(
        self, vault_owner_client, mock_unlocked_vault, mock_db, mocker,
    ):
        pkg_q = MagicMock()
        fb = MagicMock()
        fb.first.return_value = None
        pkg_q.filter_by.return_value = fb
        mocker.patch.object(pv_mod, 'Package', MagicMock(query=pkg_q))
        mock_db.commit.side_effect = RuntimeError('insert fail')
        resp = vault_owner_client.post('/payment-vault/package/create', data={
            'name_ar': 'باقة', 'name_en': 'Pack', 'price': '10',
        }, follow_redirects=False)
        assert resp.status_code == 302
        mock_db.rollback.assert_called()

    def test_edit_package_exception_rolls_back(
        self, vault_owner_client, mock_unlocked_vault, mock_db, mocker,
    ):
        pkg = MagicMock(price=10, max_users=1, max_branches=1)
        _patch_package_query(mocker, get_or_404=pkg)
        mock_db.commit.side_effect = RuntimeError('update fail')
        resp = vault_owner_client.post('/payment-vault/package/1/edit', data={
            'name_ar': 'تعديل', 'name_en': 'Edit', 'price': '20',
        })
        assert resp.status_code == 200
        mock_db.rollback.assert_called()

    def test_lock_vault_without_vault_still_redirects(self, vault_owner_client, mocker):
        mocker.patch('routes.payment_vault._get_vault_for_current_tenant', return_value=None)
        resp = vault_owner_client.post('/payment-vault/lock', follow_redirects=False)
        assert resp.status_code == 302


class TestAutoApproveSuccess:
    def test_auto_approve_notifies_when_approvals_exist(
        self, vault_owner_client, mock_unlocked_vault, mocker,
    ):
        mocker.patch(
            'services.auto_approval_service.AutoApprovalService.run_auto_approval',
            return_value={'total_approved': 2, 'total_amount': 150.0},
        )
        notify = mocker.patch(
            'services.notification_service.NotificationService.notify_auto_approval',
        )
        resp = vault_owner_client.post('/payment-vault/auto-approve', follow_redirects=False)
        assert resp.status_code == 302
        notify.assert_called_once_with(2, 150.0)


class TestWebhookEdgePaths:
    NP_PAYLOAD = b'{"payment_id":"np-dup","payment_status":"finished"}'
    STRIPE_PAYLOAD = b'{"id":"evt_dup","type":"payment_intent.succeeded"}'

    def test_nowpayments_duplicate_webhook(self, vault_owner_client, mock_unlocked_vault, mocker):
        mocker.patch('routes.payment_vault._is_duplicate_webhook', return_value=True)
        mocker.patch('routes.payment_vault._reject_stale_webhook_timestamp', return_value=None)
        mocker.patch('utils.nowpayments_ipn.resolve_nowpayments_ipn_secret', return_value='sec')
        mocker.patch(
            'services.webhook_service.WebhookService.verify_nowpayments_signature',
            return_value=True,
        )
        resp = vault_owner_client.post(
            '/payment-vault/webhook/nowpayments',
            data=self.NP_PAYLOAD,
            content_type='application/json',
            headers={'x-nowpayments-sig': 'sig'},
        )
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'duplicate'

    def test_nowpayments_stale_timestamp_rejected(self, vault_owner_client, mock_unlocked_vault, mocker):
        mocker.patch('routes.payment_vault._is_duplicate_webhook', return_value=False)
        mocker.patch('utils.nowpayments_ipn.resolve_nowpayments_ipn_secret', return_value='sec')
        old = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        payload = f'{{"payment_id":"np-old","timestamp":"{old}"}}'.encode()
        resp = vault_owner_client.post(
            '/payment-vault/webhook/nowpayments',
            data=payload,
            content_type='application/json',
            headers={'x-nowpayments-sig': 'sig'},
        )
        assert resp.status_code == 401

    def test_nowpayments_process_failure_returns_400(
        self, vault_owner_client, mock_unlocked_vault, mocker,
    ):
        mocker.patch('routes.payment_vault._is_duplicate_webhook', return_value=False)
        mocker.patch('routes.payment_vault._reject_stale_webhook_timestamp', return_value=None)
        mocker.patch('utils.nowpayments_ipn.resolve_nowpayments_ipn_secret', return_value='sec')
        mocker.patch(
            'services.webhook_service.WebhookService.verify_nowpayments_signature',
            return_value=True,
        )
        mocker.patch(
            'services.webhook_service.WebhookService.process_nowpayments_webhook',
            return_value={'success': False},
        )
        mocker.patch('routes.payment_vault.PaymentLog.log_action')
        resp = vault_owner_client.post(
            '/payment-vault/webhook/nowpayments',
            data=self.NP_PAYLOAD,
            content_type='application/json',
            headers={'x-nowpayments-sig': 'sig'},
        )
        assert resp.status_code == 400

    def test_stripe_no_vault_returns_503(self, vault_owner_client, mocker):
        mocker.patch('routes.payment_vault._get_vault_for_current_tenant', return_value=None)
        mocker.patch('routes.payment_vault._is_duplicate_webhook', return_value=False)
        mocker.patch('routes.payment_vault._reject_stale_webhook_timestamp', return_value=None)
        resp = vault_owner_client.post(
            '/payment-vault/webhook/stripe',
            data=self.STRIPE_PAYLOAD,
            content_type='application/json',
            headers={'Stripe-Signature': 'sig'},
        )
        assert resp.status_code == 503

    def test_stripe_duplicate_webhook(self, vault_owner_client, mock_unlocked_vault, mocker):
        mocker.patch('routes.payment_vault._is_duplicate_webhook', return_value=True)
        mocker.patch('routes.payment_vault._reject_stale_webhook_timestamp', return_value=None)
        mocker.patch(
            'services.webhook_service.WebhookService.verify_stripe_signature',
            return_value=True,
        )
        resp = vault_owner_client.post(
            '/payment-vault/webhook/stripe',
            data=self.STRIPE_PAYLOAD,
            content_type='application/json',
            headers={'Stripe-Signature': 'sig'},
        )
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'duplicate'


class TestPublicApiErrorPaths:
    PURCHASE = '/payment-vault/api/purchase'
    DONATION = '/payment-vault/api/donation'
    PURCHASE_DATA = {
        'package_id': 1,
        'customer_name': 'Ali',
        'customer_email': 'ali@test.com',
        'payment_method': 'crypto',
        'amount_paid': 100,
    }
    DONATION_DATA = {'amount': 50, 'payment_method': 'crypto', 'crypto_type': 'btc'}

    @pytest.fixture(autouse=True)
    def _api_key_ok(self, mocker):
        mocker.patch('routes.payment_vault._validate_api_key', return_value=None)
        mocker.patch('routes.payment_vault._check_idempotency_key', return_value=None)

    def test_purchase_rejects_untrusted_origin(self, vault_owner_client, app_factory, mocker):
        mocker.patch(
            'routes.payment_vault._payment_vault_trusted_origins',
            return_value=frozenset({'http://localhost:5000'}),
        )
        resp = vault_owner_client.post(
            self.PURCHASE,
            json=self.PURCHASE_DATA,
            headers={'Origin': 'https://evil.example'},
        )
        assert resp.status_code == 403

    def test_purchase_not_json_returns_400(self, vault_owner_client, mocker):
        mocker.patch('routes.payment_vault._validate_public_api_origin', return_value=None)
        resp = vault_owner_client.post(
            self.PURCHASE,
            data='not-json',
            content_type='text/plain',
        )
        assert resp.status_code == 400

    def test_purchase_missing_package_returns_404(self, vault_owner_client, mocker):
        mocker.patch('routes.payment_vault._validate_public_api_origin', return_value=None)
        mocker.patch('routes.payment_vault.db.session.get', return_value=None)
        resp = vault_owner_client.post(self.PURCHASE, json=self.PURCHASE_DATA)
        assert resp.status_code == 404

    def test_purchase_crypto_nowpayments_success(self, vault_owner_client, mocker, mock_db):
        mocker.patch('routes.payment_vault._validate_public_api_origin', return_value=None)
        pkg = MagicMock(is_active=True, price=50, name_ar='Basic', slug='basic')
        mocker.patch('routes.payment_vault.db.session.get', return_value=pkg)
        mocker.patch('routes.payment_vault.LoggingCore.log_audit')
        don_q = MagicMock()
        don_q.filter_by.return_value.first.return_value = None
        mocker.patch('routes.payment_vault.Donation.query', don_q)
        np = mocker.patch('routes.payment_vault.NOWPaymentsService').return_value
        np.create_payment.return_value = {
            'success': True,
            'payment_id': 'np_99',
            'pay_address': 'addr',
            'pay_amount': 0.01,
            'invoice_url': 'https://pay.example/inv',
        }
        resp = vault_owner_client.post(self.PURCHASE, json=self.PURCHASE_DATA)
        assert resp.status_code == 201
        body = resp.get_json()
        assert body['success'] is True
        assert body['payment_address'] == 'addr'

    def test_donation_strips_invalid_email(self, vault_owner_client, mocker, mock_db):
        mocker.patch('routes.payment_vault._validate_public_api_origin', return_value=None)
        mocker.patch('routes.payment_vault.LoggingCore.log_audit')
        np = mocker.patch('routes.payment_vault.NOWPaymentsService').return_value
        np.create_payment.return_value = {'success': False}
        resp = vault_owner_client.post(
            self.DONATION,
            json={
                'amount': 50,
                'payment_method': 'crypto',
                'donor_email': 'not-an-email',
            },
        )
        assert resp.status_code == 201


class TestListFilterBranches:
    def test_donations_crypto_filter(self, vault_owner_client, mock_unlocked_vault, mocker):
        item = MagicMock()
        pag = MagicMock(items=[item], total=1, page=1, per_page=20, pages=1)
        q = MagicMock()
        q.filter_by.return_value = q
        q.filter.return_value = q
        q.order_by.return_value.paginate.return_value = pag
        q.filter.return_value.count.return_value = 0
        q.with_entities.return_value.scalar.return_value = 0
        mocker.patch('routes.payment_vault.Donation.query', q)
        resp = vault_owner_client.get('/payment-vault/donations?crypto=btc')
        assert resp.status_code == 200

    def test_v2_purchases_package_id_filter(self, vault_owner_client, mocker):
        q = MagicMock()
        q.filter_by.return_value = q
        q.filter.return_value = q
        q.order_by.return_value = q
        pag = MagicMock(
            items=[MagicMock(to_dict=MagicMock(return_value={'id': 1}))],
            page=1, per_page=20, total=1, pages=1,
            has_next=False, has_prev=False,
        )
        q.paginate.return_value = pag
        mocker.patch('routes.payment_vault.PackagePurchase.query', q)
        resp = vault_owner_client.get('/payment-vault/api/v2/purchases?package_id=3')
        assert resp.status_code == 200
        q.filter_by.assert_any_call(package_id=3)


class TestActivatePurchaseBranches:
    def test_activate_without_linked_donation(
        self, vault_owner_client, mock_unlocked_vault, mock_db, mocker,
    ):
        purchase = MagicMock(
            activation_status='pending',
            payment_status='pending',
            customer_email='solo@test.com',
        )
        _patch_purchase_query(mocker, get_or_404=purchase)
        don_q = MagicMock()
        don_q.filter_by.return_value.first.return_value = None
        mocker.patch('routes.payment_vault.Donation.query', don_q)
        resp = vault_owner_client.post('/payment-vault/purchase/1/activate', follow_redirects=False)
        assert resp.status_code == 302
        assert purchase.activation_status == 'activated'
