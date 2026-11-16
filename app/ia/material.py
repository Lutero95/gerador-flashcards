"""Material enviado pelo aluno: extrai texto no servidor e envia ao provedor só o que não é texto.

O texto é guardado no pedido e fatiado entre os lotes (cada lote recebe só a sua fatia).
Imagens e PDFs escaneados vão para a Files API; o PDF escaneado é dividido em partes, uma por lote,
para não reenviar o documento inteiro a cada chamada (ver ANALISE_PRECOS_E_CUSTOS.md, seção 3.3).
"""
import logging
import os
from datetime import datetime, timedelta

from docx import Document
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

from app.ia.base import Anexo
from app.models import agora

logger = logging.getLogger('gerador_flashcards')

MIME_IMAGEM = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp'}
EXTENSOES_TEXTO = {'.txt', '.md', '.docx'}
# Abaixo disso, em média por página, o PDF é tratado como escaneado (imagem) e vai para a IA como arquivo
MIN_CARACTERES_POR_PAGINA = 200

# Páginas de PDF aceitas por faixa de cards (ANALISE_PRECOS_E_CUSTOS.md, seção 5.2): material enorme para
# poucos cards é o caso que mais custa (e o que mais convida abuso)
LIMITE_PAGINAS = [(50, 30), (100, 50), (200, 100), (500, 300)]

ASSINATURAS = {
    '.pdf': (b'%PDF',),
    '.png': (b'\x89PNG\r\n\x1a\n',),
    '.jpg': (b'\xff\xd8\xff',),
    '.jpeg': (b'\xff\xd8\xff',),
    '.docx': (b'PK\x03\x04',),
}


def limite_paginas(quantidade):
    return next((paginas for ate, paginas in LIMITE_PAGINAS if quantidade <= ate), LIMITE_PAGINAS[-1][1])


def conferir_conteudo(nome, caminho):
    """Confere se o conteúdo bate com a extensão (magic bytes): um .pdf tem de começar como PDF."""
    extensao = os.path.splitext(caminho)[1].lower()
    with open(caminho, 'rb') as f:
        inicio = f.read(12)
    if extensao == '.webp':
        valido = inicio[:4] == b'RIFF' and inicio[8:12] == b'WEBP'
    elif extensao in ASSINATURAS:
        valido = inicio.startswith(ASSINATURAS[extensao])
    else:
        valido = b'\x00' not in inicio  # .txt / .md: texto, não binário
    if not valido:
        raise MaterialInvalido(f'O arquivo {nome} não parece ser do tipo {extensao}.')


class MaterialInvalido(ValueError):
    pass


def ler_texto(caminho):
    extensao = os.path.splitext(caminho)[1].lower()
    if extensao == '.docx':
        try:
            return '\n'.join(p.text for p in Document(caminho).paragraphs)
        except Exception as erro:
            raise MaterialInvalido('Não foi possível ler o arquivo .docx.') from erro
    with open(caminho, encoding='utf-8', errors='replace') as f:
        return f.read()


def ler_pdf(caminho):
    """Devolve (texto, número de páginas)."""
    try:
        leitor = PdfReader(caminho)
        return '\n'.join((pagina.extract_text() or '') for pagina in leitor.pages), len(leitor.pages)
    except (PdfReadError, ValueError, OSError) as erro:
        raise MaterialInvalido('Não foi possível ler o PDF enviado.') from erro


def dividir_pdf(caminho, partes, pasta):
    """Divide o PDF em até `partes` arquivos com páginas contíguas."""
    leitor = PdfReader(caminho)
    total = len(leitor.pages)
    partes = max(1, min(partes, total))
    caminhos = []
    for indice in range(partes):
        inicio, fim = indice * total // partes, (indice + 1) * total // partes
        escritor = PdfWriter()
        for numero in range(inicio, fim):
            escritor.add_page(leitor.pages[numero])
        destino = os.path.join(pasta, f'{os.path.basename(caminho)}.parte{indice}.pdf')
        with open(destino, 'wb') as f:
            escritor.write(f)
        caminhos.append(destino)
    return caminhos


def _remoto(ia, caminho, mime_type, nome, tipo, parte=None, total_partes=None):
    arquivo = ia.enviar_arquivo(caminho, mime_type)
    return {
        'nome': nome, 'tipo': tipo, 'parte': parte, 'total_partes': total_partes,
        'remoto': arquivo.nome, 'uri': arquivo.uri, 'mime_type': arquivo.mime_type,
        'expira_em': arquivo.expira_em.isoformat() if arquivo.expira_em else None,
    }


def processar_uploads(ia, arquivos, num_partes, limite_caracteres, pasta, max_paginas=None):
    """arquivos: [(nome_original, caminho)]. Devolve (texto_extraido, referencias).

    Valida tudo (tipo real e número de páginas) antes de enviar qualquer coisa ao provedor.
    """
    paginas_total = 0
    for nome, caminho in arquivos:
        conferir_conteudo(nome, caminho)
        if caminho.lower().endswith('.pdf'):
            paginas_total += ler_pdf(caminho)[1]
    if max_paginas is not None and paginas_total > max_paginas:
        raise MaterialInvalido(f'O material tem {paginas_total} páginas; para essa quantidade de cards o limite '
                               f'é {max_paginas}. Envie menos páginas ou escolha mais cards.')

    textos, referencias = [], []
    for nome, caminho in arquivos:
        extensao = os.path.splitext(caminho)[1].lower()
        if extensao in MIME_IMAGEM:
            referencias.append(_remoto(ia, caminho, MIME_IMAGEM[extensao], nome, 'imagem'))
        elif extensao == '.pdf':
            texto, paginas = ler_pdf(caminho)
            if paginas and len(texto.strip()) >= MIN_CARACTERES_POR_PAGINA * paginas:
                textos.append((nome, texto))
                referencias.append({'nome': nome, 'tipo': 'texto', 'caracteres': len(texto)})
            else:
                pedacos = dividir_pdf(caminho, num_partes, pasta)
                for indice, pedaco in enumerate(pedacos):
                    referencias.append(_remoto(ia, pedaco, 'application/pdf', nome, 'pdf', indice, len(pedacos)))
        elif extensao in EXTENSOES_TEXTO:
            texto = ler_texto(caminho)
            textos.append((nome, texto))
            referencias.append({'nome': nome, 'tipo': 'texto', 'caracteres': len(texto)})

    texto = '\n\n'.join(f'### {nome}\n{conteudo.strip()}' for nome, conteudo in textos if conteudo.strip())
    return texto[:limite_caracteres], referencias


def fatia(texto, partes, indice):
    """A `indice`-ésima de `partes` fatias do texto, cortando em espaço em branco."""
    if not texto or partes <= 1:
        return texto
    indice = indice % partes

    def corte(posicao):
        if posicao <= 0:
            return 0
        if posicao >= len(texto):
            return len(texto)
        espaco = texto.rfind(' ', 0, posicao)
        return espaco if espaco > posicao - 500 else posicao

    tamanho = len(texto) / partes
    return texto[corte(round(indice * tamanho)):corte(round((indice + 1) * tamanho))].strip()


def anexos_para(referencias, indice):
    """Arquivos remotos usados pela parte `indice`: todas as imagens + a parte correspondente de cada PDF."""
    anexos = []
    for ref in referencias or []:
        if ref['tipo'] == 'imagem':
            anexos.append(Anexo(uri=ref['uri'], mime_type=ref['mime_type']))
        elif ref['tipo'] == 'pdf' and ref['parte'] == indice % ref['total_partes']:
            anexos.append(Anexo(uri=ref['uri'], mime_type=ref['mime_type']))
    return anexos


def material_expira_antes(referencias, margem):
    """True se algum arquivo remoto deixa de existir no provedor antes de agora + margem."""
    limite = agora() + margem
    for ref in referencias or []:
        if ref.get('expira_em') and datetime.fromisoformat(ref['expira_em']) < limite:
            return True
    return False


def apagar_remotos(ia, referencias):
    """Não deixa material do aluno guardado no provedor depois da geração (LGPD)."""
    for ref in referencias or []:
        if ref.get('remoto'):
            try:
                ia.apagar_arquivo(ref['remoto'])
            except Exception:
                logger.warning('Não foi possível apagar o arquivo %s do provedor', ref['remoto'])


# Margem exigida no pagamento: a geração em lotes precisa terminar antes de os arquivos expirarem
MARGEM_MATERIAL = timedelta(hours=3)
