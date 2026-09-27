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

const EVENT_FIELD_LABELS: Readonly<Record<string, string>> = {
  title: 'título',
  category: 'tipo de publicación',
  authority: 'organismo',
  'authority.name': 'organismo',
  administration_level: 'nivel administrativo',
  source_url: 'enlace oficial',
  'dates.published_at': 'fecha de publicación',
  'dates.event_at': 'fecha del acto',
  'geography.municipality': 'municipio',
  'geography.province': 'provincia',
  'financial.grant_amount': 'importe de la convocatoria',
};

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
  const fields = [...new Set((event.changedFields ?? []).map((field) => EVENT_FIELD_LABELS[field] ?? 'información de la ficha'))];
  return fields.length > 0
    ? `InfoCs detectó cambios en ${fields.join(', ')}`
    : 'InfoCs detectó cambios en la ficha';
}
