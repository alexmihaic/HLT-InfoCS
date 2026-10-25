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

export interface SystemTimestampView {
  /** Machine-readable value for `<time datetime>`; absent when the stored value is not a valid instant. */
  readonly dateTime?: string;
  readonly text: string;
}

/** Date-time that declares its own zone: a trailing `Z` or a numeric offset after the time part (never the date's hyphens). */
const EXPLICIT_ZONE_TIMESTAMP = /^(\d{4})-(\d{2})-(\d{2})T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})$/i;

/** `Date` rolls impossible days (30 February) over to the next month, so the calendar date is checked first. */
function isRealCalendarDate(year: number, month: number, day: number): boolean {
  const leap = (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
  const daysInMonth = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return month >= 1 && month <= 12 && day >= 1 && day <= daysInMonth[month - 1]!;
}

/**
 * Presents a stored InfoCs timestamp without altering it. A missing value shows
 * a neutral placeholder. Values that are unparseable or declare no zone (a bare
 * date, or a date-time without `Z`/offset) are kept literally: converting them
 * would invent a time or depend on the build machine's time zone.
 */
export function describeSystemTimestamp(value: string | undefined | null): SystemTimestampView {
  if (typeof value !== 'string' || value.trim() === '') return { text: 'No disponible' };
  const parts = EXPLICIT_ZONE_TIMESTAMP.exec(value);
  if (!parts || !isRealCalendarDate(Number(parts[1]), Number(parts[2]), Number(parts[3])) || Number.isNaN(new Date(value).getTime())) {
    return { text: value };
  }
  return { dateTime: value, text: formatPortalDateTime(value) };
}
