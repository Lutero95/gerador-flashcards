import os
import json
import genanki
import random
from flask import Flask, request, send_file, render_template, jsonify
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['OUTPUT_FOLDER'] = 'output'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

# Criar pastas se não existirem
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)


def criar_deck_anki(dados_json, nome_deck="Flashcards"):
    """
    Cria um deck Anki a partir de dados JSON.
    
    Formato esperado do JSON:
    {
        "nome_deck": "Nome do Baralho" (opcional),
        "cards": [
            {
                "pergunta": "Qual é a pergunta?",
                "resposta": "Esta é a resposta"
            },
            ...
        ]
    }
    """
    # Gerar IDs únicos para o modelo e deck
    modelo_id = random.randrange(1 << 30, 1 << 31)
    deck_id = random.randrange(1 << 30, 1 << 31)
    
    # Obter nome do deck do JSON, se fornecido
    if isinstance(dados_json, dict) and 'nome_deck' in dados_json:
        nome_deck = dados_json['nome_deck']
        cards_data = dados_json.get('cards', [])
    else:
        # Se o JSON for uma lista direta de cards
        cards_data = dados_json if isinstance(dados_json, list) else []
    
    # Criar modelo de nota
    modelo = genanki.Model(
        modelo_id,
        'Modelo Simples',
        fields=[
            {'name': 'Pergunta'},
            {'name': 'Resposta'},
        ],
        templates=[
            {
                'name': 'Card 1',
                'qfmt': '<div style="font-family: arial; font-size: 20px; text-align: center; color: black; background-color: white;">{{Pergunta}}</div>',
                'afmt': '{{FrontSide}}<hr id="answer"><div style="font-family: arial; font-size: 20px; text-align: center; color: navy; background-color: white;">{{Resposta}}</div>',
            },
        ],
        css='''
            .card {
                font-family: arial;
                font-size: 20px;
                text-align: center;
                color: black;
                background-color: white;
            }
        '''
    )
    
    # Criar deck
    deck = genanki.Deck(deck_id, nome_deck)
    
    # Adicionar notas ao deck
    for card_data in cards_data:
        pergunta = card_data.get('pergunta', '')
        resposta = card_data.get('resposta', '')
        
        nota = genanki.Note(
            model=modelo,
            fields=[pergunta, resposta]
        )
        deck.add_note(nota)
    
    return deck


@app.route('/')
def index():
    """Renderiza a página principal"""
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_arquivo():
    """Processa o upload do arquivo JSON e gera o APKG"""
    try:
        # Verificar se o arquivo foi enviado
        if 'arquivo' not in request.files:
            return jsonify({'erro': 'Nenhum arquivo enviado'}), 400
        
        arquivo = request.files['arquivo']
        
        # Verificar se um arquivo foi selecionado
        if arquivo.filename == '':
            return jsonify({'erro': 'Nenhum arquivo selecionado'}), 400
        
        # Verificar se é um arquivo JSON
        if not arquivo.filename.endswith('.json'):
            return jsonify({'erro': 'O arquivo deve ser um JSON'}), 400
        
        # Salvar arquivo temporariamente
        filename = secure_filename(arquivo.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        arquivo.save(filepath)
        
        # Ler e processar o JSON
        with open(filepath, 'r', encoding='utf-8') as f:
            dados_json = json.load(f)
        
        # Validar estrutura do JSON
        if isinstance(dados_json, dict):
            if 'cards' not in dados_json:
                return jsonify({'erro': 'JSON deve conter uma chave "cards" com a lista de flashcards'}), 400
            cards = dados_json['cards']
        elif isinstance(dados_json, list):
            cards = dados_json
        else:
            return jsonify({'erro': 'Formato de JSON inválido'}), 400
        
        if not cards:
            return jsonify({'erro': 'Nenhum card encontrado no JSON'}), 400
        
        # Validar que os cards têm pergunta e resposta
        for i, card in enumerate(cards):
            if 'pergunta' not in card or 'resposta' not in card:
                return jsonify({'erro': f'Card {i+1} deve conter "pergunta" e "resposta"'}), 400
        
        # Criar deck Anki
        deck = criar_deck_anki(dados_json)
        
        # Gerar nome do arquivo de saída
        nome_base = os.path.splitext(filename)[0]
        output_filename = f'{nome_base}.apkg'
        output_filepath = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)
        
        # Gerar arquivo APKG
        genanki.Package(deck).write_to_file(output_filepath)
        
        # Limpar arquivo temporário
        os.remove(filepath)
        
        return jsonify({
            'sucesso': True,
            'mensagem': f'Deck criado com sucesso! {len(cards)} cards adicionados.',
            'arquivo': output_filename
        })
    
    except json.JSONDecodeError:
        return jsonify({'erro': 'Erro ao ler JSON. Verifique se o formato está correto'}), 400
    except Exception as e:
        return jsonify({'erro': f'Erro ao processar arquivo: {str(e)}'}), 500


@app.route('/download/<filename>')
def download_arquivo(filename):
    """Disponibiliza o download do arquivo APKG gerado"""
    try:
        filepath = os.path.join(app.config['OUTPUT_FOLDER'], secure_filename(filename))
        
        if not os.path.exists(filepath):
            return jsonify({'erro': 'Arquivo não encontrado'}), 404
        
        return send_file(
            filepath,
            as_attachment=True,
            download_name=filename,
            mimetype='application/apkg'
        )
    except Exception as e:
        return jsonify({'erro': f'Erro ao baixar arquivo: {str(e)}'}), 500


if __name__ == '__main__':
    print("=" * 50)
    print("Gerador de Flashcards Anki")
    print("=" * 50)
    print("Servidor iniciado em http://localhost:5000")
    print("Pressione Ctrl+C para encerrar")
    print("=" * 50)
    app.run(debug=True, host='0.0.0.0', port=5000)

