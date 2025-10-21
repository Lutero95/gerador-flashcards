# 🚀 Deploy no Vercel - Gerador de Flashcards Anki

## 📌 Pré-requisitos

1. Conta no GitHub (gratuita)
2. Conta no Vercel (gratuita) - https://vercel.com
3. Git instalado no seu computador

---

## 🔧 Passo a Passo

### 1️⃣ Criar Repositório no GitHub

1. Acesse https://github.com e faça login
2. Clique em **"New repository"** (Novo repositório)
3. Dê um nome (ex: `gerador-flashcards-anki`)
4. Deixe como **Public** ou **Private** (ambos funcionam)
5. Clique em **"Create repository"**

### 2️⃣ Subir o Código para o GitHub

Abra o terminal na pasta do projeto e execute:

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/SEU_REPOSITORIO.git
git push -u origin main
```

> ⚠️ **Importante**: Substitua `SEU_USUARIO` e `SEU_REPOSITORIO` pelos seus dados!

### 3️⃣ Conectar ao Vercel

1. Acesse https://vercel.com e faça login
2. Clique em **"Add New"** → **"Project"**
3. Clique em **"Import Git Repository"**
4. Selecione o repositório que você criou
5. Clique em **"Import"**

### 4️⃣ Configurar o Deploy

Na tela de configuração:

1. **Framework Preset**: Selecione **"Other"**
2. **Root Directory**: Deixe como está (`.`)
3. **Build Command**: Deixe vazio ou use `echo "No build required"`
4. **Output Directory**: Deixe vazio
5. **Install Command**: `pip install -r requirements.txt` (já detectado automaticamente)

6. Clique em **"Deploy"** 🚀

### 5️⃣ Aguardar o Deploy

O Vercel irá:
- ✅ Instalar as dependências Python
- ✅ Configurar as serverless functions
- ✅ Fazer o deploy da aplicação
- ✅ Gerar uma URL pública (ex: `seu-projeto.vercel.app`)

⏱️ Tempo estimado: 1-2 minutos

---

## 🌐 Acessar sua Aplicação

Após o deploy, você receberá uma URL como:
```
https://seu-projeto.vercel.app
```

**Pronto!** Sua aplicação está no ar! 🎉

---

## 🔄 Atualizar a Aplicação

Sempre que você fizer alterações no código:

```bash
git add .
git commit -m "Descrição das mudanças"
git push
```

O Vercel detecta automaticamente e faz o **redeploy automaticamente**! ✨

---

## ⚙️ Configurações Avançadas (Opcional)

### Domínio Personalizado

1. No painel do Vercel, vá em **"Settings"** → **"Domains"**
2. Adicione seu domínio personalizado
3. Configure o DNS conforme as instruções

### Variáveis de Ambiente

Se precisar adicionar variáveis de ambiente:

1. Vá em **"Settings"** → **"Environment Variables"**
2. Adicione as variáveis necessárias
3. Faça redeploy

---

## 📊 Monitoramento

O Vercel oferece gratuitamente:
- 📈 Analytics de uso
- 🐛 Logs de erros
- ⚡ Métricas de performance
- 📊 Estatísticas de requisições

Acesse tudo no painel do projeto no Vercel!

---

## 🆓 Limites do Plano Gratuito

O plano gratuito do Vercel inclui:
- ✅ Bandwidth: 100GB/mês
- ✅ Serverless Functions: 100GB-Hrs
- ✅ Builds: 6,000 minutos/mês
- ✅ Projetos ilimitados
- ✅ Deploy automático

**Mais que suficiente para uso pessoal e pequenos projetos!** 🎯

---

## 🔧 Solução de Problemas

### Erro: "Build Failed"
- Verifique se o `requirements.txt` está correto
- Verifique os logs de build no Vercel
- Certifique-se de que todas as dependências são compatíveis

### Erro: "Function Timeout"
- O timeout padrão é 10 segundos (plano gratuito)
- Para arquivos JSON muito grandes, considere otimizar
- O plano Pro tem timeout de 60 segundos

### Erro: "Module not found"
- Verifique se a dependência está no `requirements.txt`
- Faça um novo deploy forçado

---

## 📞 Suporte

- Documentação Vercel: https://vercel.com/docs
- Documentação Python no Vercel: https://vercel.com/docs/functions/runtimes/python
- GitHub Issues: Crie issues no seu repositório

---

## 🎯 Dicas de Otimização

1. **Cache**: O Vercel faz cache automático dos assets
2. **CDN Global**: Seu site é servido de múltiplos data centers
3. **HTTPS**: SSL/TLS automático e gratuito
4. **Compressão**: Gzip/Brotli automático

---

## ✅ Checklist Final

Antes de compartilhar sua aplicação:

- [ ] Testou o upload de arquivos JSON
- [ ] Testou o download do APKG gerado
- [ ] Verificou se funciona em diferentes navegadores
- [ ] Testou em dispositivos móveis
- [ ] Compartilhou a URL com outras pessoas

---

## 🎉 Parabéns!

Sua aplicação de Gerador de Flashcards Anki está no ar e acessível para qualquer pessoa no mundo! 🌍

Compartilhe a URL e ajude outras pessoas a criar seus flashcards! 📚✨

---

## 📝 Notas Importantes

1. **Arquivos temporários**: No Vercel, arquivos são processados em memória e não salvos permanentemente
2. **Serverless**: Cada requisição é independente - perfeito para essa aplicação
3. **Escalabilidade**: O Vercel escala automaticamente conforme o uso
4. **Zero configuração**: Tudo funciona out-of-the-box!

---

**Desenvolvido com ❤️ para a comunidade Anki**

