"""Rotas de simulação de pagamento. Só registradas com APP_ENV=development (ver create_app)."""
from flask import Blueprint, current_app, jsonify

from app.db import Session
from app.pagamentos.servico import processar_notificacao

bp = Blueprint('dev', __name__, url_prefix='/dev')

ACOES = {'aprovar': 'approved', 'recusar': 'rejected', 'expirar': 'cancelled'}


@bp.route('/pagamentos/<provider_payment_id>/<acao>', methods=['POST'])
def simular_pagamento(provider_payment_id, acao):
    """Muda o Pix de teste "no provedor" e segue o mesmo caminho de uma notificação real."""
    provedor = current_app.extensions['pagamentos']
    if provedor is None or provedor.nome != 'fake' or acao not in ACOES:
        return jsonify({'erro': 'Não encontrado'}), 404
    if not provedor.simular(provider_payment_id, ACOES[acao]):
        return jsonify({'erro': 'Pagamento de teste não encontrado'}), 404

    processar_notificacao(provider_payment_id)
    Session.commit()
    return jsonify({'sucesso': True, 'status': ACOES[acao]})
