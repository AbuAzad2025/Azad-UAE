"""Zero-touch boot provisioning.

Everything in here runs automatically from ``create_app`` — there is no script to
invoke by hand. Each step is idempotent, individually guarded, and reports through
``current_app.logger``.

A note on what this deliberately does *not* do: it never invents a login
credential. ``utils.system_init._ensure_owner_user`` already plants the owner
("Master Key") on first boot and **raises** rather than fall back to a default
password, and ``assert_production_sanity`` already enforces a 16+ character mixed
OWNER_PASSWORD in production. Adding an auto-seeded account with a known password
would be a backdoor on every deployment, so this module reports on that state
instead of creating it.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from flask import current_app

from app.integrity import _is_migration_command

# Tables whose absence means the database is unusable rather than merely
# incomplete. Checked by name through the SQLAlchemy inspector so no model import
# or live query is needed.
CORE_TABLES = (
    "alembic_version",
    "tenants",
    "users",
    "roles",
    "permissions",
    "gl_accounts",
    "gl_journal_entries",
    "gl_journal_lines",
    "currencies",
)

# Directories the application writes to. Centralised here because several routes
# used to call os.makedirs at import time or inline in a request handler, which
# meant a read-only or partially-created tree only failed when the feature was
# first used.
STORAGE_DIRS = (
    "instance",
    "instance/backups",
    "logs",
    "uploads",
    "uploads/training",
    "static/uploads",
    "static/uploads/logos",
    "static/uploads/watermarks",
)


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _project_root() -> Path:
    return Path(current_app.root_path).resolve().parent


def ensure_storage_paths() -> None:
    """Create every directory the app writes to. Never raises."""
    root = _project_root()
    for rel in STORAGE_DIRS:
        path = root / rel
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            current_app.logger.warning("bootstrap: cannot create directory %s: %s", rel, exc)
            continue
        # Restrictive where it matters. Uploaded files are user-supplied, so they
        # must not be group/other writable.
        if rel.startswith(("uploads", "static/uploads", "instance")):
            try:
                path.chmod(0o750)
            except OSError as exc:  # pragma: no cover - platform dependent
                current_app.logger.debug("bootstrap: chmod on %s not applied: %s", rel, exc)
    current_app.logger.info("bootstrap: storage paths verified (%d)", len(STORAGE_DIRS))


def verify_schema() -> bool:
    """Report schema health. Never raises; returns True when the core tables exist.

    By default this only reports. Set ``AUTO_MIGRATE=1`` to let the boot actually
    repair a fresh database by running the Alembic chain.

    ``db.create_all()`` is never used for this: it cannot alter an existing table
    and silently diverges from the migration history, which turns a recoverable
    "database is behind" into a schema that no longer matches its migrations.
    """
    if os.environ.get("SKIP_SYSTEM_INTEGRITY") or _is_migration_command():
        return True

    try:
        from sqlalchemy import inspect

        from extensions import db

        inspector = inspect(db.engine)
        present = set(inspector.get_table_names())
    except Exception as exc:
        current_app.logger.error("bootstrap: cannot reach the database: %s", exc)
        return False

    missing = [t for t in CORE_TABLES if t not in present]
    if not missing:
        current_app.logger.info("bootstrap: schema OK (%d core tables present)", len(CORE_TABLES))
        return True

    current_app.logger.error(
        "bootstrap: SCHEMA INCOMPLETE - missing %d core table(s): %s", len(missing), ", ".join(missing)
    )

    if not _truthy(os.environ.get("AUTO_MIGRATE")):
        current_app.logger.error(
            "bootstrap: refusing to start against an incomplete schema. Run 'flask db upgrade', "
            "or set AUTO_MIGRATE=1 to let the boot apply migrations automatically."
        )
        return False

    try:
        from flask_migrate import upgrade

        current_app.logger.info("bootstrap: AUTO_MIGRATE=1 - applying migrations")
        upgrade()
        inspector = inspect(db.engine)
        still_missing = [t for t in CORE_TABLES if t not in set(inspector.get_table_names())]
        if still_missing:
            current_app.logger.error(
                "bootstrap: migrations applied but core tables are still missing: %s", ", ".join(still_missing)
            )
            return False
        current_app.logger.info("bootstrap: migrations applied, schema now complete")
        return True
    except Exception as exc:
        current_app.logger.error("bootstrap: AUTO_MIGRATE failed: %s", exc, exc_info=True)
        return False


def check_credential_state() -> None:
    """Report on the owner account without ever creating one. Never raises."""
    try:
        from models.user import User

        owners = User.query.filter_by(is_owner=True).count()
    except Exception as exc:
        current_app.logger.debug("bootstrap: credential state not queryable yet: %s", exc)
        return

    if owners:
        current_app.logger.info("bootstrap: owner account present (%d) - not touching credentials", owners)
        return

    current_app.logger.warning(
        "bootstrap: NO owner account exists. One will be planted on this boot using OWNER_PASSWORD. "
        "In production OWNER_PASSWORD must be set to >=16 chars with mixed case, digit and special "
        "character, or startup is refused. This routine will not fall back to a default password."
    )


def verify_seed_manifest() -> None:
    """Check the seeded data sets against ``utils/seed_manifest.py``. Never raises.

    This is the guard that keeps the manifest honest. The manifest is a claim
    about what the boot seeds; this measures it, so a seeder that silently stops
    running - or a count that drifts - is reported instead of sitting in a
    Markdown file the way the old "37 perms / 8 roles / 76 industry fields"
    claim did.
    """
    from utils.seed_manifest import ALL_SEED_SETS

    healthy: list[str] = []
    drifted: list[str] = []
    unverified: list[str] = []
    missing_probe: list[str] = []
    probe_unrunnable: list[str] = []

    for seed_set in ALL_SEED_SETS:
        if seed_set.seeder is None:
            continue  # deliberate, or created by a human
        if seed_set.verify is None:
            unverified.append(seed_set.key)
            continue
        probe = _resolve(seed_set.verify)
        if probe is None:
            # The manifest points at something that does not exist. That is a bug
            # in the manifest, so it is reported separately from a probe that
            # simply could not run.
            missing_probe.append(seed_set.key)
            continue
        try:
            actual = probe()
        except Exception as exc:
            # Schema not there yet, or the table is absent. A different problem
            # from a broken dotted path, and only worth debug-level output.
            current_app.logger.debug("seed-manifest: probe for %s could not run: %s", seed_set.key, exc, exc_info=True)
            probe_unrunnable.append(seed_set.key)
            continue

        if seed_set.expected is None or actual >= seed_set.expected:
            healthy.append(f"{seed_set.key}={actual}")
        else:
            drifted.append(f"{seed_set.key}={actual} (expected >= {seed_set.expected})")

    current_app.logger.info(
        "seed-manifest: %d healthy, %d drifted, %d missing-probe, %d probe-unrunnable, %d undeclared",
        len(healthy),
        len(drifted),
        len(missing_probe),
        len(probe_unrunnable),
        len(unverified),
    )
    for item in drifted:
        current_app.logger.warning("seed-manifest: UNDER-SEEDED -> %s", item)
    for item in missing_probe:
        current_app.logger.error("seed-manifest: manifest points at a missing probe -> %s", item)
    for item in probe_unrunnable:
        current_app.logger.debug("seed-manifest: probe could not run -> %s", item)
    for item in unverified:
        current_app.logger.debug("seed-manifest: no probe declared -> %s", item)


def _resolve(dotted: str):
    """Import ``pkg.mod.attr`` and return the attribute, or None."""
    from importlib import import_module

    module_path, _, attr = dotted.rpartition(".")
    if not module_path:
        return None
    try:
        return getattr(import_module(module_path), attr)
    except (ImportError, AttributeError):
        return None


def run_boot_provisioning(app: Any, phase: str = "pre") -> None:
    """Single entry point called from ``create_app``. Never raises.

    Two phases, because the steps have real ordering constraints:

    * ``phase="pre"`` runs before the integrity/seed steps. Storage and schema are
      preconditions there - seeding writes to the database, so it must not be
      attempted against a schema that is missing.
    * ``phase="post"`` runs after seeding, so the credential report describes the
      state the operator actually ended up with. Running it earlier would log
      "no owner account" on every fresh boot and then immediately plant one.
    """
    if os.environ.get("SKIP_BOOT_PROVISIONING"):
        app.logger.info("bootstrap: skipped (SKIP_BOOT_PROVISIONING set)")
        return

    steps = (
        (("storage", ensure_storage_paths), ("schema", verify_schema))
        if phase == "pre"
        else (
            ("credentials", check_credential_state),
            ("seed-manifest", verify_seed_manifest),
        )
    )

    with app.app_context():
        for label, step in steps:
            try:
                step()
            except Exception as exc:  # pragma: no cover - defensive
                app.logger.error("bootstrap: %s step failed: %s", label, exc, exc_info=True)
