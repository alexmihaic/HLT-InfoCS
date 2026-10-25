"""Transporte de solo lectura del canal 643 de PLACSP.

GET por HTTPS, sin credenciales, sin redirecciones, sin reintentos. Timeout y
límites de cuerpo configurables. El opener es inyectable: las pruebas no abren
sockets. No existe CLI ni runner; nada en este módulo escribe en disco.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import socket
import ssl
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from infocs.fetch.placsp.config import (
    ACCEPT,
    ALLOWED_CONTENT_TYPE,
    DEFAULT_MAX_PAGES,
    DEFAULT_MAX_RESPONSE_BYTES,
    DEFAULT_TIMEOUT_SECONDS,
    PRODUCTION_POLICY,
    ROOT_URL,
    USER_AGENT,
    TransportPolicy,
    UrlPolicyError,
    resolve_next_url,
    validate_feed_url,
)
from infocs.fetch.placsp.models import PlacspPage, PlacspParseError, ParserLimits
from infocs.fetch.placsp.parser import parse_feed_page

_CHUNK_BYTES = 64 * 1024


class PlacspTransportError(RuntimeError):
    """Fallo de transporte o de paginación; `reason` es un código estable sin datos de la URL."""

    def __init__(self, reason: str, http_status: int | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.http_status = http_status


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


_OPENER = build_opener(_NoRedirectHandler())
ResponseOpener = Callable[[Request, float], Any]


def _open_without_redirects(request: Request, timeout: float) -> Any:
    return _OPENER.open(request, timeout=timeout)


@dataclass(frozen=True, slots=True)
class FetchedPage:
    url: str
    body: bytes
    status: int

    def __repr__(self) -> str:
        return f"FetchedPage(status={self.status}, bytes={len(self.body)})"


class PlacspTransport:
    def __init__(
        self,
        *,
        policy: TransportPolicy = PRODUCTION_POLICY,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        max_pages: int = DEFAULT_MAX_PAGES,
        opener: ResponseOpener | None = None,
    ) -> None:
        if timeout_seconds <= 0 or max_response_bytes <= 0 or max_pages <= 0:
            raise ValueError("timeout, tamaño máximo y páginas máximas deben ser positivos.")
        if policy.provisional and opener is None:
            # El segundo origen no está aprobado: la política provisional solo se prueba con respuestas ficticias.
            raise PlacspTransportError("provisional_policy_disabled")
        self.policy = policy
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.max_pages = max_pages
        self._opener = opener or _open_without_redirects

    def fetch_page(self, url: str) -> FetchedPage:
        try:
            validate_feed_url(url, self.policy)
        except UrlPolicyError:
            raise PlacspTransportError("invalid_request_url") from None
        request = Request(url, headers={"Accept": ACCEPT, "User-Agent": USER_AGENT}, method="GET")
        try:
            response = self._opener(request, self.timeout_seconds)
        except HTTPError as error:
            error.close()
            raise _status_error(error.code) from None
        except (TimeoutError, socket.timeout):
            raise PlacspTransportError("timeout") from None
        except (ssl.SSLError, URLError, OSError):
            raise PlacspTransportError("network_failure") from None
        try:
            with response:
                status = getattr(response, "status", None)
                if not isinstance(status, int):
                    status = response.getcode()
                if status != 200:
                    raise _status_error(status)
                headers = getattr(response, "headers", None)
                self._check_headers(headers, status)
                body = self._read_limited(response, status)
        except (TimeoutError, socket.timeout):
            raise PlacspTransportError("timeout") from None
        except (ssl.SSLError, URLError, OSError):
            raise PlacspTransportError("network_failure") from None
        return FetchedPage(url, body, status)

    def fetch_chain(
        self, start_url: str = ROOT_URL, *, limits: ParserLimits | None = None
    ) -> tuple[tuple[FetchedPage, PlacspPage], ...]:
        """Sigue `rel=next` con tope de páginas y detección de ciclos.

        Cualquier fallo (red, XML, paginación o entradas descartadas) aborta toda la
        cadena: no se devuelven páginas parciales ni incompletas. No decide completitud ni avanza ningún estado.
        """
        limits = limits or ParserLimits(max_bytes=self.max_response_bytes)
        results: list[tuple[FetchedPage, PlacspPage]] = []
        seen: set[str] = set()
        url: str | None = start_url
        while url is not None:
            if url in seen:
                raise PlacspTransportError("pagination_loop")
            if len(results) >= self.max_pages:
                raise PlacspTransportError("too_many_pages")
            seen.add(url)
            fetched = self.fetch_page(url)
            try:
                page = parse_feed_page(fetched.body, limits)
            except PlacspParseError as error:
                raise PlacspTransportError(f"parse_{error.code}") from None
            if not page.complete:  # defensa: parse_feed_page ya falla cerrado en modo estricto
                raise PlacspTransportError("parse_entries_discarded")
            results.append((fetched, page))
            href = page.feed.next_href
            if href is None:
                url = None
                continue
            try:
                url = resolve_next_url(fetched.url, href, self.policy)
            except UrlPolicyError:
                raise PlacspTransportError("pagination_unsafe") from None
        return tuple(results)

    def _check_headers(self, headers: Any, status: int) -> None:
        content_type = headers.get("Content-Type") if headers is not None else None
        if not isinstance(content_type, str) or content_type.split(";", 1)[0].strip().lower() != ALLOWED_CONTENT_TYPE:
            raise PlacspTransportError("mime_incompatible", status)
        encoding = headers.get("Content-Encoding") if headers is not None else None
        if isinstance(encoding, str) and encoding.strip().lower() not in {"", "identity"}:
            raise PlacspTransportError("content_encoding_unsupported", status)
        declared = headers.get("Content-Length") if headers is not None else None
        if isinstance(declared, str):
            if not declared.strip().isdigit():
                raise PlacspTransportError("invalid_content_length", status)
            if int(declared) > self.max_response_bytes:
                raise PlacspTransportError("body_too_large", status)

    def _read_limited(self, response: Any, status: int) -> bytes:
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = response.read(min(_CHUNK_BYTES, self.max_response_bytes + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > self.max_response_bytes:
                raise PlacspTransportError("body_too_large", status)
            chunks.append(chunk)
        return b"".join(chunks)


def _status_error(status: int) -> PlacspTransportError:
    if 300 <= status < 400:
        return PlacspTransportError("redirect_rejected", status)
    if status == 429:
        return PlacspTransportError("rate_limited", status)
    if 500 <= status < 600:
        return PlacspTransportError("server_error", status)
    return PlacspTransportError("http_failure", status)
