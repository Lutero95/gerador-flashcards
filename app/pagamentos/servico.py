"""Regras de pagamento: criar Pix, aplicar o status do provedor ao pedido e sincronizar.

É o único caminho que muda um pedido por causa de pagamento: webhook, consulta (polling)
e os botões de simulação do modo de teste passam todos por aplicar_status().
"""
import logging
from datetime import timedelta

from flask import current_app
from sqlalchemy import select

from app.db import Session
from app.ia.geracao import apos_pagamento
from app.ia.material import apagar_remotos
from app.models import Pagamento, StatusPedido as S, agora
from app.pagamentos.fake import FakePaymentProvider
from app.pagamentos.mercadopago import MercadoPagoProvider
from app.pedidos import transicionar

logger = logging.getLogger('gerador_flashcards')

# Status do provedor que encerram um Pix sem pagamento
ENCERRADOS = {'cancelled', 'expired', 'rejected'}
# Status em que vale a pena perguntar ao provedor se algo mudou
A_CONSULTAR = {'pending', 'in_process', 'expired'}
# O Mercado Pago cancela o Pix no prazo; a consulta pode ainda ver "pending" por alguns instantes
GRACA_EXPIRACAO = timedelta(minutes=2)


def criar_provider_pagamento(config):
    """Instancia o provedor configurado, ou None se não houver credenciais (geração fica bloqueada)."""
    if config['PAYMENT_PROVIDER'] == 'fake':
        return FakePaymentProvider(config['PIX_EXPIRACAO_MIN'])
    if config['PAYMENT_PROVIDER'] == 'mercadopago' and config['MERCADOPAGO_ACCESS_TOKEN']:
        return MercadoPagoProvider(
            config['MERCADOPAGO_ACCESS_TOKEN'],
            webhook_secret=config['MERCADOPAGO_WEBHOOK_SECRET'],
            expiracao_min=config['PIX_EXPIRACAO_MIN'],
            url_publica=config['URL_PUBLICA'],
            aceitar_webhook_sem_segredo=config['APP_ENV'] == 'development',
        )
    logger.warning('Nenhum provedor de pagamento configurado (PAYMENT_PROVIDER=%s)', config['PAYMENT_PROVIDER'])
    return None


def provedor():
    return current_app.extensions['pagamentos']


def pix_vigente(pedido):
    """O Pix ativo, se ainda puder ser pago; senão None."""
    pagamento = pedido.pagamento_ativo
    if pedido.status != S.AGUARDANDO_PAGAMENTO or pagamento is None or pagamento.status != 'pending':
        return None
    if pagamento.expira_em is not None and agora() >= pagamento.expira_em:
        return None
    return pagamento


def criar_pix(pedido):
    """Cria um novo Pix para o pedido (pedido.email e preco_centavos já definidos)."""
    tentativa = len(pedido.pagamentos) + 1
    idempotency_key = f'{pedido.id}-{tentativa}'
    resultado = provedor().criar_pix(pedido, idempotency_key)
    pagamento = Pagamento(
        provider=provedor().nome,
        provider_payment_id=resultado.provider_payment_id,
        status=resultado.status,
        valor_centavos=pedido.preco_centavos,
        qr_code=resultado.qr_code,
        qr_code_base64=resultado.qr_code_base64,
        ticket_url=resultado.ticket_url,
        expira_em=resultado.expira_em,
        idempotency_key=idempotency_key,
    )
    pedido.pagamentos.append(pagamento)
    transicionar(pedido, S.AGUARDANDO_PAGAMENTO)
    return pagamento


def aplicar_status(pagamento, situacao):
    """Aplica ao pagamento/pedido a situação informada pelo provedor. Idempotente."""
    pedido = pagamento.pedido

    if situacao.external_reference and situacao.external_reference != pedido.id:
        logger.error('Pagamento %s: external_reference %s não corresponde ao pedido %s',
                     pagamento.provider_payment_id, situacao.external_reference, pedido.id)
        return

    if situacao.status == 'approved':
        if pagamento.status in ('approved', 'divergente', 'refunded'):
            return  # já processado
        if situacao.valor_centavos is not None and situacao.valor_centavos != pagamento.valor_centavos:
            pagamento.status = 'divergente'
            logger.error('Pagamento %s aprovado com valor %s, esperado %s: pedido não liberado',
                         pagamento.provider_payment_id, situacao.valor_centavos, pagamento.valor_centavos)
            return
        if any(p is not pagamento and p.status == 'approved' for p in pedido.pagamentos):
            # Pedido já pago por outro Pix: devolve o dinheiro do segundo
            pagamento.status = 'approved'
            if provedor().reembolsar(pagamento.provider_payment_id):
                pagamento.status = 'refunded'
            logger.warning('Pagamento duplicado %s do pedido %s (reembolso: %s)',
                           pagamento.provider_payment_id, pedido.id, pagamento.status == 'refunded')
            return
        pagamento.status = 'approved'
        if pedido.status in (S.AGUARDANDO_PAGAMENTO, S.EXPIRADO):
            transicionar(pedido, S.PAGO)
            apos_pagamento(pedido)
        return

    anterior = pagamento.status
    pagamento.status = situacao.status

    if situacao.status in ENCERRADOS:
        if pagamento is pedido.pagamento_ativo and pedido.status == S.AGUARDANDO_PAGAMENTO:
            transicionar(pedido, S.EXPIRADO)
    elif situacao.status in ('refunded', 'charged_back') and anterior == 'approved':
        if pedido.status in (S.PAGO, S.GERANDO, S.CONCLUIDO, S.FALHOU):
            transicionar(pedido, S.REEMBOLSADO)
            apagar_remotos(current_app.extensions['ia'], pedido.referencias_arquivos)


def sincronizar(pedido):
    """Consulta o provedor sobre o Pix ativo e aplica o resultado (usado no polling da página)."""
    pagamento = pedido.pagamento_ativo
    if pedido.status not in (S.AGUARDANDO_PAGAMENTO, S.EXPIRADO) or pagamento is None or provedor() is None:
        return
    if pagamento.status in A_CONSULTAR:
        situacao = provedor().consultar(pagamento.provider_payment_id)
        if situacao:
            aplicar_status(pagamento, situacao)

    if (pedido.status == S.AGUARDANDO_PAGAMENTO and pagamento.status == 'pending'
            and pagamento.expira_em is not None and agora() > pagamento.expira_em + GRACA_EXPIRACAO):
        pagamento.status = 'expired'
        transicionar(pedido, S.EXPIRADO)
    Session.commit()


def pagamento_aprovado(pedido):
    return next((p for p in pedido.pagamentos if p.status == 'approved'), None)


def resolver_falha(pedido, opcao):
    """Pedido pago cuja geração falhou: 'total' devolve tudo; 'parcial' entrega os cards gerados e
    devolve a parte proporcional ao que faltou. Devolve False se o provedor recusar o reembolso."""
    pagamento = pagamento_aprovado(pedido)
    if opcao == 'total':
        valor = pagamento.valor_centavos
    else:
        faltam = max(0, pedido.quantidade_solicitada - len(pedido.cards))
        valor = round(pagamento.valor_centavos * faltam / pedido.quantidade_solicitada)

    if valor > 0 and not provedor().reembolsar(pagamento.provider_payment_id, None if opcao == 'total' else valor):
        return False

    pedido.reembolso_centavos = valor
    if opcao == 'total':
        pagamento.status = 'refunded'
        transicionar(pedido, S.REEMBOLSADO)
    else:
        transicionar(pedido, S.CONCLUIDO)
        pedido.expira_em = agora() + timedelta(days=current_app.config['DIAS_RETENCAO_PEDIDO'])
    logger.info('Pedido %s: falha resolvida com opção %s (reembolso de %d centavos)', pedido.id, opcao, valor)
    return True


def processar_notificacao(provider_payment_id):
    """Trata uma notificação já autenticada: nunca confia no corpo, sempre reconsulta o provedor."""
    pagamento = Session.scalar(select(Pagamento).where(Pagamento.provider_payment_id == str(provider_payment_id)))
    if pagamento is None:
        logger.warning('Notificação para pagamento desconhecido %s', provider_payment_id)
        return False
    situacao = provedor().consultar(pagamento.provider_payment_id)
    if situacao is None:
        return False
    aplicar_status(pagamento, situacao)
    return True
