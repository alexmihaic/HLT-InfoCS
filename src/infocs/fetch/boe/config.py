"""Constantes de runtime verificadas para el sumario diario del BOE.

``collectors/boe/source_contract.yaml`` es documentación machine-readable de
la auditoría, no configuración consumida en runtime: el proyecto no incorpora
un parser YAML sólo para esta fase. Estas constantes son la única fuente de
verdad que usa el transporte hasta una futura convergencia documentada.
"""

from __future__ import annotations

from datetime import date, datetime
import re
from urllib.parse import urlsplit

BOE_ALLOWED_HOSTS = frozenset({"www.boe.es", "boe.es"})
BOE_SUMMARY_URL_TEMPLATE = "https://www.boe.es/datosabiertos/api/boe/sumario/{date}"
BOE_ACCEPT = "application/json"
BOE_USER_AGENT = "InfoCs/0.1"
DEFAULT_TIMEOUT_SECONDS = 15.0
# Límite de seguridad de InfoCs, no límite oficial del BOE. Es > 6 veces la
# muestra JSON de ~315 KB verificada en la auditoría de fuente.
DEFAULT_MAX_RESPONSE_BYTES = 2 * 1024 * 1024

_BOE_DATE_PATTERN = re.compile(r"\d{8}\Z")


def normalize_publication_date(value: date | str) -> str:
    """Devuelve una fecha BOE AAAAMMDD o rechaza la entrada antes de llamar a red."""
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    if not isinstance(value, str) or not _BOE_DATE_PATTERN.fullmatch(value):
        raise ValueError("La fecha BOE debe usar el formato YYYYMMDD.")
    try:
        datetime.strptime(value, "%Y%m%d")
    except ValueError as error:
        raise ValueError("La fecha BOE no es una fecha de calendario válida.") from error
    return value


def validate_boe_url(url: str) -> None:
    """Exige HTTPS y un host BOE aprobado; no autoriza URLs arbitrarias."""
    if not isinstance(url, str) or not url:
        raise ValueError("La URL BOE debe ser una cadena no vacía.")
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("La URL BOE contiene un puerto no válido.") from error
    if parsed.scheme != "https":
        raise ValueError("La URL BOE debe usar HTTPS.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("La URL BOE no puede contener credenciales.")
    if host not in BOE_ALLOWED_HOSTS:
        raise ValueError("La URL BOE apunta a un host no autorizado.")
    if port not in (None, 443):
        raise ValueError("La URL BOE usa un puerto no autorizado.")


def summary_url_for(publication_date: date | str) -> str:
    """Construye exclusivamente el endpoint auditado del sumario diario."""
    url = BOE_SUMMARY_URL_TEMPLATE.format(date=normalize_publication_date(publication_date))
    validate_boe_url(url)
    return url
