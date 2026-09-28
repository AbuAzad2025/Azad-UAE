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
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Any, cast

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
        try:
            path = root / rel
        except (TypeError, ValueError) as exc:
            # A malformed entry raises before any syscall. pathlib raises
            # ValueError for an embedded null character rather than the OSError
            # a real mkdir failure produces, so both are handled here - the
            # contract is that this function never propagates.
            current_app.logger.warning("bootstrap: unusable storage path %r: %s", rel, exc)
            continue
        try:
            path.mkdir(parents=True, exist_ok=True)
        except (OSError, ValueError) as exc:
            # ValueError, not just OSError: pathlib defers path validation until
            # the syscall, so an embedded null character surfaces from mkdir()
            # rather than from the constructor above.
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
    if _truthy(os.environ.get("SKIP_SYSTEM_INTEGRITY")) or _is_migration_command():
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

    Every set lands in exactly one bucket, and the buckets mean what they say:

    ``satisfied``
        An expectation is declared, the probe ran, and the comparison passed.
    ``violated``
        An expectation is declared, the probe ran, and the comparison failed.
        Logged at WARNING - this is an under-seeded or corrupted install.
    ``unmeasured``
        The probe ran but no ``expected`` is declared, so the number is
        reported for a human and deliberately *not* called healthy. This bucket
        did not exist before; "no expectation" used to be folded into
        ``satisfied``, which meant a probe could run, its result be thrown away
        and the set still be reported as fine.
    ``no_probe``
        No ``verify`` callable is declared, so nothing was measured. A set with
        ``seeder=None`` *and* no probe is skipped entirely rather than reported
        here, because nothing about it is knowable from the database.
    ``unrunnable``
        The probe raised. Logged at WARNING, not debug: on a real PostgreSQL
        install this is the signature of a missing or partial schema, and at
        debug level it was invisible in production.
    ``broken_probe``
        The manifest points at a dotted path that does not resolve. That is a
        bug in the manifest itself and is logged at ERROR.
    """
    from utils.seed_manifest import ALL_SEED_SETS

    if _truthy(os.environ.get("SKIP_SYSTEM_INTEGRITY")) or _is_migration_command():
        # During `flask db upgrade` the schema is mid-build: probing it would
        # report every set as unmeasurable, which is noise that looks like a
        # seeding failure. The post-migration boot is where this is measured.
        return

    satisfied: list[str] = []
    violated: list[str] = []
    unmeasured: list[str] = []
    no_probe: list[str] = []
    unrunnable: list[str] = []
    broken_probe: list[str] = []

    for seed_set in ALL_SEED_SETS:
        if seed_set.verify is None:
            if seed_set.seeder is None:
                # Deliberate, or created by a human. Nothing to measure and
                # nothing to judge.
                continue
            no_probe.append(seed_set.key)
            continue
        probe = _resolve(seed_set.verify)
        if probe is None:
            broken_probe.append(seed_set.key)
            continue
        try:
            actual = probe()
        except Exception as exc:
            current_app.logger.warning(
                "seed-manifest: probe for %s could not run: %s", seed_set.key, exc, exc_info=True
            )
            unrunnable.append(seed_set.key)
            continue

        if seed_set.expected is None:
            # Measured, but nothing to judge it against. Report the number and
            # leave the verdict to a human instead of inventing one.
            unmeasured.append(f"{seed_set.key}={actual} (no expected declared)")
            continue

        has_tenants = True
        if seed_set.scope == "tenant":
            from utils.seed_manifest_probe import count_active_tenants

            try:
                has_tenants = count_active_tenants() > 0
            except Exception:  # pragma: no cover - defensive
                has_tenants = True

        bucket, detail = seed_set.verdict(actual, has_tenants=has_tenants)
        if bucket == "satisfied":
            satisfied.append(detail)
        elif bucket == "unmeasured":
            unmeasured.append(detail)
        else:
            violated.append(detail)

    current_app.logger.info(
        "seed-manifest: %d satisfied, %d VIOLATED, %d unmeasured, %d no-probe, %d probe-unrunnable, %d broken-probe",
        len(satisfied),
        len(violated),
        len(unmeasured),
        len(no_probe),
        len(unrunnable),
        len(broken_probe),
    )
    for item in unmeasured:
        current_app.logger.info("seed-manifest: unmeasured -> %s", item)
    for item in no_probe:
        current_app.logger.info("seed-manifest: no probe declared -> %s", item)
    for item in unrunnable:
        current_app.logger.warning("seed-manifest: NOT MEASURED (probe failed) -> %s", item)
    for item in violated:
        current_app.logger.warning("seed-manifest: VIOLATED -> %s", item)
    for item in broken_probe:
        current_app.logger.error("seed-manifest: manifest points at a missing probe -> %s", item)


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


@contextmanager
def _isolated_transaction(app: Any = None):
    """Run a read-only reporting step so a failure cannot poison the session.

    SQLAlchemy puts every statement in one session-level transaction, and
    PostgreSQL keeps a transaction failed the moment a statement errors, for
    good: every later command on that connection returns
    InFailedSqlTransaction until a ROLLBACK happens. A reporting step allowed to
    touch the database without its own transaction can therefore break work that
    has nothing to do with it - the failure that stopped ``flask db upgrade`` on
    a fresh database was exactly that.

    Rolls back on entry and on exit. On entry because the session may already
    be poisoned by whatever ran before this step - clearing that is the whole
    point - and on exit so this step cannot poison what runs next. Both are only
    read-only steps, so there is never anything to keep.
    """
    from sqlalchemy.orm import Session

    from extensions import db

    session = cast("Session", db.session)

    def _clear() -> None:
        try:
            if session.get_transaction() is not None:
                session.rollback()
        except Exception as exc:  # pragma: no cover - defensive
            # Deliberately not current_app.logger: this can run before an app
            # context is pushed, and raising from the handler would mask the
            # failure we were trying to report.
            if app is not None:
                app.logger.debug("bootstrap: rollback around integrity step failed: %s", exc)

    _clear()
    try:
        yield
    finally:
        _clear()


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
    if _truthy(os.environ.get("SKIP_BOOT_PROVISIONING")):
        app.logger.info("bootstrap: skipped (SKIP_BOOT_PROVISIONING set)")
        return

    # Integrity is a *report* of the state of the database, but it is the first
    # thing that touches it. On a brand-new database that aborts the shared
    # transaction and every later step - including the very migration this
    # command exists to run - fails with InFailedSqlTransaction. Probes that
    # legitimately cannot run (no tenant yet, table mid-migration) must not be
    # able to do that, so the verification is isolated in its own transaction
    # and rolled back on any failure.
    integrity_labels = {"credentials", "seed-manifest"}

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
            isolate = label in integrity_labels
            context = _isolated_transaction(app) if isolate else nullcontext()
            try:
                with context:
                    step()
            except Exception as exc:  # pragma: no cover - defensive
                app.logger.error("bootstrap: %s step failed: %s", label, exc, exc_info=True)
