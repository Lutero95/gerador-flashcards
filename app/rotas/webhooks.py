"""Notificações dos provedores de pagamento: autenticadas, idempotentes e sem confiar no corpo."""
import logging

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import Session
from app.erros import resposta_erro_interno
from app.models import EventoWebhook, Pagamento
from app.pagamentos.servico import processar_notificacao

logger = logging.getLogger('gerador_flashcards')

bp = Blueprint('webhooks', __name__)


# /webhook-mercadopago é o endereço antigo, mantido caso ainda esteja cadastrado no painel
@bp.route('/webhooks/mercadopago', methods=['POST'])
@bp.route('/webhook-mercadopago', methods=['POST'])
def webhook_mercadopago():
    provedor = current_app.extensions['pagamentos']
    if provedor is None or provedor.nome != 'mercadopago':
        return jsonify({'erro': 'Pagamentos não configurados'}), 503

    try:
        evento = provedor.validar_webhook(request.headers, request.args, request.get_data())
        if evento is None:
            logger.warning('Webhook rejeitado. X-Request-Id: %s', request.headers.get('x-request-id', ''))
            return jsonify({'erro': 'Assinatura inválida'}), 401

        if evento.provider_payment_id is None:
            return jsonify({'sucesso': True, 'ignorado': True}), 200

        ja_processado = Session.scalar(select(EventoWebhook).where(
            EventoWebhook.provider == provedor.nome, EventoWebhook.evento_id == evento.evento_id))
        if ja_processado is not None:
            return jsonify({'sucesso': True, 'duplicado': True}), 200

        conhecido = Session.scalar(select(Pagamento.id).where(
            Pagamento.provider_payment_id == evento.provider_payment_id)) is not None
        if conhecido and not processar_notificacao(evento.provider_payment_id):
            # Consulta ao provedor falhou: não registra o evento, para o Mercado Pago reenviar
            Session.rollback()
            return jsonify({'erro': 'Consulta ao provedor indisponível'}), 503

        Session.add(EventoWebhook(provider=provedor.nome, evento_id=evento.evento_id))
        try:
            Session.commit()
        except IntegrityError:
            Session.rollback()  # outra instância processou o mesmo evento ao mesmo tempo
        return jsonify({'sucesso': True}), 200

    except Exception:
        return resposta_erro_interno('Erro ao processar webhook.')
