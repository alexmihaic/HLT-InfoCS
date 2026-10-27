/** Shared shapes for the BDNS presentation view. Types only: no runtime import. */

/** Values remain official; labels, formatting and paths are presentation-derived. */
export interface BDNSOfficialView {
  readonly origin: 'official';
  readonly label: string;
  readonly canonicalPath: string;
}

export interface BDNSTextView extends BDNSOfficialView {
  readonly value: string;
}

export interface BDNSDateView extends BDNSOfficialView {
  readonly value: string;
  readonly display: string;
}

/** Literal extract metadata. The source locator is deliberately not rendered in 03B-1. */
export interface BDNSExtractView {
  readonly canonicalPath: string;
  readonly diary?: BDNSTextView;
  readonly publicationDate?: BDNSDateView;
  readonly title?: BDNSTextView;
  readonly titleCoofficial?: BDNSTextView;
  readonly cve?: BDNSTextView;
}

export interface BDNSExtractsView extends BDNSOfficialView {
  readonly items: readonly BDNSExtractView[];
}
