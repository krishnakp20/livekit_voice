from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import settings
from app.db.base import Base
import app.db.models  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL_SYNC)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = create_engine(settings.DATABASE_URL_SYNC, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
