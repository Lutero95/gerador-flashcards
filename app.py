"""Execução local: `python app.py`. Aplica as migrações pendentes e sobe o servidor."""
import os

from app import create_app
from app.db import migrar

aplicacao = create_app()

if __name__ == '__main__':
    migrar(aplicacao.config['DATABASE_URL'])
    # Debug só quando pedido explicitamente: o debugger do Werkzeug permite executar código remotamente
    debug = os.environ.get('FLASK_DEBUG') == '1'
    host = os.environ.get('FLASK_HOST', '127.0.0.1')
    print("=" * 50)
    print("Gerador de Flashcards")
    print("=" * 50)
    print(f"Servidor iniciado em http://localhost:5000 (debug {'ligado' if debug else 'desligado'})")
    print("Pressione Ctrl+C para encerrar")
    print("=" * 50)
    aplicacao.run(debug=debug, host=host, port=5000)
