"""Regras do pedido: máquina de estados e efeitos de uma mudança no pagamento."""
import hashlib
import re
import unicodedata

from app.models import Card, StatusPedido as S, agora

# Única fonte de verdade das transições permitidas
TRANSICOES = {
    S.RASCUNHO: {S.PREVIA_PRONTA, S.FALHOU, S.EXPIRADO},
    S.PREVIA_PRONTA: {S.AGUARDANDO_PAGAMENTO, S.EXPIRADO},
    S.AGUARDANDO_PAGAMENTO: {S.PAGO, S.EXPIRADO},
    # Só volta a aguardar com um novo Pix. EXPIRADO -> PAGO cobre o Pix que o provedor confirmou
    # como pago no limite do prazo: o dinheiro entrou, então o pedido é entregue.
    S.EXPIRADO: {S.AGUARDANDO_PAGAMENTO, S.PAGO},
    S.PAGO: {S.GERANDO, S.FALHOU, S.REEMBOLSADO},
    S.GERANDO: {S.CONCLUIDO, S.FALHOU},
    # FALHOU -> CONCLUIDO: o cliente escolheu ficar com os cards gerados + reembolso proporcional
    S.FALHOU: {S.GERANDO, S.REEMBOLSADO, S.CONCLUIDO},
    S.CONCLUIDO: {S.REEMBOLSADO},
    S.REEMBOLSADO: set(),
}


class TransicaoInvalida(Exception):
    pass


def transicionar(pedido, novo_status):
    # O default da coluna só é aplicado no INSERT: um pedido ainda não salvo está em rascunho
    atual = pedido.status or S.RASCUNHO
    if novo_status not in TRANSICOES[atual]:
        raise TransicaoInvalida(f'{atual} -> {novo_status}')
    pedido.status = novo_status
    if novo_status == S.PAGO:
        pedido.pago_em = agora()
    elif novo_status == S.CONCLUIDO:
        pedido.concluido_em = agora()


def normalizar_texto(texto):
    """Minúsculas, sem acentos e sem pontuação: base da deduplicação de perguntas."""
    sem_acento = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[^a-z0-9]+', ' ', sem_acento.lower()).strip()


def hash_texto(texto):
    return hashlib.sha256(texto.encode('utf-8')).hexdigest()


# Perguntas com essa sobreposição de palavras (Jaccard) são consideradas a mesma pergunta
LIMIAR_SIMILARIDADE = 0.8


def palavras(texto):
    return {p for p in normalizar_texto(texto).split() if len(p) > 2}


def similares(a, b):
    if not a or not b:
        return False
    return len(a & b) / len(a | b) >= LIMIAR_SIMILARIDADE


def adicionar_cards(pedido, cards, lote=0, limite=None):
    """Anexa cards ao pedido, ignorando perguntas repetidas (texto igual ou quase igual).

    Devolve quantos cards foram adicionados (no máximo `limite`, se informado).
    """
    existentes = {c.hash_normalizado for c in pedido.cards}
    conjuntos = [palavras(c.pergunta) for c in pedido.cards]
    ordem = len(pedido.cards)
    adicionados = 0
    for card in cards:
        if limite is not None and adicionados >= limite:
            break
        h = hash_texto(normalizar_texto(card['pergunta']))
        conjunto = palavras(card['pergunta'])
        if h in existentes or any(similares(conjunto, outro) for outro in conjuntos):
            continue
        existentes.add(h)
        conjuntos.append(conjunto)
        pedido.cards.append(Card(ordem=ordem, pergunta=card['pergunta'], resposta=card['resposta'],
                                 lote=lote, hash_normalizado=h))
        ordem += 1
        adicionados += 1
    return adicionados

