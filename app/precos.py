"""Tabela de preços por faixa de quantidade de cards, em centavos."""

# (até N cards, preço em centavos). Para adotar a tabela sugerida em
# ANALISE_PRECOS_E_CUSTOS.md, seção 4, basta trocar esta lista.
FAIXAS = [
    (50, 390),
    (100, 690),
    (200, 990),
    (500, 1890),
    (1000, 2790),
    (2000, 3990),
]


def calcular_preco_centavos(quantidade):
    """Preço da menor faixa que comporta a quantidade; acima da última faixa, o preço máximo."""
    for limite, preco in FAIXAS:
        if quantidade <= limite:
            return preco
    return FAIXAS[-1][1]


def centavos_para_reais(centavos):
    return round(centavos / 100, 2)
