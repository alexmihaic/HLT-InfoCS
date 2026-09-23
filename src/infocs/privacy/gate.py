"""Privacy Gate v1: detección determinista y conservadora antes de publicar."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import json
from pathlib import Path
import re
from typing import Any, Mapping

from infocs.models import Record


class PrivacyGateError(ValueError):
    """La configuración o ejecución del gate no cumple su contrato."""


class PrivacyDecisionType(StrEnum):
    ALLOW = "allow"
    QUARANTINE = "quarantine"
    REJECT = "reject"


class TaxIdentifierClassification(StrEnum):
    PERSONAL_IDENTIFIER = "personal_identifier"
    LEGAL_ENTITY_TAX_IDENTIFIER = "legal_entity_tax_identifier"
    AMBIGUOUS_TAX_IDENTIFIER = "ambiguous_tax_identifier"


_DECISIONS = frozenset(PrivacyDecisionType)
_RULE_NAMES = frozenset({
    "spanish_personal_identifier",
    "ambiguous_tax_identifier",
    "iban",
    "personal_email",
    "personal_phone",
    "structured_private_address",
})

_DNI_NIE_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:[XYZ][ -]?\d{7}|\d{8})[ -]?[A-Z](?![A-Za-z0-9])",
    re.IGNORECASE,
)
_PERSONAL_NIF_KLM_RE = re.compile(r"(?<![A-Za-z0-9])[KLM]\d{7}[A-Z](?![A-Za-z0-9])", re.IGNORECASE)
_LEGAL_ENTITY_NIF_RE = re.compile(r"(?<![A-Za-z0-9])[ABCDEFGHJNPQRSUVW]\d{7}[0-9A-J](?![A-Za-z0-9])", re.IGNORECASE)
_AMBIGUOUS_TAX_SHAPE_RE = re.compile(
    r"(?:\d{8}[A-Z]|[XYZKLM]\d{7}[A-Z]|[ABCDEFGHJNPQRSUVW]\d{7}[0-9A-J])\Z",
    re.IGNORECASE,
)
_IBAN_RE = re.compile(r"(?<![A-Z0-9])[A-Z]{2}\d{2}(?:[ -]?[A-Z0-9]){11,34}(?![A-Z0-9])", re.IGNORECASE)
_EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+\-])[A-Za-z0-9.!#$%&'*+/=?^_`{|}~\-]+@"
    r"([A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?)+)"
)
_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+34[ .-]?[6789](?:[ .-]?\d){8}|[6789](?:[ .-]?\d){2}[ .-]\d{3}[ .-]\d{3})(?!\d)"
)
_PRIVATE_ADDRESS_RE = re.compile(
    r"\b(?:domicilio|direcci[oó]n)\s+(?:de\s+)?(?:uso\s+)?(?:particular|personal)\s*:\s*"
    r"[^,\n]{3,120}\s+\d{1,4}\b",
    re.IGNORECASE,
)
_CONSUMER_EMAIL_PROVIDERS_DEFAULT = frozenset({
    "gmail.com", "googlemail.com", "hotmail.com", "outlook.com", "yahoo.com",
    "yahoo.es", "icloud.com", "proton.me", "protonmail.com",
})


@dataclass(frozen=True, slots=True)
class PrivacyReason:
    """Razón segura: nunca contiene el valor detectado."""

    rule: str
    field: str

    def to_dict(self) -> dict[str, str]:
        return {"rule": self.rule, "field": self.field}


@dataclass(frozen=True, slots=True)
class PrivacyClassification:
    """Clasificación estructural del identificador, sin copiar su valor."""

    classification: TaxIdentifierClassification
    field: str

    def to_dict(self) -> dict[str, str]:
        return {"classification": self.classification.value, "field": self.field}


@dataclass(frozen=True, slots=True)
class PrivacyDecision:
    decision: PrivacyDecisionType
    record_id: str
    reasons: tuple[PrivacyReason, ...] = ()
    classifications: tuple[PrivacyClassification, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.decision, PrivacyDecisionType) or self.decision not in _DECISIONS:
            raise PrivacyGateError("La decisión de privacidad no es válida.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "record_id": self.record_id,
            "reasons": [reason.to_dict() for reason in self.reasons],
            "classifications": [item.to_dict() for item in self.classifications],
        }


@dataclass(frozen=True, slots=True)
class PrivacyRule:
    enabled: bool
    decision: PrivacyDecisionType


@dataclass(frozen=True, slots=True)
class PrivacyConfig:
    rules: Mapping[str, PrivacyRule]
    personal_email_providers: frozenset[str]
    personal_phone_context_terms: tuple[str, ...]

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "PrivacyConfig":
        if not isinstance(payload, Mapping):
            raise PrivacyGateError("La configuración de privacidad debe ser un objeto JSON.")
        if payload.get("schema_version") != "1":
            raise PrivacyGateError("config/privacy-rules.json requiere schema_version 1.")
        raw_rules = payload.get("rules")
        if not isinstance(raw_rules, Mapping) or set(raw_rules) != _RULE_NAMES:
            raise PrivacyGateError("La configuración debe declarar exactamente las reglas v1.")
        rules: dict[str, PrivacyRule] = {}
        for name in sorted(_RULE_NAMES):
            raw_rule = raw_rules[name]
            if not isinstance(raw_rule, Mapping) or not isinstance(raw_rule.get("enabled"), bool):
                raise PrivacyGateError(f"La configuración de la regla {name} no es válida.")
            try:
                decision = PrivacyDecisionType(raw_rule.get("decision"))
            except ValueError as error:
                raise PrivacyGateError(f"La decisión de la regla {name} no es válida.") from error
            rules[name] = PrivacyRule(raw_rule["enabled"], decision)

        raw_providers = payload.get("personal_email_providers")
        if not isinstance(raw_providers, list) or not raw_providers:
            raise PrivacyGateError("personal_email_providers debe ser una lista no vacía.")
        providers = frozenset(_normalise_domain(value) for value in raw_providers)
        if "" in providers:
            raise PrivacyGateError("Hay un proveedor de email personal vacío.")

        raw_phone_terms = payload.get("personal_phone_context_terms")
        if not isinstance(raw_phone_terms, list) or not raw_phone_terms:
            raise PrivacyGateError("personal_phone_context_terms debe ser una lista no vacía.")
        phone_terms = tuple(_required_text(term, "personal_phone_context_terms") for term in raw_phone_terms)
        return cls(rules, providers, phone_terms)

    @classmethod
    def default(cls) -> "PrivacyConfig":
        config_path = Path(__file__).resolve().parents[3] / "config" / "privacy-rules.json"
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise PrivacyGateError("No se pudo cargar config/privacy-rules.json.") from error
        return cls.from_mapping(payload)


class PrivacyGate:
    """Evalúa records finalizados antes de cualquier escritura pública."""

    def __init__(self, config: PrivacyConfig | None = None) -> None:
        self.config = config if config is not None else PrivacyConfig.default()
        self.validate()

    @classmethod
    def default(cls) -> "PrivacyGate":
        return cls(PrivacyConfig.default())

    @classmethod
    def from_file(cls, path: str | Path) -> "PrivacyGate":
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise PrivacyGateError("No se pudo cargar la configuración de privacidad.") from error
        if not isinstance(payload, Mapping):
            raise PrivacyGateError("La configuración de privacidad debe ser un objeto JSON.")
        return cls(PrivacyConfig.from_mapping(payload))

    def validate(self) -> None:
        if set(self.config.rules) != _RULE_NAMES:
            raise PrivacyGateError("Faltan reglas de privacidad v1.")
        if not self.config.personal_email_providers or not self.config.personal_phone_context_terms:
            raise PrivacyGateError("La configuración del Privacy Gate está incompleta.")
        if any(
            not isinstance(rule, PrivacyRule)
            or not isinstance(rule.decision, PrivacyDecisionType)
            or rule.decision not in _DECISIONS
            for rule in self.config.rules.values()
        ):
            raise PrivacyGateError("Hay una decisión de privacidad desconocida.")

    def evaluate(self, record: Record) -> PrivacyDecision:
        if not isinstance(record, Record):
            raise PrivacyGateError("PrivacyGate.evaluate() requiere un Record finalizado.")

        reasons: list[PrivacyReason] = []
        classifications: list[PrivacyClassification] = []
        fields = _inspected_fields(record)
        for field, value in fields.items():
            if field.endswith("tax_identifier"):
                classification = classify_spanish_tax_identifier(value)
                if classification is not None:
                    classifications.append(PrivacyClassification(classification, field))
                    if classification is TaxIdentifierClassification.PERSONAL_IDENTIFIER:
                        self._detect(
                            "spanish_personal_identifier", field, lambda _: True, value, reasons
                        )
                    elif classification is TaxIdentifierClassification.AMBIGUOUS_TAX_IDENTIFIER:
                        self._detect("ambiguous_tax_identifier", field, lambda _: True, value, reasons)
                continue

            self._detect("spanish_personal_identifier", field, _has_valid_personal_identifier, value, reasons)
            self._detect("iban", field, _has_valid_iban, value, reasons)
            if field in {"title", "description"}:
                self._detect("personal_email", field, self._has_consumer_email, value, reasons)
                self._detect("personal_phone", field, self._has_contextual_personal_phone, value, reasons)
                self._detect("structured_private_address", field, _has_private_address, value, reasons)

        unique_reasons = {(reason.rule, reason.field): reason for reason in reasons}
        unique_classifications = {(item.classification.value, item.field): item for item in classifications}
        ordered_reasons = tuple(unique_reasons[key] for key in sorted(unique_reasons))
        ordered_classifications = tuple(unique_classifications[key] for key in sorted(unique_classifications))
        decisions = [self.config.rules[reason.rule].decision for reason in ordered_reasons]
        decision = (
            PrivacyDecisionType.REJECT
            if PrivacyDecisionType.REJECT in decisions
            else PrivacyDecisionType.QUARANTINE if decisions else PrivacyDecisionType.ALLOW
        )
        return PrivacyDecision(decision, record.id, ordered_reasons, ordered_classifications)

    def assert_allowed(self, record: Record) -> PrivacyDecision:
        decision = self.evaluate(record)
        if decision.decision is not PrivacyDecisionType.ALLOW:
            raise PrivacyGateError("El Record no está permitido para publicación.")
        return decision

    def _detect(self, rule: str, field: str, detector: Any, value: str, reasons: list[PrivacyReason]) -> None:
        configured = self.config.rules[rule]
        if configured.enabled and detector(value):
            reasons.append(PrivacyReason(rule=rule, field=field))

    def _has_consumer_email(self, value: str) -> bool:
        return any(
            _normalise_domain(match.group(1)) in self.config.personal_email_providers
            for match in _EMAIL_RE.finditer(value)
        )

    def _has_contextual_personal_phone(self, value: str) -> bool:
        for number in _PHONE_RE.finditer(value):
            preceding = value[max(0, number.start() - 100):number.start()].casefold()
            for term in self.config.personal_phone_context_terms:
                cue = term.casefold()
                cue_start = preceding.rfind(cue)
                if cue_start < 0:
                    continue
                gap = preceding[cue_start + len(cue):]
                if re.fullmatch(r"[\s:;,(.\-]{0,12}", gap):
                    return True
        return False


def classify_spanish_tax_identifier(value: str) -> TaxIdentifierClassification | None:
    """Clasifica sólo formatos españoles comprobables; nunca usa nombres/contexto."""
    candidate = value.strip().upper()
    if _has_valid_personal_identifier(candidate):
        return TaxIdentifierClassification.PERSONAL_IDENTIFIER
    if _LEGAL_ENTITY_NIF_RE.fullmatch(candidate) and _has_valid_legal_entity_nif(candidate):
        return TaxIdentifierClassification.LEGAL_ENTITY_TAX_IDENTIFIER
    if _AMBIGUOUS_TAX_SHAPE_RE.fullmatch(candidate):
        return TaxIdentifierClassification.AMBIGUOUS_TAX_IDENTIFIER
    return None


def _inspected_fields(record: Record) -> dict[str, str]:
    """Devuelve sólo texto público pertinente; excluye URLs, IDs y metadatos."""
    fields: dict[str, str] = {"title": record.title}
    if record.description is not None:
        fields["description"] = record.description
    if record.procurement and record.procurement.awardee:
        fields["procurement.awardee.name"] = record.procurement.awardee.name
        if record.procurement.awardee.tax_identifier is not None:
            fields["procurement.awardee.tax_identifier"] = record.procurement.awardee.tax_identifier
    if record.grant and record.grant.beneficiary:
        fields["grant.beneficiary.name"] = record.grant.beneficiary.name
        if record.grant.beneficiary.tax_identifier is not None:
            fields["grant.beneficiary.tax_identifier"] = record.grant.beneficiary.tax_identifier
    return fields


def _has_valid_personal_identifier(value: str) -> bool:
    for pattern in (_DNI_NIE_RE, _PERSONAL_NIF_KLM_RE):
        for match in pattern.finditer(value):
            compact = re.sub(r"[ -]", "", match.group(0)).upper()
            digits = compact[:-1]
            if digits[0] in "XYZ":
                digits = {"X": "0", "Y": "1", "Z": "2"}[digits[0]] + digits[1:]
            elif digits[0] in "KLM":
                digits = digits[1:]
            if "TRWAGMYFPDXBNJZSQVHLCKE"[int(digits) % 23] == compact[-1]:
                return True
    return False


def _has_valid_legal_entity_nif(value: str) -> bool:
    compact = value.upper()
    digits = compact[1:8]
    total = 0
    for index, char in enumerate(digits):
        digit = int(char)
        if index % 2 == 0:
            doubled = digit * 2
            total += doubled // 10 + doubled % 10
        else:
            total += digit
    control_digit = (10 - total % 10) % 10
    control_letter = "JABCDEFGHI"[control_digit]
    prefix = compact[0]
    if prefix in "PQRSNW":
        return compact[-1] == control_letter
    if prefix in "ABEH":
        return compact[-1] == str(control_digit)
    return compact[-1] in {str(control_digit), control_letter}


def _has_valid_iban(value: str) -> bool:
    for match in _IBAN_RE.finditer(value.upper()):
        compact = re.sub(r"[ -]", "", match.group(0))
        if not (15 <= len(compact) <= 34):
            continue
        numeric = "".join(str(ord(char) - 55) if char.isalpha() else char for char in compact[4:] + compact[:4])
        if int(numeric) % 97 == 1:
            return True
    return False


def _has_private_address(value: str) -> bool:
    return _PRIVATE_ADDRESS_RE.search(value) is not None


def _normalise_domain(value: Any) -> str:
    if not isinstance(value, str):
        raise PrivacyGateError("Los dominios deben ser texto.")
    return value.strip().lower().rstrip(".")


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PrivacyGateError(f"{field} debe contener texto no vacío.")
    return value.strip()
