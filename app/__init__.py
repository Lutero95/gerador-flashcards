"""Fábrica da aplicação: usada tanto na execução local (app.py) quanto na Vercel (api/index.py)."""
import hashlib
import logging
import os

from flask import Flask

from app import db, seguranca
from app.config import carregar_config
from app.ia.gemini import GeminiProvider
from app.pagamentos.servico import criar_provider_pagamento


def create_app(config=None):
    app = Flask(__name__)
    app.config.update(carregar_config())
    if config:
        app.config.update(config)

    logging.basicConfig(level=logging.INFO)

    db.init_app(app)
    seguranca.init_app(app)
    app.extensions['ia'] = GeminiProvider(app.config['GEMINI_API_KEY'])
    app.extensions['pagamentos'] = criar_provider_pagamento(app.config)

    app.config['VERSAO_ESTATICOS'] = versao_dos_estaticos(app.static_folder)

    @app.context_processor
    def dados_das_paginas():
        from app.precos import FAIXAS
        return {
            'faixas_preco': [{'ate': ate, 'centavos': centavos,
                              'texto': f'R$ {centavos // 100},{centavos % 100:02d}'} for ate, centavos in FAIXAS
                             if ate <= app.config['MAX_CARDS']],
            'max_cards': app.config['MAX_CARDS'],
            'contato_email': app.config['CONTATO_EMAIL'],
            'versao_estaticos': app.config['VERSAO_ESTATICOS'],
        }

    from app.rotas import api_pedidos, dev, paginas, tarefas, webhooks
    app.register_blueprint(paginas.bp)
    app.register_blueprint(api_pedidos.bp)
    app.register_blueprint(webhooks.bp)
    app.register_blueprint(tarefas.bp)
    if app.config['APP_ENV'] == 'development':
        app.register_blueprint(dev.bp)

    return app


def versao_dos_estaticos(pasta):
    """Hash do conteúdo de static/: muda a URL dos arquivos a cada deploy e evita cache velho no navegador."""
    resumo = hashlib.sha256()
    for raiz, _, arquivos in sorted(os.walk(pasta)):
        for nome in sorted(arquivos):
            with open(os.path.join(raiz, nome), 'rb') as f:
                resumo.update(f.read())
    return resumo.hexdigest()[:10]
