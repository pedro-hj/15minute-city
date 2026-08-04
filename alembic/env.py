from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from fifteen_minute_city.db.connection import get_database_url
from fifteen_minute_city.db.models import Base

# Alembic Config object, which provides access to the values within the .ini file in use.
config = context.config

# Dynamically set sqlalchemy.url from normalized environment variable
try:
    database_url = get_database_url()
    if database_url:
        config.set_main_option("sqlalchemy.url", database_url)
except ValueError:
    pass

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set target metadata for autogenerate support
target_metadata = Base.metadata


def include_object(object, name, type_, reflected, compare_to):
    """Filter out PostGIS system tables like spatial_ref_sys from autogenerate."""
    if type_ == "table" and name in ["spatial_ref_sys", "layer", "topology"]:
        return False
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
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
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
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
