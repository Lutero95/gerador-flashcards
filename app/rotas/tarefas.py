"""Tarefas periódicas, chamadas pelo Cron da Vercel (vercel.json) com Authorization: Bearer <CRON_SECRET>."""
import hmac
import logging
from datetime import timedelta

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import delete, select

from app.db import Session
from app.ia.geracao import descartar_material
from app.models import ContadorRequisicao, CotaPrevia, Pedido, StatusPedido as S, agora
from app.pedidos import transicionar

logger = logging.getLogger('gerador_flashcards')

bp = Blueprint('tarefas', __name__)

NAO_PAGOS = (S.PREVIA_PRONTA, S.AGUARDANDO_PAGAMENTO, S.EXPIRADO)
ENCERRADOS = (S.CONCLUIDO, S.FALHOU, S.REEMBOLSADO)


def autorizado():
    segredo = current_app.config['CRON_SECRET']
    if not segredo:
        return current_app.config['APP_ENV'] == 'development'
    return hmac.compare_digest(request.headers.get('Authorization', ''), f'Bearer {segredo}')


def limpar():
    """Expira pedidos não pagos, descarta material do aluno e apaga contadores antigos."""
    cfg = current_app.config
    limite_nao_pago = agora() - timedelta(days=cfg['DIAS_PEDIDO_NAO_PAGO'])
    resultado = {'pedidos_expirados': 0, 'materiais_descartados': 0, 'rascunhos_abandonados': 0}

    for pedido in Session.scalars(select(Pedido).where(Pedido.status.in_(NAO_PAGOS),
                                                       Pedido.criado_em < limite_nao_pago)):
        if pedido.status != S.EXPIRADO:
            transicionar(pedido, S.EXPIRADO)
            resultado['pedidos_expirados'] += 1
        if pedido.material_texto or pedido.referencias_arquivos:
            descartar_material(pedido)
            pedido.referencias_arquivos = None
            resultado['materiais_descartados'] += 1

    # Rascunho parado há mais de um dia: a requisição da prévia morreu no meio
    for pedido in Session.scalars(select(Pedido).where(Pedido.status == S.RASCUNHO,
                                                       Pedido.criado_em < agora() - timedelta(days=1))):
        transicionar(pedido, S.FALHOU)
        descartar_material(pedido)
        resultado['rascunhos_abandonados'] += 1

    for pedido in Session.scalars(select(Pedido).where(Pedido.status.in_(ENCERRADOS),
                                                       Pedido.material_texto.is_not(None))):
        descartar_material(pedido)
        resultado['materiais_descartados'] += 1

    resultado['contadores_apagados'] = Session.execute(delete(ContadorRequisicao).where(
        ContadorRequisicao.janela < agora() - timedelta(days=1))).rowcount
    resultado['cotas_apagadas'] = Session.execute(delete(CotaPrevia).where(
        CotaPrevia.data < (agora() - timedelta(days=2)).date())).rowcount
    Session.commit()
    logger.info('Limpeza: %s', resultado)
    return resultado


@bp.route('/tarefas/limpeza', methods=['GET', 'POST'])
def limpeza():
    if not autorizado():
        return jsonify({'erro': 'Não encontrado'}), 404
    return jsonify(limpar())
