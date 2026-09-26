"""Cliente HTTP serial y de sólo lectura para búsqueda/detalle SNPSAP."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
import json
import socket
import ssl
from typing import Any, TypeVar
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from infocs.fetch.bdns.config import (
    BDNS_ACCEPT,
    BDNS_MAX_RESPONSE_BYTES,
    BDNS_TIMEOUT_SECONDS,
    BDNS_USER_AGENT,
    detail_url_for,
    search_url_for,
)
from infocs.fetch.bdns.models import (
    BDNSConvocatoriaDetail,
    BDNSFetchResult,
    BDNSPage,
    BDNSRequestStatus,
    BDNSSearchQuery,
)
from infocs.fetch.bdns.parser import BDNSContractError, parse_bdns_detail, parse_bdns_search


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


_OPENER = build_opener(_NoRedirectHandler())
ResponseOpener = Callable[[Request, float], Any]
PayloadT = TypeVar("PayloadT")


def _open_without_redirects(request: Request, timeout: float) -> Any:
    return _OPENER.open(request, timeout=timeout)


class BDNSTransport:
    """Obtiene JSON tipado; nunca persiste ni expone cuerpos de respuesta.

    La consulta es serial y sin reintentos automáticos. Timeout y límite de
    cuerpo son protecciones InfoCs, no límites declarados por la API.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = BDNS_TIMEOUT_SECONDS,
        max_response_bytes: int = BDNS_MAX_RESPONSE_BYTES,
        opener: ResponseOpener | None = None,
    ) -> None:
        if timeout_seconds <= 0 or max_response_bytes <= 0:
            raise ValueError("timeout y máximo de respuesta deben ser positivos.")
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self._opener = opener or _open_without_redirects

    def search(self, query: BDNSSearchQuery | None = None) -> BDNSFetchResult[BDNSPage]:
        query = query or BDNSSearchQuery()
        try:
            url = search_url_for(query)
        except ValueError:
            return BDNSFetchResult(BDNSRequestStatus.INVALID_REQUEST, None, reason="invalid_query")
        raw_result = self._get_json(url)
        if raw_result.status is not BDNSRequestStatus.SUCCESS or raw_result.payload is None:
            return BDNSFetchResult(raw_result.status, raw_result.http_status, reason=raw_result.reason)
        http_status, payload = raw_result.http_status, raw_result.payload
        try:
            page = parse_bdns_search(payload)
        except BDNSContractError:
            return BDNSFetchResult(BDNSRequestStatus.SOURCE_FAILURE, http_status, reason="invalid_payload")
        outcome = BDNSRequestStatus.NO_RESULTS if not page.items else BDNSRequestStatus.SUCCESS
        return BDNSFetchResult(outcome, http_status, payload=page)

    def fetch_detail(self, numero_convocatoria: str) -> BDNSFetchResult[BDNSConvocatoriaDetail]:
        try:
            url = detail_url_for(numero_convocatoria)
        except ValueError:
            return BDNSFetchResult(BDNSRequestStatus.INVALID_REQUEST, None, reason="invalid_query")
        raw_result = self._get_json(url)
        if raw_result.status is not BDNSRequestStatus.SUCCESS or raw_result.payload is None:
            return BDNSFetchResult(raw_result.status, raw_result.http_status, reason=raw_result.reason)
        http_status, payload = raw_result.http_status, raw_result.payload
        try:
            detail = parse_bdns_detail(payload)
        except BDNSContractError:
            return BDNSFetchResult(BDNSRequestStatus.SOURCE_FAILURE, http_status, reason="invalid_payload")
        if detail.codigo_bdns != numero_convocatoria:
            return BDNSFetchResult(BDNSRequestStatus.SOURCE_FAILURE, http_status, reason="identity_mismatch")
        return BDNSFetchResult(BDNSRequestStatus.SUCCESS, http_status, payload=detail)

    def _get_json(self, url: str) -> BDNSFetchResult[dict[str, Any]]:
        request = Request(
            url,
            headers={"Accept": BDNS_ACCEPT, "User-Agent": BDNS_USER_AGENT},
            method="GET",
        )
        try:
            response = self._opener(request, self.timeout_seconds)
        except HTTPError as error:
            error.close()
            return _failure_for_status(error.code)
        except (TimeoutError, socket.timeout, ssl.SSLError, URLError, OSError):
            return BDNSFetchResult(BDNSRequestStatus.SOURCE_FAILURE, None, reason="network_failure")

        try:
            with response:
                status = _response_status(response)
                if status != 200:
                    return _failure_for_status(status)
                content_type = _header(response, "Content-Type")
                if not _is_json_mime(content_type):
                    return BDNSFetchResult(BDNSRequestStatus.SOURCE_FAILURE, status, reason="mime_incompatible")
                if _declared_too_large(response, self.max_response_bytes):
                    return BDNSFetchResult(BDNSRequestStatus.SOURCE_FAILURE, status, reason="body_too_large")
                body = response.read(self.max_response_bytes + 1)
        except (TimeoutError, socket.timeout, ssl.SSLError, URLError, OSError):
            return BDNSFetchResult(BDNSRequestStatus.SOURCE_FAILURE, None, reason="network_failure")

        if len(body) > self.max_response_bytes:
            return BDNSFetchResult(BDNSRequestStatus.SOURCE_FAILURE, 200, reason="body_too_large")
        try:
            payload = json.loads(body.decode("utf-8"), parse_float=Decimal)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return BDNSFetchResult(BDNSRequestStatus.SOURCE_FAILURE, 200, reason="invalid_json")
        if not isinstance(payload, dict):
            return BDNSFetchResult(BDNSRequestStatus.SOURCE_FAILURE, 200, reason="invalid_payload")
        return BDNSFetchResult(BDNSRequestStatus.SUCCESS, status, payload=payload)


def _failure_for_status(status: int) -> BDNSFetchResult[Any]:
    if status == 400:
        return BDNSFetchResult(BDNSRequestStatus.INVALID_REQUEST, status, reason="http_400")
    if status == 429:
        return BDNSFetchResult(BDNSRequestStatus.SOURCE_FAILURE, status, reason="rate_limited")
    return BDNSFetchResult(BDNSRequestStatus.SOURCE_FAILURE, status, reason="http_failure")


def _response_status(response: Any) -> int:
    status = getattr(response, "status", None)
    if not isinstance(status, int):
        status = response.getcode()
    if not isinstance(status, int):
        raise OSError("Respuesta HTTP sin status válido.")
    return status


def _header(response: Any, name: str) -> str | None:
    headers = getattr(response, "headers", None)
    value = headers.get(name) if headers is not None else None
    return value if isinstance(value, str) else None


def _is_json_mime(content_type: str | None) -> bool:
    return content_type is not None and content_type.split(";", 1)[0].strip().lower() == BDNS_ACCEPT


def _declared_too_large(response: Any, maximum: int) -> bool:
    content_length = _header(response, "Content-Length")
    if content_length is None:
        return False
    try:
        return int(content_length) > maximum
    except ValueError:
        return False
