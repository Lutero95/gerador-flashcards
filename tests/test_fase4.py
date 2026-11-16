"""Critérios de aceite da Fase 4: anti-abuso e controle de orçamento."""
import io
import re
from datetime import timedelta
from types import SimpleNamespace

import httpx
import pytest
from reportlab.pdfgen import canvas
from sqlalchemy import func, select

from app import seguranca
from app.db import Session
from app.models import ContadorRequisicao, CotaPrevia, Pedido, StatusPedido as S, UsoIA, agora
from conftest import PNG, criar_pedido, executar_lotes, gerar, pedir_pix, simular


def pedido_do_token(token):
    return Session.scalar(select(Pedido).where(Pedido.token_acesso == token))


def pdf_com_paginas(paginas):
    buffer = io.BytesIO()
    folha = canvas.Canvas(buffer)
    for _ in range(paginas):
        folha.drawString(100, 700, 'pagina ' * 60)
        folha.showPage()
    folha.save()
    return buffer.getvalue()


def enviar(client, quantidade, arquivos):
    dados = {'prompt': 'Resumo', 'quantidade': str(quantidade)}
    for i, (nome, conteudo) in enumerate(arquivos):
        dados[f'arquivo_{i}'] = (io.BytesIO(conteudo), nome)
    return client.post('/api/pedidos', data=dados, content_type='multipart/form-data')


# Rate limit por IP (contadores no banco)

def test_rate_limit_ao_criar_pedido(criar_aplicacao):
    aplicacao = criar_aplicacao(LIMITE_CRIAR_PEDIDO_MIN=2)
    client = aplicacao.test_client()
    assert criar_pedido(client).status_code == 201
    assert criar_pedido(client).status_code == 201
    resposta = criar_pedido(client)
    assert resposta.status_code == 429 and 0 < int(resposta.headers['Retry-After']) <= 61
    assert len(aplicacao.extensions['ia'].chamadas) == 2


def test_rate_limit_separa_ips_so_atras_do_proxy(criar_aplicacao):
    atras_do_proxy = criar_aplicacao(LIMITE_CRIAR_PEDIDO_MIN=1, CONFIAR_PROXY=True).test_client()
    for ip, esperado in (('10.0.0.1', 201), ('10.0.0.1', 429), ('10.0.0.2', 201)):
        resposta = atras_do_proxy.post('/api/pedidos', json={'prompt': 'x', 'quantidade': 2},
                                       headers={'x-real-ip': ip})
        assert resposta.status_code == esperado


def test_cabecalho_forjado_nao_escapa_do_limite_sem_proxy(criar_aplicacao):
    client = criar_aplicacao(LIMITE_CRIAR_PEDIDO_MIN=1, CONFIAR_PROXY=False).test_client()
    for ip, esperado in (('10.0.0.1', 201), ('10.0.0.2', 429)):
        resposta = client.post('/api/pedidos', json={'prompt': 'x', 'quantidade': 2},
                               headers={'x-forwarded-for': ip})
        assert resposta.status_code == esperado


def test_rate_limit_no_polling(criar_aplicacao):
    client = criar_aplicacao(LIMITE_CONSULTA_MIN=3).test_client()
    token = gerar(client)
    codigos = [client.get(f'/api/pedidos/{token}').status_code for _ in range(4)]
    assert codigos == [200, 200, 200, 429]


# Cloudflare Turnstile

@pytest.fixture
def turnstile(monkeypatch):
    chamadas = []
    resultado = {'success': True}

    def post(url, timeout, data):
        chamadas.append(data)
        if resultado.get('erro'):
            raise httpx.ConnectError('fora do ar')
        return SimpleNamespace(json=lambda: resultado)

    monkeypatch.setattr(seguranca.httpx, 'post', post)
    return SimpleNamespace(chamadas=chamadas, resultado=resultado)


def test_turnstile_valido_libera_a_previa(criar_aplicacao, turnstile):
    aplicacao = criar_aplicacao(TURNSTILE_SECRET='segredo', TURNSTILE_SITE_KEY='site')
    resposta = criar_pedido(aplicacao.test_client(), turnstile_token='token-do-widget')
    assert resposta.status_code == 201
    assert turnstile.chamadas[0]['secret'] == 'segredo' and turnstile.chamadas[0]['response'] == 'token-do-widget'


@pytest.mark.parametrize('token,resultado', [('', {'success': True}), ('t', {'success': False}),
                                             ('t', {'erro': True})])
def test_turnstile_bloqueia_robos(criar_aplicacao, turnstile, token, resultado):
    turnstile.resultado.clear()
    turnstile.resultado.update(resultado)
    aplicacao = criar_aplicacao(TURNSTILE_SECRET='segredo', TURNSTILE_SITE_KEY='site')
    resposta = criar_pedido(aplicacao.test_client(), turnstile_token=token)
    assert resposta.status_code == 403
    assert aplicacao.extensions['ia'].chamadas == []


def test_pagina_inclui_o_widget_quando_configurado(criar_aplicacao):
    html = criar_aplicacao(TURNSTILE_SITE_KEY='minha-chave').test_client().get('/').get_data(as_text=True)
    assert 'challenges.cloudflare.com/turnstile/v0/api.js' in html and 'data-sitekey="minha-chave"' in html


# Cota de prévias por visitante e por IP

def test_cota_por_visitante_com_compra_direta(criar_aplicacao):
    aplicacao = criar_aplicacao(PREVIAS_POR_DIA=2)
    client = aplicacao.test_client()
    assert criar_pedido(client).status_code == 201
    assert criar_pedido(client).status_code == 201
    resposta = criar_pedido(client)
    assert resposta.status_code == 429
    assert resposta.get_json()['motivo'] == 'cota' and resposta.get_json()['compra_direta_disponivel'] is True
    assert client.get('/api/previa/disponibilidade').get_json()['disponivel'] is False

    outro_navegador = aplicacao.test_client()  # cookie novo
    assert criar_pedido(outro_navegador).status_code == 201


def test_limpar_cookies_nao_escapa_da_cota_por_ip(criar_aplicacao):
    aplicacao = criar_aplicacao(PREVIAS_POR_DIA=2, PREVIAS_POR_DIA_IP=3)
    codigos = [criar_pedido(aplicacao.test_client()).status_code for _ in range(4)]  # 4 "navegadores"
    assert codigos == [201, 201, 201, 429]


def test_ip_nunca_e_guardado_em_claro(aplicacao, client):
    token = gerar(client)
    with aplicacao.app_context():
        chaves = list(Session.scalars(select(CotaPrevia.visitante_hash)))
        chaves += list(Session.scalars(select(ContadorRequisicao.chave)))
        assert chaves and not any('127.0.0.1' in chave for chave in chaves)
        assert re.fullmatch(r'[0-9a-f]{64}', pedido_do_token(token).visitante_hash)


def test_cookie_do_visitante_e_protegido(client):
    criar_pedido(client)
    cookie = client.get_cookie('session')
    assert cookie is not None and cookie.http_only and cookie.same_site == 'Lax'


# Orçamento global diário de prévias

def test_orcamento_diario_pausa_previas_mas_nao_a_compra(criar_aplicacao):
    # IA falsa: 100 tokens de entrada + 50 de saída; flash-lite a US$ 0,30 / 2,50 por milhão = US$ 0,000155
    aplicacao = criar_aplicacao(ORCAMENTO_PREVIAS_USD_DIA=0.0002, MODELO_PREVIA='gemini-flash-lite-latest')
    client = aplicacao.test_client()
    assert criar_pedido(client).status_code == 201
    with aplicacao.app_context():
        custo = Session.scalar(select(UsoIA.custo_estimado_usd))
        assert custo == pytest.approx(0.000155)
    assert criar_pedido(client).status_code == 201  # ainda abaixo do teto
    resposta = criar_pedido(client)
    assert resposta.status_code == 429 and resposta.get_json()['motivo'] == 'orcamento'
    assert criar_pedido(client, modo='direto').status_code == 201


def test_modelo_sem_preco_usa_o_mais_caro(aplicacao):
    with aplicacao.app_context():
        assert seguranca.estimar_custo_usd('modelo-novo', 1_000_000, 0) == 0.75


# Compra direta (sem prévia)

def test_compra_direta_gera_tudo_depois_do_pagamento(criar_aplicacao):
    aplicacao = criar_aplicacao(PREVIAS_POR_DIA=0)
    client, ia = aplicacao.test_client(), aplicacao.extensions['ia']
    resposta = criar_pedido(client, 100, modo='direto')
    estado = resposta.get_json()
    assert resposta.status_code == 201 and estado['previa'] == [] and estado['preco_texto'] == 'R$ 6,90'
    assert ia.chamadas == []

    token = estado['token']
    pedir_pix(client, token)
    simular(client, token, 'aprovar')
    estado = executar_lotes(client, token)
    assert estado['status'] == S.CONCLUIDO and estado['quantidade_gerada'] == 100
    assert [c['schema'] for c in ia.chamadas] == ['LoteGerado'] * 3


# Cache de prévia

def test_mesma_previa_e_reaproveitada_sem_custo(criar_aplicacao):
    aplicacao = criar_aplicacao(CACHE_PREVIA_HORAS=24, PREVIAS_POR_DIA=1)
    client, ia = aplicacao.test_client(), aplicacao.extensions['ia']
    primeira = criar_pedido(client, 60).get_json()
    segunda = criar_pedido(client, 60)  # já sem cota: o cache não conta
    assert segunda.status_code == 201
    assert len(ia.chamadas) == 1
    assert segunda.get_json()['previa'] == primeira['previa']
    assert segunda.get_json()['token'] != primeira['token']
    with aplicacao.app_context():
        assert [lote.quantidade for lote in pedido_do_token(segunda.get_json()['token']).lotes] == [40, 15]


def test_cache_nao_vale_para_outra_quantidade_nem_arquivos(criar_aplicacao):
    aplicacao = criar_aplicacao(CACHE_PREVIA_HORAS=24)
    client, ia = aplicacao.test_client(), aplicacao.extensions['ia']
    criar_pedido(client, 60)
    criar_pedido(client, 61)
    enviar(client, 60, [('notas.txt', b'Enzimas')])
    assert len(ia.chamadas) == 3


def test_cache_expira(criar_aplicacao):
    aplicacao = criar_aplicacao(CACHE_PREVIA_HORAS=24)
    client, ia = aplicacao.test_client(), aplicacao.extensions['ia']
    token = gerar(client, 60)
    with aplicacao.app_context():
        pedido_do_token(token).criado_em = agora() - timedelta(hours=25)
        Session.commit()
    criar_pedido(client, 60)
    assert len(ia.chamadas) == 2


# Limites de upload

def test_limite_de_paginas_por_faixa(client, ia):
    resposta = enviar(client, 10, [('apostila.pdf', pdf_com_paginas(31))])  # até 50 cards: 30 páginas
    assert resposta.status_code == 400 and '31 páginas' in resposta.get_json()['erro']
    assert ia.chamadas == [] and ia.enviados == []
    assert enviar(client, 100, [('apostila.pdf', pdf_com_paginas(31))]).status_code == 201  # 100 cards: 50


@pytest.mark.parametrize('nome,conteudo', [('foto.pdf', PNG), ('imagem.png', b'%PDF-1.4'),
                                           ('notas.txt', b'texto\x00binario'), ('doc.docx', b'nao e zip')])
def test_conteudo_precisa_bater_com_a_extensao(client, ia, nome, conteudo):
    resposta = enviar(client, 10, [(nome, conteudo)])
    assert resposta.status_code == 400 and nome in resposta.get_json()['erro']
    assert ia.enviados == []


def test_webp_valido_e_aceito(client, ia):
    webp = b'RIFF\x24\x00\x00\x00WEBPVP8 ' + b'\x00' * 20
    assert enviar(client, 10, [('foto.webp', webp)]).status_code == 201
    assert ia.enviados[0]['mime_type'] == 'image/webp'


# Cabeçalhos de segurança

def test_cabecalhos_e_csp_com_nonce(client):
    resposta = client.get('/')
    html = resposta.get_data(as_text=True)
    csp = resposta.headers['Content-Security-Policy']
    nonce = re.search(r"'nonce-([^']+)'", csp).group(1)
    scripts = re.findall(r'<script([^>]*)>(.*?)</script>', html, re.S)
    assert scripts and all(f'nonce="{nonce}"' in atributos for atributos, _ in scripts)
    assert all(not corpo.strip() for _, corpo in scripts)  # nenhum script inline: todos em static/js
    assert "frame-ancestors 'none'" in csp and "object-src 'none'" in csp
    assert 'onclick=' not in html
    assert resposta.headers['X-Content-Type-Options'] == 'nosniff'
    assert resposta.headers['Referrer-Policy'] == 'no-referrer'
    assert resposta.headers['X-Frame-Options'] == 'DENY'
    assert nonce != re.search(r"'nonce-([^']+)'", client.get('/').headers['Content-Security-Policy']).group(1)


def test_api_tem_nosniff_sem_csp(client):
    resposta = client.get('/api/preco?quantidade=10')
    assert resposta.headers['X-Content-Type-Options'] == 'nosniff'
    assert 'Content-Security-Policy' not in resposta.headers


# Expiração de pedidos não pagos (Cron diário da Vercel)

def envelhecer(aplicacao, token, dias):
    with aplicacao.app_context():
        pedido_do_token(token).criado_em = agora() - timedelta(days=dias)
        Session.commit()


def test_limpeza_expira_pedidos_nao_pagos_e_descarta_material(aplicacao, client, ia):
    token = enviar(client, 10, [('quadro.png', PNG)]).get_json()['token']
    recente = gerar(client)
    envelhecer(aplicacao, token, 8)

    resultado = client.get('/tarefas/limpeza').get_json()
    assert resultado['pedidos_expirados'] == 1
    with aplicacao.app_context():
        pedido = pedido_do_token(token)
        assert pedido.status == S.EXPIRADO and pedido.referencias_arquivos is None
        assert pedido_do_token(recente).status == S.PREVIA_PRONTA
    assert ia.apagados == ['files/1']


def test_pedido_antigo_nao_aceita_pagamento(aplicacao, client):
    token = gerar(client)
    envelhecer(aplicacao, token, 8)
    resposta = pedir_pix(client, token)
    assert resposta.status_code == 410 and 'expirou' in resposta.get_json()['erro']


def test_limpeza_protegida_por_segredo(criar_aplicacao):
    client = criar_aplicacao(CRON_SECRET='s3gredo').test_client()
    assert client.get('/tarefas/limpeza').status_code == 404
    assert client.get('/tarefas/limpeza', headers={'Authorization': 'Bearer errado'}).status_code == 404
    assert client.get('/tarefas/limpeza', headers={'Authorization': 'Bearer s3gredo'}).status_code == 200


def test_limpeza_apaga_contadores_antigos(aplicacao, client):
    gerar(client)
    with aplicacao.app_context():
        for contador in Session.scalars(select(ContadorRequisicao)):
            contador.janela = agora() - timedelta(days=2)
        Session.commit()
    assert client.get('/tarefas/limpeza').get_json()['contadores_apagados'] >= 1
    with aplicacao.app_context():
        antigos = Session.scalar(select(func.count()).select_from(ContadorRequisicao).where(
            ContadorRequisicao.janela < agora() - timedelta(days=1)))
        assert antigos == 0
