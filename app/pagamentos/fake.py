"""Provedor de pagamento de TESTE: nenhum dinheiro envolvido. Proibido em produção (ver config.py)."""
import base64
import random
from datetime import timedelta
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select

from app.db import Session
from app.models import PagamentoFake, agora, novo_uuid
from app.pagamentos.base import ResultadoPix, StatusPagamento


def qr_de_teste_png(semente):
    """PNG que parece um QR code, com a faixa "PIX DE TESTE" — não é pagável."""
    modulos, tamanho_modulo, margem = 25, 10, 20
    lado = modulos * tamanho_modulo + 2 * margem
    imagem = Image.new('RGB', (lado, lado + 40), 'white')
    desenho = ImageDraw.Draw(imagem)
    gerador = random.Random(semente)
    for linha in range(modulos):
        for coluna in range(modulos):
            if gerador.random() < 0.45:
                x, y = margem + coluna * tamanho_modulo, margem + linha * tamanho_modulo
                desenho.rectangle([x, y, x + tamanho_modulo - 1, y + tamanho_modulo - 1], fill='#1C1917')
    desenho.rectangle([0, lado - 10, lado, lado + 40], fill='#FACC15')
    fonte = ImageFont.load_default(size=22)
    desenho.text((lado / 2, lado + 15), 'PIX DE TESTE', fill='#1C1917', font=fonte, anchor='mm')
    buffer = BytesIO()
    imagem.save(buffer, format='PNG')
    return base64.b64encode(buffer.getvalue()).decode('ascii')


class FakePaymentProvider:
    nome = 'fake'

    def __init__(self, expiracao_min=30):
        self._expiracao_min = expiracao_min

    def criar_pix(self, pedido, idempotency_key):
        existente = Session.scalar(select(PagamentoFake).where(PagamentoFake.idempotency_key == idempotency_key))
        remoto = existente or PagamentoFake(id=f'fake-{novo_uuid()}', valor_centavos=pedido.preco_centavos,
                                            external_reference=pedido.id, idempotency_key=idempotency_key)
        if existente is None:
            Session.add(remoto)
        return ResultadoPix(
            provider_payment_id=remoto.id,
            status=remoto.status,
            qr_code=f'PIX-DE-TESTE-{remoto.id}-SEM-VALOR',
            qr_code_base64=qr_de_teste_png(remoto.id),
            ticket_url='',
            expira_em=agora() + timedelta(minutes=self._expiracao_min),
        )

    def consultar(self, provider_payment_id):
        remoto = Session.get(PagamentoFake, provider_payment_id)
        if remoto is None:
            return None
        return StatusPagamento(status=remoto.status, valor_centavos=remoto.valor_centavos,
                               external_reference=remoto.external_reference)

    def reembolsar(self, provider_payment_id, valor_centavos=None):
        remoto = Session.get(PagamentoFake, provider_payment_id)
        if remoto is None:
            return False
        if valor_centavos is None or valor_centavos >= remoto.valor_centavos:
            remoto.status = 'refunded'  # parcial: continua "approved", como no Mercado Pago
        return True

    def validar_webhook(self, headers, query_args, body):
        return None  # o fake não envia webhooks; use as rotas /dev/pagamentos/...

    def simular(self, provider_payment_id, status):
        """Muda o status "no provedor", como se o banco tivesse processado o Pix."""
        remoto = Session.get(PagamentoFake, provider_payment_id)
        if remoto is None:
            return False
        remoto.status = status
        return True
