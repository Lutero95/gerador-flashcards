"""Modelos do banco. Valores monetários sempre em centavos (int); datas em UTC sem fuso."""
import secrets
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def agora():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def novo_uuid():
    return str(uuid.uuid4())


def novo_token():
    return secrets.token_urlsafe(32)


class StatusPedido:
    RASCUNHO = 'rascunho'
    PREVIA_PRONTA = 'previa_pronta'
    AGUARDANDO_PAGAMENTO = 'aguardando_pagamento'
    PAGO = 'pago'
    GERANDO = 'gerando'
    CONCLUIDO = 'concluido'
    FALHOU = 'falhou'
    REEMBOLSADO = 'reembolsado'
    EXPIRADO = 'expirado'


class TipoEntrada:
    TEMA = 'tema'
    ARQUIVO = 'arquivo'
    TEXTO = 'texto'


class Pedido(Base):
    __tablename__ = 'pedidos'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_uuid)
    # Vai na URL do pedido: é o que dá acesso a ele, por isso é longo e aleatório
    token_acesso: Mapped[str] = mapped_column(String(64), unique=True, index=True, default=novo_token)
    email: Mapped[str | None] = mapped_column(String(320))
    prompt: Mapped[str] = mapped_column(Text)
    prompt_hash: Mapped[str] = mapped_column(String(64), index=True)
    tipo_entrada: Mapped[str] = mapped_column(String(20), default=TipoEntrada.TEMA)
    referencias_arquivos: Mapped[list | None] = mapped_column(JSON)
    quantidade_solicitada: Mapped[int] = mapped_column(Integer)
    preco_centavos: Mapped[int | None] = mapped_column(Integer)
    nome_deck: Mapped[str | None] = mapped_column(String(200))
    plano_subtopicos: Mapped[list | None] = mapped_column(JSON)
    fontes: Mapped[list | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default=StatusPedido.RASCUNHO, index=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    pago_em: Mapped[datetime | None] = mapped_column(DateTime)
    concluido_em: Mapped[datetime | None] = mapped_column(DateTime)
    expira_em: Mapped[datetime | None] = mapped_column(DateTime)
    visitante_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    # Texto extraído do material enviado (PDF com texto, DOCX, TXT, texto colado), fatiado entre os lotes
    material_texto: Mapped[str | None] = mapped_column(Text)
    # Valor devolvido ao cliente (reembolso total ou proporcional)
    reembolso_centavos: Mapped[int | None] = mapped_column(Integer)

    cards: Mapped[list['Card']] = relationship(
        back_populates='pedido', order_by='Card.ordem', cascade='all, delete-orphan')
    pagamentos: Mapped[list['Pagamento']] = relationship(
        back_populates='pedido', order_by='Pagamento.criado_em', cascade='all, delete-orphan')
    lotes: Mapped[list['LoteGeracao']] = relationship(
        back_populates='pedido', order_by='LoteGeracao.n', cascade='all, delete-orphan')

    @property
    def pagamento_ativo(self):
        """O Pix mais recente. Um pedido pode ter vários (QR renovado), mas só um vale."""
        return self.pagamentos[-1] if self.pagamentos else None


class Pagamento(Base):
    __tablename__ = 'pagamentos'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_uuid)
    pedido_id: Mapped[str] = mapped_column(ForeignKey('pedidos.id'), index=True)
    provider: Mapped[str] = mapped_column(String(30))
    # Sempre string: o Mercado Pago devolve int na criação e string no webhook
    provider_payment_id: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(30), default='pending')
    valor_centavos: Mapped[int] = mapped_column(Integer)
    qr_code: Mapped[str | None] = mapped_column(Text)
    qr_code_base64: Mapped[str | None] = mapped_column(Text)
    ticket_url: Mapped[str | None] = mapped_column(Text)
    expira_em: Mapped[datetime | None] = mapped_column(DateTime)
    idempotency_key: Mapped[str] = mapped_column(String(80), unique=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, default=agora, onupdate=agora)

    pedido: Mapped[Pedido] = relationship(back_populates='pagamentos')


class Card(Base):
    __tablename__ = 'cards'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pedido_id: Mapped[str] = mapped_column(ForeignKey('pedidos.id'), index=True)
    ordem: Mapped[int] = mapped_column(Integer)
    pergunta: Mapped[str] = mapped_column(Text)
    resposta: Mapped[str] = mapped_column(Text)
    lote: Mapped[int] = mapped_column(Integer, default=0)  # 0 = prévia
    hash_normalizado: Mapped[str] = mapped_column(String(64), index=True)

    pedido: Mapped[Pedido] = relationship(back_populates='cards')


class StatusLote:
    PENDENTE = 'pendente'
    GERANDO = 'gerando'
    CONCLUIDO = 'concluido'
    FALHOU = 'falhou'


class LoteGeracao(Base):
    """Uma parte da geração paga: o front pede os lotes em sequência e acompanha o progresso."""
    __tablename__ = 'lotes_geracao'
    __table_args__ = (UniqueConstraint('pedido_id', 'n'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pedido_id: Mapped[str] = mapped_column(ForeignKey('pedidos.id'), index=True)
    n: Mapped[int] = mapped_column(Integer)  # 1, 2, 3...
    quantidade: Mapped[int] = mapped_column(Integer)
    subtopicos: Mapped[list] = mapped_column(JSON)  # [{"nome": ..., "quantidade": ...}]
    # 0 = lote planejado na prévia; 1, 2 = rodadas de complemento para cobrir cards faltantes
    rodada: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default=StatusLote.PENDENTE)
    tentativas: Mapped[int] = mapped_column(Integer, default=0)
    iniciado_em: Mapped[datetime | None] = mapped_column(DateTime)
    concluido_em: Mapped[datetime | None] = mapped_column(DateTime)

    pedido: Mapped[Pedido] = relationship(back_populates='lotes')


class EventoWebhook(Base):
    """Eventos já processados, para ignorar notificações duplicadas."""
    __tablename__ = 'eventos_webhook'
    __table_args__ = (UniqueConstraint('provider', 'evento_id'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(30))
    evento_id: Mapped[str] = mapped_column(String(128))
    recebido_em: Mapped[datetime] = mapped_column(DateTime, default=agora)


class UsoIA(Base):
    __tablename__ = 'uso_ia'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pedido_id: Mapped[str | None] = mapped_column(ForeignKey('pedidos.id'), index=True)
    etapa: Mapped[str] = mapped_column(String(30))  # plano / previa / lote_n / geracao
    modelo: Mapped[str] = mapped_column(String(80))
    tokens_entrada: Mapped[int] = mapped_column(Integer, default=0)
    tokens_saida: Mapped[int] = mapped_column(Integer, default=0)
    custo_estimado_usd: Mapped[float | None] = mapped_column(Float)
    latencia_ms: Mapped[int] = mapped_column(Integer, default=0)
    sucesso: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora, index=True)


class PagamentoFake(Base):
    """Lado "do provedor" do FakePaymentProvider: o que a API do banco diria sobre o Pix de teste."""
    __tablename__ = 'pagamentos_fake'

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(30), default='pending')
    valor_centavos: Mapped[int] = mapped_column(Integer)
    external_reference: Mapped[str] = mapped_column(String(36))
    idempotency_key: Mapped[str] = mapped_column(String(80), unique=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)


class ContadorRequisicao(Base):
    """Contador de requisições por chave (ex.: IP + rota) numa janela de tempo: rate limit sem Redis."""
    __tablename__ = 'contadores_requisicao'
    __table_args__ = (UniqueConstraint('chave', 'janela'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chave: Mapped[str] = mapped_column(String(128))
    janela: Mapped[datetime] = mapped_column(DateTime, index=True)
    total: Mapped[int] = mapped_column(Integer, default=0)


class CotaPrevia(Base):
    __tablename__ = 'cotas_previa'
    __table_args__ = (UniqueConstraint('visitante_hash', 'data'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    visitante_hash: Mapped[str] = mapped_column(String(64))
    data: Mapped[date] = mapped_column(Date)
    quantidade: Mapped[int] = mapped_column(Integer, default=0)
