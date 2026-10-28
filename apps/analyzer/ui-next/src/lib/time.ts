/**
 * Server timestamps are ISO strings. Older reports carry no UTC offset (the server
 * wrote its local time, which on the hosted deploy is UTC); the browser would read
 * those as *its own* local time and show them shifted. Treat an offset-less stamp as UTC.
 */
export function parseServerDate(value?: string | null): Date | null {
  if (!value) return null;
  const hasZone = /([zZ]|[+-]\d{2}:?\d{2})$/.test(value);
  const date = new Date(hasZone || !/T\d/.test(value) ? value : `${value}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatDateTime(value?: string | null): string {
  const date = parseServerDate(value);
  return date ? date.toLocaleString() : value ? String(value) : "—";
}

export function formatDate(value?: string | null): string {
  const date = parseServerDate(value);
  return date ? date.toLocaleDateString() : value ? String(value) : "—";
}
