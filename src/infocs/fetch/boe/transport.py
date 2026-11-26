"""Transporte HTTP conservador para el único endpoint BOE autorizado en 03B."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
import json
import socket
import ssl
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from infocs.fetch.boe.config import (
    BOE_ACCEPT,
    BOE_USER_AGENT,
    DEFAULT_MAX_RESPONSE_BYTES,
    DEFAULT_TIMEOUT_SECONDS,
    summary_url_for,
)
from infocs.fetch.boe.models import BOEFetchResult, BOEFetchStatus
from infocs.fetch.boe.parser import BOEContractError, parse_boe_summary


class _NoRedirectHandler(HTTPRedirectHandler):
    """Convierte cualquier 3xx en error: 03B no necesita redirects."""

    def redirect_request(self, request, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


_NO_REDIRECT_OPENER = build_opener(_NoRedirectHandler())
ResponseOpener = Callable[[Request, float], Any]


def _open_without_redirects(request: Request, timeout: float) -> Any:
    return _NO_REDIRECT_OPENER.open(request, timeout=timeout)


class BOETransport:
    """Descarga, valida y parsea un sumario sin escribir respuestas a disco.

    Reintenta de forma limitada errores transitorios de transporte.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        opener: ResponseOpener | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds debe ser positivo.")
        if max_response_bytes <= 0:
            raise ValueError("max_response_bytes debe ser positivo.")
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self._opener = opener or _open_without_redirects
        self._sleeper = sleeper

    def fetch_daily_summary(self, publication_date: date | str) -> BOEFetchResult:
        for attempt in range(3):
            result = self._fetch_once(publication_date)
            transient = result.reason == "network_timeout" or (result.reason == "http_failure" and result.http_status in {429, 500, 502, 503, 504})
            if not transient or attempt == 2:
                return result
            self._sleeper(float(2 ** attempt))
        raise AssertionError("unreachable")

    def _fetch_once(self, publication_date: date | str) -> BOEFetchResult:
        """Obtiene sólo el sumario BOE auditado para una fecha AAAAMMDD."""
        url = summary_url_for(publication_date)
        request = Request(
            url,
            headers={"Accept": BOE_ACCEPT, "User-Agent": BOE_USER_AGENT},
            method="GET",
        )
        try:
            response = self._opener(request, self.timeout_seconds)
        except HTTPError as error:
            return self._result_for_http_status(error.code)
        except (TimeoutError, socket.timeout):
            return BOEFetchResult(BOEFetchStatus.SOURCE_FAILURE, None, reason="network_timeout")
        except URLError as error:
            reason = "network_timeout" if isinstance(error.reason, (TimeoutError, socket.timeout)) else "network_failure"
            return BOEFetchResult(BOEFetchStatus.SOURCE_FAILURE, None, reason=reason)
        except (ssl.SSLError, OSError):
            return BOEFetchResult(BOEFetchStatus.SOURCE_FAILURE, None, reason="network_failure")

        try:
            with response:
                status = _response_status(response)
                if status != 200:
                    return self._result_for_http_status(status)
                if not _is_json_mime(_header(response, "Content-Type")):
                    return BOEFetchResult(BOEFetchStatus.SOURCE_FAILURE, status, reason="mime_incompatible")
                if _declared_too_large(response, self.max_response_bytes):
                    return BOEFetchResult(BOEFetchStatus.SOURCE_FAILURE, status, reason="body_too_large")
                body = response.read(self.max_response_bytes + 1)
        except (TimeoutError, socket.timeout):
            return BOEFetchResult(BOEFetchStatus.SOURCE_FAILURE, None, reason="network_timeout")
        except URLError as error:
            reason = "network_timeout" if isinstance(error.reason, (TimeoutError, socket.timeout)) else "network_failure"
            return BOEFetchResult(BOEFetchStatus.SOURCE_FAILURE, None, reason=reason)
        except (ssl.SSLError, OSError):
            return BOEFetchResult(BOEFetchStatus.SOURCE_FAILURE, None, reason="network_failure")

        if len(body) > self.max_response_bytes:
            return BOEFetchResult(BOEFetchStatus.SOURCE_FAILURE, 200, reason="body_too_large")
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return BOEFetchResult(BOEFetchStatus.SOURCE_FAILURE, 200, reason="invalid_json")
        try:
            summary = parse_boe_summary(payload)
        except BOEContractError:
            return BOEFetchResult(BOEFetchStatus.SOURCE_FAILURE, 200, reason="invalid_payload")
        return BOEFetchResult(BOEFetchStatus.COMPLETE_SUCCESS, 200, summary=summary)

    @staticmethod
    def _result_for_http_status(status: int) -> BOEFetchResult:
        if status == 404:
            return BOEFetchResult(BOEFetchStatus.NO_DAILY_PUBLICATION, status, reason="daily_summary_not_found")
        if status == 400:
            return BOEFetchResult(BOEFetchStatus.INVALID_REQUEST, status, reason="invalid_request")
        return BOEFetchResult(BOEFetchStatus.SOURCE_FAILURE, status, reason="http_failure")


def _response_status(response: Any) -> int:
    status = getattr(response, "status", None)
    if not isinstance(status, int):
        status = response.getcode()
    if not isinstance(status, int):
        raise OSError("La respuesta HTTP no tiene un status válido.")
    return status


def _header(response: Any, name: str) -> str | None:
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    value = headers.get(name)
    return value if isinstance(value, str) else None


def _is_json_mime(content_type: str | None) -> bool:
    return content_type is not None and content_type.split(";", 1)[0].strip().lower() == BOE_ACCEPT


def _declared_too_large(response: Any, maximum: int) -> bool:
    content_length = _header(response, "Content-Length")
    if content_length is None:
        return False
    try:
        return int(content_length) > maximum
    except ValueError:
        return False
