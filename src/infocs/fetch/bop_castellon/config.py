"""Constantes runtime mínimas para el formulario JSF observado del BOP."""

from __future__ import annotations

from datetime import date, datetime
import re
from urllib.parse import urlsplit

BOP_HOST = "bop.dipcas.es"
BOP_BASE_URL = "https://bop.dipcas.es"
BOP_ARCHIVE_PATH = "/PortalBOP/boletinesAntiguos/"
BOP_ARCHIVE_URL = f"{BOP_BASE_URL}{BOP_ARCHIVE_PATH}"
BOP_USER_AGENT = "InfoCs/0.1 (+https://github.com/alexmihaic/HLT-InfoCS)"
BOP_TIMEOUT_SECONDS = 20.0
# Límites de seguridad InfoCs, no límites publicados por la Diputación.
BOP_MAX_GET_BYTES = 1024 * 1024
BOP_MAX_POST_BYTES = 8 * 1024 * 1024
BOP_ACCEPT_HTML = "text/html"
BOP_ACCEPT_XML = "text/xml, application/xml"
BOP_RESULT_UPDATE_ID = "formListBoletinAntiguos"
BOP_REDUCED_FORM_ID = "buscadorReducidaForm"
BOP_ANNOUNCEMENTS_CONTAINER_ID = "busquedaBoletinesForm:resultadoBusquedaBoletines"
BOP_FORM_ID = "buscadorForm"
BOP_SUBMIT_NAME = "buscadorForm:j_idt152"
BOP_PARTIAL_RENDER = "formListBoletinAntiguos formListAnunciosBolAnt buscadorForm buscadorReducidaForm"
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")


def normalize_requested_date(value: date | str) -> tuple[date | None, str]:
    """Valida una fecha ISO sin red y devuelve su fecha de calendario y texto."""
    if isinstance(value, datetime):
        return None, value.isoformat()
    if isinstance(value, date):
        return value, value.isoformat()
    if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
        return None, value if isinstance(value, str) else str(value)
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None, value
    return parsed, value


def format_portal_date(value: date) -> str:
    # El datepicker observado usa la notación JavaScript/PrimeFaces dd/mm/yy;
    # "yy" corresponde a año de cuatro dígitos (ejemplo auditado: 22/09/2026).
    return value.strftime("%d/%m/%Y")


def validate_official_url(url: str, *, path: str) -> str:
    """Exige URL HTTPS del host BOP y el endpoint de portal esperado."""
    if not isinstance(url, str) or not url:
        raise ValueError("URL BOP vacía.")
    parsed = urlsplit(url)
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("URL BOP no válida.") from error
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").lower().rstrip(".") != BOP_HOST
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or parsed.path != path
    ):
        raise ValueError("URL BOP no autorizada.")
    return url


def validate_portal_navigation_url(url: str) -> str:
    """Permite JSF navigation sólo bajo origen HTTPS y contexto PortalBOP."""
    if not isinstance(url, str) or not url:
        raise ValueError("URL BOP vacía.")
    parsed = urlsplit(url)
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("URL BOP no válida.") from error
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").lower().rstrip(".") != BOP_HOST
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or not parsed.path.startswith("/PortalBOP/")
    ):
        raise ValueError("Navegación BOP no autorizada.")
    return url
