"""Política de red del canal 643 de PLACSP (contrato v0.2, §3 y §4).

Solo constantes y validación de URL, sin red.

Política PROVISIONAL de cero queries y cero fragmentos: ninguna URL del canal 643
observada (raíz y archivos `next`) lleva query, y aceptar parámetros arbitrarios
ampliaría la superficie sin evidencia. Cualquier `?` o `#` se rechaza con el motivo
estable `url_query_or_fragment`, sin excepciones. Debe contrastarse con el feed
oficial antes de activar transporte real (el contrato v0.1 §7 hablaba de "query
legítima"; el v0.2 no la menciona). La política de dos orígenes es
provisional: el contrato la propone, pero el segundo origen no está aprobado como
excepción, así que solo puede usarse con un opener inyectado (pruebas).
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import urljoin, urlsplit

FEED_ID = "643"
OFFICIAL_ID_PREFIX = f"{FEED_ID}::"

PRIMARY_HOST = "contrataciondelsectorpublico.gob.es"
SECONDARY_HOST = "contrataciondelestado.es"  # los enlaces del feed lo usan; sin aprobar
CHANNEL_PATH_PREFIX = "/sindicacion/sindicacion_643/"
ROOT_FILE = "licitacionesPerfilesContratanteCompleto3.atom"
ROOT_URL = f"https://{PRIMARY_HOST}{CHANNEL_PATH_PREFIX}{ROOT_FILE}"

_FILE_PATTERN = re.compile(r"licitacionesPerfilesContratanteCompleto3(?:_\d{8}_\d{6})?\.atom\Z")
_FORBIDDEN_CHARS = re.compile(r"[\x00-\x20\x7f\\@]")
_ENCODED_HAZARD = re.compile(r"%(?:2[eEfF5]|5[cC]|00|3[fF]|23|40)", re.IGNORECASE)

USER_AGENT = "InfoCs-placsp/0 (read-only)"
ACCEPT = "application/atom+xml"
ALLOWED_CONTENT_TYPE = "application/atom+xml"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_RESPONSE_BYTES = 32 * 1024 * 1024  # recalibrable (D10); la página observada pesaba ~12 MB
DEFAULT_MAX_PAGES = 5


class UrlPolicyError(ValueError):
    """URL fuera de política; `code` es un código estable sin datos de la URL."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class TransportPolicy:
    name: str
    hosts: frozenset[str]
    provisional: bool = False


# Única política utilizable con la red real.
PRODUCTION_POLICY = TransportPolicy("placsp-643-primary", frozenset({PRIMARY_HOST}))
# Propuesta del contrato v0.2 §4. Desactivada para uso real: ver PlacspTransport.
PROVISIONAL_TWO_ORIGIN_POLICY = TransportPolicy(
    "placsp-643-two-origin-provisional", frozenset({PRIMARY_HOST, SECONDARY_HOST}), provisional=True
)


def validate_feed_url(url: object, policy: TransportPolicy) -> str:
    """Valida una URL absoluta del canal 643 y la devuelve sin cambios."""
    if not isinstance(url, str) or not url:
        raise UrlPolicyError("url_not_string")
    if "?" in url or "#" in url:
        raise UrlPolicyError("url_query_or_fragment")
    if _FORBIDDEN_CHARS.search(url):
        raise UrlPolicyError("url_forbidden_characters")
    if _ENCODED_HAZARD.search(url):
        raise UrlPolicyError("url_encoded_hazard")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise UrlPolicyError("url_unparseable") from None
    if parts.scheme != "https":
        raise UrlPolicyError("url_scheme")
    if parts.username is not None or parts.password is not None:
        raise UrlPolicyError("url_userinfo")
    host = parts.hostname or ""
    if host not in policy.hosts or parts.netloc.lower() not in {host, f"{host}:443"} or port not in (None, 443):
        raise UrlPolicyError("url_host_not_allowed")
    path = parts.path
    if not path.startswith(CHANNEL_PATH_PREFIX) or "//" in path:
        raise UrlPolicyError("url_path_not_allowed")
    segments = path.split("/")
    if any(segment in {".", ".."} for segment in segments):
        raise UrlPolicyError("url_path_not_allowed")
    if "/" in path[len(CHANNEL_PATH_PREFIX):] or not _FILE_PATTERN.fullmatch(segments[-1]):
        raise UrlPolicyError("url_file_not_allowed")
    return url


def resolve_next_url(current_url: str, reference: object, policy: TransportPolicy) -> str:
    """Resuelve un `rel=next` contra la URL actual (nunca contra `xml:base`).

    La referencia cruda se comprueba antes de resolverla para que un traversal no
    desaparezca durante la resolución; el destino completo se valida después.
    """
    if not isinstance(reference, str) or not reference:
        raise UrlPolicyError("next_not_string")
    if "?" in reference or "#" in reference:
        raise UrlPolicyError("url_query_or_fragment")
    if _FORBIDDEN_CHARS.search(reference) or _ENCODED_HAZARD.search(reference) or ".." in reference:
        raise UrlPolicyError("next_unsafe")
    if any(segment == "." for segment in reference.split("/")):
        raise UrlPolicyError("next_unsafe")  # `urljoin` normalizaría "." antes de validar el destino
    return validate_feed_url(urljoin(current_url, reference), policy)
