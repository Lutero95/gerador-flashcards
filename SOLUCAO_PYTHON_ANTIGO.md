# ⚠️ Problema: Python 3.6.8 é muito antigo

O `google-generativeai` requer Python 3.7 ou superior. Você está usando Python 3.6.8.

## 🔧 Solução: Atualizar o Python

### Opção 1: Instalar Python mais recente (Recomendado)

1. **Baixe o Python mais recente:**
   - Acesse: https://www.python.org/downloads/
   - Baixe Python 3.9, 3.10, 3.11 ou 3.12 (qualquer um funciona)

2. **Durante a instalação:**
   - ✅ **IMPORTANTE**: Marque a opção **"Add Python to PATH"**
   - Clique em "Install Now"

3. **Após instalar, verifique:**
   ```bash
   py --version
   ```
   Deve mostrar Python 3.9 ou superior

4. **Reinstale as dependências:**
   ```bash
   py -m pip install -r requirements.txt
   ```

5. **Teste novamente:**
   ```bash
   py app.py
   ```

### Opção 2: Usar Python específico (se tiver múltiplas versões)

Se você já tem Python 3.7+ instalado em outro lugar:

1. **Encontre o caminho do Python mais recente:**
   ```bash
   py -0  # Lista todas as versões Python instaladas
   ```

2. **Use o Python específico:**
   ```bash
   py -3.9 -m pip install -r requirements.txt
   py -3.9 app.py
   ```

### Opção 3: Usar ambiente virtual (Recomendado para projetos)

1. **Crie um ambiente virtual:**
   ```bash
   py -m venv venv
   ```

2. **Ative o ambiente virtual:**
   ```bash
   venv\Scripts\activate
   ```

3. **Instale as dependências:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Execute:**
   ```bash
   python app.py
   ```

## ✅ Verificar se funcionou

Após atualizar, teste:
```bash
py -c "import google.generativeai; print('OK!')"
```

Se mostrar "OK!", está funcionando! 🎉

## 📝 Nota

Se continuar usando Python 3.6.8, você não conseguirá usar a geração automática de flashcards com Gemini, mas ainda pode usar o conversor de JSON para APKG.


