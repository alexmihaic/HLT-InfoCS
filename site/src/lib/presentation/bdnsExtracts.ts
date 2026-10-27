import type { FrontendBDNSExtract } from '../data/types';
import type { BDNSDateView, BDNSExtractView, BDNSExtractsView, BDNSOfficialView, BDNSTextView } from './bdnsViewTypes';

/** Presentation helpers supplied by the caller so this module stays dependency-free. */
export interface BDNSViewFactory {
  readonly officialGroup: (label: string, canonicalPath: string) => BDNSOfficialView;
  readonly textView: (label: string, value: string, canonicalPath: string) => BDNSTextView;
  readonly dateView: (label: string, value: string, canonicalPath: string) => BDNSDateView;
}

/**
 * Projects only the official extract metadata that can be displayed. Empty lists,
 * an extract with no readable metadata, or a title that merely repeats the page
 * title never produce a section or a fabricated extract.
 */
export function buildBDNSExtractsView(
  data: readonly FrontendBDNSExtract[],
  recordTitle: string,
  factory: BDNSViewFactory,
  basePath = 'source_data.bdns.extracts',
): BDNSExtractsView {
  const items = data
    .map((extract, index) => extractView(extract, index, recordTitle, factory, basePath))
    .filter((extract) => extract.diary !== undefined || extract.publicationDate !== undefined
      || extract.title !== undefined || extract.titleCoofficial !== undefined || extract.cve !== undefined);
  return { ...factory.officialGroup('Extractos publicados en diarios oficiales', basePath), items };
}

function extractView(
  data: FrontendBDNSExtract,
  index: number,
  recordTitle: string,
  factory: BDNSViewFactory,
  basePath: string,
): BDNSExtractView {
  // Indexed paths refer to the supplied canonical order, not a ranking or new ID.
  const path = `${basePath}[${index}]`;
  // An extract title that only repeats the page title adds no information.
  const title = sameVisibleText(data.title, recordTitle) ? undefined : data.title;
  return {
    canonicalPath: path,
    ...(data.diary !== undefined ? { diary: factory.textView('Diario oficial', data.diary, `${path}.diary`) } : {}),
    ...(data.publicationDate !== undefined
      ? { publicationDate: factory.dateView('Fecha del extracto', data.publicationDate, `${path}.publication_date`) }
      : {}),
    ...(title !== undefined ? { title: factory.textView('Título del extracto', title, `${path}.title`) } : {}),
    ...(data.titleCoofficial !== undefined
      ? { titleCoofficial: factory.textView('Título del extracto en otra lengua', data.titleCoofficial, `${path}.title_coofficial`) }
      : {}),
    ...(data.cve !== undefined ? { cve: factory.textView('CVE', data.cve, `${path}.cve`) } : {}),
  };
}

function sameVisibleText(left: string | undefined, right: string): boolean {
  if (left === undefined) return false;
  return left.replace(/\s+/gu, ' ').trim() === right.replace(/\s+/gu, ' ').trim();
}
