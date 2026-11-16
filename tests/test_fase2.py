"""Critérios de aceite da Fase 2 do PLANO_DE_IMPLEMENTACAO.md: pagamentos confiáveis e recuperáveis."""
import hashlib
import hmac
import json
import time
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app import create_app
from app.config import ConfiguracaoInvalida
from app.db import Session
from app.models import EventoWebhook, Pagamento, PagamentoFake, Pedido, StatusPedido as S, agora
from app.pagamentos.mercadopago import MercadoPagoProvider, ler_x_signature, montar_manifest
from conftest import executar_lotes, gerar, gerar_e_pagar, pedir_pix, simular, url_apkg


def pedido_do_token(token):
    return Session.scalar(select(Pedido).where(Pedido.token_acesso == token))


# 2.3 — provedor fake e rotas de simulação

def test_pix_de_teste_tem_qr_png_e_codigo_ficticio(client):
    token = gerar(client)
    estado = pedir_pix(client, token).get_json()
    assert estado['status'] == S.AGUARDANDO_PAGAMENTO
    assert estado['modo_teste'] is True
    assert estado['pix']['qr_code'].startswith('PIX-DE-TESTE-')
    import base64
    assert base64.b64decode(estado['pix']['qr_code_base64'])[:8] == b'\x89PNG\r\n\x1a\n'


def test_simulacoes_seguem_o_caminho_do_webhook(client):
    token = gerar(client)
    pedir_pix(client, token)
    simular(client, token, 'recusar')
    estado = client.get(f'/api/pedidos/{token}').get_json()
    assert estado['status'] == S.EXPIRADO and estado['status_texto'] == 'Pagamento recusado'
    assert estado['pix'] is None and estado['pode_gerar_pix'] is True


def test_rotas_dev_nao_existem_fora_de_desenvolvimento(monkeypatch):
    for nome, valor in {'APP_ENV': 'production', 'DATABASE_URL': 'postgresql://u:s@h/db', 'SECRET_KEY': 'x',
                        'PAYMENT_PROVIDER': 'mercadopago', 'MERCADOPAGO_ACCESS_TOKEN': 'tok',
                        'MERCADOPAGO_WEBHOOK_SECRET': 's', 'URL_PUBLICA': 'https://x.app',
                        'GEMINI_API_KEY': 'k', 'TURNSTILE_SITE_KEY': 'site', 'TURNSTILE_SECRET': 'segredo'}.items():
        monkeypatch.setenv(nome, valor)
    rotas = {r.rule for r in create_app().url_map.iter_rules()}
    assert not any(r.startswith('/dev') for r in rotas)


def test_fake_proibido_em_producao(monkeypatch):
    for nome, valor in {'APP_ENV': 'production', 'DATABASE_URL': 'postgresql://u:s@h/db', 'SECRET_KEY': 'x',
                        'PAYMENT_PROVIDER': 'fake', 'GEMINI_API_KEY': 'k'}.items():
        monkeypatch.setenv(nome, valor)
    with pytest.raises(ConfiguracaoInvalida):
        create_app()


def test_simulacao_recusada_se_provedor_nao_e_fake(aplicacao, client):
    token = gerar(client)
    pix = pedir_pix(client, token).get_json()['pix']
    aplicacao.extensions['pagamentos'] = MercadoPagoProvider('TEST-x')
    assert client.post(f'/dev/pagamentos/{pix["id_teste"]}/aprovar').status_code == 404


# 2.4 — pedido persistente e retomada

def test_pagina_do_pedido(client):
    token = gerar(client)
    assert client.get(f'/pedido/{token}').status_code == 200
    assert client.get('/pedido/token-inexistente').status_code == 404


def test_pix_exige_email_valido(client):
    token = gerar(client)
    for email in ('', 'sem-arroba', 'a@b'):
        assert pedir_pix(client, token, email).status_code == 400


def test_pix_vigente_e_reaproveitado(aplicacao, client):
    token = gerar(client)
    primeiro = pedir_pix(client, token).get_json()['pix']
    segundo = pedir_pix(client, token).get_json()['pix']
    assert primeiro == segundo
    with aplicacao.app_context():
        assert Session.scalar(select(func.count()).select_from(PagamentoFake)) == 1


def test_pedido_expirado_so_paga_com_novo_pix(aplicacao, client):
    token = gerar(client)
    antigo = pedir_pix(client, token).get_json()['pix']
    simular(client, token, 'expirar')

    estado = client.get(f'/api/pedidos/{token}').get_json()
    assert estado['status'] == S.EXPIRADO and estado['pix'] is None
    assert client.get(url_apkg(token)).status_code == 403

    novo = pedir_pix(client, token).get_json()
    assert novo['status'] == S.AGUARDANDO_PAGAMENTO
    assert novo['pix']['id_teste'] != antigo['id_teste']
    with aplicacao.app_context():
        chaves = [p.idempotency_key for p in pedido_do_token(token).pagamentos]
        assert [c.rsplit('-', 1)[1] for c in chaves] == ['1', '2']

    simular(client, token, 'aprovar')
    assert client.get(url_apkg(token)).status_code == 200


def test_pix_vencido_pelo_relogio_expira_na_consulta(aplicacao, client):
    token = gerar(client)
    pedir_pix(client, token)
    with aplicacao.app_context():
        pagamento = pedido_do_token(token).pagamento_ativo
        pagamento.expira_em = agora() - timedelta(minutes=10)
        Session.commit()
    estado = client.get(f'/api/pedidos/{token}').get_json()
    assert estado['status'] == S.EXPIRADO and estado['pode_gerar_pix'] is True


def test_pagamento_confirmado_no_limite_do_prazo_e_entregue(aplicacao, client):
    token = gerar(client)
    id_teste = pedir_pix(client, token).get_json()['pix']['id_teste']
    simular(client, token, 'expirar')
    # O banco confirmou o Pix antigo mesmo assim: o dinheiro entrou, o pedido é entregue
    client.post(f'/dev/pagamentos/{id_teste}/aprovar')
    assert client.get(url_apkg(token)).status_code == 200


def test_pedido_sobrevive_a_reinicio_com_pix_pendente(criar_aplicacao):
    primeira = criar_aplicacao().test_client()
    token = gerar(primeira)
    id_teste = pedir_pix(primeira, token).get_json()['pix']['id_teste']

    segunda = criar_aplicacao().test_client()
    assert segunda.get(f'/api/pedidos/{token}').get_json()['pix']['id_teste'] == id_teste
    segunda.post(f'/dev/pagamentos/{id_teste}/aprovar')
    assert segunda.get(url_apkg(token)).status_code == 200


def test_downloads_respeitam_prazo_de_retencao(aplicacao, client):
    token = gerar_e_pagar(client)
    with aplicacao.app_context():
        pedido = pedido_do_token(token)
        assert pedido.expira_em > agora() + timedelta(days=29)
        pedido.expira_em = agora() - timedelta(seconds=1)
        Session.commit()
    assert client.get(url_apkg(token)).status_code == 410
    assert client.get(f'/api/pedidos/{token}').get_json()['downloads'] is None


# 2.6 — regras de dinheiro

def test_valor_divergente_nao_aprova(aplicacao, client):
    token = gerar(client)
    id_teste = pedir_pix(client, token).get_json()['pix']['id_teste']
    with aplicacao.app_context():
        Session.get(PagamentoFake, id_teste).valor_centavos = 1  # pagaram R$ 0,01
        Session.commit()
    simular(client, token, 'aprovar')
    assert client.get(url_apkg(token)).status_code == 403
    with aplicacao.app_context():
        assert pedido_do_token(token).pagamento_ativo.status == 'divergente'


def test_segundo_pagamento_do_mesmo_pedido_e_reembolsado(aplicacao, client):
    token = gerar(client)
    primeiro = pedir_pix(client, token).get_json()['pix']['id_teste']
    simular(client, token, 'expirar')
    pedir_pix(client, token)
    simular(client, token, 'aprovar')
    client.post(f'/dev/pagamentos/{primeiro}/aprovar')  # o Pix antigo também foi pago

    with aplicacao.app_context():
        status = {p.provider_payment_id: p.status for p in pedido_do_token(token).pagamentos}
        assert status[primeiro] == 'refunded'
        assert sorted(status.values()) == ['approved', 'refunded']
        assert Session.get(PagamentoFake, primeiro).status == 'refunded'
    assert client.get(url_apkg(token)).status_code == 200


def test_aprovacao_repetida_e_idempotente(aplicacao, client):
    token = gerar(client)
    id_teste = pedir_pix(client, token).get_json()['pix']['id_teste']
    client.post(f'/dev/pagamentos/{id_teste}/aprovar')
    with aplicacao.app_context():
        concluido_em = pedido_do_token(token).concluido_em
    # A mesma aprovação chegando de novo (webhook repetido, polling) não muda nada
    assert client.post(f'/dev/pagamentos/{id_teste}/aprovar').status_code == 200
    client.get(f'/api/pedidos/{token}')
    with aplicacao.app_context():
        pedido = pedido_do_token(token)
        assert pedido.status == S.CONCLUIDO and pedido.concluido_em == concluido_em
        assert [p.status for p in pedido.pagamentos] == ['approved']


# 2.2 — Mercado Pago: criação do Pix e webhook

class RespostasSDK:
    """Imita o SDK do Mercado Pago, registrando as chamadas."""

    def __init__(self):
        self.criados, self.reembolsos = [], []
        self.pagamento = {'status': 'pending', 'transaction_amount': 3.90, 'external_reference': None}
        self.falhar_consulta = False

    def payment(self):
        return self

    def refund(self):
        return self

    def create(self, dados, opcoes=None):
        if isinstance(dados, dict):
            self.criados.append((dados, opcoes.custom_headers))
            return {'status': 201, 'response': {
                'id': 555, 'status': 'pending', 'date_of_expiration': dados['date_of_expiration'],
                'point_of_interaction': {'transaction_data': {'qr_code': 'copia', 'qr_code_base64': 'b64'}}}}
        self.reembolsos.append(dados)
        return {'status': 201, 'response': {}}

    def get(self, payment_id):
        if self.falhar_consulta:
            return {'status': 500, 'response': {}}
        return {'status': 200, 'response': dict(self.pagamento)}


SEGREDO = 'segredo-do-webhook'


@pytest.fixture
def mp(aplicacao):
    provedor = MercadoPagoProvider('TEST-token', webhook_secret=SEGREDO, url_publica='https://meusite.app')
    provedor._sdk = sdk = RespostasSDK()
    aplicacao.extensions['pagamentos'] = provedor
    return sdk


def assinar(data_id, request_id, ts=None, segredo=SEGREDO):
    ts = str(ts if ts is not None else int(time.time()))
    v1 = hmac.new(segredo.encode(), montar_manifest(data_id, request_id, ts).encode(), hashlib.sha256).hexdigest()
    return {'x-signature': f'ts={ts},v1={v1}', 'x-request-id': request_id}


def notificar(client, data_id='555', request_id='req-1', evento_id=1, cabecalhos=None):
    corpo = json.dumps({'id': evento_id, 'type': 'payment', 'action': 'payment.updated', 'data': {'id': data_id}})
    return client.post(f'/webhooks/mercadopago?data.id={data_id}&type=payment', data=corpo,
                       content_type='application/json',
                       headers=cabecalhos if cabecalhos is not None else assinar(data_id, request_id))


def test_manifest_no_formato_da_documentacao():
    assert montar_manifest('123', 'abc', '1704908010') == 'id:123;request-id:abc;ts:1704908010;'
    assert montar_manifest('123', '', '1704908010') == 'id:123;ts:1704908010;'
    assert ler_x_signature('ts=1704908010,v1=deadbeef') == ('1704908010', 'deadbeef')


def test_mercadopago_cria_pix_com_idempotencia_e_referencia(client, mp, aplicacao):
    token = gerar(client)
    estado = pedir_pix(client, token).get_json()
    dados, cabecalhos = mp.criados[0]
    with aplicacao.app_context():
        pedido = pedido_do_token(token)
        assert cabecalhos['x-idempotency-key'] == f'{pedido.id}-1'
        assert dados['external_reference'] == pedido.id
    assert dados['payer']['email'] == 'aluno@exemplo.com'
    assert dados['transaction_amount'] == 3.9
    assert dados['notification_url'] == 'https://meusite.app/webhooks/mercadopago'
    assert 'date_of_expiration' in dados
    assert estado['pix']['qr_code'] == 'copia' and estado['modo_teste'] is False


def test_webhook_valido_aprova_o_pedido(client, mp, aplicacao):
    token = gerar(client)
    pedir_pix(client, token)
    with aplicacao.app_context():
        mp.pagamento.update(status='approved', external_reference=pedido_do_token(token).id)
    assert notificar(client).status_code == 200
    assert client.get(url_apkg(token)).status_code == 200


@pytest.mark.parametrize('cabecalhos', [
    {},
    assinar('555', 'req-1', segredo='outro-segredo'),
    assinar('999', 'req-1'),  # assinatura de outro pagamento
    assinar('555', 'req-1', ts=int(time.time()) - 3600),  # ts expirado
])
def test_webhook_invalido_e_rejeitado_sem_alterar_o_pedido(client, mp, aplicacao, cabecalhos):
    token = gerar(client)
    pedir_pix(client, token)
    mp.pagamento['status'] = 'approved'
    assert notificar(client, cabecalhos=cabecalhos).status_code == 401
    with aplicacao.app_context():
        assert pedido_do_token(token).status == S.AGUARDANDO_PAGAMENTO
        assert Session.scalar(select(func.count()).select_from(EventoWebhook)) == 0


def test_webhook_aceita_ts_em_milissegundos(client, mp):
    gerar(client)
    assert notificar(client, cabecalhos=assinar('555', 'req-1', ts=int(time.time() * 1000))).status_code == 200


def test_webhook_duplicado_e_ignorado(client, mp, aplicacao):
    token = gerar(client)
    pedir_pix(client, token)
    assert notificar(client, evento_id=77).status_code == 200
    resposta = notificar(client, evento_id=77)
    assert resposta.get_json().get('duplicado') is True
    with aplicacao.app_context():
        assert Session.scalar(select(func.count()).select_from(EventoWebhook)) == 1


def test_webhook_com_falha_na_consulta_pede_reenvio(client, mp, aplicacao):
    token = gerar(client)
    pedir_pix(client, token)
    mp.falhar_consulta = True
    assert notificar(client).status_code == 503
    with aplicacao.app_context():
        assert Session.scalar(select(func.count()).select_from(EventoWebhook)) == 0


def test_webhook_de_pagamento_desconhecido_ou_outro_topico(client, mp):
    assert notificar(client, data_id='424242').status_code == 200
    corpo = json.dumps({'id': 5, 'type': 'plan', 'data': {'id': '1'}})
    resposta = client.post('/webhooks/mercadopago?data.id=1&type=plan', data=corpo,
                           content_type='application/json', headers=assinar('1', 'r'))
    assert resposta.get_json().get('ignorado') is True


def test_webhook_no_endereco_antigo(client, mp):
    corpo = json.dumps({'id': 9, 'type': 'payment', 'data': {'id': '1'}})
    resposta = client.post('/webhook-mercadopago?data.id=1&type=payment', data=corpo,
                           content_type='application/json', headers=assinar('1', 'r'))
    assert resposta.status_code == 200


def test_referencia_de_outro_pedido_nao_aprova(client, mp):
    token = gerar(client)
    pedir_pix(client, token)
    mp.pagamento.update(status='approved', external_reference='outro-pedido')
    notificar(client)
    assert client.get(url_apkg(token)).status_code == 403


def test_reembolso_de_pagamento_aprovado_marca_pedido(client, mp, aplicacao):
    token = gerar(client)
    pedir_pix(client, token)
    with aplicacao.app_context():
        mp.pagamento.update(status='approved', external_reference=pedido_do_token(token).id)
    notificar(client, evento_id=1)
    mp.pagamento['status'] = 'refunded'
    notificar(client, evento_id=2)
    with aplicacao.app_context():
        assert pedido_do_token(token).status == S.REEMBOLSADO
    assert client.get(url_apkg(token)).status_code == 403


def test_webhook_sem_segredo_so_em_desenvolvimento():
    provedor = MercadoPagoProvider('TEST-x', webhook_secret='')
    assert provedor.validar_webhook({}, {'data.id': '1', 'type': 'payment'}, b'{}') is None
    dev = MercadoPagoProvider('TEST-x', webhook_secret='', aceitar_webhook_sem_segredo=True)
    assert dev.validar_webhook({}, {'data.id': '1', 'type': 'payment'}, b'{}').provider_payment_id == '1'


def test_pedido_ja_pago_nao_aceita_novo_pix(client):
    token = gerar_e_pagar(client)
    assert pedir_pix(client, token).status_code == 409


def test_pagamento_gravado_com_id_em_string(client, mp, aplicacao):
    token = gerar(client)
    pedir_pix(client, token)
    with aplicacao.app_context():
        pagamento = Session.scalar(select(Pagamento))
        assert pagamento.provider_payment_id == '555'
        assert pedido_do_token(token).email == 'aluno@exemplo.com'
