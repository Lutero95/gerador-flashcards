"""Configuração lida do ambiente (.env), com padrões seguros e validação para produção."""
import json
import os

from dotenv import load_dotenv


class ConfiguracaoInvalida(RuntimeError):
    pass


def _int(nome, padrao):
    return int(os.environ.get(nome, padrao))


def _float(nome, padrao):
    return float(os.environ.get(nome, padrao))


def normalizar_database_url(url):
    """Aceita as URLs no formato do Neon/Supabase/Heroku (postgres://) e usa o driver psycopg 3."""
    if url.startswith('postgres://'):
        url = 'postgresql://' + url[len('postgres://'):]
    if url.startswith('postgresql://'):
        url = 'postgresql+psycopg://' + url[len('postgresql://'):]
    return url


def carregar_config():
    """Lê as variáveis de ambiente e devolve um dicionário para app.config."""
    load_dotenv()
    app_env = os.environ.get('APP_ENV', 'development')

    config = {
        'APP_ENV': app_env,
        'DATABASE_URL': normalizar_database_url(os.environ.get('DATABASE_URL', 'sqlite:///local.db')),
        'SECRET_KEY': os.environ.get('SECRET_KEY', ''),
        # Em desenvolvimento o padrão é o provedor fake (sem dinheiro); em produção, o Mercado Pago
        'PAYMENT_PROVIDER': os.environ.get('PAYMENT_PROVIDER',
                                           'fake' if app_env == 'development' else 'mercadopago'),
        'MERCADOPAGO_ACCESS_TOKEN': os.environ.get('MERCADOPAGO_ACCESS_TOKEN', ''),
        'MERCADOPAGO_WEBHOOK_SECRET': os.environ.get('MERCADOPAGO_WEBHOOK_SECRET', ''),
        # Endereço público do site (https://...), usado como notification_url do Pix
        'URL_PUBLICA': os.environ.get('URL_PUBLICA', ''),
        'GEMINI_API_KEY': os.environ.get('GEMINI_API_KEY', ''),
        # Modelos trocáveis sem deploy. O *_FALLBACK é usado quando o principal falha ou está sobrecarregado.
        'MODELO_PREVIA': os.environ.get('MODELO_PREVIA', 'gemini-flash-lite-latest'),
        'MODELO_PREVIA_FALLBACK': os.environ.get('MODELO_PREVIA_FALLBACK', 'gemini-flash-latest'),
        'MODELO_GERACAO': os.environ.get('MODELO_GERACAO', 'gemini-flash-latest'),
        'MODELO_GERACAO_FALLBACK': os.environ.get('MODELO_GERACAO_FALLBACK', 'gemini-flash-lite-latest'),
        # Orçamento de raciocínio (thinking), cobrado como saída. -1 = não enviar (padrão do modelo).
        'THINKING_PREVIA': _int('THINKING_PREVIA', 0),
        'THINKING_GERACAO': _int('THINKING_GERACAO', 512),
        'MAX_CARDS': _int('MAX_CARDS', 500),
        'TAMANHO_PREVIA': _int('TAMANHO_PREVIA', 5),
        'TAMANHO_LOTE': _int('TAMANHO_LOTE', 40),
        # Tempo máximo gasto com a IA numa requisição de lote (cabe no limite de 60 s da função serverless)
        'TEMPO_MAX_LOTE_S': _int('TEMPO_MAX_LOTE_S', 45),
        # Abaixo desta fração do pedido, a geração é considerada falha (oferece reembolso)
        'ENTREGA_MINIMA': _float('ENTREGA_MINIMA', 0.9),
        # Material enviado: texto guardado por pedido e amostra usada na prévia grátis
        'LIMITE_CARACTERES_MATERIAL': _int('LIMITE_CARACTERES_MATERIAL', 200_000),
        'LIMITE_CARACTERES_PREVIA': _int('LIMITE_CARACTERES_PREVIA', 30_000),
        # Prévias grátis: por visitante (cookie assinado) e por IP (hash), e teto global de custo por dia
        'PREVIAS_POR_DIA': _int('PREVIAS_POR_DIA', 3),
        'PREVIAS_POR_DIA_IP': _int('PREVIAS_POR_DIA_IP', 15),
        'ORCAMENTO_PREVIAS_USD_DIA': _float('ORCAMENTO_PREVIAS_USD_DIA', 0.50),
        # Mesma prévia (mesmo tema + quantidade, sem arquivos) reaproveitada por este tempo. 0 desliga.
        'CACHE_PREVIA_HORAS': _int('CACHE_PREVIA_HORAS', 24),
        # Pedido não pago fica disponível por este tempo
        'DIAS_PEDIDO_NAO_PAGO': _int('DIAS_PEDIDO_NAO_PAGO', 7),
        # Limites de requisições por IP, por minuto
        'LIMITE_CRIAR_PEDIDO_MIN': _int('LIMITE_CRIAR_PEDIDO_MIN', 10),
        'LIMITE_CONSULTA_MIN': _int('LIMITE_CONSULTA_MIN', 60),
        'LIMITE_ACOES_MIN': _int('LIMITE_ACOES_MIN', 30),
        # Preço dos modelos em US$ por 1 milhão de tokens [entrada, saída] (ANALISE_PRECOS_E_CUSTOS.md).
        # Confira os valores atuais na página oficial do Gemini; modelo desconhecido usa o mais caro da tabela.
        'PRECOS_MODELOS_USD': json.loads(os.environ.get('PRECOS_MODELOS_USD') or json.dumps({
            'gemini-flash-lite-latest': [0.30, 2.50],
            'gemini-flash-latest': [0.75, 3.75],
        })),
        # Atrás do proxy da Vercel, o IP do cliente vem no cabeçalho x-real-ip / x-forwarded-for
        'CONFIAR_PROXY': os.environ.get('CONFIAR_PROXY', '1' if app_env == 'production' else '0') == '1',
        # E-mail de contato exibido no rodapé, nos Termos e na Política de Privacidade
        'CONTATO_EMAIL': os.environ.get('CONTATO_EMAIL', ''),
        # Protege a rota de limpeza chamada pelo Cron da Vercel
        'CRON_SECRET': os.environ.get('CRON_SECRET', ''),
        'PIX_EXPIRACAO_MIN': _int('PIX_EXPIRACAO_MIN', 30),
        'DIAS_RETENCAO_PEDIDO': _int('DIAS_RETENCAO_PEDIDO', 30),
        'TURNSTILE_SITE_KEY': os.environ.get('TURNSTILE_SITE_KEY', ''),
        'TURNSTILE_SECRET': os.environ.get('TURNSTILE_SECRET', ''),
        'MAX_CONTENT_LENGTH': 16 * 1024 * 1024,
    }

    if app_env == 'production':
        validar_producao(config)
    elif not config['SECRET_KEY']:
        config['SECRET_KEY'] = 'dev-inseguro-nao-use-em-producao'

    return config


def validar_producao(config):
    """Em produção a aplicação se recusa a subir sem o mínimo necessário para cobrar com segurança."""
    faltando = []
    if not config['SECRET_KEY']:
        faltando.append('SECRET_KEY')
    if not os.environ.get('DATABASE_URL') or config['DATABASE_URL'].startswith('sqlite'):
        faltando.append('DATABASE_URL (Postgres)')
    if config['PAYMENT_PROVIDER'] == 'fake':
        faltando.append('PAYMENT_PROVIDER real (fake não é permitido em produção)')
    if config['PAYMENT_PROVIDER'] == 'mercadopago':
        if not config['MERCADOPAGO_ACCESS_TOKEN']:
            faltando.append('MERCADOPAGO_ACCESS_TOKEN')
        if not config['MERCADOPAGO_WEBHOOK_SECRET']:
            faltando.append('MERCADOPAGO_WEBHOOK_SECRET')
        if not config['URL_PUBLICA'].startswith('https://'):
            faltando.append('URL_PUBLICA (https://...)')
    if not config['GEMINI_API_KEY']:
        faltando.append('GEMINI_API_KEY')
    if not config['TURNSTILE_SITE_KEY'] or not config['TURNSTILE_SECRET']:
        faltando.append('TURNSTILE_SITE_KEY e TURNSTILE_SECRET')
    if faltando:
        raise ConfiguracaoInvalida('Configuração de produção incompleta: ' + ', '.join(faltando))
