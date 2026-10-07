interface PagefindData {
  readonly url?: unknown;
  readonly plain_excerpt?: unknown;
  readonly meta?: Readonly<Record<string, unknown>>;
}

interface PagefindResult {
  data(): Promise<PagefindData>;
}

interface PagefindApi {
  search(query: string): Promise<{ results: readonly PagefindResult[] }>;
}

const root = document.querySelector<HTMLElement>('[data-search-root]');

if (root) {
  const form = root.querySelector<HTMLFormElement>('form[role="search"]');
  const input = root.querySelector<HTMLInputElement>('#search-query');
  const status = root.querySelector<HTMLElement>('#search-status');
  const empty = root.querySelector<HTMLElement>('#search-empty');
  const results = root.querySelector<HTMLOListElement>('#search-results');

  if (form && input && status && empty && results) {
    const searchInput = input;
    const searchStatus = status;
    const emptyState = empty;
    const resultList = results;
    let pagefindPromise: Promise<PagefindApi> | undefined;
    let requestNumber = 0;

    function getPagefind(): Promise<PagefindApi> {
      pagefindPromise ??= import(/* @vite-ignore */ new URL('/pagefind/pagefind.js', window.location.origin).href) as Promise<PagefindApi>;
      return pagefindPromise;
    }

    function metadataString(meta: Readonly<Record<string, unknown>> | undefined, key: string): string | null {
      const value = meta?.[key];
      return typeof value === 'string' && value.trim().length > 0 ? value.trim() : null;
    }

    function metadataLiteral(meta: Readonly<Record<string, unknown>> | undefined, key: string): string | null {
      const value = meta?.[key];
      return typeof value === 'string' && value.trim().length > 0 ? value : null;
    }

    function publicRecordPath(value: string | null): string | null {
      if (!value) return null;
      try {
        const url = new URL(value, window.location.origin);
        if (url.origin !== window.location.origin || !url.pathname.startsWith('/registro/')) return null;
        return `${url.pathname}${url.search}${url.hash}`;
      } catch {
        return null;
      }
    }

    function appendText(parent: HTMLElement, tagName: keyof HTMLElementTagNameMap, className: string, text: string): HTMLElement {
      const element = document.createElement(tagName);
      if (className) element.className = className;
      element.textContent = text;
      parent.append(element);
      return element;
    }

    function makeResult(data: PagefindData): HTMLLIElement | null {
      const meta = data.meta;
      if (metadataString(meta, 'kind') !== 'record') return null;

      const path = publicRecordPath(metadataString(meta, 'public_url') ?? (typeof data.url === 'string' ? data.url : null));
      const title = metadataString(meta, 'title');
      if (!path || !title) return null;

      const item = document.createElement('li');
      item.className = 'record-card search-result';

      const badges = document.createElement('p');
      badges.className = 'record-meta';
      const source = metadataString(meta, 'source');
      const category = metadataString(meta, 'category');
      if (source) appendText(badges, 'span', 'source-badge', source);
      if (category) appendText(badges, 'span', 'category-badge', category);
      if (badges.childElementCount > 0) item.append(badges);

      const heading = document.createElement('h2');
      const link = document.createElement('a');
      link.href = path;
      link.textContent = title;
      heading.append(link);
      item.append(heading);

      const authority = metadataString(meta, 'authority');
      if (authority) appendText(item, 'p', 'search-result-authority', authority);

      const bdnsCallType = metadataLiteral(meta, 'bdns_call_type');
      const bdnsBudgetDisplay = metadataLiteral(meta, 'bdns_budget_display');
      const bdnsBudgetCurrency = metadataLiteral(meta, 'bdns_budget_currency');
      const bdnsBudgetCurrencyNotice = metadataLiteral(meta, 'bdns_budget_currency_notice');
      if (bdnsCallType || bdnsBudgetDisplay) {
        const summary = document.createElement('dl');
        summary.className = 'record-card-bdns-summary search-result-bdns-summary';
        if (bdnsCallType) {
          const fact = document.createElement('div');
          appendText(fact, 'dt', '', 'Tipo de convocatoria');
          appendText(fact, 'dd', '', bdnsCallType);
          summary.append(fact);
        }
        if (bdnsBudgetDisplay) {
          const fact = document.createElement('div');
          appendText(fact, 'dt', '', 'Presupuesto de la convocatoria');
          const value = document.createElement('dd');
          value.append(document.createTextNode(bdnsBudgetDisplay));
          if (bdnsBudgetCurrency) value.append(document.createTextNode(` · ${bdnsBudgetCurrency}`));
          if (bdnsBudgetCurrencyNotice) appendText(value, 'span', 'muted', bdnsBudgetCurrencyNotice);
          fact.append(value);
          summary.append(fact);
        }
        item.append(summary);
      }

      const dateLabel = metadataString(meta, 'primary_date_label');
      const dateValue = metadataString(meta, 'primary_date_value');
      if (dateLabel && dateValue) {
        const dateLine = document.createElement('p');
        dateLine.className = 'search-result-date';
        const label = document.createElement('span');
        label.className = 'date-label';
        label.textContent = `${dateLabel}: `;
        dateLine.append(label);
        const time = document.createElement('time');
        const dateIso = metadataString(meta, 'primary_date_iso');
        if (dateIso) time.dateTime = dateIso;
        time.textContent = dateValue;
        dateLine.append(time);
        item.append(dateLine);
      }

      if (typeof data.plain_excerpt === 'string' && data.plain_excerpt.trim()) {
        appendText(item, 'p', 'search-result-excerpt', data.plain_excerpt.trim());
      }
      return item;
    }

    async function searchFromUrl(): Promise<void> {
      const currentRequest = ++requestNumber;
      const query = new URLSearchParams(window.location.search).get('q')?.trim() ?? '';
      searchInput.value = query;
      resultList.replaceChildren();

      if (!query) {
        searchStatus.textContent = 'Introduce un término para buscar en las publicaciones oficiales.';
        emptyState.hidden = false;
        emptyState.textContent = 'La búsqueda se realiza en las fichas públicas de registros.';
        return;
      }

      searchStatus.textContent = 'Buscando en las publicaciones…';
      emptyState.hidden = true;

      try {
        const pagefind = await getPagefind();
        const search = await pagefind.search(query);
        const data = await Promise.all(search.results.map((result) => result.data()));
        if (currentRequest !== requestNumber) return;

        const items = data.map(makeResult).filter((item): item is HTMLLIElement => item !== null);
        resultList.replaceChildren(...items);
        if (items.length === 0) {
          searchStatus.textContent = `No se encontraron resultados para «${query}».`;
          emptyState.textContent = 'Prueba con otros términos presentes en las publicaciones.';
          emptyState.hidden = false;
        } else {
          searchStatus.textContent = `${items.length} ${items.length === 1 ? 'resultado' : 'resultados'} para «${query}».`;
          emptyState.hidden = true;
        }
      } catch {
        if (currentRequest !== requestNumber) return;
        searchStatus.textContent = 'No se pudo cargar el índice de búsqueda.';
        emptyState.textContent = 'Vuelve a intentarlo más tarde.';
        emptyState.hidden = false;
      }
    }

    window.addEventListener('popstate', () => void searchFromUrl());
    window.addEventListener('pageshow', (event) => {
      if (event.persisted) void searchFromUrl();
    });
    void searchFromUrl();
  }
}
