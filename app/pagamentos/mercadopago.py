"""Provedor Mercado Pago: Pix pela API /v1/payments e validação de webhook no formato x-signature."""
import hashlib
import hmac
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone

import mercadopago
from mercadopago.config import RequestOptions

from app.pagamentos.base import ErroPagamento, EventoValidado, ResultadoPix, StatusPagamento
from app.precos import centavos_para_reais

logger = logging.getLogger('gerador_flashcards')

# Notificações com ts mais antigo que isso são rejeitadas (proteção contra reenvio de notificação capturada)
TOLERANCIA_WEBHOOK_S = 10 * 60


def _para_utc_sem_fuso(texto):
    if not texto:
        return None
    try:
        return datetime.fromisoformat(texto).astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        return None


def montar_manifest(data_id, request_id, ts):
    """Manifest assinado pelo Mercado Pago; partes ausentes são omitidas."""
    partes = []
    if data_id:
        partes.append(f'id:{data_id};')
    if request_id:
        partes.append(f'request-id:{request_id};')
    if ts:
        partes.append(f'ts:{ts};')
    return ''.join(partes)


def ler_x_signature(valor):
    """'ts=1704908010,v1=abc...' -> ('1704908010', 'abc...')"""
    campos = {}
    for parte in (valor or '').split(','):
        chave, _, conteudo = parte.strip().partition('=')
        campos[chave.strip()] = conteudo.strip()
    return campos.get('ts'), campos.get('v1')


class MercadoPagoProvider:
    nome = 'mercadopago'

    def __init__(self, access_token, webhook_secret='', expiracao_min=30, url_publica='',
                 aceitar_webhook_sem_segredo=False):
        self._sdk = mercadopago.SDK(access_token)
        self._webhook_secret = webhook_secret
        self._expiracao_min = expiracao_min
        self._url_publica = url_publica.rstrip('/')
        self._aceitar_sem_segredo = aceitar_webhook_sem_segredo

    def criar_pix(self, pedido, idempotency_key):
        expira = datetime.now(timezone.utc) + timedelta(minutes=self._expiracao_min)
        dados = {
            'transaction_amount': centavos_para_reais(pedido.preco_centavos),
            'description': f'{len(pedido.cards)} flashcards - {pedido.nome_deck}',
            'payment_method_id': 'pix',
            'external_reference': pedido.id,
            'date_of_expiration': expira.isoformat(timespec='milliseconds'),
            'payer': {'email': pedido.email},
        }
        # O Mercado Pago não aceita localhost; sem URL pública o status chega pela consulta (polling)
        if self._url_publica.startswith('https://'):
            dados['notification_url'] = f'{self._url_publica}/webhooks/mercadopago'

        resposta = self._sdk.payment().create(
            dados, RequestOptions(custom_headers={'x-idempotency-key': idempotency_key}))

        if resposta['status'] not in (200, 201):
            logger.error('Falha ao criar Pix do pedido %s: %s', pedido.id, resposta.get('response'))
            raise ErroPagamento('Mercado Pago recusou a criação do Pix')

        pagamento = resposta['response']
        transacao = pagamento.get('point_of_interaction', {}).get('transaction_data', {})
        return ResultadoPix(
            provider_payment_id=str(pagamento['id']),
            status=pagamento.get('status', 'pending'),
            qr_code=transacao.get('qr_code', ''),
            qr_code_base64=transacao.get('qr_code_base64', ''),
            ticket_url=transacao.get('ticket_url', ''),
            expira_em=_para_utc_sem_fuso(pagamento.get('date_of_expiration')),
        )

    def consultar(self, provider_payment_id):
        resposta = self._sdk.payment().get(provider_payment_id)
        if resposta['status'] != 200:
            logger.warning('Consulta do pagamento %s falhou: %s', provider_payment_id, resposta['status'])
            return None
        pagamento = resposta['response']
        valor = pagamento.get('transaction_amount')
        return StatusPagamento(
            status=pagamento.get('status', ''),
            valor_centavos=round(valor * 100) if valor is not None else None,
            external_reference=pagamento.get('external_reference'),
        )

    def reembolsar(self, provider_payment_id, valor_centavos=None):
        corpo = {'amount': centavos_para_reais(valor_centavos)} if valor_centavos is not None else None
        resposta = self._sdk.refund().create(provider_payment_id, corpo)
        if resposta['status'] not in (200, 201):
            logger.error('Reembolso do pagamento %s falhou: %s', provider_payment_id, resposta.get('response'))
            return False
        return True

    def validar_webhook(self, headers, query_args, body):
        """Valida a assinatura x-signature conforme a documentação do Mercado Pago.

        Só a autenticidade é verificada aqui: o status em si é sempre reconsultado na API.
        """
        try:
            corpo = json.loads(body) if body else {}
        except ValueError:
            corpo = {}

        # data.id vem da query string; se alfanumérico, em minúsculas
        data_id = query_args.get('data.id') or ''
        if re.fullmatch(r'[A-Za-z0-9]+', data_id):
            data_id = data_id.lower()
        request_id = headers.get('x-request-id', '')
        ts, assinatura = ler_x_signature(headers.get('x-signature', ''))

        if not self._webhook_secret:
            if not self._aceitar_sem_segredo:
                logger.warning('Webhook rejeitado: MERCADOPAGO_WEBHOOK_SECRET não configurado')
                return None
        else:
            if not ts or not assinatura:
                return None
            esperado = hmac.new(self._webhook_secret.encode('utf-8'),
                                montar_manifest(data_id, request_id, ts).encode('utf-8'),
                                hashlib.sha256).hexdigest()
            if not hmac.compare_digest(esperado, assinatura):
                return None
            try:
                ts_segundos = int(ts) / (1000 if int(ts) > 10 ** 12 else 1)
            except ValueError:
                return None
            if abs(time.time() - ts_segundos) > TOLERANCIA_WEBHOOK_S:
                logger.warning('Webhook rejeitado: ts fora da janela (%s)', ts)
                return None

        tipo = query_args.get('type') or corpo.get('type')
        evento_id = str(corpo.get('id') or request_id or f'{data_id}:{ts}')
        return EventoValidado(evento_id=evento_id,
                              provider_payment_id=data_id if tipo == 'payment' and data_id else None)
