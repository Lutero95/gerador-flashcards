# Análise de Preços × Custos de IA — Gerador de Flashcards

Data: 28/09/2026 · Complementa o `PLANO_DE_IMPLEMENTACAO.md` (a Parte 3, sobre o roteador de modelos, continua sendo **atualização futura**).

---

## 1. Resposta curta

- **A tabela de preços atual não dá prejuízo** com modelos baratos ou intermediários: o custo de IA fica entre **1% e 20%** do preço de cada faixa.
- **Pode dar prejuízo em três situações**, todas evitáveis:
  1. modelo "Pro" com raciocínio (*thinking*) sem limite nas faixas de 1.000–2.000 cards;
  2. PDF grande **reenviado inteiro a cada lote** (é o que acontece se a geração em lotes for implementada de forma ingênua);
  3. aumento de preço dos modelos (ex.: fim de promoção) sem revisar a tabela.
- **A carteira fica equilibrada**: mesmo usando modelos mais caros para concurseiros e medicina, a margem média por venda fica em torno de **90%** sobre o custo de IA. Com as prévias grátis incluídas, o **ponto de equilíbrio fica entre ~15 e ~49 vendas por mês**, dependendo de como você formalizar a atividade (ver seção 3.5 — **MEI não serve para venda de software**).
- **Os preços não são abusivos.** Em reais por card, as faixas grandes custam o mesmo ou menos que os concorrentes. O único ponto que pode **parecer** injusto é a faixa de entrada: quem pede 10 cards paga os mesmos R$ 3,90 de quem pede 50.

---

## 2. Premissas (ajustáveis nos scripts `analise/custo.py` e `analise/carteira.py` — rode `python analise/carteira.py` para refazer as contas)

| Item | Valor usado | Fonte/observação |
|---|---|---|
| Dólar | R$ 5,20 + IOF 3,5% (cartão internacional) = **R$ 5,38** | Cotação de 28/09/2026 |
| Taxa do Pix (Mercado Pago, online) | **0,99%** | Checkout Transparente, dinheiro na hora |
| Tamanho do lote | 40 cards por chamada | conforme Fase 3 do plano |
| Entrada fixa por lote | 1.500 tokens (instruções) + lista de perguntas já geradas (máx. 200 × 20 tokens) | anti‑duplicação |
| Chamada de "plano de subtópicos" | 2.000 tokens de entrada, 800 de saída | 1 por pedido |
| Retentativas/falhas | +10% sobre o custo | |
| PDF | ~600 tokens por página | |

### Tokens por card, por tipo de usuário

Estimados a partir de cards de exemplo realistas em português (formato JSON, com margem de 50% porque o prompt pede respostas "completas"):

| Perfil | Exemplo de pergunta típica | Tokens de saída/card |
|---|---|---|
| Autodidata — idiomas | "O que significa *give up*?" → tradução + frase de exemplo | ~50 |
| Estudante — escola/ENEM | "O que diz a 2ª Lei de Newton?" | ~75 |
| Estudante — graduação/técnico | "Diferença entre inibição competitiva e não competitiva?" | ~95 |
| Autodidata — programação | "Diferença entre *list* e *tuple* em Python?" (com trecho de código) | ~95 |
| Medicina/residência | "Critérios de Light para exsudato pleural?" | ~110 |
| **Concurseiro** | "Prazo de validade de concurso (art. 37, III, CF)?", "CESPE — certo ou errado: a SV 13…", "Prescrição na Lei 8.112 (art. 142)?" | **~140** (resposta com fundamento legal) |

O concurseiro é o perfil mais caro por card **e** o que mais exige precisão (número de artigo, prazo, súmula). Por isso as tabelas abaixo usam o perfil concurseiro como pior caso.

### Preços dos modelos (por 1 milhão de tokens, em US$)

| Modelo | Entrada | Saída | Classe |
|---|---|---|---|
| GPT‑5.6 Luna | 0,20 | 1,20 | barato |
| Gemini 3.1 Flash‑Lite | 0,25 | 1,50 | barato |
| Gemini 3.5 Flash‑Lite | 0,30 | 2,50 | barato |
| Gemini 3 Flash | 0,50 | 3,00 | intermediário |
| Gemini 3.8 Flash (promocional) | 0,75 | 3,75 | intermediário |
| Gemini 3.8 Flash (após a promoção*) | 1,50 | 7,50 | intermediário |
| Claude Haiku 4.5 | 1,00 | 5,00 | intermediário |
| Claude Sonnet 5 | 2,00 | 10,00 | avançado |
| Gemini 3.1 Pro | 2,00 | 12,00 | avançado |
| GPT‑5.6 Terra | 2,00 | 12,00 | avançado |

\* A página oficial do Gemini mostra US$ 0,75/3,75 para a família 3.6–3.8 Flash. Uma fonte de terceiros diz que esse preço é promocional até 31/12/2026 e dobra em 01/01/2027. Por isso o cenário "após a promoção" está incluído. **No Gemini, os tokens de raciocínio (*thinking*) são cobrados como saída.**

---

## 3. Resultados

### 3.1 Tabela atual × custo (perfil concurseiro, tema digitado, *thinking* desligado)

Custo de IA em R$ no **topo** de cada faixa (pior caso da faixa) | margem sobre o valor líquido recebido:

| Modelo | 50 → R$3,90 | 100 → R$6,90 | 200 → R$9,90 | 500 → R$18,90 | 1000 → R$27,90 | 2000 → R$39,90 |
|---|---|---|---|---|---|---|
| Gemini 3.1 Flash‑Lite | 0,08 · 98% | 0,14 · 98% | 0,28 · 97% | 0,72 · 96% | 1,44 · 95% | 2,89 · 93% |
| GPT‑5.6 Luna | 0,06 · 98% | 0,12 · 98% | 0,23 · 98% | 0,58 · 97% | 1,15 · 96% | 2,31 · 94% |
| Gemini 3 Flash | 0,16 · 96% | 0,29 · 96% | 0,56 · 94% | 1,44 · 92% | 2,88 · 90% | 5,77 · 85% |
| Gemini 3.8 Flash (promo) | 0,20 · 95% | 0,37 · 95% | 0,72 · 93% | 1,84 · 90% | 3,69 · 87% | 7,41 · 81% |
| Gemini 3.8 Flash (pós‑promo) | 0,40 · 90% | 0,74 · 89% | 1,43 · 85% | 3,69 · 80% | 7,38 · 73% | 14,82 · 62% |
| Claude Haiku 4.5 | 0,27 · 93% | 0,49 · 93% | 0,96 · 90% | 2,46 · 87% | 4,92 · 82% | 9,88 · 75% |
| Claude Sonnet 5 | 0,53 · 86% | 0,98 · 86% | 1,91 · 80% | 4,92 · 74% | 9,85 · 64% | 19,76 · 50% |
| Gemini 3.1 Pro / GPT‑5.6 Terra | 0,62 · 84% | 1,16 · 83% | 2,25 · 77% | 5,76 · 69% | 11,51 · 58% | 23,09 · 42% |

### 3.2 Mesmo cenário com *thinking* sem controle (raciocínio ≈ tamanho da resposta)

| Modelo | 200 | 500 | 1000 | 2000 |
|---|---|---|---|---|
| Gemini 3.1 Flash‑Lite | 95% | 93% | 90% | 86% |
| Gemini 3.8 Flash (pós‑promo) | 72% | 63% | 51% | 31% |
| Claude Sonnet 5 | 63% | 51% | 34% | **8%** |
| Gemini 3.1 Pro / GPT‑5.6 Terra | 56% | 42% | 22% | **−9% (prejuízo)** |

**Lição:** o *thinking* é o maior "vazamento" silencioso de custo. Na prática, raciocínio sem limite pode ser 2–4× maior que a resposta; aqui foi usado 1×. **Limitar o orçamento de thinking não é opcional.**

### 3.3 PDF grande — o risco mais sério para concurseiros

Um concurseiro enviando a Lei 8.112 + trechos da CF (~200 páginas ≈ 120 mil tokens):

| Modelo | Cards | Reenviando o PDF inteiro a cada lote | Enviando só a fatia de cada lote |
|---|---|---|---|
| Gemini 3.1 Flash‑Lite | 2000 | R$ 11,94 · margem 70% | R$ 3,22 · 92% |
| Gemini 3.8 Flash (promo) | 2000 | R$ 34,58 · margem 12% | R$ 8,43 · 79% |
| Gemini 3.1 Pro | 200 | R$ 10,78 · **−10%** | R$ 4,97 · 49% |
| Gemini 3.1 Pro | 500 | R$ 25,65 · **−37%** | R$ 8,47 · 55% |
| Gemini 3.1 Pro | 2000 | R$ 95,55 · **−142%** | R$ 25,80 · 35% |

**Lição:** o que causa prejuízo é **reenviar o material inteiro a cada lote**, não o preço do card. Solução: dividir o material em fatias e mandar só a fatia de cada lote. O cache de contexto (*context caching*) também ajuda. Além disso, limitar o número de páginas por faixa.

### 3.4 Carteira (as faixas se compensam?)

Simulação com a política de modelos proposta na seção 5 e um mix de vendas plausível. O mix é **premissa**; troque pelos dados reais assim que tiver vendas.

- Faixas: 50 (35%), 100 (30%), 200 (18%), 500 (12%), 1000 (4%), 2000 (1%). Cliente usa ~70% do topo da faixa.
- Perfis: concurseiro 35%, escola/ENEM 25%, graduação 20%, medicina 10%, idiomas 5%, programação 5%.

| Indicador | Valor |
|---|---|
| Ticket médio líquido (após Pix) | **R$ 8,91** |
| Custo médio de IA por venda | **R$ 0,80** |
| Margem de contribuição | **R$ 8,11 (91%)** |
| Custo de uma prévia grátis (plano + 5 cards, Flash‑Lite) | **R$ 0,016** |

Custo das prévias grátis por venda, conforme a conversão prévia → compra: 2% → R$ 0,81 · 5% → R$ 0,33 · 10% → R$ 0,16. Mesmo com 50 prévias para cada venda, elas custam menos de R$ 1 por venda.

### 3.5 Custos fixos e ponto de equilíbrio (corrigido: MEI não se aplica)

> **Correção:** a versão anterior deste documento considerava o DAS‑MEI. **Venda ou licenciamento de software/SaaS não está entre as ocupações permitidas ao MEI.** Os cenários abaixo substituem aquele cálculo. São estimativas para conversar com um contador, não orientação tributária.

Premissas: conversão de 5%; Vercel Pro US$ 20 ≈ R$ 108 (**o plano Hobby da Vercel proíbe uso comercial**); domínio ~R$ 3/mês; contador ~R$ 200/mês nos cenários com CNPJ (valor estimado — peça orçamentos).

| Cenário | Custo fixo/mês | Imposto | Margem por venda | Ponto de equilíbrio |
|---|---|---|---|---|
| Pessoa física (carnê‑leão), fase de teste | ~R$ 111 | IR sobre o lucro, somado ao salário CLT no ajuste anual | R$ 7,78 antes do IR | **~15 vendas/mês** |
| Inova Simples ou ME no Simples Nacional, Anexo III (6%) | ~R$ 311 | 6% da receita | R$ 7,24 | **~43 vendas/mês** |
| ME no Simples Nacional, Anexo V (15,5%) | ~R$ 311 | 15,5% da receita | R$ 6,39 | **~49 vendas/mês** |

**Conclusão:** a carteira fica equilibrada com folga, e a IA não é o problema. **O custo que realmente pesa é o fixo** (hospedagem, contador e imposto).

---

## 4. Os preços são abusivos?

| Referência | Preço | Observação |
|---|---|---|
| Seu gerador — 50 cards | R$ 3,90 (R$ 0,078/card) | pagamento único, sem assinatura |
| Seu gerador — 500 cards | R$ 18,90 (R$ 0,038/card) | |
| Seu gerador — 2000 cards | R$ 39,90 (R$ 0,020/card) | |
| Keezmo (BR) | R$ 24,90/mês por 150 créditos (≈150 páginas) | assinatura |
| Quorify (BR) | grátis 1 uso/dia; Pro a partir de R$ 16/mês | assinatura |
| AnkiDecks | grátis 4 gerações/mês; Pro US$ 5/mês (anual) ≈ R$ 26 | assinatura |

- **Não são abusivos.** O público (estudante, concurseiro) prefere pagar pouco e só quando precisa, e o modelo de pagamento avulso por Pix serve bem a isso. Um baralho de 100 cards sobre a Lei 8.112 por R$ 6,90 economiza horas de trabalho manual.
- **A margem de ~90% sobre o custo de IA não é exploração.** Ela paga custos fixos, prévias grátis, reembolsos, impostos e o seu trabalho.
- **O ponto fraco é a faixa de entrada.** Quem quer 10 cards paga R$ 0,39 por card, e o salto de 50 para 51 cards quase dobra o preço (R$ 3,90 → R$ 6,90). Isso não gera prejuízo, mas pode soar injusto.

### Tabela sugerida (mesma lógica, degraus mais suaves, alinhada ao limite de 500 do plano)

| Até | Preço sugerido | R$/card no topo |
|---|---|---|
| 25 | R$ 2,90 | 0,116 |
| 50 | R$ 3,90 | 0,078 |
| 100 | R$ 6,90 | 0,069 |
| 200 | R$ 9,90 | 0,050 |
| 300 | R$ 12,90 | 0,043 |
| 500 | R$ 17,90 | 0,036 |

Com a política de modelos da seção 5, a margem no topo de todas essas faixas fica **acima de 65%**, mesmo para concurseiro e medicina. As faixas de 1.000 e 2.000 cards podem voltar quando houver dados reais. Uma opção mais simples é um **pacote de créditos** (ex.: 1.000 cards por R$ 29,90, usados em vários baralhos), que também resolve o caso de "preciso de 60 cards agora e 40 semana que vem".

---

## 5. Impacto na regra futura de alternância de modelos (roteador)

> ⚠️ **Atualização futura — não implementar agora.** Esta seção serve para ajustar a Parte 3 do `PLANO_DE_IMPLEMENTACAO.md` quando ela for implementada.

### 5.1 Política inicial sugerida

| Perfil detectado | Exemplo de pedido | Modelo | Thinking |
|---|---|---|---|
| Idiomas, escola/ENEM, programação básica | "verbos irregulares em inglês", "Revolução Francesa" | **Flash‑Lite** (ou GPT‑5.6 Luna como alternativa) | desligado |
| Graduação/técnico | "farmacologia de anti‑hipertensivos", "cálculo de juros compostos" | **Gemini 3 Flash** | baixo |
| Concurseiro e medicina — até 200 cards | "Lei 8.112 — prazos", "critérios diagnósticos de sepse" | **modelo avançado** (Gemini 3.1 Pro / Sonnet 5) | limitado |
| Concurseiro e medicina — acima de 200 cards | "CF/88 completa, art. 1º ao 100" | **Flash intermediário + revisão por modelo avançado** (o modelo avançado lê os cards e aponta erros, sem gerar tudo) | baixo |

Resultado simulado dessa política (margem no topo da faixa atual):

| Perfil | 50 | 100 | 200 | 500 | 1000 | 2000 |
|---|---|---|---|---|---|---|
| Idiomas | 99% | 99% | 99% | 98% | 98% | 97% |
| Escola/ENEM | 99% | 99% | 98% | 98% | 97% | 96% |
| Graduação | 96% | 96% | 95% | 93% | 91% | 87% |
| Programação | 99% | 98% | 98% | 97% | 96% | 95% |
| Medicina | 81% | 80% | 73% | 85% | 80% | 72% |
| Concurseiro | 77% | 75% | 67% | 82% | 75% | 66% |

### 5.2 Regras obrigatórias para o roteador não gerar prejuízo

1. **Teto de custo por nível de risco, sem rebaixar a qualidade em silêncio** (substitui o teto único de 25% sugerido antes — ver seção 5.4):
   - risco baixo (idiomas, ENEM, programação básica): teto de 25% do valor líquido; pode rebaixar o modelo;
   - risco médio (graduação/técnico): teto de 30%; rebaixa só mantendo a revisão por amostragem;
   - **risco alto (concurseiro, medicina, direito, finanças): teto de 40%; nunca rebaixar o modelo gerador.** Se ainda passar do teto, oferecer ao usuário menos cards ou o modo "Precisão máxima" com preço próprio.
2. **Orçamento de thinking por perfil**, sempre com limite explícito.
3. **Material fatiado por lote** + cache de contexto. Nunca reenviar o PDF inteiro em cada chamada.
4. **Limite de páginas por faixa** (ex.: até 50 páginas na faixa de 100 cards; até 300 na de 500).
5. **Tabela de preços dos modelos em configuração** (não no código), com alerta quando o custo médio real (`UsoIA`) passar de 15% da receita no mês.
6. **Reavaliar trimestralmente.** Os preços mudam rápido (vide a possível dobra do Gemini Flash em 01/01/2027).

### 5.3 O que importa para precisão nesses públicos (mais que o tamanho do modelo)

- **Concurseiros:**
  - erram-se números de artigos, prazos e súmulas — a melhor defesa é **ancorar no texto da lei** (arquivo enviado ou texto oficial), não só usar um modelo maior;
  - vale oferecer cards no **formato de omissão de palavras (*cloze*)**, o padrão do Anki para lei seca, e questões **"certo ou errado" no estilo CESPE/Cebraspe**;
  - a resposta sempre deve trazer o fundamento ("art. 37, III, CF/88").
- **Medicina:** doses, critérios e condutas — os mesmos cuidados, mais um aviso de que o conteúdo é para estudo e não substitui protocolos oficiais.
- **Escola/ENEM:** conceitos com aplicação e fórmulas; usar MathJax (`\( … \)`), que o Anki já renderiza.
- **Idiomas:** cards curtos, frase de exemplo e card invertido (PT→EN e EN→PT).
- **Programação:** blocos de código formatados; conferir a sintaxe.

**Consequência para o roteador:** o classificador deve detectar também o **tipo de card** (lei seca → cloze; idiomas → invertido), não só a complexidade.

---

### 5.4 Riscos de rebaixar o modelo para caber no teto de custo

**O ponto crítico:** na política da seção 5.1, os pedidos que passariam de um teto único de 25% são justamente os de concurseiro e medicina entre 100 e 200 cards (custo de 25–33% do preço). Um teto único e automático rebaixaria o modelo **exatamente onde a precisão mais importa**.

#### O que piora quando se usa um modelo menor

| Risco | Como aparece | Quem é mais afetado |
|---|---|---|
| **Alucinação de detalhe factual** — o maior risco | número de artigo, inciso, prazo, súmula, dose ou valor de referência trocado ou inventado, escrito com total confiança | concurseiro, medicina |
| **Conhecimento desatualizado** | lei alterada, súmula cancelada, protocolo revisto | concurseiro, medicina |
| **Perda de nuance** | ignora exceções e "salvo…", que são o alvo das pegadinhas de banca ("em regra" × "sempre") | concurseiro |
| **Cobertura rasa** | cards genéricos e repetitivos em volta do óbvio, sem aprofundar os subtópicos | todos em quantidades grandes |
| **Falha em seguir o material** | usa o que "sabe" em vez do PDF enviado, ou mistura os dois | quem envia arquivo |
| **Erro de raciocínio** | cálculo, dedução ou enunciado "certo ou errado" com gabarito invertido | exatas, concurseiro |
| **Formato** | JSON quebrado, cloze mal marcado, LaTeX inválido (gasta retentativas) | todos (baixo impacto) |

#### Risco × complexidade

| Complexidade | Exemplo | Efeito de rebaixar o modelo |
|---|---|---|
| Baixa, conhecimento consolidado | vocabulário, fotossíntese, Revolução Francesa | **baixo** — modelos pequenos acertam bem conteúdo muito comum |
| Média | enzimologia, estruturas de dados, contabilidade básica | **moderado** — mais cards rasos e alguns erros pontuais |
| Alta, com detalhe exato | lei seca, jurisprudência, farmacologia, critérios diagnósticos | **alto** — um erro de prazo ou dose é pior que não ter o card, porque o aluno memoriza o erro |
| Alta, nicho ou recente | legislação estadual/municipal, edital específico, norma recente | **muito alto** — modelos de qualquer tamanho erram sem o texto de referência |

**Por que é grave para esse público:** flashcard é feito para ser memorizado. Um erro não é só um card inútil: ele vira resposta errada na prova e destrói a confiança no produto, gerando reembolso e boca a boca negativo. Para o concurseiro, um card errado custa mais que os centavos economizados.

#### Política recomendada, em ordem (só avança se a etapa anterior não bastar)

1. **Cortar desperdício antes de mexer no modelo:** thinking com limite, material fatiado, cache de contexto, anti‑duplicação.
2. **Mudar a arquitetura, não o nível:** um modelo intermediário gera e o modelo avançado revisa. Isso costuma manter ou até **melhorar** a precisão por menos custo. A revisão deve checar número de artigo, prazos, valores e o gabarito de "certo ou errado".
3. **Ancorar no texto (o que mais reduz erro):** para lei seca, usar o texto da lei (arquivo enviado ou texto oficial) e exigir que cada card cite o trecho de origem. Um card cujo fundamento não aparece no material é descartado ou marcado. Isso vale mais que trocar para um modelo maior.
4. **Aceitar margem menor até o teto do nível** (seção 5.2): em risco alto, até 40% de custo ainda deixa ~60% de margem.
5. **Se ainda passar do teto: perguntar, não rebaixar em silêncio.** Oferecer "gerar 150 cards com precisão máxima" ou o modo "Precisão máxima" com preço próprio.
6. **Rebaixar automaticamente só em risco baixo**, e sempre registrar em `UsoIA` qual modelo gerou cada lote.

#### Salvaguardas de qualidade (valem para qualquer modelo)

- Revisão automática por amostragem em todo lote de risco médio ou alto; se a taxa de erro da amostra passar de um limite (ex.: 5%), o lote é refeito com modelo melhor.
- Para lei seca: cada card cita artigo e diploma legal, com checagem de que o trecho existe no material quando houver arquivo.
- Aviso claro na entrega: "Conteúdo gerado por IA. Confira os fundamentos legais/clínicos antes de memorizar."
- Botão "reportar card incorreto" na prévia e na página do pedido; os reportes alimentam o ajuste da política.
- Conjunto de avaliação fixo (~30 temas por perfil) rodado sempre que o modelo ou a política mudar.

---

## 6. Ações recomendadas agora (entram nas Fases 1–3 do plano)

- [ ] Guardar a tabela de preços dos modelos e as faixas de preço em configuração (`precos.py` / variáveis).
- [ ] Limitar o thinking na prévia (zero) e na geração (baixo) — já previsto na Fase 3.
- [ ] Fatiar o material por lote — acrescentar à Fase 3.
- [ ] Limite de páginas por faixa — acrescentar à Fase 4.
- [ ] Registrar custo real em `UsoIA` e comparar com esta estimativa após as primeiras 50 vendas.
- [ ] Decidir: manter a tabela atual ou adotar a tabela sugerida da seção 4.
- [ ] Migrar da Vercel Hobby para Pro (ou outra hospedagem que permita uso comercial) antes de cobrar de verdade.
- [ ] Escolher a forma de formalização com um contador (seção 7.1) e colocar nos Termos o aviso de marca "Anki®" (seção 7.2).

---

## 7. Questões legais (visão geral — não substitui advogado ou contador)

### 7.1 Formalização sendo CLT

- **Ser CLT não impede ter CNPJ.** Leia o contrato de trabalho e as políticas da empresa (cláusulas de exclusividade, de não concorrência e de propriedade intelectual) e não use equipamento nem horário do empregador. Servidores públicos têm regras próprias.
- **MEI não serve para esta atividade:** venda e licenciamento de software/SaaS não estão entre as ocupações permitidas. Enquadrar-se num CNAE "parecido" pode levar a desenquadramento retroativo e multa.
- **Caminhos possíveis:**
  1. **Validar como pessoa física:** receber pelo Mercado Pago no CPF e recolher IR pelo **carnê‑leão**. Em 2026 há isenção mensal até R$ 5.000, mas no ajuste anual essa renda é somada ao salário CLT. Vender com habitualidade como pessoa física pode ser questionado pelo Fisco; serve como fase curta de teste.
  2. **Inova Simples:** regime para iniciativas inovadoras, com abertura simplificada e **venda experimental até o limite de receita do MEI (R$ 81 mil/ano)**, podendo optar pelo Simples Nacional.
  3. **ME/SLU no Simples Nacional:** CNAE 6203‑1/00 (desenvolvimento e licenciamento de software não customizável), Anexo III (a partir de 6%) se o Fator R ≥ 28%, ou Anexo V (a partir de 15,5%).
- **Seguro‑desemprego:** ter CNPJ ativo com renda pode afetar o benefício se você for demitido. Confirme com um contador.

### 7.2 Gerar arquivos .apkg

**Não há impedimento legal para gerar arquivos no formato .apkg.**

- O formato é aberto: um pacote compactado com um banco SQLite. O Anki para computador é código aberto (AGPLv3) e o AnkiDroid também (GPLv3). Formato de arquivo não é protegido por direito autoral, e gerar arquivos compatíveis é interoperabilidade.
- A biblioteca usada, **genanki, tem licença MIT**, que permite uso comercial. Mantenha o aviso de licença dela.
- Nenhum código do Anki (AGPL) é incorporado ao seu sistema. Se um dia copiar código do próprio Anki, aí sim valem as obrigações da AGPL.
- **O cuidado real é a marca "Anki":** é marca registrada da Ankitects, em processo de transição para a AnkiHub, que já obrigou apps "imitadores" a mudar de nome.
  - **Não use "Anki" no nome do produto, no domínio nem no logo** (ex.: evite "AnkiGen").
  - Uso descritivo é aceito: "gera baralhos **compatíveis com o Anki**".
  - Coloque no rodapé o aviso: "Anki® é marca registrada da Ankitects. Este site não é afiliado nem endossado pelo Anki." O próprio criador do Anki aprovou esse modelo de aviso num caso semelhante.

### 7.3 Conteúdo dos cards

- **Texto de lei é de domínio público** (Lei 9.610/98, art. 8º, IV). Cards de lei seca podem reproduzir artigos.
- **Material enviado pelo usuário** (apostilas e cursos pagos) pode ter direitos autorais. Os Termos de Uso devem dizer que o usuário é responsável pelo que envia e que o baralho é para uso pessoal de estudo.
- **Não reproduza questões de bancos pagos** (ex.: plataformas de questões) nem venda baralhos prontos feitos a partir delas. Cards "no estilo CESPE" gerados pela IA não são problema.

### 7.4 Consumidor, dados e provedores de IA

- **CDC (arrependimento de 7 dias em compras online):** para conteúdo digital já entregue o tema é discutido. A prévia grátis, o preço mostrado antes e uma política de reembolso clara nos Termos reduzem o risco. Na dúvida, reembolse.
- **LGPD:** informe quais dados coleta (e‑mail, arquivos), por quanto tempo guarda e que os arquivos são processados por um provedor de IA. Apague arquivos após a geração.
- **Termos dos provedores de IA:** use o **plano pago** da API do Gemini em produção. No plano gratuito, o conteúdo enviado pode ser usado pelo Google para melhorar produtos, o que é inadequado para arquivos de clientes.

---

## Fontes

- Preços oficiais da API Gemini: https://ai.google.dev/gemini-api/docs/pricing
- Preços da API OpenAI: https://openai.com/api/pricing/
- Preços da API Claude: https://platform.claude.com/docs/en/about-claude/pricing
- Nota sobre preço promocional do Gemini Flash (terceiros): https://developer.puter.com/tutorials/gemini-api-pricing/
- Taxa de Pix online do Mercado Pago (0,99%): https://marreiradigital.com.br/calculadora-mercadopago/
- Dólar em 28/09/2026: https://www.infomoney.com.br/mercados/dolar-hoje-abertura-fechamento-comercial-turismo-28092026/
- Vercel Hobby — uso não comercial: https://vercel.com/docs/plans/hobby
- Concorrentes: https://www.keezmo.com/ · https://quorifyapp.com.br/tools/flashcards-generator · https://anki-decks.com/payment/pricing/
- MEI em TI — atividades permitidas e riscos: https://www.meucontadoronline.com.br/blog/mei-em-ti-atividades-permitidas-riscos-fiscais/
- Alternativas ao MEI para software (CNAE, anexos, Fator R): https://contabilidade.com/blog/desenvolvedor-pode-ser-mei-em-2026-veja-como-abrir-cnpj-escolher-o-cnae-ideal-e-pagar-menos-impostos/
- CLT pode ter CNPJ/MEI: https://meutudo.com.br/blog/clt-pode-ter-mei/
- Inova Simples (gov.br): https://www.gov.br/empresas-e-negocios/pt-br/inova-simples/preciso-de-informacoes/perguntas-frequentes
- Carnê‑leão 2026: https://empresaabertabh.com.br/recursos/carne-leao
- Anki — licença e formato: https://en.wikipedia.org/wiki/Anki_(software)
- Marca Anki e aviso de não afiliação (fórum oficial): https://forums.ankiweb.net/t/question-about-api-access-naming-anki-cards-in-external-app/66116
- genanki (licença MIT): https://github.com/kerrickstaley/genanki
