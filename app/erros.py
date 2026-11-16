import logging
import uuid

from flask import jsonify

logger = logging.getLogger('gerador_flashcards')


def resposta_erro_interno(mensagem, status=500):
    """Loga a exceção atual com um erro_id e devolve ao cliente só uma mensagem amigável."""
    erro_id = uuid.uuid4().hex[:8]
    logger.exception('erro_id=%s', erro_id)
    return jsonify({
        'erro': f'{mensagem} Se o problema continuar, informe o código {erro_id} ao suporte.',
        'erro_id': erro_id
    }), status
