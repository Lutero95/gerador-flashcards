"""Engine e sessão do SQLAlchemy, uma sessão por requisição."""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, scoped_session, sessionmaker


class Base(DeclarativeBase):
    pass


Session = scoped_session(sessionmaker(expire_on_commit=False))


def criar_engine(database_url):
    opcoes = {}
    if database_url.startswith('sqlite'):
        opcoes['connect_args'] = {'check_same_thread': False}
    else:
        # Serverless: conexões podem ser derrubadas entre invocações
        opcoes['pool_pre_ping'] = True
    return create_engine(database_url, **opcoes)


def migrar(database_url):
    """Aplica as migrações do Alembic até a última versão (equivale a `alembic upgrade head`)."""
    from alembic import command
    from alembic.config import Config

    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config = Config(os.path.join(raiz, 'alembic.ini'))
    config.set_main_option('script_location', os.path.join(raiz, 'migrations'))
    config.set_main_option('sqlalchemy.url', database_url.replace('%', '%%'))
    config.attributes['configurar_logging'] = False
    command.upgrade(config, 'head')


def init_app(app):
    engine = criar_engine(app.config['DATABASE_URL'])
    Session.configure(bind=engine)
    app.extensions['db_engine'] = engine

    @app.teardown_appcontext
    def remover_sessao(exc=None):
        if exc is not None:
            Session.rollback()
        Session.remove()
