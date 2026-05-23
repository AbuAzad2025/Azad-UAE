from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.exc import NoSuchTableError


def _build_alembic_config() -> Config:
    project_root = Path(__file__).resolve().parent
    migrations_dir = project_root / "migrations"
    ini_path = migrations_dir / "alembic.ini"

    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(migrations_dir))
    return cfg


def _ensure_declared_indexes() -> tuple[int, int]:
    """Create any SQLAlchemy-declared indexes that are still missing."""
    from extensions import db

    engine = db.engine
    inspector = inspect(engine)

    checked = 0
    created = 0

    for table in db.metadata.tables.values():
        try:
            existing = {idx["name"] for idx in inspector.get_indexes(table.name)}
        except NoSuchTableError:
            continue
        for idx in table.indexes:
            checked += 1
            if idx.name in existing:
                continue
            idx.create(bind=engine, checkfirst=True)
            created += 1

    return checked, created


def run() -> None:
    import os
    os.environ.setdefault("APP_ENV", "development")
    os.environ.setdefault("DEBUG", "1")
    os.environ.setdefault("SKIP_SYSTEM_INTEGRITY", "1")

    from app import create_app
    from extensions import db

    app = create_app()
    with app.app_context():
        cfg = _build_alembic_config()

        # Single comprehensive schema migration to latest version.
        # If schema drift exists (manual column/index changes), stamp head safely.
        command.upgrade(cfg, "head")

        checked, created = _ensure_declared_indexes()
        print("MIGRATION_OK")
        print(f"INDEXES_CHECKED={checked}")
        print(f"INDEXES_CREATED={created}")


if __name__ == "__main__":
    run()
