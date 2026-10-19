import type { FrontendRecord, FrontendTerritorialMatch } from '../data/types';

/**
 * Municipality derived by InfoCs from the exact territorial matches already
 * stored in the canonical Record provenance. It never changes canonical data
 * and is always presented as derived, not as an official field.
 *
 * Rules (conservative, BOE only):
 * - only `municipality_exact` matches from the official INE nomenclator
 *   (method `official_variant…`, INE code 12xxx), found in the official title;
 * - the matched title text must literally equal one official variant of the
 *   municipality name (same capitalisation and accents), so lowercase common
 *   words or unaccented spellings never become a municipality;
 * - exactly one distinct municipality code, otherwise no assignment (ambiguous);
 * - province matches never become a municipality;
 * - "convocante" only when the title opens with the issuing city council of
 *   that municipality ("Resolución de <fecha>, del Ayuntamiento de X…",
 *   "Anuncio del Ayuntamiento de X…", "Edicto del Ayuntamiento de X…");
 *   any other mention is only "relacionado".
 */

export type MunicipalityRole = 'convocante' | 'relacionado';

export interface DerivedMunicipality {
  readonly code: string;
  readonly name: string;
  readonly role: MunicipalityRole;
  readonly label: 'Municipio convocante' | 'Municipio relacionado';
}

const INE_MUNICIPALITY = /^12\d{3}$/;
const ISSUER_PREFIX = /^(?:Resolución de \d{1,2} de [a-záéíóú]+ de \d{4}, del|Anuncio del|Edicto del) Ayuntamiento de /u;

export function derivedMunicipality(record: Pick<FrontendRecord, 'sourceId' | 'title' | 'territorialMatches'>): DerivedMunicipality | null {
  if (record.sourceId !== 'boe') return null;
  const matches = (record.territorialMatches ?? []).filter(isReliableMunicipalityMatch);
  const codes = new Set(matches.map((match) => match.entityCode));
  if (codes.size !== 1) return null;
  const [match] = matches;
  const convocante = matches.some((candidate) => isIssuingCouncil(record.title, candidate.matchedText));
  return {
    code: match.entityCode,
    name: match.entityName,
    role: convocante ? 'convocante' : 'relacionado',
    label: convocante ? 'Municipio convocante' : 'Municipio relacionado',
  };
}

function isReliableMunicipalityMatch(match: FrontendTerritorialMatch): boolean {
  return match.reason === 'municipality_exact'
    && match.field === 'title'
    && match.method.startsWith('official_variant')
    && INE_MUNICIPALITY.test(match.entityCode)
    && match.matchedText.trim() !== ''
    && officialVariants(match.entityName).includes(match.matchedText);
}

function isIssuingCouncil(title: string, matchedText: string): boolean {
  const prefix = ISSUER_PREFIX.exec(title);
  if (!prefix) return false;
  const rest = title.slice(prefix[0].length);
  return rest.startsWith(matchedText) && !/^[\p{L}\p{N}]/u.test(rest.slice(matchedText.length));
}

function officialVariants(name: string): string[] {
  return name.split('/').map((variant) => variant.trim()).filter(Boolean);
}

/** Literal short name for filters (first official variant of the INE name). */
export function municipalityShortName(name: string): string {
  return officialVariants(name)[0] ?? name;
}
