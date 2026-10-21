"""Tenant module feature flags - the switches dynamic GL provisioning reads.

``services/gl_provisioning_service.py`` provisions a tenant's GL concept
mappings per module, and every non-core module is gated on a tenant feature
flag that is read off the tenant with ``getattr(tenant, flag, False)``::

    for mod in GL_MODULE_DEFINITIONS.values():
        if not mod.required:
            flag = mod.feature_flag
            if flag and not getattr(tenant, flag, False):
                continue

A flag that has no column on the ``tenants`` table is therefore always False,
the module is never provisioned, and under the production default
(``ENABLE_DYNAMIC_GL_MAPPING=True``) the concepts that module owns have no
mapping row - so the posting that needs one of them is refused outright.

Eight of those flags had no column at all. These tests pin the fix:

* the eight columns exist on the model and in the migrated schema, as
  non-null booleans that default to true;
* a tenant created through the ORM and a row inserted outside the ORM end up
  with the same values - which only holds when the model's declared default
  and the migration's server default agree;
* the migration is attached to the previous head and is reversible.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa

from extensions import db

MIGRATION_MODULE = "migrations.versions.5e2b8f4a6c13_add_tenant_module_feature_flags"

MIGRATION_REVISION = "5e2b8f4a6c13"
MIGRATION_DOWN_REVISION = "b7e1c4a9d305"

MODULE_FLAGS = (
    "enable_shipments",
    "enable_campaigns",
    "enable_partners",
    "enable_fixed_assets",
    "enable_donations",
    "enable_warranty_tracking",
    "enable_bank_reconciliation",
    "enable_azad_platform",
)

_TRUE_WORDS = frozenset({"1", "true", "t", "yes", "on"})
_FALSE_WORDS = frozenset({"0", "false", "f", "no", "off"})


def _as_bool(default_text) -> bool | None:
    """Normalise a server-default expression to a Python bool.

    The model declares the default as the string ``"1"`` and PostgreSQL stores
    the same default as ``true``; the two are the same value, so they are
    compared as booleans rather than as text.
    """
    if default_text is None:
        return None
    text = str(default_text).strip().strip("'").lower()
    if text in _TRUE_WORDS:
        return True
    if text in _FALSE_WORDS:
        return False
    return None


def _migration_module():
    return __import__(MIGRATION_MODULE, fromlist=["COLUMNS"])


def _make_tenant(db_session, prefix: str):
    from models.tenant import Tenant

    unique = uuid.uuid4().hex[:8]
    tenant = Tenant(
        name=f"{prefix} {unique}",
        name_ar="مستأجر تجريبي",
        slug=f"{prefix}-{unique}",
        country="AE",
        subscription_plan="basic",
        default_currency="AED",
        base_currency="AED",
    )
    db_session.add(tenant)
    db_session.flush()
    db_session.refresh(tenant)
    return tenant


class TestModuleFlagColumns:
    """The model side: the columns exist, and they are non-null booleans."""

    @pytest.mark.parametrize("flag", MODULE_FLAGS)
    def test_column_exists_on_the_model(self, flag):
        from models.tenant import Tenant

        columns = Tenant.__table__.columns
        assert flag in columns, (
            f"Tenant has no {flag} column, so getattr(tenant, {flag!r}, False) is always "
            "False and the module that owns it is never provisioned."
        )
        column = columns[flag]
        assert isinstance(column.type, sa.Boolean)
        assert column.nullable is False

    @pytest.mark.parametrize("flag", MODULE_FLAGS)
    def test_column_defaults_to_true_on_the_model(self, flag):
        from models.tenant import Tenant

        column = Tenant.__table__.columns[flag]
        assert column.default is not None
        assert column.default.arg is True
        assert column.server_default is not None
        assert _as_bool(column.server_default.arg) is True


class TestModuleFlagBehaviour:
    """The behaviour: a new tenant has every module switched on, and can
    deliberately switch one off."""

    def test_a_new_tenant_has_every_module_flag_enabled(self, db_session):
        tenant = _make_tenant(db_session, "Flag Probe")
        for flag in MODULE_FLAGS:
            assert getattr(tenant, flag) is True, f"{flag} did not default to True"

    def test_a_module_flag_can_be_switched_off(self, db_session):
        tenant = _make_tenant(db_session, "Flag Off Probe")
        tenant.enable_shipments = False
        db_session.flush()
        db_session.refresh(tenant)
        assert tenant.enable_shipments is False
        assert tenant.enable_campaigns is True


class TestMigratedSchema:
    """The schema side: the migrated ``tenants`` table carries the columns."""

    def test_migrated_schema_has_the_module_flag_columns(self, app, db_session):
        live = {c["name"]: c for c in sa.inspect(db.engine).get_columns("tenants")}
        for flag in MODULE_FLAGS:
            column = live.get(flag)
            assert column is not None, f"the migrated tenants table has no {flag} column"
            assert isinstance(column["type"], sa.Boolean)
            assert column["nullable"] is False
            assert _as_bool(column["default"]) is True, f"{flag} has no default of true in the schema"

    def test_a_row_created_outside_the_orm_gets_the_same_defaults(self, db_session):
        """A row that never touches the ORM must land on the same values.

        The model sends its own Python-side default on an ORM insert, so only
        a raw INSERT can tell whether the *server* default agrees with it.
        """
        unique = uuid.uuid4().hex[:8]
        slug = f"raw-flag-probe-{unique}"
        db_session.execute(
            sa.text(
                "INSERT INTO tenants (name, name_ar, slug, prices_include_vat, is_active, created_at) "
                "VALUES (:name, :name_ar, :slug, false, true, :created_at)"
            ),
            {
                "name": f"Raw Flag Probe {unique}",
                "name_ar": "مستأجر تجريبي",
                "slug": slug,
                "created_at": datetime.now(UTC),
            },
        )
        row = db_session.execute(
            sa.text(f"SELECT {', '.join(MODULE_FLAGS)} FROM tenants WHERE slug = :slug"),
            {"slug": slug},
        ).fetchone()
        assert row is not None
        for flag, value in zip(MODULE_FLAGS, row, strict=True):
            assert value is True, f"{flag} came out as {value!r} for a row created outside the ORM"


class TestProvisioningGate:
    """The gate itself: every module flag has to be a real column.

    This is the defect the eight columns exist to remove, pinned as an
    invariant so a module added later cannot reintroduce it silently.
    """

    def test_every_gl_module_feature_flag_is_a_real_tenant_column(self):
        from models.gl_account_registry import GL_MODULE_DEFINITIONS
        from models.tenant import Tenant

        columns = set(Tenant.__table__.columns.keys())
        missing = {
            mod.module_code: mod.feature_flag
            for mod in GL_MODULE_DEFINITIONS.values()
            if mod.feature_flag and mod.feature_flag not in columns
        }
        assert not missing, (
            f"these GL modules name a feature flag that is not a column on Tenant: {missing}. "
            "getattr(tenant, flag, False) is always False for a flag with no column, so the "
            "module is never provisioned and its postings are refused under "
            "ENABLE_DYNAMIC_GL_MAPPING=True."
        )

    def test_every_flag_added_here_is_read_by_a_module(self):
        from models.gl_account_registry import GL_MODULE_DEFINITIONS

        flags = {mod.feature_flag for mod in GL_MODULE_DEFINITIONS.values() if mod.feature_flag}
        assert set(MODULE_FLAGS) <= flags, (
            f"these columns are not read by any GL module: {sorted(set(MODULE_FLAGS) - flags)}"
        )


class TestMigration:
    """The revision: attached to the previous head, matching the model, reversible."""

    def test_migration_is_attached_to_the_previous_head(self):
        module = _migration_module()
        assert module.revision == MIGRATION_REVISION
        assert module.down_revision == MIGRATION_DOWN_REVISION

    def test_migration_server_defaults_match_the_model(self):
        from models.tenant import Tenant

        module = _migration_module()
        declared = dict(module.COLUMNS)
        assert set(declared) == set(MODULE_FLAGS)
        for flag, default in declared.items():
            column = Tenant.__table__.columns[flag]
            assert column.server_default is not None
            assert column.server_default.arg == default, (
                f"{flag}: the model declares server_default={column.server_default.arg!r} but the "
                f"migration declares {default!r}"
            )
            assert _as_bool(default) is True

    def test_migration_round_trips_on_a_scratch_table(self, db_session, monkeypatch):
        """upgrade() adds the eight columns, downgrade() drops exactly those.

        The revision is run against a scratch table rather than ``tenants``
        itself: it is the same code path, but it takes no lock on a table the
        rest of the suite is reading. PostgreSQL DDL is transactional, so the
        scratch table disappears with the test's rollback.
        """
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        module = _migration_module()
        scratch = "tenants_flag_probe"
        monkeypatch.setattr(module, "TABLE", scratch)

        connection = db_session.connection()
        connection.execute(sa.text(f'DROP TABLE IF EXISTS "{scratch}"'))
        connection.execute(sa.text(f'CREATE TABLE "{scratch}" (id serial PRIMARY KEY)'))

        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()

        live = {c["name"]: c for c in sa.inspect(connection).get_columns(scratch)}
        for flag in MODULE_FLAGS:
            column = live.get(flag)
            assert column is not None, f"upgrade() did not add {flag}"
            assert column["nullable"] is False
            assert _as_bool(column["default"]) is True

        with Operations.context(MigrationContext.configure(connection)):
            module.downgrade()

        live = {c["name"]: c for c in sa.inspect(connection).get_columns(scratch)}
        for flag in MODULE_FLAGS:
            assert flag not in live, f"downgrade() did not drop {flag}"
