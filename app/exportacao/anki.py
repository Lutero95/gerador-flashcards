"""Gera o .apkg em memória a partir dos cards."""
import hashlib
import html
import re
from io import BytesIO

import genanki

# Tipo de nota fixo: baixar vários baralhos não cria um tipo de nota novo no Anki a cada vez
MODELO_ID = 1607392319

MODELO = genanki.Model(
    MODELO_ID,
    'Gerador de Flashcards - Básico',
    fields=[
        {'name': 'Pergunta'},
        {'name': 'Resposta'},
    ],
    templates=[
        {
            'name': 'Card 1',
            'qfmt': '<div style="font-family: arial; font-size: 20px; text-align: center; color: black; background-color: white;">{{Pergunta}}</div>',
            'afmt': '{{FrontSide}}<hr id="answer"><div style="font-family: arial; font-size: 20px; text-align: center; color: navy; background-color: white;">{{Resposta}}</div>',
        },
    ],
    css='''
        .card {
            font-family: arial;
            font-size: 20px;
            text-align: center;
            color: black;
            background-color: white;
        }
    '''
)

_TAGS_SEGURAS = re.compile(r'&lt;(/?)(b|i|u|br|sub|sup)\s*/?&gt;', re.IGNORECASE)


def sanitizar_campo(texto):
    """Escapa HTML, preservando só marcações simples (b, i, u, br, sub, sup) e quebras de linha."""
    escapado = html.escape(str(texto), quote=False)
    escapado = _TAGS_SEGURAS.sub(lambda m: f'<{m.group(1)}{m.group(2).lower()}>', escapado)
    return escapado.replace('\r\n', '\n').replace('\n', '<br>')


def id_deterministico(semente):
    """ID de deck estável: baixar o mesmo pedido de novo atualiza o baralho em vez de duplicar."""
    valor = int(hashlib.sha256(semente.encode('utf-8')).hexdigest()[:12], 16)
    return (1 << 30) + valor % (1 << 30)


def gerar_apkg(nome_deck, cards, semente):
    """cards: iterável de (pergunta, resposta). semente: identifica o baralho (ex.: pedido.id)."""
    deck = genanki.Deck(id_deterministico(semente), nome_deck or 'Flashcards')
    for pergunta, resposta in cards:
        deck.add_note(genanki.Note(model=MODELO, fields=[sanitizar_campo(pergunta), sanitizar_campo(resposta)]))

    buffer = BytesIO()
    genanki.Package(deck).write_to_file(buffer)
    return buffer.getvalue()
