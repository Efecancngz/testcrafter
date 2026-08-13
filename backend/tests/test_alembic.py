from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
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
    inspector = inspect(engine)
    migrated_tables = set(inspector.get_table_names()) - {"alembic_version"}
    model_tables = set(Base.metadata.tables.keys())

    assert migrated_tables == model_tables

    for table_name in model_tables:
        migrated_columns = {col["name"] for col in inspector.get_columns(table_name)}
        model_columns = {col.name for col in Base.metadata.tables[table_name].columns}
        assert migrated_columns == model_columns, f"column mismatch in {table_name}"
