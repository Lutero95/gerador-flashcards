# 📚 Gerador de Flashcards Anki

Sistema web para gerar arquivos APKG (Anki) a partir de arquivos JSON contendo perguntas e respostas.

## 🚀 Funcionalidades

- Upload de arquivos JSON com perguntas e respostas
- Geração automática de decks no formato APKG
- Download do arquivo gerado para importação no Anki
- Interface web moderna e intuitiva
- Suporte a drag-and-drop de arquivos
- Validação de formato JSON

## 📋 Pré-requisitos

- Python 3.7 ou superior
- pip (gerenciador de pacotes Python)

## 🔧 Instalação

1. Clone ou baixe este repositório

2. Instale as dependências:
```bash
py -m pip install -r requirements.txt
```
   
   > **Nota para Windows**: Use `py -m pip` em vez de apenas `pip`

3. Configure a chave da API do Gemini:
   - Copie o arquivo `.env.example` para `.env`:
   ```bash
   copy .env.example .env
   ```
   - Abra o arquivo `.env` e substitua `sua_chave_aqui` pela sua chave real do Gemini
   - Obtenha sua chave em: https://makersuite.google.com/app/apikey
   
   > **Importante**: O arquivo `.env` não será enviado para o GitHub (já está no .gitignore)

## 🚀 Deploy no Vercel (Recomendado)

**Quer hospedar seu gerador online gratuitamente?**

➡️ Siga o guia completo em **[DEPLOY_VERCEL.md](DEPLOY_VERCEL.md)**

Com o Vercel, sua aplicação fica:
- ✅ Acessível 24/7 na internet
- ✅ Com HTTPS gratuito
- ✅ Deploy automático ao atualizar o código
- ✅ Sem custo (plano gratuito generoso)

**Basta:**
1. Subir o código para o GitHub
2. Conectar ao Vercel
3. Pronto! URL pública gerada automaticamente

---

## ▶️ Como Usar Localmente

1. Inicie o servidor:
```bash
py app.py
```
   
   > **Nota para Windows**: Use `py` em vez de `python`

2. Abra seu navegador e acesse:
```
http://localhost:5000
```

3. Prepare seu arquivo JSON no formato correto (veja exemplo abaixo)

4. Faça upload do arquivo através da interface

5. Clique em "Gerar Deck Anki"

6. Baixe o arquivo APKG gerado

7. Importe o arquivo no Anki

## 📝 Formato do JSON

O arquivo JSON deve seguir este formato:

```json
{
  "nome_deck": "Meu Baralho de Estudos",
  "cards": [
    {
      "pergunta": "Qual é a capital do Brasil?",
      "resposta": "Brasília"
    },
    {
      "pergunta": "Quanto é 2 + 2?",
      "resposta": "4"
    },
    {
      "pergunta": "Quem descobriu o Brasil?",
      "resposta": "Pedro Álvares Cabral"
    }
  ]
}
```

### Campos:

- **nome_deck** (opcional): Nome do baralho que aparecerá no Anki. Se não fornecido, será usado "Flashcards"
- **cards** (obrigatório): Lista de flashcards
  - **pergunta** (obrigatório): Texto da frente do cartão
  - **resposta** (obrigatório): Texto do verso do cartão

### Formato alternativo (lista simples):

Você também pode usar uma lista direta:

```json
[
  {
    "pergunta": "Qual é a capital do Brasil?",
    "resposta": "Brasília"
  },
  {
    "pergunta": "Quanto é 2 + 2?",
    "resposta": "4"
  }
]
```

## 📁 Estrutura do Projeto

```
gerador-flashcards/
├── app.py                 # Execução local: aplica migrações e sobe o servidor
├── api/index.py           # Entrada da Vercel: usa o mesmo create_app()
├── app/
│   ├── __init__.py        # create_app()
│   ├── config.py          # Variáveis de ambiente, padrões e validação de produção
│   ├── db.py / models.py  # SQLAlchemy: Pedido, Pagamento, Card, EventoWebhook, UsoIA, CotaPrevia
│   ├── pedidos.py         # Máquina de estados do pedido
│   ├── precos.py          # Faixas de preço (centavos)
│   ├── ia/                # Provedor Gemini (google-genai), prompts e orquestração
│   ├── pagamentos/        # Mercado Pago (Pix)
│   ├── exportacao/        # .apkg e PDF gerados na hora do download
│   ├── rotas/             # Páginas, API e webhooks
│   ├── templates/         # Páginas (base, início, pedido, termos, privacidade) e ícones SVG
│   └── static/            # CSS e JavaScript (sem framework; carregados com CSP)
├── migrations/            # Alembic
├── tests/                 # pytest
└── .env.example           # Modelo de configuração (só placeholders)
```

## 🛠️ Tecnologias Utilizadas

- **Flask 3**: Framework web Python
- **SQLAlchemy 2 + Alembic**: banco de dados (SQLite local, Postgres em produção)
- **google-genai**: API do Gemini com saída estruturada
- **genanki / reportlab**: geração do .apkg e do PDF de fontes
- **Mercado Pago**: pagamento via Pix

## ⚙️ Configuração

Todas as opções vêm de variáveis de ambiente; veja `.env.example`. Por padrão:
- Porta 5000, escutando só em 127.0.0.1, com debug desligado (`FLASK_DEBUG=1` liga)
- Banco `sqlite:///local.db` (as migrações rodam sozinhas no `python app.py`; manualmente: `alembic upgrade head`)
- Até `MAX_CARDS=500` cards por pedido
- Prévias grátis: 3 por navegador e 15 por IP por dia, com teto de US$ 0,50/dia no total; esgotadas, a compra
  direta (sem prévia) continua disponível
- Rate limit por IP, Cloudflare Turnstile (obrigatório em produção), CSP com nonce e demais cabeçalhos de segurança
- Limpeza diária (`/tarefas/limpeza`, Cron da Vercel): expira pedidos não pagos após 7 dias e descarta o material
  enviado pelos alunos

Testes: `pip install -r requirements-dev.txt` e depois `python -m pytest tests`.

## 🔄 Como funciona um pedido

1. **Prévia grátis** (`POST /api/pedidos`): o aluno descreve o tema (e pode anexar PDF, DOCX, TXT, imagens ou colar
   texto) e escolhe a quantidade — o preço aparece antes (`GET /api/preco`). A IA mais barata monta o plano de
   subtópicos e gera 5 cards de amostra.
2. **Pagamento** (`POST /api/pedidos/<token>/pagamento`): Pix com e-mail, na página `/pedido/<token>`.
3. **Geração em lotes** (`POST /api/pedidos/<token>/lotes/<n>`): depois de pago, a página pede um lote de ~40 cards
   por vez, mostrando o progresso. Fechou a aba? Ao reabrir, continua do lote seguinte. Cada lote recebe só a sua
   fatia do material, as perguntas já existentes (para não repetir) e tenta o modelo reserva se o principal falhar.
4. **Entrega**: `.apkg` e PDF de fontes gerados na hora do download. Se a IA não chegar a 90% do pedido, o aluno
   escolhe entre ficar com os cards gerados + reembolso proporcional, ou reembolso total.

## 💳 Como testar pagamentos sem dinheiro real

1. **Dia a dia (padrão em desenvolvimento):** `PAYMENT_PROVIDER=fake`. Gere um baralho, informe um e-mail na página do pedido e use o painel amarelo **Modo de teste** para *Simular aprovação / recusa / expiração*. As rotas `POST /dev/pagamentos/<id>/aprovar|recusar|expirar` só existem com `APP_ENV=development`, e a aplicação não sobe com o fake em produção.
2. **Integração real em modo teste:** `PAYMENT_PROVIDER=mercadopago` com as **credenciais de teste** (`TEST-...`) e contas de usuário de teste do painel de desenvolvedor do Mercado Pago.
3. **Webhook na sua máquina:** exponha o Flask com um túnel (`cloudflared tunnel --url http://localhost:5000` ou `ngrok http 5000`), defina `URL_PUBLICA` com a URL https do túnel, cadastre `<URL_PUBLICA>/webhooks/mercadopago` no painel de Webhooks (modo teste), configure `MERCADOPAGO_WEBHOOK_SECRET` e use **Simular notificação** no painel.
4. **Antes de produção:** um ambiente de *preview* na Vercel com credenciais de teste e banco separado.

Cada pedido tem uma página própria (`/pedido/<token>`): pode fechar a aba, recarregar ou reiniciar o servidor que o pedido continua lá. A página inicial lista os últimos 5 pedidos deste navegador.

## 🔒 Segurança

- Validação de tipo de arquivo (apenas .json)
- Validação de estrutura JSON
- Nomes de arquivo seguros (usando `secure_filename`)
- Limpeza automática de arquivos temporários

## 🐛 Solução de Problemas

### Erro: "pip não é reconhecido" (Windows)
Use o Python launcher do Windows:
```bash
py -m pip install -r requirements.txt
```
E para executar o servidor:
```bash
py app.py
```

### Erro: "Module not found"
Certifique-se de instalar todas as dependências:
```bash
py -m pip install -r requirements.txt
```

### Erro: "Port already in use"
Mude a porta no arquivo `app.py`:
```python
app.run(debug=debug, host=host, port=5001)  # Use outra porta
```

### Erro ao gerar APKG
Verifique se o JSON está no formato correto e contém as chaves "pergunta" e "resposta" em todos os cards.

## 📱 Acesso na Rede Local

Para acessar de outros dispositivos na mesma rede:

1. Descubra o IP da máquina que está executando o servidor:
```bash
# Windows
ipconfig

# Linux/Mac
ifconfig
```

2. Acesse de outros dispositivos usando:
```
http://SEU_IP:5000
```

## 📄 Licença

Este projeto é de código aberto e está disponível para uso livre.

## 👨‍💻 Contribuições

Contribuições são bem-vindas! Sinta-se à vontade para:
- Reportar bugs
- Sugerir novas funcionalidades
- Enviar pull requests

## 📞 Suporte

Se encontrar problemas, verifique:
1. Se todas as dependências foram instaladas
2. Se o formato do JSON está correto
3. Se a porta 5000 está disponível
4. Os logs no terminal para mensagens de erro

---

Desenvolvido com ❤️ para facilitar a criação de flashcards no Anki

