import { matchesRecordFilters, recordCountLabel, sanitizeFilterValue, sanitizeFilterDate, type RecordFilterSelection } from '../lib/presentation/recordFilters';

const form = document.querySelector<HTMLFormElement>('[data-record-filters]');
const list = document.querySelector<HTMLElement>('[data-record-list]');
if (form && list) {
  const count = document.querySelector<HTMLElement>('[data-record-count]');
  const empty = document.querySelector<HTMLElement>('[data-filter-empty]');
  const error = document.querySelector<HTMLElement>('#filter-date-error');
  const reset = form.querySelector<HTMLButtonElement>('[data-filter-reset]');
  const fields = { tipo: 'category', convocatoria: 'callType', municipio: 'municipality', organismo: 'authority', fuente: 'source', desde: 'from', hasta: 'to' } as const;
  const controls = [...form.querySelectorAll<HTMLSelectElement | HTMLInputElement>('select, input')];
  const items = [...list.querySelectorAll<HTMLLIElement>(':scope > li')].map(element => ({ element, attributes: { category: element.dataset.category, callType: element.dataset.calltype, municipality: element.dataset.municipality, authority: element.dataset.authority, source: element.dataset.source, date: element.dataset.date } }));
  const labels = new Map<HTMLOptionElement, string>();
  controls.forEach(control => { if (control instanceof HTMLSelectElement) [...control.options].forEach(option => labels.set(option, option.textContent!.replace(/ \(\d+\)$/, ''))); });
  const restore = () => {
    const params = new URLSearchParams(location.search);
    for (const control of controls) {
      // Duplicate parameters are ambiguous, so discard them.
      const value = params.getAll(control.name).length === 1 ? params.get(control.name) : null;
      control.value = control instanceof HTMLSelectElement ? sanitizeFilterValue(value, [...control.options].map(option => option.value)) : sanitizeFilterDate(value);
    }
  };
  const apply = (mode: 'push' | 'replace' | 'none') => {
    controls.forEach(control => { if (control instanceof HTMLInputElement) control.value = sanitizeFilterDate(control.value); });
    const selection: RecordFilterSelection = { category: '', municipality: '', callType: '', ...Object.fromEntries(controls.map(control => [fields[control.name as keyof typeof fields], control.value])) };
    const reversed = !!selection.from && !!selection.to && selection.from > selection.to;
    if (error) error.hidden = !reversed;
    controls.filter(control => control instanceof HTMLInputElement).forEach(control => control.setAttribute('aria-invalid', String(reversed)));
    let visible = 0;
    for (const { element, attributes } of items) {
      element.hidden = !matchesRecordFilters(attributes, selection);
      if (!element.hidden) visible++;
    }
    if (count) { const text = recordCountLabel(visible, items.length); if (count.textContent !== text) count.textContent = text; }
    if (empty) empty.hidden = visible !== 0;
    if (reset) reset.hidden = !controls.some(control => control.value);
    // Counts hold every other field fixed and substitute only this option.
    for (const control of controls) {
      if (!(control instanceof HTMLSelectElement)) continue;
      const key = fields[control.name as keyof typeof fields];
      for (const option of control.options) {
        const matches = items.filter(item => matchesRecordFilters(item.attributes, { ...selection, [key]: option.value })).length;
        option.textContent = `${labels.get(option)} (${matches})`;
      }
    }
    if (mode !== 'none') {
      const params = new URLSearchParams();
      controls.forEach(control => { if (control.value) params.set(control.name, control.value); });
      const query = params.toString();
      const url = `${location.pathname}${query ? `?${query}` : ''}${location.hash}`;
      if (url !== `${location.pathname}${location.search}${location.hash}`) history[mode === 'push' ? 'pushState' : 'replaceState'](null, '', url);
    }
  };
  reset?.addEventListener('click', () => { controls.forEach(control => control.value = ''); apply('push'); controls[0]?.focus(); });
  form.addEventListener('change', () => apply('push'));
  form.addEventListener('submit', event => { event.preventDefault(); apply('push'); });
  window.addEventListener('popstate', () => { restore(); apply('none'); });
  restore();
  apply('replace');
}
