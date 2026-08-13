from pathlib import Path
from alembic import command
from alembic.config import Config
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine
from app.db import Base
from app import models  # noqa: F401 — import registers all model classes on Base.metadata

BACKEND_DIR = Path(__file__).resolve().parent.parent

def test_alembic_upgrade_head_matches_current_models(tmp_path):
    db_path = tmp_path / "alembic_check.db"
    db_url = f"sqlite:///{db_path}"

    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    alembic_cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(db_url)
    with engine.connect() as conn:
        migration_context = MigrationContext.configure(conn)
        diff = compare_metadata(migration_context, Base.metadata)

    assert diff == [], f"schema drift between migrations and models: {diff}"
