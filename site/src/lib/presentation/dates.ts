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
