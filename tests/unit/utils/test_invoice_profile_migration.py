"""The profile backfill must never guess between tenants or overwrite data."""

import importlib
from types import SimpleNamespace

from sqlalchemy import Boolean, Column, Integer, MetaData, String, Table, create_engine, select


def test_backfill_preserves_profiles_and_skips_ambiguous_settings(monkeypatch):
    migration = importlib.import_module("migrations.versions.2f8a0b4c9d31_copy_invoice_profile_settings")
    metadata = MetaData()
    tenants = Table(
        "tenants",
        metadata,
        Column("id", Integer, primary_key=True),
        *(Column(target, String) for target, _ in migration._FIELDS),
    )
    settings = Table(
        "invoice_settings",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("tenant_id", Integer),
        Column("is_active", Boolean),
        *(Column(source, String) for _, source in migration._FIELDS),
    )
    engine = create_engine("sqlite://")
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            tenants.insert(),
            [
                {"id": 1, "bank_name": None},
                {"id": 2, "bank_name": "Profile bank"},
                {"id": 3, "bank_name": None},
                {"id": 4, "bank_name": None},
            ],
        )
        connection.execute(
            settings.insert(),
            [
                {"id": 1, "tenant_id": 1, "is_active": True, "bank_name": "A bank", "footer_text_ar": "A footer"},
                {"id": 2, "tenant_id": 1, "is_active": False, "bank_name": "Old bank", "footer_text_ar": "Old"},
                {"id": 3, "tenant_id": 2, "is_active": True, "bank_name": "B bank", "footer_text_ar": "B footer"},
                {"id": 4, "tenant_id": 3, "is_active": True, "bank_name": "First", "footer_text_ar": "First"},
                {"id": 5, "tenant_id": 3, "is_active": True, "bank_name": "Second", "footer_text_ar": "Second"},
            ],
        )
        monkeypatch.setattr(migration, "op", SimpleNamespace(get_bind=lambda: connection))
        migration.upgrade()
        migration.upgrade()  # safe to retry

        rows = {row.id: row for row in connection.execute(select(tenants)).all()}
        assert rows[1].bank_name == "A bank"
        assert rows[1].footer_invoice_text_ar == "A footer"
        assert rows[2].bank_name == "Profile bank"
        assert rows[2].footer_invoice_text_ar == "B footer"
        assert rows[3].bank_name is None
        assert rows[3].footer_invoice_text_ar is None
        assert rows[4].bank_name is None
        assert connection.execute(select(settings.c.bank_name).where(settings.c.id == 3)).scalar_one() == "B bank"
    engine.dispose()
