"""Cov4: celery_tasks — schedule parse/no-op tasks/cache/abandoned-cart arcs.

Skipped-with-reason (need live infra / unsafe in test env): every task that
bootstraps a default-config app via ``create_app()`` —
run_inventory_reconciliation, send_invoice_email, auto_backup_database,
update_exchange_rates, train_neural_models, send_payment_reminders.
A bare ``create_app()`` uses development config (dev database + real
network/mail gateways), so executing them here would touch the dev DB and
external providers. They are not testable in isolation.
"""

from __future__ import annotations

from unittest.mock import patch

from services.celery_tasks import (
    _parse_backup_schedule,
    cleanup_old_cache,
    generate_monthly_report,
    send_abandoned_cart_reminders,
)


def test_parse_backup_schedule_branches():
    assert str(_parse_backup_schedule(None)) == str(_parse_backup_schedule(""))
    assert str(_parse_backup_schedule("bogus")) == str(_parse_backup_schedule("0 2 * * *"))
    parsed = _parse_backup_schedule("15 3 * * 1")
    assert parsed.minute == {15}
    assert parsed.hour == {3}
    assert parsed.day_of_week == {1}


def test_generate_monthly_report_noop():
    out = generate_monthly_report(1, 2026)
    assert out["success"] is False
    assert "ReportService" in out["error"]


def test_cleanup_old_cache_success_and_failure():
    assert cleanup_old_cache() == {"success": True, "message": "Cache cleared"}
    with patch("services.celery_tasks.cache.clear", side_effect=RuntimeError("redis down")):
        out = cleanup_old_cache()
        assert out == {"success": False, "error": "redis down"}


def test_abandoned_cart_no_carts_is_noop(db_session):
    assert send_abandoned_cart_reminders() is None


def test_abandoned_cart_first_reminder_skips_storeless(db_session, sample_tenant):
    from datetime import UTC, datetime, timedelta

    from models.shop_abandoned_cart import ShopAbandonedCart

    cart = ShopAbandonedCart(
        tenant_id=sample_tenant.id,
        created_at=datetime.now(UTC) - timedelta(hours=2),
        reminder_sent_at=None,
        recovered=False,
        reminder_count=0,
    )
    db_session.add(cart)
    db_session.flush()
    # store lookup: tenant has no store email configured path -> continue branch
    with patch("services.celery_tasks.StoreService.get_tenant_store", return_value=None):
        assert send_abandoned_cart_reminders() is None
    db_session.refresh(cart)
    assert cart.reminder_sent_at is None


def test_abandoned_cart_second_reminder_and_exception(db_session, sample_tenant):
    from datetime import UTC, datetime, timedelta

    from models.shop_abandoned_cart import ShopAbandonedCart

    cart = ShopAbandonedCart(
        tenant_id=sample_tenant.id,
        created_at=datetime.now(UTC) - timedelta(hours=30),
        reminder_sent_at=datetime.now(UTC) - timedelta(hours=26),
        recovered=False,
        reminder_count=1,
    )
    db_session.add(cart)
    db_session.flush()
    from types import SimpleNamespace

    store = SimpleNamespace(email="store@example.com")
    with patch("services.celery_tasks.StoreService.get_tenant_store", return_value=store):
        assert send_abandoned_cart_reminders() is None
    db_session.refresh(cart)
    assert cart.reminder_count == 2
    # exception path: store lookup blows up -> logged, loop continues
    with patch("services.celery_tasks.StoreService.get_tenant_store",
               side_effect=RuntimeError("boom")):
        assert send_abandoned_cart_reminders() is None
