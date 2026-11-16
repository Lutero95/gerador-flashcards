# Plano de Implementação — Gerador de Flashcards

> **Como usar este documento:** entregue-o ao Claude Code com a instrução
> *"Implemente o PLANO_DE_IMPLEMENTACAO.md fase por fase, começando pela Fase 0. Ao final de cada fase, rode os testes e me mostre o resumo antes de seguir."*
>
> A **Parte 3 (Roteador de modelos de IA)** é uma atualização **FUTURA** e **NÃO deve ser implementada agora** — veja a nota no início dela.

Data da análise: 28/09/2026 · Base analisada: `app.py`, `api/index.py`, `templates/index.html`, `vercel.json`, `.vercelignore`, `requirements.txt`, `.env`/`env.example` (apenas nomes das chaves).

---

## Sumário

- Parte 1 — Diagnóstico
  - 1.1 Problemas críticos (corrigir antes de qualquer outra coisa)
  - 1.2 Regras de negócio atuais e falhas de fluxo
  - 1.3 Segurança e integridade
  - 1.4 Eficiência e custo de IA
  - 1.5 Design e usabilidade (IHC)
  - 1.6 O que os sites populares fazem
  - 1.7 Estratégia financeira: prévia grátis, custo de abandono e abuso
- Parte 2 — Plano de implementação (Fases 0 a 6)
- Parte 3 — Futuro: roteador de modelos de IA (**não implementar agora**)
- Apêndice — Fontes consultadas

---

# PARTE 1 — DIAGNÓSTICO

## 1.1 Problemas críticos

| # | Problema | Onde | Impacto |
|---|---|---|---|
| C1 | **Em produção (Vercel) não existe cobrança.** O `vercel.json` manda tudo para `api/index.py`, que não tem nenhuma integração de pagamento, e o `.vercelignore` exclui o `app.py`. Qualquer pessoa gera e baixa de graça (até 100 cards). | `vercel.json`, `.vercelignore`, `api/index.py` | Receita zero + custo de IA aberto |
| C2 | **Chave real do Gemini dentro do `env.example`** (é idêntica à do `.env`). O arquivo ainda não foi commitado, mas um `git add .` a publica no GitHub. | `env.example` | Uso indevido da sua cota/fatura |
| C3 | **Download liberado sem pagamento** quando o `geracao_id` não está em memória (após qualquer reinício do servidor, ou em outra instância serverless) ou quando o nome do arquivo não tem `_`. Arquivos antigos em `output/` também são servidos. | `app.py` `/download/<filename>` | Bypass do pagamento |
| C4 | **Endpoints abertos de pagamento**: `/criar-pagamento-pix` cria cobrança de **qualquer valor** sem vínculo com geração; `/verificar-pagamento/<id>` devolve dados de **qualquer** pagamento da sua conta (IDOR). | `app.py` | Confusão do usuário, vazamento de dados |
| C5 | **Webhook nunca funciona**: (a) a validação da assinatura não segue o formato do Mercado Pago (`ts=...,v1=...` com manifest `id:...;request-id:...;ts:...;`), então com segredo configurado **todo webhook legítimo é rejeitado**; sem segredo, aceita qualquer coisa; (b) compara `payment_id` inteiro salvo com o `data.id` string recebido → nunca encontra o pedido. | `validar_webhook_mercadopago`, `/webhook-mercadopago` | Pagamento só é detectado se a aba ficar aberta fazendo polling |
| C6 | **Estado em memória** (`pending_payments = {}`) e arquivos em disco local/`/tmp`. Em serverless cada requisição pode cair em outra instância; qualquer reinício perde pedidos **já pagos**. | `app.py` | Cliente paga e não recebe |
| C7 | `app.run(debug=True, host='0.0.0.0')` expõe o debugger do Werkzeug (execução remota de código) se rodar acessível na rede. | `app.py` final | RCE |

## 1.2 Regras de negócio atuais e falhas de fluxo

**Regras existentes (como o código se comporta hoje):**

- Quantidade: front limita a 1–100; `app.py` aceita até 2000; `api/index.py` até 100. Valores inválidos viram 10 silenciosamente.
- Menções de quantidade no prompt são removidas por regex (`limpar_quantidade_do_prompt`).
- Preço por faixa sobre a quantidade **efetivamente gerada**: ≤50 R$3,90 · ≤100 R$6,90 · ≤200 R$9,90 · ≤500 R$18,90 · ≤1000 R$27,90 · ≤2000 R$39,90.
- Fluxo: gera tudo com IA → salva arquivos → cria PIX → modal com QR → polling a cada 5s → libera links.
- E-mail do pagador é fixo `test@test.com` (o front da geração não coleta e-mail).

**Falhas de fluxo encontradas:**

1. **Fechar o modal = perder a compra.** Não há página do pedido, nem botão "retomar pagamento", nem nada salvo no navegador. Se o usuário pagar depois de fechar, o dinheiro entra e ele não recebe o arquivo (webhook quebrado + estado volátil).
2. **O botão "💳 Pagar com PIX" da tela principal** abre um formulário de valor livre que **não está ligado a nenhuma geração**. Um usuário que fechou o modal e tenta "voltar a pagar" por ele paga e não recebe nada.
3. **Preço só aparece depois de gerar.** O usuário não sabe quanto vai pagar ao escolher a quantidade — surpresa no fim do funil.
4. **Nenhuma prévia do conteúdo** antes de pagar — o usuário paga "às cegas".
5. **QR expirado não pode ser renovado.**
6. **Status em inglês** ("pending", "approved") exibido cru ao usuário.
7. **Dois listeners** no botão "Verificar Pagamento" → requisições duplicadas.
8. **Falha após pagamento não tem tratamento** (não existe reembolso nem nova tentativa).
9. **Limite 2000 é irreal numa única chamada**: o JSON de 2000 cards passa do limite de saída do modelo, trunca, o `json.loads` falha e **o custo dos tokens é perdido** sem entregar nada. O mesmo tende a acontecer com o tempo limite da função serverless.
10. Arquivos temporários com nome `temp_{nome_original}` — **dois usuários enviando `resumo.pdf` ao mesmo tempo sobrescrevem o arquivo um do outro** (um recebe cards do material do outro).

## 1.3 Segurança e integridade (lista completa)

| Sev. | Item | Correção |
|---|---|---|
| Crítica | C1–C7 acima | Fases 0–2 |
| Alta | Sem rate limit/captcha: qualquer script pode chamar `/gerar` em loop e queimar sua cota de IA ("ataque à carteira") | Rate limit por IP + Cloudflare Turnstile + orçamento diário (Fase 4) |
| Alta | Colisão de nomes de upload entre usuários (item 10 acima) | `tempfile.mkdtemp()` por requisição, nome `uuid4` |
| Alta | Sem `X-Idempotency-Key` na criação do pagamento → PIX duplicado em retry | Chave de idempotência = id do pedido + tentativa |
| Média | Mensagens `str(e)` enviadas ao cliente vazam detalhes internos | Log interno + mensagem amigável com código de erro |
| Média | Flask/Werkzeug 2.0.3 (2022) com CVEs conhecidas | Atualizar para Flask 3.x |
| Média | SDK `google-generativeai` descontinuado; o "fallback" de modelos é falso (o construtor `GenerativeModel()` não chama a API, então nunca cai no próximo) | Migrar para `google-genai`; fallback real no momento da chamada |
| Média | Upload sem lista branca de tipos nem limite de nº de arquivos/páginas | Lista branca (pdf, docx, txt, md, png, jpg, webp), máx. 5 arquivos, checagem de *magic bytes* |
| Média | Texto das fontes vai direto para `reportlab.Paragraph` (que interpreta marcação) → PDF quebra com `<` ou `&` | `xml.sax.saxutils.escape` |
| Baixa | `file.name` inserido via `innerHTML` na prévia de arquivos (self‑XSS) | `textContent` |
| Baixa | Conteúdo gerado vai como HTML para o Anki | Escapar HTML dos campos (ou permitir só tags seguras: `b i u br sub sup`) |
| Baixa | Sem aviso de privacidade (LGPD): arquivos do usuário são enviados ao Google | Texto curto + página de Privacidade/Termos |
| Organização | Código duplicado entre `app.py` e `api/index.py`; ~1.150 linhas num só arquivo | Refatorar em módulos (Fase 1) |

## 1.4 Eficiência e custo de IA

- **Uma chamada gigante** para N cards: lenta, trunca, sem progresso, perde tudo se falhar. → **Gerar em lotes** (~40 cards) com um "plano de subtópicos" feito antes; cada lote é salvo no banco. Falhou o lote 4? Refaz só o lote 4.
- **JSON extraído por regex** → usar *structured output* (`response_mime_type="application/json"` + `response_schema`). Menos falhas = menos tokens desperdiçados.
- **Tokens de "raciocínio" (thinking)** dos modelos Flash recentes são cobrados como saída e podem multiplicar o custo sem melhorar cards simples. → Configurar orçamento de thinking baixo/zero para geração e prévia.
- **Arquivos do deck não precisam ser guardados**: guarde os cards (JSON) no banco e gere `.apkg`/`.pdf` **na hora do download** (leva milissegundos). Elimina o problema de `/tmp`/disco em serverless.
- **Cache por hash do prompt** para prévias repetidas (mesmo tema + mesma quantidade).
- **Deduplicação** de perguntas entre lotes (normalizar texto e comparar similaridade simples).
- **Registrar consumo** (tokens de entrada/saída e custo estimado por chamada) — base para decisões de preço e para o roteador futuro.

**Ordem de grandeza do custo** (confira os preços atuais na página oficial do Gemini antes de decidir; eles mudam com frequência): um card ocupa algo como 80–150 tokens de saída. Com um modelo Flash na faixa de US$ 3 por milhão de tokens de saída, 100 cards ≈ 15 mil tokens ≈ **US$ 0,05**; uma prévia de 5 cards custa frações de centavo. Ou seja: **o custo de um abandono comum é pequeno; o risco real é abuso automatizado e gerações enormes que falham.** É isso que o plano ataca primeiro.

## 1.5 Design e usabilidade (IHC)

Avaliação pelas 10 heurísticas de Nielsen e leis de UX:

| Heurística / princípio | Situação atual | Melhoria |
|---|---|---|
| Visibilidade do status | Spinner genérico "Gerando seu deck..." sem tempo nem progresso | Stepper em 3 etapas + barra de progresso por lote ("40 de 100 cards") |
| Correspondência com o mundo real | "approved/pending", "APKG" sem explicação | Português claro; "Arquivo para o Anki (.apkg)" com link "como importar" |
| Controle e liberdade | Fechar o modal perde tudo | Pedido persistente com link próprio; "Retomar pagamento" |
| Consistência / Lei de Jakob | Botão "Pagar com PIX" solto, sem contexto | Pagamento só existe dentro do fluxo do pedido |
| Prevenção de erros | Aviso ⚠️ "a quantidade no texto será ignorada" | Detectar o número no texto e **preencher o campo automaticamente** |
| Reconhecer em vez de lembrar | Upload escondido num botão "+" | Abas visíveis: **Tema · Arquivo · Colar texto** + área de arrastar |
| Flexibilidade | Campo numérico minúsculo dentro da frase | Chips de quantidade alinhados às faixas de preço (10 · 25 · 50 · 100 · 200 · 500) com preço ao lado |
| Estética minimalista | Gradiente roxo em tela cheia, sombras fortes, emojis como ícones | Fundo neutro, 1 cor de destaque, ícones SVG consistentes |
| Recuperação de erros | Mensagens técnicas (`str(e)`) | Mensagem humana + o que fazer + código para suporte |
| Ajuda e documentação | Nenhuma | Seção "Como funciona", FAQ (o que é Anki, como importar, reembolso, privacidade) |
| Lei de Hick | Ok (poucas opções) | Manter: um caminho principal por tela |
| Lei de Fitts / mobile | QR code no celular é inútil (a pessoa está no próprio celular) | No mobile, **"Copiar código Pix" vira o botão principal**; QR fica secundário |
| Regra do pico‑fim | Fim da jornada = download seco | Tela final com sucesso claro, download automático, instruções de importação e "gerar outro baralho" |
| Acessibilidade (WCAG) | Cinza `#999` sobre branco (contraste ~2,8:1, reprovado); modal sem foco preso nem `Esc`; itens de menu são `div` com `onclick` (sem teclado) | Contraste ≥ 4,5:1, `<dialog>`/`role="dialog"` com foco, botões reais, `aria-live` para status |

## 1.6 O que os sites populares fazem (e por que funcionam)

Referências: Quizlet, Knowt, Gizmo, AnkiDecks, StudyFetch, RemNote — e, fora do nicho, o modelo "vê antes, paga depois" do remove.bg/Canva.

**Padrões visuais recorrentes:**

1. **O gerador é o herói da página.** A primeira dobra é uma caixa grande: "cole, envie ou descreva → gere". Nada de modal ou menu para começar.
2. **Resultado visível imediatamente.** Os cards aparecem na tela como cartões que viram (pergunta/resposta), antes de qualquer download. Isso *é* o argumento de venda.
3. **Visual limpo:** fundo branco/off‑white, **uma** cor de destaque, tipografia sans‑serif moderna (Inter, Plus Jakarta, Geist), muito espaço em branco, cantos arredondados moderados.
4. **Preço transparente e antecipado:** página/tabela de preços simples; limites do grátis explícitos.
5. **Prova social e confiança:** números de uso, depoimentos reais (quando houver), selo do meio de pagamento, política de reembolso visível.
6. **Grátis limitado por quantidade, não por qualidade:** AnkiDecks dá 4 gerações/mês no plano grátis; Gemini/NotebookLM limita gerações por dia; Gizmo impõe espera entre importações; StudyFetch libera o primeiro conjunto. Ninguém dá geração ilimitada sem conta.

**Direção de design proposta:**

- Paleta: fundo `#FAFAF9`, texto `#1C1917`, destaque único (ex.: verde‑azulado `#0F766E` — remete a "aprovado/Pix" e foge do roxo genérico), estados de sucesso/erro com contraste AA. Modo escuro opcional.
- Tipografia: Inter (Google Fonts), 16px base, títulos 32–40px.
- Estrutura da página: **Hero com gerador** → **Como funciona (3 passos)** → **Exemplo de baralho** (cards reais clicáveis) → **Preços** → **FAQ** → **Rodapé** (Termos, Privacidade, Contato).
- Stepper fixo no topo do fluxo: **1 Descreva → 2 Veja a prévia → 3 Pague e baixe**.

## 1.7 Estratégia financeira

### Problema 1 — "Gerou, desistiu, perdi o custo dos tokens"
### Problema 2 — "Cobro antes de o usuário ver qualquer coisa"

Os dois se resolvem invertendo a ordem do fluxo:

> **Prévia grátis pequena → pagamento → geração completa.**

1. Usuário descreve o tema e escolhe a quantidade → **vê o preço antes**.
2. Clica **"Ver prévia grátis"** → o sistema gera o **plano de subtópicos + 5 cards** com o modelo mais barato e mostra na tela.
3. Gostou → paga o Pix → **só então** o sistema gera o restante (os 5 da prévia entram no baralho final).
4. Não gostou → pode ajustar o tema e gerar outra prévia (dentro do limite diário) ou ir embora. **Custo perdido: só a prévia.**

**Por que isso não afugenta o usuário:** ele vê valor antes de pagar, o preço é conhecido desde o início, e não há contador de urgência nem pop‑up insistente. É o mesmo raciocínio do remove.bg (prévia grátis, paga pelo arquivo completo).

**E se todo mundo só fizer a prévia?** Controle por limites e orçamento, não por pressão:

| Controle | Valor sugerido (configurável por variável de ambiente) |
|---|---|
| Tamanho da prévia | 5 cards |
| Prévias por visitante/dia | 3 (cookie assinado + hash do IP) |
| Captcha invisível | Cloudflare Turnstile (gratuito) antes de gerar prévia |
| Orçamento global diário para prévias | ex.: US$ 0,50/dia → ao atingir, prévias pausam e o usuário vê "prévias esgotadas hoje, você ainda pode comprar direto" |
| Modelo da prévia | o mais barato disponível, thinking desligado |
| Cache | mesma prévia para o mesmo tema + quantidade por 24h |

**Conta de equilíbrio (para você acompanhar):** `prévias pagas por uma venda = (preço − taxa Pix − custo da geração completa) ÷ custo médio de uma prévia`. Com prévias custando frações de centavo, **uma venda de R$ 3,90 cobre centenas de prévias**. O painel de consumo (Fase 6) mostra a taxa de conversão real para você ajustar os limites.

**Outras mitigações sem pressão:**

- Pedido não pago fica salvo por 7 dias com link para retomar (a prévia continua lá).
- Um lembrete por e‑mail **somente se** o usuário marcar "me avise" (opt‑in, uma única vez).
- Falhou a geração depois do pagamento? Tenta de novo automaticamente; se ainda assim não entregar, **reembolso automático** via API do Mercado Pago. Isso gera confiança e evita chargebacks.
- Futuro opcional: **pacotes de créditos** (ex.: 300 cards por R$ X) para reduzir fricção de um Pix por baralho.

**Limite máximo de cards:** recomendo **500** por pedido (configurável em `MAX_CARDS`). Acima disso, a qualidade cai (repetição) e o tempo cresce muito; as faixas de 1000 e 2000 podem voltar quando a geração em lotes estiver madura.

---

# PARTE 2 — PLANO DE IMPLEMENTAÇÃO

## Diretrizes gerais para o Claude Code

- Stack mantida: **Python + Flask**, deploy na **Vercel**. Um único ponto de entrada (`api/index.py` apenas importa `create_app()`).
- Banco: **SQLAlchemy 2.x**. Local: SQLite. Produção: Postgres gratuito (Neon ou Supabase) via `DATABASE_URL`. Migrações com **Alembic**.
- Valores monetários **sempre em centavos (int)**.
- Todos os limites em variáveis de ambiente com padrões seguros.
- Nada de segredo em arquivo versionado. Mensagens ao usuário em português.
- Cada fase termina com testes passando (`pytest`) e um resumo das mudanças.

### Estrutura de pastas alvo

```
gerador-flashcards/
├── api/index.py                  # só: from app import create_app; app = create_app()
├── app/
│   ├── __init__.py               # create_app(), registro de blueprints
│   ├── config.py                 # lê env, valida, valores padrão
│   ├── db.py                     # engine/sessão SQLAlchemy
│   ├── models.py                 # Pedido, Pagamento, Card, EventoWebhook, UsoIA, CotaPrevia
│   ├── precos.py                 # tabela de faixas, cálculo em centavos
│   ├── seguranca.py              # rate limit, turnstile, tokens, headers
│   ├── ia/
│   │   ├── base.py               # interface LLMProvider (preparada p/ roteador futuro)
│   │   ├── gemini.py             # implementação com google-genai + structured output
│   │   ├── prompts.py            # prompts de plano, prévia e lote
│   │   └── geracao.py            # orquestra plano → prévia → lotes → dedupe
│   ├── pagamentos/
│   │   ├── base.py               # interface PaymentProvider
│   │   ├── mercadopago.py        # provider real
│   │   └── fake.py               # provider de teste (sem dinheiro)
│   ├── exportacao/
│   │   ├── anki.py               # gera .apkg em memória a partir dos cards
│   │   └── pdf.py                # PDF de fontes (com escape)
│   ├── rotas/
│   │   ├── paginas.py            # /, /pedido/<token>, /termos, /privacidade
│   │   ├── api_pedidos.py
│   │   ├── webhooks.py
│   │   └── dev.py                # só registrado se APP_ENV=development
│   ├── templates/  static/
├── migrations/                   # Alembic
├── tests/
├── .env.example                  # só placeholders
└── requirements.txt
```

---

## FASE 0 — Correções urgentes de segurança (fazer primeiro, deploy imediato)

**Ação manual do Lutero (antes de tudo):**
1. **Revogar a chave do Gemini** atual no Google AI Studio e gerar outra (ela está em texto puro no `env.example`).
2. Colocar a nova chave apenas no `.env` local e nas variáveis de ambiente da Vercel.

**Tarefas do Claude Code:**

- [ ] 0.1 Substituir o conteúdo do `env.example` por placeholders (`GEMINI_API_KEY=coloque_sua_chave_aqui`) e renomear para `.env.example`. Confirmar que `.env` está no `.gitignore`.
- [ ] 0.2 **Remover** as rotas `/criar-pagamento-pix` e `/verificar-pagamento/<payment_id>` e, no front, o botão "💳 Pagar com PIX" e o formulário de valor livre.
- [ ] 0.3 `/download`: negar por padrão. Só servir se o pedido existir **e** estiver pago. Nunca servir arquivo cujo ID não seja reconhecido. Apagar a pasta `output/` do projeto (arquivos antigos).
- [ ] 0.4 Tirar `debug=True`; usar `debug=os.getenv("FLASK_DEBUG") == "1"` e `host="127.0.0.1"` por padrão.
- [ ] 0.5 Enquanto a Fase 2 não sai: **desativar a geração paga em produção** ou manter o limite atual de 100 com um aviso — decisão do Lutero. Recomendação: colocar um limite global diário de gerações via variável de ambiente para conter custo.
- [ ] 0.6 Uploads: diretório temporário único por requisição (`tempfile.mkdtemp`) com nomes `uuid4`; lista branca de extensões; máx. 5 arquivos.
- [ ] 0.7 Parar de retornar `str(e)` ao cliente; logar internamente com um `erro_id` e devolver mensagem amigável contendo esse `erro_id`.

**Critério de aceite:** nenhum endpoint cria cobrança fora de um pedido; download sem pagamento retorna 403/404 mesmo após reiniciar o servidor; nenhum segredo em arquivo versionado.

---

## FASE 1 — Arquitetura, banco de dados e unificação

- [ ] 1.1 Criar a estrutura de pastas acima. `api/index.py` e execução local passam a usar o **mesmo** `create_app()`. Remover o `app.py` antigo (ou deixá‑lo como wrapper de 3 linhas para `python app.py` local). Ajustar `.vercelignore`.
- [ ] 1.2 Atualizar dependências: `Flask>=3.0`, `Werkzeug>=3.0`, `google-genai`, `SQLAlchemy>=2.0`, `alembic`, `psycopg[binary]`, `mercadopago`, `genanki`, `reportlab`, `python-dotenv`, `pypdf`, `python-docx`, `pytest`. Remover `google-generativeai`.
- [ ] 1.3 `config.py` com todas as variáveis:

  | Variável | Padrão | Uso |
  |---|---|---|
  | `APP_ENV` | `development` | `development` / `production` |
  | `DATABASE_URL` | `sqlite:///local.db` | Postgres em produção |
  | `SECRET_KEY` | — (obrigatória em prod) | assinar cookies |
  | `PAYMENT_PROVIDER` | `fake` em dev | `fake` / `mercadopago` |
  | `MERCADOPAGO_ACCESS_TOKEN`, `MERCADOPAGO_WEBHOOK_SECRET` | — | |
  | `GEMINI_API_KEY` | — | |
  | `MODELO_PREVIA`, `MODELO_GERACAO` | modelos Flash‑Lite / Flash atuais | trocar sem deploy de código |
  | `MAX_CARDS` | `500` | limite por pedido |
  | `TAMANHO_PREVIA` | `5` | |
  | `TAMANHO_LOTE` | `40` | |
  | `PREVIAS_POR_DIA` | `3` | por visitante |
  | `ORCAMENTO_PREVIAS_USD_DIA` | `0.50` | teto global |
  | `PIX_EXPIRACAO_MIN` | `30` | |
  | `DIAS_RETENCAO_PEDIDO` | `30` | download disponível |
  | `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET` | — | captcha |

  Em `production`, falhar na inicialização se faltar `SECRET_KEY`, `DATABASE_URL`, chave do provedor de pagamento ou se `PAYMENT_PROVIDER=fake`.

- [ ] 1.4 Modelos (`models.py`):

  - **Pedido**: `id (uuid)`, `token_acesso` (32 bytes aleatórios url‑safe, único — é o que vai na URL do pedido), `email` (opcional até o pagamento), `prompt`, `prompt_hash`, `tipo_entrada` (tema/arquivo/texto), `referencias_arquivos` (JSON: URIs no Gemini ou texto extraído), `quantidade_solicitada`, `preco_centavos`, `nome_deck`, `plano_subtopicos` (JSON), `fontes` (JSON), `status`, `criado_em`, `pago_em`, `concluido_em`, `expira_em`, `visitante_hash`.
  - **Status do pedido** (máquina de estados, transições validadas em um único lugar):
    `rascunho → previa_pronta → aguardando_pagamento → pago → gerando → concluido`
    e ramos `falhou`, `reembolsado`, `expirado`.
  - **Pagamento**: `id`, `pedido_id`, `provider`, `provider_payment_id` (**string**), `status`, `valor_centavos`, `qr_code`, `qr_code_base64`, `ticket_url`, `expira_em`, `idempotency_key`, `criado_em`, `atualizado_em`. Um pedido pode ter vários (QR renovado), mas só um ativo.
  - **Card**: `pedido_id`, `ordem`, `pergunta`, `resposta`, `lote` (0 = prévia), `hash_normalizado`.
  - **EventoWebhook**: `provider`, `evento_id` (único) — idempotência.
  - **UsoIA**: `pedido_id`, `etapa` (plano/prévia/lote_n), `modelo`, `tokens_entrada`, `tokens_saida`, `custo_estimado_usd`, `latencia_ms`, `sucesso`.
  - **CotaPrevia**: `visitante_hash`, `data`, `quantidade` (ou usar tabela de contadores genérica).

- [ ] 1.5 `exportacao/anki.py` gera o `.apkg` **em memória** a partir dos Cards do banco (genanki escreve em arquivo temporário → ler → apagar). Usar IDs de modelo/deck **determinísticos** (derivados do `pedido.id`) para que baixar de novo não crie baralho duplicado no Anki. Escapar HTML dos campos.
- [ ] 1.6 `exportacao/pdf.py` com `escape()` em cada fonte.
- [ ] 1.7 Nenhum arquivo gerado é guardado em disco; tudo é produzido no download.

**Critério de aceite:** `flask run` local e Vercel usam o mesmo código; `alembic upgrade head` cria as tabelas; testes de exportação passam.

---

## FASE 2 — Pagamentos confiáveis, testáveis e recuperáveis

### 2.1 Interface de provedor

```python
class PaymentProvider(Protocol):
    def criar_pix(self, pedido, idempotency_key: str) -> ResultadoPix: ...
    def consultar(self, provider_payment_id: str) -> StatusPagamento: ...
    def reembolsar(self, provider_payment_id: str) -> bool: ...
    def validar_webhook(self, headers, query_args, body) -> EventoValidado | None: ...
```

### 2.2 `MercadoPagoProvider`

- [ ] Criar o Pix com `X-Idempotency-Key`, `external_reference = pedido.id`, `date_of_expiration = agora + PIX_EXPIRACAO_MIN`, `notification_url` = URL pública do webhook, e o e‑mail informado pelo usuário.
- [ ] Avaliar a **API de Orders** (`/v1/orders`) do Mercado Pago, que é a documentada atualmente para Pix e tem simulação de aprovação no ambiente de teste (ver 2.5). Se usar a API antiga `/v1/payments`, manter a mesma interface.
- [ ] **Validação correta do webhook:**
  1. Ler header `x-signature` (formato `ts=<ts>,v1=<hash>`) e `x-request-id`.
  2. Pegar `data.id` **da query string** e convertê‑lo para minúsculas se for alfanumérico.
  3. Montar o manifest `id:<data.id>;request-id:<x-request-id>;ts:<ts>;` (omitindo partes ausentes, conforme documentação).
  4. `HMAC-SHA256(secret, manifest)` em hex, comparar com `v1` usando `hmac.compare_digest`.
  5. Rejeitar se `ts` for muito antigo (ex.: > 10 min).
  6. **Nunca confiar no corpo**: após validar, consultar o pagamento na API e usar esse status.
  7. Registrar `EventoWebhook` para ignorar duplicados; responder 200 rápido.
- [ ] Localizar o pedido por `external_reference` / `provider_payment_id` **como string** (corrige o bug int×str).
- [ ] Conferir se `valor pago == preco_centavos` do pedido antes de marcar como pago.

### 2.3 `FakePaymentProvider` (testar sem dinheiro real)

- [ ] Gera um QR code falso (imagem PNG com o texto "PIX DE TESTE") e um código copia‑e‑cola fictício.
- [ ] Status guardado no banco.
- [ ] Rota **só em desenvolvimento**: `POST /dev/pagamentos/<id>/aprovar` (e `/recusar`, `/expirar`). Ela chama o mesmo código que o webhook chamaria.
- [ ] No front, quando `APP_ENV=development`, mostrar na tela do Pix um painel amarelo "Modo de teste" com os botões **Simular aprovação / Simular recusa / Simular expiração**.
- [ ] A aplicação **se recusa a iniciar** com `PAYMENT_PROVIDER=fake` em `production`.

### 2.4 Pedido persistente e retomada (resolve o problema do pop‑up)

- [ ] Página **`/pedido/<token_acesso>`**: mostra prévia, status, preço, QR/copia‑e‑cola, contador de expiração (informativo), botão **"Gerar novo código Pix"** quando expirado, progresso da geração e botões de download quando concluído.
- [ ] Ao criar o pedido, o front salva `{token, nome_deck, criado_em}` no `localStorage` e mostra no topo da página inicial um banner discreto **"Você tem 1 pedido em andamento — continuar"**. Seção "Meus pedidos" com os últimos 5.
- [ ] O modal/painel de pagamento pode ser fechado à vontade: fechar só oculta; o polling continua e o banner aparece.
- [ ] Após pagar, e‑mail (se fornecido) com o link do pedido — pode ficar para a Fase 6 se não houver serviço de e‑mail; o link na tela + localStorage já resolve o essencial.
- [ ] Downloads disponíveis por `DIAS_RETENCAO_PEDIDO` pelo mesmo link.

### 2.5 Como testar pagamentos sem dinheiro real (documentar no README)

1. **Dia a dia / testes automáticos:** `PAYMENT_PROVIDER=fake` + botões "Simular aprovação". Zero dependência externa.
2. **Integração real em modo teste:** usar as **credenciais de teste** do Mercado Pago (o seu `.env` já usa um token que começa com `TEST-`) e **contas de usuário de teste** criadas no painel de desenvolvedor. Na API de Orders, a documentação de teste de Pix indica usar `payer.first_name = "APRO"` para simular aprovação.
3. **Webhook na máquina local:** expor o Flask com um túnel (`cloudflared tunnel --url http://localhost:5000` ou `ngrok http 5000`), cadastrar essa URL no painel de Webhooks do Mercado Pago (modo teste) e usar a opção **"Simular notificação"** do painel para validar a assinatura.
4. **Ambiente de *preview* na Vercel** com credenciais de teste e banco separado, antes de promover para produção.

### 2.6 Testes (pytest)

- [ ] Assinatura do webhook: válida, inválida, `ts` expirado, evento duplicado.
- [ ] Máquina de estados: não é possível baixar sem `concluido`; não é possível pagar pedido `expirado` sem gerar novo Pix.
- [ ] Download 403 para pedido não pago, 404 para token inexistente, 200 após aprovação simulada.
- [ ] Valor divergente não aprova.

**Critério de aceite:** fechar o modal, recarregar a página, reiniciar o servidor — o pedido continua lá e é possível pagar e baixar. Todo o fluxo roda localmente sem dinheiro real.

---

## FASE 3 — Novo fluxo de geração: prévia grátis → pagamento → geração em lotes

### 3.1 Endpoints

| Método | Rota | Função |
|---|---|---|
| `GET` | `/api/preco?quantidade=N` | devolve preço em centavos e a faixa (para mostrar antes de gerar) |
| `POST` | `/api/pedidos` | recebe tema/arquivos/texto + quantidade + token Turnstile; cria pedido; gera **plano + prévia**; devolve `token_acesso`, cards da prévia, preço |
| `GET` | `/api/pedidos/<token>` | status completo (para polling) |
| `POST` | `/api/pedidos/<token>/pagamento` | cria Pix ou devolve o ativo se ainda válido; exige e‑mail |
| `POST` | `/api/pedidos/<token>/lotes/<n>` | gera o lote *n* **somente se pago**; idempotente (se já existe, devolve o existente) |
| `GET` | `/api/pedidos/<token>/baralho.apkg` | só `concluido` |
| `GET` | `/api/pedidos/<token>/fontes.pdf` | só `concluido` |
| `POST` | `/webhooks/mercadopago` | webhook |

### 3.2 Geração

- [ ] **Plano (na prévia):** uma chamada barata devolve `nome_deck`, lista de subtópicos com quantidade de cards por subtópico (somando `quantidade_solicitada`), e os `TAMANHO_PREVIA` primeiros cards. Tudo com `response_schema`.
- [ ] **Lotes (após pagamento):** o **front** conduz a geração chamando `/lotes/1`, `/lotes/2`, ... em sequência e atualizando a barra de progresso. Isso cabe no tempo limite de funções serverless e dá feedback real. Cada lote recebe seus subtópicos + a lista resumida de perguntas já existentes para evitar repetição.
- [ ] Se o usuário fechar a aba durante a geração, ao reabrir `/pedido/<token>` o front continua do próximo lote pendente.
- [ ] Deduplicação por `hash_normalizado` (minúsculas, sem acentos/pontuação) + similaridade simples; se faltar card, um lote extra pequeno completa.
- [ ] Retentativa por lote (até 2) com backoff; fallback **real** de modelo no momento da chamada (se o modelo principal der erro/limite, tenta o secundário).
- [ ] Se ao final o pedido não chegar a um mínimo (ex.: 90% do solicitado) após as tentativas: marcar `falhou`, oferecer ao usuário **"baixar o que foi gerado + reembolso proporcional"** ou **reembolso total** automático. Registrar tudo.
- [ ] Preço cobrado = faixa da **quantidade solicitada** (conhecida antes); a garantia acima protege o cliente.
- [ ] Arquivos enviados: extrair texto de PDF/DOCX/TXT no servidor (limite de caracteres configurável) e salvar no pedido; imagens vão para a Files API do Gemini e a referência é salva (válida por tempo limitado — a geração completa deve ocorrer dentro desse prazo; se expirar, pedir reenvio). Informar o usuário que o conteúdo é processado por IA de terceiros.
- [ ] Remover a regex `limpar_quantidade_do_prompt`: em vez de apagar, o **front** detecta "50 flashcards" no texto e ajusta o seletor de quantidade, com um aviso discreto "Ajustamos a quantidade para 50".
- [ ] Configurar orçamento de *thinking* baixo/zero na geração e zero na prévia.
- [ ] **Fatiar o material enviado por lote** (cada lote recebe só a sua fatia do PDF/texto + cache de contexto). Reenviar o material inteiro a cada lote pode dar prejuízo — ver `ANALISE_PRECOS_E_CUSTOS.md`, seção 3.3.
- [ ] Registrar `UsoIA` em toda chamada.

**Critério de aceite:** um pedido de 200 cards é gerado em ~5 lotes com barra de progresso; derrubar a conexão no meio e reabrir o link retoma do ponto certo; nenhum card duplicado exato.

---

## FASE 4 — Anti‑abuso e controle de orçamento

- [ ] Rate limit por IP (ex.: 10 req/min em `/api/pedidos`, 60 req/min em polling). Em serverless, guardar contadores no banco (tabela simples com janela de tempo) ou num Redis gratuito (Upstash), atrás de uma interface para poder trocar.
- [ ] **Cloudflare Turnstile** no botão "Ver prévia grátis" (validação no servidor).
- [ ] Cota de prévias por visitante (`PREVIAS_POR_DIA`) usando cookie assinado + hash de IP (sem guardar IP em claro — LGPD).
- [ ] **Orçamento diário global** de prévias em USD (soma de `UsoIA.custo_estimado` do dia). Ao atingir: prévias pausadas; compra direta continua disponível ("Prévias grátis esgotadas por hoje — você ainda pode gerar o baralho completo").
- [ ] Cache de prévia por `prompt_hash + quantidade` por 24h (não vale para arquivos).
- [ ] Limites de upload: 5 arquivos, 16 MB total, N páginas/caracteres.
- [ ] Headers de segurança: `Content-Security-Policy`, `X-Content-Type-Options`, `Referrer-Policy`, `frame-ancestors 'none'`.
- [ ] Expirar pedidos não pagos após 7 dias (job ou limpeza preguiçosa em cada requisição; na Vercel pode ser um Cron Job diário).

---

## FASE 5 — Redesign da interface (UI/UX)

Referência visual: seção 1.6. Manter HTML + CSS + JS puro (sem framework) para não aumentar complexidade; separar CSS e JS em `static/`.

- [ ] 5.1 **Página inicial** com: Hero (título curto + gerador), "Como funciona" em 3 passos, "Exemplo de baralho" com cards que viram, tabela de **Preços** (faixas), **FAQ** (o que é Anki; como importar `.apkg` no computador/celular; o que é a prévia grátis; política de reembolso; privacidade dos arquivos), rodapé com Termos, Privacidade e contato.
- [ ] 5.2 **Gerador:** abas *Tema · Arquivo · Colar texto*; área de arrastar arquivos visível; chips de quantidade com preço ao lado ("50 cards · R$ 3,90"); preço total sempre visível; botão principal **"Ver prévia grátis"**.
- [ ] 5.3 **Stepper** 1 Descreva → 2 Prévia → 3 Pague e baixe.
- [ ] 5.4 **Tela de prévia:** 5 cards que viram ao clicar/tocar, nome do baralho, lista de subtópicos que serão cobertos, preço, botões **"Gerar baralho completo — R$ X"** e "Ajustar tema".
- [ ] 5.5 **Pagamento** (painel na própria página do pedido, não um modal bloqueante): campo de e‑mail ("para receber o link do seu baralho"), QR code, botão grande **"Copiar código Pix"** (principal no mobile), contador de expiração, status em português ("Aguardando pagamento", "Pago!", "Código expirado — gerar novo"), texto "Pode fechar esta página; seu pedido fica salvo neste link".
- [ ] 5.6 **Geração:** barra de progresso por lote e mensagens de etapa.
- [ ] 5.7 **Conclusão:** download automático do `.apkg`, botão para PDF de fontes, mini‑tutorial "Como importar no Anki", botão "Criar outro baralho".
- [ ] 5.8 **Acessibilidade:** contraste AA, `:focus-visible`, `<dialog>` quando houver modal, `aria-live="polite"` nos status, todos os controles como `<button>`, textos alternativos, navegação por teclado.
- [ ] 5.9 **Responsivo** mobile‑first (360px) sem rolagem horizontal.
- [ ] 5.10 Remover emojis como ícones (usar SVG), remover gradiente roxo de tela cheia, adotar a paleta e a fonte Inter da seção 1.6.
- [ ] 5.12 Rodapé com aviso: "Anki® é marca registrada da Ankitects. Este site não é afiliado nem endossado pelo Anki." Não usar "Anki" no nome/logo do produto (ver `ANALISE_PRECOS_E_CUSTOS.md`, seção 7.2).
- [ ] 5.11 Páginas `/termos` e `/privacidade` com textos simples (LGPD: quais dados, por quanto tempo, que arquivos vão para um provedor de IA).

---

## FASE 6 — Testes, observabilidade e operação

- [ ] Suite `pytest` cobrindo: preço por faixa, máquina de estados, webhook, provider fake, rate limit, exportação `.apkg`/PDF, geração com provedor de IA *mockado* (sem gastar tokens).
- [ ] Teste ponta a ponta com Playwright: tema → prévia → pagamento fake → aprovação simulada → lotes → download.
- [ ] Logs estruturados (JSON) com `pedido_id` e `erro_id`.
- [ ] Página `/admin` protegida por senha (variável de ambiente) com: pedidos do dia, taxa de conversão prévia→pagamento, custo de IA do dia/mês, receita, pedidos com falha, botão de reembolso manual.
- [ ] Atualizar README: como rodar local, como testar pagamentos (seção 2.5), variáveis de ambiente, deploy.
- [ ] Limpar arquivos de documentação antigos/duplicados (`COMO_USAR.txt`, `GUIA_RAPIDO_DEPLOY.txt`, `COMANDOS_DEPLOY.txt`, `SOLUCAO_PYTHON_ANTIGO.md`) consolidando no README.

---

# PARTE 3 — FUTURO: ROTEADOR DE MODELOS DE IA

> ⚠️ **NOTA IMPORTANTE — NÃO IMPLEMENTAR AGORA.**
> Esta parte descreve uma atualização futura. Claude Code: **não implemente nada desta seção** até o Lutero pedir explicitamente. A única preparação permitida agora é a que já está nas Fases 1 e 3: a interface `LLMProvider` em `app/ia/base.py`, os nomes de modelo vindos de configuração e o registro de consumo em `UsoIA`.

**Nome correto do recurso:** o que você descreveu é um **roteador de modelos** (*model router*). Um "balanceador de carga" distribui requisições iguais entre servidores idênticos; aqui a ideia é **escolher o modelo certo** para cada pedido conforme a complexidade — o objetivo é precisão sem desperdício.

### Visão geral

```
pedido ──► Classificador (barato) ──► Política de roteamento ──► Provedor escolhido ──► Validador de qualidade
                │                              │                        │                      │
         domínio, profundidade,         tabela configurável      fallback/circuit        amostra reprovada →
         tamanho da fonte, qtd          (YAML/banco)             breaker por provedor    re-gera com modelo acima
```

### Componentes

1. **Classificador de complexidade**
   - Primeiro por **heurísticas gratuitas**: tamanho/tipo dos arquivos, presença de fórmulas/LaTeX, quantidade pedida, palavras‑chave de domínio (medicina, direito, engenharia, concursos).
   - Se incerto, uma chamada ao modelo mais barato devolvendo JSON: `{dominio, nivel: basico|intermediario|avancado, exige_precisao_factual: bool, multimodal: bool}`.
   - Resultado salvo no pedido (reaproveitado em todos os lotes).
2. **Política de roteamento** (arquivo `roteamento.yaml` ou tabela no banco), por exemplo:
   - básico + texto → modelo *lite* barato
   - intermediário ou arquivos grandes → modelo *flash*
   - avançado + precisão factual (medicina, direito) → modelo *pro* **ou** flash + etapa de verificação
   - multimodal (imagens) → modelo com visão
3. **Provedores plugáveis**: implementações de `LLMProvider` para Gemini, OpenAI, Anthropic etc., cada uma com preço por token configurado para calcular custo.
4. **Resiliência**: fallback automático para o próximo provedor da lista em caso de erro/limite, *circuit breaker* (tira do ar por alguns minutos um provedor que falha em sequência), timeouts por etapa.
5. **Validador de qualidade**: um modelo barato revisa uma amostra de cada lote (factualidade, duplicidade, clareza). Se reprovar acima de um limite, o lote é refeito com o modelo do nível acima.
6. **Aprendizado com dados**: usar `UsoIA` + taxa de reprovação do validador + reclamações/reembolsos para ajustar a tabela de roteamento periodicamente.
7. **Controles de custo**: teto de custo por pedido (se o roteamento escolher um modelo caro demais para a margem daquela faixa de preço, rebaixar ou dividir em mais lotes); relatório de margem por faixa no `/admin`.

### Regras de custo e política inicial

Ver `ANALISE_PRECOS_E_CUSTOS.md`, seção 5: política de modelos por perfil (estudante, concurseiro, autodidata), teto de custo por nível de risco (25% baixo / 30% médio / 40% alto) **sem rebaixar em silêncio o modelo em assuntos de alta precisão** (seção 5.4: riscos de fidelidade e política recomendada), limite de thinking, material fatiado, limite de páginas por faixa e detecção do tipo de card (cloze para lei seca, invertido para idiomas).

### Pré‑requisitos antes de começar esta parte

- Fases 0–6 concluídas e em produção.
- Pelo menos algumas semanas de dados em `UsoIA` para ter base de comparação.
- Conjunto de avaliação: ~30 temas de referência com cards "bons" para medir se o roteador mantém a qualidade.

---

# APÊNDICE — Fontes consultadas

- Mercado Pago — Teste de compra com Pix (API de Orders): https://www.mercadopago.com.br/developers/pt/docs/checkout-api-orders/integration-test/pix
- Mercado Pago — Notificações e validação de `x-signature`: https://www.mercadopago.com.br/developers/pt/docs/qr-code/notifications.md
- AnkiDecks — Preços e limites do plano grátis: https://anki-decks.com/payment/pricing/
- Comparativo de geradores de flashcards com IA (StudyFetch, Knowt, AnkiDecks, RemNote, Gizmo, Quizlet): https://www.scriptbyai.com/best-ai-flashcard-generators/
- Preços da API Gemini (referência de terceiros — conferir na página oficial do Google antes de decidir): https://developer.puter.com/tutorials/gemini-api-pricing/
