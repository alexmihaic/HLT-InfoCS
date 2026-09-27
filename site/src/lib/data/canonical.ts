import type {
  AdministrationLevel,
  FrontendAuthority,
  FrontendDocument,
  FrontendEvent,
  FrontendFinancial,
  FrontendGeography,
  FrontendGrant,
  FrontendRecord,
} from './types';

const ADMINISTRATION_LEVELS = new Set<AdministrationLevel>([
  'municipal',
  'provincial',
  'autonomous',
  'state',
]);
const MONEY_FIELDS = {
  base_budget: 'baseBudget',
  estimated_value: 'estimatedValue',
  tender_amount: 'tenderAmount',
  award_amount: 'awardAmount',
  modification_amount: 'modificationAmount',
  grant_amount: 'grantAmount',
} as const;

type ObjectValue = Record<string, unknown>;

export function adaptRecord(value: unknown, label: string): FrontendRecord {
  const record = object(value, label);
  const source = object(record.source, `${label}.source`);
  const dates = object(record.dates, `${label}.dates`);
  const technical = object(record.technical, `${label}.technical`);

  if (!Object.hasOwn(record, 'authority')) {
    throw contractError(label, 'falta authority (puede ser null)');
  }

  return {
    id: requiredString(record.id, `${label}.id`),
    sourceId: requiredString(source.id, `${label}.source.id`),
    ...(record.source && typeof source.official_id === 'string'
      ? { officialId: requiredString(source.official_id, `${label}.source.official_id`) }
      : {}),
    category: requiredString(record.category, `${label}.category`),
    title: requiredString(record.title, `${label}.title`),
    authority: adaptAuthority(record.authority, `${label}.authority`),
    administrationLevel: nullableAdministrationLevel(
      record.administration_level,
      `${label}.administration_level`,
    ),
    ...(record.dates && dates.published_at !== undefined
      ? { publishedAt: dateString(dates.published_at, `${label}.dates.published_at`) }
      : {}),
    ...(record.dates && dates.event_at !== undefined
      ? { eventAt: dateString(dates.event_at, `${label}.dates.event_at`) }
      : {}),
    detectedAt: dateTimeString(dates.detected_at, `${label}.dates.detected_at`),
    lastCheckedAt: dateTimeString(dates.last_checked_at, `${label}.dates.last_checked_at`),
    sourceUrl: requiredString(record.source_url, `${label}.source_url`),
    ...(record.geography !== undefined
      ? { geography: adaptGeography(record.geography, `${label}.geography`) }
      : {}),
    ...(record.grant !== undefined ? { grant: adaptGrant(record.grant, `${label}.grant`) } : {}),
    ...(record.financial !== undefined
      ? { financial: adaptFinancial(record.financial, `${label}.financial`) }
      : {}),
    ...(record.documents !== undefined
      ? { documents: adaptDocuments(record.documents, `${label}.documents`) }
      : {}),
    tags: record.tags === undefined ? [] : stringArray(record.tags, `${label}.tags`),
    contentHash: hashString(technical.content_hash, `${label}.technical.content_hash`),
  };
}

export function adaptEvent(value: unknown, label: string): FrontendEvent {
  const event = object(value, label);
  const type = event.type;
  if (type !== 'create' && type !== 'update') {
    throw contractError(label, 'type debe ser create o update');
  }

  return {
    eventId: requiredString(event.event_id, `${label}.event_id`),
    type,
    recordId: requiredString(event.record_id, `${label}.record_id`),
    sourceId: requiredString(event.source_id, `${label}.source_id`),
    observedAt: dateTimeString(event.observed_at, `${label}.observed_at`),
    contentHash: hashString(event.content_hash, `${label}.content_hash`),
    ...(event.previous_content_hash !== undefined
      ? { previousContentHash: hashString(event.previous_content_hash, `${label}.previous_content_hash`) }
      : {}),
    ...(event.changed_fields !== undefined
      ? { changedFields: stringArray(event.changed_fields, `${label}.changed_fields`) }
      : {}),
  };
}

export function parseCanonicalJson(text: string, label: string): unknown {
  try {
    return JSON.parse(text) as unknown;
  } catch {
    throw contractError(label, 'JSON no parseable');
  }
}

function adaptAuthority(value: unknown, label: string): FrontendAuthority | null {
  if (value === null) return null;
  const authority = object(value, label);
  return {
    id: requiredString(authority.id, `${label}.id`),
    name: requiredString(authority.name, `${label}.name`),
    administrationLevel: nullableAdministrationLevel(
      authority.administration_level,
      `${label}.administration_level`,
    ),
  };
}

function adaptGeography(value: unknown, label: string): FrontendGeography {
  const geography = object(value, label);
  return {
    ...(geography.municipality !== undefined
      ? { municipality: requiredString(geography.municipality, `${label}.municipality`) }
      : {}),
    ...(geography.province !== undefined
      ? { province: requiredString(geography.province, `${label}.province`) }
      : {}),
  };
}

function adaptGrant(value: unknown, label: string): FrontendGrant {
  const grant = object(value, label);
  return {
    ...(grant.call_id !== undefined ? { callId: requiredString(grant.call_id, `${label}.call_id`) } : {}),
    ...(grant.resolution_id !== undefined
      ? { resolutionId: requiredString(grant.resolution_id, `${label}.resolution_id`) }
      : {}),
  };
}

function adaptFinancial(value: unknown, label: string): FrontendFinancial {
  const financial = object(value, label);
  const adapted: Record<string, { value: string; currency: string }> = {};
  for (const [canonicalKey, frontendKey] of Object.entries(MONEY_FIELDS)) {
    if (financial[canonicalKey] === undefined) continue;
    const amount = object(financial[canonicalKey], `${label}.${canonicalKey}`);
    adapted[frontendKey] = {
      value: requiredString(amount.value, `${label}.${canonicalKey}.value`),
      currency: requiredString(amount.currency, `${label}.${canonicalKey}.currency`),
    };
  }
  return adapted as FrontendFinancial;
}

function adaptDocuments(value: unknown, label: string): readonly FrontendDocument[] {
  if (!Array.isArray(value)) throw contractError(label, 'debe ser una lista');
  return value.map((item, index) => {
    const itemLabel = `${label}[${index}]`;
    const document = object(item, itemLabel);
    if (document.archive_status !== 'not_archived' && document.archive_status !== 'archived') {
      throw contractError(itemLabel, 'archive_status no reconocido');
    }
    return {
      sourceUrl: requiredString(document.source_url, `${itemLabel}.source_url`),
      archiveStatus: document.archive_status,
      hasLocalCopy: booleanValue(document.has_local_copy, `${itemLabel}.has_local_copy`),
      publicationAllowed: booleanValue(document.publication_allowed, `${itemLabel}.publication_allowed`),
    };
  });
}

function nullableAdministrationLevel(value: unknown, label: string): AdministrationLevel | null {
  if (value === null) return null;
  if (typeof value === 'string' && ADMINISTRATION_LEVELS.has(value as AdministrationLevel)) {
    return value as AdministrationLevel;
  }
  throw contractError(label, 'nivel administrativo incompatible');
}

function object(value: unknown, label: string): ObjectValue {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw contractError(label, 'debe ser un objeto');
  }
  return value as ObjectValue;
}

function requiredString(value: unknown, label: string): string {
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw contractError(label, 'debe ser texto no vacío');
  }
  return value;
}

function dateString(value: unknown, label: string): string {
  const result = requiredString(value, label);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(result) || Number.isNaN(Date.parse(`${result}T00:00:00Z`))) {
    throw contractError(label, 'fecha incompatible');
  }
  return result;
}

function dateTimeString(value: unknown, label: string): string {
  const result = requiredString(value, label);
  if (!/^\d{4}-\d{2}-\d{2}T/.test(result) || Number.isNaN(Date.parse(result))) {
    throw contractError(label, 'timestamp incompatible');
  }
  return result;
}

function hashString(value: unknown, label: string): string {
  const result = requiredString(value, label);
  if (!/^[a-f0-9]{64}$/.test(result)) throw contractError(label, 'hash incompatible');
  return result;
}

function stringArray(value: unknown, label: string): readonly string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== 'string')) {
    throw contractError(label, 'debe ser una lista de textos');
  }
  return value as string[];
}

function booleanValue(value: unknown, label: string): boolean {
  if (typeof value !== 'boolean') throw contractError(label, 'debe ser booleano');
  return value;
}

function contractError(label: string, reason: string): Error {
  return new Error(`Frontend data contract: ${label}: ${reason}.`);
}
