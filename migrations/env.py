from logging.config import fileConfig

from alembic import context

from app import models  # noqa: F401 - registra as tabelas em Base.metadata
from app.config import carregar_config
from app.db import Base, criar_engine

config = context.config

if config.config_file_name is not None and config.attributes.get('configurar_logging', True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def database_url():
    """URL passada explicitamente (ex.: testes, migrar()) ou a DATABASE_URL do ambiente."""
    return config.get_main_option('sqlalchemy.url') or carregar_config()['DATABASE_URL']


def run_migrations_offline() -> None:
    url = database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=url.startswith('sqlite'),
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = database_url()
    connectable = criar_engine(url)
    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                render_as_batch=url.startswith('sqlite'),
            )

            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
