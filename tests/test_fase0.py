"""Critérios de aceite da Fase 0 do PLANO_DE_IMPLEMENTACAO.md."""
import io
import os
import re
import subprocess

from sqlalchemy import func, select

from app.db import Session
from app.models import PagamentoFake
from conftest import PNG, RAIZ, criar_pedido, gerar, gerar_e_pagar, pedir_pix, simular, url_apkg, url_pdf


# 0.1 — nenhum segredo em arquivo versionável

def test_nenhuma_chave_google_em_arquivo_versionavel():
    arquivos = subprocess.run(
        ['git', 'ls-files', '--cached', '--others', '--exclude-standard'],
        cwd=RAIZ, capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    assert '.env' not in arquivos
    vazados = []
    for nome in arquivos:
        caminho = os.path.join(RAIZ, nome)
        if not os.path.isfile(caminho):
            continue
        with open(caminho, 'rb') as f:
            if re.search(rb'AIza[0-9A-Za-z_\-]{20,}', f.read()):
                vazados.append(nome)
    assert vazados == []


def test_env_example_renomeado_com_placeholders():
    assert not os.path.exists(os.path.join(RAIZ, 'env.example'))
    with open(os.path.join(RAIZ, '.env.example'), encoding='utf-8') as f:
        assert 'GEMINI_API_KEY=coloque_sua_chave_aqui' in f.read()


# 0.2 — nenhuma cobrança fora de um pedido

def test_rotas_de_pagamento_avulso_removidas(aplicacao, client):
    assert client.post('/criar-pagamento-pix', json={'valor': 1}).status_code == 404
    assert client.get('/verificar-pagamento/123').status_code == 404
    with aplicacao.app_context():
        assert Session.scalar(select(func.count()).select_from(PagamentoFake)) == 0


def test_front_sem_formulario_de_valor_livre(client):
    html = client.get('/').get_data(as_text=True)
    assert 'abrirPagamentoBtn' not in html
    assert 'paymentValor' not in html
    assert '/criar-pagamento-pix' not in html


# 0.3 — download nega por padrão

def test_download_de_geracao_desconhecida_e_404(client):
    assert client.get('/api/pedidos/nao-existe/baralho.apkg').status_code == 404
    assert client.get('/download/arquivo.apkg').status_code == 404


def test_download_bloqueado_ate_aprovacao(client):
    token = gerar(client)
    assert client.get(url_apkg(token)).status_code == 403
    assert pedir_pix(client, token).status_code == 200
    assert client.get(url_apkg(token)).status_code == 403
    assert client.get(url_pdf(token)).status_code == 403
    assert client.get(f'/api/pedidos/{token}').get_json()['downloads'] is None

    simular(client, token, 'aprovar')
    downloads = client.get(f'/api/pedidos/{token}').get_json()['downloads']
    assert downloads['apkg'] == url_apkg(token)

    apkg = client.get(downloads['apkg'])
    assert apkg.status_code == 200
    assert apkg.data[:2] == b'PK'  # .apkg é um zip
    assert client.get(downloads['pdf']).data[:4] == b'%PDF'
    assert client.get(f'/api/pedidos/{token}/baralho.exe').status_code == 404


def test_reinicio_do_servidor_nao_libera_nem_perde_pedido(criar_aplicacao):
    primeira = criar_aplicacao().test_client()
    pago = gerar_e_pagar(primeira)
    nao_pago = gerar(primeira)
    pedir_pix(primeira, nao_pago)

    # "Reinício": nova instância da aplicação, mesmo banco
    cliente = criar_aplicacao().test_client()
    assert cliente.get(url_apkg(nao_pago)).status_code == 403
    assert cliente.get(url_apkg(pago)).status_code == 200


# 0.4 — debug desligado por padrão

def test_debug_desligado_por_padrao():
    with open(os.path.join(RAIZ, 'app.py'), encoding='utf-8') as f:
        codigo = f.read()
    assert 'debug=True' not in codigo
    assert "os.environ.get('FLASK_DEBUG') == '1'" in codigo
    assert "os.environ.get('FLASK_HOST', '127.0.0.1')" in codigo


# 0.5 — contenção de custo (o limite provisório virou cota + orçamento na Fase 4)

def test_cota_esgotada_nao_gasta_ia(criar_aplicacao):
    aplicacao = criar_aplicacao(PREVIAS_POR_DIA=1)
    cliente = aplicacao.test_client()
    assert criar_pedido(cliente).status_code == 201
    assert criar_pedido(cliente).status_code == 429
    assert len(aplicacao.extensions['ia'].chamadas) == 1


def test_sem_pagamento_configurado_nao_gasta_ia(aplicacao, client, ia):
    aplicacao.extensions['pagamentos'] = None
    assert criar_pedido(client).status_code == 503
    assert ia.chamadas == []


# 0.6 — uploads isolados, lista branca e limite de arquivos

def enviar_arquivos(client, arquivos):
    dados = {'prompt': 'Resumo', 'quantidade': '2'}
    for i, (nome, conteudo) in enumerate(arquivos):
        dados[f'arquivo_{i}'] = (io.BytesIO(conteudo), nome)
    return client.post('/api/pedidos', data=dados, content_type='multipart/form-data')


def test_uploads_com_mesmo_nome_nao_colidem(client, ia):
    assert enviar_arquivos(client, [('foto.png', PNG + b'a')]).status_code == 201
    assert enviar_arquivos(client, [('foto.png', PNG + b'b')]).status_code == 201
    primeiro, segundo = ia.enviados[0]['caminho'], ia.enviados[1]['caminho']
    assert os.path.dirname(primeiro) != os.path.dirname(segundo)
    assert 'foto' not in os.path.basename(primeiro)
    # Existiam durante o envio (foram lidos) e foram apagados depois
    assert [e['tamanho'] for e in ia.enviados] == [len(PNG) + 1] * 2
    assert not os.path.exists(primeiro) and not os.path.exists(os.path.dirname(primeiro))


def test_upload_rejeita_extensao_fora_da_lista(client, ia):
    resp = enviar_arquivos(client, [('virus.exe', b'MZ')])
    assert resp.status_code == 400
    assert ia.chamadas == []


def test_upload_rejeita_mais_de_5_arquivos(client, ia):
    resp = enviar_arquivos(client, [(f'a{i}.txt', b'x') for i in range(6)])
    assert resp.status_code == 400
    assert ia.chamadas == []


# 0.7 — erros internos não vazam para o cliente

def test_erro_interno_nao_vaza_detalhes(client, ia):
    ia.erro = RuntimeError('detalhe-interno-secreto')
    resp = criar_pedido(client)
    corpo = resp.get_json()
    assert resp.status_code == 503
    assert 'detalhe-interno-secreto' not in resp.get_data(as_text=True)
    assert re.fullmatch(r'[0-9a-f]{8}', corpo['erro_id'])
    assert corpo['erro_id'] in corpo['erro']


# /upload (JSON → APKG) continua funcionando, sem gravar em disco

def test_upload_json_devolve_apkg_direto(client):
    with open(os.path.join(RAIZ, 'exemplo.json'), 'rb') as f:
        resp = client.post('/upload', data={'arquivo': (f, 'exemplo.json')}, content_type='multipart/form-data')
    assert resp.status_code == 200
    assert resp.data[:2] == b'PK'
    assert 'exemplo.apkg' in resp.headers['Content-Disposition']
