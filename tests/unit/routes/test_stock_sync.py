"""Unit tests for the external POS stock-sync engine."""

import pytest


@pytest.fixture
def app():
    import os

    os.environ["FLASK_ENV"] = "testing"
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    from app.factory import create_app

    _app = create_app()
    with _app.app_context():
        from extensions import db

        db.create_all()
        yield _app


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

        with app.app_context():
            with pytest.raises(ValueError, match="idempotency_key is required"):
                StockSyncService.process_sync_payload({"movements": []})

    def test_process_payload_missing_tenant_id(self, app):
        from services.stock_sync_service import StockSyncService

        with app.app_context():
            with pytest.raises(ValueError, match="tenant_id is required"):
                StockSyncService.process_sync_payload({"idempotency_key": "k1", "movements": []})

    def test_idempotency_caching(self, app, client):
        from extensions import db
        from models import SyncBatch, Tenant
        import uuid

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
