import warnings
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.db.models import Base
from app.db.session import database_url

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata

# compare_server_default also makes Alembic compare the generated column chunks.tsv. It cannot alter one, and
# it warns on every run that this one differs, because its text comparison never matches the expression as
# PostgreSQL prints it (casts, extra parentheses). That warning carries no information and reads like drift.
warnings.filterwarnings("ignore", message=r"Computed default on chunks\.tsv cannot be modified")


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(database_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_server_default=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
