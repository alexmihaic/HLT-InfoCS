const DATE_FORMATTER = new Intl.DateTimeFormat('es-ES', {
  day: 'numeric',
  month: 'long',
  year: 'numeric',
  timeZone: 'UTC',
});

/** Display the ISO calendar date without shifting it across time zones. */
export function formatPortalDate(value: string): string {
  const calendarDate = value.slice(0, 10);
  const date = new Date(`${calendarDate}T00:00:00Z`);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(calendarDate) || Number.isNaN(date.getTime())) {
    throw new Error('Fecha incompatible para presentación.');
  }
  return DATE_FORMATTER.format(date);
}

const DATE_TIME_FORMATTER = new Intl.DateTimeFormat('es-ES', {
  day: 'numeric',
  month: 'long',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  timeZone: 'Europe/Madrid',
  timeZoneName: 'short',
});

/** Display an InfoCs system timestamp (not an official date) in Madrid time. */
export function formatPortalDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) throw new Error('Marca temporal incompatible para presentación.');
  return DATE_TIME_FORMATTER.format(date);
}

const DATE_TIME_SHORT_FORMATTER = new Intl.DateTimeFormat('es-ES', {
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
  timeZone: 'Europe/Madrid',
});

/** Compact InfoCs system timestamp (Madrid time) for dense layouts; the full form stays in `title`. */
export function formatPortalDateTimeShort(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) throw new Error('Marca temporal incompatible para presentación.');
  return DATE_TIME_SHORT_FORMATTER.format(date);
}
