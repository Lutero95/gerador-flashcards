"""Critérios de aceite da Fase 3: prévia grátis → pagamento → geração em lotes."""
import io
import json
import sqlite3
import zipfile
from datetime import timedelta

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy import select

from app.db import Session
from app.ia.base import IAErroPermanente, IAErroTemporario
from app.ia.material import fatia
from app.models import LoteGeracao, PagamentoFake, Pedido, StatusLote as L, StatusPedido as S, UsoIA, agora
from app.pedidos import adicionar_cards
from conftest import PNG, criar_pedido, executar_lotes, gerar, pedir_pix, simular, url_apkg


def pedido_do_token(token):
    return Session.scalar(select(Pedido).where(Pedido.token_acesso == token))


def pagar(client, token):
    assert pedir_pix(client, token).status_code == 200
    assert simular(client, token, 'aprovar').status_code == 200


def notas_no_apkg(conteudo, tmp_path):
    with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
        (tmp_path / 'col.anki2').write_bytes(z.read('collection.anki2'))
    con = sqlite3.connect(tmp_path / 'col.anki2')
    try:
        return con.execute('select count(*) from notes').fetchone()[0]
    finally:
        con.close()


def pdf(paginas, texto_por_pagina=''):
    buffer = io.BytesIO()
    folha = canvas.Canvas(buffer, pagesize=A4)
    for numero in range(paginas):
        if texto_por_pagina:
            objeto = folha.beginText(40, 800)
            for linha in range(0, len(texto_por_pagina), 90):
                objeto.textLine(texto_por_pagina[linha:linha + 90])
            folha.drawText(objeto)
        else:
            folha.rect(100, 100 + numero * 10, 200, 200, fill=1)  # "escaneado": só imagem, sem texto
        folha.showPage()
    folha.save()
    return buffer.getvalue()


# 3.1 — preço antes de gerar

@pytest.mark.parametrize('quantidade,centavos,faixa', [(10, 390, 50), (51, 690, 100), (5000, 1890, 500)])
def test_preco_antes_de_gerar(client, quantidade, centavos, faixa):
    dados = client.get(f'/api/preco?quantidade={quantidade}').get_json()
    assert (dados['preco_centavos'], dados['faixa_ate']) == (centavos, faixa)
    assert dados['quantidade'] == min(quantidade, 500)


# 3.2 — plano + prévia

def test_previa_gera_plano_e_5_cards_com_modelo_barato(criar_aplicacao):
    aplicacao = criar_aplicacao(MODELO_PREVIA='barato', MODELO_PREVIA_FALLBACK='reserva', THINKING_PREVIA=0)
    client, ia = aplicacao.test_client(), aplicacao.extensions['ia']
    resposta = criar_pedido(client, 100)
    estado = resposta.get_json()

    assert resposta.status_code == 201
    assert estado['status'] == S.PREVIA_PRONTA
    assert len(estado['previa']) == 5
    assert estado['preco_centavos'] == 690  # preço pela quantidade pedida, conhecido antes
    assert sum(s['quantidade'] for s in estado['subtopicos']) == 100
    assert [(c['modelo'], c['thinking']) for c in ia.chamadas] == [('barato', 0)]
    with aplicacao.app_context():
        lotes = pedido_do_token(estado['token']).lotes
        assert [(lote.n, lote.quantidade) for lote in lotes] == [(1, 40), (2, 40), (3, 15)]


def test_lote_exige_pagamento(client):
    token = gerar(client, 100)
    assert client.post(f'/api/pedidos/{token}/lotes/1').status_code == 402
    pedir_pix(client, token)
    assert client.post(f'/api/pedidos/{token}/lotes/1').status_code == 402


def test_geracao_completa_em_lotes(criar_aplicacao, tmp_path):
    aplicacao = criar_aplicacao(MODELO_GERACAO='principal', THINKING_GERACAO=512)
    client, ia = aplicacao.test_client(), aplicacao.extensions['ia']
    token = gerar(client, 100)
    pagar(client, token)

    estado = client.get(f'/api/pedidos/{token}').get_json()
    assert estado['status'] == S.PAGO and estado['proximo_lote'] == 1
    assert client.get(url_apkg(token)).status_code == 403  # ainda gerando

    estado = executar_lotes(client, token)
    assert estado['status'] == S.CONCLUIDO
    assert estado['quantidade_gerada'] == 100
    assert estado['progresso'] == {'lotes_concluidos': 3, 'lotes_total': 3}
    assert notas_no_apkg(client.get(url_apkg(token)).data, tmp_path) == 100

    chamadas_lote = [c for c in ia.chamadas if c['schema'] == 'LoteGerado']
    assert [(c['modelo'], c['thinking']) for c in chamadas_lote] == [('principal', 512)] * 3
    # Cada lote recebe as perguntas já existentes, para não repetir
    assert 'Previa pergunta numero 1 ' in chamadas_lote[0]['prompt']
    assert 'Lote pergunta numero' in chamadas_lote[2]['prompt']
    with aplicacao.app_context():
        etapas = [u.etapa for u in Session.scalars(select(UsoIA).order_by(UsoIA.id))]
        assert etapas == ['previa', 'lote_1', 'lote_2', 'lote_3']


def test_retoma_do_lote_certo_apos_fechar_a_pagina_e_reiniciar(criar_aplicacao):
    primeira = criar_aplicacao().test_client()
    token = gerar(primeira, 100)
    pagar(primeira, token)
    assert primeira.post(f'/api/pedidos/{token}/lotes/1').status_code == 200

    segunda = criar_aplicacao().test_client()  # "reinício" e página reaberta
    estado = segunda.get(f'/api/pedidos/{token}').get_json()
    assert estado['status'] == S.GERANDO and estado['proximo_lote'] == 2
    assert executar_lotes(segunda, token)['status'] == S.CONCLUIDO


def test_lote_ja_gerado_nao_e_refeito(client, ia):
    token = gerar(client, 100)
    pagar(client, token)
    client.post(f'/api/pedidos/{token}/lotes/1')
    chamadas = len(ia.chamadas)
    resposta = client.post(f'/api/pedidos/{token}/lotes/1')
    assert resposta.status_code == 200 and len(ia.chamadas) == chamadas
    assert resposta.get_json()['quantidade_gerada'] == 45


def test_lote_em_andamento_em_outra_aba(aplicacao, client):
    token = gerar(client, 100)
    pagar(client, token)
    with aplicacao.app_context():
        lote = pedido_do_token(token).lotes[0]
        lote.status, lote.iniciado_em = L.GERANDO, agora()
        Session.commit()
    assert client.post(f'/api/pedidos/{token}/lotes/1').status_code == 409

    with aplicacao.app_context():  # a requisição que gerava morreu: lote travado é retomado
        pedido_do_token(token).lotes[0].iniciado_em = agora() - timedelta(minutes=5)
        Session.commit()
    assert client.post(f'/api/pedidos/{token}/lotes/1').status_code == 200


# Retentativa e troca real de modelo

def test_troca_de_modelo_quando_o_principal_esta_sobrecarregado(criar_aplicacao):
    aplicacao = criar_aplicacao(MODELO_PREVIA='principal', MODELO_PREVIA_FALLBACK='reserva')
    ia = aplicacao.extensions['ia']
    ia.falhas = [IAErroTemporario('503'), IAErroTemporario('503'), IAErroTemporario('503')]
    assert criar_pedido(aplicacao.test_client(), 10).status_code == 201
    # Alterna em vez de insistir no modelo sobrecarregado
    assert [c['modelo'] for c in ia.chamadas] == ['principal', 'reserva', 'principal', 'reserva']
    with aplicacao.app_context():
        assert [u.sucesso for u in Session.scalars(select(UsoIA).order_by(UsoIA.id))] == [False, False, False, True]


def test_erro_permanente_vai_direto_para_o_reserva(criar_aplicacao):
    aplicacao = criar_aplicacao(MODELO_PREVIA='inexistente', MODELO_PREVIA_FALLBACK='reserva')
    ia = aplicacao.extensions['ia']
    ia.falhas = [IAErroPermanente('404'), IAErroTemporario('503')]
    assert criar_pedido(aplicacao.test_client(), 10).status_code == 201
    assert [c['modelo'] for c in ia.chamadas] == ['inexistente', 'reserva', 'reserva']  # o 404 sai da fila


def test_previa_falha_sem_cobrar_nada(aplicacao, client, ia):
    ia.erro = IAErroTemporario('503')
    resposta = criar_pedido(client, 10)
    assert resposta.status_code == 503 and 'erro_id' in resposta.get_json()
    with aplicacao.app_context():
        pedido = Session.scalar(select(Pedido))
        assert pedido.status == S.FALHOU and not pedido.pagamentos


def test_lote_que_falha_e_repetido_pelo_front(client, ia):
    token = gerar(client, 100)
    pagar(client, token)
    ia.falhas = [IAErroTemporario('503')] * 4  # os dois modelos, duas vezes cada
    assert client.post(f'/api/pedidos/{token}/lotes/1').status_code == 502
    estado = client.get(f'/api/pedidos/{token}').get_json()
    assert estado['proximo_lote'] == 1  # continua pendente: a página tenta de novo
    assert executar_lotes(client, token)['status'] == S.CONCLUIDO


# Falta de cards: complemento, mínimo de 90% e reembolso

def test_lotes_curtos_sao_completados(client, ia):
    ia.fracao_lote = 0.8
    token = gerar(client, 100)
    pagar(client, token)
    estado = executar_lotes(client, token)
    assert estado['status'] == S.CONCLUIDO
    assert estado['quantidade_gerada'] >= 90


def test_abaixo_de_90_por_cento_oferece_reembolso(aplicacao, client, ia):
    ia.fracao_lote = 0.5
    token = gerar(client, 100)
    pagar(client, token)
    estado = executar_lotes(client, token)
    assert estado['status'] == S.FALHOU
    assert estado['quantidade_gerada'] < 90
    assert estado['resolucao']['parcial']['cards'] == estado['quantidade_gerada']
    assert client.get(url_apkg(token)).status_code == 403
    with aplicacao.app_context():
        rodadas = {lote.rodada for lote in pedido_do_token(token).lotes}
        assert rodadas == {0, 1, 2}  # duas rodadas de complemento antes de desistir


def test_resolucao_parcial_entrega_e_devolve_o_proporcional(aplicacao, client, ia, tmp_path):
    token = gerar(client, 100)
    pagar(client, token)
    ia.erro = IAErroTemporario('fora do ar')
    estado = executar_lotes(client, token)
    assert estado['status'] == S.FALHOU and estado['quantidade_gerada'] == 5

    estado = client.post(f'/api/pedidos/{token}/resolucao', json={'opcao': 'parcial'}).get_json()
    assert estado['status'] == S.CONCLUIDO
    assert estado['reembolso_texto'] == 'R$ 6,56'  # 95% de R$ 6,90
    assert notas_no_apkg(client.get(url_apkg(token)).data, tmp_path) == 5
    with aplicacao.app_context():
        pedido = pedido_do_token(token)
        assert pedido.reembolso_centavos == 656
        assert Session.get(PagamentoFake, pedido.pagamento_ativo.provider_payment_id).status == 'approved'


def test_resolucao_total_reembolsa_tudo(aplicacao, client, ia):
    token = gerar(client, 100)
    pagar(client, token)
    ia.erro = IAErroTemporario('fora do ar')
    executar_lotes(client, token)

    estado = client.post(f'/api/pedidos/{token}/resolucao', json={'opcao': 'total'}).get_json()
    assert estado['status'] == S.REEMBOLSADO and estado['reembolso_texto'] == 'R$ 6,90'
    assert client.get(url_apkg(token)).status_code == 403
    with aplicacao.app_context():
        pagamento = pedido_do_token(token).pagamento_ativo
        assert Session.get(PagamentoFake, pagamento.provider_payment_id).status == 'refunded'
    assert client.post(f'/api/pedidos/{token}/resolucao', json={'opcao': 'total'}).status_code == 409


def test_perguntas_quase_iguais_sao_descartadas():
    pedido = Pedido()
    adicionados = adicionar_cards(pedido, [
        {'pergunta': 'Qual é a função da enzima amilase na digestão?', 'resposta': 'a'},
        {'pergunta': 'Qual é a função da enzima amilase durante a digestão?', 'resposta': 'b'},
        {'pergunta': 'Onde a amilase é produzida?', 'resposta': 'c'},
        {'pergunta': 'Qual é a função da insulina?', 'resposta': 'd'},
        {'pergunta': 'Qual é a função do glucagon?', 'resposta': 'e'},  # parecida, mas é outra pergunta
    ])
    assert adicionados == 4
    assert [c.resposta for c in pedido.cards] == ['a', 'c', 'd', 'e']


# Material enviado: texto extraído e fatiado; escaneado dividido; imagens em todos os lotes

def enviar(client, quantidade, arquivos, **campos):
    dados = {'prompt': 'Resumo da aula', 'quantidade': str(quantidade), **campos}
    for i, (nome, conteudo) in enumerate(arquivos):
        dados[f'arquivo_{i}'] = (io.BytesIO(conteudo), nome)
    return client.post('/api/pedidos', data=dados, content_type='multipart/form-data')


def test_pdf_com_texto_e_extraido_e_fatiado_por_lote(aplicacao, client, ia):
    documento = pdf(3, 'conteudo da aula ' * 40)
    resposta = enviar(client, 100, [('aula.pdf', documento)])
    assert resposta.status_code == 201
    assert ia.enviados == []  # PDF com texto não vai para a IA como arquivo
    token = resposta.get_json()['token']
    assert 'conteudo da aula' in ia.chamadas[0]['prompt']
    with aplicacao.app_context():
        material = pedido_do_token(token).material_texto

    pagar(client, token)
    executar_lotes(client, token)
    with aplicacao.app_context():
        assert pedido_do_token(token).material_texto is None  # descartado ao concluir (LGPD)
    lotes = [c['prompt'] for c in ia.chamadas if c['schema'] == 'LoteGerado']
    assert fatia(material, 3, 0) in lotes[0] and fatia(material, 3, 2) in lotes[2]
    assert fatia(material, 3, 2) not in lotes[0]


def test_fatias_cobrem_o_texto_sem_cortar_palavras():
    texto = ' '.join(f'palavra{i}' for i in range(3000))
    partes = [fatia(texto, 4, i) for i in range(4)]
    assert ' '.join(partes).split() == texto.split()


def test_pdf_escaneado_e_dividido_uma_parte_por_lote(aplicacao, client, ia):
    resposta = enviar(client, 100, [('scan.pdf', pdf(6))])
    token = resposta.get_json()['token']
    assert [e['mime_type'] for e in ia.enviados] == ['application/pdf'] * 3
    assert [a.uri for a in ia.chamadas[0]['anexos']] == ['https://arquivos/1']

    pagar(client, token)
    executar_lotes(client, token)
    lotes = [c for c in ia.chamadas if c['schema'] == 'LoteGerado']
    assert [[a.uri for a in c['anexos']] for c in lotes] == [['https://arquivos/1'], ['https://arquivos/2'],
                                                             ['https://arquivos/3']]
    assert sorted(ia.apagados) == ['files/1', 'files/2', 'files/3']  # apagados após a geração


def test_imagens_vao_para_todos_os_lotes(client, ia):
    token = enviar(client, 100, [('quadro.png', PNG)]).get_json()['token']
    pagar(client, token)
    executar_lotes(client, token)
    assert all([a.uri for a in c['anexos']] == ['https://arquivos/1'] for c in ia.chamadas)


def test_pdf_invalido_e_recusado(client, ia):
    resposta = enviar(client, 10, [('quebrado.pdf', b'isto nao e um pdf')])
    assert resposta.status_code == 400 and 'quebrado.pdf' in resposta.get_json()['erro']
    # Com assinatura de PDF, mas corrompido: cai na leitura do PDF
    resposta = enviar(client, 10, [('corrompido.pdf', b'%PDF-1.4 lixo')])
    assert resposta.status_code == 400 and 'PDF' in resposta.get_json()['erro']
    assert ia.chamadas == []


def test_texto_colado_vira_material(aplicacao, client, ia):
    token = gerar(client, 10, texto='Anotações coladas pelo aluno sobre mitose')
    assert 'Anotações coladas pelo aluno sobre mitose' in ia.chamadas[0]['prompt']
    with aplicacao.app_context():
        assert pedido_do_token(token).tipo_entrada == 'texto'


def test_material_expirado_impede_pagamento(aplicacao, client):
    token = enviar(client, 10, [('quadro.png', PNG)]).get_json()['token']
    with aplicacao.app_context():
        pedido = pedido_do_token(token)
        referencias = [dict(r, expira_em=(agora() + timedelta(hours=1)).isoformat())
                       for r in pedido.referencias_arquivos]
        pedido.referencias_arquivos = referencias
        Session.commit()
    resposta = pedir_pix(client, token)
    assert resposta.status_code == 409 and 'nova prévia' in resposta.get_json()['erro']


def test_pedido_pequeno_conclui_no_pagamento(client):
    token = gerar(client, 5)
    pagar(client, token)
    estado = client.get(f'/api/pedidos/{token}').get_json()
    assert estado['status'] == S.CONCLUIDO and estado['proximo_lote'] is None


def test_previa_nao_mostra_cards_dos_lotes(client):
    token = gerar(client, 100)
    pagar(client, token)
    client.post(f'/api/pedidos/{token}/lotes/1')
    estado = client.get(f'/api/pedidos/{token}').get_json()
    assert len(estado['previa']) == 5 and estado['quantidade_gerada'] == 45


def test_chamadas_respeitam_o_prazo_da_requisicao(criar_aplicacao, monkeypatch):
    from app.ia import geracao
    relogio = iter([0, 0, 38, 38, 38, 38])  # a 2ª tentativa começaria com só 7 s restando
    monkeypatch.setattr(geracao.time, 'monotonic', lambda: next(relogio))
    aplicacao = criar_aplicacao(TEMPO_MAX_LOTE_S=45)
    ia = aplicacao.extensions['ia']
    ia.erro = IAErroTemporario('503')
    assert criar_pedido(aplicacao.test_client(), 10).status_code == 503
    # 1ª chamada: 45 s de prazo menos 15 s reservados ao reserva; depois restam só 7 s e ela desiste
    assert len(ia.chamadas) == 1 and ia.chamadas[0]['timeout'] == 30



def test_timeout_do_principal_nao_consome_o_tempo_do_reserva(criar_aplicacao, monkeypatch):
    """Caso real (28/09/2026): 503 rápido, depois ReadTimeout no mesmo modelo e o reserva nunca rodava."""
    from app.ia import geracao
    agora_s = [0.0]
    monkeypatch.setattr(geracao.time, 'monotonic', lambda: agora_s[0])
    aplicacao = criar_aplicacao(MODELO_PREVIA='principal', MODELO_PREVIA_FALLBACK='reserva', TEMPO_MAX_LOTE_S=45)
    ia = aplicacao.extensions['ia']
    original = ia.gerar_json

    def gerar_com_relogio(prompt, schema, modelo, anexos=None, thinking_budget=None, timeout_s=None):
        if modelo == 'principal':
            ia.chamadas.append({'modelo': modelo, 'timeout': timeout_s, 'schema': 'x', 'prompt': ''})
            agora_s[0] += timeout_s  # o principal fica pendurado até o timeout
            raise IAErroTemporario('ReadTimeout')
        return original(prompt, schema, modelo, anexos, thinking_budget, timeout_s)

    ia.gerar_json = gerar_com_relogio
    assert criar_pedido(aplicacao.test_client(), 10).status_code == 201
    assert [(c['modelo'], c['timeout']) for c in ia.chamadas] == [('principal', 30), ('reserva', 15)]
