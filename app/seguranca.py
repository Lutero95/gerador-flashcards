"""Anti-abuso e controle de custo (Fase 4 do plano).

- Rate limit por IP, com contadores no banco (funciona em serverless, sem Redis)
- Cloudflare Turnstile antes de gerar prévia
- Cota de prévias por visitante (cookie assinado) e por IP (só o hash, nunca o IP em claro — LGPD)
- Orçamento global diário de prévias em US$, somado a partir de UsoIA
- Cabeçalhos de segurança e CSP com nonce
"""
import functools
import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta

import httpx
from flask import current_app, g, jsonify, request, session
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.db import Session
from app.models import ContadorRequisicao, CotaPrevia, UsoIA, agora

logger = logging.getLogger('gerador_flashcards')

URL_TURNSTILE = 'https://challenges.cloudflare.com/turnstile/v0/siteverify'


# Identificação do cliente

def ip_cliente():
    """IP do cliente. Atrás da Vercel, o proxy sobrescreve x-real-ip / x-forwarded-for (não dá para forjar)."""
    if current_app.config['CONFIAR_PROXY']:
        encaminhado = request.headers.get('x-real-ip') or request.headers.get('x-forwarded-for', '').split(',')[0]
        if encaminhado.strip():
            return encaminhado.strip()
    return request.remote_addr or 'desconhecido'


def hash_privado(valor):
    """HMAC com a SECRET_KEY: identifica sem guardar o dado em claro e sem permitir reverter por força bruta."""
    return hmac.new(current_app.config['SECRET_KEY'].encode(), valor.encode(), hashlib.sha256).hexdigest()


def visitante_id():
    """Identificador aleatório do navegador, guardado no cookie de sessão assinado."""
    if 'visitante' not in session:
        session['visitante'] = secrets.token_urlsafe(16)
        session.permanent = True
    return session['visitante']


# Rate limit

class LimitadorBanco:
    """Janela fixa por minuto, contada no banco. Mesma interface serviria para Redis (ex.: Upstash)."""

    def consumir(self, chave, limite, janela_s=60):
        """Conta uma requisição. Devolve (permitido, segundos até a janela seguinte)."""
        agora_ = agora()
        inicio = datetime.fromtimestamp(int(agora_.timestamp()) // janela_s * janela_s)
        for _ in range(2):  # a segunda volta cobre a corrida de duas requisições criando a mesma linha
            atualizadas = Session.execute(
                update(ContadorRequisicao)
                .where(ContadorRequisicao.chave == chave, ContadorRequisicao.janela == inicio)
                .values(total=ContadorRequisicao.total + 1)
            ).rowcount
            if atualizadas:
                break
            try:
                Session.add(ContadorRequisicao(chave=chave, janela=inicio, total=1))
                Session.flush()
                break
            except IntegrityError:
                Session.rollback()
        total = Session.scalar(select(ContadorRequisicao.total).where(
            ContadorRequisicao.chave == chave, ContadorRequisicao.janela == inicio))
        Session.commit()
        restante = int((inicio + timedelta(seconds=janela_s) - agora_).total_seconds()) + 1
        return total <= limite, restante


def limitar(chave_config):
    """Decorator: limita a rota a N requisições por minuto por IP (N vem da configuração)."""
    def decorador(funcao):
        @functools.wraps(funcao)
        def envolvida(*args, **kwargs):
            limite = current_app.config[chave_config]
            chave = f'{funcao.__name__}:{hash_privado(ip_cliente())[:32]}'
            permitido, espera = current_app.extensions['limitador'].consumir(chave, limite)
            if not permitido:
                resposta = jsonify({'erro': 'Muitas requisições em pouco tempo. Aguarde um instante e tente de novo.'})
                resposta.headers['Retry-After'] = str(espera)
                return resposta, 429
            return funcao(*args, **kwargs)
        return envolvida
    return decorador


# Turnstile

def verificar_turnstile(token):
    """Valida o token do Turnstile no servidor. Sem segredo configurado (desenvolvimento), não exige."""
    segredo = current_app.config['TURNSTILE_SECRET']
    if not segredo:
        return True
    if not token:
        return False
    try:
        resposta = httpx.post(URL_TURNSTILE, timeout=5, data={
            'secret': segredo, 'response': token, 'remoteip': ip_cliente()})
        return bool(resposta.json().get('success'))
    except (httpx.HTTPError, ValueError):
        logger.warning('Turnstile indisponível; bloqueando a prévia por precaução')
        return False


# Cota de prévias e orçamento

def _chaves_de_cota():
    cfg = current_app.config
    return [(hash_privado('visitante:' + visitante_id()), cfg['PREVIAS_POR_DIA']),
            (hash_privado('ip:' + ip_cliente()), cfg['PREVIAS_POR_DIA_IP'])]


def _usadas_hoje(chave):
    return Session.scalar(select(CotaPrevia.quantidade).where(
        CotaPrevia.visitante_hash == chave, CotaPrevia.data == agora().date())) or 0


def estimar_custo_usd(modelo, tokens_entrada, tokens_saida):
    tabela = current_app.config['PRECOS_MODELOS_USD']
    if modelo in tabela:
        entrada, saida = tabela[modelo]
    else:  # modelo sem preço cadastrado: estima pelo mais caro, para o orçamento errar para o lado seguro
        entrada, saida = max(tabela.values(), key=lambda precos: precos[1])
    return (tokens_entrada * entrada + tokens_saida * saida) / 1_000_000


def gasto_previas_hoje():
    inicio = datetime.combine(agora().date(), datetime.min.time())
    return Session.scalar(select(func.coalesce(func.sum(UsoIA.custo_estimado_usd), 0.0)).where(
        UsoIA.etapa == 'previa', UsoIA.criado_em >= inicio)) or 0.0


def motivo_sem_previa():
    """None se este visitante pode gerar uma prévia agora; senão 'cota' ou 'orcamento'."""
    if gasto_previas_hoje() >= current_app.config['ORCAMENTO_PREVIAS_USD_DIA']:
        return 'orcamento'
    if any(_usadas_hoje(chave) >= limite for chave, limite in _chaves_de_cota()):
        return 'cota'
    return None


def registrar_previa():
    """Conta uma prévia (que chamou a IA) na cota do visitante e do IP. Devolve o hash do visitante."""
    hoje = agora().date()
    for chave, _ in _chaves_de_cota():
        atualizadas = Session.execute(
            update(CotaPrevia).where(CotaPrevia.visitante_hash == chave, CotaPrevia.data == hoje)
            .values(quantidade=CotaPrevia.quantidade + 1)).rowcount
        if not atualizadas:
            Session.add(CotaPrevia(visitante_hash=chave, data=hoje, quantidade=1))
    return _chaves_de_cota()[0][0]


# Cabeçalhos de segurança

def gerar_nonce():
    g.csp_nonce = secrets.token_urlsafe(16)


def cabecalhos_de_seguranca(resposta):
    resposta.headers['X-Content-Type-Options'] = 'nosniff'
    resposta.headers['X-Frame-Options'] = 'DENY'
    # O token do pedido vai na URL: sem Referer, ele não vaza para sites de terceiros
    resposta.headers['Referrer-Policy'] = 'no-referrer'
    if current_app.config['APP_ENV'] == 'production':
        resposta.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    if resposta.mimetype == 'text/html':
        nonce = getattr(g, 'csp_nonce', '')
        resposta.headers['Content-Security-Policy'] = '; '.join([
            "default-src 'self'",
            f"script-src 'self' 'nonce-{nonce}' https://challenges.cloudflare.com",
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
            'font-src https://fonts.gstatic.com',
            "img-src 'self' data:",
            "connect-src 'self'",
            'frame-src https://challenges.cloudflare.com',
            "frame-ancestors 'none'",
            "base-uri 'none'",
            "form-action 'self'",
            "object-src 'none'",
        ])
    return resposta


def init_app(app):
    app.extensions['limitador'] = LimitadorBanco()
    app.config.setdefault('SESSION_COOKIE_HTTPONLY', True)
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_SECURE'] = app.config['APP_ENV'] == 'production'
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=365)
    app.before_request(gerar_nonce)
    app.after_request(cabecalhos_de_seguranca)

    @app.context_processor
    def expor_nonce():
        return {'csp_nonce': getattr(g, 'csp_nonce', ''), 'turnstile_site_key': app.config['TURNSTILE_SITE_KEY']}
