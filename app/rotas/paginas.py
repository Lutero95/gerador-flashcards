from flask import Blueprint, current_app, render_template
from sqlalchemy import select

from app.db import Session
from app.models import Pedido

bp = Blueprint('paginas', __name__)


@bp.route('/')
def index():
    """Renderiza a página principal"""
    return render_template('index.html', max_cards=current_app.config['MAX_CARDS'])


@bp.route('/termos')
def termos():
    return render_template('termos.html')


@bp.route('/privacidade')
def privacidade():
    return render_template('privacidade.html')


@bp.route('/pedido/<token>')
def pedido(token):
    """Página permanente do pedido: prévia, pagamento e downloads. O conteúdo vem de /api/pedidos/<token>."""
    existe = Session.scalar(select(Pedido.id).where(Pedido.token_acesso == token)) is not None
    return render_template('pedido.html', token=token, existe=existe), 200 if existe else 404
