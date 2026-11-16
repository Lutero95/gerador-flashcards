"""Critérios de aceite da Fase 5: redesign da interface (UI/UX e acessibilidade)."""
import os
import re
import shutil
import subprocess

import pytest

from conftest import RAIZ, gerar, pedir_pix, simular

TEMPLATES = os.path.join(RAIZ, 'app', 'templates')
ESTATICOS = os.path.join(RAIZ, 'app', 'static')


def ler(*partes):
    with open(os.path.join(*partes), encoding='utf-8') as f:
        return f.read()


# 5.1 — página inicial

def test_pagina_inicial_tem_todas_as_secoes(client):
    html = client.get('/').get_data(as_text=True)
    for trecho in ('id="como-funciona"', 'id="exemplo"', 'id="precos"', 'id="perguntas"',
                   'href="/termos"', 'href="/privacidade"', 'Ver prévia grátis'):
        assert trecho in html


def test_tabela_de_precos_vem_da_configuracao(client):
    html = client.get('/').get_data(as_text=True)
    for ate, preco in ((50, 'R$ 3,90'), (100, 'R$ 6,90'), (200, 'R$ 9,90'), (500, 'R$ 18,90')):
        assert f'<td>Até {ate} flashcards</td><td>{preco}</td>' in html
    assert 'Até 1000 flashcards' not in html  # acima de MAX_CARDS não é vendido


# 5.2 — gerador com abas e chips de quantidade

def test_abas_acessiveis(client):
    html = client.get('/').get_data(as_text=True)
    assert 'role="tablist"' in html
    for tipo in ('tema', 'arquivo', 'texto'):
        assert f'id="aba-{tipo}" aria-controls="painel-{tipo}"' in html
        assert f'role="tabpanel" id="painel-{tipo}" aria-labelledby="aba-{tipo}"' in html


def test_chips_de_quantidade_com_preco(client):
    html = client.get('/').get_data(as_text=True)
    chips = re.findall(r'data-quantidade="(\d+)"[^>]*>\1 cards\s*<span class="preco-chip">(R\$ [\d,]+)</span>', html)
    assert chips == [('10', 'R$ 3,90'), ('25', 'R$ 3,90'), ('50', 'R$ 3,90'), ('100', 'R$ 6,90'),
                     ('200', 'R$ 9,90'), ('500', 'R$ 18,90')]


# 5.4 a 5.7 — dados que a página do pedido usa

def test_estado_traz_assunto_e_etapa_da_geracao(client):
    token = gerar(client, 100)
    estado = client.get(f'/api/pedidos/{token}').get_json()
    assert estado['assunto'] == 'Enzimas' and estado['lote_atual'] is None
    pedir_pix(client, token)
    simular(client, token, 'aprovar')
    estado = client.get(f'/api/pedidos/{token}').get_json()
    assert estado['lote_atual'] == {'n': 1, 'posicao': 1, 'total': 3, 'subtopicos': ['Fundamentos']}


def test_pagina_do_pedido_tem_tutorial_e_criar_outro(client):
    html = client.get(f'/pedido/{gerar(client)}').get_data(as_text=True)
    for trecho in ('Como importar no Anki', 'Criar outro baralho', 'id="ajustarTema"', 'id="copiarPix"',
                   'role="progressbar"', 'id="passos"'):
        assert trecho in html


# 5.8 — acessibilidade

def luminancia(hexa):
    canais = [int(hexa[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lineares = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canais]
    return 0.2126 * lineares[0] + 0.7152 * lineares[1] + 0.0722 * lineares[2]


def contraste(a, b):
    claro, escuro = sorted((luminancia(a), luminancia(b)), reverse=True)
    return (claro + 0.05) / (escuro + 0.05)


@pytest.mark.parametrize('texto,fundo', [
    ('texto', 'fundo'), ('texto-suave', 'fundo'), ('texto-suave', 'superficie'), ('destaque', 'superficie'),
    ('destaque', 'fundo'), ('destaque-escuro', 'destaque-claro'), ('erro', 'erro-fundo'),
    ('sucesso', 'sucesso-fundo'), ('alerta', 'alerta-fundo'),
])
def test_contraste_aa_da_paleta(texto, fundo):
    css = ler(ESTATICOS, 'css', 'app.css')
    cores = dict(re.findall(r'--([\w-]+):\s*(#[0-9A-Fa-f]{6})', css))
    assert contraste(cores[texto], cores[fundo]) >= 4.5


def test_texto_branco_sobre_o_destaque_passa_aa():
    css = ler(ESTATICOS, 'css', 'app.css')
    destaque = re.search(r'--destaque:\s*(#[0-9A-Fa-f]{6})', css).group(1)
    assert contraste('#FFFFFF', destaque) >= 4.5


def test_foco_visivel_e_movimento_reduzido():
    css = ler(ESTATICOS, 'css', 'app.css')
    assert ':focus-visible' in css and 'prefers-reduced-motion' in css


@pytest.mark.parametrize('caminho', ['/', '/termos', '/privacidade'])
def test_estrutura_acessivel(client, caminho):
    html = client.get(caminho).get_data(as_text=True)
    assert '<html lang="pt-BR">' in html
    assert 'class="pular-para-conteudo" href="#conteudo"' in html and '<main id="conteudo"' in html
    assert len(re.findall(r'<h1[ >]', html)) == 1
    assert 'onclick=' not in html and ' style="' not in html
    for tag in re.findall(r'<img[^>]*>', html):
        assert 'alt="' in tag


def test_campos_tem_rotulo(client):
    html = client.get('/').get_data(as_text=True)
    ids = re.findall(r'<(?:input|textarea)[^>]*\bid="([^"]+)"', html)
    for identificador in ids:
        if identificador == 'entradaArquivos':
            continue  # acionado pela área de arquivos, que tem rótulo próprio
        assert f'for="{identificador}"' in html, identificador


# 5.10 — sem emojis como ícones, sem o gradiente roxo antigo

EMOJI = re.compile('[\U0001F300-\U0001FAFF☀-➿⭐✅]')


@pytest.mark.parametrize('nome', ['base.html', 'index.html', 'pedido.html', 'termos.html', 'privacidade.html'])
def test_sem_emojis_nos_templates(nome):
    assert not EMOJI.search(ler(TEMPLATES, nome))


def test_sem_emojis_nos_scripts():
    for nome in os.listdir(os.path.join(ESTATICOS, 'js')):
        assert not EMOJI.search(ler(ESTATICOS, 'js', nome)), nome


def test_paleta_nova():
    css = ler(ESTATICOS, 'css', 'app.css')
    assert '#667eea' not in css and '#764ba2' not in css
    assert '--fundo: #FAFAF9' in css and '--destaque: #0F766E' in css and "'Inter'" in css


# 5.11 e 5.12 — Termos, Privacidade e marca

def test_termos_e_privacidade(client):
    termos = client.get('/termos').get_data(as_text=True)
    privacidade = client.get('/privacidade').get_data(as_text=True)
    assert 'Reembolso' in termos and '90%' in termos
    for trecho in ('Lei 13.709/2018', 'Google (API Gemini)', 'Mercado Pago', 'apagados'):
        assert trecho in privacidade


def test_contato_aparece_quando_configurado(criar_aplicacao):
    html = criar_aplicacao(CONTATO_EMAIL='suporte@exemplo.com').test_client().get('/termos').get_data(as_text=True)
    assert 'mailto:suporte@exemplo.com' in html


def test_aviso_de_marca_e_nome_sem_anki(client):
    html = client.get('/').get_data(as_text=True)
    assert 'Anki® é marca registrada da Ankitects. Este site não é afiliado nem endossado pelo Anki.' in html
    titulo = re.search(r'<title>(.*?)</title>', html).group(1)
    marca = re.search(r'class="marca"[^>]*>.*?<span>(.*?)</span>', html, re.S).group(1)
    assert 'Anki' not in titulo and 'Anki' not in marca


# CSS e JS separados em static/

def test_estaticos_servidos_com_versao(client):
    html = client.get('/').get_data(as_text=True)
    versoes = set(re.findall(r'/static/(?:css|js)/[\w.]+\?v=(\w+)', html))
    assert len(versoes) == 1
    for caminho, tipo in (('/static/css/app.css', 'text/css'), ('/static/js/inicio.js', 'javascript')):
        resposta = client.get(caminho)
        assert resposta.status_code == 200 and tipo in resposta.content_type


@pytest.mark.skipif(shutil.which('node') is None, reason='Node.js não instalado')
@pytest.mark.parametrize('nome', ['comum.js', 'inicio.js', 'pedido.js'])
def test_scripts_sem_erro_de_sintaxe(nome):
    resultado = subprocess.run(['node', '--check', os.path.join(ESTATICOS, 'js', nome)], capture_output=True, text=True)
    assert resultado.returncode == 0, resultado.stderr


def test_ids_usados_pelos_scripts_existem_nos_templates():
    """Pega o erro mais comum de refatoração de front: um $('id') que não existe mais no HTML."""
    for script, template in (('inicio.js', 'index.html'), ('pedido.js', 'pedido.html')):
        js = ler(ESTATICOS, 'js', script)
        html = ler(TEMPLATES, template) + ler(TEMPLATES, 'base.html')
        usados = set(re.findall(r"\$\('([\w-]+)'\)", js))
        faltando = sorted(i for i in usados if f'id="{i}"' not in html)
        assert not faltando, f'{script}: {faltando}'
