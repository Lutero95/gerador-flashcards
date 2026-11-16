"""Provedor Gemini com o SDK google-genai e saída estruturada (sem extrair JSON por regex)."""
import logging
import time
from datetime import timezone

import httpx
from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from app.ia.base import ArquivoRemoto, IAErroPermanente, IAErroTemporario, IAIndisponivel, RespostaIA

logger = logging.getLogger('gerador_flashcards')

# As retentativas e a troca de modelo são feitas por nós (app/ia/geracao.py), dentro do prazo do lote;
# por isso o SDK não repete chamadas sozinho.
TIMEOUT_MS = 40_000


class GeminiProvider:
    nome = 'gemini'

    def __init__(self, api_key):
        self._api_key = api_key
        self._client = None  # criado no primeiro uso: montar o cliente HTTP custa ~1,5 s no cold start
        self._sem_thinking = set()  # modelos que recusaram o orçamento de raciocínio pedido

    def _cliente(self):
        if self._client is None:
            if not self._api_key:
                raise IAIndisponivel('GEMINI_API_KEY não configurada')
            self._client = genai.Client(
                api_key=self._api_key,
                http_options=types.HttpOptions(timeout=TIMEOUT_MS, retry_options=types.HttpRetryOptions(attempts=1)),
            )
        return self._client

    def gerar_json(self, prompt, schema, modelo, anexos=None, thinking_budget=None, timeout_s=None):
        conteudo = [prompt] + [types.Part.from_uri(file_uri=a.uri, mime_type=a.mime_type) for a in anexos or []]
        if modelo in self._sem_thinking:
            thinking_budget = None
        try:
            try:
                resposta, latencia_ms = self._chamar(modelo, conteudo, schema, thinking_budget, timeout_s)
            except errors.ClientError as erro:
                if thinking_budget is None or erro.code != 400:
                    raise
                # Alguns modelos recusam certos orçamentos (ex.: o flash-lite 3.5 não aceita 0) com um 400
                # genérico: repete sem a configuração e lembra do modelo para não pagar a recusa de novo
                logger.warning('Modelo %s recusou thinking_budget=%s; usando o padrão do modelo', modelo, thinking_budget)
                resposta, latencia_ms = self._chamar(modelo, conteudo, schema, None, timeout_s)
                self._sem_thinking.add(modelo)
        except errors.ClientError as erro:
            raise IAErroPermanente(f'{modelo}: {erro.code} {erro.status}') from erro
        return self._interpretar(resposta, schema, modelo, latencia_ms)

    def _chamar(self, modelo, conteudo, schema, thinking_budget, timeout_s=None):
        config = {'response_mime_type': 'application/json', 'response_schema': schema}
        if timeout_s is not None:
            config['http_options'] = types.HttpOptions(timeout=int(min(timeout_s * 1000, TIMEOUT_MS)))
        if thinking_budget is not None:
            config['thinking_config'] = types.ThinkingConfig(thinking_budget=thinking_budget)
        inicio = time.monotonic()
        try:
            resposta = self._cliente().models.generate_content(
                model=modelo, contents=conteudo, config=types.GenerateContentConfig(**config))
        except errors.ServerError as erro:
            raise IAErroTemporario(f'{modelo}: {erro.code} {erro.status}') from erro
        except errors.ClientError as erro:
            if erro.code == 429:
                raise IAErroTemporario(f'{modelo}: limite de taxa') from erro
            if erro.code == 400:
                raise  # tratado em gerar_json (thinking) ou convertido abaixo
            raise IAErroPermanente(f'{modelo}: {erro.code} {erro.status}') from erro
        except (httpx.TimeoutException, httpx.TransportError) as erro:
            raise IAErroTemporario(f'{modelo}: {type(erro).__name__}') from erro
        return resposta, int((time.monotonic() - inicio) * 1000)

    def _interpretar(self, resposta, schema, modelo, latencia_ms):
        try:
            objeto = resposta.parsed if resposta.parsed is not None else schema.model_validate_json(resposta.text or '')
        except (ValidationError, ValueError) as erro:
            raise IAErroTemporario(f'{modelo}: resposta fora do formato') from erro

        uso = resposta.usage_metadata
        return RespostaIA(
            dados=objeto.model_dump(),
            modelo=modelo,
            tokens_entrada=(uso.prompt_token_count or 0) if uso else 0,
            tokens_saida=((uso.candidates_token_count or 0) + (uso.thoughts_token_count or 0)) if uso else 0,
            latencia_ms=latencia_ms,
        )

    def enviar_arquivo(self, caminho, mime_type):
        try:
            arquivo = self._cliente().files.upload(file=caminho, config=types.UploadFileConfig(mime_type=mime_type))
        except (errors.APIError, httpx.HTTPError) as erro:
            raise IAErroTemporario(f'envio de arquivo: {erro}') from erro
        expira = arquivo.expiration_time
        if expira is not None and expira.tzinfo is not None:
            expira = expira.astimezone(timezone.utc).replace(tzinfo=None)
        return ArquivoRemoto(nome=arquivo.name, uri=arquivo.uri, mime_type=mime_type, expira_em=expira)

    def apagar_arquivo(self, nome):
        self._cliente().files.delete(name=nome)
