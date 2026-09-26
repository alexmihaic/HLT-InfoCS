"""Configuración de transporte BDNS: los límites son política local InfoCs."""

from __future__ import annotations

from urllib.parse import urlencode

from infocs.fetch.bdns.models import BDNSSearchQuery

BDNS_API_BASE = "https://www.infosubvenciones.es/bdnstrans/api"
BDNS_SEARCH_PATH = "/convocatorias/busqueda"
BDNS_DETAIL_PATH = "/convocatorias"
BDNS_SEARCH_URL = f"{BDNS_API_BASE}{BDNS_SEARCH_PATH}"
BDNS_DETAIL_URL = f"{BDNS_API_BASE}{BDNS_DETAIL_PATH}"
BDNS_ACCEPT = "application/json"
BDNS_USER_AGENT = "InfoCs/0.1 (+https://github.com/alexmihaic/HLT-InfoCS)"

# Valores de protección decididos por InfoCs. No son límites publicados por BDNS.
BDNS_TIMEOUT_SECONDS = 15.0
BDNS_MAX_RESPONSE_BYTES = 2 * 1024 * 1024

BDNS_SEARCH_ORDER_FIELDS = frozenset(
    {
        "numeroConvocatoria",
        "mrr",
        "nivel1",
        "nivel2",
        "nivel3",
        "fechaRecepcion",
        "descripcion",
        "descripcionLeng",
    }
)


def validate_search_query(query: BDNSSearchQuery) -> None:
    if isinstance(query.page, bool) or not isinstance(query.page, int) or query.page < 0:
        raise ValueError("page debe ser un entero no negativo.")
    if isinstance(query.page_size, bool) or not isinstance(query.page_size, int) or query.page_size < 1:
        raise ValueError("page_size debe ser un entero positivo.")
    if query.order not in BDNS_SEARCH_ORDER_FIELDS:
        raise ValueError("order no pertenece al conjunto documentado por SNPSAP.")
    if query.direction not in {"asc", "desc"}:
        raise ValueError("direction debe ser asc o desc.")
    if query.numero_convocatoria is not None and (
        not isinstance(query.numero_convocatoria, str) or not query.numero_convocatoria.strip()
    ):
        raise ValueError("numero_convocatoria debe ser texto no vacío si se proporciona.")


def search_url_for(query: BDNSSearchQuery) -> str:
    validate_search_query(query)
    params: list[tuple[str, str]] = [
        ("page", str(query.page)),
        ("pageSize", str(query.page_size)),
        ("order", query.order),
        ("direccion", query.direction),
    ]
    if query.numero_convocatoria is not None:
        params.append(("numeroConvocatoria", query.numero_convocatoria))
    return f"{BDNS_SEARCH_URL}?{urlencode(params)}"


def detail_url_for(numero_convocatoria: str) -> str:
    if not isinstance(numero_convocatoria, str) or not numero_convocatoria.strip():
        raise ValueError("numeroConvocatoria debe ser texto no vacío.")
    return f"{BDNS_DETAIL_URL}?{urlencode({'numConv': numero_convocatoria})}"
