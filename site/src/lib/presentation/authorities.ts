import type { FrontendRecord } from '../data/types';

/**
 * Groups published BDNS Records by the literal `authority_hierarchy.nivel2`
 * value supplied by BDNS. This is an official label, not a normalized legal
 * entity: values are never merged by similarity, never mapped to municipalities
 * and Records without that field are left out. `nivel3` is not used for
 * grouping in this version (it is already visible in each Record detail).
 */

export const AUTHORITY_GROUP_LABEL = 'Administración convocante (según BDNS)';

export interface AuthorityGroup {
  readonly slug: string;
  readonly name: string;
  readonly records: readonly FrontendRecord[];
}

const MAX_SLUG_LENGTH = 80;

/** Deterministic ASCII slug; returns null when nothing usable remains. */
export function authoritySlug(value: string): string | null {
  const slug = value
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, MAX_SLUG_LENGTH)
    .replace(/-+$/g, '');
  return slug.length > 0 ? slug : null;
}

export function authorityGroups(records: readonly FrontendRecord[]): AuthorityGroup[] {
  const byName = new Map<string, FrontendRecord[]>();
  for (const record of records) {
    if (record.sourceId !== 'bdns') continue;
    const name = record.bdns?.authorityHierarchy?.nivel2;
    if (typeof name !== 'string' || name.trim() === '') continue;
    const bucket = byName.get(name) ?? [];
    bucket.push(record);
    byName.set(name, bucket);
  }

  const slugOwner = new Map<string, string>();
  const groups: AuthorityGroup[] = [];
  for (const [name, groupRecords] of byName) {
    const slug = authoritySlug(name);
    if (slug === null) continue;
    const owner = slugOwner.get(slug);
    if (owner !== undefined && owner !== name) {
      throw new Error(`Organismos: colisión de slug «${slug}» entre dos valores BDNS distintos.`);
    }
    slugOwner.set(slug, name);
    groups.push({ slug, name, records: groupRecords });
  }
  return groups.sort((left, right) =>
    right.records.length - left.records.length || left.name.localeCompare(right.name, 'es'));
}
