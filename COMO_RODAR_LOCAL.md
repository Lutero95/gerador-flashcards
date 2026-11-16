# 🚀 Como Rodar Localmente

Guia passo a passo para testar o Gerador de Flashcards localmente.

## 📋 Pré-requisitos

- Python 3.10 ou superior instalado
- pip (gerenciador de pacotes Python)

## 🔧 Passo a Passo

### 1️⃣ Instalar Dependências

Abra o terminal na pasta do projeto e execute:

**Windows:**
```bash
py -m pip install -r requirements.txt
```

**Linux/Mac:**
```bash
pip install -r requirements.txt
```

> 💡 Se der erro de permissão, use: `pip install --user -r requirements.txt`

### 2️⃣ Configurar a Chave do Gemini

1. **Copie o arquivo de exemplo para `.env`:**
   
   **Windows:**
   ```bash
   copy .env.example .env
   ```
   
   **Linux/Mac:**
   ```bash
   cp .env.example .env
   ```

2. **Edite o arquivo `.env`** e coloque sua chave do Gemini:
   ```
   GEMINI_API_KEY=sua_chave_aqui
   ```
   
   > 🔑 Obtenha sua chave em: https://makersuite.google.com/app/apikey

### 3️⃣ Rodar o Servidor

> Na primeira execução é criado o banco local `local.db` (SQLite) e as migrações são aplicadas automaticamente. Para aplicá-las manualmente: `alembic upgrade head`.
>
> O servidor escuta só em `127.0.0.1` e com o modo debug desligado. Para ligar o debug durante o desenvolvimento, defina `FLASK_DEBUG=1` (no `.env` ou no terminal). Nunca ligue o debug com o servidor acessível na rede.

**Windows:**
```bash
py app.py
```

**Linux/Mac:**
```bash
python app.py
```

Você verá uma mensagem como:
```
==================================================
Gerador de Flashcards Anki
==================================================
Servidor iniciado em http://localhost:5000
Pressione Ctrl+C para encerrar
==================================================
```

### 4️⃣ Acessar no Navegador

Abra seu navegador e acesse:
```
http://localhost:5000
```

## ✅ Testar a Aplicação

1. **Digite um assunto** no campo de texto (ex: "Sistema circulatório humano")
2. **Defina a quantidade** de flashcards desejada (ex: 10)
3. **Clique em "Gerar Flashcards"**
4. **Aguarde** a geração (pode levar alguns segundos)
5. **Baixe** os arquivos APKG e PDF gerados

## 🛑 Parar o Servidor

Para parar o servidor, pressione:
```
Ctrl + C
```

## 🐛 Problemas Comuns

### Erro: "Module not found"
**Solução:** Instale as dependências novamente:
```bash
py -m pip install -r requirements.txt
```

### Erro: "GEMINI_API_KEY não configurada"
**Solução:** 
1. Verifique se o arquivo `.env` existe na raiz do projeto
2. Verifique se a chave está correta no arquivo `.env`
3. Reinicie o servidor após criar/editar o `.env`

### Erro: "Port 5000 already in use"
**Solução:** 
1. Feche outros programas usando a porta 5000, ou
2. Altere a porta no arquivo `app.py` (linha final):
   ```python
   app.run(debug=debug, host=host, port=5001)
   ```

### Erro: "pip não é reconhecido" (Windows)
**Solução:** Use o Python launcher:
```bash
py -m pip install -r requirements.txt
```

## 📝 Notas Importantes

- ⚠️ O arquivo `.env` contém sua chave secreta - **NUNCA** compartilhe ou envie para o GitHub
- ✅ O arquivo `.env` já está no `.gitignore` e não será enviado acidentalmente
- 🔄 Se você alterar o arquivo `.env`, reinicie o servidor para aplicar as mudanças

## 🎯 Próximos Passos

Após testar localmente, você pode:
- Fazer deploy no Vercel (veja `DEPLOY_VERCEL.md`)
- Personalizar a interface
- Adicionar novas funcionalidades

---

**Boa sorte com seus testes! 🚀**


