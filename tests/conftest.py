import os
import re
import sys
from datetime import timedelta

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from app import create_app  # noqa: E402
from app.db import Base, Session  # noqa: E402
from app.ia import geracao  # noqa: E402
from app.ia.base import ArquivoRemoto, RespostaIA  # noqa: E402
from app.models import agora  # noqa: E402


class IAFalsa:
    """Provedor de IA sem rede. Responde conforme o schema (prévia ou lote) com perguntas únicas.

    - falhas: exceções levantadas, uma por chamada, antes de voltar a responder normalmente
    - erro: exceção levantada em toda chamada
    - fracao_lote: fração dos cards pedidos que um lote devolve (simula resposta curta)
    """
    nome = 'falsa'

    def __init__(self):
        self.chamadas = []
        self.falhas = []
        self.erro = None
        self.fracao_lote = 1.0
        self.enviados = []
        self.apagados = []
        self._contador = 0

    def _cards(self, quantidade, prefixo):
        cards = []
        for _ in range(quantidade):
            self._contador += 1
            cards.append({'pergunta': f'{prefixo} pergunta numero {self._contador} sobre tema{self._contador}',
                          'resposta': f'Resposta {self._contador}'})
        return cards

    def gerar_json(self, prompt, schema, modelo, anexos=None, thinking_budget=None, timeout_s=None):
        self.chamadas.append({'prompt': prompt, 'schema': schema.__name__, 'modelo': modelo,
                              'anexos': anexos or [], 'thinking': thinking_budget, 'timeout': timeout_s})
        if self.falhas:
            raise self.falhas.pop(0)
        if self.erro:
            raise self.erro
        pedidos = int(re.search(r'EXATAMENTE (\d+)', prompt).group(1))
        if schema.__name__ == 'PlanoPrevia':
            total = int(re.search(r'TOTAL DO BARALHO: (\d+)', prompt).group(1))
            dados = {'nome_deck': 'Deck de Teste', 'fontes': ['Fonte A'],
                     'subtopicos': [{'nome': 'Fundamentos', 'quantidade': total // 2},
                                    {'nome': 'Aplicações', 'quantidade': total - total // 2}],
                     'cards': self._cards(pedidos, 'Previa')}
        else:
            dados = {'cards': self._cards(int(pedidos * self.fracao_lote), 'Lote'), 'fontes': ['Fonte B']}
        return RespostaIA(dados=dados, modelo=modelo, tokens_entrada=100, tokens_saida=50, latencia_ms=7)

    def enviar_arquivo(self, caminho, mime_type):
        with open(caminho, 'rb') as f:
            conteudo = f.read()
        self.enviados.append({'caminho': caminho, 'mime_type': mime_type, 'tamanho': len(conteudo)})
        n = len(self.enviados)
        return ArquivoRemoto(nome=f'files/{n}', uri=f'https://arquivos/{n}', mime_type=mime_type,
                             expira_em=agora() + timedelta(hours=48))

    def apagar_arquivo(self, nome):
        self.apagados.append(nome)


@pytest.fixture
def db_url(tmp_path):
    return f'sqlite:///{(tmp_path / "teste.db").as_posix()}'


@pytest.fixture
def criar_aplicacao(db_url, monkeypatch):
    """Cria apps apontando para o mesmo banco (simula reinícios do servidor).

    Por padrão usa o FakePaymentProvider real, em modo desenvolvimento, e uma IA falsa.
    """
    monkeypatch.setattr(geracao, '_dormir', lambda segundos: None)

    def fabrica(**config):
        aplicacao = create_app({'DATABASE_URL': db_url, 'TESTING': True, 'APP_ENV': 'development',
                                'PAYMENT_PROVIDER': 'fake', 'MAX_CARDS': 500, 'TAMANHO_PREVIA': 5,
                                'TAMANHO_LOTE': 40, 'TURNSTILE_SECRET': '', 'TURNSTILE_SITE_KEY': '',
                                # Anti-abuso desligado por padrão; os testes da Fase 4 ligam o que testam
                                'PREVIAS_POR_DIA': 1000, 'PREVIAS_POR_DIA_IP': 1000, 'CACHE_PREVIA_HORAS': 0,
                                'ORCAMENTO_PREVIAS_USD_DIA': 1000.0, 'LIMITE_CRIAR_PEDIDO_MIN': 1000,
                                'LIMITE_CONSULTA_MIN': 1000, 'LIMITE_ACOES_MIN': 1000, **config})
        Base.metadata.create_all(aplicacao.extensions['db_engine'])
        aplicacao.extensions['ia'] = IAFalsa()
        return aplicacao

    yield fabrica
    Session.remove()


@pytest.fixture
def aplicacao(criar_aplicacao):
    return criar_aplicacao()


@pytest.fixture
def client(aplicacao):
    return aplicacao.test_client()


@pytest.fixture
def ia(aplicacao):
    return aplicacao.extensions['ia']


# Atalhos do fluxo: prévia → Pix → pagamento simulado → lotes

def criar_pedido(client, quantidade=2, **extra):
    return client.post('/api/pedidos', json={'prompt': 'Enzimas', 'quantidade': quantidade, **extra})


def gerar(client, quantidade=2, **extra):
    resposta = criar_pedido(client, quantidade, **extra)
    assert resposta.status_code == 201, resposta.get_json()
    return resposta.get_json()['token']


def pedir_pix(client, token, email='aluno@exemplo.com'):
    return client.post(f'/api/pedidos/{token}/pagamento', json={'email': email})


def simular(client, token, acao):
    """Simula aprovar/recusar/expirar o Pix ativo do pedido pelas rotas de desenvolvimento."""
    pix = client.get(f'/api/pedidos/{token}').get_json()['pix']
    return client.post(f'/dev/pagamentos/{pix["id_teste"]}/{acao}')


def executar_lotes(client, token, limite=50):
    """Faz o que a página do pedido faz: pede o próximo lote até não haver mais."""
    estado = client.get(f'/api/pedidos/{token}').get_json()
    for _ in range(limite):
        if not estado['proximo_lote']:
            return estado
        resposta = client.post(f'/api/pedidos/{token}/lotes/{estado["proximo_lote"]}')
        estado = resposta.get_json() if resposta.get_json().get('token') else client.get(
            f'/api/pedidos/{token}').get_json()
    raise AssertionError('lotes não terminaram')


def gerar_e_pagar(client, quantidade=2):
    token = gerar(client, quantidade)
    assert pedir_pix(client, token).status_code == 200
    assert simular(client, token, 'aprovar').status_code == 200
    executar_lotes(client, token)
    return token


def url_apkg(token):
    return f'/api/pedidos/{token}/baralho.apkg'


PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 16  # começo de um PNG válido (o servidor confere os magic bytes)


def url_pdf(token):
    return f'/api/pedidos/{token}/fontes.pdf'
