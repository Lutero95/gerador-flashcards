"""Critérios de aceite da Fase 1 do PLANO_DE_IMPLEMENTACAO.md."""
import importlib.util
import io
import json
import os
import sqlite3
import zipfile
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, inspect, select

from app import create_app
from app.config import ConfiguracaoInvalida, normalizar_database_url, validar_producao
from app.db import Session, migrar
from app.exportacao.anki import gerar_apkg, id_deterministico, sanitizar_campo
from app.exportacao.pdf import gerar_pdf_fontes
from google.genai import errors

from app.ia.base import Anexo, IAErroPermanente, IAErroTemporario, IAIndisponivel
from app.ia.gemini import GeminiProvider
from app.ia.prompts import LoteGerado
from app.models import Pedido, StatusPedido as S, UsoIA
from app.pedidos import TransicaoInvalida, adicionar_cards, transicionar
from app.precos import calcular_preco_centavos
from conftest import PNG, RAIZ, criar_pedido, gerar, gerar_e_pagar, pedir_pix, url_apkg, url_pdf


# 1.1 — um único create_app para local e Vercel

def test_vercel_e_local_usam_o_mesmo_create_app():
    spec = importlib.util.spec_from_file_location('api_index', os.path.join(RAIZ, 'api', 'index.py'))
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    rotas = {r.rule for r in modulo.app.url_map.iter_rules()}
    assert {'/', '/api/pedidos', '/api/pedidos/<token>/lotes/<int:n>', '/api/pedidos/<token>/baralho.apkg',
            '/webhooks/mercadopago'} <= rotas
    with open(os.path.join(RAIZ, 'api', 'index.py'), encoding='utf-8') as f:
        assert 'create_app()' in f.read()


# Critério de aceite: `alembic upgrade head` cria as tabelas

def test_migracoes_criam_todas_as_tabelas(tmp_path):
    url = f'sqlite:///{(tmp_path / "migrado.db").as_posix()}'
    migrar(url)
    engine = create_engine(url)
    tabelas = set(inspect(engine).get_table_names())
    engine.dispose()
    assert {'pedidos', 'pagamentos', 'cards', 'eventos_webhook', 'uso_ia', 'cotas_previa',
            'alembic_version'} <= tabelas


# 1.3 — configuração

def test_normaliza_url_do_postgres():
    assert normalizar_database_url('postgres://u:s@h/db') == 'postgresql+psycopg://u:s@h/db'
    assert normalizar_database_url('postgresql://u:s@h/db') == 'postgresql+psycopg://u:s@h/db'
    assert normalizar_database_url('sqlite:///local.db') == 'sqlite:///local.db'


def config_producao(**extra):
    return {'SECRET_KEY': 'x', 'DATABASE_URL': 'postgresql+psycopg://h/db', 'PAYMENT_PROVIDER': 'mercadopago',
            'MERCADOPAGO_ACCESS_TOKEN': 'tok', 'MERCADOPAGO_WEBHOOK_SECRET': 's', 'URL_PUBLICA': 'https://x.app',
            'GEMINI_API_KEY': 'k', 'TURNSTILE_SITE_KEY': 'site', 'TURNSTILE_SECRET': 'segredo', **extra}


def test_producao_exige_configuracao_completa(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://h/db')
    validar_producao(config_producao())
    for faltando in ({'SECRET_KEY': ''}, {'PAYMENT_PROVIDER': 'fake'}, {'MERCADOPAGO_ACCESS_TOKEN': ''},
                     {'DATABASE_URL': 'sqlite:///local.db'}, {'MERCADOPAGO_WEBHOOK_SECRET': ''},
                     {'URL_PUBLICA': 'http://localhost:5000'}, {'TURNSTILE_SECRET': ''}):
        with pytest.raises(ConfiguracaoInvalida):
            validar_producao(config_producao(**faltando))


def test_producao_nao_sobe_sem_secret_key(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setenv('SECRET_KEY', '')
    with pytest.raises(ConfiguracaoInvalida):
        create_app()


def test_quantidade_limitada_por_max_cards(criar_aplicacao):
    aplicacao = criar_aplicacao(MAX_CARDS=500)
    aplicacao.test_client().post('/api/pedidos', json={'prompt': 'x', 'quantidade': 5000})
    assert 'TOTAL DO BARALHO: 500 flashcards' in aplicacao.extensions['ia'].chamadas[0]['prompt']


# Preços em centavos

@pytest.mark.parametrize('quantidade,centavos', [(1, 390), (50, 390), (51, 690), (100, 690), (200, 990),
                                                 (500, 1890), (1000, 2790), (2000, 3990), (5000, 3990)])
def test_preco_por_faixa(quantidade, centavos):
    assert calcular_preco_centavos(quantidade) == centavos


# 1.4 — modelos e máquina de estados

def test_pedido_persistido_com_cards_pagamento_e_uso_ia(aplicacao, client):
    token = gerar(client)
    pedir_pix(client, token)
    with aplicacao.app_context():
        pedido = Session.scalar(select(Pedido).where(Pedido.token_acesso == token))
        assert len(token) >= 40 and token != pedido.id
        assert pedido.status == S.AGUARDANDO_PAGAMENTO
        assert pedido.preco_centavos == 390
        assert len(pedido.cards) == 2 and all(c.lote == 0 for c in pedido.cards)  # pedido de 2: só a prévia
        assert pedido.pagamento_ativo.provider_payment_id.startswith('fake-')
        assert pedido.pagamento_ativo.valor_centavos == 390
        assert pedido.pagamento_ativo.idempotency_key == f'{pedido.id}-1'
        uso = Session.scalar(select(UsoIA).where(UsoIA.pedido_id == pedido.id))
        assert (uso.sucesso, uso.tokens_entrada, uso.tokens_saida) == (True, 100, 50)


def test_falha_da_ia_marca_pedido_e_registra_uso(aplicacao, client, ia):
    ia.erro = RuntimeError('fora do ar')
    assert criar_pedido(client).status_code == 503
    with aplicacao.app_context():
        pedido = Session.scalar(select(Pedido))
        assert pedido.status == S.FALHOU
        assert Session.scalar(select(UsoIA)).sucesso is False


def test_transicoes_validas_e_invalidas():
    pedido = Pedido(status=S.RASCUNHO)
    for status in (S.PREVIA_PRONTA, S.AGUARDANDO_PAGAMENTO, S.PAGO, S.GERANDO, S.CONCLUIDO):
        transicionar(pedido, status)
    assert pedido.pago_em is not None and pedido.concluido_em is not None

    with pytest.raises(TransicaoInvalida):
        transicionar(Pedido(status=S.RASCUNHO), S.CONCLUIDO)
    novo = Pedido()  # ainda não salvo: status None conta como rascunho
    transicionar(novo, S.PREVIA_PRONTA)
    assert novo.status == S.PREVIA_PRONTA
    with pytest.raises(TransicaoInvalida):
        transicionar(Pedido(status=S.EXPIRADO), S.CONCLUIDO)
    with pytest.raises(TransicaoInvalida):
        transicionar(Pedido(status=S.REEMBOLSADO), S.AGUARDANDO_PAGAMENTO)


def test_cards_repetidos_sao_ignorados():
    pedido = Pedido()
    adicionar_cards(pedido, [{'pergunta': 'O que é ATP?', 'resposta': 'a'},
                             {'pergunta': 'o que e atp', 'resposta': 'b'},
                             {'pergunta': 'O que é ADP?', 'resposta': 'c'}])
    assert [c.ordem for c in pedido.cards] == [0, 1]
    assert pedido.cards[1].pergunta == 'O que é ADP?'


# 1.5 / 1.6 / 1.7 — exportação em memória

def notas_do_apkg(conteudo, tmp_path):
    with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
        (tmp_path / 'col.anki2').write_bytes(z.read('collection.anki2'))
    con = sqlite3.connect(tmp_path / 'col.anki2')
    try:
        notas = [r[0].split('\x1f') for r in con.execute('select flds from notes')]
        decks = json.loads(con.execute('select decks from col').fetchone()[0])
    finally:
        con.close()
    return notas, decks


def test_apkg_escapa_html_e_usa_id_deterministico(tmp_path):
    conteudo = gerar_apkg('Deck', [('<script>alert(1)</script> & <b>ATP</b>', 'linha 1\nlinha 2')], semente='p1')
    notas, decks = notas_do_apkg(conteudo, tmp_path)
    assert notas == [['&lt;script&gt;alert(1)&lt;/script&gt; &amp; <b>ATP</b>', 'linha 1<br>linha 2']]
    assert str(id_deterministico('p1')) in decks
    assert id_deterministico('p1') == id_deterministico('p1') != id_deterministico('p2')


def test_sanitizar_campo_mantem_so_tags_seguras():
    assert sanitizar_campo('H<sub>2</sub>O <img src=x onerror=1>') == 'H<sub>2</sub>O &lt;img src=x onerror=1&gt;'


def test_pdf_aceita_fontes_com_marcacao():
    assert gerar_pdf_fontes(['Livro <Bioquímica> & cia', 'Artigo <b']).startswith(b'%PDF')


def test_nada_gravado_em_disco_na_geracao(client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    token = gerar_e_pagar(client)
    client.get(url_apkg(token))
    client.get(url_pdf(token))
    assert sorted(os.listdir(tmp_path)) == ['teste.db']


def test_docx_e_txt_viram_texto_no_prompt(client, ia):
    from docx import Document
    buffer = io.BytesIO()
    documento = Document()
    documento.add_paragraph('Conteudo do docx')
    documento.save(buffer)
    client.post('/api/pedidos', data={
        'prompt': 'Resumo', 'quantidade': '2',
        'arquivo_0': (io.BytesIO(buffer.getvalue()), 'aula.docx'),
        'arquivo_1': (io.BytesIO('Conteudo do txt'.encode()), 'notas.txt'),
        'imagem_2': (io.BytesIO(PNG), 'foto.png'),
    }, content_type='multipart/form-data')
    chamada = ia.chamadas[0]
    assert 'Conteudo do docx' in chamada['prompt'] and 'Conteudo do txt' in chamada['prompt']
    assert [a.mime_type for a in chamada['anexos']] == ['image/png']


# Provedor Gemini (google-genai), com o cliente substituído

class ClienteGeminiFalso:
    def __init__(self, erros=()):
        self.configs, self.conteudos, self.apagados = [], [], []
        self.erros = list(erros)
        self.files = SimpleNamespace(upload=self._upload, delete=self._delete)
        self.models = SimpleNamespace(generate_content=self._gerar)

    def _upload(self, file, config):
        return SimpleNamespace(name='files/1', uri='https://arquivos/1', expiration_time=None)

    def _delete(self, name):
        self.apagados.append(name)

    def _gerar(self, model, contents, config):
        self.configs.append(config)
        self.conteudos.append(contents)
        if self.erros:
            raise self.erros.pop(0)
        lote = LoteGerado(cards=[{'pergunta': 'p', 'resposta': 'r'}], fontes=[])
        uso = SimpleNamespace(prompt_token_count=10, candidates_token_count=20, thoughts_token_count=5)
        return SimpleNamespace(parsed=lote, text=lote.model_dump_json(), usage_metadata=uso)


def provedor_com(cliente):
    provedor = GeminiProvider('chave')
    provedor._client = cliente
    return provedor


def test_gemini_usa_saida_estruturada_e_conta_thinking_como_saida():
    cliente = ClienteGeminiFalso()
    resposta = provedor_com(cliente).gerar_json('prompt', LoteGerado, 'modelo-x', thinking_budget=0,
                                                anexos=[Anexo(uri='https://arquivos/9', mime_type='application/pdf')])
    config = cliente.configs[0]
    assert config.response_mime_type == 'application/json' and config.response_schema is LoteGerado
    assert config.thinking_config.thinking_budget == 0
    assert cliente.conteudos[0][1].file_data.file_uri == 'https://arquivos/9'
    assert resposta.dados['cards'] == [{'pergunta': 'p', 'resposta': 'r'}]
    assert (resposta.tokens_entrada, resposta.tokens_saida) == (10, 25)


def test_gemini_classifica_erros():
    sobrecarga = errors.ServerError(503, {'error': {'code': 503, 'status': 'UNAVAILABLE', 'message': 'high demand'}})
    limite = errors.ClientError(429, {'error': {'code': 429, 'status': 'RESOURCE_EXHAUSTED', 'message': 'x'}})
    inexistente = errors.ClientError(404, {'error': {'code': 404, 'status': 'NOT_FOUND', 'message': 'x'}})
    for erro, esperado in ((sobrecarga, IAErroTemporario), (limite, IAErroTemporario),
                           (inexistente, IAErroPermanente)):
        with pytest.raises(esperado):
            provedor_com(ClienteGeminiFalso([erro])).gerar_json('p', LoteGerado, 'm')


def test_gemini_repete_sem_thinking_se_o_modelo_recusar():
    # Mensagem real do gemini-3.5-flash-lite para thinking_budget=0: não cita "thinking"
    recusa = errors.ClientError(400, {'error': {'code': 400, 'status': 'INVALID_ARGUMENT',
                                                'message': 'Request contains an invalid argument.'}})
    cliente = ClienteGeminiFalso([recusa])
    provedor = provedor_com(cliente)
    provedor.gerar_json('p', LoteGerado, 'lite', thinking_budget=0)
    assert cliente.configs[0].thinking_config.thinking_budget == 0
    assert cliente.configs[1].thinking_config is None
    provedor.gerar_json('p', LoteGerado, 'lite', thinking_budget=0)  # já sabe: nem tenta de novo
    assert len(cliente.configs) == 3 and cliente.configs[2].thinking_config is None


def test_gemini_400_sem_thinking_e_permanente():
    invalido = errors.ClientError(400, {'error': {'code': 400, 'status': 'INVALID_ARGUMENT', 'message': 'x'}})
    with pytest.raises(IAErroPermanente):
        provedor_com(ClienteGeminiFalso([invalido])).gerar_json('p', LoteGerado, 'm')


def test_gemini_envia_e_apaga_arquivo():
    cliente = ClienteGeminiFalso()
    provedor = provedor_com(cliente)
    remoto = provedor.enviar_arquivo('a.png', 'image/png')
    assert (remoto.nome, remoto.uri, remoto.mime_type) == ('files/1', 'https://arquivos/1', 'image/png')
    provedor.apagar_arquivo(remoto.nome)
    assert cliente.apagados == ['files/1']


def test_gemini_sem_chave():
    with pytest.raises(IAIndisponivel):
        GeminiProvider('').gerar_json('p', LoteGerado, 'm')
