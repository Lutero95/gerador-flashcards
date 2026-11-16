"""API do pedido: preço, prévia grátis, pagamento, geração em lotes e download (PLANO, seção 3.1)."""
import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
from datetime import timedelta
from io import BytesIO

from flask import Blueprint, current_app, jsonify, request, send_file, url_for
from sqlalchemy import select
from werkzeug.utils import secure_filename

from app.db import Session
from app.erros import resposta_erro_interno
from app.exportacao.anki import gerar_apkg
from app.exportacao.pdf import gerar_pdf_fontes
from app.ia.base import IAErroPermanente, IAErroTemporario, IAIndisponivel
from app.ia.geracao import (LOTE_TRAVADO, PreviaVazia, buscar_previa_em_cache, copiar_previa, gerar_previa,
                            numero_de_lotes, processar_lote, proximo_lote)
from app.ia.material import (MARGEM_MATERIAL, MaterialInvalido, limite_paginas, material_expira_antes,
                             processar_uploads)
from app.models import Pedido, StatusLote as L, StatusPedido as S, TipoEntrada, agora
from app.pagamentos.base import ErroPagamento
from app.pagamentos.servico import criar_pix, pix_vigente, provedor, resolver_falha, sincronizar
from app.pedidos import hash_texto, normalizar_texto, transicionar
from app.precos import FAIXAS, calcular_preco_centavos
from app.seguranca import (hash_privado, limitar, motivo_sem_previa, registrar_previa, verificar_turnstile,
                           visitante_id)

bp = Blueprint('api_pedidos', __name__)

# Uploads aceitos
EXTENSOES_DOCUMENTO = {'.pdf', '.docx', '.txt', '.md'}
EXTENSOES_IMAGEM = {'.png', '.jpg', '.jpeg', '.webp'}
MAX_ARQUIVOS_UPLOAD = 5

EMAIL_VALIDO = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

STATUS_TEXTO = {
    S.RASCUNHO: 'Em preparação',
    S.PREVIA_PRONTA: 'Prévia pronta',
    S.AGUARDANDO_PAGAMENTO: 'Aguardando pagamento',
    S.EXPIRADO: 'Código Pix expirado',
    S.PAGO: 'Pago! Preparando a geração',
    S.GERANDO: 'Gerando seu baralho',
    S.CONCLUIDO: 'Pronto para baixar',
    S.FALHOU: 'Não conseguimos gerar o baralho completo',
    S.REEMBOLSADO: 'Reembolsado',
}

AVISO_IA = ('Conteúdo gerado por IA. Confira fatos importantes (datas, artigos de lei, doses) antes de memorizar. '
            'Arquivos enviados são processados pela IA do Google e apagados após a geração.')


def ler_quantidade(valor):
    """Converte a quantidade recebida, aplicando padrão e o limite MAX_CARDS."""
    try:
        quantidade = int(valor)
        if quantidade < 1:
            quantidade = 10
    except (ValueError, TypeError):
        quantidade = 10
    return min(quantidade, current_app.config['MAX_CARDS'])


def nome_arquivo(nome_deck):
    return re.sub(r'[^a-zA-Z0-9_-]', '_', secure_filename(nome_deck or '')) or 'flashcards'


def buscar_pedido(token):
    return Session.scalar(select(Pedido).where(Pedido.token_acesso == token))


def iso_utc(momento):
    return momento.isoformat() + 'Z' if momento else None


def formatar_reais(centavos):
    return f'R$ {centavos // 100},{centavos % 100:02d}' if centavos is not None else None


def download_disponivel(pedido):
    return pedido.status == S.CONCLUIDO and (pedido.expira_em is None or agora() < pedido.expira_em)


def estado_pedido(pedido):
    """Tudo que a página do pedido precisa para se desenhar."""
    token = pedido.token_acesso
    pix = pix_vigente(pedido)
    ativo = pedido.pagamento_ativo
    modo_teste = provedor() is not None and provedor().nome == 'fake'
    lote = proximo_lote(pedido)

    status_texto = STATUS_TEXTO[pedido.status]
    if pedido.status == S.EXPIRADO and ativo is not None and ativo.status == 'rejected':
        status_texto = 'Pagamento recusado'
    if pedido.status == S.CONCLUIDO and not download_disponivel(pedido):
        status_texto = 'Prazo de download encerrado'

    resolucao = None
    if pedido.status == S.FALHOU and pedido.pagamentos:
        faltam = max(0, pedido.quantidade_solicitada - len(pedido.cards))
        parcial = round(pedido.preco_centavos * faltam / pedido.quantidade_solicitada)
        resolucao = {
            'parcial': {'cards': len(pedido.cards), 'reembolso_texto': formatar_reais(parcial)} if pedido.cards else None,
            'total': {'reembolso_texto': formatar_reais(pedido.preco_centavos)},
        }

    return {
        'token': token,
        'url_pedido': url_for('paginas.pedido', token=token),
        'status': pedido.status,
        'status_texto': status_texto,
        'nome_deck': pedido.nome_deck,
        'assunto': pedido.prompt,
        'quantidade_solicitada': pedido.quantidade_solicitada,
        'quantidade_gerada': len(pedido.cards),
        'preco_centavos': pedido.preco_centavos,
        'preco_texto': formatar_reais(pedido.preco_centavos),
        'email': pedido.email,
        'criado_em': iso_utc(pedido.criado_em),
        'subtopicos': pedido.plano_subtopicos or [],
        'previa': [{'pergunta': c.pergunta, 'resposta': c.resposta} for c in pedido.cards if c.lote == 0],
        'pode_gerar_pix': pix is None and pedido.status in (S.PREVIA_PRONTA, S.AGUARDANDO_PAGAMENTO, S.EXPIRADO),
        'pix': {
            'qr_code': pix.qr_code,
            'qr_code_base64': pix.qr_code_base64,
            'expira_em': iso_utc(pix.expira_em),
            'id_teste': pix.provider_payment_id if modo_teste else None,
        } if pix else None,
        'proximo_lote': lote.n if lote else None,
        'lote_atual': {
            'n': lote.n,
            'posicao': pedido.lotes.index(lote) + 1,
            'total': len(pedido.lotes),
            'subtopicos': [s['nome'] for s in lote.subtopicos],
        } if lote else None,
        'progresso': {
            'lotes_concluidos': sum(1 for item in pedido.lotes if item.status in (L.CONCLUIDO, L.FALHOU)),
            'lotes_total': len(pedido.lotes),
        },
        'resolucao': resolucao,
        'reembolso_texto': formatar_reais(pedido.reembolso_centavos) if pedido.reembolso_centavos else None,
        'downloads': {
            'apkg': url_for('api_pedidos.baixar_baralho', token=token),
            'pdf': url_for('api_pedidos.baixar_fontes', token=token),
        } if download_disponivel(pedido) else None,
        'disponivel_ate': iso_utc(pedido.expira_em) if pedido.status == S.CONCLUIDO else None,
        'aviso_ia': AVISO_IA,
        'modo_teste': modo_teste,
    }


MENSAGENS_SEM_PREVIA = {
    'cota': 'Você já usou as prévias grátis de hoje.',
    'orcamento': 'As prévias grátis de hoje se esgotaram.',
}


@bp.route('/api/previa/disponibilidade', methods=['GET'])
@limitar('LIMITE_CONSULTA_MIN')
def disponibilidade_previa():
    """Se este visitante ainda pode gerar prévia grátis hoje (senão, a compra direta continua disponível)."""
    motivo = motivo_sem_previa()
    return jsonify({'disponivel': motivo is None, 'motivo': motivo,
                    'mensagem': MENSAGENS_SEM_PREVIA.get(motivo) and
                    f'{MENSAGENS_SEM_PREVIA[motivo]} Você ainda pode gerar o baralho completo (sem prévia).'})


@bp.route('/api/preco', methods=['GET'])
@limitar('LIMITE_CONSULTA_MIN')
def consultar_preco():
    """Preço antes de gerar: faixa e valor para a quantidade escolhida."""
    quantidade = ler_quantidade(request.args.get('quantidade', 10))
    centavos = calcular_preco_centavos(quantidade)
    limite = next((ate for ate, _ in FAIXAS if quantidade <= ate), FAIXAS[-1][0])
    return jsonify({'quantidade': quantidade, 'preco_centavos': centavos, 'preco_texto': formatar_reais(centavos),
                    'faixa_ate': limite, 'max_cards': current_app.config['MAX_CARDS']})


@bp.route('/api/pedidos', methods=['POST'])
@limitar('LIMITE_CRIAR_PEDIDO_MIN')
def criar_pedido():
    """Cria o pedido com a prévia grátis (plano + primeiros cards) ou, com modo=direto, sem prévia."""
    try:
        dados = request.form if request.form or request.files else (request.get_json(silent=True) or {})
        prompt = str(dados.get('prompt', '')).strip()
        texto = str(dados.get('texto', '')).strip()
        direto = dados.get('modo') == 'direto'
        if not prompt:
            return jsonify({'erro': 'Descreva o assunto dos flashcards.'}), 400
        quantidade = ler_quantidade(dados.get('quantidade', 10))

        enviados = [arquivo for chave, arquivo in request.files.items(multi=True)
                    if chave.startswith(('arquivo_', 'imagem_')) and arquivo.filename]
        if len(enviados) > MAX_ARQUIVOS_UPLOAD:
            return jsonify({'erro': f'Envie no máximo {MAX_ARQUIVOS_UPLOAD} arquivos.'}), 400
        permitidas = EXTENSOES_DOCUMENTO | EXTENSOES_IMAGEM
        for arquivo in enviados:
            if os.path.splitext(arquivo.filename)[1].lower() not in permitidas:
                return jsonify({'erro': f'Tipo de arquivo não permitido: {arquivo.filename}. '
                                        f'Aceitos: {", ".join(sorted(permitidas))}.'}), 400

        if provedor() is None:
            return jsonify({'erro': 'Sistema de pagamento não configurado. Tente novamente mais tarde.'}), 503
        if not verificar_turnstile(dados.get('turnstile_token')):
            return jsonify({'erro': 'Não conseguimos confirmar que você não é um robô. Recarregue a página e '
                                    'tente de novo.'}), 403

        prompt_hash = hash_texto(normalizar_texto(prompt))
        origem = None
        if not direto:
            # Prévia em cache não custa nada: não conta na cota nem no orçamento
            origem = None if (enviados or texto) else buscar_previa_em_cache(prompt_hash, quantidade)
            motivo = None if origem else motivo_sem_previa()
            if motivo:
                return jsonify({'erro': f'{MENSAGENS_SEM_PREVIA[motivo]} Você ainda pode gerar o baralho '
                                        'completo, sem prévia.', 'motivo': motivo,
                                'compra_direta_disponivel': True}), 429

        pedido = Pedido(
            prompt=prompt,
            prompt_hash=prompt_hash,
            tipo_entrada=TipoEntrada.ARQUIVO if enviados else (TipoEntrada.TEXTO if texto else TipoEntrada.TEMA),
            quantidade_solicitada=quantidade,
            preco_centavos=calcular_preco_centavos(quantidade),  # preço da quantidade pedida, conhecido antes
            visitante_hash=hash_privado('visitante:' + visitante_id()),
        )
        Session.add(pedido)

        # Diretório exclusivo desta requisição, com nomes aleatórios: uploads simultâneos não colidem
        pasta = tempfile.mkdtemp(prefix='flashcards_upload_')
        try:
            arquivos = []
            for arquivo in enviados:
                caminho = os.path.join(pasta, uuid.uuid4().hex + os.path.splitext(arquivo.filename)[1].lower())
                arquivo.save(caminho)
                arquivos.append((secure_filename(arquivo.filename) or 'arquivo', caminho))
            material, referencias = processar_uploads(
                current_app.extensions['ia'], arquivos, max(1, numero_de_lotes(quantidade)),
                current_app.config['LIMITE_CARACTERES_MATERIAL'], pasta, max_paginas=limite_paginas(quantidade))
        except MaterialInvalido as erro:
            Session.rollback()
            return jsonify({'erro': str(erro)}), 400
        finally:
            shutil.rmtree(pasta, ignore_errors=True)

        if texto:
            material = f'### Texto colado\n{texto}\n\n{material}'.strip()
        pedido.material_texto = material[:current_app.config['LIMITE_CARACTERES_MATERIAL']] or None
        pedido.referencias_arquivos = referencias or None

        if direto:
            transicionar(pedido, S.PREVIA_PRONTA)  # sem prévia: o plano é montado depois do pagamento
            Session.commit()
            return jsonify(estado_pedido(pedido)), 201

        if origem is not None:
            copiar_previa(pedido, origem)
            transicionar(pedido, S.PREVIA_PRONTA)
            Session.commit()
            return jsonify(estado_pedido(pedido)), 201

        registrar_previa()
        Session.commit()
        try:
            gerar_previa(pedido)
        except (IAErroTemporario, IAErroPermanente, IAIndisponivel, PreviaVazia):
            # Sem rollback: as tentativas registradas em UsoIA são justamente o custo a acompanhar
            transicionar(pedido, S.FALHOU)
            Session.commit()
            return resposta_erro_interno('A IA não conseguiu gerar a prévia agora (pode estar sobrecarregada). '
                                         'Tente novamente em alguns minutos.', 503)

        transicionar(pedido, S.PREVIA_PRONTA)
        Session.commit()
        return jsonify(estado_pedido(pedido)), 201

    except Exception:
        Session.rollback()
        return resposta_erro_interno('Não foi possível gerar a prévia.')


@bp.route('/api/pedidos/<token>', methods=['GET'])
@limitar('LIMITE_CONSULTA_MIN')
def consultar_pedido(token):
    """Estado do pedido (usado no polling). Consulta o provedor se houver Pix pendente."""
    pedido = buscar_pedido(token)
    if pedido is None:
        return jsonify({'erro': 'Pedido não encontrado'}), 404
    try:
        sincronizar(pedido)
        return jsonify(estado_pedido(pedido))
    except Exception:
        return resposta_erro_interno('Não foi possível consultar o pedido.')


@bp.route('/api/pedidos/<token>/pagamento', methods=['POST'])
@limitar('LIMITE_ACOES_MIN')
def pagar_pedido(token):
    """Cria o Pix do pedido, ou devolve o que ainda está válido. Exige e-mail."""
    pedido = buscar_pedido(token)
    if pedido is None:
        return jsonify({'erro': 'Pedido não encontrado'}), 404
    if provedor() is None:
        return jsonify({'erro': 'Sistema de pagamento não configurado. Tente novamente mais tarde.'}), 503

    dados = request.get_json(silent=True) or {}
    email = str(dados.get('email', '')).strip()
    if len(email) > 320 or not EMAIL_VALIDO.match(email):
        return jsonify({'erro': 'Informe um e-mail válido para receber o link do seu baralho.'}), 400

    try:
        sincronizar(pedido)
        if pix_vigente(pedido) is not None:
            return jsonify(estado_pedido(pedido))

        if pedido.status == S.AGUARDANDO_PAGAMENTO:
            # Pix vencido que o provedor ainda não cancelou: encerra antes de criar outro
            pedido.pagamento_ativo.status = 'expired'
            transicionar(pedido, S.EXPIRADO)

        if pedido.status not in (S.PREVIA_PRONTA, S.EXPIRADO):
            return jsonify({'erro': 'Este pedido não aceita mais pagamento.', 'status': pedido.status}), 409

        if pedido.criado_em < agora() - timedelta(days=current_app.config['DIAS_PEDIDO_NAO_PAGO']):
            return jsonify({'erro': 'Esta prévia expirou. Gere uma nova para comprar o baralho.'}), 410

        if material_expira_antes(pedido.referencias_arquivos, MARGEM_MATERIAL):
            return jsonify({'erro': 'Os arquivos enviados para esta prévia já expiraram. '
                                    'Gere uma nova prévia para comprar o baralho.'}), 409

        pedido.email = email
        try:
            criar_pix(pedido)
        except ErroPagamento:
            Session.rollback()
            return jsonify({'erro': 'Não foi possível criar o pagamento Pix. Tente novamente em instantes.'}), 502
        Session.commit()
        return jsonify(estado_pedido(pedido))
    except Exception:
        return resposta_erro_interno('Não foi possível criar o pagamento.')


@bp.route('/api/pedidos/<token>/lotes/<int:n>', methods=['POST'])
@limitar('LIMITE_ACOES_MIN')
def gerar_lote(token, n):
    """Gera o lote n (só com o pedido pago). Idempotente: lote já gerado não é refeito."""
    pedido = buscar_pedido(token)
    if pedido is None:
        return jsonify({'erro': 'Pedido não encontrado'}), 404
    try:
        sincronizar(pedido)
        if pedido.status in (S.PREVIA_PRONTA, S.AGUARDANDO_PAGAMENTO, S.EXPIRADO, S.RASCUNHO):
            return jsonify({'erro': 'Pagamento ainda não confirmado.'}), 402

        lote = next((item for item in pedido.lotes if item.n == n), None)
        if lote is None:
            return jsonify({'erro': 'Lote não encontrado'}), 404
        if pedido.status not in (S.PAGO, S.GERANDO) or lote.status in (L.CONCLUIDO, L.FALHOU):
            return jsonify(estado_pedido(pedido))
        if lote.status == L.GERANDO and agora() - lote.iniciado_em < LOTE_TRAVADO:
            return jsonify({**estado_pedido(pedido), 'erro': 'Este lote já está sendo gerado.'}), 409

        gerou = processar_lote(pedido, lote)
        return jsonify(estado_pedido(pedido)), 200 if gerou else 502
    except Exception:
        Session.rollback()
        return resposta_erro_interno('Não foi possível gerar esta parte do baralho.')


@bp.route('/api/pedidos/<token>/resolucao', methods=['POST'])
@limitar('LIMITE_ACOES_MIN')
def resolver_pedido(token):
    """Geração falhou após o pagamento: o cliente escolhe reembolso total ou parcial com os cards gerados."""
    pedido = buscar_pedido(token)
    if pedido is None:
        return jsonify({'erro': 'Pedido não encontrado'}), 404
    opcao = str((request.get_json(silent=True) or {}).get('opcao', ''))
    if pedido.status != S.FALHOU or not pedido.pagamentos:
        return jsonify({'erro': 'Este pedido não tem pendências.'}), 409
    if opcao not in ('total', 'parcial') or (opcao == 'parcial' and not pedido.cards):
        return jsonify({'erro': 'Opção inválida.'}), 400
    try:
        if not resolver_falha(pedido, opcao):
            Session.rollback()
            return jsonify({'erro': 'O reembolso não foi aceito agora. Tente novamente em instantes.'}), 502
        Session.commit()
        return jsonify(estado_pedido(pedido))
    except Exception:
        Session.rollback()
        return resposta_erro_interno('Não foi possível concluir o reembolso.')


def _pedido_para_download(token):
    """Devolve (pedido, None) ou (None, resposta de erro). Nega por padrão."""
    pedido = buscar_pedido(token)
    if pedido is None:
        return None, (jsonify({'erro': 'Arquivo não encontrado'}), 404)
    sincronizar(pedido)
    if pedido.status != S.CONCLUIDO:
        return None, (jsonify({'erro': 'Pagamento não aprovado ou baralho ainda em geração.'}), 403)
    if not download_disponivel(pedido):
        return None, (jsonify({'erro': 'O prazo para baixar este baralho terminou.'}), 410)
    return pedido, None


@bp.route('/api/pedidos/<token>/baralho.apkg')
@limitar('LIMITE_ACOES_MIN')
def baixar_baralho(token):
    try:
        pedido, erro = _pedido_para_download(token)
        if erro:
            return erro
        conteudo = gerar_apkg(pedido.nome_deck, [(c.pergunta, c.resposta) for c in pedido.cards], semente=pedido.id)
        return send_file(BytesIO(conteudo), as_attachment=True,
                         download_name=f'{nome_arquivo(pedido.nome_deck)}.apkg', mimetype='application/apkg')
    except Exception:
        return resposta_erro_interno('Não foi possível gerar o arquivo.')


@bp.route('/api/pedidos/<token>/fontes.pdf')
@limitar('LIMITE_ACOES_MIN')
def baixar_fontes(token):
    try:
        pedido, erro = _pedido_para_download(token)
        if erro:
            return erro
        return send_file(BytesIO(gerar_pdf_fontes(pedido.fontes)), as_attachment=True,
                         download_name=f'{nome_arquivo(pedido.nome_deck)}_fontes.pdf', mimetype='application/pdf')
    except Exception:
        return resposta_erro_interno('Não foi possível gerar o arquivo.')


@bp.route('/upload', methods=['POST'])
@limitar('LIMITE_ACOES_MIN')
def upload_arquivo():
    """Converte um JSON de cards em APKG e devolve o arquivo diretamente (nada fica em disco)"""
    try:
        if 'arquivo' not in request.files:
            return jsonify({'erro': 'Nenhum arquivo enviado'}), 400

        arquivo = request.files['arquivo']

        if arquivo.filename == '':
            return jsonify({'erro': 'Nenhum arquivo selecionado'}), 400

        if not arquivo.filename.endswith('.json'):
            return jsonify({'erro': 'O arquivo deve ser um JSON'}), 400

        conteudo = arquivo.read()
        dados_json = json.loads(conteudo.decode('utf-8'))

        if isinstance(dados_json, dict):
            if 'cards' not in dados_json:
                return jsonify({'erro': 'JSON deve conter uma chave "cards" com a lista de flashcards'}), 400
            cards = dados_json['cards']
            nome_deck = dados_json.get('nome_deck', 'Flashcards')
        elif isinstance(dados_json, list):
            cards = dados_json
            nome_deck = 'Flashcards'
        else:
            return jsonify({'erro': 'Formato de JSON inválido'}), 400

        if not cards:
            return jsonify({'erro': 'Nenhum card encontrado no JSON'}), 400

        for i, card in enumerate(cards):
            if not isinstance(card, dict) or 'pergunta' not in card or 'resposta' not in card:
                return jsonify({'erro': f'Card {i+1} deve conter "pergunta" e "resposta"'}), 400

        apkg = gerar_apkg(nome_deck, [(c['pergunta'], c['resposta']) for c in cards],
                          semente=hashlib.sha256(conteudo).hexdigest())
        nome_base = os.path.splitext(secure_filename(arquivo.filename))[0] or 'flashcards'

        return send_file(BytesIO(apkg), as_attachment=True, download_name=f'{nome_base}.apkg',
                         mimetype='application/octet-stream')

    except (json.JSONDecodeError, UnicodeDecodeError):
        return jsonify({'erro': 'Erro ao ler JSON. Verifique se o formato está correto'}), 400
    except Exception:
        return resposta_erro_interno('Erro ao processar o arquivo.')
