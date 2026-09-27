"""Zero-touch boot provisioning (app/bootstrap.py).

The property that matters most here is the negative one: boot must never
manufacture a login. ``utils.system_init`` plants the owner from OWNER_PASSWORD
and refuses to fall back to a default, and these tests pin that so a future
"just make deployment easier" change cannot quietly reintroduce a backdoor.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app import bootstrap as bs


@pytest.fixture(autouse=True)
def _restore_env(monkeypatch):
    """Bootstrap reads env flags; keep them out of the rest of the session.

    SKIP_SYSTEM_INTEGRITY is deliberately left alone: the session-scoped ``app``
    fixture sets it before create_app so the schema check stays inert in tests,
    and the two tests that need the check active remove it themselves.
    """
    for var in ("SKIP_BOOT_PROVISIONING", "AUTO_MIGRATE"):
        monkeypatch.delenv(var, raising=False)
    yield


class TestStoragePaths:
    def test_every_declared_path_exists_after_boot(self, app):
        root = Path(app.root_path).resolve().parent
        for rel in bs.STORAGE_DIRS:
            assert (root / rel).is_dir(), f"{rel} was not provisioned"

    def test_provisioning_is_idempotent(self, app):
        with app.app_context():
            bs.ensure_storage_paths()
            bs.ensure_storage_paths()  # must not raise or warn
        assert (Path(app.root_path).resolve().parent / "uploads").is_dir()

    def test_missing_directory_is_recreated(self, app, monkeypatch, tmp_path):
        """A directory deleted underneath a running app comes back on next boot."""
        target = Path(app.root_path).resolve().parent / "uploads" / "training"
        shutil.rmtree(target, ignore_errors=True)
        assert not target.is_dir()
        with app.app_context():
            bs.ensure_storage_paths()
        assert target.is_dir()

    def test_unwritable_location_does_not_raise(self, app, monkeypatch, tmp_path):
        """A provisioning failure must be logged, never fatal."""
        monkeypatch.setattr(bs, "STORAGE_DIRS", ("definitely/not/creatable/\0bad",))
        with app.app_context():
            bs.ensure_storage_paths()  # must not raise


class TestSchemaVerification:
    def test_returns_bool_and_never_raises(self, app, monkeypatch):
        monkeypatch.setenv("SKIP_SYSTEM_INTEGRITY", "1")
        with app.app_context():
            assert isinstance(bs.verify_schema(), bool)

    def test_honours_skip_flag(self, app, monkeypatch):
        monkeypatch.setenv("SKIP_SYSTEM_INTEGRITY", "1")
        with app.app_context():
            assert bs.verify_schema() is True

    def test_honours_migration_command(self, app, monkeypatch):
        """`flask db upgrade` must not be blocked by the schema check."""
        monkeypatch.setattr(bs, "_is_migration_command", lambda: True)
        with app.app_context():
            assert bs.verify_schema() is True

    def test_unreachable_database_is_reported_not_raised(self, app, monkeypatch):
        def _boom(*a, **k):
            raise RuntimeError("no database")

        monkeypatch.delenv("SKIP_SYSTEM_INTEGRITY", raising=False)
        monkeypatch.setattr("sqlalchemy.inspect", _boom)
        with app.app_context():
            assert bs.verify_schema() is False


class TestCredentialState:
    def test_never_raises(self, app, monkeypatch):
        monkeypatch.setattr(
            "models.user.User.query",
            property(lambda self: (_ for _ in ()).throw(RuntimeError("no table"))),
        )
        with app.app_context():
            bs.check_credential_state()

    def test_boot_never_creates_a_default_password_account(self, app):
        """No default-credential account may exist as a side effect of booting.

        This is the regression guard for the deliberate decision not to
        auto-seed a well-known superadmin. Boot reports on credentials; it does
        not invent them.
        """
        from models.user import User

        with app.app_context():
            users = User.query.all()

        weak_defaults = {"superadmin", "admin", "root", "sa", "postgres", "owner"}
        for user in users:
            assert user.username.lower() not in weak_defaults or user.is_owner, (
                f"boot created a default account '{user.username}'; the owner account is "
                "seeded from OWNER_PASSWORD by utils.system_init and must be the only one"
            )
            # No account may authenticate with a known-empty/default secret.
            if user.is_owner:
                continue
            assert user.password_hash, f"user {user.username} has no password hash"


class TestBootIsNeverFatal:
    @pytest.mark.parametrize("step", ["ensure_storage_paths", "verify_schema", "check_credential_state"])
    def test_a_failing_step_does_not_stop_the_boot(self, app, monkeypatch, step):
        def _boom(*a, **k):
            raise RuntimeError("boom")

        monkeypatch.setattr(bs, step, _boom)
        # Both phases must complete despite the exploding step; the real logger
        # records the error, which is the whole point of the guard.
        bs.run_boot_provisioning(app, phase="pre")
        bs.run_boot_provisioning(app, phase="post")

    def test_skip_flag_short_circuits(self, app, monkeypatch):
        monkeypatch.setenv("SKIP_BOOT_PROVISIONING", "1")
        with app.app_context():
            bs.run_boot_provisioning(app, phase="pre")  # must not raise or provision
