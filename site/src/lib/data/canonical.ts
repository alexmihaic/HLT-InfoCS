import type {
  AdministrationLevel,
  FrontendAuthority,
  FrontendBDNSData,
  FrontendBDNSBudget,
  FrontendBDNSAuthorityHierarchy,
  FrontendBDNSClassification,
  FrontendBDNSApplication,
  FrontendBDNSRegulatoryBases,
  FrontendBDNSDocument,
  FrontendBDNSExtract,
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
  let bdns: FrontendBDNSData | undefined;
  if (record.source_data !== undefined) {
    const sourceData = closedObject(record.source_data, `${label}.source_data`, ['bdns']);
    if (source.id !== 'bdns' || record.category !== 'grants.call' || technical.content_hash_version !== 2) {
      throw contractError(label, 'binding BDNS source/category/hash version incompatible');
    }
    bdns = adaptBDNSData(sourceData.bdns, `${label}.source_data.bdns`);
  }

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
    ...(bdns !== undefined ? { bdns } : {}),
  };
}

/** Historic direct adapter calls may omit BDNS data; the public loader may not. */
export function assertProductiveRecord(record: FrontendRecord, label: string): void {
  if (record.sourceId === 'bdns' && (record.bdns === undefined || record.category !== 'grants.call')) {
    throw contractError(label, 'Record BDNS productivo requiere extensión v2 grants.call');
  }
}

function adaptBDNSData(value: unknown, label: string): FrontendBDNSData {
  const data = closedObject(value, label, [
    'extension_version', 'official_title_coofficial', 'authority_hierarchy', 'budget_total',
    'call_type', 'instruments', 'eligible_beneficiary_types', 'sectors', 'impact_regions',
    'received_date', 'application', 'purpose', 'regulatory_bases', 'electronic_office_url',
    'extract_published_in_official_diary', 'documents', 'extracts',
  ]);
  if (data.extension_version !== '1.0') throw contractError(label, 'BDNS extension version incompatible');
  const result: FrontendBDNSData = {
    extensionVersion: '1.0',
    ...optionalTexts(data, { official_title_coofficial: 'officialTitleCoofficial', call_type: 'callType',
      purpose: 'purpose', electronic_office_url: 'electronicOfficeUrl' }, label),
    ...optionalTexts(data, { received_date: 'receivedDate' }, label, bdnsDate),
    ...optionalBlock(data, 'authority_hierarchy', 'authorityHierarchy', label, adaptBDNSHierarchy),
    ...optionalBlock(data, 'budget_total', 'budgetTotal', label, adaptBDNSBudget),
    ...optionalBlock(data, 'application', 'application', label, adaptBDNSApplication),
    ...optionalBlock(data, 'regulatory_bases', 'regulatoryBases', label, adaptBDNSBases),
    ...optionalFlag(data, 'extract_published_in_official_diary', 'extractPublishedInOfficialDiary', label),
    instruments: bdnsArray(data.instruments, `${label}.instruments`, requiredString),
    eligibleBeneficiaryTypes: bdnsArray(data.eligible_beneficiary_types, `${label}.eligible_beneficiary_types`, adaptBDNSClassification),
    sectors: bdnsArray(data.sectors, `${label}.sectors`, adaptBDNSClassification),
    impactRegions: bdnsArray(data.impact_regions, `${label}.impact_regions`, requiredString),
    documents: bdnsArray(data.documents, `${label}.documents`, adaptBDNSDocument),
    extracts: bdnsArray(data.extracts, `${label}.extracts`, adaptBDNSExtract),
  };
  assertMeaningful(result, label, ['extensionVersion']);
  return result;
}

function adaptBDNSHierarchy(value: unknown, label: string): FrontendBDNSAuthorityHierarchy {
  const data = closedObject(value, label, ['nivel1', 'nivel2', 'nivel3']);
  const result = optionalTexts(data, { nivel1: 'nivel1', nivel2: 'nivel2', nivel3: 'nivel3' }, label);
  assertMeaningful(result, label);
  return result;
}

function adaptBDNSBudget(value: unknown, label: string): FrontendBDNSBudget {
  const data = closedObject(value, label, ['value', 'currency']);
  const amount = requiredString(data.value, `${label}.value`);
  if (!/^(0|[1-9][0-9]*)(\.[0-9]+)?$/.test(amount)) throw contractError(label, 'decimal canónico incompatible');
  const currency = optionalTexts(data, { currency: 'currency' }, label);
  if (currency.currency !== undefined && !/^[A-Z]{3}$/.test(currency.currency)) {
    throw contractError(label, 'currency incompatible');
  }
  return { value: amount, ...currency };
}

function adaptBDNSClassification(value: unknown, label: string): FrontendBDNSClassification {
  const data = closedObject(value, label, ['label', 'code']);
  return { label: requiredString(data.label, `${label}.label`), ...optionalTexts(data, { code: 'code' }, label) };
}

function adaptBDNSApplication(value: unknown, label: string): FrontendBDNSApplication {
  const data = closedObject(value, label, ['start_date', 'end_date', 'start_text', 'end_text', 'abierto']);
  const result = {
    ...optionalTexts(data, { start_date: 'startDate', end_date: 'endDate' }, label, bdnsDate),
    ...optionalTexts(data, { start_text: 'startText', end_text: 'endText' }, label),
    ...optionalFlag(data, 'abierto', 'abierto', label),
  };
  assertMeaningful(result, label);
  return result;
}

function adaptBDNSBases(value: unknown, label: string): FrontendBDNSRegulatoryBases {
  const data = closedObject(value, label, ['description', 'source_locator']);
  // Text only: no URL parser, navigation decision, trim or rewriting.
  const result = optionalTexts(data, { description: 'description', source_locator: 'sourceLocator' }, label);
  assertMeaningful(result, label);
  return result;
}

function adaptBDNSDocument(value: unknown, label: string): FrontendBDNSDocument {
  const data = closedObject(value, label, ['source_document_id', 'description', 'filename', 'published_date', 'modified_value']);
  if (typeof data.source_document_id !== 'number' || !Number.isSafeInteger(data.source_document_id) || data.source_document_id < 0) {
    throw contractError(label, 'document ID requiere entero no negativo representable exactamente');
  }
  return {
    sourceDocumentId: data.source_document_id,
    ...optionalTexts(data, { description: 'description', filename: 'filename', modified_value: 'modifiedValue' }, label),
    ...optionalTexts(data, { published_date: 'publishedDate' }, label, bdnsDate),
  };
}

function adaptBDNSExtract(value: unknown, label: string): FrontendBDNSExtract {
  const data = closedObject(value, label, ['cve', 'diary', 'source_url', 'publication_date', 'title', 'title_coofficial']);
  const result = {
    ...optionalTexts(data, { cve: 'cve', diary: 'diary', source_url: 'sourceUrl', title: 'title', title_coofficial: 'titleCoofficial' }, label),
    ...optionalTexts(data, { publication_date: 'publicationDate' }, label, bdnsDate),
  };
  assertMeaningful(result, label);
  return result;
}

function closedObject(value: unknown, label: string, keys: readonly string[]): ObjectValue {
  const data = object(value, label);
  if (Object.keys(data).some((key) => !keys.includes(key))) {
    // Unknown key names can themselves contain source text: never interpolate them.
    throw contractError(label, 'campo desconocido');
  }
  return data;
}

function optionalTexts<K extends string>(data: ObjectValue, mapping: Readonly<Record<string, K>>, label: string,
  reader: (value: unknown, label: string) => string = requiredString): Partial<Record<K, string>> {
  const result: Partial<Record<K, string>> = {};
  for (const [key, target] of Object.entries(mapping)) {
    if (data[key] !== undefined && data[key] !== null) result[target] = reader(data[key], `${label}.${key}`);
  }
  return result;
}

function optionalBlock<K extends string, T>(data: ObjectValue, key: string, target: K, label: string,
  reader: (value: unknown, label: string) => T): Partial<Record<K, T>> {
  const result: Partial<Record<K, T>> = {};
  if (data[key] !== undefined && data[key] !== null) result[target] = reader(data[key], `${label}.${key}`);
  return result;
}

function optionalFlag<K extends string>(data: ObjectValue, key: string, target: K, label: string): Partial<Record<K, boolean>> {
  const result: Partial<Record<K, boolean>> = {};
  if (data[key] !== undefined && data[key] !== null) result[target] = booleanValue(data[key], `${label}.${key}`);
  return result;
}

function bdnsArray<T>(value: unknown, label: string, reader: (value: unknown, label: string) => T): readonly T[] {
  if (value === undefined) return [];
  if (!Array.isArray(value)) throw contractError(label, 'debe ser una lista');
  return value.map((item, index) => reader(item, `${label}[${index}]`));
}

function assertMeaningful(value: object, label: string, excluded: readonly string[] = []): void {
  if (!Object.entries(value).some(([key, item]) => !excluded.includes(key) && item !== undefined && (!Array.isArray(item) || item.length > 0))) {
    throw contractError(label, 'bloque sin datos significativos');
  }
}

function bdnsDate(value: unknown, label: string): string {
  const result = dateString(value, label);
  // Date.parse alone accepts rollover dates such as February 30.
  if (result.startsWith('0000-') || new Date(`${result}T00:00:00Z`).toISOString().slice(0, 10) !== result) {
    throw contractError(label, 'fecha calendario incompatible');
  }
  return result;
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
