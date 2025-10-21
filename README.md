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
│
├── api/                   # Serverless functions (Vercel)
│   └── index.py          # API principal (Flask adaptado)
│
├── templates/            # Templates HTML
│   └── index.html       # Interface web
│
├── app.py                # Servidor Flask local
├── requirements.txt      # Dependências do projeto
├── vercel.json          # Configuração do Vercel
├── .vercelignore        # Arquivos ignorados no deploy
│
├── README.md            # Documentação principal
├── DEPLOY_VERCEL.md     # Guia de deploy no Vercel
├── COMO_USAR.txt        # Guia rápido de uso
└── exemplo.json         # Arquivo de exemplo para testes
```

## 🛠️ Tecnologias Utilizadas

- **Flask**: Framework web Python
- **genanki**: Biblioteca para gerar arquivos Anki
- **HTML/CSS/JavaScript**: Interface web moderna

## ⚙️ Configuração

O servidor está configurado para:
- Porta: 5000
- Host: 0.0.0.0 (acessível na rede local)
- Tamanho máximo de arquivo: 16MB
- Modo debug: Ativado (desative em produção)

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
app.run(debug=True, host='0.0.0.0', port=5001)  # Use outra porta
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

