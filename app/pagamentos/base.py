"""Interface comum dos provedores de pagamento (Mercado Pago real e o fake de testes)."""
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


class ErroPagamento(RuntimeError):
    pass


@dataclass
class ResultadoPix:
    provider_payment_id: str
    status: str
    qr_code: str
    qr_code_base64: str
    ticket_url: str
    expira_em: datetime | None  # UTC sem fuso


@dataclass
class StatusPagamento:
    """Situação do pagamento segundo o provedor: approved, pending, rejected, cancelled, expired, refunded."""
    status: str
    valor_centavos: int | None = None
    external_reference: str | None = None


@dataclass
class EventoValidado:
    """Notificação autêntica. provider_payment_id é None quando o tópico não é de pagamento."""
    evento_id: str
    provider_payment_id: str | None


class PaymentProvider(Protocol):
    nome: str

    def criar_pix(self, pedido, idempotency_key: str) -> ResultadoPix: ...

    def consultar(self, provider_payment_id: str) -> StatusPagamento | None: ...

    def reembolsar(self, provider_payment_id: str, valor_centavos: int | None = None) -> bool:
        """Reembolso total (valor None) ou parcial."""
        ...

    def validar_webhook(self, headers, query_args, body: bytes) -> EventoValidado | None: ...
