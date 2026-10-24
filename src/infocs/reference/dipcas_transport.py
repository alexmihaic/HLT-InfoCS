"""Transporte de solo lectura para el dataset `ayuntamientos` de la Diputación de Castellón.

OpenDataSoft Explore API v2.1. Peticiones GET por HTTPS, sin credenciales, sin
redirecciones, sin reintentos. Timeout y límite de cuerpo son protecciones InfoCs.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
import socket
import ssl
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

DIPCAS_HOST = "dipcas.opendatasoft.com"
DIPCAS_DATASET_ID = "ayuntamientos"
DIPCAS_DATASET_URL = f"https://{DIPCAS_HOST}/api/explore/v2.1/catalog/datasets/{DIPCAS_DATASET_ID}"
DIPCAS_RECORDS_URL = f"{DIPCAS_DATASET_URL}/records"
DIPCAS_USER_AGENT = "InfoCs-reference/0 (read-only)"
DIPCAS_TIMEOUT_SECONDS = 20.0
DIPCAS_MAX_RESPONSE_BYTES = 1_048_576
DIPCAS_PAGE_SIZE = 100  # máximo observado de `limit` en /records de Explore v2.1
DIPCAS_MAX_PAGES = 5

# Campos oficiales solicitados (minimización en origen). Contrastados con
# `fields` del metadato del dataset el 2026-10-24.
DIPCAS_SELECT_FIELDS = ("id", "ine", "dir3", "nombre_poblacion", "comarca", "web_ayuntamiento", "sede_electronica")
DIPCAS_ORDER_BY = ("dir3", "ine")


class DipcasFetchError(RuntimeError):
    """Fallo de transporte o de contrato; `reason` es un código estable."""

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
class DipcasRecordsResult:
    records: tuple[dict[str, Any], ...]
    total_count: int
    request_urls: tuple[str, ...]


def _quote_keep_commas(value: str, safe: str = "", encoding: str | None = None, errors: str | None = None) -> str:
    return quote(value, safe=",", encoding=encoding, errors=errors)


def records_url(*, offset: int, limit: int) -> str:
    if offset < 0 or not 0 < limit <= DIPCAS_PAGE_SIZE:
        raise ValueError("offset/limit fuera de rango.")
    query = urlencode(
        {
            "select": ",".join(DIPCAS_SELECT_FIELDS),
            "order_by": ",".join(DIPCAS_ORDER_BY),
            "limit": limit,
            "offset": offset,
        },
        quote_via=_quote_keep_commas,
    )
    return f"{DIPCAS_RECORDS_URL}?{query}"


class DipcasTransport:
    def __init__(
        self,
        *,
        timeout_seconds: float = DIPCAS_TIMEOUT_SECONDS,
        max_response_bytes: int = DIPCAS_MAX_RESPONSE_BYTES,
        max_pages: int = DIPCAS_MAX_PAGES,
        opener: ResponseOpener | None = None,
    ) -> None:
        if timeout_seconds <= 0 or max_response_bytes <= 0 or max_pages <= 0:
            raise ValueError("timeout, tamaño máximo y páginas máximas deben ser positivos.")
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.max_pages = max_pages
        self._opener = opener or _open_without_redirects

    def fetch_metadata(self) -> tuple[dict[str, Any], str]:
        """Devuelve (metadatos del dataset, URL consultada)."""
        return self._get_json(DIPCAS_DATASET_URL), DIPCAS_DATASET_URL

    def fetch_records(self) -> DipcasRecordsResult:
        records: list[dict[str, Any]] = []
        urls: list[str] = []
        total: int | None = None
        for _ in range(self.max_pages):
            url = records_url(offset=len(records), limit=DIPCAS_PAGE_SIZE)
            urls.append(url)
            payload = self._get_json(url)
            page_total, results = payload.get("total_count"), payload.get("results")
            if isinstance(page_total, bool) or not isinstance(page_total, int) or page_total < 0 or not isinstance(results, list):
                raise DipcasFetchError("invalid_payload")
            if total is not None and page_total != total:
                raise DipcasFetchError("inconsistent_total_count")
            total = page_total
            if len(results) > DIPCAS_PAGE_SIZE or not all(isinstance(item, dict) for item in results):
                raise DipcasFetchError("invalid_payload")
            records.extend(results)
            if len(records) > total:
                raise DipcasFetchError("inconsistent_total_count")
            if len(records) == total:
                return DipcasRecordsResult(tuple(records), total, tuple(urls))
            if not results:
                raise DipcasFetchError("truncated_pagination")
        raise DipcasFetchError("too_many_pages")

    def _get_json(self, url: str) -> dict[str, Any]:
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.hostname != DIPCAS_HOST:
            raise DipcasFetchError("invalid_request")
        request = Request(url, headers={"Accept": "application/json", "User-Agent": DIPCAS_USER_AGENT}, method="GET")
        try:
            response = self._opener(request, self.timeout_seconds)
        except HTTPError as error:
            error.close()
            raise _status_error(error.code) from None
        except (TimeoutError, socket.timeout):
            raise DipcasFetchError("timeout") from None
        except (ssl.SSLError, URLError, OSError):
            raise DipcasFetchError("network_failure") from None
        try:
            with response:
                status = getattr(response, "status", None)
                if not isinstance(status, int):
                    status = response.getcode()
                if status != 200:
                    raise _status_error(status)
                headers = getattr(response, "headers", None)
                content_type = headers.get("Content-Type") if headers is not None else None
                if not isinstance(content_type, str) or content_type.split(";", 1)[0].strip().lower() != "application/json":
                    raise DipcasFetchError("mime_incompatible", status)
                declared = headers.get("Content-Length") if headers is not None else None
                if isinstance(declared, str) and declared.isdigit() and int(declared) > self.max_response_bytes:
                    raise DipcasFetchError("body_too_large", status)
                body = response.read(self.max_response_bytes + 1)
        except (TimeoutError, socket.timeout):
            raise DipcasFetchError("timeout") from None
        except (ssl.SSLError, URLError, OSError):
            raise DipcasFetchError("network_failure") from None
        if len(body) > self.max_response_bytes:
            raise DipcasFetchError("body_too_large", 200)
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise DipcasFetchError("invalid_json", 200) from None
        if not isinstance(payload, dict):
            raise DipcasFetchError("invalid_payload", 200)
        return payload


def _status_error(status: int) -> DipcasFetchError:
    if status == 429:
        return DipcasFetchError("rate_limited", status)
    if 500 <= status < 600:
        return DipcasFetchError("server_error", status)
    return DipcasFetchError("http_failure", status)
