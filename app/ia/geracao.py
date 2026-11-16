"""Orquestra a geração: plano + prévia (grátis) e, após o pagamento, lotes conduzidos pelo front.

Regras de custo (ANALISE_PRECOS_E_CUSTOS.md): prévia com o modelo mais barato e sem raciocínio;
lotes com raciocínio limitado; material fatiado por lote; troca de modelo quando o principal falha.
"""
import logging
import math
import time
from datetime import timedelta

from flask import current_app
from sqlalchemy import select

from app.db import Session
from app.ia.base import IAErroPermanente, IAErroTemporario, IAIndisponivel
from app.ia.material import anexos_para, apagar_remotos, fatia
from app.ia.prompts import LoteGerado, PlanoPrevia, prompt_lote, prompt_previa
from app.models import LoteGeracao, Pedido, StatusLote as L, StatusPedido as S, TipoEntrada, UsoIA, agora
from app.pedidos import adicionar_cards, transicionar
from app.seguranca import estimar_custo_usd

logger = logging.getLogger('gerador_flashcards')

TENTATIVAS_POR_MODELO = 2
ESPERA_ENTRE_TENTATIVAS_S = 1
TEMPO_MINIMO_CHAMADA_S = 10  # com menos que isso restando no prazo, não vale começar outra chamada
RESERVA_PARA_PROXIMA_S = 15  # tempo guardado para a próxima tentativa (ex.: o modelo reserva)
MAX_TENTATIVAS_LOTE = 2  # requisições do front; cada uma já tenta os dois modelos
MAX_RODADAS_COMPLEMENTO = 2
LOTE_TRAVADO = timedelta(seconds=90)  # lote "gerando" há mais que isso: a requisição morreu
MAX_PERGUNTAS_CONTEXTO = 200
FONTE_PADRAO = 'Informações geradas com base em conhecimento geral'

_dormir = time.sleep  # substituído nos testes


class PreviaVazia(RuntimeError):
    pass


def modelos(chave):
    cfg = current_app.config
    return list(dict.fromkeys(m for m in (cfg[chave], cfg[f'{chave}_FALLBACK']) if m))


def thinking(chave):
    valor = current_app.config[chave]
    return None if valor < 0 else valor


def chamar_ia(pedido_id, etapa, prompt, schema, lista_modelos, anexos, thinking_budget):
    """Chama a IA com retentativa e troca real de modelo, dentro do prazo de uma requisição.

    Os modelos se alternam (principal, reserva, principal, reserva): repetir de imediato um modelo
    sobrecarregado costuma falhar de novo. Enquanto houver outra tentativa na fila, cada chamada deixa
    RESERVA_PARA_PROXIMA_S do prazo livre, para um timeout não consumir o tempo do modelo reserva.
    Toda chamada (com ou sem sucesso) fica registrada em UsoIA.
    """
    ia = current_app.extensions['ia']
    prazo = current_app.config['TEMPO_MAX_LOTE_S']
    inicio = time.monotonic()
    ultimo_erro = None
    fila = [modelo for _ in range(TENTATIVAS_POR_MODELO) for modelo in lista_modelos]
    descartados = set()  # modelos com erro permanente não voltam para a fila

    for posicao, modelo in enumerate(fila):
        if modelo in descartados:
            continue
        if posicao >= len(lista_modelos):
            _dormir(ESPERA_ENTRE_TENTATIVAS_S)  # segunda volta: dá um respiro ao provedor
        restante = prazo - (time.monotonic() - inicio)
        if restante < TEMPO_MINIMO_CHAMADA_S:
            raise IAErroTemporario('prazo da requisição esgotado') from ultimo_erro
        ha_proxima = any(m not in descartados for m in fila[posicao + 1:])
        timeout = restante
        if ha_proxima and restante - RESERVA_PARA_PROXIMA_S >= TEMPO_MINIMO_CHAMADA_S:
            timeout = restante - RESERVA_PARA_PROXIMA_S
        try:
            resposta = ia.gerar_json(prompt, schema, modelo, anexos=anexos, thinking_budget=thinking_budget,
                                     timeout_s=timeout)
        except IAIndisponivel:
            raise
        except IAErroPermanente as erro:
            Session.add(UsoIA(pedido_id=pedido_id, etapa=etapa, modelo=modelo, sucesso=False))
            logger.warning('IA %s falhou em %s (permanente): %s', modelo, etapa, erro)
            ultimo_erro = erro
            descartados.add(modelo)
            continue
        except Exception as erro:
            Session.add(UsoIA(pedido_id=pedido_id, etapa=etapa, modelo=modelo, sucesso=False))
            logger.warning('IA %s falhou em %s (tentativa %d): %s', modelo, etapa, posicao + 1, erro)
            ultimo_erro = erro
            continue
        Session.add(UsoIA(
            pedido_id=pedido_id, etapa=etapa, modelo=resposta.modelo,
            tokens_entrada=resposta.tokens_entrada, tokens_saida=resposta.tokens_saida,
            custo_estimado_usd=estimar_custo_usd(resposta.modelo, resposta.tokens_entrada, resposta.tokens_saida),
            latencia_ms=resposta.latencia_ms, sucesso=True,
        ))
        return resposta

    if isinstance(ultimo_erro, (IAErroTemporario, IAErroPermanente)):
        raise ultimo_erro
    raise IAErroTemporario(f'todas as tentativas falharam: {ultimo_erro}') from ultimo_erro


def limpar_cards(cards):
    return [
        {'pergunta': c['pergunta'].strip(), 'resposta': c['resposta'].strip()}
        for c in cards
        if c.get('pergunta', '').strip() and c.get('resposta', '').strip()
    ]


def mesclar_fontes(atuais, novas):
    fontes = [f.strip() for f in (atuais or []) + (novas or []) if f and f.strip()]
    fontes = [f for f in dict.fromkeys(fontes) if f != FONTE_PADRAO]
    return fontes or [FONTE_PADRAO]


def normalizar_subtopicos(lista, total, assunto):
    """Distribui exatamente `total` cards entre os subtópicos, respeitando as proporções pedidas."""
    validos = []
    for item in lista or []:
        nome = str(item.get('nome', '')).strip()[:150]
        try:
            quantidade = max(0, int(item.get('quantidade', 0)))
        except (TypeError, ValueError):
            quantidade = 0
        if nome:
            validos.append((nome, quantidade))
    validos = validos[:max(total, 1)]
    soma = sum(q for _, q in validos)
    if not validos or soma == 0 or total <= 0:
        return [{'nome': assunto[:150], 'quantidade': max(total, 0)}]

    brutos = [q * total / soma for _, q in validos]
    inteiros = [math.floor(b) for b in brutos]
    # Maiores restos recebem o que sobrou do arredondamento
    for indice in sorted(range(len(brutos)), key=lambda i: brutos[i] - inteiros[i], reverse=True)[:total - sum(inteiros)]:
        inteiros[indice] += 1
    return [{'nome': nome, 'quantidade': q} for (nome, _), q in zip(validos, inteiros) if q > 0]


def dividir_em_lotes(subtopicos, tamanho):
    """[{nome, quantidade}] -> lista de lotes, cada um com até `tamanho` cards (subtópicos podem ser divididos)."""
    lotes, atual, espaco = [], [], tamanho
    for sub in subtopicos:
        restante = sub['quantidade']
        while restante > 0:
            usar = min(restante, espaco)
            atual.append({'nome': sub['nome'], 'quantidade': usar})
            restante -= usar
            espaco -= usar
            if espaco == 0:
                lotes.append(atual)
                atual, espaco = [], tamanho
    if atual:
        lotes.append(atual)
    return lotes


def numero_de_lotes(quantidade):
    """Quantos lotes um pedido terá (usado para dividir o material antes da prévia)."""
    cfg = current_app.config
    return math.ceil(max(0, quantidade - min(cfg['TAMANHO_PREVIA'], quantidade)) / cfg['TAMANHO_LOTE'])


def gerar_previa(pedido):
    """Plano de subtópicos + os primeiros cards (grátis), com o modelo mais barato e sem raciocínio."""
    cfg = current_app.config
    total = pedido.quantidade_solicitada
    tamanho = min(cfg['TAMANHO_PREVIA'], total)
    amostra = (pedido.material_texto or '')[:cfg['LIMITE_CARACTERES_PREVIA']]
    anexos = anexos_para(pedido.referencias_arquivos, 0)

    resposta = chamar_ia(pedido.id, 'previa', prompt_previa(pedido.prompt, total, tamanho, amostra, bool(anexos)),
                         PlanoPrevia, modelos('MODELO_PREVIA'), anexos, thinking('THINKING_PREVIA'))
    dados = resposta.dados

    pedido.nome_deck = (dados.get('nome_deck') or '').strip()[:200] or 'Flashcards'
    pedido.fontes = mesclar_fontes([], dados.get('fontes'))
    adicionar_cards(pedido, limpar_cards(dados.get('cards', [])), lote=0, limite=tamanho)
    if not pedido.cards:
        raise PreviaVazia('a IA não devolveu cards na prévia')

    subtopicos = normalizar_subtopicos(dados.get('subtopicos'), total, pedido.prompt)
    pedido.plano_subtopicos = subtopicos
    montar_lotes(pedido, subtopicos)


def buscar_previa_em_cache(prompt_hash, quantidade):
    """Prévia recente do mesmo tema e quantidade (sem arquivos), para reaproveitar sem chamar a IA."""
    horas = current_app.config['CACHE_PREVIA_HORAS']
    if horas <= 0:
        return None
    candidatos = Session.scalars(
        select(Pedido).where(
            Pedido.prompt_hash == prompt_hash,
            Pedido.quantidade_solicitada == quantidade,
            Pedido.tipo_entrada == TipoEntrada.TEMA,
            Pedido.nome_deck.is_not(None),
            Pedido.criado_em >= agora() - timedelta(hours=horas),
        ).order_by(Pedido.criado_em.desc()).limit(5))
    return next((p for p in candidatos if any(c.lote == 0 for c in p.cards) and p.plano_subtopicos), None)


def copiar_previa(pedido, origem):
    pedido.nome_deck = origem.nome_deck
    pedido.fontes = list(origem.fontes or [])
    pedido.plano_subtopicos = [dict(s) for s in origem.plano_subtopicos]
    adicionar_cards(pedido, [{'pergunta': c.pergunta, 'resposta': c.resposta} for c in origem.cards if c.lote == 0])
    montar_lotes(pedido, pedido.plano_subtopicos)


def novo_lote(n, subtopicos, rodada):
    """Lote com todos os campos preenchidos: os defaults das colunas só valem depois do INSERT, e o lote
    pode ser consultado antes disso (ex.: compra direta, que monta e usa os lotes na mesma requisição)."""
    return LoteGeracao(n=n, quantidade=sum(s['quantidade'] for s in subtopicos), subtopicos=subtopicos,
                       rodada=rodada, status=L.PENDENTE, tentativas=0)


def montar_lotes(pedido, subtopicos):
    """Desconta a prévia dos primeiros subtópicos e divide o restante em lotes."""
    ja_gerados = len(pedido.cards)
    fila = []
    for sub in subtopicos:
        desconto = min(sub['quantidade'], ja_gerados)
        ja_gerados -= desconto
        if sub['quantidade'] - desconto > 0:
            fila.append({'nome': sub['nome'], 'quantidade': sub['quantidade'] - desconto})
    for n, subs in enumerate(dividir_em_lotes(fila, current_app.config['TAMANHO_LOTE']), start=1):
        pedido.lotes.append(novo_lote(n, subs, rodada=0))


def lotes_planejados(pedido):
    return max(1, sum(1 for lote in pedido.lotes if lote.rodada == 0))


def travado(lote):
    return lote.status == L.GERANDO and (lote.iniciado_em is None or agora() - lote.iniciado_em > LOTE_TRAVADO)


def proximo_lote(pedido):
    """O próximo lote que o front deve pedir (None se não há nada a gerar)."""
    if pedido.status not in (S.PAGO, S.GERANDO):
        return None
    return next((lote for lote in pedido.lotes if lote.status in (L.PENDENTE, L.GERANDO)), None)


def executar_lote(pedido, lote):
    """Gera os cards de um lote com a fatia de material correspondente. Devolve quantos entraram."""
    indice = lote.n - 1
    material = fatia(pedido.material_texto, lotes_planejados(pedido), indice) if pedido.material_texto else None
    anexos = anexos_para(pedido.referencias_arquivos, indice)
    perguntas = [c.pergunta[:120] for c in pedido.cards][-MAX_PERGUNTAS_CONTEXTO:]

    prompt = prompt_lote(pedido.prompt, pedido.nome_deck, lote.quantidade, lote.subtopicos, perguntas,
                         material, bool(anexos))
    resposta = chamar_ia(pedido.id, f'lote_{lote.n}', prompt, LoteGerado, modelos('MODELO_GERACAO'), anexos,
                         thinking('THINKING_GERACAO'))

    faltam = pedido.quantidade_solicitada - len(pedido.cards)
    adicionados = adicionar_cards(pedido, limpar_cards(resposta.dados.get('cards', [])), lote=lote.n,
                                  limite=min(lote.quantidade, max(faltam, 0)))
    pedido.fontes = mesclar_fontes(pedido.fontes, resposta.dados.get('fontes'))
    return adicionados


def processar_lote(pedido, lote):
    """Executa o lote e atualiza seu estado. Devolve True se gerou, False se falhou."""
    if pedido.status == S.PAGO:
        transicionar(pedido, S.GERANDO)
    lote.status = L.GERANDO
    lote.tentativas += 1
    lote.iniciado_em = agora()
    Session.commit()

    try:
        executar_lote(pedido, lote)
    except Exception:
        logger.exception('Lote %d do pedido %s falhou (tentativa %d)', lote.n, pedido.id, lote.tentativas)
        lote.status = L.FALHOU if lote.tentativas >= MAX_TENTATIVAS_LOTE else L.PENDENTE
        finalizar_se_possivel(pedido)
        Session.commit()
        return False

    lote.status = L.CONCLUIDO
    lote.concluido_em = agora()
    finalizar_se_possivel(pedido)
    Session.commit()
    return True


def finalizar_se_possivel(pedido):
    """Sem lotes em aberto: completa o que faltou, conclui ou marca como falha."""
    if pedido.status != S.GERANDO or any(lote.status in (L.PENDENTE, L.GERANDO) for lote in pedido.lotes):
        return

    cfg = current_app.config
    total = pedido.quantidade_solicitada
    faltam = total - len(pedido.cards)
    rodada = max((lote.rodada for lote in pedido.lotes), default=0) + 1

    if faltam > 0 and rodada <= MAX_RODADAS_COMPLEMENTO:
        subtopicos = normalizar_subtopicos(pedido.plano_subtopicos, faltam, pedido.prompt)
        proximo_n = max((lote.n for lote in pedido.lotes), default=0) + 1
        for deslocamento, subs in enumerate(dividir_em_lotes(subtopicos, cfg['TAMANHO_LOTE'])):
            pedido.lotes.append(novo_lote(proximo_n + deslocamento, subs, rodada))
        return

    if len(pedido.cards) >= math.ceil(cfg['ENTREGA_MINIMA'] * total):
        concluir(pedido)
    else:
        transicionar(pedido, S.FALHOU)
        descartar_material(pedido)
        logger.error('Pedido %s falhou: %d de %d cards', pedido.id, len(pedido.cards), total)


def descartar_material(pedido):
    """Terminada a geração, o material do aluno não fica guardado: nem no provedor, nem no banco (LGPD)."""
    apagar_remotos(current_app.extensions['ia'], pedido.referencias_arquivos)
    pedido.material_texto = None


def concluir(pedido):
    transicionar(pedido, S.CONCLUIDO)
    pedido.expira_em = agora() + timedelta(days=current_app.config['DIAS_RETENCAO_PEDIDO'])
    descartar_material(pedido)


def apos_pagamento(pedido):
    """Chamado quando o pagamento é confirmado. Sem lotes a gerar (pedido pequeno), conclui na hora."""
    if not pedido.plano_subtopicos and not pedido.cards and not pedido.lotes:
        # Compra direta, sem prévia (prévias esgotadas): o plano é o próprio assunto, dividido em lotes
        pedido.plano_subtopicos = normalizar_subtopicos([], pedido.quantidade_solicitada, pedido.prompt)
        montar_lotes(pedido, pedido.plano_subtopicos)
    if any(lote.status in (L.PENDENTE, L.GERANDO) for lote in pedido.lotes):
        return  # o front conduz os lotes a partir da página do pedido
    transicionar(pedido, S.GERANDO)
    finalizar_se_possivel(pedido)
