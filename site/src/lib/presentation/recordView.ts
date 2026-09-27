import type { FrontendRecord } from '../data/types';
import { formatPortalDate } from './dates';

export interface PrimaryDateView {
  readonly value: string;
  readonly label: 'Publicado' | 'Detectado por InfoCs';
  readonly display: string;
}

export function primaryDate(record: FrontendRecord): PrimaryDateView {
  const value = record.publishedAt ?? record.detectedAt;
  return {
    value,
    label: record.publishedAt ? 'Publicado' : 'Detectado por InfoCs',
    display: formatPortalDate(value),
  };
}

export function geographyLabels(record: FrontendRecord): readonly string[] {
  if (!record.geography) return [];
  return [
    ...(record.geography.municipality ? [`Municipio: ${record.geography.municipality}`] : []),
    ...(record.geography.province ? [`Provincia: ${record.geography.province}`] : []),
  ];
}
