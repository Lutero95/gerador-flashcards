"""Interface dos provedores de IA. Preparada para o roteador de modelos futuro (Parte 3 do plano)."""
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel


class IAIndisponivel(RuntimeError):
    """Provedor sem configuração (ex.: sem chave)."""


class IAErroTemporario(RuntimeError):
    """Sobrecarga, limite de taxa, timeout ou resposta malformada: vale tentar de novo ou outro modelo."""


class IAErroPermanente(RuntimeError):
    """Erro que não se resolve repetindo a mesma chamada (ex.: modelo inexistente, pedido inválido)."""


@dataclass
class Anexo:
    """Arquivo já enviado ao provedor (Files API), referenciado por URI."""
    uri: str
    mime_type: str


@dataclass
class ArquivoRemoto:
    nome: str  # identificador no provedor, usado para apagar
    uri: str
    mime_type: str
    expira_em: datetime | None  # UTC sem fuso


@dataclass
class RespostaIA:
    dados: dict
    modelo: str
    tokens_entrada: int
    tokens_saida: int  # inclui tokens de raciocínio (thinking), cobrados como saída
    latencia_ms: int


class LLMProvider(Protocol):
    nome: str

    def gerar_json(self, prompt: str, schema: type[BaseModel], modelo: str,
                   anexos: list[Anexo] | None = None, thinking_budget: int | None = None,
                   timeout_s: float | None = None) -> RespostaIA:
        """Gera uma resposta que obedece ao schema. Levanta IAErroTemporario ou IAErroPermanente."""
        ...

    def enviar_arquivo(self, caminho: str, mime_type: str) -> ArquivoRemoto: ...

    def apagar_arquivo(self, nome: str) -> None: ...
