"""Política BOE de publicación por reglas declarativas, desactivada por defecto.

Complementa la revisión manual por ``official_id`` (ADR-016) sin sustituirla.
Precedencia (de mayor a menor):

1. Restricciones obligatorias: integridad del Record (hash, fuente,
   identificador) y Privacy distinto de ALLOW.
2. Evidencia obligatoria: sección, título, categoría e inclusión territorial.
   Ni 1 ni 2 pueden superarse con una aprobación manual.
3. Decisiones manuales explícitas por ID (aprobación, hold o rechazo humano).
4. Exclusiones de la política (secciones y términos de título).
5. Reglas positivas habilitadas.
6. HOLD por defecto.

Las decisiones humanas por ID preceden a las exclusiones porque son una
revisión del contenido concreto; las exclusiones sólo limitan reglas
generales. Una regla nunca prevalece sobre Privacy, un rechazo o un hold
manual. Con la política desactivada el resultado productivo es idéntico al de
``review_publication``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
import json
from pathlib import Path
import re
import unicodedata
from typing import Any, Mapping

from infocs.fetch.boe.models import BOEItem, BOETerritorialDecision, BOETerritorialDecisionStatus, BOETerritorialField
from infocs.diff.core import content_hash
from infocs.models import Category, Record
from infocs.privacy import PrivacyDecision, PrivacyDecisionType
from infocs.publication.review import (
    PublicationDecision,
    PublicationDecisionType,
    PublicationReviewConfig,
    review_publication,
)


DEFAULT_BOE_RULES_CONFIG = (
    Path(__file__).resolve().parents[4] / "config" / "publication-review" / "boe-rules.json"
)
RULE_APPROVED_REASON = "rule_approved"
_POLICY_ID = re.compile(r"boe\.rule-publication\.v[1-9][0-9]*\Z")
_RULE_ID = re.compile(r"[a-z0-9][a-z0-9-]{2,63}\Z")
_SECTION = re.compile(r"[0-9A-Z]{1,3}\Z")
_TERRITORIAL_REASONS = frozenset({"municipality_exact", "province_exact", "authority_exact"})
_TERRITORIAL_FIELDS = frozenset(item.value for item in BOETerritorialField)
_RULE_KEYS = frozenset({
    "rule_id", "enabled", "section_code", "category", "department_names",
    "territorial_fields", "territorial_reasons_all", "territorial_reasons_any",
    "title_must_match_any", "title_must_not_match_any",
})
_POLICY_KEYS = frozenset({"schema_version", "source_id", "policy_id", "enabled", "authorization", "exclusions", "rules"})
_AUTHORIZATION_KEYS = frozenset({"approved_by", "approved_on", "reference"})
_EXCLUSION_KEYS = frozenset({"section_codes", "title_terms"})
_EVALUATION_SEAL = object()


class BOERulePolicyError(ValueError):
    """La configuración de reglas BOE no cumple su contrato cerrado."""


class BOERuleOutcome(StrEnum):
    MANUAL_APPROVED = "manual_approved"
    CANDIDATE = "candidate"
    HOLD = "hold"
    DENY = "deny"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class BOEPublicationRule:
    rule_id: str
    enabled: bool
    section_code: str
    category: Category
    department_names: tuple[str, ...]
    territorial_fields: tuple[str, ...]
    territorial_reasons_all: tuple[str, ...]
    territorial_reasons_any: tuple[str, ...]
    title_must_match_any: tuple[str, ...]
    title_must_not_match_any: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BOEPublicationRulePolicy:
    policy_id: str
    enabled: bool
    approved_by: str | None
    approved_on: date | None
    reference: str | None
    excluded_sections: tuple[str, ...]
    excluded_title_terms: tuple[str, ...]
    rules: tuple[BOEPublicationRule, ...]

    @classmethod
    def from_file(cls, path: str | Path = DEFAULT_BOE_RULES_CONFIG) -> "BOEPublicationRulePolicy":
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise BOERulePolicyError("No se pudo cargar la política de reglas BOE.") from error
        return cls.from_mapping(payload)

    @classmethod
    def from_mapping(cls, payload: Any) -> "BOEPublicationRulePolicy":
        data = _closed(payload, _POLICY_KEYS, "política")
        if data["schema_version"] != "1" or data["source_id"] != "boe":
            raise BOERulePolicyError("Versión o fuente de la política no válida.")
        policy_id = data["policy_id"]
        if not isinstance(policy_id, str) or not _POLICY_ID.fullmatch(policy_id):
            raise BOERulePolicyError("policy_id no válido.")
        enabled = data["enabled"]
        if not isinstance(enabled, bool):
            raise BOERulePolicyError("enabled debe ser booleano.")

        approved_by = approved_on = reference = None
        authorization = data["authorization"]
        if authorization is not None:
            auth = _closed(authorization, _AUTHORIZATION_KEYS, "authorization")
            approved_by = _text(auth["approved_by"], "authorization.approved_by")
            reference = _text(auth["reference"], "authorization.reference")
            try:
                approved_on = date.fromisoformat(_text(auth["approved_on"], "authorization.approved_on"))
            except ValueError as error:
                raise BOERulePolicyError("authorization.approved_on no es una fecha válida.") from error

        exclusions = _closed(data["exclusions"], _EXCLUSION_KEYS, "exclusions")
        excluded_sections = _sections(exclusions["section_codes"], "exclusions.section_codes")
        excluded_terms = _terms(exclusions["title_terms"], "exclusions.title_terms", required=False)

        raw_rules = data["rules"]
        if not isinstance(raw_rules, list):
            raise BOERulePolicyError("rules debe ser una lista.")
        rules = tuple(_parse_rule(raw, index, excluded_sections) for index, raw in enumerate(raw_rules))
        if len({rule.rule_id for rule in rules}) != len(rules):
            raise BOERulePolicyError("rule_id duplicado.")

        if enabled:
            # Activación de dos llaves: flag global más autorización humana registrada.
            if approved_by is None or approved_on is None or reference is None:
                raise BOERulePolicyError("Activar la política requiere authorization completa.")
            if not any(rule.enabled for rule in rules):
                raise BOERulePolicyError("Una política activa requiere al menos una regla habilitada.")
        elif any(rule.enabled for rule in rules):
            raise BOERulePolicyError("Ninguna regla puede estar habilitada con la política desactivada.")

        return cls(policy_id, enabled, approved_by, approved_on, reference, excluded_sections, excluded_terms, rules)

    @property
    def active_rules(self) -> tuple[BOEPublicationRule, ...]:
        return tuple(rule for rule in self.rules if self.enabled and rule.enabled)


@dataclass(frozen=True, slots=True)
class BOERuleEvaluation:
    """Resultado auditable; sólo el evaluador puede emitirlo (sello)."""

    outcome: BOERuleOutcome
    reasons: tuple[str, ...]
    rule_id: str | None
    record_id: str
    content_hash: str
    policy_id: str | None
    active: bool
    _seal: object = field(repr=False, compare=False)

    def is_issued(self) -> bool:
        return self._seal is _EVALUATION_SEAL


def evaluate_boe_publication(
    item: BOEItem,
    territorial: BOETerritorialDecision,
    record: Record,
    privacy: PrivacyDecision,
    manual_config: PublicationReviewConfig,
    policy: BOEPublicationRulePolicy | None,
    *,
    shadow: bool = False,
) -> BOERuleEvaluation:
    """Evalúa sin efectos. ``shadow`` evalúa reglas aunque estén desactivadas.

    En modo shadow el resultado CANDIDATE significa sólo "cumpliría la regla";
    ``active`` permanece False y nunca puede convertirse en autorización.
    """
    if not isinstance(record, Record) or record.source.id != "boe":
        raise BOERulePolicyError("La política sólo evalúa Records BOE.")
    if not isinstance(privacy, PrivacyDecision) or privacy.record_id != record.id:
        raise BOERulePolicyError("La decisión Privacy no corresponde al Record.")
    policy_id = policy.policy_id if policy is not None else None
    live = policy is not None and policy.enabled and not shadow

    def result(outcome: BOERuleOutcome, *reasons: str, rule_id: str | None = None, active: bool = False) -> BOERuleEvaluation:
        evaluation = object.__new__(BOERuleEvaluation)
        for name, value in (
            ("outcome", outcome), ("reasons", tuple(reasons)), ("rule_id", rule_id),
            ("record_id", record.id), ("content_hash", record.technical.content_hash),
            ("policy_id", policy_id), ("active", active), ("_seal", _EVALUATION_SEAL),
        ):
            object.__setattr__(evaluation, name, value)
        return evaluation

    # 1. Restricciones obligatorias.
    if (
        content_hash(record.to_dict()) != record.technical.content_hash
        or record.source.official_id != item.official_id
    ):
        return result(BOERuleOutcome.DENY, "record_integrity_failure", active=live)
    if privacy.decision is not PrivacyDecisionType.ALLOW:
        return result(BOERuleOutcome.DENY, f"privacy_{privacy.decision.value}", active=live)

    # 2. Evidencia obligatoria.
    missing = []
    if not item.section_code or not item.section_code.strip():
        missing.append("missing_section")
    if not item.title or not item.title.strip():
        missing.append("missing_title")
    if not isinstance(record.category, Category):
        missing.append("missing_category")
    if territorial.status is not BOETerritorialDecisionStatus.INCLUDE or not territorial.matches:
        missing.append("missing_territorial_inclusion")
    if missing:
        return result(BOERuleOutcome.UNRESOLVED, *missing, active=live)

    # 3. Decisiones humanas explícitas por ID.
    manual = review_publication(record, privacy, manual_config)
    if manual.explicitly_listed:
        if manual.decision is PublicationDecisionType.REJECTED:
            return result(BOERuleOutcome.DENY, "manual_rejected", active=live)
        if manual.decision is PublicationDecisionType.HOLD:
            return result(BOERuleOutcome.HOLD, f"manual_hold_{manual.reason_code}", active=live)
        return result(BOERuleOutcome.MANUAL_APPROVED, "manual_approved", active=live)
    if policy is None:
        return result(BOERuleOutcome.HOLD, "no_policy")

    section = item.section_code.strip().upper()
    title = _normalise(item.title)

    # 4. Exclusiones de la política (sólo limitan reglas automáticas).
    if section in policy.excluded_sections:
        return result(BOERuleOutcome.HOLD, "excluded_section", active=live)
    if any(_contains(title, term) for term in policy.excluded_title_terms):
        return result(BOERuleOutcome.HOLD, "excluded_title_term", active=live)

    # 5. Reglas positivas.
    rules = policy.rules if shadow else policy.active_rules
    section_rules = [rule for rule in rules if rule.section_code == section]
    if not section_rules:
        return result(BOERuleOutcome.HOLD, "no_rule_for_section", active=live)
    failures: list[str] = []
    for rule in section_rules:
        reason = _rule_failure(rule, item, territorial, record, title)
        if reason is None:
            return result(BOERuleOutcome.CANDIDATE, "rule_matched", rule_id=rule.rule_id, active=live)
        failures.append(reason)

    # 6. HOLD por defecto, con el primer motivo observable.
    return result(BOERuleOutcome.HOLD, failures[0], active=live)


def publication_decision_for(evaluation: BOERuleEvaluation, manual: PublicationDecision) -> PublicationDecision:
    """Traduce una evaluación activa al contrato productivo de Publication Review.

    Las restricciones obligatorias prevalecen sobre cualquier decisión manual:
    un fallo de integridad aborta (fail-closed) y la falta de evidencia o un
    Privacy distinto de ALLOW nunca terminan en aprobación. Fuera de eso, las
    decisiones manuales explícitas se devuelven intactas. Sólo una evaluación
    emitida, activa y CANDIDATE produce aprobación por regla.
    """
    if not evaluation.is_issued() or not evaluation.active:
        return manual
    first = evaluation.reasons[0] if evaluation.reasons else ""
    if first == "record_integrity_failure":
        raise BOERulePolicyError("Integridad del Record BOE no verificable; publicación abortada.")
    if evaluation.outcome in {BOERuleOutcome.DENY, BOERuleOutcome.UNRESOLVED}:
        if manual.decision is PublicationDecisionType.REJECTED:
            return manual
        if first.startswith("privacy_"):
            return PublicationDecision(PublicationDecisionType.HOLD, "personal_content_review", manual.explicitly_listed)
        if first == "missing_territorial_inclusion":
            return PublicationDecision(PublicationDecisionType.HOLD, "territorial_review_required", manual.explicitly_listed)
        if evaluation.outcome is BOERuleOutcome.UNRESOLVED:
            return PublicationDecision(PublicationDecisionType.HOLD, "not_in_allowlist", manual.explicitly_listed)
    if manual.explicitly_listed or manual.decision is not PublicationDecisionType.HOLD:
        return manual
    if evaluation.outcome is BOERuleOutcome.CANDIDATE:
        return PublicationDecision(PublicationDecisionType.APPROVED, RULE_APPROVED_REASON, False)
    if first in {"excluded_section", "excluded_title_term", "rule_title_exclusion"}:
        return PublicationDecision(PublicationDecisionType.HOLD, "personal_content_review", False)
    if first == "territorial_requirements_not_met":
        return PublicationDecision(PublicationDecisionType.HOLD, "territorial_review_required", False)
    return manual


def _rule_failure(
    rule: BOEPublicationRule,
    item: BOEItem,
    territorial: BOETerritorialDecision,
    record: Record,
    title: str,
) -> str | None:
    if record.category is not rule.category:
        return "category_mismatch"
    if rule.department_names and _normalise(item.department_name) not in {_normalise(name) for name in rule.department_names}:
        return "department_not_allowed"
    reasons = {
        match.reason.value
        for match in territorial.matches
        if match.field.value in rule.territorial_fields
    }
    if not set(rule.territorial_reasons_all) <= reasons:
        return "territorial_requirements_not_met"
    if rule.territorial_reasons_any and not reasons & set(rule.territorial_reasons_any):
        return "territorial_requirements_not_met"
    if rule.title_must_not_match_any and any(_contains(title, term) for term in rule.title_must_not_match_any):
        return "rule_title_exclusion"
    if rule.title_must_match_any and not any(_contains(title, term) for term in rule.title_must_match_any):
        return "title_pattern_not_matched"
    return None


def _parse_rule(raw: Any, index: int, excluded_sections: tuple[str, ...]) -> BOEPublicationRule:
    data = _closed(raw, _RULE_KEYS, f"rules[{index}]")
    rule_id = data["rule_id"]
    if not isinstance(rule_id, str) or not _RULE_ID.fullmatch(rule_id):
        raise BOERulePolicyError(f"rules[{index}].rule_id no válido.")
    if not isinstance(data["enabled"], bool):
        raise BOERulePolicyError(f"rules[{index}].enabled debe ser booleano.")
    section = data["section_code"]
    if not isinstance(section, str) or not _SECTION.fullmatch(section):
        raise BOERulePolicyError(f"rules[{index}].section_code no válido.")
    if section in excluded_sections:
        raise BOERulePolicyError(f"rules[{index}] no puede habilitar una sección excluida.")
    try:
        category = Category(data["category"])
    except ValueError as error:
        raise BOERulePolicyError(f"rules[{index}].category no válida.") from error
    fields = _closed_values(data["territorial_fields"], _TERRITORIAL_FIELDS, f"rules[{index}].territorial_fields")
    reasons_all = _closed_values(data["territorial_reasons_all"], _TERRITORIAL_REASONS, f"rules[{index}].territorial_reasons_all", required=False)
    reasons_any = _closed_values(data["territorial_reasons_any"], _TERRITORIAL_REASONS, f"rules[{index}].territorial_reasons_any", required=False)
    if not reasons_all and not reasons_any:
        raise BOERulePolicyError(f"rules[{index}] requiere evidencia territorial explícita.")
    title_any = _terms(data["title_must_match_any"], f"rules[{index}].title_must_match_any", required=True)
    title_not = _terms(data["title_must_not_match_any"], f"rules[{index}].title_must_not_match_any", required=False)
    departments = data["department_names"]
    if not isinstance(departments, list) or not departments or not all(isinstance(value, str) and value.strip() for value in departments):
        raise BOERulePolicyError(f"rules[{index}].department_names requiere al menos un departamento.")
    return BOEPublicationRule(
        rule_id, data["enabled"], section, category, tuple(departments), fields,
        reasons_all, reasons_any, title_any, title_not,
    )


def _closed(value: Any, keys: frozenset[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise BOERulePolicyError(f"{label} debe declarar exactamente: {', '.join(sorted(keys))}.")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BOERulePolicyError(f"{label} debe ser texto no vacío.")
    return value.strip()


def _sections(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and _SECTION.fullmatch(item) for item in value):
        raise BOERulePolicyError(f"{label} no válido.")
    return tuple(value)


def _terms(value: Any, label: str, *, required: bool) -> tuple[str, ...]:
    if not isinstance(value, list) or (required and not value):
        raise BOERulePolicyError(f"{label} debe ser una lista{' no vacía' if required else ''}.")
    terms = []
    for item in value:
        if not isinstance(item, str) or not _normalise(item):
            raise BOERulePolicyError(f"{label} contiene un término vacío.")
        terms.append(_normalise(item))
    return tuple(terms)


def _closed_values(value: Any, allowed: frozenset[str], label: str, *, required: bool = True) -> tuple[str, ...]:
    if not isinstance(value, list) or (required and not value) or not all(item in allowed for item in value):
        raise BOERulePolicyError(f"{label} no válido.")
    return tuple(value)


def _normalise(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(stripped.split())


def _contains(normalised_text: str, term: str) -> bool:
    """Coincidencia por palabra completa (sin subcadenas), admitiendo plural."""
    return re.search(rf"(?<!\w){re.escape(term)}(?:e?s)?(?!\w)", normalised_text) is not None
