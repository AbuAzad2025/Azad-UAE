"""The profile backfill must never guess between tenants or overwrite data."""

import importlib
from types import SimpleNamespace

from sqlalchemy import Boolean, Column, Integer, MetaData, Numeric, String, Table, create_engine, select


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


def _overlay_test_tables(metadata, migration):
    tenants = Table(
        "tenants",
        metadata,
        Column("id", Integer, primary_key=True),
        *(Column(name, String) for name in migration._TEXT_BACKFILL),
        *(
            Column(
                name,
                Numeric(3, 2)
                if name == "watermark_opacity"
                else Boolean()
                if name.startswith(("show_", "enable_"))
                else String,
            )
            for name in migration._SCALAR_BACKFILL
        ),
        Column("footer_invoice_text_ar", String, nullable=True),
        Column("footer_invoice_text_en", String, nullable=True),
    )
    settings = Table(
        "invoice_settings",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("tenant_id", Integer),
        Column("is_active", Boolean),
        *(Column(source, String) for tenant_col, source in migration._TEXT_BACKFILL.items()),
        *(
            Column(
                source,
                Numeric(3, 2)
                if tenant_col == "watermark_opacity"
                else Boolean()
                if tenant_col.startswith(("show_", "enable_"))
                else String,
            )
            for tenant_col, source in migration._SCALAR_BACKFILL.items()
        ),
    )
    return tenants, settings


def test_overlay_backfill_combines_legacy_and_single_active_settings(monkeypatch):
    migration = importlib.import_module("migrations.versions.6a4b7c8d9e30_print_overlay_to_tenant")
    metadata = MetaData()
    tenants, settings = _overlay_test_tables(metadata, migration)
    engine = create_engine("sqlite://")
    metadata.create_all(engine)
    with engine.begin() as connection:
        blank = {c.name: None for c in tenants.columns}

        def _tenant_row(**values) -> dict:
            row = dict(blank)
            row.update(values)
            return row

        tenant_insert = [
            _tenant_row(id=1),
            _tenant_row(id=2, bank_name="Profile bank", footer_text_ar="tenant footer"),
            _tenant_row(id=3),
            _tenant_row(id=4),
            _tenant_row(id=5, footer_text_ar="", footer_invoice_text_ar="legacy footer"),
        ]
        connection.execute(tenants.insert(), tenant_insert)
        settings_blank = {c.name: None for c in settings.columns}

        def _settings_row(**values) -> dict:
            row = dict(settings_blank)
            row.update(values)
            return row

        settings_insert = [
            _settings_row(id=1, tenant_id=1, is_active=True, bank_name="Settings bank", footer_text_ar="s footer"),
            _settings_row(id=3, tenant_id=3, is_active=True, bank_name="First", footer_text_ar="First"),
            _settings_row(id=4, tenant_id=3, is_active=True, bank_name="Second", footer_text_ar="Second"),
            _settings_row(id=5, tenant_id=5, is_active=True, bank_name="Five", footer_text_ar="s footer 5"),
        ]
        connection.execute(settings.insert(), settings_insert)
        tenant_col_names = {c.name for c in tenants.columns}
        monkeypatch.setattr(migration, "op", SimpleNamespace(get_bind=lambda: connection))
        # DDL cannot run inside this mock; exercise the data movement directly.
        migration._legacy_footer_carry(connection, tenant_col_names)
        migration._backfill(connection)
        migration._legacy_footer_carry(connection, tenant_col_names)
        migration._backfill(connection)  # idempotent

        rows = {row.id: row for row in connection.execute(select(tenants)).all()}
        assert rows[1].bank_name == "Settings bank"
        assert rows[1].footer_text_ar == "s footer"
        assert rows[2].bank_name == "Profile bank"  # tenant value preserved
        assert rows[2].footer_text_ar == "tenant footer"  # tenant value preserved
        assert rows[3].bank_name is None  # ambiguous - untouched
        assert rows[3].footer_text_ar is None
        assert rows[4].bank_name is None  # no settings - untouched
        # Legacy alias overrides the empty snapshot field, not a populated one.
        assert rows[5].footer_text_ar == "legacy footer"
        assert rows[5].bank_name == "Five"
    engine.dispose()
