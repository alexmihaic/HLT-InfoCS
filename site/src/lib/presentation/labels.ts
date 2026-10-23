import type { FrontendEvent, FrontendRecord, SourceMeta } from '../data/types';

const CATEGORY_LABELS: Readonly<Record<string, string>> = {
  regulation: 'Normativa',
  procurement: 'Contratación pública',
  'procurement.notice': 'Licitación',
  'procurement.award': 'Adjudicación',
  grants: 'Subvenciones',
  'grants.call': 'Convocatoria de subvención',
  'grants.resolution': 'Resolución de subvención',
  budget: 'Presupuestos',
  employment: 'Empleo público',
  urbanism: 'Urbanismo',
  governing_bodies: 'Órganos de gobierno',
  agreement: 'Convenios',
  auction: 'Subastas',
  other: 'Otros actos y publicaciones',
};

const SOURCE_LABELS: Readonly<Record<string, string>> = {
  boe: 'BOE',
  bdns: 'BDNS',
  bop_castellon: 'BOP Castellón',
};

const LEVEL_LABELS: Readonly<Record<string, string>> = {
  municipal: 'Municipal',
  provincial: 'Provincial',
  autonomous: 'Autonómico',
  state: 'Estatal',
};

// Closed paths, not prefix matching: an unknown descendant must stay unknown.
// Table order is also the public order, independent of changed_fields ordering.
const EVENT_FIELD_GROUPS = [
  { paths: ['title'], label: 'el título' },
  { paths: ['category'], label: 'el tipo de publicación' },
  { paths: ['authority', 'authority.name'], label: 'el organismo' },
  { paths: ['administration_level'], label: 'el nivel administrativo' },
  { paths: ['source_url'], label: 'el enlace oficial' },
  { paths: ['dates', 'dates.published_at', 'dates.event_at'], label: 'las fechas de la publicación' },
  { paths: ['geography.municipality'], label: 'el municipio' },
  { paths: ['geography.province'], label: 'la provincia' },
  { paths: ['financial.grant_amount'], label: 'el importe de la convocatoria' },
  { paths: ['documents'], label: 'la documentación' },
] as const;

// Canonical BDNS paths (not the camelCase frontend projection). Arrays are
// atomic in the semantic diff. Labels describe an area, never a change direction.
const BDNS_EVENT_FIELD_GROUPS = [
  { paths: ['source_data.bdns.official_title_coofficial'], label: 'el título' },
  { paths: ['source_data.bdns.authority_hierarchy', 'source_data.bdns.authority_hierarchy.nivel1', 'source_data.bdns.authority_hierarchy.nivel2', 'source_data.bdns.authority_hierarchy.nivel3'], label: 'el organismo convocante' },
  { paths: ['source_data.bdns.application', 'source_data.bdns.application.start_date', 'source_data.bdns.application.end_date', 'source_data.bdns.application.start_text', 'source_data.bdns.application.end_text', 'source_data.bdns.application.abierto'], label: 'el plazo de solicitud' },
  { paths: ['source_data.bdns.budget_total', 'source_data.bdns.budget_total.value', 'source_data.bdns.budget_total.currency'], label: 'el presupuesto de la convocatoria' },
  { paths: ['source_data.bdns.eligible_beneficiary_types'], label: 'los tipos de destinatarios' },
  { paths: ['source_data.bdns.documents'], label: 'la documentación' },
  { paths: ['source_data.bdns.extracts', 'source_data.bdns.extract_published_in_official_diary'], label: 'los extractos en diarios oficiales' },
  { paths: ['source_data.bdns.regulatory_bases', 'source_data.bdns.regulatory_bases.description', 'source_data.bdns.regulatory_bases.source_locator'], label: 'las bases reguladoras' },
] as const;

export function categoryLabel(category: string): string {
  return CATEGORY_LABELS[category] ?? 'Publicación administrativa';
}

export function sourceLabel(sourceId: string, sources: readonly SourceMeta[]): string {
  return SOURCE_LABELS[sourceId] ?? sources.find((source) => source.sourceId === sourceId)?.name ?? 'Fuente oficial';
}

export function administrationLevelLabel(level: NonNullable<FrontendRecord['administrationLevel']>): string {
  return LEVEL_LABELS[level];
}

export function eventDescription(event: FrontendEvent): string {
  if (event.type === 'create') return 'InfoCs incorporó esta publicación';
  const changed = new Set(event.changedFields ?? []);
  if (changed.size === 0) return 'InfoCs detectó cambios en la ficha';
  const groups: readonly { readonly paths: readonly string[]; readonly label: string }[] = [
    ...EVENT_FIELD_GROUPS,
    ...(event.sourceId === 'bdns' ? BDNS_EVENT_FIELD_GROUPS : []),
  ];
  const recognized = new Set<string>();
  const labels = new Set<string>();
  for (const group of groups) {
    if (!group.paths.some((path) => changed.has(path))) continue;
    for (const path of group.paths) recognized.add(path);
    labels.add(event.sourceId === 'boe' && group.label === 'el organismo' ? 'la sección del BOE' : group.label);
  }
  if ([...changed].some((path) => !recognized.has(path))) {
    labels.add(labels.size > 0 ? 'otros datos de la ficha' : 'información de la ficha');
  }
  const parts = [...labels];
  const text = parts.length > 1 ? `${parts.slice(0, -1).join(', ')} y ${parts.at(-1)}` : parts[0];
  return `InfoCs detectó cambios en ${text}`;
}
