from unittest.mock import patch


class TestPaymentCallbackIPWhitelist:
    def test_payment_callback_rejects_non_whitelisted_ip(self, client):
        with patch('routes.auth._is_nowpayments_ip', return_value=False):
            resp = client.post(
                '/auth/payment/callback',
                json={'payment_id': '123'},
                headers={'x-nowpayments-sig': 'fake'},
            )
            assert resp.status_code == 403
            assert resp.get_json()['error'] == 'غير مصرح'


class TestPaymentCallbackDuplicate:
    def test_payment_callback_rejects_duplicate(self, client):
        from datetime import datetime, timezone
        from routes.auth import _payment_callback_cache
        _payment_callback_cache['123:finished'] = datetime.now(timezone.utc).timestamp()

        try:
            with patch('routes.auth._is_nowpayments_ip', return_value=True):
                resp = client.post(
                    '/auth/payment/callback',
                    json={'payment_id': '123', 'payment_status': 'finished'},
                    headers={'x-nowpayments-sig': 'valid'},
                )
                assert resp.status_code == 200
                assert resp.get_json()['status'] == 'already_processed'
        finally:
            _payment_callback_cache.pop('123:finished', None)
