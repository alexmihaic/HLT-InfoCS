/** Visible-count text for the record list; also the content of its status region. */
export function recordCountLabel(visible: number, total: number): string {
  return visible === total
    ? `${total} ${total === 1 ? 'registro publicado' : 'registros publicados'}`
    : `${visible} de ${total} registros publicados`;
}
