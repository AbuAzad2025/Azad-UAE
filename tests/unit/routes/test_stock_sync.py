"""Unit tests for the external POS stock-sync engine."""

import uuid

import pytest


@pytest.fixture
def app():
    import os

    prev_db = os.environ.get("DATABASE_URL")
    os.environ["FLASK_ENV"] = "testing"
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    from app.factory import create_app

    _app = create_app()
    with _app.app_context():
        from extensions import db

        db.create_all()
        yield _app
    if prev_db is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = prev_db


@pytest.fixture
def client(app):
    return app.test_client()


class TestApiKeyDecorator:
    def test_missing_headers(self, client):
        rv = client.post("/api/v2/stock/sync")
        assert rv.status_code == 401
        assert rv.get_json()["error"] == "Missing API credentials"

    def test_invalid_key(self, client):
        rv = client.post(
            "/api/v2/stock/sync",
            headers={"X-API-Key": "bad", "X-API-Secret": "bad"},
        )
        assert rv.status_code == 403
        assert rv.get_json()["error"] == "Invalid or inactive API key"


class TestStockSyncService:
    def test_process_payload_missing_idempotency(self, app):
        from services.stock_sync_service import StockSyncService

        with app.app_context(), pytest.raises(ValueError, match="idempotency_key is required"):
            StockSyncService.process_sync_payload({"movements": []})

    def test_process_payload_missing_tenant_id(self, app):
        from services.stock_sync_service import StockSyncService

        with app.app_context(), pytest.raises(ValueError, match="tenant_id is required"):
            StockSyncService.process_sync_payload({"idempotency_key": "k1", "movements": []})

    def test_idempotency_caching(self, app, client):
        import uuid

        from extensions import db
        from models import SyncBatch, Tenant

        with app.app_context():
            uniq = str(uuid.uuid4())[:8]
            tenant = Tenant(
                name=f"SyncTest {uniq}",
                name_ar=f"اختبار {uniq}",
                slug=f"sync-test-{uniq}",
                email=f"sync{uniq}@test.local",
                phone_1="0500000000",
                country="AE",
                subscription_plan="basic",
                default_currency="AED",
                base_currency="AED",
            )
            db.session.add(tenant)
            db.session.flush()

            # Seed a completed batch
            batch = SyncBatch(
                tenant_id=tenant.id,
                idempotency_key=f"cached-key-{uniq}",
                status="completed",
            )
            db.session.add(batch)
            db.session.commit()

            # Subsequent call should hit cache
            from services.stock_sync_service import StockSyncService

            result = StockSyncService.process_sync_payload(
                {
                    "idempotency_key": f"cached-key-{uniq}",
                    "tenant_id": tenant.id,
                    "movements": [],
                }
            )
            assert result["cached"] is True
            assert result["status"] == "completed"


# ── Route-level HTTP contract (auth + status mapping) ────────────────────────


@pytest.fixture
def api_credentials(app):
    """An active tenant with a write-scoped API key, persisted for the
    @api_key_required decorator to authenticate against."""
    from extensions import db
    from models import APIKey, Tenant

    uniq = uuid.uuid4().hex[:8]
    tenant = Tenant(
        name=f"SyncRoute {uniq}",
        name_ar="مزامنة",
        slug=f"sync-route-{uniq}",
        email=f"syncroute{uniq}@test.local",
        phone_1="0500000000",
        country="AE",
        subscription_plan="basic",
        default_currency="AED",
        base_currency="AED",
    )
    db.session.add(tenant)
    db.session.flush()

    key = APIKey(
        name=f"pos-sync-{uniq}",
        key=f"key-{uuid.uuid4().hex}",
        secret=f"secret-{uuid.uuid4().hex}",
        service="external_pos",
        scope="write",
        is_active=True,
        tenant_id=tenant.id,
    )
    db.session.add(key)
    db.session.commit()
    return {"tenant": tenant, "headers": {"X-API-Key": key.key, "X-API-Secret": key.secret}}


class TestSyncStockRoute:
    def test_empty_payload_rejected_400(self, client, api_credentials):
        rv = client.post("/api/v2/stock/sync", json={}, headers=api_credentials["headers"])
        assert rv.status_code == 400
        body = rv.get_json()
        assert body["success"] is False
        assert body["message"] == "Empty payload"

    def test_missing_body_treated_as_empty_payload(self, client, api_credentials):
        rv = client.post(
            "/api/v2/stock/sync",
            data="",
            headers={**api_credentials["headers"], "Content-Type": "application/json"},
        )
        assert rv.status_code == 400
        assert rv.get_json()["message"] == "Empty payload"

    def test_value_error_maps_to_422(self, client, api_credentials):
        from unittest.mock import patch

        with patch(
            "routes.stock_sync.StockSyncService.process_sync_payload",
            side_effect=ValueError("Product not found: sku=GHOST"),
        ):
            rv = client.post(
                "/api/v2/stock/sync",
                json={"idempotency_key": "k", "tenant_id": 1},
                headers=api_credentials["headers"],
            )
        assert rv.status_code == 422
        body = rv.get_json()
        assert body["success"] is False
        assert "Product not found" in body["message"]

    def test_unexpected_error_maps_to_generic_500(self, client, api_credentials):
        from unittest.mock import patch

        with patch(
            "routes.stock_sync.StockSyncService.process_sync_payload",
            side_effect=RuntimeError("db on fire"),
        ):
            rv = client.post(
                "/api/v2/stock/sync",
                json={"idempotency_key": "k", "tenant_id": 1, "movements": []},
                headers=api_credentials["headers"],
            )
        assert rv.status_code == 500
        body = rv.get_json()
        # Internal details must never leak to the client.
        assert body["message"] == "Sync processing failed"
        assert "db on fire" not in rv.get_data(as_text=True)

    def test_cached_result_maps_to_409(self, client, api_credentials):
        from unittest.mock import patch

        cached = {"ok": True, "batch_id": 9, "status": "completed", "cached": True, "movements": []}
        with patch(
            "routes.stock_sync.StockSyncService.process_sync_payload",
            return_value=cached,
        ) as svc:
            rv = client.post(
                "/api/v2/stock/sync",
                json={"idempotency_key": "k", "tenant_id": 1, "movements": []},
                headers=api_credentials["headers"],
            )
        assert rv.status_code == 409
        body = rv.get_json()
        assert body["success"] is True
        assert body["data"]["cached"] is True
        assert body["data"]["batch_id"] == 9
        payload_sent = svc.call_args.args[0]
        assert payload_sent["idempotency_key"] == "k"

    def test_successful_sync_returns_200_with_result(self, client, api_credentials):
        from unittest.mock import patch

        result = {
            "ok": True,
            "batch_id": 3,
            "status": "completed",
            "cached": False,
            "movements": [{"movement_id": 11, "product_id": 5}],
        }
        with patch(
            "routes.stock_sync.StockSyncService.process_sync_payload",
            return_value=result,
        ):
            rv = client.post(
                "/api/v2/stock/sync",
                json={"idempotency_key": "k", "tenant_id": 1, "movements": [{"sku": "S"}]},
                headers=api_credentials["headers"],
            )
        assert rv.status_code == 200
        body = rv.get_json()
        assert body["success"] is True
        assert body["data"]["batch_id"] == 3
        assert body["data"]["movements"][0]["movement_id"] == 11


class TestSyncStatusRoute:
    def test_status_found_returns_200(self, client, api_credentials):
        from unittest.mock import patch

        status = {
            "batch_id": 7,
            "status": "completed",
            "idempotency_key": "abc",
            "payload_hash": "h" * 64,
            "processed_at": "2026-01-01T00:00:00+00:00",
            "error_message": None,
        }
        with patch("routes.stock_sync.StockSyncService.get_sync_status", return_value=status) as svc:
            rv = client.get("/api/v2/stock/sync/status/7", headers=api_credentials["headers"])
        assert rv.status_code == 200
        body = rv.get_json()
        assert body["success"] is True
        assert body["data"]["batch_id"] == 7
        assert body["data"]["status"] == "completed"
        svc.assert_called_once_with(7)

    def test_unknown_batch_returns_404(self, client, api_credentials):
        from unittest.mock import patch

        with patch("routes.stock_sync.StockSyncService.get_sync_status", return_value=None):
            rv = client.get("/api/v2/stock/sync/status/424242", headers=api_credentials["headers"])
        assert rv.status_code == 404
        assert rv.get_json()["message"] == "Batch not found"

    def test_read_only_key_cannot_write(self, app, client):
        from extensions import db
        from models import APIKey, Tenant

        uniq = uuid.uuid4().hex[:8]
        tenant = Tenant(
            name=f"ReadOnly {uniq}",
            name_ar="قراءة",
            slug=f"read-only-{uniq}",
            email=f"ro{uniq}@test.local",
            phone_1="0500000000",
            country="AE",
            subscription_plan="basic",
            default_currency="AED",
            base_currency="AED",
        )
        db.session.add(tenant)
        db.session.flush()
        key = APIKey(
            name="ro",
            key=f"ro-key-{uuid.uuid4().hex}",
            secret=f"ro-secret-{uuid.uuid4().hex}",
            service="external_pos",
            scope="read",
            is_active=True,
            tenant_id=tenant.id,
        )
        db.session.add(key)
        db.session.commit()

        headers = {"X-API-Key": key.key, "X-API-Secret": key.secret}
        rv = client.post("/api/v2/stock/sync", json={"x": 1}, headers=headers)
        assert rv.status_code == 403
        assert rv.get_json()["error"] == "Read-only API key"

    def test_platform_level_key_without_tenant_rejected(self, app, client):
        from extensions import db
        from models import APIKey

        key = APIKey(
            name="platform",
            key=f"plat-{uuid.uuid4().hex}",
            secret=f"plat-{uuid.uuid4().hex}",
            service="internal",
            scope="write",
            is_active=True,
            tenant_id=None,
        )
        db.session.add(key)
        db.session.commit()

        rv = client.post(
            "/api/v2/stock/sync",
            json={"x": 1},
            headers={"X-API-Key": key.key, "X-API-Secret": key.secret},
        )
        assert rv.status_code == 403
        assert rv.get_json()["error"] == "API key not bound to a tenant"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
