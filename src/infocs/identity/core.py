"""Identidad estable y canonicalización sintáctica, sin acceso a red."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re
from typing import Any, Mapping
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit


class IdentityError(ValueError): pass

@dataclass(frozen=True, slots=True)
class RecordIdentity:
    record_id: str
    strategy: str
    stable_identifier: str

def _slug(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    if not value: raise IdentityError("Identificador estable vacío.")
    return value

def canonical_url(value: str) -> str:
    """Normaliza solo esquema/host, fragmento, slash y tracking inequívoco."""
    try: parts = urlsplit(value)
    except ValueError: return value
    if not parts.scheme or not parts.netloc: return value
    host = parts.netloc.lower()
    path = quote(re.sub(r"/+", "/", parts.path or "/"), safe="/%:@")
    if path != "/": path = path.rstrip("/")
    pairs = [(key, val) for key, val in parse_qsl(parts.query, keep_blank_values=True)
             if not (key.lower().startswith("utm_") or key.lower() in {"gclid", "fbclid"})]
    # No se reordenan parámetros: puede alterar APIs o URLs administrativas.
    return urlunsplit((parts.scheme.lower(), host, path, urlencode(pairs, doseq=True), ""))

def identify(record: Mapping[str, Any]) -> RecordIdentity:
    source = str(record["source"]["id"])
    authority_data = record.get("authority")
    authority_id = str(authority_data.get("id", "")) if isinstance(authority_data, Mapping) else ""
    official_id = record["source"].get("official_id")
    if official_id:
        strategy, stable = "official_id", str(official_id)
    elif record.get("procurement", {}).get("expediente"):
        strategy, stable = "case_number", f"{authority_id}:{record['procurement']['expediente']}"
    elif record.get("source_url"):
        strategy, stable = "canonical_url", canonical_url(str(record["source_url"]))
    else:
        strategy = "composite_fingerprint"
        dates = record.get("dates", {})
        raw = "\x1f".join((source, authority_id, str(record.get("title", "")).casefold().strip(), str(dates.get("published_at", "")), str(record.get("procurement", {}).get("expediente", ""))))
        stable = sha256(raw.encode("utf-8")).hexdigest()
    # El sufijo evita colisiones de valores oficiales distintos que comparten slug.
    digest = sha256(stable.encode("utf-8")).hexdigest()[:16]
    token = f"{_slug(stable)[:64]}-{digest}" if strategy != "composite_fingerprint" else stable
    return RecordIdentity(f"infocs:{_slug(source)}:{token}", strategy, stable)
