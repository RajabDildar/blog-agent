from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

from apps.api.config import get_settings
from apps.api.db.base import Base
# Import models to ensure they are registered with Base.metadata
import apps.api.db.models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_object(object, name, type_, reflected, compare_to):
    """
    Ensure Alembic only manages application tables.
    LangGraph checkpoint tables (checkpoint*, langgraph*) are managed separately
    by LangGraph setup and must never appear in Alembic migrations.
    """
    if type_ == "table" and (
        name.startswith("checkpoint")
        or name.startswith("langgraph")
    ):
        return False
    return True


def get_url():
    """Retrieve database URL from settings if not set in config."""
    db_url = config.get_main_option("sqlalchemy.url")
    if not db_url or "driver://user:pass@localhost/dbname" in db_url:
        return get_settings().DATABASE_URL
    return db_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
