"""Prompts e schemas de saída: plano + prévia (grátis) e lotes (após o pagamento)."""
from pydantic import BaseModel


class CardGerado(BaseModel):
    pergunta: str
    resposta: str


class SubtopicoPlano(BaseModel):
    nome: str
    quantidade: int


class PlanoPrevia(BaseModel):
    nome_deck: str
    subtopicos: list[SubtopicoPlano]
    cards: list[CardGerado]
    fontes: list[str]


class LoteGerado(BaseModel):
    cards: list[CardGerado]
    fontes: list[str]


REGRAS_DE_QUALIDADE = """REGRAS DE QUALIDADE:
- NUNCA invente informações; na dúvida, não crie o card
- Cada card cobre um aspecto distinto; nada de perguntas repetidas com pequenas variações
- Pergunta clara e específica; resposta completa, precisa e objetiva
- Varie os tipos: definições, processos, relações, causas e efeitos, comparações, exemplos, aplicações
- Use texto simples; para ênfase, apenas as marcações <b>, <i>, <u>, <sub>, <sup>"""


def _bloco_material(material, tem_anexos):
    partes = []
    if tem_anexos:
        partes.append('Há arquivos/imagens anexados: use o conteúdo deles como base principal.')
    if material:
        partes.append(f'--- MATERIAL DO ALUNO ---\n{material}\n--- FIM DO MATERIAL ---\n'
                      'Baseie os cards principalmente neste material.')
    return ('\n\n' + '\n\n'.join(partes)) if partes else ''


def prompt_previa(assunto, quantidade_total, tamanho_previa, material=None, tem_anexos=False):
    return f"""Você é um especialista em criar flashcards educacionais.

ASSUNTO: {assunto}{_bloco_material(material, tem_anexos)}

TOTAL DO BARALHO: {quantidade_total} flashcards.

TAREFA:
1. "nome_deck": um nome curto para o baralho.
2. "subtopicos": divida o assunto em subtópicos, do mais fundamental ao mais avançado, e distribua
   os {quantidade_total} flashcards entre eles no campo "quantidade" (a soma deve ser {quantidade_total}).
3. "cards": crie EXATAMENTE {tamanho_previa} flashcards de amostra, dos primeiros subtópicos, que mostrem
   bem a qualidade do baralho completo.
4. "fontes": fontes confiáveis relacionadas ao conteúdo.

{REGRAS_DE_QUALIDADE}"""


def prompt_lote(assunto, nome_deck, quantidade, subtopicos, perguntas_existentes, material=None,
                tem_anexos=False):
    lista_subtopicos = '\n'.join(f'- {s["nome"]}: {s["quantidade"]} cards' for s in subtopicos)
    existentes = '\n'.join(f'- {p}' for p in perguntas_existentes) or '(nenhuma ainda)'
    return f"""Você é um especialista em criar flashcards educacionais.

BARALHO: {nome_deck}
ASSUNTO: {assunto}{_bloco_material(material, tem_anexos)}

Crie EXATAMENTE {quantidade} flashcards, distribuídos assim:
{lista_subtopicos}

PERGUNTAS QUE JÁ EXISTEM NO BARALHO (não repita nem reformule):
{existentes}

{REGRAS_DE_QUALIDADE}

"fontes": fontes confiáveis relacionadas aos cards deste lote."""
