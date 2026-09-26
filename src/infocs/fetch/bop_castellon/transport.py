"""Cliente JSF stateful y acotado para la consulta de una edición BOP."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
import http.cookiejar
import socket
import ssl
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import (
    HTTPRedirectHandler,
    HTTPCookieProcessor,
    Request,
    build_opener,
)

from infocs.fetch.bop_castellon.config import (
    BOP_ACCEPT_HTML,
    BOP_ACCEPT_XML,
    BOP_ARCHIVE_URL,
    BOP_FORM_ID,
    BOP_MAX_GET_BYTES,
    BOP_MAX_POST_BYTES,
    BOP_PARTIAL_RENDER,
    BOP_SUBMIT_NAME,
    BOP_TIMEOUT_SECONDS,
    BOP_USER_AGENT,
    format_portal_date,
    normalize_requested_date,
)
from infocs.fetch.bop_castellon.models import BOPFetchResult, BOPFetchStatus
from infocs.fetch.bop_castellon.parser import (
    BOPContractError,
    parse_announcements_page,
    parse_search_partial_response,
    parse_selection_redirect,
    parse_view_state,
)


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


class _SameSessionOpener:
    def __init__(self, jar: http.cookiejar.CookieJar) -> None:
        self._opener = build_opener(HTTPCookieProcessor(jar), _NoRedirectHandler())

    def open(self, request: Request, timeout: float) -> Any:
        return self._opener.open(request, timeout=timeout)


OpenerFactory = Callable[[http.cookiejar.CookieJar], Any]


class BOPTransport:
    """Busca una edición, la selecciona por JSF y recupera su HTML de anuncios."""

    def __init__(
        self,
        *,
        timeout_seconds: float = BOP_TIMEOUT_SECONDS,
        max_get_bytes: int = BOP_MAX_GET_BYTES,
        max_post_bytes: int = BOP_MAX_POST_BYTES,
        opener_factory: OpenerFactory | None = None,
    ) -> None:
        if timeout_seconds <= 0 or max_get_bytes <= 0 or max_post_bytes <= 0:
            raise ValueError("Los límites del transporte deben ser positivos.")
        self.timeout_seconds = timeout_seconds
        self.max_get_bytes = max_get_bytes
        self.max_post_bytes = max_post_bytes
        self._opener_factory = opener_factory or _SameSessionOpener

    def fetch_issue(self, requested_date: date | str) -> BOPFetchResult:
        parsed_date, display_date = normalize_requested_date(requested_date)
        if parsed_date is None:
            return BOPFetchResult(BOPFetchStatus.INVALID_REQUEST, display_date, reason="invalid_date")

        jar = http.cookiejar.CookieJar()
        opener = self._opener_factory(jar)
        try:
            get_response = opener.open(
                Request(
                    BOP_ARCHIVE_URL,
                    headers={"Accept": BOP_ACCEPT_HTML, "User-Agent": BOP_USER_AGENT},
                    method="GET",
                ),
                timeout=self.timeout_seconds,
            )
            get_status, get_type, get_body = self._read_response(get_response, self.max_get_bytes)
            if get_status != 200:
                return self._failure(display_date, "http_failure", get_status)
            if not _mime_is(get_type, "text/html"):
                return self._failure(display_date, "mime_incompatible", get_status)
            html = _decode(get_body)
            try:
                view_state, hidden_fields = parse_view_state(html)
            except BOPContractError:
                return self._failure(display_date, "view_state_missing", get_status)

            form_date = format_portal_date(parsed_date)
            fields = dict(hidden_fields)
            fields.update(
                {
                    BOP_FORM_ID: BOP_FORM_ID,
                    "buscadorForm:numBoletinAntiguo": "",
                    "buscadorForm:fechaInicialAntiguo_input": form_date,
                    "buscadorForm:fechaFinalAntiguo_input": form_date,
                    BOP_SUBMIT_NAME: BOP_SUBMIT_NAME,
                    "javax.faces.ViewState": view_state,
                    "javax.faces.partial.ajax": "true",
                    "javax.faces.source": BOP_SUBMIT_NAME,
                    "javax.faces.partial.execute": BOP_FORM_ID,
                    "javax.faces.partial.render": BOP_PARTIAL_RENDER,
                }
            )
            post_data = urlencode(fields).encode("utf-8")
            post_request = Request(
                BOP_ARCHIVE_URL,
                data=post_data,
                headers={
                    "Accept": BOP_ACCEPT_XML,
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "Faces-Request": "partial/ajax",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": BOP_ARCHIVE_URL,
                    "User-Agent": BOP_USER_AGENT,
                },
                method="POST",
            )
            post_response = opener.open(post_request, timeout=self.timeout_seconds)
            post_status, post_type, post_body = self._read_response(post_response, self.max_post_bytes)
            if post_status != 200:
                return self._failure(display_date, "http_failure", post_status)
            if not _mime_is(post_type, "text/xml", "application/xml"):
                return self._failure(display_date, "mime_incompatible", post_status)
            search_xml = _decode(post_body)
            try:
                selection = parse_search_partial_response(
                    search_xml,
                    parsed_date,
                    current_view_state=view_state,
                )
            except BOPContractError as error:
                return self._failure(display_date, str(error), post_status)
            if selection is None:
                return BOPFetchResult(BOPFetchStatus.NO_PUBLICATION, display_date, http_status=post_status)

            selection_fields = dict(selection.hidden_fields)
            selection_fields.update(
                {
                    selection.form_id: selection.form_id,
                    "javax.faces.partial.ajax": "true",
                    "javax.faces.source": selection.source_component,
                    "javax.faces.partial.execute": "@all",
                    selection.source_component: selection.source_component,
                }
            )
            selection_data = urlencode(selection_fields).encode("utf-8")
            selection_request = Request(
                selection.action_url,
                data=selection_data,
                headers={
                    "Accept": BOP_ACCEPT_XML,
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "Faces-Request": "partial/ajax",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": BOP_ARCHIVE_URL,
                    "User-Agent": BOP_USER_AGENT,
                },
                method="POST",
            )
            selection_response = opener.open(selection_request, timeout=self.timeout_seconds)
            selection_status, selection_type, selection_body = self._read_response(
                selection_response,
                self.max_post_bytes,
            )
            if selection_status != 200:
                return self._failure(display_date, "selection_http_failure", selection_status)
            if not _mime_is(selection_type, "text/xml", "application/xml"):
                return self._failure(display_date, "selection_mime_incompatible", selection_status)
            selection_xml = _decode(selection_body)
            navigation_url = parse_selection_redirect(selection_xml, response_url=selection.action_url)

            announcements_request = Request(
                navigation_url,
                headers={"Accept": BOP_ACCEPT_HTML, "User-Agent": BOP_USER_AGENT},
                method="GET",
            )
            announcements_response = opener.open(announcements_request, timeout=self.timeout_seconds)
            page_status, page_type, page_body = self._read_response(announcements_response, self.max_get_bytes)
            if page_status != 200:
                return self._failure(display_date, "announcements_http_failure", page_status)
            if not _mime_is(page_type, "text/html"):
                return self._failure(display_date, "announcements_mime_incompatible", page_status)
            try:
                announcements = parse_announcements_page(_decode(page_body))
            except BOPContractError as error:
                return self._failure(
                    display_date,
                    str(error),
                    page_status,
                    diagnostic=error.diagnostic,
                )
        except _BodyTooLarge:
            return self._failure(display_date, "body_too_large")
        except BOPContractError as error:
            reason = str(error)
            return self._failure(display_date, reason)
        except HTTPError as error:
            return self._failure(display_date, "http_failure", error.code)
        except (TimeoutError, socket.timeout):
            return self._failure(display_date, "timeout")
        except (ssl.SSLError, URLError, OSError):
            return self._failure(display_date, "network_failure")

        issue = selection.issue
        issue_with_announcements = type(issue)(
            portal_id=issue.portal_id,
            published_date=issue.published_date,
            issue_number=issue.issue_number,
            issue_code=issue.issue_code,
            announcements=announcements,
        )
        return BOPFetchResult(
            BOPFetchStatus.COMPLETE_SUCCESS,
            display_date,
            issue=issue_with_announcements,
            http_status=page_status,
        )

    @staticmethod
    def _read_response(response: Any, limit: int) -> tuple[int, str | None, bytes]:
        try:
            with response:
                status = getattr(response, "status", None)
                if not isinstance(status, int):
                    status = response.getcode()
                headers = getattr(response, "headers", {})
                content_type = headers.get("Content-Type") if headers is not None else None
                declared = headers.get("Content-Length") if headers is not None else None
                if isinstance(declared, str):
                    try:
                        if int(declared) > limit:
                            raise _BodyTooLarge
                    except ValueError:
                        pass
                body = response.read(limit + 1)
        except _BodyTooLarge:
            raise
        if len(body) > limit:
            raise _BodyTooLarge
        return int(status), content_type if isinstance(content_type, str) else None, body

    @staticmethod
    def _failure(
        requested_date: str,
        reason: str,
        http_status: int | None = None,
        *,
        diagnostic: dict[str, object] | None = None,
    ) -> BOPFetchResult:
        return BOPFetchResult(
            BOPFetchStatus.SOURCE_FAILURE,
            requested_date,
            http_status=http_status,
            reason=reason,
            diagnostic=diagnostic,
        )


class _BodyTooLarge(Exception):
    pass


def _mime_is(content_type: str | None, *expected: str) -> bool:
    return content_type is not None and content_type.split(";", 1)[0].strip().lower() in expected


def _decode(body: bytes) -> str:
    try:
        return body.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise BOPContractError("invalid_encoding") from error
